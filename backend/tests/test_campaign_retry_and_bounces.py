from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from httpx import AsyncClient
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.auth.models import User
from app.modules.campaigns.delivery_service import (
    CampaignDeliveryService,
    is_retryable_delivery_error,
)
from app.modules.campaigns.models import (
    Campaign,
    CampaignDelivery,
    CampaignDeliveryStatus,
    CampaignRecipient,
    CampaignRecipientStatus,
    CampaignStatus,
    SuppressionEntry,
    SuppressionReason,
)
from app.modules.campaigns.schemas import CampaignCreate
from app.modules.campaigns.service import CampaignService
from app.modules.campaigns.suppression_service import SuppressionService
from app.modules.companies.models import Company, CompanyRole, CompanyUser
from app.modules.domains.models import Domain, DomainVerificationStatus
from app.modules.email_accounts.models import EmailAccount
from app.modules.emails.models import Email, EmailDirection, EmailStatus
from app.modules.emails.monitoring_service import EmailMonitoringService
from app.services.imap.parser import EmailParser, ParsedEmail
from tests.test_email_monitoring import make_rfc3464_dsn_bounce
from app.services.smtp.client import SMTPClient
from app.services.smtp.exceptions import (
    SMTPAuthenticationError,
    SMTPConfigurationError,
    SMTPConnectionError,
    SMTPRecipientRejectedError,
    SMTPSendError,
)
from app.services.transport.exceptions import (
    TransportAuthenticationError,
    TransportConfigurationError,
    TransportConnectionError,
    TransportRecipientRejectedError,
    TransportSendError,
)
from app.workers import tasks
from app.workers.campaign_tasks import (
    _async_retry_campaign_delivery_task,
    retry_campaign_delivery_task,
)
from tests.conftest import TestAsyncSessionLocal


@pytest.fixture(autouse=True)
def configure_worker_db():
    """Ensure delivery engine worker tasks use the test database."""
    orig_session_maker = tasks.WorkerAsyncSessionLocal
    tasks.WorkerAsyncSessionLocal = TestAsyncSessionLocal
    yield
    tasks.WorkerAsyncSessionLocal = orig_session_maker


# =============================================================================
# Helper Utilities
# =============================================================================

async def register_and_login(async_client: AsyncClient, email: str, name: str = "Test User") -> str:
    pwd = "ValidPass123!@#"
    resp = await async_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": pwd, "full_name": name},
    )
    assert resp.status_code == 201
    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": pwd},
    )
    assert login_resp.status_code == 200
    return login_resp.json()["access_token"]


async def create_company_helper(async_client: AsyncClient, token: str, name: str) -> int:
    resp = await async_client.post(
        "/api/v1/companies/",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": name},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def setup_test_campaign(
    async_client: AsyncClient,
    db_session: AsyncSession,
    token: str,
    company_id: int,
    domain_name: str = "testmail.com",
) -> tuple[int, int, int]:
    """Helper setting up a verified domain, email account, DRAFT campaign, and recipient."""
    # 1. Verified domain
    domain = Domain(
        company_id=company_id,
        domain_name=domain_name,
        verification_status=DomainVerificationStatus.VERIFIED.value,
    )
    db_session.add(domain)
    await db_session.flush()

    # 2. Email account
    account = EmailAccount(
        company_id=company_id,
        domain_id=domain.id,
        name="Campaign Sender",
        email_address=f"sender@{domain_name}",
        provider="CUSTOM",
        smtp_host=f"smtp.{domain_name}",
        smtp_port=587,
        smtp_security="STARTTLS",
        smtp_username=f"sender@{domain_name}",
        smtp_password_encrypted="enc_password",
        is_active=True,
    )
    db_session.add(account)
    await db_session.commit()
    await db_session.refresh(account)

    # 3. Create Campaign via API
    camp_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Retry & Bounce Test Campaign",
            "email_account_id": account.id,
            "subject": "Hello {{first_name}}",
            "body_text": "Hi {{first_name}}, testing retries.",
        },
    )
    assert camp_resp.status_code == 201
    camp_id = camp_resp.json()["id"]

    # 4. Add Recipient
    recip_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}/recipients",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": f"target@{domain_name}", "first_name": "Target"},
    )
    assert recip_resp.status_code == 201
    recip_id = recip_resp.json()["id"]

    # 5. Set Campaign status to RUNNING (campaign is past dispatch / active)
    camp = await db_session.get(Campaign, camp_id)
    camp.status = CampaignStatus.RUNNING.value
    await db_session.commit()

    return camp_id, account.id, recip_id


# =============================================================================
# 1. Transport-Aware Retry Classification Tests
# =============================================================================

