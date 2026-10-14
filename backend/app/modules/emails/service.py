from datetime import datetime, timezone
import email.utils
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
import logging
import re
from typing import Any, Dict, List, Optional, Tuple
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.sanitizer import sanitize_html
from app.modules.auth.models import User
from app.modules.email_accounts.models import EmailAccount
from app.modules.emails.models import Email, EmailAttachment, EmailDirection, EmailStatus, EmailThread
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
from app.services.transport.base import EmailTransport
from app.services.transport.exceptions import (
    EmailTransportException,
    TransportAuthenticationError,
    TransportConfigurationError,
    TransportConnectionError,
    TransportRecipientRejectedError,
    TransportSendError,
)
from app.services.transport.models import EmailTransportRequest, EmailTransportResult
from app.services.transport.smtp import SMTPTransport

logger = logging.getLogger(__name__)


def process_inline_media_images(
    html_content: str,
    company_id: int,
) -> Tuple[str, List[Dict[str, Any]]]:
    """Scan HTML for local company media images and convert them for inline CID email embedding.

    Scans for src=".../api/v1/media/{company_id}/{filename}".
    Returns:
        Tuple of (mime_html_copy, list_of_inline_media_dicts)
    """
    if not html_content or "/api/v1/media/" not in html_content:
        return html_content, []

    from app.core.storage import AttachmentStorageService

    # Match src attributes containing /api/v1/media/{company_id}/{filename}
    pattern = re.compile(
        r'''(?i)(src=["'])(?:https?://[^/"'>]+)?(?:/api/v1/media/'''
        + str(company_id)
        + r'''/([a-f0-9]{32}\.(?:png|jpg|jpeg|gif|webp)))(["'])'''
    )

    found_files: Dict[str, Any] = {}
    for match in pattern.finditer(html_content):
        filename = match.group(2)
        if filename not in found_files:
            try:
                path = AttachmentStorageService.resolve_media_path(company_id, filename)
                if path.is_file():
                    found_files[filename] = path
            except Exception:
                pass

    if not found_files:
        return html_content, []

    inline_items: List[Dict[str, Any]] = []
    mime_html = html_content

    for filename, path in found_files.items():
        cid_val = f"media_{filename}@pulsemail"
        ext = path.suffix.lower()
        subtype = "jpeg" if ext in {".jpg", ".jpeg"} else ext.lstrip(".")
        img_bytes = path.read_bytes()

        # Replace src with cid: in outgoing MIME HTML copy
        replace_pattern = re.compile(
            r'''(?i)(src=["'])(?:https?://[^/"'>]+)?(?:/api/v1/media/'''
            + str(company_id)
            + r'''/'''
            + re.escape(filename)
            + r''')(["'])'''
        )
        mime_html = replace_pattern.sub(rf'\1cid:{cid_val}\2', mime_html)

        inline_items.append({
            "cid": cid_val,
            "cid_header": f"<{cid_val}>",
            "bytes": img_bytes,
            "maintype": "image",
            "subtype": subtype,
            "filename": filename,
        })

    return mime_html, inline_items


