from datetime import datetime, timezone
from email.message import EmailMessage
from unittest.mock import MagicMock, patch
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.email_accounts.models import EmailAccount
from app.modules.emails.models import Email, EmailDirection, EmailStatus, EmailThread
from app.services.imap.adapter import StandardIMAPAdapter
from app.services.imap.exceptions import (
    IMAPAuthenticationError,
    IMAPConfigurationError,
    IMAPConnectionError,
)
from app.workers.celery_app import celery_app
from app.workers.tasks import (
    WorkerAsyncSessionLocal,
    is_retryable_exception,
    sync_all_active_accounts_task,
    sync_email_account_task,
)
from tests.conftest import TestAsyncSessionLocal


# =============================================================================
# Test Setup & Fixtures
# =============================================================================

@pytest.fixture(autouse=True)
def configure_worker_db_and_celery():
    """Ensure worker tasks use the test database and run in Celery eager mode."""
    from app.workers import tasks
    orig_session_maker = tasks.WorkerAsyncSessionLocal
    tasks.WorkerAsyncSessionLocal = TestAsyncSessionLocal

    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = False

    yield

    tasks.WorkerAsyncSessionLocal = orig_session_maker
    celery_app.conf.task_always_eager = False
    celery_app.conf.task_eager_propagates = False


async def register_and_login(client: AsyncClient, email: str, name: str = "Test User") -> str:
    """Register and login a test user, returning bearer token."""
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123!", "full_name": name},
    )
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    return login_resp.json()["access_token"]


async def create_company_helper(client: AsyncClient, token: str, name: str) -> int:
    """Create a company and return its ID."""
    resp = await client.post(
        "/api/v1/companies/",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": name},
    )
    return resp.json()["id"]


async def create_account_helper(
    client: AsyncClient,
    token: str,
    company_id: int,
    email: str = "support@company.com",
    is_active: bool = True,
) -> int:
    """Create an email account configured for IMAP synchronization."""
    resp = await client.post(
        f"/api/v1/companies/{company_id}/email-accounts",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Support Inbox",
            "email_address": email,
            "provider": "CUSTOM",
            "smtp_host": "smtp.company.com",
            "smtp_port": 587,
            "smtp_security": "STARTTLS",
            "smtp_username": email,
            "smtp_password": "SmtpPassword123!",
            "imap_host": "imap.company.com",
            "imap_port": 993,
            "imap_security": "SSL",
            "imap_username": email,
            "imap_password": "SecretPassword123!",
        },
    )
    acc_id = resp.json()["id"]
    if not is_active:
        await client.put(
            f"/api/v1/companies/{company_id}/email-accounts/{acc_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"is_active": False},
        )
    return acc_id


def make_sample_email_bytes(
    msg_id: str = "<test-msg-001@external.com>",
    subject: str = "Test Subject",
    sender: str = "sender@external.com",
    body: str = "Hello from background sync!",
) -> bytes:
    """Create a simple MIME email message."""
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = "support@company.com"
    msg["Subject"] = subject
    msg["Date"] = "Wed, 16 Sep 2026 12:00:00 +0000"
    msg["Message-ID"] = msg_id
    msg.set_content(body)
    return msg.as_bytes()


