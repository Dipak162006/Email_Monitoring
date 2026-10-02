import asyncio
import concurrent.futures
from contextlib import asynccontextmanager
import logging
from typing import Any, Dict, List, Optional

from celery.exceptions import MaxRetriesExceededError
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.modules.email_accounts.models import EmailAccount
from app.modules.emails.sync_service import EmailSyncService
from app.services.imap.exceptions import (
    IMAPAuthenticationError,
    IMAPConfigurationError,
    IMAPConnectionError,
    IMAPFolderError,
    IMAPServiceException,
)
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# Dedicated engine with NullPool for Celery worker processes to avoid
# cross-event-loop connection reuse issues with asyncpg.
worker_async_engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
    poolclass=NullPool,
)

WorkerAsyncSessionLocal = async_sessionmaker(
    bind=worker_async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


@asynccontextmanager
async def get_worker_db():
    """Context manager providing a dedicated AsyncSession for worker tasks with rollback on failure."""
    async with WorkerAsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def run_async(coro):
    """Execute an async coroutine safely, supporting both worker processes and active event loops in tests."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(asyncio.run, coro).result()
    else:
        return asyncio.run(coro)


def is_retryable_exception(exc: Exception) -> bool:
    """Classify whether an exception encountered during mailbox sync is a transient/retryable network error."""
    target = exc
    if isinstance(exc, HTTPException) and exc.__cause__:
        target = exc.__cause__

    # Fatal configuration or authentication errors must NEVER be retried
    if isinstance(target, (IMAPAuthenticationError, IMAPConfigurationError, IMAPFolderError)):
        return False

    # Connection and network timeouts are retryable
    if isinstance(target, (IMAPConnectionError, ConnectionRefusedError, ConnectionResetError, TimeoutError, OSError)):
        return True

    # Inspect detail on generic HTTPExceptions
    if isinstance(exc, HTTPException):
        detail = str(exc.detail or "").lower()
        if "authentication failed" in detail or "verify account credentials" in detail:
            return False
        if "invalid" in detail and "configuration" in detail:
            return False
        if exc.status_code in (502, 503, 504):
            return True

    return False


import uuid
from app.core.redis import get_redis_client


class AccountSyncLock:
    """Distributed lock ensuring that only one synchronization task runs
    per email account at a time across all Celery workers.
    """
    LOCK_PREFIX = "lock:email_sync:"
    RELEASE_SCRIPT = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
    """

    def __init__(self, account_id: int, ttl: int = 300):
        self.account_id = account_id
        self.ttl = ttl
        self.lock_key = f"{self.LOCK_PREFIX}{account_id}"
        self.token = str(uuid.uuid4())
        self._acquired = False

    async def acquire(self) -> bool:
        """Attempt to acquire the lock with NX and EX."""
        try:
            client = get_redis_client()
            acquired = await client.set(self.lock_key, self.token, nx=True, ex=self.ttl)
            self._acquired = bool(acquired)
            return self._acquired
        except Exception as exc:
            logger.warning("Redis error acquiring sync lock for account %d: %s", self.account_id, exc)
            return True

    async def release(self) -> None:
        """Atomically release the lock only if the token matches."""
        if not self._acquired:
            return
        try:
            client = get_redis_client()
            await client.eval(self.RELEASE_SCRIPT, 1, self.lock_key, self.token)
        except Exception as exc:
            logger.warning("Redis error releasing sync lock for account %d: %s", self.account_id, exc)
        finally:
            self._acquired = False


async def _async_sync_email_account(
    account_id: int,
    folder: str = "INBOX",
    max_messages: int = 50,
) -> Dict[str, Any]:
    """Asynchronous core of the single-account synchronization task."""
    lock = AccountSyncLock(account_id=account_id)
    acquired = await lock.acquire()
    if not acquired:
        logger.warning(
            "Sync lock for account %d is already held by another worker. Skipping overlapping execution.",
            account_id,
        )
        return {
            "status": "LOCKED",
            "account_id": account_id,
            "message": f"Sync lock for account {account_id} is already held. Skipping overlapping execution.",
        }

    try:
        async with get_worker_db() as db:
            # 1. Load EmailAccount from DB
            stmt = select(EmailAccount).where(EmailAccount.id == account_id)
            result = await db.execute(stmt)
            account = result.scalars().first()

            if not account:
                logger.warning("Email account %d not found in database. Skipping background sync.", account_id)
                return {
                    "status": "NOT_FOUND",
                    "account_id": account_id,
                    "error": "Email account not found.",
                }

            if not account.is_active:
                logger.info("Email account %d is inactive. Skipping background sync.", account_id)
                return {
                    "status": "INACTIVE",
                    "account_id": account_id,
                    "message": "Email account is inactive.",
                }

            if not account.imap_host:
                logger.warning("Email account %d has no IMAP host configured.", account_id)
                raise IMAPConfigurationError("Email account does not have an IMAP host configured.")

            # 2. Delegate to existing EmailSyncService
            sync_service = EmailSyncService()
            sync_result = await sync_service.sync_mailbox(
                db=db,
                account=account,
                folder=folder,
                max_messages=max_messages,
            )

            return {
                "status": sync_result.status,
                "account_id": account.id,
                "folder": sync_result.folder,
                "total_discovered": sync_result.total_discovered,
                "new_messages": sync_result.new_messages,
                "duplicates_skipped": sync_result.duplicates_skipped,
                "malformed_skipped": sync_result.malformed_skipped,
                "synced_at": sync_result.synced_at.isoformat() if sync_result.synced_at else None,
                "error_message": sync_result.error_message,
            }
    finally:
        await lock.release()


@celery_app.task(
    bind=True,
    name="app.workers.tasks.sync_email_account_task",
    max_retries=settings.MAX_SYNC_RETRIES,
    acks_late=True,
)
def sync_email_account_task(
    self,
    account_id: int,
    folder: str = "INBOX",
    max_messages: int = 50,
) -> Dict[str, Any]:
    """Celery task executing IMAP synchronization for a single authorized email account."""
    logger.info("Starting background sync for account %d (folder: %s)", account_id, folder)
    try:
        return run_async(_async_sync_email_account(account_id, folder, max_messages))
    except Exception as exc:
        if is_retryable_exception(exc):
            retry_count = self.request.retries
            max_retries = self.max_retries if self.max_retries is not None else settings.MAX_SYNC_RETRIES
            if retry_count < max_retries:
                countdown = settings.SYNC_RETRY_BACKOFF_SECONDS * (2 ** retry_count)
                logger.warning(
                    "Transient error synchronizing account %d (attempt %d/%d). Retrying in %ds...",
                    account_id,
                    retry_count + 1,
                    max_retries,
                    countdown,
                )
                raise self.retry(exc=exc, countdown=countdown)
            else:
                logger.error(
                    "Max retries (%d) exceeded for account %d. Marking task as failed.",
                    max_retries,
                    account_id,
                )
                raise
        else:
            logger.error(
                "Non-retryable error synchronizing account %d: %s",
                account_id,
                str(exc),
            )
            raise


async def _async_sync_all_active_accounts(
    company_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Query active email accounts and dispatch individual sync tasks."""
    async with get_worker_db() as db:
        stmt = select(EmailAccount.id).where(EmailAccount.is_active == True)
        if company_id is not None:
            stmt = stmt.where(EmailAccount.company_id == company_id)

        result = await db.execute(stmt)
        account_ids = result.scalars().all()

    dispatched = []
    for acc_id in account_ids:
        sync_email_account_task.delay(account_id=acc_id)
        dispatched.append(acc_id)

    logger.info(
        "Dispatched background synchronization for %d active accounts (company_id=%s).",
        len(dispatched),
        company_id,
    )
    return {
        "status": "DISPATCHED",
        "company_id": company_id,
        "dispatched_count": len(dispatched),
        "account_ids": dispatched,
    }


@celery_app.task(
    name="app.workers.tasks.sync_all_active_accounts_task",
    acks_late=True,
)
def sync_all_active_accounts_task(
    company_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Celery fan-out task dispatching individual sync jobs for all active accounts."""
    return run_async(_async_sync_all_active_accounts(company_id))
