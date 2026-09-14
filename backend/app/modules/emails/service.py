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
from app.modules.emails.models import Email, EmailDirection, EmailStatus
from app.modules.emails.schemas import EmailSendRequest
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
    ) -> Tuple[EmailMessage, str, List[str]]:
        """Construct a standardized MIME EmailMessage instance from account settings and send request.
        
        Returns:
            Tuple containing (EmailMessage, generated_message_id, envelope_recipients_list)
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

        return msg, message_id, all_recipients

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

        # 2. Build MIME Message
        mime_msg, message_id, envelope_recipients = self.build_mime_message(account, send_req)
        to_list = [str(r) for r in send_req.to]
        cc_list = [str(r) for r in send_req.cc] if send_req.cc else None
        bcc_list = [str(r) for r in send_req.bcc] if send_req.bcc else None
        sender_str = str(mime_msg["From"])

        # 3. Attempt SMTP Transmission
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
                user_id=current_user.id if current_user else None,
                message_id=message_id,
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
            db.add(email_record)
            await db.commit()
            await db.refresh(email_record)
            logger.info("Successfully sent and logged email id=%d (Message-ID: %s)", email_record.id, message_id)
            return email_record

        except Exception as exc:
            # Determine safe error message for persistence and client response
            safe_error_msg = getattr(exc, "safe_message", "Failed to transmit message via SMTP.")
            logger.warning("SMTP sending failure for account id=%d: %s", account.id, safe_error_msg)

            # Persist the attempted email in FAILED state for auditability and error tracking
            failed_email_record = Email(
                company_id=account.company_id,
                email_account_id=account.id,
                user_id=current_user.id if current_user else None,
                message_id=message_id,
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