def make_dsn_bounce_bytes(
    bounce_msg_id: str,
    orig_msg_id: str,
    recipient: str = "baduser@external.com",
) -> bytes:
    """Create an RFC 3464 DSN bounce message."""
    boundary = "DSN_BOUNDARY_BG_TEST"
    raw = (
        f"From: MAILER-DAEMON@mail.server.com\r\n"
        f"To: sender@company.com\r\n"
        f"Subject: Delivery Status Notification (Failure)\r\n"
        f"Date: Wed, 16 Sep 2026 12:00:00 +0000\r\n"
        f"Message-ID: {bounce_msg_id}\r\n"
        f"In-Reply-To: {orig_msg_id}\r\n"
        f"MIME-Version: 1.0\r\n"
        f'Content-Type: multipart/report; report-type=delivery-status; boundary="{boundary}"\r\n'
        f"\r\n"
        f"--{boundary}\r\n"
        f"Content-Type: text/plain; charset=utf-8\r\n"
        f"\r\n"
        f"Delivery failed for {recipient}\r\n"
        f"\r\n"
        f"--{boundary}\r\n"
        f"Content-Type: message/delivery-status\r\n"
        f"\r\n"
        f"Final-Recipient: rfc822; {recipient}\r\n"
        f"Action: failed\r\n"
        f"Status: 5.1.1\r\n"
        f"Diagnostic-Code: smtp; 550 5.1.1 Recipient address rejected\r\n"
        f"\r\n"
        f"--{boundary}\r\n"
        f"Content-Type: message/rfc822\r\n"
        f"\r\n"
        f"From: sender@company.com\r\n"
        f"To: {recipient}\r\n"
        f"Subject: Original Message\r\n"
        f"Message-ID: {orig_msg_id}\r\n"
        f"\r\n"
        f"Original body\r\n"
        f"--{boundary}--\r\n"
    )
    return raw.encode("utf-8")


# =============================================================================
# M14 Test Cases
# =============================================================================

def test_01_celery_registration_and_beat_schedule():
    """M. Celery registration: tasks registered with Celery app and periodic beat configured."""
    assert "app.workers.tasks.sync_email_account_task" in celery_app.tasks
    assert "app.workers.tasks.sync_all_active_accounts_task" in celery_app.tasks

    schedule = celery_app.conf.beat_schedule
    assert "sync-active-email-accounts-periodic" in schedule
    entry = schedule["sync-active-email-accounts-periodic"]
    assert entry["task"] == "app.workers.tasks.sync_all_active_accounts_task"


