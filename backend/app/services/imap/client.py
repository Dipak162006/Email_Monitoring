from datetime import datetime, timezone
import imaplib
import logging
import re
import socket
import ssl
from typing import List, Optional, Tuple, Union
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


def parse_internaldate(raw_bytes_or_str: Union[bytes, str]) -> Optional[datetime]:
    """Parse an IMAP INTERNALDATE response attribute into a timezone-aware UTC datetime."""
    if isinstance(raw_bytes_or_str, bytes):
        text_val = raw_bytes_or_str.decode("utf-8", errors="replace")
    else:
        text_val = str(raw_bytes_or_str)

    # Example: INTERNALDATE "23-Sep-2026 07:49:33 +0000" or " 3-Sep-2026 07:49:33 +0530"
    match = re.search(
        r'INTERNALDATE\s+"?\s*(\d{1,2}-[A-Za-z]{3}-\d{4}\s+\d{2}:\d{2}:\d{2}\s+[+-]\d{4})"?',
        text_val,
        re.IGNORECASE,
    )
    if not match:
        match = re.search(r'(\d{1,2}-[A-Za-z]{3}-\d{4}\s+\d{2}:\d{2}:\d{2}\s+[+-]\d{4})', text_val)

    if match:
        val = match.group(1).strip()
        # Ensure 2-digit day for strptime (%d)
        parts = val.split("-", 1)
        if len(parts[0]) == 1:
            val = "0" + val
        try:
            return datetime.strptime(val, "%d-%b-%Y %H:%M:%S %z").astimezone(timezone.utc)
        except Exception:
            pass
    return None



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
        except (imaplib.IMAP4.error, Exception) as err:
            logger.warning("Failed to fetch message UID %s: %s", uid, err)
            return None

    def fetch_messages_batch(
        self,
        uids: List[str],
        chunk_size: int = 50,
    ) -> List[Tuple[str, bytes, Optional[datetime]]]:
        """Fetch raw messages and INTERNALDATE in chunks for a list of UIDs without marking as seen."""
        if not self._client:
            raise IMAPConnectionError("No active IMAP connection.")
        if not uids:
            return []

        results: List[Tuple[str, bytes, Optional[datetime]]] = []
        uid_list = [str(u) for u in uids if u]

        for i in range(0, len(uid_list), chunk_size):
            chunk = uid_list[i : i + chunk_size]
            uid_str = ",".join(chunk)
            try:
                typ, data = self._client.uid("fetch", uid_str, "(INTERNALDATE BODY.PEEK[])")
                if typ != "OK" or not data:
                    typ, data = self._client.uid("fetch", uid_str, "(INTERNALDATE RFC822)")
                if typ != "OK" or not data:
                    continue

                for item in data:
                    if isinstance(item, tuple) and len(item) >= 2:
                        header_info = (
                            item[0].decode("utf-8", errors="replace")
                            if isinstance(item[0], bytes)
                            else str(item[0])
                        )
                        raw_bytes = item[1] if isinstance(item[1], bytes) else b""

                        # Extract UID from header_info (e.g. "3646 (UID 4780 INTERNALDATE ...")
                        uid_match = re.search(r'\bUID\s+(\d+)\b', header_info, re.IGNORECASE)
                        msg_uid = uid_match.group(1) if uid_match else None
                        internaldate = parse_internaldate(header_info)

                        if msg_uid and raw_bytes:
                            results.append((msg_uid, raw_bytes, internaldate))
            except Exception as err:
                logger.warning("Batch fetch failed for UIDs %s: %s", uid_str, err)

        return results

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
