class IMAPServiceException(Exception):
    """Base exception for IMAP service and transport errors."""

    def __init__(self, message: str, safe_message: str = "IMAP service error occurred."):
        super().__init__(message)
        self.message = message
        self.safe_message = safe_message


class IMAPConfigurationError(IMAPServiceException):
    """Raised when an EmailAccount has invalid or missing IMAP settings."""

    def __init__(self, message: str = "Incomplete or invalid IMAP configuration for email account."):
        super().__init__(message=message, safe_message=message)


class IMAPConnectionError(IMAPServiceException):
    """Raised when establishing a connection to the IMAP server fails."""

    def __init__(self, message: str = "Failed to connect to IMAP server."):
        super().__init__(message=message, safe_message="Could not connect to IMAP server: Connection refused or timed out.")


class IMAPAuthenticationError(IMAPServiceException):
    """Raised when IMAP login authentication fails."""

    def __init__(self, message: str = "IMAP authentication failed."):
        super().__init__(message=message, safe_message="IMAP authentication failed. Please verify account credentials.")


class IMAPFolderError(IMAPServiceException):
    """Raised when an IMAP mailbox folder (e.g. INBOX) cannot be selected or does not exist."""

    def __init__(self, folder: str, message: str = "Failed to select IMAP folder."):
        super().__init__(
            message=f"{message}: {folder}",
            safe_message=f"Could not access IMAP folder '{folder}'.",
        )
        self.folder = folder


class IMAPFetchError(IMAPServiceException):
    """Raised when searching or fetching messages from the IMAP server fails."""

    def __init__(self, message: str = "Failed to fetch messages from IMAP server."):
        super().__init__(message=message, safe_message="Error retrieving message data from IMAP server.")
