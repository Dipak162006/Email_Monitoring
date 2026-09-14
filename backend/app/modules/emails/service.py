from datetime import datetime, timezone
import email.utils
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
import logging
from typing import List, Optional, Tuple
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.auth.models import User
from app.modules.email_accounts.models import EmailAccount
from app.modules.emails.models import Email, EmailDirection, EmailStatus, EmailThread
from app.modules.emails.schemas import EmailSendRequest
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


class EmailService:
    """Service orchestrating email message construction, authorization verification,
    SMTP transmission, and database audit persistence.
    """

    def __init__(self, smtp_adapter: Optional[BaseSMTPAdapter] = None):
        self.smtp_adapter = smtp_adapter or StandardSMTPAdapter()

    @staticmethod
    def build_mime_message(
        account: EmailAccount,
        send_req: EmailSendRequest,
        parent_email: Optional[Email] = None,
    ) -> Tuple[EmailMessage, str, List[str], Optional[str], Optional[str]]:
        """Construct a standardized MIME EmailMessage instance from account settings and send request.
        
        Returns:
            Tuple containing (EmailMessage, generated_message_id, envelope_recipients_list, in_reply_to, references)
        """
        msg = EmailMessage()

        # 1. Authoritative From Address (derived exclusively from server-side EmailAccount)
        sender_display = formataddr((account.name, account.email_address)) if account.name else account.email_address
        msg["From"] = sender_display

        # 2. Destination Headers
        to_addrs = [str(addr) for addr in send_req.to]
        msg["To"] = ", ".join(to_addrs)

        cc_addrs: Optional[List[str]] = None
        if send_req.cc:
            cc_addrs = [str(addr) for addr in send_req.cc]
            msg["Cc"] = ", ".join(cc_addrs)

        bcc_addrs: Optional[List[str]] = None
        if send_req.bcc:
            bcc_addrs = [str(addr) for addr in send_req.bcc]
            # Note: BCC is deliberately NOT placed in public MIME headers to preserve privacy

        if send_req.reply_to:
            msg["Reply-To"] = str(send_req.reply_to)

        # 3. Subject & Identification Headers
        msg["Subject"] = send_req.subject or ""
        domain = account.email_address.split("@")[-1] if "@" in account.email_address else "localhost"
        message_id = make_msgid(domain=domain)
        msg["Message-ID"] = message_id
        msg["Date"] = email.utils.formatdate(localtime=True)

        # Threading Headers (In-Reply-To and References)
        in_reply_to_val = send_req.in_reply_to or (parent_email.message_id if parent_email else None)
        references_val: Optional[str] = None
        if in_reply_to_val:
            msg["In-Reply-To"] = in_reply_to_val
            # Construct References from parent's references + parent's message_id without duplicates
            parent_refs: List[str] = []
            if parent_email and parent_email.references_header:
                parent_refs = EmailThreadService.extract_message_ids(parent_email.references_header)
            elif parent_email and parent_email.in_reply_to:
                parent_refs = EmailThreadService.extract_message_ids(parent_email.in_reply_to)

            combined_refs = list(parent_refs)
            if in_reply_to_val not in combined_refs:
                combined_refs.append(in_reply_to_val)
            references_val = " ".join(combined_refs)
            msg["References"] = references_val

        # 4. Message Bodies (Text and/or HTML)
        if send_req.body_text and send_req.body_html:
            msg.set_content(send_req.body_text)
            msg.add_alternative(send_req.body_html, subtype="html")
        elif send_req.body_html:
            msg.set_content(send_req.body_html, subtype="html")
        else:
            msg.set_content(send_req.body_text or "")

        # 5. Build full envelope recipient list (deduplicated while preserving order)
        all_recipients: List[str] = []
        for r in to_addrs + (cc_addrs or []) + (bcc_addrs or []):
            if r not in all_recipients:
                all_recipients.append(r)

        return msg, message_id, all_recipients, in_reply_to_val, references_val

    async def send_email(
        self,
        db: AsyncSession,
        current_user: Optional[User],
        account: EmailAccount,
        send_req: EmailSendRequest,
    ) -> Email:
        """Construct, transmit, and record an outgoing email message.
        
        Persists an Email record in the database with status SENT upon successful transmission,
        or status FAILED upon any transport or connection failure before raising an HTTPException.
        """
        # 1. Validate Account State & Configuration
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

        # 2. Resolve or Create Conversation Thread
        thread, parent_email = await EmailThreadService.resolve_or_create_outgoing_thread(
            db=db,
            account=account,
            requested_thread_id=send_req.thread_id,
            in_reply_to=send_req.in_reply_to,
            subject=send_req.subject,
            body_text=send_req.body_text,
            body_html=send_req.body_html,
        )

        # 3. Build MIME Message
        mime_msg, message_id, envelope_recipients, in_reply_to_val, references_val = self.build_mime_message(
            account=account,
            send_req=send_req,
            parent_email=parent_email,
        )
        to_list = [str(r) for r in send_req.to]
        cc_list = [str(r) for r in send_req.cc] if send_req.cc else None
        bcc_list = [str(r) for r in send_req.bcc] if send_req.bcc else None
        sender_str = str(mime_msg["From"])

        # 4. Attempt SMTP Transmission
        try:
            await self.smtp_adapter.send(
                account=account,
                message=mime_msg,
                envelope_recipients=envelope_recipients,
            )

            # Record successful transmission
            email_record = Email(
                company_id=account.company_id,
                email_account_id=account.id,
                thread_id=thread.id,
                user_id=current_user.id if current_user else None,
                message_id=message_id,
                in_reply_to=in_reply_to_val,
                references_header=references_val,
                direction=EmailDirection.OUTGOING.value,
                status=EmailStatus.SENT.value,
                sender=sender_str,
                recipients=to_list,
                cc=cc_list,
                bcc=bcc_list,
                reply_to=str(send_req.reply_to) if send_req.reply_to else None,
                subject=send_req.subject,
                body_text=send_req.body_text,
                body_html=send_req.body_html,
                is_read=True,
                sent_at=datetime.now(timezone.utc),
                error_message=None,
            )
            EmailThreadService.attach_email_to_thread(thread, email_record)
            db.add(email_record)
            await db.commit()
            await db.refresh(email_record)
            logger.info("Successfully sent and logged email id=%d (Message-ID: %s, Thread-ID: %d)", email_record.id, message_id, thread.id)
            return email_record

        except Exception as exc:
            # Determine safe error message for persistence and client response
            safe_error_msg = getattr(exc, "safe_message", "Failed to transmit message via SMTP.")
            logger.warning("SMTP sending failure for account id=%d: %s", account.id, safe_error_msg)

            # Persist the attempted email in FAILED state for auditability and error tracking
            failed_email_record = Email(
                company_id=account.company_id,
                email_account_id=account.id,
                thread_id=thread.id,
                user_id=current_user.id if current_user else None,
                message_id=message_id,
                in_reply_to=in_reply_to_val,
                references_header=references_val,
                direction=EmailDirection.OUTGOING.value,
                status=EmailStatus.FAILED.value,
                sender=sender_str,
                recipients=to_list,
                cc=cc_list,
                bcc=bcc_list,
                reply_to=str(send_req.reply_to) if send_req.reply_to else None,
                subject=send_req.subject,
                body_text=send_req.body_text,
                body_html=send_req.body_html,
                is_read=True,
                sent_at=None,
                error_message=safe_error_msg,
            )
            EmailThreadService.attach_email_to_thread(thread, failed_email_record)
            db.add(failed_email_record)
            await db.commit()
            await db.refresh(failed_email_record)

            # Map domain exceptions to safe HTTP responses
            if isinstance(exc, SMTPConfigurationError):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=safe_error_msg)
            elif isinstance(exc, (SMTPAuthenticationError, SMTPConnectionError, SMTPRecipientRejectedError, SMTPSendError, SMTPServiceException)):
                raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=safe_error_msg)
            else:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="SMTP server error during email transmission.",
                )

    @staticmethod
    async def get_email(db: AsyncSession, email_id: int) -> Optional[Email]:
        """Fetch a specific email by database primary key ID."""
        result = await db.execute(select(Email).where(Email.id == email_id))
        return result.scalars().first()
