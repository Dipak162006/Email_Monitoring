from abc import ABC, abstractmethod
import asyncio
from datetime import datetime
import logging
from typing import List, Optional, Set, Tuple
from app.core.security import decrypt_credential
from app.modules.email_accounts.models import EmailAccount, SecurityMode
from app.services.imap.client import IMAPClient
from app.services.imap.exceptions import IMAPConfigurationError

logger = logging.getLogger(__name__)


class BaseIMAPAdapter(ABC):
    """Abstract interface for IMAP mailbox retrieval adapters.
    
    Permits plugging in different transport implementations or test fakes
    without altering the core mailbox synchronization business logic.
    """

    @abstractmethod
    async def fetch_messages(
        self,
        account: EmailAccount,
        folder: str = "INBOX",
        max_messages: int = 50,
        existing_uids: Optional[Set[str]] = None,
    ) -> List[Tuple[str, bytes, Optional[datetime]]]:
        """Asynchronously connect, authenticate, and fetch raw message data from the specified mailbox folder.
        
        Returns:
            List of tuples: [(uid, raw_bytes, internaldate), ...]
        """
        pass


class StandardIMAPAdapter(BaseIMAPAdapter):
    """Standard provider-neutral IMAP adapter executing blocking operations in an asyncio worker thread."""

    def __init__(self, client: Optional[IMAPClient] = None):
        self.client = client or IMAPClient()

    def _resolve_port(self, account: EmailAccount) -> int:
        """Resolve IMAP port, falling back to 993 for SSL or 143 for STARTTLS/NONE."""
        if account.imap_port and account.imap_port > 0:
            return account.imap_port
        if account.imap_security == SecurityMode.SSL.value:
            return 993
        return 143

    def _fetch_sync(
        self,
        account: EmailAccount,
        folder: str,
        max_messages: int,
        existing_uids: Optional[Set[str]] = None,
    ) -> List[Tuple[str, bytes, Optional[datetime]]]:
        """Synchronously execute IMAP lifecycle: connect, login, select, search, fetch, logout."""
        if not account.imap_host:
            raise IMAPConfigurationError("Account is missing IMAP server host configuration.")

        port = self._resolve_port(account)
        security_mode = account.imap_security or SecurityMode.SSL.value
        username = account.imap_username or account.email_address

        # Decrypt password strictly in memory
        plaintext_password: Optional[str] = None
        if account.imap_password_encrypted:
            plaintext_password = decrypt_credential(account.imap_password_encrypted)

        if not plaintext_password:
            raise IMAPConfigurationError("Email account is missing required IMAP password.")

        try:
            self.client.connect(
                host=account.imap_host,
                port=port,
                security_mode=security_mode,
            )
            self.client.login(username=username, password=plaintext_password)
            self.client.select_folder(folder=folder)

            # Search message UIDs
            uids = self.client.search_uids("ALL")
            logger.info("Found %d total messages in folder '%s' for account %d", len(uids), folder, account.id)

            # Prioritize unsynced messages if existing_uids is provided
            if existing_uids:
                unsynced = [u for u in uids if u not in existing_uids]
                if unsynced:
                    # Select most recent unsynced UIDs up to max_messages
                    selected_uids = unsynced[-max_messages:] if len(unsynced) > max_messages else unsynced
                else:
                    # All messages on server are already synced; check the most recent tail
                    selected_uids = uids[-max_messages:] if len(uids) > max_messages else uids
            else:
                selected_uids = uids[-max_messages:] if len(uids) > max_messages else uids

            # Use batch fetching if available and supported, with per-message fallback
            fetched_batch: List[Tuple[str, bytes, Optional[datetime]]] = []
            if hasattr(self.client, "fetch_messages_batch"):
                try:
                    fetched_batch = self.client.fetch_messages_batch(selected_uids)
                except Exception as err:
                    logger.debug("Batch fetch exception: %s, falling back to per-message fetch", err)
                    fetched_batch = []

            if fetched_batch:
                return fetched_batch

            fetched_messages: List[Tuple[str, bytes, Optional[datetime]]] = []
            for uid in selected_uids:
                raw_bytes = self.client.fetch_message_by_uid(uid)
                if raw_bytes:
                    fetched_messages.append((uid, raw_bytes, None))

            return fetched_messages
        finally:
            self.client.close()

    async def fetch_messages(
        self,
        account: EmailAccount,
        folder: str = "INBOX",
        max_messages: int = 50,
        existing_uids: Optional[Set[str]] = None,
    ) -> List[Tuple[str, bytes, Optional[datetime]]]:
        """Run blocking IMAP operations non-blockingly using an asyncio executor thread."""
        return await asyncio.to_thread(
            self._fetch_sync,
            account=account,
            folder=folder,
            max_messages=max_messages,
            existing_uids=existing_uids,
        )