def test_01_retryable_transport_failure_classification():
    """Verify transport error classification according to the existing taxonomy:
    - Connection, timeout, and transient send failures are retryable.
    - Configuration, authentication, and recipient rejected failures are NOT retryable.
    """
    # Retryable errors
    assert is_retryable_delivery_error(TransportConnectionError()) is True
    assert is_retryable_delivery_error(SMTPConnectionError()) is True
    assert is_retryable_delivery_error(TransportSendError()) is True
    assert is_retryable_delivery_error(SMTPSendError()) is True
    assert is_retryable_delivery_error(TimeoutError("Socket timeout")) is True
    assert is_retryable_delivery_error(ConnectionRefusedError("Connection refused")) is True
    assert is_retryable_delivery_error(OSError("Network unreachable")) is True

    # Non-retryable errors
    assert is_retryable_delivery_error(TransportConfigurationError()) is False
    assert is_retryable_delivery_error(SMTPConfigurationError()) is False
    assert is_retryable_delivery_error(TransportAuthenticationError()) is False
    assert is_retryable_delivery_error(SMTPAuthenticationError()) is False
    assert is_retryable_delivery_error(TransportRecipientRejectedError(["bad@mail.com"])) is False
    assert is_retryable_delivery_error(SMTPRecipientRejectedError(["bad@mail.com"])) is False

    # Wrapped exception handling
    from fastapi import HTTPException
    http_err = HTTPException(status_code=502, detail="Gateway error")
    http_err.original_exception = SMTPConnectionError()
    assert is_retryable_delivery_error(http_err) is True

    http_fatal = HTTPException(status_code=400, detail="Bad config")
    http_fatal.original_exception = SMTPConfigurationError()
    assert is_retryable_delivery_error(http_fatal) is False

    assert is_retryable_delivery_error(None) is False


# =============================================================================
# 2. Retry Attempt Tracking, Increments & Execution Tests
# =============================================================================

