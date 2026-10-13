import logging
from typing import Optional

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

logger = logging.getLogger(__name__)


class SMTPTransport(EmailTransport):
    """Concrete EmailTransport implementation backed by the existing SMTP infrastructure.
    
    Delegates directly to BaseSMTPAdapter / StandardSMTPAdapter, ensuring that all existing
    SMTP protocol, connection handling, TLS negotiation, authentication, and smtplib execution
    are reused without duplication.
    """

    def __init__(self, smtp_adapter: Optional[BaseSMTPAdapter] = None):
        self.smtp_adapter = smtp_adapter or StandardSMTPAdapter()

    async def send(self, request: EmailTransportRequest) -> EmailTransportResult:
        """Transmit email via the delegated SMTP adapter.
        
        Translates or propagates SMTP exceptions safely and returns an EmailTransportResult.
        """
        account = request.account
        message = request.get_message()
        envelope_recipients = request.envelope_recipients

        # Extract message ID for result tracking if present
        msg_id_val = message.get("Message-ID")
        message_id = str(msg_id_val).strip() if msg_id_val else None

        try:
            await self.smtp_adapter.send(
                account=account,
                message=message,
                envelope_recipients=envelope_recipients,
            )
            return EmailTransportResult(
                success=True,
                message_id=message_id,
                rejected_recipients=[],
            )
        except TransportConfigurationError:
            raise
        except SMTPConfigurationError as exc:
            err = TransportConfigurationError(str(exc))
            if hasattr(exc, "safe_message"):
                err.safe_message = exc.safe_message
            raise err from exc
        except TransportAuthenticationError:
            raise
        except SMTPAuthenticationError as exc:
            err = TransportAuthenticationError(str(exc))
            if hasattr(exc, "safe_message"):
                err.safe_message = exc.safe_message
            raise err from exc
        except TransportConnectionError:
            raise
        except SMTPConnectionError as exc:
            err = TransportConnectionError(str(exc))
            if hasattr(exc, "safe_message"):
                err.safe_message = exc.safe_message
            raise err from exc
        except TransportRecipientRejectedError:
            raise
        except SMTPRecipientRejectedError as exc:
            err = TransportRecipientRejectedError(exc.rejected_recipients, message=str(exc))
            if hasattr(exc, "safe_message"):
                err.safe_message = exc.safe_message
            raise err from exc
        except TransportSendError:
            raise
        except SMTPSendError as exc:
            err = TransportSendError(str(exc))
            if hasattr(exc, "safe_message"):
                err.safe_message = exc.safe_message
            raise err from exc
        except SMTPServiceException as exc:
            safe_msg = getattr(exc, "safe_message", "SMTP service error occurred.")
            raise EmailTransportException(str(exc), safe_message=safe_msg) from exc
        except Exception as exc:
            raise TransportSendError(f"Unexpected transport failure: {exc}") from exc
