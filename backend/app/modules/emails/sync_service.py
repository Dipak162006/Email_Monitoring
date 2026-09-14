from datetime import datetime, timezone
import logging
from typing import Optional
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.email_accounts.models import EmailAccount
from app.modules.emails.models import Email, EmailDirection, EmailStatus, EmailThread
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

logger = logging.getLogger(__name__)


class EmailSyncService:
    """Service orchestrating IMAP mailbox message retrieval, MIME parsing,
    account-scoped duplicate prevention, and database synchronization.
    """

    def __init__(self, imap_adapter: Optional[BaseIMAPAdapter] = None):
        self.imap_adapter = imap_adapter or StandardIMAPAdapter()

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
        """
        # 1. Validate Account State & Configuration
        if not account.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email account is inactive and cannot be synchronized.",
            )
        if not account.imap_host:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email account does not have an IMAP host configured.",
            )

        # 2. Fetch Messages via Adapter
        try:
            raw_messages = await self.imap_adapter.fetch_messages(
                account=account,
                folder=folder,
                max_messages=max_messages,
            )
        except IMAPConfigurationError as cfg_err:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=cfg_err.safe_message,
            ) from cfg_err
        except (IMAPAuthenticationError, IMAPConnectionError, IMAPFolderError, IMAPServiceException) as imap_err:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=imap_err.safe_message,
            ) from imap_err
        except Exception as exc:
            logger.error("Unexpected error during IMAP synchronization: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="An unexpected error occurred during mailbox synchronization.",
            ) from exc

        total_discovered = len(raw_messages)
        new_messages = 0
        duplicates_skipped = 0
        malformed_skipped = 0

        # 3. Process, Parse, and Deduplicate Each Message
        for uid, raw_bytes in raw_messages:
            try:
                parsed = EmailParser.parse_raw_email(raw_bytes, imap_uid=uid)
            except Exception as parse_err:
                logger.warning("Skipping malformed message (UID %s): %s", uid, parse_err)
                malformed_skipped += 1
                continue

            # Account-scoped duplicate check
            is_duplicate = False

            # Check by message_id within this email_account_id
            if parsed.message_id:
                dup_msg_query = select(Email.id).where(
                    Email.email_account_id == account.id,
                    Email.message_id == parsed.message_id,
                )
                dup_msg_res = await db.execute(dup_msg_query)
                if dup_msg_res.scalars().first() is not None:
                    is_duplicate = True

            # Check by imap_uid within this email_account_id
            if not is_duplicate and parsed.imap_uid:
                dup_uid_query = select(Email.id).where(
                    Email.email_account_id == account.id,
                    Email.imap_uid == parsed.imap_uid,
                )
                dup_uid_res = await db.execute(dup_uid_query)
                if dup_uid_res.scalars().first() is not None:
                    is_duplicate = True

            if is_duplicate:
                duplicates_skipped += 1
                continue

            # 4. Resolve or Create Conversation Thread
            thread, is_reply_to_outgoing = await EmailThreadService.resolve_or_create_incoming_thread(
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
                status=EmailStatus.RECEIVED.value,
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
                received_at=datetime.now(timezone.utc),
                error_message=None,
            )
            EmailThreadService.attach_email_to_thread(
                thread=thread,
                email=email_record,
                is_reply_to_outgoing=is_reply_to_outgoing,
            )
            db.add(email_record)
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
            folder=folder,
            total_discovered=total_discovered,
            new_messages=new_messages,
            duplicates_skipped=duplicates_skipped,
            malformed_skipped=malformed_skipped,
            synced_at=datetime.now(timezone.utc),
            error_message=None,
        )
