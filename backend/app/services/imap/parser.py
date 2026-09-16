from dataclasses import dataclass
from datetime import datetime, timezone
import email
from email.header import decode_header
from email.utils import formataddr, getaddresses, parseaddr, parsedate_to_datetime
import logging
import re
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ParsedEmail:
    """Normalized data representation of a parsed raw MIME email message."""
    message_id: Optional[str]
    in_reply_to: Optional[str]
    references_header: Optional[str]
    sender: str
    recipients: List[str]
    cc: Optional[List[str]]
    bcc: Optional[List[str]]
    reply_to: Optional[str]
    subject: str
    body_text: Optional[str]
    body_html: Optional[str]
    date: datetime
    imap_uid: Optional[str] = None
    # M13 Monitoring fields
    is_bounce: bool = False
    bounce_action: Optional[str] = None
    bounce_status: Optional[str] = None
    bounce_diagnostic: Optional[str] = None
    bounce_recipient: Optional[str] = None
    bounce_original_message_id: Optional[str] = None
    is_auto_reply: bool = False
    auto_submitted: Optional[str] = None


class EmailParser:
    """MIME email parser extracting normalized metadata and bodies from raw RFC 822/2822 bytes."""

    @staticmethod
    def decode_header_str(header_value: Optional[str]) -> str:
        """Safely decode RFC 2047 encoded-word headers into a Unicode string."""
        if not header_value:
            return ""

        try:
            decoded_parts = decode_header(header_value)
            result = []
            for part, encoding in decoded_parts:
                if isinstance(part, bytes):
                    charset = encoding or "utf-8"
                    try:
                        result.append(part.decode(charset, errors="replace"))
                    except (LookupError, UnicodeDecodeError):
                        result.append(part.decode("utf-8", errors="replace"))
                else:
                    result.append(str(part))
            return "".join(result).strip()
        except Exception as exc:
            logger.warning("Failed to decode email header '%s': %s", header_value[:30], exc)
            return str(header_value).strip()

    @classmethod
    def format_single_address(cls, header_value: Optional[str]) -> str:
        """Parse and format a single sender or reply-to address preserving decoded display names."""
        if not header_value:
            return ""

        name, addr = parseaddr(header_value)
        decoded_name = cls.decode_header_str(name) if name else ""
        addr = addr.strip()

        if decoded_name and addr:
            return f"{decoded_name} <{addr}>"
        return addr or decoded_name or header_value.strip()

    @classmethod
    def parse_addresses(cls, header_value: Optional[str]) -> List[str]:
        """Extract a clean list of email addresses from destination headers (To, CC, BCC)."""
        if not header_value:
            return []

        addresses = getaddresses([header_value])
        cleaned: List[str] = []
        for name, addr in addresses:
            addr = addr.strip()
            if addr and addr not in cleaned:
                cleaned.append(addr)
        return cleaned

    @staticmethod
    def extract_message_ids(header_text: Optional[str]) -> List[str]:
        """Extract and deduplicate <message-id> tokens from header text."""
        if not header_text:
            return []
        tokens = re.findall(r"<[^>]+>", header_text)
        seen = set()
        result = []
        for t in tokens:
            t = t.strip()
            if t and t not in seen:
                seen.add(t)
                result.append(t)
        return result

    @classmethod
    def _detect_bounce_and_auto_reply(
        cls,
        msg: email.message.Message,
        subject: str,
        in_reply_to: Optional[str],
        references_header: Optional[str],
    ) -> Tuple[bool, Optional[str], Optional[str], Optional[str], Optional[str], Optional[str], bool, Optional[str]]:
        """Conservative RFC 3464 DSN bounce and RFC 3834 auto-reply detection.
        
        Returns:
            (is_bounce, bounce_action, bounce_status, bounce_diagnostic, bounce_recipient, bounce_original_message_id, is_auto_reply, auto_submitted)
        """
        is_bounce = False
        bounce_action: Optional[str] = None
        bounce_status: Optional[str] = None
        bounce_diagnostic: Optional[str] = None
        bounce_recipient: Optional[str] = None
        bounce_original_message_id: Optional[str] = None

        is_auto_reply = False
        auto_submitted: Optional[str] = None

        # 1. Detect Auto-Reply / Out-of-Office headers (RFC 3834 / Exchange)
        raw_auto = msg.get("Auto-Submitted")
        if raw_auto:
            auto_submitted = raw_auto.strip()
            if auto_submitted.lower() not in ("no", ""):
                is_auto_reply = True

        raw_suppress = msg.get("X-Auto-Response-Suppress")
        if raw_suppress and raw_suppress.strip():
            is_auto_reply = True

        raw_precedence = str(msg.get("Precedence") or "").strip().lower()
        if raw_precedence in ("auto_reply", "autoreply"):
            is_auto_reply = True
        elif raw_precedence in ("bulk", "junk"):
            subj_lower = (subject or "").lower()
            if any(k in subj_lower for k in ("out of office", "automatic reply", "auto-reply", "vacation", "autoreply")):
                is_auto_reply = True

        # 2. Inspect RFC 3464 DSN & delivery-status MIME parts
        content_type = msg.get_content_type().lower()
        report_type = str(msg.get_param("report-type") or "").strip().lower()
        is_report = (content_type == "multipart/report" and (not report_type or report_type == "delivery-status"))

        has_delivery_status_part = False
        x_failed_recipients = msg.get("X-Failed-Recipients")

        if msg.is_multipart():
            for part in msg.walk():
                p_ct = part.get_content_type().lower()
                if p_ct == "message/delivery-status":
                    has_delivery_status_part = True
                    payload = part.get_payload()
                    sub_headers_list = []
                    if isinstance(payload, list):
                        for sub_part in payload:
                            if hasattr(sub_part, "items"):
                                sub_headers_list.append(dict(sub_part.items()))
                    else:
                        raw_dsn = part.get_payload(decode=True)
                        if raw_dsn:
                            text_dsn = raw_dsn.decode("utf-8", errors="replace")
                        elif isinstance(payload, str):
                            text_dsn = payload
                        else:
                            text_dsn = ""
                        blocks = text_dsn.replace("\r\n", "\n").split("\n\n")
                        for blk in blocks:
                            if blk.strip():
                                sub_msg = email.message_from_string(blk)
                                if sub_msg.items():
                                    sub_headers_list.append(dict(sub_msg.items()))

                    for hdrs in sub_headers_list:
                        lower_hdrs = {k.lower(): v for k, v in hdrs.items()}
                        if not bounce_action and "action" in lower_hdrs:
                            bounce_action = str(lower_hdrs["action"]).strip().lower()
                        if not bounce_status and "status" in lower_hdrs:
                            bounce_status = str(lower_hdrs["status"]).strip()
                        if not bounce_diagnostic and "diagnostic-code" in lower_hdrs:
                            bounce_diagnostic = cls.decode_header_str(str(lower_hdrs["diagnostic-code"]))
                        if not bounce_recipient and "final-recipient" in lower_hdrs:
                            bounce_recipient = str(lower_hdrs["final-recipient"]).strip()

                elif p_ct in ("message/rfc822", "text/rfc822-headers") and not bounce_original_message_id:
                    payload = part.get_payload()
                    orig_msg = None
                    if isinstance(payload, list) and len(payload) > 0 and hasattr(payload[0], "get"):
                        orig_msg = payload[0]
                    else:
                        raw_orig = part.get_payload(decode=True)
                        if raw_orig:
                            try:
                                orig_msg = email.message_from_bytes(raw_orig)
                            except Exception:
                                pass
                        elif isinstance(payload, str):
                            try:
                                orig_msg = email.message_from_string(payload)
                            except Exception:
                                pass
                    if orig_msg:
                        raw_orig_id = orig_msg.get("Message-ID")
                        if raw_orig_id:
                            bounce_original_message_id = raw_orig_id.strip()

        elif content_type == "message/delivery-status":
            has_delivery_status_part = True
            raw_dsn = msg.get_payload(decode=True)
            text_dsn = raw_dsn.decode("utf-8", errors="replace") if raw_dsn else str(msg.get_payload() or "")
            blocks = text_dsn.replace("\r\n", "\n").split("\n\n")
            for blk in blocks:
                if blk.strip():
                    sub_msg = email.message_from_string(blk)
                    lower_hdrs = {k.lower(): v for k, v in dict(sub_msg.items()).items()}
                    if not bounce_action and "action" in lower_hdrs:
                        bounce_action = str(lower_hdrs["action"]).strip().lower()
                    if not bounce_status and "status" in lower_hdrs:
                        bounce_status = str(lower_hdrs["status"]).strip()
                    if not bounce_diagnostic and "diagnostic-code" in lower_hdrs:
                        bounce_diagnostic = cls.decode_header_str(str(lower_hdrs["diagnostic-code"]))
                    if not bounce_recipient and "final-recipient" in lower_hdrs:
                        bounce_recipient = str(lower_hdrs["final-recipient"]).strip()

        # 3. Determine if this message is structurally a bounce
        if is_report or has_delivery_status_part:
            is_bounce = True
            if not bounce_action:
                bounce_action = "failed"
        elif x_failed_recipients:
            is_bounce = True
            bounce_recipient = x_failed_recipients.strip()
            bounce_action = "failed"

        # 4. Resolve original Message-ID fallback if not extracted from embedded message
        if is_bounce and not bounce_original_message_id:
            if in_reply_to and in_reply_to.strip():
                clean_in_reply = in_reply_to.strip()
                tokens = cls.extract_message_ids(clean_in_reply)
                bounce_original_message_id = tokens[0] if tokens else clean_in_reply
            elif references_header:
                ref_ids = cls.extract_message_ids(references_header)
                if ref_ids:
                    bounce_original_message_id = ref_ids[-1]

        # Ensure bounce messages are never flagged as auto-replies
        if is_bounce:
            is_auto_reply = False

        return (
            is_bounce,
            bounce_action,
            bounce_status,
            bounce_diagnostic,
            bounce_recipient,
            bounce_original_message_id,
            is_auto_reply,
            auto_submitted,
        )

    @classmethod
    def parse_raw_email(cls, raw_bytes: bytes, imap_uid: Optional[str] = None) -> ParsedEmail:
        """Parse raw email bytes into a normalized ParsedEmail dataclass."""
        msg = email.message_from_bytes(raw_bytes)

        # 1. Message Identifiers & Threading
        raw_msg_id = msg.get("Message-ID")
        message_id = raw_msg_id.strip() if raw_msg_id else None

        raw_in_reply_to = msg.get("In-Reply-To")
        in_reply_to = raw_in_reply_to.strip() if raw_in_reply_to else None

        raw_references = msg.get("References")
        references_header = raw_references.strip() if raw_references else None

        # 2. Subject
        subject = cls.decode_header_str(msg.get("Subject", ""))

        # 3. Addresses
        sender = cls.format_single_address(msg.get("From")) or "unknown@localhost"
        recipients = cls.parse_addresses(msg.get("To"))
        cc_recipients = cls.parse_addresses(msg.get("Cc")) or None
        bcc_recipients = cls.parse_addresses(msg.get("Bcc")) or None

        reply_to: Optional[str] = None
        if msg.get("Reply-To"):
            reply_to = cls.format_single_address(msg.get("Reply-To"))

        # 4. Date
        date = datetime.now(timezone.utc)
        raw_date = msg.get("Date")
        if raw_date:
            try:
                parsed_dt = parsedate_to_datetime(raw_date)
                if parsed_dt.tzinfo is None:
                    parsed_dt = parsed_dt.replace(tzinfo=timezone.utc)
                date = parsed_dt
            except Exception:
                pass

        # 5. Extract Text and HTML Bodies
        body_text: Optional[str] = None
        body_html: Optional[str] = None

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition") or "")

                # Skip attachments from being treated as message bodies
                if "attachment" in content_disposition.lower():
                    continue

                if content_type == "text/plain" and body_text is None:
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        try:
                            body_text = payload.decode(charset, errors="replace")
                        except (LookupError, UnicodeDecodeError):
                            body_text = payload.decode("utf-8", errors="replace")

                elif content_type == "text/html" and body_html is None:
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        try:
                            body_html = payload.decode(charset, errors="replace")
                        except (LookupError, UnicodeDecodeError):
                            body_html = payload.decode("utf-8", errors="replace")
        else:
            payload = msg.get_payload(decode=True)
            charset = msg.get_content_charset() or "utf-8"
            decoded_body = ""
            if payload:
                try:
                    decoded_body = payload.decode(charset, errors="replace")
                except (LookupError, UnicodeDecodeError):
                    decoded_body = payload.decode("utf-8", errors="replace")

            if msg.get_content_type() == "text/html":
                body_html = decoded_body
            else:
                body_text = decoded_body

        # 6. Detect Bounce & Auto-Reply Indicators
        (
            is_bounce,
            bounce_action,
            bounce_status,
            bounce_diagnostic,
            bounce_recipient,
            bounce_original_message_id,
            is_auto_reply,
            auto_submitted,
        ) = cls._detect_bounce_and_auto_reply(
            msg=msg,
            subject=subject,
            in_reply_to=in_reply_to,
            references_header=references_header,
        )

        return ParsedEmail(
            message_id=message_id,
            in_reply_to=in_reply_to,
            references_header=references_header,
            sender=sender,
            recipients=recipients or [sender],
            cc=cc_recipients,
            bcc=bcc_recipients,
            reply_to=reply_to,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            date=date,
            imap_uid=imap_uid,
            is_bounce=is_bounce,
            bounce_action=bounce_action,
            bounce_status=bounce_status,
            bounce_diagnostic=bounce_diagnostic,
            bounce_recipient=bounce_recipient,
            bounce_original_message_id=bounce_original_message_id,
            is_auto_reply=is_auto_reply,
            auto_submitted=auto_submitted,
        )
