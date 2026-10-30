import logging
import poplib
import socket
import ssl
from typing import Dict, List, Optional, Union
from app.services.pop3.exceptions import (
    POP3AuthenticationError,
    POP3ConfigurationError,
    POP3ConnectionError,
)

logger = logging.getLogger(__name__)


class POP3Client:
    """Provider-neutral client for interacting with POP3 mail servers using standard-library poplib.
    
    Guarantees strict non-destructive synchronization:
    - Never issues the POP3 'DELE' command.
    - Preserves all remote messages on the mail server.
    - Uses persistent UIDL identifiers for safe duplicate prevention.
    """

    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.connection: Optional[Union[poplib.POP3, poplib.POP3_SSL]] = None
        self._connected: bool = False

    def connect(
        self,
        host: str,
        port: int = 995,
        security_mode: str = "SSL",
    ) -> None:
        """Establish a network socket connection to the POP3 server.
        
        Supports implicit SSL/TLS (default for port 995, e.g. pop3s.aruba.it)
        as well as explicit STARTTLS and plain connections.
        """
        if not host:
            raise POP3ConfigurationError("POP3 host must not be empty.")

        sec_upper = (security_mode or "SSL").upper()

        try:
            if sec_upper == "SSL":
                # Implicit SSL/TLS on port 995
                ssl_context = ssl.create_default_context()
                self.connection = poplib.POP3_SSL(
                    host=host,
                    port=port,
                    timeout=self.timeout,
                    context=ssl_context,
                )
            elif sec_upper == "STARTTLS":
                # Connect cleartext and upgrade via STLS
                self.connection = poplib.POP3(
                    host=host,
                    port=port,
                    timeout=self.timeout,
                )
                ssl_context = ssl.create_default_context()
                self.connection.stls(context=ssl_context)
            else:
                # Plain unencrypted connection
                self.connection = poplib.POP3(
                    host=host,
                    port=port,
                    timeout=self.timeout,
                )

            self._connected = True
            logger.info("Successfully connected to POP3 server %s:%d (%s)", host, port, sec_upper)

        except (socket.timeout, TimeoutError) as exc:
            logger.error("Connection timed out to POP3 server %s:%d: %s", host, port, exc)
            raise POP3ConnectionError(f"Connection timed out to POP3 server {host}:{port}: {exc}") from exc
        except (socket.error, OSError, ssl.SSLError) as exc:
            logger.error("Network/SSL error connecting to POP3 server %s:%d: %s", host, port, exc)
            raise POP3ConnectionError(f"Network error connecting to POP3 server {host}:{port}: {exc}") from exc
        except Exception as exc:
            logger.error("Unexpected error connecting to POP3 server %s:%d: %s", host, port, exc)
            raise POP3ConnectionError(f"Failed to connect to POP3 server {host}:{port}: {exc}") from exc

    def login(self, username: str, password: str) -> None:
        """Authenticate against the POP3 server using USER and PASS.
        
        Classifies authentication rejections distinctly from transient network failures.
        """
        if not self.connection:
            raise POP3ConnectionError("Cannot login without an active POP3 connection.")

        if not username:
            raise POP3ConfigurationError("POP3 username must not be empty.")

        try:
            self.connection.user(username)
            self.connection.pass_(password)
            logger.info("Successfully authenticated POP3 user '%s'", username)

        except poplib.error_proto as exc:
            err_msg = str(exc)
            logger.warning("POP3 authentication rejected for user '%s': %s", username, err_msg)
            raise POP3AuthenticationError(
                f"POP3 authentication failed for user '{username}': {err_msg}"
            ) from exc
        except (socket.timeout, TimeoutError, socket.error, OSError, ssl.SSLError) as exc:
            logger.error("Connection interrupted during POP3 authentication for user '%s': %s", username, exc)
            raise POP3ConnectionError(
                f"Connection error during POP3 authentication for user '{username}': {exc}"
            ) from exc

    def get_uidl_map(self) -> Dict[int, str]:
        """Query all available message identifiers on the POP3 server via UIDL.
        
        Returns:
            Dict mapping 1-based sequential message number -> persistent UIDL string:
            {1: "000000014b2d38f2", 2: "000000024b2d38f3", ...}
            
        Notice: POP3 message numbers (1, 2, 3) are ephemeral and renumbered upon deletion,
        while UIDL strings remain permanently unique per message on the server.
        """
        if not self.connection:
            raise POP3ConnectionError("Cannot retrieve UIDL without an active POP3 connection.")

        try:
            # poplib.uidl() returns (response, [line, ...], octets)
            resp, lines, octets = self.connection.uidl()
            uidl_map: Dict[int, str] = {}

            for line in lines:
                if isinstance(line, bytes):
                    line_str = line.decode("utf-8", errors="replace").strip()
                else:
                    line_str = str(line).strip()

                if not line_str:
                    continue

                parts = line_str.split(None, 1)
                if len(parts) == 2:
                    try:
                        msg_num = int(parts[0])
                        uidl = parts[1].strip()
                        if uidl:
                            uidl_map[msg_num] = uidl
                    except ValueError:
                        logger.warning("Skipping malformed POP3 UIDL line: %s", line_str)
                        continue

            logger.info("Discovered %d total messages with UIDL on POP3 server", len(uidl_map))
            return uidl_map

        except poplib.error_proto as exc:
            logger.error("POP3 server rejected UIDL command: %s", exc)
            raise POP3ConnectionError(f"POP3 server rejected UIDL: {exc}") from exc
        except (socket.timeout, TimeoutError, socket.error, OSError, ssl.SSLError) as exc:
            logger.error("Connection error during POP3 UIDL retrieval: %s", exc)
            raise POP3ConnectionError(f"Connection error during POP3 UIDL query: {exc}") from exc

    def retrieve_raw_message(self, msg_num: int) -> bytes:
        """Download raw RFC 822 email message bytes using POP3 RETR.
        
        Guarantees non-destructive download: NEVER calls DELE.
        """
        if not self.connection:
            raise POP3ConnectionError("Cannot retrieve message without an active POP3 connection.")

        try:
            # poplib.retr(which) returns (response, ['line', ...], octets)
            resp, lines, octets = self.connection.retr(msg_num)

            # Reconstruct raw RFC 822 stream
            if lines and isinstance(lines[0], bytes):
                return b"\r\n".join(lines)
            elif lines:
                return "\r\n".join(str(l) for l in lines).encode("utf-8")
            return b""

        except poplib.error_proto as exc:
            logger.warning("POP3 RETR failed for message number %d: %s", msg_num, exc)
            raise POP3ConnectionError(f"POP3 RETR failed for message {msg_num}: {exc}") from exc
        except (socket.timeout, TimeoutError, socket.error, OSError, ssl.SSLError) as exc:
            logger.error("Connection interrupted during POP3 RETR for message %d: %s", msg_num, exc)
            raise POP3ConnectionError(f"Connection error downloading message {msg_num}: {exc}") from exc

    def quit(self) -> None:
        """Send QUIT to the POP3 server and close the socket.
        
        Because DELE is never issued during the session, all messages remain on the server.
        """
        if self.connection and self._connected:
            try:
                self.connection.quit()
                logger.info("Closed POP3 connection cleanly via QUIT.")
            except Exception as exc:
                logger.debug("Non-critical error sending POP3 QUIT: %s", exc)
            finally:
                self.connection = None
                self._connected = False

    def disconnect(self) -> None:
        """Safe fallback to close connection without raising exceptions."""
        if self.connection:
            try:
                self.connection.quit()
            except Exception:
                pass
            finally:
                self.connection = None
                self._connected = False

