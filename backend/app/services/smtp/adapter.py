from abc import ABC, abstractmethod
import asyncio
from email.message import EmailMessage
from typing import List, Optional
from app.core.security import decrypt_credential
from app.modules.email_accounts.models import EmailAccount, SecurityMode
from app.services.smtp.client import SMTPClient
from app.services.smtp.exceptions import SMTPConfigurationError


class BaseSMTPAdapter(ABC):
    """Abstract interface for SMTP email transmission adapters.
    
    Allows different provider implementations (Standard SMTP, future specialized adapters)
    to be swapped without altering high-level email sending business logic.
    """

    @abstractmethod
    async def send(
        self,
        account: EmailAccount,
        message: EmailMessage,
        envelope_recipients: List[str],
    ) -> None:
        """Asynchronously transmit an email message using the account's configured SMTP settings."""
        pass


class StandardSMTPAdapter(BaseSMTPAdapter):
    """Standard provider-neutral SMTP adapter using smtplib executed in an async worker thread."""

    def __init__(self, client: Optional[SMTPClient] = None):
        self.client = client or SMTPClient()

    def _resolve_port(self, account: EmailAccount) -> int:
        """Resolve the SMTP port, falling back to industry defaults based on security mode."""
        if account.smtp_port and account.smtp_port > 0:
            return account.smtp_port
        if account.smtp_security == SecurityMode.SSL.value:
            return 465
        if account.smtp_security == SecurityMode.STARTTLS.value:
            return 587
        return 25

    async def send(
        self,
        account: EmailAccount,
        message: EmailMessage,
        envelope_recipients: List[str],
    ) -> None:
        """Send email message asynchronously using decrypted in-memory credentials."""
        if not account.smtp_host:
            raise SMTPConfigurationError("Account is missing SMTP server host configuration.")

        port = self._resolve_port(account)
        security_mode = account.smtp_security or SecurityMode.STARTTLS.value

        # Decrypt password strictly in memory for the duration of this call
        plaintext_password: Optional[str] = None
        if account.smtp_password_encrypted:
            plaintext_password = decrypt_credential(account.smtp_password_encrypted)

        username = account.smtp_username or account.email_address

        # Run blocking smtplib execution in an asyncio thread pool executor
        await asyncio.to_thread(
            self.client.send_email_sync,
            host=account.smtp_host,
            port=port,
            security_mode=security_mode,
            username=username,
            password=plaintext_password,
            from_addr=account.email_address,
            to_addrs=envelope_recipients,
            message=message,
        )
