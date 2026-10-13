from dataclasses import dataclass, field
import email.utils
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from typing import Any, Dict, List, Optional

from app.core.sanitizer import sanitize_html
from app.modules.email_accounts.models import EmailAccount


@dataclass
class EmailTransportRequest:
    """Provider-independent request value object for email transmission.
    
    Contains strictly email transport data. Does NOT contain campaign-specific
    orchestration concepts like campaign_id, recipient_id, campaign status, etc.
    """
    account: EmailAccount
    envelope_recipients: List[str]
    message: Optional[EmailMessage] = None
    subject: Optional[str] = None
    body_text: Optional[str] = None
    body_html: Optional[str] = None
    from_email: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    attachments: Optional[List[Any]] = None

    def get_message(self) -> EmailMessage:
        """Return the pre-built MIME EmailMessage, or build a standardized MIME message from fields."""
        if self.message is not None:
            return self.message

        msg = EmailMessage()
        from_addr = self.from_email or self.account.email_address
        sender_display = formataddr((self.account.name, from_addr)) if self.account.name else from_addr
        msg["From"] = sender_display
        msg["To"] = ", ".join(self.envelope_recipients)
        msg["Subject"] = self.subject or ""
        domain = from_addr.split("@")[-1] if "@" in from_addr else "localhost"
        msg["Message-ID"] = make_msgid(domain=domain)
        msg["Date"] = email.utils.formatdate(localtime=True)

        if self.headers:
            for k, v in self.headers.items():
                if k not in msg:
                    msg[k] = v

        has_text = bool(self.body_text and self.body_text.strip())
        has_html = bool(self.body_html and self.body_html.strip())
        if has_html:
            final_html = sanitize_html(self.body_html) or self.body_html
            if has_text:
                msg.set_content(self.body_text)
                msg.add_alternative(final_html, subtype="html")
            else:
                msg.set_content(final_html, subtype="html")
        else:
            msg.set_content(self.body_text or "")

        return msg


@dataclass
class EmailTransportResult:
    """Provider-independent result of an email transmission attempt."""
    success: bool = True
    message_id: Optional[str] = None
    rejected_recipients: List[str] = field(default_factory=list)
    error_message: Optional[str] = None