class EmailService:
    """Service orchestrating email message construction, authorization verification,
    transport transmission, and database audit persistence.
    """

    def __init__(
        self,
        transport: Optional[EmailTransport] = None,
        smtp_adapter: Optional[BaseSMTPAdapter] = None,
    ):
        if transport is not None:
            self.transport = transport
            if isinstance(transport, SMTPTransport):
                self.smtp_adapter = transport.smtp_adapter
            else:
                self.smtp_adapter = None
        elif smtp_adapter is not None:
            self.smtp_adapter = smtp_adapter
            self.transport = SMTPTransport(smtp_adapter=smtp_adapter)
        else:
            adapter = StandardSMTPAdapter()
            self.smtp_adapter = adapter
            self.transport = SMTPTransport(smtp_adapter=adapter)

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
        has_text = bool(send_req.body_text and send_req.body_text.strip())
        has_html = bool(send_req.body_html and send_req.body_html.strip())
        if has_html:
            sanitized = sanitize_html(send_req.body_html) or send_req.body_html
            mime_html, inline_media = process_inline_media_images(sanitized, account.company_id)
            if has_text:
                msg.set_content(send_req.body_text)
                msg.add_alternative(mime_html, subtype="html")
            else:
                msg.set_content(mime_html, subtype="html")

            # Attach local media images as inline related parts
            for item in inline_media:
                msg.add_related(
                    item["bytes"],
                    maintype=item["maintype"],
                    subtype=item["subtype"],
                    cid=item["cid_header"],
                    filename=item["filename"],
                    disposition="inline",
                )
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

        # 1b. Resolve Signature (explicit or default for account)
        from app.modules.emails.models import EmailSignature
        from app.modules.emails.signature_service import SignatureService
        target_sig = None
        if send_req.signature_id is not None:
            if current_user is not None:
                target_sig = await SignatureService.get_signature(
                    db=db,
                    current_user=current_user,
                    signature_id=send_req.signature_id,
                    company_id=account.company_id,
                )
            else:
                target_sig = await db.get(EmailSignature, send_req.signature_id)
            if not target_sig or target_sig.company_id != account.company_id or target_sig.email_account_id != account.id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Signature does not belong to the selected email account.",
                )
        else:
            if current_user is not None:
                target_sig = await SignatureService.get_default_signature(
                    db=db,
                    current_user=current_user,
                    account_id=account.id,
                    company_id=account.company_id,
                )
            else:
                stmt = select(EmailSignature).where(
                    EmailSignature.email_account_id == account.id,
                    EmailSignature.is_default == True,
                )
                res = await db.execute(stmt)
                target_sig = res.scalars().first()

        if target_sig:
            send_req.body_text, send_req.body_html = SignatureService.apply_signature_to_content(
                send_req.body_text, send_req.body_html, target_sig
            )
        elif send_req.body_html:
            send_req.body_html = sanitize_html(send_req.body_html)

        if not send_req.body_text and send_req.body_html:
            clean_txt = re.sub(r"<style[^>]*>[\s\S]*?<\/style>", " ", send_req.body_html, flags=re.IGNORECASE)
            clean_txt = re.sub(r"<script[^>]*>[\s\S]*?<\/script>", " ", clean_txt, flags=re.IGNORECASE)
            clean_txt = re.sub(r"<[^>]+>", " ", clean_txt)
            send_req.body_text = re.sub(r"\s+", " ", clean_txt).strip() or None

        # 1c. Resolve and Validate Attachments for Direct Send
        from app.modules.emails.attachment_service import AttachmentService
        validated_attachments = []
        if send_req.attachment_ids:
            validated_attachments = await AttachmentService.validate_and_load_attachments_for_send(
                db=db,
                attachment_ids=send_req.attachment_ids,
                company_id=account.company_id,
                account_id=account.id,
                current_user=current_user,
            )

        campaign_attachments = []
        if getattr(send_req, "campaign_attachment_ids", None):
            from app.modules.campaigns.models import CampaignAttachment
            unique_c_ids = list(dict.fromkeys(send_req.campaign_attachment_ids))
            c_stmt = select(CampaignAttachment).where(
                CampaignAttachment.id.in_(unique_c_ids),
                CampaignAttachment.company_id == account.company_id,
                CampaignAttachment.email_account_id == account.id,
            )
            c_res = await db.execute(c_stmt)
            found_c = {att.id: att for att in c_res.scalars().all()}
            campaign_attachments = [found_c[cid] for cid in unique_c_ids if cid in found_c]

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

        # 3b. Attach files if present
        all_to_attach = list(validated_attachments) + list(campaign_attachments)
        if all_to_attach:
            await AttachmentService.attach_to_mime_message(mime_msg, all_to_attach)

        to_list = [str(r) for r in send_req.to]
        cc_list = [str(r) for r in send_req.cc] if send_req.cc else None
        bcc_list = [str(r) for r in send_req.bcc] if send_req.bcc else None
        sender_str = str(mime_msg["From"])

        # 4. Attempt Transport Transmission
        try:
            transport_req = EmailTransportRequest(
                account=account,
                message=mime_msg,
                envelope_recipients=envelope_recipients,
            )
            await self.transport.send(transport_req)

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
            await db.flush()

            # Associate validated attachments with the resulting sent Email
            for att in validated_attachments:
                if att.email_id and att.email_id != email_record.id:
                    new_att = EmailAttachment(
                        company_id=att.company_id,
                        email_account_id=att.email_account_id,
                        email_id=email_record.id,
                        file_name=att.file_name,
                        content_type=att.content_type,
                        file_size=att.file_size,
                        storage_path=att.storage_path,
                    )
                    db.add(new_att)
                else:
                    att.email_id = email_record.id

            for c_att in campaign_attachments:
                recip_att = EmailAttachment(
                    company_id=c_att.company_id,
                    email_account_id=c_att.email_account_id,
                    email_id=email_record.id,
                    file_name=c_att.file_name,
                    content_type=c_att.content_type,
                    file_size=c_att.file_size,
                    storage_path=c_att.storage_path,
                )
                db.add(recip_att)

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
            await db.flush()

            # Associate validated attachments with the failed audit Email
            for att in validated_attachments:
                att.email_id = failed_email_record.id

            await db.commit()
            await db.refresh(failed_email_record)

            # Map domain and transport exceptions to safe HTTP responses
            if isinstance(exc, (TransportConfigurationError, SMTPConfigurationError)):
                http_exc = HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=safe_error_msg)
            elif isinstance(exc, (
                TransportAuthenticationError,
                TransportConnectionError,
                TransportRecipientRejectedError,
                TransportSendError,
                EmailTransportException,
                SMTPAuthenticationError,
                SMTPConnectionError,
                SMTPRecipientRejectedError,
                SMTPSendError,
                SMTPServiceException,
            )):
                http_exc = HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=safe_error_msg)
            else:
                http_exc = HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="SMTP server error during email transmission.",
                )
            http_exc.email_record = failed_email_record
            http_exc.original_exception = exc
            raise http_exc

    @staticmethod
    async def get_email(db: AsyncSession, email_id: int) -> Optional[Email]:
        """Fetch a specific email by database primary key ID."""
        result = await db.execute(select(Email).where(Email.id == email_id))
        return result.scalars().first()
