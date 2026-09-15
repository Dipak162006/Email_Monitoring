import email.utils
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from datetime import datetime, timezone
import logging
from typing import List, Optional, Tuple
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.auth.models import User
from app.modules.companies.service import CompanyService
from app.modules.email_accounts.models import EmailAccount
from app.modules.email_accounts.service import EmailAccountService
from app.modules.emails.mailbox_service import EmailMailboxService
from app.modules.emails.models import Email, EmailDirection, EmailStatus, EmailThread
from app.modules.emails.schemas import EmailDraftCreate, EmailDraftUpdate
from app.modules.emails.thread_service import EmailThreadService
from app.services.smtp.adapter import BaseSMTPAdapter, StandardSMTPAdapter
from app.services.smtp.exceptions import (
    SMTPAuthenticationError,
    SMTPConfigurationError,
    SMTPConnectionError,
    SMTPRecipientRejectedError,
    SMTPSendError,
    SMTPServiceException,
)

logger = logging.getLogger(__name__)


class EmailDraftService:
    """Service handling composition and draft management lifecycle:
    creation, retrieval, updates/autosave, discard (soft-delete), and sending.
    """

    @classmethod
    async def create_draft(
        cls,
        db: AsyncSession,
        current_user: User,
        draft_in: EmailDraftCreate,
        company_id: Optional[int] = None,
    ) -> Email:
        """Create a new work-in-progress draft email.
        
        Drafts allow partial addressing and content. Sender is derived strictly
        from the authorized EmailAccount. Draft creation does not alter thread metrics.
        """
        # 1. Fetch account and verify user authorization
        account = await EmailAccountService.get_email_account(db, draft_in.email_account_id)
        if not account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Email account not found.",
            )

        if company_id is not None and account.company_id != company_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Email account does not belong to the specified company.",
            )

        membership = await CompanyService.get_user_membership(
            db=db,
            company_id=account.company_id,
            user_id=current_user.id,
        )
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not belong to the company that owns this email account.",
            )

        has_access = await EmailAccountService.check_user_access(
            db=db,
            account=account,
            user_id=current_user.id,
            user_role=membership.role,
        )
        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this email account.",
            )

        # 2. Validate Thread references if drafting a reply
        validated_thread_id: Optional[int] = None
        validated_in_reply_to: Optional[str] = None

        if draft_in.thread_id is not None:
            thread_stmt = select(EmailThread).where(EmailThread.id == draft_in.thread_id)
            thread_res = await db.execute(thread_stmt)
            thread = thread_res.scalars().first()
            if not thread:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Conversation thread {draft_in.thread_id} not found.",
                )
            if thread.company_id != account.company_id or thread.email_account_id != account.id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Cannot draft a reply to a thread belonging to a different email account or company.",
                )
            validated_thread_id = thread.id

            if draft_in.in_reply_to:
                clean_in_reply_to = draft_in.in_reply_to.strip()
                p_stmt = select(Email).where(
                    Email.email_account_id == account.id,
                    Email.message_id == clean_in_reply_to,
                    Email.thread_id == thread.id,
                )
                p_res = await db.execute(p_stmt)
                parent_email = p_res.scalars().first()
                if not parent_email:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Referenced in_reply_to email does not exist in the specified thread.",
                    )
                validated_in_reply_to = clean_in_reply_to
        elif draft_in.in_reply_to:
            clean_in_reply_to = draft_in.in_reply_to.strip()
            p_stmt = select(Email).where(
                Email.email_account_id == account.id,
                Email.message_id == clean_in_reply_to,
            )
            p_res = await db.execute(p_stmt)
            parent_email = p_res.scalars().first()
            if not parent_email:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Referenced in_reply_to email '{draft_in.in_reply_to}' not found in this account.",
                )
            validated_in_reply_to = clean_in_reply_to
            if parent_email.thread_id:
                validated_thread_id = parent_email.thread_id

        # 3. Derive Authoritative From Address
        sender_display = formataddr((account.name, account.email_address)) if account.name else account.email_address

        # 4. Construct Email in DRAFT status
        to_recipients = [str(addr) for addr in draft_in.to] if draft_in.to else []
        cc_recipients = [str(addr) for addr in draft_in.cc] if draft_in.cc else None
        bcc_recipients = [str(addr) for addr in draft_in.bcc] if draft_in.bcc else None

        draft = Email(
            company_id=account.company_id,
            email_account_id=account.id,
            user_id=current_user.id,
            thread_id=validated_thread_id,
            in_reply_to=validated_in_reply_to,
            direction=EmailDirection.OUTGOING.value,
            status=EmailStatus.DRAFT.value,
            sender=sender_display,
            recipients=to_recipients,
            cc=cc_recipients,
            bcc=bcc_recipients,
            reply_to=str(draft_in.reply_to) if draft_in.reply_to else None,
            subject=draft_in.subject or "",
            body_text=draft_in.body_text,
            body_html=draft_in.body_html,
            is_read=True,
            is_starred=False,
            is_deleted=False,
            sent_at=None,
            error_message=None,
        )

        db.add(draft)
        await db.commit()
        await db.refresh(draft)
        logger.info("Created draft id=%d for account id=%d by user id=%d", draft.id, account.id, current_user.id)
        return draft

    @classmethod
    async def get_draft(
        cls,
        db: AsyncSession,
        current_user: User,
        draft_id: int,
        company_id: Optional[int] = None,
    ) -> Email:
        """Retrieve an active draft by ID ensuring authorization."""
        draft = await db.get(Email, draft_id)
        if not draft or draft.status != EmailStatus.DRAFT.value or draft.is_deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Draft not found.",
            )

        if company_id is not None and draft.company_id != company_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Draft does not belong to the specified company.",
            )

        membership = await CompanyService.get_user_membership(
            db=db,
            company_id=draft.company_id,
            user_id=current_user.id,
        )
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this draft.",
            )

        account = await EmailAccountService.get_email_account(db, draft.email_account_id)
        if not account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Associated email account not found.",
            )

        has_access = await EmailAccountService.check_user_access(
            db=db,
            account=account,
            user_id=current_user.id,
            user_role=membership.role,
        )
        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this draft.",
            )

        return draft

    @classmethod
    async def update_draft(
        cls,
        db: AsyncSession,
        current_user: User,
        draft_id: int,
        draft_update: EmailDraftUpdate,
        company_id: Optional[int] = None,
    ) -> Email:
        """Update an existing draft message with partial fields or autosave data."""
        draft = await db.get(Email, draft_id)
        if not draft:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Draft not found.",
            )

        if company_id is not None and draft.company_id != company_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Draft does not belong to the specified company.",
            )

        if draft.status != EmailStatus.DRAFT.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only draft emails can be edited.",
            )

        if draft.is_deleted:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot edit a deleted draft. Restore it first.",
            )

        # Check permission on current account
        membership = await CompanyService.get_user_membership(
            db=db,
            company_id=draft.company_id,
            user_id=current_user.id,
        )
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this draft.",
            )

        current_account = await EmailAccountService.get_email_account(db, draft.email_account_id)
        if not current_account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Associated email account not found.",
            )

        has_access = await EmailAccountService.check_user_access(
            db=db,
            account=current_account,
            user_id=current_user.id,
            user_role=membership.role,
        )
        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this draft.",
            )

        # Handle account change if requested
        active_account = current_account
        if (
            draft_update.email_account_id is not None
            and draft_update.email_account_id != draft.email_account_id
        ):
            new_account = await EmailAccountService.get_email_account(db, draft_update.email_account_id)
            if not new_account:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="New email account not found.",
                )

            if new_account.company_id != draft.company_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot reassign draft to an email account in another company.",
                )

            new_has_access = await EmailAccountService.check_user_access(
                db=db,
                account=new_account,
                user_id=current_user.id,
                user_role=membership.role,
            )
            if not new_has_access:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You do not have permission to access the new email account.",
                )

            active_account = new_account
            draft.email_account_id = new_account.id
            draft.sender = formataddr((new_account.name, new_account.email_address)) if new_account.name else new_account.email_address

        # Validate thread reference updates
        target_thread_id = draft_update.thread_id if draft_update.thread_id is not None else draft.thread_id
        target_in_reply_to = draft_update.in_reply_to if draft_update.in_reply_to is not None else draft.in_reply_to

        if draft_update.thread_id is not None:
            thread_stmt = select(EmailThread).where(EmailThread.id == draft_update.thread_id)
            thread_res = await db.execute(thread_stmt)
            thread = thread_res.scalars().first()
            if not thread:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Conversation thread {draft_update.thread_id} not found.",
                )
            if thread.company_id != active_account.company_id or thread.email_account_id != active_account.id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Conversation thread does not belong to the selected email account.",
                )
            draft.thread_id = thread.id

        if draft_update.in_reply_to is not None:
            clean_ref = draft_update.in_reply_to.strip() if draft_update.in_reply_to else None
            if clean_ref:
                p_stmt = select(Email).where(
                    Email.email_account_id == active_account.id,
                    Email.message_id == clean_ref,
                )
                p_res = await db.execute(p_stmt)
                parent_email = p_res.scalars().first()
                if not parent_email:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Referenced in_reply_to email '{clean_ref}' not found in this account.",
                    )
                draft.in_reply_to = clean_ref
            else:
                draft.in_reply_to = None

        # Apply content updates
        if draft_update.to is not None:
            draft.recipients = [str(r) for r in draft_update.to]
        if draft_update.cc is not None:
            draft.cc = [str(r) for r in draft_update.cc]
        if draft_update.bcc is not None:
            draft.bcc = [str(r) for r in draft_update.bcc]
        if draft_update.subject is not None:
            draft.subject = draft_update.subject
        if draft_update.body_text is not None:
            draft.body_text = draft_update.body_text
        if draft_update.body_html is not None:
            draft.body_html = draft_update.body_html
        if draft_update.reply_to is not None:
            draft.reply_to = str(draft_update.reply_to) if draft_update.reply_to else None

        await db.commit()
        await db.refresh(draft)
        logger.info("Updated draft id=%d", draft.id)
        return draft

    @classmethod
    async def discard_draft(
        cls,
        db: AsyncSession,
        current_user: User,
        draft_id: int,
        company_id: Optional[int] = None,
    ) -> Email:
        """Discard a draft by soft-deleting it into Trash via the existing M8 lifecycle."""
        draft = await db.get(Email, draft_id)
        if not draft:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Draft not found.",
            )

        if company_id is not None and draft.company_id != company_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Draft does not belong to the specified company.",
            )

        if draft.status != EmailStatus.DRAFT.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only draft emails can be discarded through this endpoint.",
            )

        if draft.is_deleted:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Draft is already discarded.",
            )

        membership = await CompanyService.get_user_membership(
            db=db,
            company_id=draft.company_id,
            user_id=current_user.id,
        )
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this draft.",
            )

        account = await EmailAccountService.get_email_account(db, draft.email_account_id)
        if not account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Associated email account not found.",
            )

        has_access = await EmailAccountService.check_user_access(
            db=db,
            account=account,
            user_id=current_user.id,
            user_role=membership.role,
        )
        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this draft.",
            )

        return await EmailMailboxService.soft_delete_email(db, draft)

    @classmethod
    async def send_draft(
        cls,
        db: AsyncSession,
        current_user: User,
        draft_id: int,
        smtp_adapter: Optional[BaseSMTPAdapter] = None,
        company_id: Optional[int] = None,
    ) -> Email:
        """Transmit an existing draft via SMTP, preventing concurrent sends with a row lock.
        
        On success: transitions status to SENT, sets sent_at, generates Message-ID,
        and updates conversation thread metrics.
        On failure: reverts status to DRAFT and persists sanitized error_message to keep
        the draft editable.
        """
        # 1. Acquire row lock and validate draft send readiness
        stmt = select(Email).where(Email.id == draft_id).with_for_update()
        res = await db.execute(stmt)
        draft = res.scalars().first()
        if not draft:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Draft not found.",
            )

        if company_id is not None and draft.company_id != company_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Draft does not belong to the specified company.",
            )

        if draft.status == EmailStatus.SENDING.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Draft is already being sent.",
            )

        if draft.status != EmailStatus.DRAFT.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot send email with status '{draft.status}'. Only DRAFT emails can be sent.",
            )

        if draft.is_deleted:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot send a deleted draft. Restore it first.",
            )

        # Verify company & account access
        membership = await CompanyService.get_user_membership(
            db=db,
            company_id=draft.company_id,
            user_id=current_user.id,
        )
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not belong to the company that owns this email account.",
            )

        account = await EmailAccountService.get_email_account(db, draft.email_account_id)
        if not account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Email account not found.",
            )

        has_access = await EmailAccountService.check_user_access(
            db=db,
            account=account,
            user_id=current_user.id,
            user_role=membership.role,
        )
        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to send emails from this email account.",
            )

        if not account.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email account is inactive and cannot be used for sending.",
            )

        if not account.smtp_host:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email account does not have an SMTP host configured.",
            )

        # Validate send prerequisites: recipients and body
        if not draft.recipients or len(draft.recipients) == 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="At least one recipient must be provided before sending.",
            )

        has_text = bool(draft.body_text and draft.body_text.strip())
        has_html = bool(draft.body_html and draft.body_html.strip())
        if not has_text and not has_html:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="At least one of body_text or body_html must be provided and non-empty.",
            )

        # 2. Concurrency state transition: DRAFT -> SENDING
        draft.status = EmailStatus.SENDING.value
        await db.commit()
        await db.refresh(draft)

        # 3. Resolve or Create Conversation Thread & parent references
        thread: Optional[EmailThread] = None
        parent_email: Optional[Email] = None

        if draft.thread_id is not None:
            t_stmt = select(EmailThread).where(EmailThread.id == draft.thread_id)
            t_res = await db.execute(t_stmt)
            thread = t_res.scalars().first()

            if draft.in_reply_to:
                p_stmt = select(Email).where(
                    Email.email_account_id == account.id,
                    Email.message_id == draft.in_reply_to.strip(),
                )
                p_res = await db.execute(p_stmt)
                parent_email = p_res.scalars().first()
        elif draft.in_reply_to:
            p_stmt = select(Email).where(
                Email.email_account_id == account.id,
                Email.message_id == draft.in_reply_to.strip(),
            )
            p_res = await db.execute(p_stmt)
            parent_email = p_res.scalars().first()
            if parent_email and parent_email.thread_id:
                t_stmt = select(EmailThread).where(EmailThread.id == parent_email.thread_id)
                t_res = await db.execute(t_stmt)
                thread = t_res.scalars().first()

        # If still no thread (original draft), resolve or create one now
        if not thread:
            thread, parent_email = await EmailThreadService.resolve_or_create_outgoing_thread(
                db=db,
                account=account,
                requested_thread_id=None,
                in_reply_to=draft.in_reply_to,
                subject=draft.subject,
                body_text=draft.body_text,
                body_html=draft.body_html,
            )

        # 4. Build MIME message
        mime_msg = EmailMessage()
        sender_display = formataddr((account.name, account.email_address)) if account.name else account.email_address
        mime_msg["From"] = sender_display

        to_addrs = [str(r) for r in draft.recipients]
        mime_msg["To"] = ", ".join(to_addrs)

        cc_addrs: Optional[List[str]] = None
        if draft.cc:
            cc_addrs = [str(r) for r in draft.cc]
            mime_msg["Cc"] = ", ".join(cc_addrs)

        bcc_addrs: Optional[List[str]] = None
        if draft.bcc:
            bcc_addrs = [str(r) for r in draft.bcc]
            # BCC not placed in public MIME headers to preserve privacy

        if draft.reply_to:
            mime_msg["Reply-To"] = str(draft.reply_to)

        mime_msg["Subject"] = draft.subject or ""
        domain = account.email_address.split("@")[-1] if "@" in account.email_address else "localhost"
        message_id = make_msgid(domain=domain)
        mime_msg["Message-ID"] = message_id
        mime_msg["Date"] = email.utils.formatdate(localtime=True)

        in_reply_to_val = draft.in_reply_to or (parent_email.message_id if parent_email else None)
        references_val: Optional[str] = None
        if in_reply_to_val:
            mime_msg["In-Reply-To"] = in_reply_to_val
            parent_refs: List[str] = []
            if parent_email and parent_email.references_header:
                parent_refs = EmailThreadService.extract_message_ids(parent_email.references_header)
            elif parent_email and parent_email.in_reply_to:
                parent_refs = EmailThreadService.extract_message_ids(parent_email.in_reply_to)

            combined_refs = list(parent_refs)
            if in_reply_to_val not in combined_refs:
                combined_refs.append(in_reply_to_val)
            references_val = " ".join(combined_refs)
            mime_msg["References"] = references_val

        if draft.body_text and draft.body_html:
            mime_msg.set_content(draft.body_text)
            mime_msg.add_alternative(draft.body_html, subtype="html")
        elif draft.body_html:
            mime_msg.set_content(draft.body_html, subtype="html")
        else:
            mime_msg.set_content(draft.body_text or "")

        all_recipients: List[str] = []
        for r in to_addrs + (cc_addrs or []) + (bcc_addrs or []):
            if r not in all_recipients:
                all_recipients.append(r)

        adapter = smtp_adapter or StandardSMTPAdapter()

        # 5. Attempt SMTP transmission
        try:
            await adapter.send(
                account=account,
                message=mime_msg,
                envelope_recipients=all_recipients,
            )

            # Success: Finalize Email and Thread state
            draft_res = await db.execute(select(Email).where(Email.id == draft_id))
            sent_draft = draft_res.scalars().first()

            thread_res = await db.execute(select(EmailThread).where(EmailThread.id == thread.id))
            target_thread = thread_res.scalars().first()

            sent_draft.status = EmailStatus.SENT.value
            sent_draft.sent_at = datetime.now(timezone.utc)
            sent_draft.message_id = message_id
            sent_draft.in_reply_to = in_reply_to_val
            sent_draft.references_header = references_val
            sent_draft.error_message = None
            sent_draft.thread_id = target_thread.id

            is_reply_to_incoming = bool(parent_email and parent_email.direction == EmailDirection.INCOMING.value)
            EmailThreadService.attach_email_to_thread(target_thread, sent_draft, is_reply_to_outgoing=False)

            await db.commit()
            await db.refresh(sent_draft)
            logger.info("Successfully sent draft id=%d (Message-ID: %s)", sent_draft.id, message_id)
            return sent_draft

        except Exception as exc:
            # Failure: Revert draft status to DRAFT and record sanitized error_message
            safe_error_msg = getattr(exc, "safe_message", "Failed to transmit message via SMTP.")
            logger.warning("SMTP sending failure for draft id=%d: %s", draft_id, safe_error_msg)

            draft_res = await db.execute(select(Email).where(Email.id == draft_id))
            failed_draft = draft_res.scalars().first()
            if failed_draft:
                failed_draft.status = EmailStatus.DRAFT.value
                failed_draft.error_message = safe_error_msg
                await db.commit()
                await db.refresh(failed_draft)

            if isinstance(exc, SMTPConfigurationError):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=safe_error_msg)
            elif isinstance(exc, (SMTPAuthenticationError, SMTPConnectionError, SMTPRecipientRejectedError, SMTPSendError, SMTPServiceException)):
                raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=safe_error_msg)
            else:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="SMTP server error during email transmission.",
                )
