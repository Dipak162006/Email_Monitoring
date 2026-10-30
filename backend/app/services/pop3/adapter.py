import asyncio
from datetime import datetime
import logging
from typing import List, Optional, Set, Tuple
from app.core.security import decrypt_credential
from app.modules.email_accounts.models import EmailAccount, SecurityMode
from app.services.imap.adapter import BaseIncomingAdapter
from app.services.pop3.client import POP3Client
from app.services.pop3.exceptions import (
    POP3AuthenticationError,
    POP3ConfigurationError,
    POP3ConnectionError,
)

logger = logging.getLogger(__name__)


class StandardPOP3Adapter(BaseIncomingAdapter):
    """Standard provider-neutral POP3 adapter executing blocking network operations in an asyncio worker thread.
    
    Guarantees non-destructive message synchronization:
    - Never deletes remote messages from the POP3 server (never issues DELE).
    - Uses persistent UIDL identifiers to safely track and deduplicate emails.
    - Treats the mailbox as a single incoming inbox (ignores IMAP folder constructs).
    """

    def __init__(self, client: Optional[POP3Client] = None):
        self.client = client or POP3Client()

    def _resolve_port(self, account: EmailAccount) -> int:
        """Resolve POP3 port, falling back to 995 for SSL or 110 for STARTTLS/NONE."""
        if account.imap_port and account.imap_port > 0:
            return account.imap_port
        if account.imap_security == SecurityMode.SSL.value:
            return 995
        return 110

    def _fetch_sync(
        self,
        account: EmailAccount,
        folder: str,
        max_messages: int,
        existing_uids: Optional[Set[str]] = None,
    ) -> List[Tuple[str, bytes, Optional[datetime]]]:
        """Synchronously execute POP3 lifecycle: connect, login, uidl, retr, quit.
        
        Guarantees messages are NEVER deleted from the remote server.
        """
        host = account.incoming_host or account.imap_host
        if not host:
            raise POP3ConfigurationError("Account is missing POP3 server host configuration.")

        port = self._resolve_port(account)
        security_mode = account.incoming_security or account.imap_security or SecurityMode.SSL.value
        username = account.incoming_username or account.imap_username or account.email_address

        # Decrypt password strictly in memory
        plaintext_password: Optional[str] = None
        if account.imap_password_encrypted:
            plaintext_password = decrypt_credential(account.imap_password_encrypted)

        if not plaintext_password:
            raise POP3ConfigurationError("Email account is missing required POP3 password.")

        try:
            self.client.connect(
                host=host,
                port=port,
                security_mode=security_mode,
            )
            self.client.login(username=username, password=plaintext_password)

            # Query all persistent UIDL identifiers on the server
            uidl_map = self.client.get_uidl_map()
            total_on_server = len(uidl_map)
            logger.info("Found %d total messages on POP3 server for account %d", total_on_server, account.id)

            if not uidl_map:
                return []

            # Prioritize unsynced messages if existing_uids is provided
            # In POP3, higher message numbers are received later on standard servers
            if existing_uids:
                unsynced = [
                    (msg_num, uid)
                    for msg_num, uid in sorted(uidl_map.items(), key=lambda x: x[0])
                    if uid not in existing_uids
                ]
                if unsynced:
                    # Select most recent unsynced messages up to max_messages
                    selected = unsynced[-max_messages:] if len(unsynced) > max_messages else unsynced
                else:
                    # All messages on server are already synced; check the most recent tail for backfill
                    all_sorted = sorted(uidl_map.items(), key=lambda x: x[0])
                    selected = all_sorted[-max_messages:] if len(all_sorted) > max_messages else all_sorted
            else:
                all_sorted = sorted(uidl_map.items(), key=lambda x: x[0])
                selected = all_sorted[-max_messages:] if len(all_sorted) > max_messages else all_sorted

            fetched_batch: List[Tuple[str, bytes, Optional[datetime]]] = []
            for msg_num, uidl in selected:
                try:
                    raw_bytes = self.client.retrieve_raw_message(msg_num)
                    if raw_bytes:
                        # POP3 protocol does not provide internaldate; EmailParser will extract Date header
                        fetched_batch.append((uidl, raw_bytes, None))
                except Exception as msg_err:
                    logger.warning("Failed to download POP3 message %d (UIDL %s): %s", msg_num, uidl, msg_err)
                    continue

            return fetched_batch

        finally:
            # Cleanly disconnect via QUIT - guarantees NO DELE commands are issued
            self.client.quit()

    async def fetch_messages(
        self,
        account: EmailAccount,
        folder: str = "INBOX",
        max_messages: int = 50,
        existing_uids: Optional[Set[str]] = None,
    ) -> List[Tuple[str, bytes, Optional[datetime]]]:
        """Asynchronously connect, authenticate, and fetch raw message data from the POP3 mailbox.
        
        Executes the blocking socket operations within a worker thread.
        Note: POP3 has only a single flat drop-folder; the 'folder' argument is normalized to 'INBOX'.
        """
        return await asyncio.to_thread(
            self._fetch_sync,
            account,
            "INBOX",
            max_messages,
            existing_uids,
        )