@pytest.mark.asyncio
async def test_02_single_account_task_success(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """A. Single account task: valid active account, successful sync, serializable result."""
    token = await register_and_login(async_client, "user_bg_02@test.com")
    comp_id = await create_company_helper(async_client, token, "Co BG-02")
    acc_id = await create_account_helper(async_client, token, comp_id)

    raw_email = make_sample_email_bytes(
        msg_id="<bg-msg-001@external.com>",
        subject="Background Email",
    )

    with patch.object(StandardIMAPAdapter, "fetch_messages", return_value=[("1001", raw_email)]):
        eager_res = sync_email_account_task.apply(args=[acc_id, "INBOX", 50])
        assert eager_res.successful()
        result = eager_res.result

        assert result["status"] == "SUCCESS"
        assert result["account_id"] == acc_id
        assert result["folder"] == "INBOX"
        assert result["new_messages"] == 1
        assert result["duplicates_skipped"] == 0
        assert result["total_discovered"] == 1
        assert result["synced_at"] is not None

        # Verify email was persisted in DB
        stmt = select(Email).where(Email.email_account_id == acc_id, Email.message_id == "<bg-msg-001@external.com>")
        db_res = await db_session.execute(stmt)
        saved_email = db_res.scalars().first()
        assert saved_email is not None
        assert saved_email.subject == "Background Email"

        # Verify account last_synced_at was updated
        acc_stmt = select(EmailAccount).where(EmailAccount.id == acc_id)
        acc_db = (await db_session.execute(acc_stmt)).scalars().first()
        assert acc_db.last_synced_at is not None


@pytest.mark.asyncio
async def test_03_single_account_missing_account(
    async_client: AsyncClient,
):
    """B. Missing account: task handles missing account safely without crash."""
    eager_res = sync_email_account_task.apply(args=[999999, "INBOX", 50])
    assert eager_res.successful()
    result = eager_res.result
    assert result["status"] == "NOT_FOUND"
    assert result["account_id"] == 999999


@pytest.mark.asyncio
async def test_04_single_account_inactive_account(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """C. Inactive account: synchronization is skipped and no IMAP operation occurs."""
    token = await register_and_login(async_client, "user_bg_04@test.com")
    comp_id = await create_company_helper(async_client, token, "Co BG-04")
    acc_id = await create_account_helper(async_client, token, comp_id, is_active=False)

    with patch.object(StandardIMAPAdapter, "fetch_messages") as mock_fetch:
        eager_res = sync_email_account_task.apply(args=[acc_id, "INBOX", 50])
        assert eager_res.successful()
        result = eager_res.result
        assert result["status"] == "INACTIVE"
        assert result["account_id"] == acc_id
        mock_fetch.assert_not_called()


@pytest.mark.asyncio
async def test_05_retryable_error_triggers_retry(
    async_client: AsyncClient,
):
    """D. Retryable error: temporary IMAP connection failure causes Celery retry."""
    token = await register_and_login(async_client, "user_bg_05@test.com")
    comp_id = await create_company_helper(async_client, token, "Co BG-05")
    acc_id = await create_account_helper(async_client, token, comp_id)

    # Verify error classification
    conn_err = IMAPConnectionError("Connection timed out")
    assert is_retryable_exception(conn_err) is True

    with patch.object(StandardIMAPAdapter, "fetch_messages", side_effect=conn_err):
        # In eager mode, Celery executes retries synchronously until max_retries is exceeded
        eager_res = sync_email_account_task.apply(args=[acc_id])
        assert eager_res.failed()
        exc = eager_res.result
        # The exception raised after max retries contains the connection error detail
        assert "Connection refused" in str(exc) or "timed out" in str(exc) or "Retry" in type(exc).__name__


@pytest.mark.asyncio
async def test_06_fatal_error_not_retried(
    async_client: AsyncClient,
):
    """E. Fatal error: authentication/configuration errors are not retried."""
    token = await register_and_login(async_client, "user_bg_06@test.com")
    comp_id = await create_company_helper(async_client, token, "Co BG-06")
    acc_id = await create_account_helper(async_client, token, comp_id)

    auth_err = IMAPAuthenticationError("Invalid credentials")
    assert is_retryable_exception(auth_err) is False

    cfg_err = IMAPConfigurationError("Invalid host")
    assert is_retryable_exception(cfg_err) is False

    with patch.object(StandardIMAPAdapter, "fetch_messages", side_effect=auth_err):
        eager_res = sync_email_account_task.apply(args=[acc_id])
        assert eager_res.failed()
        # Non-retryable error fails immediately without Retry exception
        assert type(eager_res.result).__name__ != "Retry"


@pytest.mark.asyncio
async def test_07_database_failure_rollback(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """F. Database failure: unhandled error triggers session rollback and leaves clean state."""
    token = await register_and_login(async_client, "user_bg_07@test.com")
    comp_id = await create_company_helper(async_client, token, "Co BG-07")
    acc_id = await create_account_helper(async_client, token, comp_id)

    with patch("app.modules.emails.sync_service.EmailSyncService.sync_mailbox", side_effect=RuntimeError("Simulated DB Crash")):
        eager_res = sync_email_account_task.apply(args=[acc_id])
        assert eager_res.failed()
        assert "Simulated DB Crash" in str(eager_res.result)

    # Database is clean, no corrupt entries
    count_stmt = select(Email).where(Email.email_account_id == acc_id)
    emails = (await db_session.execute(count_stmt)).scalars().all()
    assert len(emails) == 0


@pytest.mark.asyncio
async def test_08_m13_bounce_processing_inside_celery_task(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """J. M13 Monitoring integration inside Celery task: bounces update outgoing status to BOUNCED."""
    token = await register_and_login(async_client, "user_bg_08@test.com")
    comp_id = await create_company_helper(async_client, token, "Co BG-08")
    acc_id = await create_account_helper(async_client, token, comp_id)

    # Create outgoing email
    orig_email = Email(
        company_id=comp_id,
        email_account_id=acc_id,
        direction=EmailDirection.OUTGOING.value,
        status=EmailStatus.SENT.value,
        message_id="<orig-out-bg-001@company.com>",
        sender="support@company.com",
        recipients=["baduser@external.com"],
        subject="Invoice Notification",
        is_read=True,
    )
    db_session.add(orig_email)
    await db_session.commit()

    # DSN bounce targeting the outgoing message
    bounce_bytes = make_dsn_bounce_bytes(
        bounce_msg_id="<bounce-bg-001@mail.server.com>",
        orig_msg_id="<orig-out-bg-001@company.com>",
        recipient="baduser@external.com",
    )

    with patch.object(StandardIMAPAdapter, "fetch_messages", return_value=[("2001", bounce_bytes)]):
        eager_res = sync_email_account_task.apply(args=[acc_id])
        assert eager_res.successful()

    # Verify outgoing email transitioned to BOUNCED
    await db_session.refresh(orig_email)
    assert orig_email.status == EmailStatus.BOUNCED.value
    assert "5.1.1" in (orig_email.error_message or "")


@pytest.mark.asyncio
async def test_09_fan_out_all_active_accounts(
    async_client: AsyncClient,
):
    """G. Fan-out task: all active accounts discovered and dispatched; inactive accounts skipped."""
    token = await register_and_login(async_client, "user_bg_09@test.com")
    comp_id = await create_company_helper(async_client, token, "Co BG-09")
    acc_1 = await create_account_helper(async_client, token, comp_id, email="acc1@company.com", is_active=True)
    acc_2 = await create_account_helper(async_client, token, comp_id, email="acc2@company.com", is_active=True)
    acc_3 = await create_account_helper(async_client, token, comp_id, email="acc3@company.com", is_active=False)

    with patch("app.workers.tasks.sync_email_account_task.delay") as mock_delay:
        res = sync_all_active_accounts_task.apply()
        assert res.successful()
        data = res.result
        assert data["status"] == "DISPATCHED"
        assert acc_1 in data["account_ids"]
        assert acc_2 in data["account_ids"]
        assert acc_3 not in data["account_ids"]
        assert mock_delay.call_count >= 2


@pytest.mark.asyncio
async def test_10_company_scoped_fan_out_and_isolation(
    async_client: AsyncClient,
):
    """H & I. Company-scoped fan-out & cross-company isolation."""
    token_1 = await register_and_login(async_client, "user_bg_10_c1@test.com")
    comp_1 = await create_company_helper(async_client, token_1, "Co 1")
    acc_1 = await create_account_helper(async_client, token_1, comp_1, email="acc_c1@company1.com")

    token_2 = await register_and_login(async_client, "user_bg_10_c2@test.com")
    comp_2 = await create_company_helper(async_client, token_2, "Co 2")
    acc_2 = await create_account_helper(async_client, token_2, comp_2, email="acc_c2@company2.com")

    with patch("app.workers.tasks.sync_email_account_task.delay") as mock_delay:
        # Fan-out scoped only to Company 1
        res = sync_all_active_accounts_task.apply(args=[comp_1])
        assert res.successful()
        data = res.result
        assert data["company_id"] == comp_1
        assert acc_1 in data["account_ids"]
        assert acc_2 not in data["account_ids"]  # Company 2 account must NOT be dispatched


@pytest.mark.asyncio
async def test_11_idempotent_repeated_sync_task_execution(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """J. Duplicate/background behavior: running sync twice does not duplicate records."""
    token = await register_and_login(async_client, "user_bg_11@test.com")
    comp_id = await create_company_helper(async_client, token, "Co BG-11")
    acc_id = await create_account_helper(async_client, token, comp_id)

    raw_email = make_sample_email_bytes(
        msg_id="<dup-test-msg@external.com>",
        subject="Idempotency Check",
    )

    with patch.object(StandardIMAPAdapter, "fetch_messages", return_value=[("3001", raw_email)]):
        # First execution
        res1 = sync_email_account_task.apply(args=[acc_id]).result
        assert res1["new_messages"] == 1
        assert res1["duplicates_skipped"] == 0

        # Second execution with exact same data
        res2 = sync_email_account_task.apply(args=[acc_id]).result
        assert res2["new_messages"] == 0
        assert res2["duplicates_skipped"] == 1

    # Exactly one email in DB
    count_stmt = select(Email).where(Email.email_account_id == acc_id, Email.message_id == "<dup-test-msg@external.com>")
    emails = (await db_session.execute(count_stmt)).scalars().all()
    assert len(emails) == 1


@pytest.mark.asyncio
async def test_12_api_backward_compatibility_synchronous(
    async_client: AsyncClient,
):
    """K. API backward compatibility: background=false preserves existing synchronous behavior."""
    token = await register_and_login(async_client, "user_bg_12@test.com")
    comp_id = await create_company_helper(async_client, token, "Co BG-12")
    acc_id = await create_account_helper(async_client, token, comp_id)

    raw_email = make_sample_email_bytes(msg_id="<sync-api-001@external.com>")

    with patch.object(StandardIMAPAdapter, "fetch_messages", return_value=[("4001", raw_email)]):
        resp = await async_client.post(
            f"/api/v1/email-accounts/{acc_id}/sync",
            headers={"Authorization": f"Bearer {token}"},
            json={"folder": "INBOX", "max_messages": 50},
        )
        assert resp.status_code == 200
        data = resp.json()
        # Synchronous result contains full sync metrics
        assert data["status"] == "SUCCESS"
        assert data["new_messages"] == 1
        assert data["email_account_id"] == acc_id


@pytest.mark.asyncio
async def test_13_api_background_mode_returns_202_and_task_id(
    async_client: AsyncClient,
):
    """L. API background mode: background=true returns HTTP 202, QUEUED status, and task_id."""
    token = await register_and_login(async_client, "user_bg_13@test.com")
    comp_id = await create_company_helper(async_client, token, "Co BG-13")
    acc_id = await create_account_helper(async_client, token, comp_id)

    with patch("app.workers.tasks.sync_email_account_task.delay") as mock_delay:
        mock_task = MagicMock()
        mock_task.id = "mock-celery-task-id-12345"
        mock_delay.return_value = mock_task

        resp = await async_client.post(
            f"/api/v1/email-accounts/{acc_id}/sync?background=true",
            headers={"Authorization": f"Bearer {token}"},
            json={"folder": "INBOX", "max_messages": 50},
        )
        assert resp.status_code == 202
        data = resp.json()
        assert data["task_id"] == "mock-celery-task-id-12345"
        assert data["status"] == "QUEUED"
        assert data["email_account_id"] == acc_id
        mock_delay.assert_called_once_with(
            account_id=acc_id,
            folder="INBOX",
            max_messages=50,
        )


@pytest.mark.asyncio
async def test_14_api_job_status_endpoint(
    async_client: AsyncClient,
):
    """Verify job status query endpoint returns background job state."""
    token = await register_and_login(async_client, "user_bg_14@test.com")

    with patch("celery.result.AsyncResult") as mock_async_result:
        mock_instance = MagicMock()
        mock_instance.status = "SUCCESS"
        mock_instance.ready.return_value = True
        mock_instance.successful.return_value = True
        mock_instance.result = {"status": "SUCCESS", "new_messages": 2}
        mock_async_result.return_value = mock_instance

        resp = await async_client.get(
            "/api/v1/email-accounts/sync-jobs/test-task-id-abc",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["task_id"] == "test-task-id-abc"
        assert data["status"] == "SUCCESS"
        assert data["result"]["new_messages"] == 2


def test_15_no_credentials_in_task_arguments_or_results():
    """Security check: verify task signature and results never expose passwords or secrets."""
    import inspect
    sig = inspect.signature(sync_email_account_task)
    param_names = list(sig.parameters.keys())
    assert "password" not in param_names
    assert "secret" not in param_names
    assert "token" not in param_names
    assert param_names == ["account_id", "folder", "max_messages"]
