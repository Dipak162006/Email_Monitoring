class SMTPServiceException(Exception):
    """Base exception for SMTP service and transport errors."""

    def __init__(self, message: str, safe_message: str = "SMTP service error occurred."):
        super().__init__(message)
        self.message = message
        self.safe_message = safe_message


class SMTPConfigurationError(SMTPServiceException):
    """Raised when an EmailAccount is missing required SMTP parameters."""

    def __init__(self, message: str = "Incomplete or invalid SMTP configuration for email account."):
        super().__init__(message=message, safe_message=message)


class SMTPConnectionError(SMTPServiceException):
    """Raised when establishing a socket connection or TLS handshake to the SMTP server fails."""

    def __init__(self, message: str = "Failed to connect to SMTP server."):
        super().__init__(message=message, safe_message="Could not connect to SMTP server: Connection refused or timed out.")


class SMTPAuthenticationError(SMTPServiceException):
    """Raised when SMTP server authentication (AUTH command) fails."""

    def __init__(self, message: str = "SMTP authentication failed."):
        super().__init__(message=message, safe_message="SMTP authentication failed. Please verify account credentials.")


class SMTPRecipientRejectedError(SMTPServiceException):
    """Raised when one or more recipient email addresses are rejected by the SMTP server."""

    def __init__(self, rejected_recipients: list[str], message: str = "Recipient address rejected by SMTP server."):
        recipients_str = ", ".join(rejected_recipients)
        super().__init__(
            message=f"{message}: {recipients_str}",
            safe_message=f"One or more recipients were rejected by the SMTP server: {recipients_str}",
        )
        self.rejected_recipients = rejected_recipients


class SMTPSendError(SMTPServiceException):
    """Raised when sending message data fails after connection and authentication."""

    def __init__(self, message: str = "Failed to transmit message via SMTP."):
        super().__init__(message=message, safe_message="SMTP transmission failed during message data transfer.")