@pytest.mark.anyio
async def test_02_successful_retry_increments_attempt_and_sets_sent(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Verify that retrying an eligible FAILED delivery:
    - Increments attempt_count correctly (e.g. 1 -> 2).
    - Sends via existing EmailService.
    - Transitions CampaignDelivery to SENT with updated sent_at and Message-ID.
    - Leaves CampaignRecipient.status unchanged.
    """
    token = await register_and_login(async_client, "owner_c9_02@test.com", "Owner C9-02")
    company_id = await create_company_helper(async_client, token, "C9 Org 02")
    camp_id, acc_id, recip_id = await setup_test_campaign(async_client, db_session, token, company_id)

    # Create initial delivery in FAILED state (attempt 1)
    delivery = CampaignDelivery(
        campaign_id=camp_id,
        recipient_id=recip_id,
        status=CampaignDeliveryStatus.FAILED.value,
        attempt_count=1,
        last_attempt_at=datetime.now(timezone.utc),
        error_message="SMTP connection timed out",
    )
    db_session.add(delivery)
    await db_session.commit()
    await db_session.refresh(delivery)

    with patch("app.services.smtp.client.SMTPClient.send_email_sync", return_value=None):
        result = await CampaignDeliveryService.retry_delivery(
            delivery_id=delivery.id,
            company_id=company_id,
        )

    assert result["status"] == "SENT"
    assert result["attempt_count"] == 2

    # Verify persisted delivery
    await db_session.refresh(delivery)
    assert delivery.status == CampaignDeliveryStatus.SENT.value
    assert delivery.attempt_count == 2
    assert delivery.sent_at is not None
    assert delivery.error_message is None
    assert delivery.message_id is not None
    assert delivery.email_id is not None

    # Verify CampaignRecipient.status was not mutated
    recip = await db_session.get(CampaignRecipient, recip_id)
    assert recip.status == CampaignRecipientStatus.PENDING.value


@pytest.mark.anyio
async def test_03_retry_stops_after_maximum_attempts(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Verify that a delivery at or exceeding MAX_CAMPAIGN_DELIVERY_RETRIES:
    - Is refused for retry (status EXCEEDED_MAX_RETRIES).
    - Makes zero SMTP calls.
    - Preserves attempt_count and FAILED status.
    """
    token = await register_and_login(async_client, "owner_c9_03@test.com", "Owner C9-03")
    company_id = await create_company_helper(async_client, token, "C9 Org 03")
    camp_id, _, recip_id = await setup_test_campaign(async_client, db_session, token, company_id)

    max_retries = getattr(settings, "MAX_CAMPAIGN_DELIVERY_RETRIES", 3)
    delivery = CampaignDelivery(
        campaign_id=camp_id,
        recipient_id=recip_id,
        status=CampaignDeliveryStatus.FAILED.value,
        attempt_count=max_retries,
        last_attempt_at=datetime.now(timezone.utc),
        error_message="Persistent connection timeout",
    )
    db_session.add(delivery)
    await db_session.commit()
    await db_session.refresh(delivery)

    with patch("app.services.smtp.client.SMTPClient.send_email_sync") as mock_smtp:
        result = await CampaignDeliveryService.retry_delivery(
            delivery_id=delivery.id,
            company_id=company_id,
        )
        mock_smtp.assert_not_called()

    assert result["status"] == "EXCEEDED_MAX_RETRIES"
    assert result["attempt_count"] == max_retries

    await db_session.refresh(delivery)
    assert delivery.status == CampaignDeliveryStatus.FAILED.value
    assert delivery.attempt_count == max_retries


# =============================================================================
# 3. Idempotency & Terminal State Protection Tests
# =============================================================================

@pytest.mark.anyio
async def test_04_already_sent_delivery_is_not_retried(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Verify that a delivery with status SENT is skipped and never resent."""
    token = await register_and_login(async_client, "owner_c9_04@test.com", "Owner C9-04")
    company_id = await create_company_helper(async_client, token, "C9 Org 04")
    camp_id, _, recip_id = await setup_test_campaign(async_client, db_session, token, company_id)

    delivery = CampaignDelivery(
        campaign_id=camp_id,
        recipient_id=recip_id,
        status=CampaignDeliveryStatus.SENT.value,
        attempt_count=1,
        sent_at=datetime.now(timezone.utc),
        message_id="<sent-msg-01@testmail.com>",
    )
    db_session.add(delivery)
    await db_session.commit()
    await db_session.refresh(delivery)

    with patch("app.services.smtp.client.SMTPClient.send_email_sync") as mock_smtp:
        result = await CampaignDeliveryService.retry_delivery(
            delivery_id=delivery.id,
            company_id=company_id,
        )
        mock_smtp.assert_not_called()

    assert result["status"] == "SKIPPED"
    assert "already SENT" in result["reason"]


@pytest.mark.anyio
async def test_04b_already_sending_delivery_is_not_retried_concurrently(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Verify concurrent duplicate retry prevention:
    Worker A:
        delivery FAILED
        -> changes to SENDING
        -> commits (releases DB lock to perform SMTP)
    Worker B:
        arrives while Worker A is in-flight with SMTP
        sees delivery already SENDING
        -> exits safely without calling EmailService.send_email()
    """
    token = await register_and_login(async_client, "owner_c9_04b@test.com", "Owner C9-04b")
    company_id = await create_company_helper(async_client, token, "C9 Org 04b")
    camp_id, _, recip_id = await setup_test_campaign(async_client, db_session, token, company_id)

    # 1. Delivery starts in FAILED state from attempt 1
    delivery = CampaignDelivery(
        campaign_id=camp_id,
        recipient_id=recip_id,
        status=CampaignDeliveryStatus.FAILED.value,
        attempt_count=1,
        error_message="Connection timeout",
    )
    db_session.add(delivery)
    await db_session.commit()
    await db_session.refresh(delivery)

    # 2. Worker A begins retry: transitions FAILED -> SENDING, increments attempt to 2, and commits
    delivery.status = CampaignDeliveryStatus.SENDING.value
    delivery.attempt_count = 2
    delivery.last_attempt_at = datetime.now(timezone.utc)
    await db_session.commit()
    await db_session.refresh(delivery)

    # 3. Worker B arrives while Worker A's SMTP transmission is in progress
    with patch("app.modules.emails.service.EmailService.send_email") as mock_email_send, \
         patch("app.services.smtp.client.SMTPClient.send_email_sync") as mock_smtp:
        result = await CampaignDeliveryService.retry_delivery(
            delivery_id=delivery.id,
            company_id=company_id,
        )
        # Worker B must NOT call send_email or SMTP
        mock_email_send.assert_not_called()
        mock_smtp.assert_not_called()

    # Worker B safely exited
    assert result["status"] == "SKIPPED"
    assert "already SENDING" in result["reason"]

    # Delivery remains in SENDING for Worker A and attempt_count is preserved
    await db_session.refresh(delivery)
    assert delivery.status == CampaignDeliveryStatus.SENDING.value
    assert delivery.attempt_count == 2


@pytest.mark.anyio
async def test_05_already_bounced_delivery_is_not_retried(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Verify that a confirmed BOUNCED delivery is skipped and never retried."""
    token = await register_and_login(async_client, "owner_c9_05@test.com", "Owner C9-05")
    company_id = await create_company_helper(async_client, token, "C9 Org 05")
    camp_id, _, recip_id = await setup_test_campaign(async_client, db_session, token, company_id)

    delivery = CampaignDelivery(
        campaign_id=camp_id,
        recipient_id=recip_id,
        status=CampaignDeliveryStatus.BOUNCED.value,
        attempt_count=1,
        bounced_at=datetime.now(timezone.utc),
        error_message="Status: 5.1.1 | Diagnostic: User unknown",
    )
    db_session.add(delivery)
    await db_session.commit()
    await db_session.refresh(delivery)

    with patch("app.services.smtp.client.SMTPClient.send_email_sync") as mock_smtp:
        result = await CampaignDeliveryService.retry_delivery(
            delivery_id=delivery.id,
            company_id=company_id,
        )
        mock_smtp.assert_not_called()

    assert result["status"] == "SKIPPED"
    assert "already BOUNCED" in result["reason"]


@pytest.mark.anyio
async def test_06_suppressed_recipient_cannot_be_retried(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Verify that if a recipient is added to the company suppression list, retry is refused."""
    token = await register_and_login(async_client, "owner_c9_06@test.com", "Owner C9-06")
    company_id = await create_company_helper(async_client, token, "C9 Org 06")
    camp_id, _, recip_id = await setup_test_campaign(async_client, db_session, token, company_id)

    # Pre-suppress the recipient
    recip = await db_session.get(CampaignRecipient, recip_id)
    await SuppressionService.record_bounce_suppression(db_session, company_id, recip.email)
    await db_session.commit()

    delivery = CampaignDelivery(
        campaign_id=camp_id,
        recipient_id=recip_id,
        status=CampaignDeliveryStatus.FAILED.value,
        attempt_count=1,
        error_message="Transient timeout",
    )
    db_session.add(delivery)
    await db_session.commit()
    await db_session.refresh(delivery)

    with patch("app.services.smtp.client.SMTPClient.send_email_sync") as mock_smtp:
        result = await CampaignDeliveryService.retry_delivery(
            delivery_id=delivery.id,
            company_id=company_id,
        )
        mock_smtp.assert_not_called()

    assert result["status"] == "SUPPRESSED"
    await db_session.refresh(delivery)
    assert delivery.status == CampaignDeliveryStatus.FAILED.value
    assert "suppressed" in delivery.error_message.lower()


# =============================================================================
# 4. Campaign State & Tenant Isolation Tests
# =============================================================================

@pytest.mark.anyio
async def test_07_retry_respects_campaign_execution_state(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Verify that a retry refuses execution if the parent campaign is PAUSED or CANCELLED."""
    token = await register_and_login(async_client, "owner_c9_07@test.com", "Owner C9-07")
    company_id = await create_company_helper(async_client, token, "C9 Org 07")
    camp_id, _, recip_id = await setup_test_campaign(async_client, db_session, token, company_id)

    # Set campaign to PAUSED
    camp = await db_session.get(Campaign, camp_id)
    camp.status = CampaignStatus.PAUSED.value
    await db_session.commit()

    delivery = CampaignDelivery(
        campaign_id=camp_id,
        recipient_id=recip_id,
        status=CampaignDeliveryStatus.FAILED.value,
        attempt_count=1,
        error_message="Network issue",
    )
    db_session.add(delivery)
    await db_session.commit()
    await db_session.refresh(delivery)

    with patch("app.services.smtp.client.SMTPClient.send_email_sync") as mock_smtp:
        result = await CampaignDeliveryService.retry_delivery(
            delivery_id=delivery.id,
            company_id=company_id,
        )
        mock_smtp.assert_not_called()

    assert result["status"] == "SKIPPED"
    assert "PAUSED" in result["reason"]


@pytest.mark.anyio
async def test_08_cross_company_retry_is_rejected(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Verify that retrying with a foreign company_id is rejected with NOT_FOUND (tenant isolation)."""
    token_1 = await register_and_login(async_client, "owner_c9_08a@test.com", "Owner C9-08a")
    company_1_id = await create_company_helper(async_client, token_1, "C9 Org 08a")
    camp_id, _, recip_id = await setup_test_campaign(async_client, db_session, token_1, company_1_id)

    token_2 = await register_and_login(async_client, "owner_c9_08b@test.com", "Owner C9-08b")
    company_2_id = await create_company_helper(async_client, token_2, "C9 Org 08b")

    delivery = CampaignDelivery(
        campaign_id=camp_id,
        recipient_id=recip_id,
        status=CampaignDeliveryStatus.FAILED.value,
        attempt_count=1,
        error_message="Network issue",
    )
    db_session.add(delivery)
    await db_session.commit()
    await db_session.refresh(delivery)

    # Attempt retry using company 2's ID
    result = await CampaignDeliveryService.retry_delivery(
        delivery_id=delivery.id,
        company_id=company_2_id,
    )
    assert result["status"] == "NOT_FOUND"


# =============================================================================
# 5. Celery Asynchronous Task & Backoff Tests
# =============================================================================

@pytest.mark.anyio
async def test_09_celery_retry_task_executes_asynchronously(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Verify that Celery task retry_campaign_delivery_task runs the retry engine."""
    token = await register_and_login(async_client, "owner_c9_09@test.com", "Owner C9-09")
    company_id = await create_company_helper(async_client, token, "C9 Org 09")
    camp_id, _, recip_id = await setup_test_campaign(async_client, db_session, token, company_id)

    delivery = CampaignDelivery(
        campaign_id=camp_id,
        recipient_id=recip_id,
        status=CampaignDeliveryStatus.FAILED.value,
        attempt_count=1,
        error_message="Connection refused",
    )
    db_session.add(delivery)
    await db_session.commit()
    await db_session.refresh(delivery)

    from app.workers import tasks
    orig_session_maker = tasks.WorkerAsyncSessionLocal
    tasks.WorkerAsyncSessionLocal = TestAsyncSessionLocal

    try:
        with patch("app.services.smtp.client.SMTPClient.send_email_sync", return_value=None):
            result = await _async_retry_campaign_delivery_task(
                delivery_id=delivery.id,
                company_id=company_id,
            )
            assert result["status"] == "SENT"
            assert result["attempt_count"] == 2
    finally:
        tasks.WorkerAsyncSessionLocal = orig_session_maker


def test_10_retry_backoff_and_scheduling():
    """Verify exponential backoff calculation and max-retry bound in schedule_delivery_retry."""
    with patch("app.workers.campaign_tasks.retry_campaign_delivery_task.apply_async") as mock_apply:
        # Attempt 1 -> countdown = 60 * 2^0 = 60s
        CampaignDeliveryService.schedule_delivery_retry(delivery_id=101, company_id=1, attempt_count=1)
        mock_apply.assert_called_once()
        _, kwargs = mock_apply.call_args
        assert kwargs["countdown"] == 60

    with patch("app.workers.campaign_tasks.retry_campaign_delivery_task.apply_async") as mock_apply:
        # Attempt 2 -> countdown = 60 * 2^1 = 120s
        CampaignDeliveryService.schedule_delivery_retry(delivery_id=101, company_id=1, attempt_count=2)
        mock_apply.assert_called_once()
        _, kwargs = mock_apply.call_args
        assert kwargs["countdown"] == 120

    with patch("app.workers.campaign_tasks.retry_campaign_delivery_task.apply_async") as mock_apply:
        # Attempt >= max_retries (3) -> does NOT schedule
        res = CampaignDeliveryService.schedule_delivery_retry(delivery_id=101, company_id=1, attempt_count=3)
        mock_apply.assert_not_called()
        assert res is None


# =============================================================================
# 6. Bounce Correlation & Suppression Tests
# =============================================================================

@pytest.mark.anyio
async def test_11_bounce_correlation_marks_delivery_bounced_and_creates_suppression(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Verify that an incoming bounce matching original Message-ID:
    - Marks outgoing Email as BOUNCED with diagnostic.
    - Marks CampaignDelivery as BOUNCED with bounced_at and diagnostic.
    - Creates a company-scoped BOUNCE SuppressionEntry.
    - Leaves CampaignRecipient.status unchanged.
    """
    token = await register_and_login(async_client, "owner_c9_11@test.com", "Owner C9-11")
    company_id = await create_company_helper(async_client, token, "C9 Org 11")
    camp_id, acc_id, recip_id = await setup_test_campaign(async_client, db_session, token, company_id)

    # 1. Create original outgoing Email record
    msg_id = "<orig-camp-msg-101@testmail.com>"
    orig_email = Email(
        company_id=company_id,
        email_account_id=acc_id,
        direction=EmailDirection.OUTGOING.value,
        status=EmailStatus.SENT.value,
        message_id=msg_id,
        sender=f"sender@testmail.com",
        recipients=[f"target@testmail.com"],
        subject="Hello Target",
        body_text="Hi Target",
        is_read=True,
    )
    db_session.add(orig_email)
    await db_session.flush()

    # 2. Create CampaignDelivery linked to this Email
    delivery = CampaignDelivery(
        campaign_id=camp_id,
        recipient_id=recip_id,
        status=CampaignDeliveryStatus.SENT.value,
        email_id=orig_email.id,
        message_id=msg_id,
        sent_at=datetime.now(timezone.utc),
        attempt_count=1,
    )
    db_session.add(delivery)
    await db_session.commit()

    # 3. Process an incoming bounce notification
    account = await db_session.get(EmailAccount, acc_id)
    raw_bounce = make_rfc3464_dsn_bounce(
        bounce_msg_id="<bounce-101@mail.server.com>",
        orig_msg_id=msg_id,
        recipient="target@testmail.com",
        action="failed",
        status_code="5.1.1",
        diagnostic_code="smtp; 550 5.1.1 User unknown",
    )
    parsed_bounce = EmailParser.parse_raw_email(raw_bounce)

    matched_email = await EmailMonitoringService.match_and_process_bounce(
        db=db_session,
        account=account,
        parsed=parsed_bounce,
    )
    await db_session.commit()

    assert matched_email is not None
    assert matched_email.id == orig_email.id
    assert matched_email.status == EmailStatus.BOUNCED.value

    # 4. Verify CampaignDelivery transitioned to BOUNCED
    await db_session.refresh(delivery)
    assert delivery.status == CampaignDeliveryStatus.BOUNCED.value
    assert delivery.bounced_at is not None
    assert "5.1.1" in (delivery.error_message or "")
    assert "User unknown" in (delivery.error_message or "")

    # 5. Verify company SuppressionEntry was created
    supp_res = await db_session.execute(
        select(SuppressionEntry).where(
            SuppressionEntry.company_id == company_id,
            SuppressionEntry.email == "target@testmail.com",
        )
    )
    supp_entry = supp_res.scalar_one_or_none()
    assert supp_entry is not None
    assert supp_entry.reason == SuppressionReason.BOUNCE.value

    # 6. Verify CampaignRecipient.status transitioned to BOUNCED
    recip = await db_session.get(CampaignRecipient, recip_id)
    assert recip.status == CampaignRecipientStatus.BOUNCED.value

    # 7. Verify recipient-list API displays BOUNCED
    recip_resp = await async_client.get(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}/recipients",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert recip_resp.status_code == 200
    recipients_data = recip_resp.json()
    assert len(recipients_data) >= 1
    matched_recip_data = next(r for r in recipients_data if r["id"] == recip_id)
    assert matched_recip_data["status"] == "BOUNCED"

    # 8. Verify status remains BOUNCED after refetching the list again
    recip_resp2 = await async_client.get(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}/recipients",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert recip_resp2.status_code == 200
    matched_recip_data2 = next(r for r in recip_resp2.json() if r["id"] == recip_id)
    assert matched_recip_data2["status"] == "BOUNCED"


@pytest.mark.anyio
async def test_12_existing_suppression_not_duplicated_on_bounce(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Verify that if an address is already suppressed, a bounce does not insert a duplicate row."""
    token = await register_and_login(async_client, "owner_c9_12@test.com", "Owner C9-12")
    company_id = await create_company_helper(async_client, token, "C9 Org 12")
    camp_id, acc_id, recip_id = await setup_test_campaign(async_client, db_session, token, company_id)

    # Pre-existing suppression entry with reason MANUAL
    recip = await db_session.get(CampaignRecipient, recip_id)
    pre_supp = SuppressionEntry(
        company_id=company_id,
        email=recip.email,
        reason=SuppressionReason.MANUAL.value,
    )
    db_session.add(pre_supp)
    await db_session.commit()

    msg_id = "<orig-msg-12@testmail.com>"
    orig_email = Email(
        company_id=company_id,
        email_account_id=acc_id,
        direction=EmailDirection.OUTGOING.value,
        status=EmailStatus.SENT.value,
        message_id=msg_id,
        sender="sender@testmail.com",
        recipients=[recip.email],
        subject="Invoice",
        is_read=True,
    )
    db_session.add(orig_email)
    await db_session.flush()

    delivery = CampaignDelivery(
        campaign_id=camp_id,
        recipient_id=recip_id,
        status=CampaignDeliveryStatus.SENT.value,
        email_id=orig_email.id,
        message_id=msg_id,
    )
    db_session.add(delivery)
    await db_session.commit()

    account = await db_session.get(EmailAccount, acc_id)
    raw_bounce = make_rfc3464_dsn_bounce(
        bounce_msg_id="<bounce-12@mail.server.com>",
        orig_msg_id=msg_id,
        recipient=recip.email,
        action="failed",
        status_code="5.1.1",
        diagnostic_code="550 Mailbox not found",
    )
    parsed_bounce = EmailParser.parse_raw_email(raw_bounce)

    await EmailMonitoringService.match_and_process_bounce(
        db=db_session,
        account=account,
        parsed=parsed_bounce,
    )
    await db_session.commit()

    # Verify only 1 suppression row exists
    supp_rows = (await db_session.execute(
        select(SuppressionEntry).where(
            SuppressionEntry.company_id == company_id,
            SuppressionEntry.email == recip.email,
        )
    )).scalars().all()
    assert len(supp_rows) == 1


@pytest.mark.anyio
async def test_13_non_campaign_bounced_email_preserves_standard_behavior(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Verify that an incoming bounce for a non-campaign Email updates Email.status to BOUNCED
    without attempting to mutate CampaignDelivery or creating campaign suppression entries.
    """
    token = await register_and_login(async_client, "owner_c9_13@test.com", "Owner C9-13")
    company_id = await create_company_helper(async_client, token, "C9 Org 13")
    acc_id = await create_account_helper(async_client, token, company_id)

    msg_id = "<normal-outgoing-99@testmail.com>"
    orig_email = Email(
        company_id=company_id,
        email_account_id=acc_id,
        direction=EmailDirection.OUTGOING.value,
        status=EmailStatus.SENT.value,
        message_id=msg_id,
        sender="sender@testmail.com",
        recipients=["normal_user@external.com"],
        subject="Direct 1-to-1 Email",
        is_read=True,
    )
    db_session.add(orig_email)
    await db_session.commit()

    account = await db_session.get(EmailAccount, acc_id)
    raw_bounce = make_rfc3464_dsn_bounce(
        bounce_msg_id="<bounce-13@mail.server.com>",
        orig_msg_id=msg_id,
        recipient="normal_user@external.com",
        action="failed",
        status_code="5.1.1",
        diagnostic_code="Mailbox inactive",
    )
    parsed_bounce = EmailParser.parse_raw_email(raw_bounce)

    matched = await EmailMonitoringService.match_and_process_bounce(
        db=db_session,
        account=account,
        parsed=parsed_bounce,
    )
    await db_session.commit()

    assert matched is not None
    assert matched.status == EmailStatus.BOUNCED.value

    # Verify zero suppression entries created
    supp_count = await db_session.scalar(
        select(func.count(SuppressionEntry.id)).where(SuppressionEntry.company_id == company_id)
    )
    assert supp_count == 0


@pytest.mark.anyio
async def test_14_retry_and_bounce_race_condition_safety(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Verify race condition safety: If a bounce arrives while retry SMTP transmission
    is in flight, the retry completion does NOT overwrite terminal BOUNCED status with SENT.
    """
    token = await register_and_login(async_client, "owner_c9_14@test.com", "Owner C9-14")
    company_id = await create_company_helper(async_client, token, "C9 Org 14")
    camp_id, _, recip_id = await setup_test_campaign(async_client, db_session, token, company_id)

    delivery = CampaignDelivery(
        campaign_id=camp_id,
        recipient_id=recip_id,
        status=CampaignDeliveryStatus.FAILED.value,
        attempt_count=1,
        error_message="Transient timeout",
    )
    db_session.add(delivery)
    await db_session.commit()
    await db_session.refresh(delivery)

    # Define mock send that simulates a concurrent bounce updating delivery while sending
    async def side_effect_send_with_race(*args, **kwargs):
        # Concurrently mark delivery as BOUNCED in a separate session
        async with TestAsyncSessionLocal() as concurrent_db:
            concurrent_deliv = await concurrent_db.get(CampaignDelivery, delivery.id)
            concurrent_deliv.status = CampaignDeliveryStatus.BOUNCED.value
            concurrent_deliv.bounced_at = datetime.now(timezone.utc)
            await concurrent_db.commit()

        # Return a simulated sent Email record
        return Email(
            id=999,
            company_id=company_id,
            email_account_id=delivery.campaign.email_account_id,
            direction=EmailDirection.OUTGOING.value,
            status=EmailStatus.SENT.value,
            message_id="<race-msg@testmail.com>",
            sender="sender@testmail.com",
            recipients=["target@testmail.com"],
            subject="Hello",
            is_read=True,
        )

    with patch("app.modules.emails.service.EmailService.send_email", side_effect=side_effect_send_with_race):
        result = await CampaignDeliveryService.retry_delivery(
            delivery_id=delivery.id,
            company_id=company_id,
        )

    # Must retain terminal BOUNCED status
    assert result["status"] == "BOUNCED"
    await db_session.refresh(delivery)
    assert delivery.status == CampaignDeliveryStatus.BOUNCED.value


@pytest.mark.anyio
async def test_15_duplicate_bounce_processing_is_idempotent_and_preserves_bounced_status(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Verify duplicate IMAP bounce processing is strictly idempotent, does not create
    duplicate suppression entries, and keeps recipient status BOUNCED.
    """
    token = await register_and_login(async_client, "owner_c9_15@test.com", "Owner C9-15")
    company_id = await create_company_helper(async_client, token, "C9 Org 15")
    camp_id, acc_id, recip_id = await setup_test_campaign(async_client, db_session, token, company_id)

    recip = await db_session.get(CampaignRecipient, recip_id)

    msg_id = "<orig-camp-msg-15@testmail.com>"
    orig_email = Email(
        company_id=company_id,
        email_account_id=acc_id,
        direction=EmailDirection.OUTGOING.value,
        status=EmailStatus.SENT.value,
        message_id=msg_id,
        sender="sender@testmail.com",
        recipients=[recip.email],
        subject="Hello Target 15",
        is_read=True,
    )
    db_session.add(orig_email)
    await db_session.flush()

    delivery = CampaignDelivery(
        campaign_id=camp_id,
        recipient_id=recip_id,
        status=CampaignDeliveryStatus.SENT.value,
        email_id=orig_email.id,
        message_id=msg_id,
        sent_at=datetime.now(timezone.utc),
        attempt_count=1,
    )
    db_session.add(delivery)
    await db_session.commit()

    account = await db_session.get(EmailAccount, acc_id)
    raw_bounce = make_rfc3464_dsn_bounce(
        bounce_msg_id="<bounce-15@mail.server.com>",
        orig_msg_id=msg_id,
        recipient=recip.email,
        action="failed",
        status_code="5.1.1",
        diagnostic_code="smtp; 550 User not found",
    )
    parsed_bounce = EmailParser.parse_raw_email(raw_bounce)

    # First bounce event
    first_match = await EmailMonitoringService.record_bounce_event(
        db=db_session,
        account=account,
        parsed=parsed_bounce,
    )
    await db_session.commit()
    assert first_match is not None

    recip = await db_session.get(CampaignRecipient, recip_id)
    assert recip.status == CampaignRecipientStatus.BOUNCED.value

    # Second bounce event (duplicate IMAP sync)
    second_match = await EmailMonitoringService.record_bounce_event(
        db=db_session,
        account=account,
        parsed=parsed_bounce,
    )
    await db_session.commit()
    assert second_match is not None

    # Status remains BOUNCED consistently
    await db_session.refresh(recip)
    assert recip.status == CampaignRecipientStatus.BOUNCED.value
    await db_session.refresh(delivery)
    assert delivery.status == CampaignDeliveryStatus.BOUNCED.value

    # Exactly 1 suppression entry exists
    supp_entries = (await db_session.execute(
        select(SuppressionEntry).where(
            SuppressionEntry.company_id == company_id,
            SuppressionEntry.email == recip.email,
        )
    )).scalars().all()
    assert len(supp_entries) == 1

    # Recipient API returns BOUNCED
    api_resp = await async_client.get(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}/recipients",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert api_resp.status_code == 200
    recips_json = api_resp.json()
    assert recips_json[0]["status"] == "BOUNCED"


@pytest.mark.anyio
async def test_16_uncorrelated_or_non_bounce_preserves_tenant_isolation_and_statuses(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Verify company-level isolation: a bounce in company B cannot mutate company A's recipient,
    and non-bounce incoming messages do not trigger bounce status transitions.
    """
    token_a = await register_and_login(async_client, "owner_c9_16a@test.com", "Owner C9-16A")
    company_id_a = await create_company_helper(async_client, token_a, "C9 Org 16A")
    camp_id_a, acc_id_a, recip_id_a = await setup_test_campaign(async_client, db_session, token_a, company_id_a)

    # Set recipient and delivery to SENT
    recip_a = await db_session.get(CampaignRecipient, recip_id_a)
    recip_a.status = CampaignRecipientStatus.SENT.value

    msg_id_a = "<camp-a-msg@testmail.com>"
    orig_email_a = Email(
        company_id=company_id_a,
        email_account_id=acc_id_a,
        direction=EmailDirection.OUTGOING.value,
        status=EmailStatus.SENT.value,
        message_id=msg_id_a,
        sender="sender_a@testmail.com",
        recipients=[recip_a.email],
        subject="Camp A Email",
        is_read=True,
    )
    db_session.add(orig_email_a)
    await db_session.flush()

    delivery_a = CampaignDelivery(
        campaign_id=camp_id_a,
        recipient_id=recip_id_a,
        status=CampaignDeliveryStatus.SENT.value,
        email_id=orig_email_a.id,
        message_id=msg_id_a,
        sent_at=datetime.now(timezone.utc),
        attempt_count=1,
    )
    db_session.add(delivery_a)
    await db_session.commit()

    # Company B setup
    token_b = await register_and_login(async_client, "owner_c9_16b@test.com", "Owner C9-16B")
    company_id_b = await create_company_helper(async_client, token_b, "C9 Org 16B")
    acc_id_b = await create_account_helper(async_client, token_b, company_id_b)
    account_b = await db_session.get(EmailAccount, acc_id_b)

    # Bounce arriving for Account B referencing Company A's message-id
    cross_tenant_bounce = make_rfc3464_dsn_bounce(
        bounce_msg_id="<cross-tenant-bounce@mail.server.com>",
        orig_msg_id=msg_id_a,
        recipient=recip_a.email,
        action="failed",
        status_code="5.1.1",
        diagnostic_code="smtp; 550 Rejected",
    )
    parsed_cross = EmailParser.parse_raw_email(cross_tenant_bounce)

    res = await EmailMonitoringService.record_bounce_event(
        db=db_session,
        account=account_b,
        parsed=parsed_cross,
    )
    await db_session.commit()
    assert res is None

    # Company A recipient and delivery MUST remain SENT
    await db_session.refresh(recip_a)
    assert recip_a.status == CampaignRecipientStatus.SENT.value
    await db_session.refresh(delivery_a)
    assert delivery_a.status == CampaignDeliveryStatus.SENT.value

    # Non-bounce incoming email for Account A
    account_a = await db_session.get(EmailAccount, acc_id_a)
    normal_reply_raw = (
        f"From: {recip_a.email}\r\n"
        f"To: sender_a@testmail.com\r\n"
        f"In-Reply-To: {msg_id_a}\r\n"
        f"Subject: Re: Camp A Email\r\n"
        f"Message-ID: <reply-16@client.com>\r\n\r\n"
        f"Thanks for the update!"
    ).encode("utf-8")
    parsed_normal = EmailParser.parse_raw_email(normal_reply_raw)
    assert parsed_normal.is_bounce is False

    res_normal = await EmailMonitoringService.record_bounce_event(
        db=db_session,
        account=account_a,
        parsed=parsed_normal,
    )
    assert res_normal is None

    # Status remains SENT
    await db_session.refresh(recip_a)
    assert recip_a.status == CampaignRecipientStatus.SENT.value



# Helper for account creation without domain
async def create_account_helper(async_client: AsyncClient, token: str, company_id: int) -> int:
    resp = await async_client.post(
        f"/api/v1/companies/{company_id}/email-accounts",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Sync Account",
            "email_address": f"sync_acc_{company_id}@external.com",
            "provider": "CUSTOM",
            "smtp_host": "smtp.external.com",
            "smtp_port": 587,
            "smtp_username": f"sync_acc_{company_id}@external.com",
            "smtp_password": "password123",
            "smtp_security": "STARTTLS",
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]
