from dataclasses import dataclass
from datetime import datetime, timezone
import email
from email.header import decode_header
from email.utils import formataddr, getaddresses, parseaddr, parsedate_to_datetime
import logging
from typing import List, Optional

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
        )
