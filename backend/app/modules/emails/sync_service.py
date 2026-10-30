from datetime import datetime, timezone
import logging
from typing import Optional
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.email_accounts.models import EmailAccount
from app.modules.emails.attachment_service import AttachmentService
from app.modules.emails.models import Email, EmailDirection, EmailStatus, EmailThread
from app.modules.emails.monitoring_service import EmailMonitoringService
from app.modules.emails.schemas import EmailSyncResult
from app.modules.emails.thread_service import EmailThreadService
from app.services.imap.adapter import BaseIMAPAdapter, StandardIMAPAdapter
from app.services.imap.exceptions import (
    IMAPAuthenticationError,
    IMAPConfigurationError,
    IMAPConnectionError,
    IMAPFolderError,
    IMAPServiceException,
)
from app.services.imap.parser import EmailParser
from app.services.pop3.adapter import StandardPOP3Adapter
from app.services.pop3.exceptions import (
    POP3AuthenticationError,
    POP3ConfigurationError,
    POP3ConnectionError,
    POP3ServiceException,
)

logger = logging.getLogger(__name__)


class EmailSyncService:
    """Service orchestrating IMAP mailbox message retrieval, MIME parsing,
    account-scoped duplicate prevention, and database synchronization.
    """

    def __init__(self, imap_adapter: Optional[BaseIMAPAdapter] = None):
        self._custom_adapter = imap_adapter

    def get_adapter(self, account: EmailAccount) -> BaseIMAPAdapter:
        """Resolve the appropriate incoming transport adapter based on account configuration."""
        if self._custom_adapter is not None:
            return self._custom_adapter
        protocol = getattr(account, "incoming_protocol", "IMAP") or "IMAP"
        if protocol.upper() == "POP3":
            return StandardPOP3Adapter()
        return StandardIMAPAdapter()

    @property
    def imap_adapter(self) -> BaseIMAPAdapter:
        """Backward-compatible property returning the configured or default IMAP adapter."""
        return self._custom_adapter or StandardIMAPAdapter()

    async def sync_mailbox(
        self,
        db: AsyncSession,
        account: EmailAccount,
        folder: str = "INBOX",
        max_messages: int = 50,
    ) -> EmailSyncResult:
        """Synchronize an email account's mailbox folder with the local database.
        
        Fetches messages, deduplicates against existing records in this account,
        inserts new incoming emails, updates last_synced_at, and reports counts.
        Supports both IMAP and POP3 incoming protocols transparently.
        """
        protocol = getattr(account, "incoming_protocol", "IMAP") or "IMAP"
        protocol_label = "POP3" if protocol.upper() == "POP3" else "IMAP"

        # 1. Validate Account State & Configuration
        if not account.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email account is inactive and cannot be synchronized.",
            )
        host = account.incoming_host or account.imap_host
        if not host:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Email account does not have an {protocol_label} host configured.",
            )

        # For POP3, normalize folder to single inbox
        effective_folder = "INBOX" if protocol.upper() == "POP3" else folder

        # Query existing synced UIDs for this account to prioritize unsynced messages
        existing_uids_stmt = select(Email.imap_uid).where(
            Email.email_account_id == account.id,
            Email.imap_uid.is_not(None),
        )
        existing_uids_res = await db.execute(existing_uids_stmt)
        existing_uids = set(existing_uids_res.scalars().all())

        # 2. Fetch Messages via Protocol Adapter
        adapter = self.get_adapter(account)
        try:
            raw_messages = await adapter.fetch_messages(
                account=account,
                folder=effective_folder,
                max_messages=max_messages,
                existing_uids=existing_uids,
            )
        except (IMAPConfigurationError, POP3ConfigurationError) as cfg_err:
            detail = getattr(cfg_err, "safe_message", str(cfg_err))
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=detail,
            ) from cfg_err
        except (IMAPAuthenticationError, POP3AuthenticationError) as auth_err:
            detail = getattr(auth_err, "safe_message", str(auth_err))
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=detail,
            ) from auth_err
        except (IMAPConnectionError, POP3ConnectionError, IMAPFolderError, IMAPServiceException, POP3ServiceException) as net_err:
            detail = getattr(net_err, "safe_message", str(net_err))
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=detail,
            ) from net_err
        except Exception as exc:
            logger.error("Unexpected error during %s synchronization: %s", protocol_label, exc)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="An unexpected error occurred during mailbox synchronization.",
            ) from exc

        total_discovered = len(raw_messages)
        new_messages = 0
        duplicates_skipped = 0
        malformed_skipped = 0

        # 3. Process, Parse, and Deduplicate Each Message
        for msg_item in raw_messages:
            if len(msg_item) == 3:
                uid, raw_bytes, internaldate = msg_item
            else:
                uid, raw_bytes = msg_item[0], msg_item[1]
                internaldate = None

            try:
                parsed = EmailParser.parse_raw_email(raw_bytes, imap_uid=uid)
            except Exception as parse_err:
                logger.warning("Skipping malformed message (UID %s): %s", uid, parse_err)
                malformed_skipped += 1
                continue

            # Account-scoped duplicate check and attachment backfill
            existing_email: Optional[Email] = None

            # Check by message_id within this email_account_id
            if parsed.message_id:
                dup_msg_query = select(Email).where(
                    Email.email_account_id == account.id,
                    Email.message_id == parsed.message_id,
                )
                dup_msg_res = await db.execute(dup_msg_query)
                existing_email = dup_msg_res.scalars().first()

            # Check by imap_uid within this email_account_id
            if not existing_email and parsed.imap_uid:
                dup_uid_query = select(Email).where(
                    Email.email_account_id == account.id,
                    Email.imap_uid == parsed.imap_uid,
                )
                dup_uid_res = await db.execute(dup_uid_query)
                existing_email = dup_uid_res.scalars().first()

            if existing_email:
                duplicates_skipped += 1
                if parsed.imap_uid and not existing_email.imap_uid:
                    existing_email.imap_uid = parsed.imap_uid

                # Correct historical received_at if it was stamped with sync-time
                accurate_ts = internaldate or parsed.date
                if accurate_ts and existing_email.received_at and existing_email.sent_at:
                    if (existing_email.received_at - existing_email.sent_at).total_seconds() > 600:
                        existing_email.received_at = accurate_ts

                # Backfill missing attachments if email was previously fetched without attachments
                if parsed.attachments:
                    for att in parsed.attachments:
                        await AttachmentService.create_incoming_attachment(
                            db=db,
                            company_id=account.company_id,
                            email_account_id=account.id,
                            email_id=existing_email.id,
                            file_name=att.filename,
                            content_type=att.content_type,
                            content_bytes=att.content_bytes,
                        )
                continue

            # 4. Resolve Thread, Detect Bounces and Auto-Replies
            matched_bounced_email = None
            if parsed.is_bounce:
                matched_bounced_email = await EmailMonitoringService.match_and_process_bounce(
                    db=db,
                    account=account,
                    parsed=parsed,
                )

            # Resolve or create conversation thread
            thread = None
            is_reply_to_outgoing = False

            if matched_bounced_email and matched_bounced_email.thread_id:
                thread_stmt = select(EmailThread).where(EmailThread.id == matched_bounced_email.thread_id)
                t_res = await db.execute(thread_stmt)
                thread = t_res.scalars().first()

            if not thread:
                thread, is_reply = await EmailThreadService.resolve_or_create_incoming_thread(
                    db=db,
                    account=account,
                    message_id=parsed.message_id,
                    in_reply_to=parsed.in_reply_to,
                    references_header=parsed.references_header,
                    subject=parsed.subject,
                    body_text=parsed.body_text,
                    body_html=parsed.body_html,
                    email_date=parsed.date,
                    is_read=False,
                )
                if not parsed.is_bounce and EmailMonitoringService.is_genuine_reply(parsed):
                    is_reply_to_outgoing = is_reply
                else:
                    is_reply_to_outgoing = False
            else:
                # Attached to matched bounced email thread; bounce notifications never count as replies
                is_reply_to_outgoing = False

            # If genuine reply, match and auto-stop any corresponding campaign recipient follow-up sequences
            if EmailMonitoringService.is_genuine_reply(parsed):
                await EmailMonitoringService.match_and_process_campaign_reply(
                    db=db,
                    account=account,
                    parsed=parsed,
                    thread_id=thread.id if thread else None,
                    is_reply_to_outgoing=is_reply_to_outgoing,
                )

            # Determine incoming email status and diagnostic
            incoming_status = EmailStatus.BOUNCED.value if parsed.is_bounce else EmailStatus.RECEIVED.value
            incoming_error = None
            if parsed.is_bounce:
                parts = []
                if parsed.bounce_status:
                    parts.append(f"Status: {parsed.bounce_status}")
                if parsed.bounce_diagnostic:
                    parts.append(f"Diagnostic: {parsed.bounce_diagnostic}")
                elif parsed.bounce_action:
                    parts.append(f"Action: {parsed.bounce_action}")
                incoming_error = " | ".join(parts) if parts else "Delivery failed: Bounce notification received"

            # 5. Insert New Incoming Email
            email_record = Email(
                company_id=account.company_id,
                email_account_id=account.id,
                thread_id=thread.id,
                user_id=None,
                message_id=parsed.message_id,
                imap_uid=parsed.imap_uid,
                in_reply_to=parsed.in_reply_to,
                references_header=parsed.references_header,
                direction=EmailDirection.INCOMING.value,
                status=incoming_status,
                sender=parsed.sender,
                recipients=parsed.recipients,
                cc=parsed.cc,
                bcc=parsed.bcc,
                reply_to=parsed.reply_to,
                subject=parsed.subject,
                body_text=parsed.body_text,
                body_html=parsed.body_html,
                is_read=False,
                is_starred=False,
                sent_at=parsed.date,
                received_at=internaldate or parsed.date or datetime.now(timezone.utc),
                error_message=incoming_error,
            )
            EmailThreadService.attach_email_to_thread(
                thread=thread,
                email=email_record,
                is_reply_to_outgoing=is_reply_to_outgoing,
            )
            db.add(email_record)
            await db.flush()

            # Save attachments if present
            if parsed.attachments:
                for att in parsed.attachments:
                    await AttachmentService.create_incoming_attachment(
                        db=db,
                        company_id=account.company_id,
                        email_account_id=account.id,
                        email_id=email_record.id,
                        file_name=att.filename,
                        content_type=att.content_type,
                        content_bytes=att.content_bytes,
                    )

            new_messages += 1

        # 5. Update Account Last Synced Timestamp
        account.last_synced_at = datetime.now(timezone.utc)
        try:
            await db.commit()
            await db.refresh(account)
        except IntegrityError:
            await db.rollback()
            logger.info("Concurrent sync detected for account %d: duplicates prevented by database constraint.", account.id)
            duplicates_skipped += new_messages
            new_messages = 0

        sync_status = "SUCCESS"
        if malformed_skipped > 0:
            sync_status = "PARTIAL"

        logger.info(
            "Completed sync for account %d: %d discovered, %d new, %d duplicates, %d malformed",
            account.id,
            total_discovered,
            new_messages,
            duplicates_skipped,
            malformed_skipped,
        )

        return EmailSyncResult(
            email_account_id=account.id,
            status=sync_status,
            folder=effective_folder,
            total_discovered=total_discovered,
            new_messages=new_messages,
            duplicates_skipped=duplicates_skipped,
            malformed_skipped=malformed_skipped,
            synced_at=datetime.now(timezone.utc),
            error_message=None,
        )
