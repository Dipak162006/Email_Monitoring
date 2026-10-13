from typing import List, Optional
from app.services.smtp.exceptions import (
    SMTPAuthenticationError,
    SMTPConfigurationError,
    SMTPConnectionError,
    SMTPRecipientRejectedError,
    SMTPSendError,
    SMTPServiceException,
)


class EmailTransportException(SMTPServiceException):
    """Base exception for all transport-layer delivery errors."""
    is_retryable: bool = False

    def __init__(
        self,
        message: str,
        safe_message: str = "Email transport error occurred.",
        is_retryable: bool = False,
    ):
        super().__init__(message=message, safe_message=safe_message)
        self.is_retryable = is_retryable


class TransportConfigurationError(EmailTransportException, SMTPConfigurationError):
    """Raised when an EmailAccount is missing required transport parameters (non-retryable)."""
    is_retryable: bool = False

    def __init__(self, message: str = "Incomplete or invalid transport configuration."):
        SMTPConfigurationError.__init__(self, message=message)
        self.is_retryable = False


class TransportConnectionError(EmailTransportException, SMTPConnectionError):
    """Raised when establishing a connection to the transport server fails (transient/retryable)."""
    is_retryable: bool = True

    def __init__(self, message: str = "Failed to connect to email transport server."):
        SMTPConnectionError.__init__(self, message=message)
        self.is_retryable = True


class TransportAuthenticationError(EmailTransportException, SMTPAuthenticationError):
    """Raised when transport authentication fails (permanent / credential error)."""
    is_retryable: bool = False

    def __init__(self, message: str = "Email transport authentication failed."):
        SMTPAuthenticationError.__init__(self, message=message)
        self.is_retryable = False


class TransportRecipientRejectedError(EmailTransportException, SMTPRecipientRejectedError):
    """Raised when one or more recipient email addresses are rejected by the transport."""
    is_retryable: bool = False

    def __init__(self, rejected_recipients: List[str], message: str = "Recipient address rejected by transport."):
        SMTPRecipientRejectedError.__init__(self, rejected_recipients=rejected_recipients, message=message)
        self.is_retryable = False


class TransportSendError(EmailTransportException, SMTPSendError):
    """Raised when transmitting message data fails after connection (transient/retryable)."""
    is_retryable: bool = True

    def __init__(self, message: str = "Failed to transmit message via transport."):
        SMTPSendError.__init__(self, message=message)
        self.is_retryable = True
