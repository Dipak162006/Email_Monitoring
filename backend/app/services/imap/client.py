import imaplib
import logging
import socket
import ssl
from typing import List, Optional, Tuple
from app.modules.email_accounts.models import SecurityMode
from app.services.imap.exceptions import (
    IMAPAuthenticationError,
    IMAPConfigurationError,
    IMAPConnectionError,
    IMAPFetchError,
    IMAPFolderError,
    IMAPServiceException,
)

logger = logging.getLogger(__name__)


class IMAPClient:
    """Low-level IMAP client wrapping Python's standard imaplib.
    
    Provides connection establishment, STARTTLS / SSL negotiation,
    authentication, mailbox folder selection, and UID-based message fetching.
    All exceptions are translated to safe domain exceptions that never expose credentials.
    """

    def __init__(self, default_timeout: float = 30.0):
        self.default_timeout = default_timeout
        self._client: Optional[imaplib.IMAP4] = None

    def _create_ssl_context(self) -> ssl.SSLContext:
        """Create a default SSL context for verified TLS connections."""
        return ssl.create_default_context()

    def connect(
        self,
        host: str,
        port: int,
        security_mode: str,
        timeout: Optional[float] = None,
    ) -> None:
        """Establish IMAP connection and negotiate encryption."""
        if not host:
            raise IMAPConfigurationError("IMAP host is required.")
        if not port or port <= 0:
            raise IMAPConfigurationError("Valid IMAP port is required.")

        conn_timeout = timeout or self.default_timeout
        logger.info("Connecting to IMAP server %s:%d (mode=%s)", host, port, security_mode)

        try:
            if security_mode == SecurityMode.SSL.value:
                context = self._create_ssl_context()
                self._client = imaplib.IMAP4_SSL(host=host, port=port, ssl_context=context, timeout=conn_timeout)
            else:
                self._client = imaplib.IMAP4(host=host, port=port, timeout=conn_timeout)

            if security_mode == SecurityMode.STARTTLS.value:
                context = self._create_ssl_context()
                self._client.starttls(ssl_context=context)

        except (socket.timeout, ConnectionRefusedError, OSError) as err:
            logger.warning("IMAP connection failed to %s:%d: %s", host, port, type(err).__name__)
            raise IMAPConnectionError(f"Could not connect to IMAP server '{host}:{port}'.") from err
        except imaplib.IMAP4.error as err:
            logger.warning("IMAP protocol error during connection to %s:%d", host, port)
            raise IMAPConnectionError(f"IMAP protocol error connecting to '{host}:{port}'.") from err

    def login(self, username: str, password: str) -> None:
        """Authenticate to the IMAP server with in-memory credentials."""
        if not self._client:
            raise IMAPConnectionError("Cannot login without an active IMAP connection.")
        if not username or password is None:
            raise IMAPConfigurationError("IMAP username and password are required for authentication.")

        try:
            typ, data = self._client.login(username, password)
            if typ != "OK":
                raise IMAPAuthenticationError("IMAP login credentials rejected by server.")
            logger.info("IMAP authentication successful for %s", username)
        except imaplib.IMAP4.error as err:
            logger.warning("IMAP authentication failed for %s", username)
            raise IMAPAuthenticationError("IMAP authentication failed. Please verify credentials.") from err

    def select_folder(self, folder: str = "INBOX") -> int:
        """Select an IMAP mailbox folder in read-only mode and return message count."""
        if not self._client:
            raise IMAPConnectionError("No active IMAP connection.")

        try:
            typ, data = self._client.select(mailbox=folder, readonly=True)
            if typ != "OK":
                raise IMAPFolderError(folder, f"IMAP folder '{folder}' could not be selected.")
            count = int(data[0]) if data and data[0] else 0
            return count
        except imaplib.IMAP4.error as err:
            logger.warning("Failed to select IMAP folder '%s'", folder)
            raise IMAPFolderError(folder, f"Failed to select folder '{folder}'.") from err

    def search_uids(self, query: str = "ALL") -> List[str]:
        """Search for messages by UID and return list of UID strings."""
        if not self._client:
            raise IMAPConnectionError("No active IMAP connection.")

        try:
            typ, data = self._client.uid("search", None, query)
            if typ != "OK" or not data:
                return []
            raw_uids = data[0].split()
            return [uid.decode("utf-8", errors="replace") if isinstance(uid, bytes) else str(uid) for uid in raw_uids]
        except (imaplib.IMAP4.error, Exception) as err:
            logger.warning("IMAP search failed: %s", err)
            raise IMAPFetchError(f"Failed to search messages in IMAP mailbox.") from err

    def fetch_message_by_uid(self, uid: str) -> Optional[bytes]:
        """Fetch raw message RFC 822 bytes for a specific UID without marking it as seen."""
        if not self._client:
            raise IMAPConnectionError("No active IMAP connection.")

        try:
            # PEEK prevents server from marking unread emails as read
            typ, data = self._client.uid("fetch", uid, "(BODY.PEEK[])")
            if typ != "OK" or not data:
                # Fallback to RFC822 if BODY.PEEK[] is not supported
                typ, data = self._client.uid("fetch", uid, "(RFC822)")

            if typ != "OK" or not data:
                return None

            for response_part in data:
                if isinstance(response_part, tuple) and len(response_part) >= 2:
                    return response_part[1]
            return None
        except (imaplib.IMAP4.error, Exception) as err:
            logger.warning("Failed to fetch message UID %s: %s", uid, err)
            return None

    def close(self) -> None:
        """Cleanly close folder and disconnect/logout from the IMAP session."""
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            try:
                self._client.logout()
            except Exception:
                pass
            self._client = None
