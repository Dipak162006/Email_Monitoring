import logging
import smtplib
import socket
import ssl
from email.message import EmailMessage
from typing import List, Optional
from app.modules.email_accounts.models import SecurityMode
from app.services.smtp.exceptions import (
    SMTPAuthenticationError,
    SMTPConfigurationError,
    SMTPConnectionError,
    SMTPRecipientRejectedError,
    SMTPSendError,
    SMTPServiceException,
)

logger = logging.getLogger(__name__)


class SMTPClient:
    """Synchronous low-level client wrapper around Python's smtplib.
    
    Provides standardized connection, TLS negotiation, authentication,
    and message sending with safe exception translation that never leaks credentials.
    """

    def __init__(self, default_timeout: float = 30.0):
        self.default_timeout = default_timeout

    def _create_ssl_context(self) -> ssl.SSLContext:
        """Create a default SSL context with certificate verification."""
        return ssl.create_default_context()

    def send_email_sync(
        self,
        host: str,
        port: int,
        security_mode: str,
        username: Optional[str],
        password: Optional[str],
        from_addr: str,
        to_addrs: List[str],
        message: EmailMessage,
        timeout: Optional[float] = None,
    ) -> None:
        """Connect to the SMTP server, authenticate if required, and transmit the message.
        
        Args:
            host: SMTP server hostname or IP.
            port: SMTP server port.
            security_mode: SecurityMode string (NONE, SSL, STARTTLS).
            username: Optional SMTP login username.
            password: Optional plaintext SMTP password (in-memory only).
            from_addr: Envelope sender address.
            to_addrs: List of envelope recipient addresses.
            message: Constructed MIME EmailMessage object.
            timeout: Optional socket timeout in seconds.
        """
        if not host:
            raise SMTPConfigurationError("SMTP host is required.")
        if not port or port <= 0:
            raise SMTPConfigurationError("Valid SMTP port is required.")
        if not to_addrs:
            raise SMTPConfigurationError("At least one recipient address is required.")

        conn_timeout = timeout or self.default_timeout
        server = None

        logger.info("Initiating SMTP connection to %s:%d (mode=%s)", host, port, security_mode)

        try:
            # 1. Establish connection according to security mode
            if security_mode == SecurityMode.SSL.value:
                context = self._create_ssl_context()
                server = smtplib.SMTP_SSL(host=host, port=port, timeout=conn_timeout, context=context)
            else:
                server = smtplib.SMTP(host=host, port=port, timeout=conn_timeout)

            server.ehlo_or_helo_if_needed()

            # 2. Negotiate STARTTLS if configured
            if security_mode == SecurityMode.STARTTLS.value:
                context = self._create_ssl_context()
                server.starttls(context=context)
                server.ehlo_or_helo_if_needed()

            # 3. Authenticate if username is provided
            if username:
                if password is None:
                    raise SMTPConfigurationError("SMTP username provided without password.")
                try:
                    server.login(username, password)
                    logger.info("SMTP authentication successful for user %s on %s:%d", username, host, port)
                except smtplib.SMTPAuthenticationError as auth_err:
                    logger.warning("SMTP authentication failed for user %s on %s:%d (code: %s)", username, host, port, auth_err.smtp_code)
                    raise SMTPAuthenticationError("SMTP authentication failed. Please verify credentials.") from auth_err

            # 4. Transmit message
            refused = server.send_message(
                msg=message,
                from_addr=from_addr,
                to_addrs=to_addrs,
            )

            # send_message returns a dict of refused recipients if some failed
            if refused:
                rejected = list(refused.keys())
                logger.warning("SMTP server rejected recipients: %s", rejected)
                raise SMTPRecipientRejectedError(rejected)

            logger.info("SMTP message successfully sent to %d recipients via %s:%d", len(to_addrs), host, port)

        except (SMTPServiceException, SMTPAuthenticationError, SMTPRecipientRejectedError, SMTPConfigurationError):
            # Re-raise already sanitized domain exceptions
            raise
        except (smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected, socket.timeout, ConnectionRefusedError, OSError) as conn_err:
            logger.warning("SMTP connection error on %s:%d: %s", host, port, type(conn_err).__name__)
            raise SMTPConnectionError(f"Failed to connect to SMTP server '{host}:{port}'.") from conn_err
        except smtplib.SMTPRecipientsRefused as rec_err:
            rejected = list(rec_err.recipients.keys())
            logger.warning("All recipients rejected: %s", rejected)
            raise SMTPRecipientRejectedError(rejected) from rec_err
        except smtplib.SMTPSenderRefused as send_err:
            logger.warning("Sender address rejected by %s:%d", host, port)
            raise SMTPSendError("Sender email address was rejected by the SMTP server.") from send_err
        except smtplib.SMTPDataError as data_err:
            logger.warning("SMTP data error on %s:%d (code: %s)", host, port, data_err.smtp_code)
            raise SMTPSendError("Message data was rejected by the SMTP server.") from data_err
        except smtplib.SMTPException as smtp_err:
            logger.warning("Generic SMTP error on %s:%d: %s", host, port, type(smtp_err).__name__)
            raise SMTPSendError("An SMTP protocol error occurred while sending the email.") from smtp_err
        except Exception as exc:
            logger.error("Unexpected error during SMTP transmission to %s:%d: %s", host, port, type(exc).__name__)
            raise SMTPSendError("An unexpected error occurred during SMTP transmission.") from exc
        finally:
            if server is not None:
                try:
                    server.quit()
                except Exception:
                    try:
                        server.close()
                    except Exception:
                        pass
