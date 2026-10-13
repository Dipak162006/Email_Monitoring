from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import uuid
from httpx import AsyncClient
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import User
from app.modules.campaigns.delivery_service import CampaignDeliveryService
from app.modules.campaigns.models import (
    Campaign,
    CampaignDelivery,
    CampaignDeliveryStatus,
    CampaignRecipient,
    CampaignRecipientStatus,
    CampaignStatus,
)
from app.modules.campaigns.scheduling_service import CampaignSchedulingService
from app.modules.campaigns.service import CampaignService
from app.modules.companies.models import Company, CompanyRole, CompanyUser
from app.modules.domains.models import Domain, DomainVerificationStatus
from app.modules.email_accounts.models import EmailAccount
from app.modules.emails.models import Email
from app.services.transport.models import EmailTransportResult
from app.workers import tasks
from app.workers.campaign_tasks import (
    _async_dispatch_campaign_task,
    _async_retry_campaign_delivery_task,
    dispatch_campaign_task,
    scheduled_campaign_dispatch_task,
)
from tests.conftest import TestAsyncSessionLocal


# =============================================================================
# Fixtures & Setup
# =============================================================================

@pytest.fixture(autouse=True)
def configure_worker_db():
    """Ensure worker tasks use the test database."""
    orig_session_maker = tasks.WorkerAsyncSessionLocal
    tasks.WorkerAsyncSessionLocal = TestAsyncSessionLocal
    yield
    tasks.WorkerAsyncSessionLocal = orig_session_maker


async def register_and_login(client: AsyncClient, email: str, name: str = "Test User") -> str:
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123!", "full_name": name},
    )
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    return login_resp.json()["access_token"]


async def create_company_helper(client: AsyncClient, token: str, name: str = "Controls Org") -> int:
    resp = await client.post(
        "/api/v1/companies/",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": name},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def setup_test_campaign(
    client: AsyncClient,
    db: AsyncSession,
    owner_token: str,
    company_id: int,
    subject: str = "Schedule Test",
    body: str = "Schedule body text",
) -> tuple[int, int]:
    dom_suffix = uuid.uuid4().hex[:6]
    domain_name = f"org{company_id}-{dom_suffix}.com"

    # Domain
    dom_resp = await client.post(
        f"/api/v1/companies/{company_id}/domains",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"domain_name": domain_name},
    )
    dom_id = dom_resp.json()["id"]

    dom_res = await db.execute(select(Domain).where(Domain.id == dom_id))
    domain = dom_res.scalar_one()
    domain.verification_status = DomainVerificationStatus.VERIFIED.value
    await db.commit()

    # Sender Account
    sender_email = f"sender@{domain_name}"
    acc_resp = await client.post(
        f"/api/v1/companies/{company_id}/email-accounts",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "name": "Sender Account",
            "email_address": sender_email,
            "provider": "CUSTOM",
            "smtp_host": "smtp.test.com",
            "smtp_port": 587,
            "smtp_security": "STARTTLS",
            "smtp_username": sender_email,
            "smtp_password": "Pass!",
            "imap_host": "imap.test.com",
            "imap_port": 993,
            "imap_security": "SSL",
            "imap_username": sender_email,
            "imap_password": "Pass!",
            "domain_id": dom_id,
        },
    )
    acc_id = acc_resp.json()["id"]

    # Campaign
    camp_resp = await client.post(
        f"/api/v1/companies/{company_id}/campaigns",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "name": "C10 Campaign",
            "email_account_id": acc_id,
            "subject": subject,
            "body_text": body,
            "body_html": f"<p>{body}</p>",
        },
    )
    assert camp_resp.status_code == 201
    return camp_resp.json()["id"], acc_id


async def add_recipient(
    client: AsyncClient,
    token: str,
    company_id: int,
    campaign_id: int,
    email: str,
    first_name: str = "Alice",
) -> int:
    resp = await client.post(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/recipients",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": email, "first_name": first_name},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


# =============================================================================
# C10 Tests
# =============================================================================

@pytest.mark.asyncio
async def test_01_scheduled_campaign_dispatches_when_due(async_client: AsyncClient, db_session: AsyncSession):
    """1. SCHEDULED campaign dispatches when scheduled_at has arrived."""
    token = await register_and_login(async_client, "sched1@example.com")
    comp_id = await create_company_helper(async_client, token, "Sched Org 1")
    camp_id, _ = await setup_test_campaign(async_client, db_session, token, comp_id)
    await add_recipient(async_client, token, comp_id, camp_id, "recip1@example.com")

    # Schedule campaign for 5 minutes ago (due)
    due_time = datetime.now(timezone.utc) - timedelta(minutes=5)
    sched_resp = await async_client.post(
        f"/api/v1/companies/{comp_id}/campaigns/{camp_id}/schedule",
        headers={"Authorization": f"Bearer {token}"},
        json={"scheduled_at": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()},
    )
    assert sched_resp.status_code == 200
    assert sched_resp.json()["status"] == CampaignStatus.SCHEDULED.value

    # Manually update scheduled_at to past in DB to simulate time arrived
    camp_res = await db_session.execute(select(Campaign).where(Campaign.id == camp_id))
    camp = camp_res.scalar_one()
    camp.scheduled_at = due_time
    await db_session.commit()

    with patch("app.workers.campaign_tasks.dispatch_campaign_task.delay") as mock_delay:
        mock_task = MagicMock()
        mock_task.id = "mock-task-sched-1"
        mock_delay.return_value = mock_task

        outcomes = await CampaignSchedulingService.dispatch_due_campaigns()

        assert len(outcomes) >= 1
        matched = [o for o in outcomes if o["campaign_id"] == camp_id]
        assert len(matched) == 1
        assert matched[0]["status"] == "DISPATCHED"
        mock_delay.assert_called_once_with(campaign_id=camp_id, company_id=comp_id)

    # Verify state in DB is QUEUED
    await db_session.refresh(camp)
    assert camp.status == CampaignStatus.QUEUED.value


@pytest.mark.asyncio
async def test_02_future_scheduled_campaign_not_dispatched_early(async_client: AsyncClient, db_session: AsyncSession):
    """2. Future SCHEDULED campaign is not dispatched early."""
    token = await register_and_login(async_client, "sched2@example.com")
    comp_id = await create_company_helper(async_client, token, "Sched Org 2")
    camp_id, _ = await setup_test_campaign(async_client, db_session, token, comp_id)
    await add_recipient(async_client, token, comp_id, camp_id, "recip2@example.com")

    # Schedule in future
    future_time = datetime.now(timezone.utc) + timedelta(hours=2)
    sched_resp = await async_client.post(
        f"/api/v1/companies/{comp_id}/campaigns/{camp_id}/schedule",
        headers={"Authorization": f"Bearer {token}"},
        json={"scheduled_at": future_time.isoformat()},
    )
    assert sched_resp.status_code == 200

    with patch("app.workers.campaign_tasks.dispatch_campaign_task.delay") as mock_delay:
        outcomes = await CampaignSchedulingService.dispatch_due_campaigns()
        matched = [o for o in outcomes if o["campaign_id"] == camp_id]
        assert len(matched) == 0
        mock_delay.assert_not_called()

    camp_res = await db_session.execute(select(Campaign).where(Campaign.id == camp_id))
    camp = camp_res.scalar_one()
    assert camp.status == CampaignStatus.SCHEDULED.value


@pytest.mark.asyncio
async def test_03_multiple_scheduler_ticks_duplicate_protection(async_client: AsyncClient, db_session: AsyncSession):
    """3. Multiple scheduler ticks cannot enqueue the same campaign twice."""
    token = await register_and_login(async_client, "sched3@example.com")
    comp_id = await create_company_helper(async_client, token, "Sched Org 3")
    camp_id, _ = await setup_test_campaign(async_client, db_session, token, comp_id)
    await add_recipient(async_client, token, comp_id, camp_id, "recip3@example.com")

    # Make campaign SCHEDULED and due
    camp_res = await db_session.execute(select(Campaign).where(Campaign.id == camp_id))
    camp = camp_res.scalar_one()
    camp.status = CampaignStatus.SCHEDULED.value
    camp.scheduled_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    await db_session.commit()

    with patch("app.workers.campaign_tasks.dispatch_campaign_task.delay") as mock_delay:
        mock_task = MagicMock()
        mock_task.id = "mock-task-tick-1"
        mock_delay.return_value = mock_task

        # Tick 1: dispatches
        tick1 = await CampaignSchedulingService.dispatch_due_campaigns()
        matched1 = [o for o in tick1 if o["campaign_id"] == camp_id]
        assert matched1[0]["status"] == "DISPATCHED"
        assert mock_delay.call_count == 1

        # Tick 2: status is now QUEUED, so candidate query ignores it completely
        tick2 = await CampaignSchedulingService.dispatch_due_campaigns()
        matched2 = [o for o in tick2 if o["campaign_id"] == camp_id]
        assert len(matched2) == 0
        assert mock_delay.call_count == 1  # No second enqueue


@pytest.mark.asyncio
async def test_04_scheduled_to_queued_occurs_before_celery_execution(async_client: AsyncClient, db_session: AsyncSession):
    """4. SCHEDULED -> QUEUED occurs before Celery delivery execution."""
    token = await register_and_login(async_client, "sched4@example.com")
    comp_id = await create_company_helper(async_client, token, "Sched Org 4")
    camp_id, _ = await setup_test_campaign(async_client, db_session, token, comp_id)
    await add_recipient(async_client, token, comp_id, camp_id, "recip4@example.com")

    camp_res = await db_session.execute(select(Campaign).where(Campaign.id == camp_id))
    camp = camp_res.scalar_one()
    camp.status = CampaignStatus.SCHEDULED.value
    camp.scheduled_at = datetime.now(timezone.utc) - timedelta(minutes=2)
    await db_session.commit()

    with patch("app.workers.campaign_tasks.dispatch_campaign_task.delay") as mock_d:
        mock_d.return_value = MagicMock(id="task-before-delivery")
        await CampaignSchedulingService.dispatch_due_campaigns()
        assert mock_d.call_count == 1

    await db_session.refresh(camp)
    assert camp.status == CampaignStatus.QUEUED.value


@pytest.mark.asyncio
async def test_05_scheduler_ignores_cancelled_and_paused_campaigns(async_client: AsyncClient, db_session: AsyncSession):
    """5 & 6. Scheduler ignores CANCELLED and PAUSED campaigns even if scheduled_at is past."""
    token = await register_and_login(async_client, "sched5@example.com")
    comp_id = await create_company_helper(async_client, token, "Sched Org 5")
    camp_id1, _ = await setup_test_campaign(async_client, db_session, token, comp_id)
    camp_id2, _ = await setup_test_campaign(async_client, db_session, token, comp_id)

    # Set camp1 to CANCELLED and past scheduled_at
    c1 = (await db_session.execute(select(Campaign).where(Campaign.id == camp_id1))).scalar_one()
    c1.status = CampaignStatus.CANCELLED.value
    c1.scheduled_at = datetime.now(timezone.utc) - timedelta(minutes=10)

    # Set camp2 to PAUSED and past scheduled_at
    c2 = (await db_session.execute(select(Campaign).where(Campaign.id == camp_id2))).scalar_one()
    c2.status = CampaignStatus.PAUSED.value
    c2.scheduled_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    await db_session.commit()

    with patch("app.workers.campaign_tasks.dispatch_campaign_task.delay") as mock_delay:
        outcomes = await CampaignSchedulingService.dispatch_due_campaigns()
        matched1 = [o for o in outcomes if o["campaign_id"] == camp_id1]
        matched2 = [o for o in outcomes if o["campaign_id"] == camp_id2]
        assert len(matched1) == 0
        assert len(matched2) == 0
        mock_delay.assert_not_called()


@pytest.mark.asyncio
async def test_06_running_to_paused_state_transition(async_client: AsyncClient, db_session: AsyncSession):
    """7. RUNNING -> PAUSED works through centralized state machine."""
    token = await register_and_login(async_client, "pause1@example.com")
    comp_id = await create_company_helper(async_client, token, "Pause Org 1")
    camp_id, _ = await setup_test_campaign(async_client, db_session, token, comp_id)

    # Set to RUNNING
    camp = (await db_session.execute(select(Campaign).where(Campaign.id == camp_id))).scalar_one()
    camp.status = CampaignStatus.RUNNING.value
    await db_session.commit()

    resp = await async_client.post(
        f"/api/v1/companies/{comp_id}/campaigns/{camp_id}/pause",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == CampaignStatus.PAUSED.value

    await db_session.refresh(camp)
    assert camp.status == CampaignStatus.PAUSED.value


@pytest.mark.asyncio
async def test_07_paused_worker_stops_and_preserves_paused(async_client: AsyncClient, db_session: AsyncSession):
    """8 & 9. Paused worker stops before starting another recipient and is not marked COMPLETED."""
    token = await register_and_login(async_client, "pause2@example.com")
    comp_id = await create_company_helper(async_client, token, "Pause Org 2")
    camp_id, acc_id = await setup_test_campaign(async_client, db_session, token, comp_id)

    r1_id = await add_recipient(async_client, token, comp_id, camp_id, "recip1@test.com")
    r2_id = await add_recipient(async_client, token, comp_id, camp_id, "recip2@test.com")
    r3_id = await add_recipient(async_client, token, comp_id, camp_id, "recip3@test.com")

    # Set to QUEUED
    camp = (await db_session.execute(select(Campaign).where(Campaign.id == camp_id))).scalar_one()
    camp.status = CampaignStatus.QUEUED.value
    await db_session.commit()

    send_call_count = 0

    async def fake_transport_send(request):
        nonlocal send_call_count
        send_call_count += 1
        # During recipient 1's send, simulate user pausing the campaign in DB
        async with TestAsyncSessionLocal() as pause_db:
            c = (await pause_db.execute(select(Campaign).where(Campaign.id == camp_id))).scalar_one()
            c.status = CampaignStatus.PAUSED.value
            await pause_db.commit()
        return EmailTransportResult(success=True, message_id=f"<msg-{send_call_count}@test.com>")

    with patch("app.services.transport.smtp.SMTPTransport.send", side_effect=fake_transport_send):
        result = await CampaignDeliveryService.execute_campaign(
            campaign_id=camp_id,
            company_id=comp_id,
            db_factory=TestAsyncSessionLocal,
        )

    assert result["status"] == CampaignStatus.PAUSED.value
    assert result["sent_count"] == 1
    # Only 1 email was sent (recipient 1), recipients 2 and 3 were halted
    assert send_call_count == 1

    # Campaign in DB must remain PAUSED (NOT COMPLETED)
    await db_session.refresh(camp)
    assert camp.status == CampaignStatus.PAUSED.value

    # Recipient 1 is SENT; Recipients 2 & 3 remain PENDING
    rec1 = (await db_session.execute(select(CampaignRecipient).where(CampaignRecipient.id == r1_id))).scalar_one()
    rec2 = (await db_session.execute(select(CampaignRecipient).where(CampaignRecipient.id == r2_id))).scalar_one()
    rec3 = (await db_session.execute(select(CampaignRecipient).where(CampaignRecipient.id == r3_id))).scalar_one()
    assert rec1.status == CampaignRecipientStatus.SENT.value
    assert rec2.status == CampaignRecipientStatus.PENDING.value
    assert rec3.status == CampaignRecipientStatus.PENDING.value


@pytest.mark.asyncio
async def test_08_resume_campaign_continues_without_resending_sent(async_client: AsyncClient, db_session: AsyncSession):
    """10 & 11. PAUSED -> RUNNING works and resume continues pending recipients without resending SENT."""
    token = await register_and_login(async_client, "resume1@example.com")
    comp_id = await create_company_helper(async_client, token, "Resume Org")
    camp_id, acc_id = await setup_test_campaign(async_client, db_session, token, comp_id)

    r1_id = await add_recipient(async_client, token, comp_id, camp_id, "recip1@resume.com")
    r2_id = await add_recipient(async_client, token, comp_id, camp_id, "recip2@resume.com")

    # Recipient 1 already has a SENT delivery
    camp = (await db_session.execute(select(Campaign).where(Campaign.id == camp_id))).scalar_one()
    camp.status = CampaignStatus.PAUSED.value

    rec1 = (await db_session.execute(select(CampaignRecipient).where(CampaignRecipient.id == r1_id))).scalar_one()
    rec1.status = CampaignRecipientStatus.SENT.value

    deliv1 = CampaignDelivery(
        campaign_id=camp_id,
        recipient_id=r1_id,
        status=CampaignDeliveryStatus.SENT.value,
        attempt_count=1,
        sent_at=datetime.now(timezone.utc),
    )
    db_session.add(deliv1)
    await db_session.commit()

    # Resume campaign via API
    with patch("app.workers.campaign_tasks.dispatch_campaign_task.delay") as mock_delay:
        resp = await async_client.post(
            f"/api/v1/companies/{comp_id}/campaigns/{camp_id}/resume",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == CampaignStatus.RUNNING.value
        mock_delay.assert_called_once_with(campaign_id=camp_id, company_id=comp_id)

    send_call_count = 0

    async def fake_transport_send(request):
        nonlocal send_call_count
        send_call_count += 1
        return EmailTransportResult(success=True, message_id=f"<msg-resume-{send_call_count}@test.com>")

    with patch("app.services.transport.smtp.SMTPTransport.send", side_effect=fake_transport_send):
        result = await CampaignDeliveryService.execute_campaign(
            campaign_id=camp_id,
            company_id=comp_id,
            db_factory=TestAsyncSessionLocal,
        )

    # Only recipient 2 was sent; recipient 1 was NOT resent
    assert result["sent_count"] == 1
    assert send_call_count == 1

    # Campaign is now COMPLETED
    assert result["status"] == CampaignStatus.COMPLETED.value
    await db_session.refresh(camp)
    assert camp.status == CampaignStatus.COMPLETED.value


@pytest.mark.asyncio
async def test_09_running_to_cancelled_halts_processing_and_preserves_cancelled(async_client: AsyncClient, db_session: AsyncSession):
    """12. RUNNING -> CANCELLED prevents additional recipients."""
    token = await register_and_login(async_client, "cancel1@example.com")
    comp_id = await create_company_helper(async_client, token, "Cancel Org 1")
    camp_id, _ = await setup_test_campaign(async_client, db_session, token, comp_id)

    r1_id = await add_recipient(async_client, token, comp_id, camp_id, "recip1@cancel.com")
    r2_id = await add_recipient(async_client, token, comp_id, camp_id, "recip2@cancel.com")

    camp = (await db_session.execute(select(Campaign).where(Campaign.id == camp_id))).scalar_one()
    camp.status = CampaignStatus.QUEUED.value
    await db_session.commit()

    send_call_count = 0

    async def fake_transport_send(request):
        nonlocal send_call_count
        send_call_count += 1
        # Cancel campaign during recipient 1 send
        async with TestAsyncSessionLocal() as cancel_db:
            c = (await cancel_db.execute(select(Campaign).where(Campaign.id == camp_id))).scalar_one()
            c.status = CampaignStatus.CANCELLED.value
            await cancel_db.commit()
        return EmailTransportResult(success=True, message_id=f"<msg-cancel-{send_call_count}@test.com>")

    with patch("app.services.transport.smtp.SMTPTransport.send", side_effect=fake_transport_send):
        result = await CampaignDeliveryService.execute_campaign(
            campaign_id=camp_id,
            company_id=comp_id,
            db_factory=TestAsyncSessionLocal,
        )

    assert result["status"] == CampaignStatus.CANCELLED.value
    assert result["sent_count"] == 1
    assert send_call_count == 1

    await db_session.refresh(camp)
    assert camp.status == CampaignStatus.CANCELLED.value

    # Recipient 2 remained pending
    rec2 = (await db_session.execute(select(CampaignRecipient).where(CampaignRecipient.id == r2_id))).scalar_one()
    assert rec2.status == CampaignRecipientStatus.PENDING.value


@pytest.mark.asyncio
async def test_10_paused_to_cancelled_and_cannot_resume_or_schedule(async_client: AsyncClient, db_session: AsyncSession):
    """13 & 14. PAUSED -> CANCELLED works, and CANCELLED campaign cannot be resumed or scheduled."""
    token = await register_and_login(async_client, "cancel2@example.com")
    comp_id = await create_company_helper(async_client, token, "Cancel Org 2")
    camp_id, _ = await setup_test_campaign(async_client, db_session, token, comp_id)

    camp = (await db_session.execute(select(Campaign).where(Campaign.id == camp_id))).scalar_one()
    camp.status = CampaignStatus.PAUSED.value
    await db_session.commit()

    # PAUSED -> CANCELLED via API
    cancel_resp = await async_client.post(
        f"/api/v1/companies/{comp_id}/campaigns/{camp_id}/cancel",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == CampaignStatus.CANCELLED.value

    # CANCELLED cannot be resumed
    resume_resp = await async_client.post(
        f"/api/v1/companies/{comp_id}/campaigns/{camp_id}/resume",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resume_resp.status_code == 400

    # CANCELLED cannot be scheduled
    sched_resp = await async_client.post(
        f"/api/v1/companies/{comp_id}/campaigns/{camp_id}/schedule",
        headers={"Authorization": f"Bearer {token}"},
        json={"scheduled_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()},
    )
    assert sched_resp.status_code == 400


@pytest.mark.asyncio
async def test_11_retry_worker_does_not_send_when_paused_or_cancelled(async_client: AsyncClient, db_session: AsyncSession):
    """15 & 16. Retry worker does not send while campaign is PAUSED or CANCELLED."""
    token = await register_and_login(async_client, "retry_ctl@example.com")
    comp_id = await create_company_helper(async_client, token, "Retry Org")
    camp_id, _ = await setup_test_campaign(async_client, db_session, token, comp_id)
    r_id = await add_recipient(async_client, token, comp_id, camp_id, "retry@test.com")

    # Create FAILED delivery
    deliv = CampaignDelivery(
        campaign_id=camp_id,
        recipient_id=r_id,
        status=CampaignDeliveryStatus.FAILED.value,
        attempt_count=1,
    )
    db_session.add(deliv)

    camp = (await db_session.execute(select(Campaign).where(Campaign.id == camp_id))).scalar_one()
    camp.status = CampaignStatus.PAUSED.value
    await db_session.commit()
    await db_session.refresh(deliv)

    mock_email_service = MagicMock()

    # 1. When PAUSED -> retry must skip without calling send_email
    res_paused = await CampaignDeliveryService.retry_delivery(
        delivery_id=deliv.id,
        company_id=comp_id,
        db_factory=TestAsyncSessionLocal,
        email_service=mock_email_service,
    )
    assert res_paused["status"] == "SKIPPED"
    assert "PAUSED" in res_paused["reason"]
    mock_email_service.send_email.assert_not_called()

    # 2. When CANCELLED -> retry must skip without calling send_email
    camp.status = CampaignStatus.CANCELLED.value
    await db_session.commit()

    res_cancelled = await CampaignDeliveryService.retry_delivery(
        delivery_id=deliv.id,
        company_id=comp_id,
        db_factory=TestAsyncSessionLocal,
        email_service=mock_email_service,
    )
    assert res_cancelled["status"] == "SKIPPED"
    assert "CANCELLED" in res_cancelled["reason"]
    mock_email_service.send_email.assert_not_called()


@pytest.mark.asyncio
async def test_12_cross_company_control_rejected(async_client: AsyncClient, db_session: AsyncSession):
    """19. Cross-company scheduling/control is rejected."""
    token1 = await register_and_login(async_client, "org1_owner@example.com")
    token2 = await register_and_login(async_client, "org2_owner@example.com")
    comp1 = await create_company_helper(async_client, token1, "Org 1")
    comp2 = await create_company_helper(async_client, token2, "Org 2")

    camp1_id, _ = await setup_test_campaign(async_client, db_session, token1, comp1)

    # Org 2 attempts to pause Org 1's campaign -> 404 (anti-enumeration)
    pause_resp = await async_client.post(
        f"/api/v1/companies/{comp2}/campaigns/{camp1_id}/pause",
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert pause_resp.status_code == 404

    # Org 2 attempts to cancel Org 1's campaign -> 404
    cancel_resp = await async_client.post(
        f"/api/v1/companies/{comp2}/campaigns/{camp1_id}/cancel",
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert cancel_resp.status_code == 404

    # Org 2 attempts to schedule Org 1's campaign -> 404
    sched_resp = await async_client.post(
        f"/api/v1/companies/{comp2}/campaigns/{camp1_id}/schedule",
        headers={"Authorization": f"Bearer {token2}"},
        json={"scheduled_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()},
    )
    assert sched_resp.status_code == 404


@pytest.mark.asyncio
async def test_13_timezone_aware_scheduled_at_behavior(async_client: AsyncClient, db_session: AsyncSession):
    """20. Timezone-aware scheduled_at behavior is correct."""
    token = await register_and_login(async_client, "tz_test@example.com")
    comp_id = await create_company_helper(async_client, token, "TZ Org")
    camp_id, _ = await setup_test_campaign(async_client, db_session, token, comp_id)

    now_utc = datetime.now(timezone.utc)
    future_utc = now_utc + timedelta(hours=3)

    # Schedule via API with timezone-aware ISO string
    resp = await async_client.post(
        f"/api/v1/companies/{comp_id}/campaigns/{camp_id}/schedule",
        headers={"Authorization": f"Bearer {token}"},
        json={"scheduled_at": future_utc.isoformat()},
    )
    assert resp.status_code == 200

    camp = (await db_session.execute(select(Campaign).where(Campaign.id == camp_id))).scalar_one()
    assert camp.scheduled_at is not None
    # Ensure compare with now_utc does not raise TypeError
    sched = camp.scheduled_at
    if sched.tzinfo is None:
        sched = sched.replace(tzinfo=timezone.utc)
    assert sched > now_utc


@pytest.mark.asyncio
async def test_14_resume_with_actual_active_campaign_worker_does_not_duplicate_dispatch(
    async_client: AsyncClient, db_session: AsyncSession
):
    """Resume with an actual active C8 campaign worker does NOT create unnecessary duplicate execution."""
    token = await register_and_login(async_client, "active_c8@example.com")
    comp_id = await create_company_helper(async_client, token, "Active C8 Org")
    camp_id, _ = await setup_test_campaign(async_client, db_session, token, comp_id)

    r1_id = await add_recipient(async_client, token, comp_id, camp_id, "active_c8_r1@test.com")
    r2_id = await add_recipient(async_client, token, comp_id, camp_id, "active_c8_r2@test.com")

    # Campaign is PAUSED
    camp = (await db_session.execute(select(Campaign).where(Campaign.id == camp_id))).scalar_one()
    camp.status = CampaignStatus.PAUSED.value

    # Recipient 1 has an active C8 campaign worker mid-send (status=SENDING, attempt_count=1, recipient=PENDING)
    deliv1 = CampaignDelivery(
        campaign_id=camp_id,
        recipient_id=r1_id,
        status=CampaignDeliveryStatus.SENDING.value,
        attempt_count=1,
        last_attempt_at=datetime.now(timezone.utc),
    )
    db_session.add(deliv1)
    await db_session.commit()

    # When resumed, campaign transitions to RUNNING, but does NOT schedule duplicate dispatch task
    with patch("app.workers.campaign_tasks.dispatch_campaign_task.delay") as mock_delay:
        resp = await async_client.post(
            f"/api/v1/companies/{comp_id}/campaigns/{camp_id}/resume",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == CampaignStatus.RUNNING.value
        mock_delay.assert_not_called()


@pytest.mark.asyncio
async def test_15_resume_while_only_retry_worker_sending_ensures_campaign_execution(
    async_client: AsyncClient, db_session: AsyncSession
):
    """Resume while ONLY a C9 retry delivery is SENDING still schedules campaign execution for remaining pending recipients."""
    token = await register_and_login(async_client, "retry_sending@example.com")
    comp_id = await create_company_helper(async_client, token, "Retry Sending Org")
    camp_id, _ = await setup_test_campaign(async_client, db_session, token, comp_id)

    r1_id = await add_recipient(async_client, token, comp_id, camp_id, "failed_retry_r1@test.com")
    r2_id = await add_recipient(async_client, token, comp_id, camp_id, "pending_r2@test.com")

    # Campaign is PAUSED
    camp = (await db_session.execute(select(Campaign).where(Campaign.id == camp_id))).scalar_one()
    camp.status = CampaignStatus.PAUSED.value

    # Recipient 1 is FAILED with a retry delivery currently SENDING (attempt_count=2)
    rec1 = (await db_session.execute(select(CampaignRecipient).where(CampaignRecipient.id == r1_id))).scalar_one()
    rec1.status = CampaignRecipientStatus.FAILED.value

    deliv1 = CampaignDelivery(
        campaign_id=camp_id,
        recipient_id=r1_id,
        status=CampaignDeliveryStatus.SENDING.value,
        attempt_count=2,
        last_attempt_at=datetime.now(timezone.utc),
    )
    db_session.add(deliv1)
    await db_session.commit()

    # When resumed, since ONLY a C9 retry worker is SENDING, resume MUST enqueue campaign execution
    with patch("app.workers.campaign_tasks.dispatch_campaign_task.delay") as mock_delay:
        resp = await async_client.post(
            f"/api/v1/companies/{comp_id}/campaigns/{camp_id}/resume",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == CampaignStatus.RUNNING.value
        mock_delay.assert_called_once_with(campaign_id=camp_id, company_id=comp_id)


@pytest.mark.asyncio
async def test_16_campaign_execution_processes_pending_recipients_after_retry_finishes(
    async_client: AsyncClient, db_session: AsyncSession
):
    """After retry worker finishes, campaign execution processes remaining pending recipients and leaves FAILED to retry."""
    token = await register_and_login(async_client, "post_retry@example.com")
    comp_id = await create_company_helper(async_client, token, "Post Retry Org")
    camp_id, _ = await setup_test_campaign(async_client, db_session, token, comp_id)

    r1_id = await add_recipient(async_client, token, comp_id, camp_id, "r1_retry@test.com")
    r2_id = await add_recipient(async_client, token, comp_id, camp_id, "r2_pending@test.com")

    camp = (await db_session.execute(select(Campaign).where(Campaign.id == camp_id))).scalar_one()
    camp.status = CampaignStatus.RUNNING.value

    # Recipient 1 had failed initially, retry worker ran and completed delivery to SENT
    rec1 = (await db_session.execute(select(CampaignRecipient).where(CampaignRecipient.id == r1_id))).scalar_one()
    rec1.status = CampaignRecipientStatus.FAILED.value

    deliv1 = CampaignDelivery(
        campaign_id=camp_id,
        recipient_id=r1_id,
        status=CampaignDeliveryStatus.SENT.value,
        attempt_count=2,
        sent_at=datetime.now(timezone.utc),
    )
    db_session.add(deliv1)
    await db_session.commit()

    send_call_count = 0

    async def fake_transport_send(request):
        nonlocal send_call_count
        send_call_count += 1
        return EmailTransportResult(success=True, message_id=f"<msg-post-retry-{send_call_count}@test.com>")

    with patch("app.services.transport.smtp.SMTPTransport.send", side_effect=fake_transport_send):
        result = await CampaignDeliveryService.execute_campaign(
            campaign_id=camp_id,
            company_id=comp_id,
            db_factory=TestAsyncSessionLocal,
        )

    # Only recipient 2 was processed; recipient 1 was skipped
    assert result["sent_count"] == 1
    assert send_call_count == 1
    assert result["status"] == CampaignStatus.COMPLETED.value

    rec2 = (await db_session.execute(select(CampaignRecipient).where(CampaignRecipient.id == r2_id))).scalar_one()
    assert rec2.status == CampaignRecipientStatus.SENT.value


@pytest.mark.asyncio
async def test_17_resumed_campaign_skips_sent_and_bounced_and_failed_recipients(
    async_client: AsyncClient, db_session: AsyncSession
):
    """Already SENT and BOUNCED deliveries remain skipped; FAILED deliveries remain under C9 retry handling."""
    token = await register_and_login(async_client, "skip_types@example.com")
    comp_id = await create_company_helper(async_client, token, "Skip Types Org")
    camp_id, _ = await setup_test_campaign(async_client, db_session, token, comp_id)

    r1_id = await add_recipient(async_client, token, comp_id, camp_id, "sent_recip@test.com")
    r2_id = await add_recipient(async_client, token, comp_id, camp_id, "bounced_recip@test.com")
    r3_id = await add_recipient(async_client, token, comp_id, camp_id, "failed_recip@test.com")
    r4_id = await add_recipient(async_client, token, comp_id, camp_id, "pending_recip@test.com")

    # Set up recipients and deliveries
    rec1 = (await db_session.execute(select(CampaignRecipient).where(CampaignRecipient.id == r1_id))).scalar_one()
    rec1.status = CampaignRecipientStatus.SENT.value
    deliv1 = CampaignDelivery(
        campaign_id=camp_id,
        recipient_id=r1_id,
        status=CampaignDeliveryStatus.SENT.value,
        attempt_count=1,
        sent_at=datetime.now(timezone.utc),
    )

    rec2 = (await db_session.execute(select(CampaignRecipient).where(CampaignRecipient.id == r2_id))).scalar_one()
    rec2.status = CampaignRecipientStatus.FAILED.value
    deliv2 = CampaignDelivery(
        campaign_id=camp_id,
        recipient_id=r2_id,
        status=CampaignDeliveryStatus.BOUNCED.value,
        attempt_count=1,
    )

    rec3 = (await db_session.execute(select(CampaignRecipient).where(CampaignRecipient.id == r3_id))).scalar_one()
    rec3.status = CampaignRecipientStatus.FAILED.value
    deliv3 = CampaignDelivery(
        campaign_id=camp_id,
        recipient_id=r3_id,
        status=CampaignDeliveryStatus.FAILED.value,
        attempt_count=1,
    )

    camp = (await db_session.execute(select(Campaign).where(Campaign.id == camp_id))).scalar_one()
    camp.status = CampaignStatus.RUNNING.value

    db_session.add_all([deliv1, deliv2, deliv3])
    await db_session.commit()

    send_call_count = 0

    async def fake_transport_send(request):
        nonlocal send_call_count
        send_call_count += 1
        return EmailTransportResult(success=True, message_id=f"<msg-skip-{send_call_count}@test.com>")

    with patch("app.services.transport.smtp.SMTPTransport.send", side_effect=fake_transport_send):
        result = await CampaignDeliveryService.execute_campaign(
            campaign_id=camp_id,
            company_id=comp_id,
            db_factory=TestAsyncSessionLocal,
        )

    # Only recipient 4 was processed and sent; 1, 2, 3 were completely skipped
    assert result["sent_count"] == 1
    assert send_call_count == 1
    assert result["status"] == CampaignStatus.COMPLETED.value


@pytest.mark.asyncio
async def test_18_in_flight_smtp_operation_pauses_completes_halts_and_resumes(
    async_client: AsyncClient, db_session: AsyncSession
):
    """In-flight SMTP operation:
    - recipient A is already sending
    - campaign is paused
    - A completes
    - no additional recipient begins
    - campaign remains PAUSED
    - after resume, pending recipients continue.
    """
    token = await register_and_login(async_client, "inflight_pause@example.com")
    comp_id = await create_company_helper(async_client, token, "Inflight Pause Org")
    camp_id, _ = await setup_test_campaign(async_client, db_session, token, comp_id)

    r_a_id = await add_recipient(async_client, token, comp_id, camp_id, "recip_a@inflight.com")
    r_b_id = await add_recipient(async_client, token, comp_id, camp_id, "recip_b@inflight.com")

    camp = (await db_session.execute(select(Campaign).where(Campaign.id == camp_id))).scalar_one()
    camp.status = CampaignStatus.RUNNING.value
    await db_session.commit()

    sent_messages = []

    # 1. During recipient A's send, simulate campaign pause
    async def fake_transport_send_first_worker(request):
        recip = request.envelope_recipients[0] if getattr(request, "envelope_recipients", None) else ""
        sent_messages.append(recip)
        # Pause campaign in DB while recipient A is sending
        async with TestAsyncSessionLocal() as pause_db:
            c = (await pause_db.execute(select(Campaign).where(Campaign.id == camp_id))).scalar_one()
            c.status = CampaignStatus.PAUSED.value
            await pause_db.commit()
        return EmailTransportResult(success=True, message_id=f"<msg-inflight-{len(sent_messages)}@test.com>")

    with patch("app.services.transport.smtp.SMTPTransport.send", side_effect=fake_transport_send_first_worker):
        result1 = await CampaignDeliveryService.execute_campaign(
            campaign_id=camp_id,
            company_id=comp_id,
            db_factory=TestAsyncSessionLocal,
        )

    # Recipient A completed, no additional recipient began
    assert result1["status"] == CampaignStatus.PAUSED.value
    assert result1["sent_count"] == 1
    assert sent_messages == ["recip_a@inflight.com"]

    # In DB: campaign remains PAUSED; recipient A is SENT; recipient B remains PENDING
    await db_session.refresh(camp)
    assert camp.status == CampaignStatus.PAUSED.value

    rec_a = (await db_session.execute(select(CampaignRecipient).where(CampaignRecipient.id == r_a_id))).scalar_one()
    rec_b = (await db_session.execute(select(CampaignRecipient).where(CampaignRecipient.id == r_b_id))).scalar_one()
    assert rec_a.status == CampaignRecipientStatus.SENT.value
    assert rec_b.status == CampaignRecipientStatus.PENDING.value

    # 2. Resume campaign via API
    with patch("app.workers.campaign_tasks.dispatch_campaign_task.delay") as mock_delay:
        resp = await async_client.post(
            f"/api/v1/companies/{comp_id}/campaigns/{camp_id}/resume",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == CampaignStatus.RUNNING.value
        # Since recipient A is already SENT (no delivery is SENDING), resume schedules execution task
        mock_delay.assert_called_once_with(campaign_id=camp_id, company_id=comp_id)

    # 3. New campaign worker runs and continues with pending recipient B
    async def fake_transport_send_resumed_worker(request):
        recip = request.envelope_recipients[0] if getattr(request, "envelope_recipients", None) else ""
        sent_messages.append(recip)
        return EmailTransportResult(success=True, message_id=f"<msg-inflight-{len(sent_messages)}@test.com>")

    with patch("app.services.transport.smtp.SMTPTransport.send", side_effect=fake_transport_send_resumed_worker):
        result2 = await CampaignDeliveryService.execute_campaign(
            campaign_id=camp_id,
            company_id=comp_id,
            db_factory=TestAsyncSessionLocal,
        )

    assert result2["sent_count"] == 1
    assert result2["status"] == CampaignStatus.COMPLETED.value
    assert sent_messages == ["recip_a@inflight.com", "recip_b@inflight.com"]

    await db_session.refresh(camp)
    assert camp.status == CampaignStatus.COMPLETED.value

    await db_session.refresh(rec_b)
    assert rec_b.status == CampaignRecipientStatus.SENT.value


# ==============================================================================
# C11.1 Rescheduling Tests (Allow Rescheduling an Already Scheduled Campaign)
# ==============================================================================


@pytest.mark.asyncio
async def test_reschedule_scheduled_campaign_success_and_persistence(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Test successful rescheduling of an already SCHEDULED campaign to a new future time."""
    token = await register_and_login(async_client, "resched_success@test.com")
    comp_id = await create_company_helper(async_client, token, "Resched Success Co")
    camp_id, _ = await setup_test_campaign(async_client, db_session, token, comp_id)
    await add_recipient(async_client, token, comp_id, camp_id, "recip_resched@test.com")

    # 1. Initial schedule for +2 days
    initial_time = datetime.now(timezone.utc) + timedelta(days=2)
    resp1 = await async_client.post(
        f"/api/v1/companies/{comp_id}/campaigns/{camp_id}/schedule",
        headers={"Authorization": f"Bearer {token}"},
        json={"scheduled_at": initial_time.isoformat()},
    )
    assert resp1.status_code == 200
    assert resp1.json()["status"] == CampaignStatus.SCHEDULED.value

    # 2. Reschedule to +5 days
    new_time = datetime.now(timezone.utc) + timedelta(days=5)
    resp2 = await async_client.post(
        f"/api/v1/companies/{comp_id}/campaigns/{camp_id}/schedule",
        headers={"Authorization": f"Bearer {token}"},
        json={"scheduled_at": new_time.isoformat()},
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["status"] == CampaignStatus.SCHEDULED.value
    assert data2["scheduled_at"] is not None

    # 3. Verify persistence in database
    camp = (await db_session.execute(select(Campaign).where(Campaign.id == camp_id))).scalar_one()
    assert camp.status == CampaignStatus.SCHEDULED.value
    # Ensure saved scheduled_at is updated to approximately new_time
    assert camp.scheduled_at is not None
    assert camp.scheduled_at.year == new_time.year
    assert camp.scheduled_at.month == new_time.month
    assert camp.scheduled_at.day == new_time.day


@pytest.mark.asyncio
async def test_reschedule_scheduled_campaign_invalid_and_past_time_rejection(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Test that rescheduling a SCHEDULED campaign rejects past dates and missing scheduled_at."""
    token = await register_and_login(async_client, "resched_val@test.com")
    comp_id = await create_company_helper(async_client, token, "Resched Val Co")
    camp_id, _ = await setup_test_campaign(async_client, db_session, token, comp_id)

    # Initial schedule
    initial_time = datetime.now(timezone.utc) + timedelta(days=1)
    await async_client.post(
        f"/api/v1/companies/{comp_id}/campaigns/{camp_id}/schedule",
        headers={"Authorization": f"Bearer {token}"},
        json={"scheduled_at": initial_time.isoformat()},
    )

    # 1. Reschedule to past time -> 400
    past_time = datetime.now(timezone.utc) - timedelta(hours=2)
    resp_past = await async_client.post(
        f"/api/v1/companies/{comp_id}/campaigns/{camp_id}/schedule",
        headers={"Authorization": f"Bearer {token}"},
        json={"scheduled_at": past_time.isoformat()},
    )
    assert resp_past.status_code == 400
    assert "must be in the future" in resp_past.json()["detail"].lower()

    # 2. Reschedule with empty body (missing scheduled_at) on SCHEDULED campaign -> 400
    resp_empty = await async_client.post(
        f"/api/v1/companies/{comp_id}/campaigns/{camp_id}/schedule",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert resp_empty.status_code == 400
    assert "scheduled_at must be provided" in resp_empty.json()["detail"].lower()


@pytest.mark.asyncio
async def test_reschedule_ineligible_campaign_statuses_rejected(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Test that campaigns in ineligible statuses (RUNNING, PAUSED, QUEUED, CANCELLED) reject rescheduling."""
    token = await register_and_login(async_client, "resched_inelig@test.com")
    comp_id = await create_company_helper(async_client, token, "Resched Inelig Co")
    camp_id, _ = await setup_test_campaign(async_client, db_session, token, comp_id)

    camp = (await db_session.execute(select(Campaign).where(Campaign.id == camp_id))).scalar_one()

    future_time = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    for ineligible_status in [
        CampaignStatus.RUNNING.value,
        CampaignStatus.PAUSED.value,
        CampaignStatus.QUEUED.value,
        CampaignStatus.CANCELLED.value,
        CampaignStatus.COMPLETED.value,
        CampaignStatus.FAILED.value,
    ]:
        camp.status = ineligible_status
        await db_session.commit()

        resp = await async_client.post(
            f"/api/v1/companies/{comp_id}/campaigns/{camp_id}/schedule",
            headers={"Authorization": f"Bearer {token}"},
            json={"scheduled_at": future_time},
        )
        assert resp.status_code == 400
        assert "only draft or scheduled" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_reschedule_and_scheduler_race_prevents_duplicate_dispatch(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Test that rescheduling prevents duplicate/early dispatch and protects against scheduler races."""
    token = await register_and_login(async_client, "resched_race@test.com")
    comp_id = await create_company_helper(async_client, token, "Resched Race Co")
    camp_id, _ = await setup_test_campaign(async_client, db_session, token, comp_id)
    await add_recipient(async_client, token, comp_id, camp_id, "recip_race@test.com")

    # 1. Campaign was scheduled for now (due)
    due_time = datetime.now(timezone.utc) - timedelta(minutes=1)
    camp = (await db_session.execute(select(Campaign).where(Campaign.id == camp_id))).scalar_one()
    camp.status = CampaignStatus.SCHEDULED.value
    camp.scheduled_at = due_time
    await db_session.commit()

    # 2. User reschedules to future (+2 hours)
    future_time = datetime.now(timezone.utc) + timedelta(hours=2)
    resp = await async_client.post(
        f"/api/v1/companies/{comp_id}/campaigns/{camp_id}/schedule",
        headers={"Authorization": f"Bearer {token}"},
        json={"scheduled_at": future_time.isoformat()},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == CampaignStatus.SCHEDULED.value

    # 3. Scheduler ticks immediately: since scheduled_at is now in future, it MUST NOT dispatch
    with patch("app.workers.campaign_tasks.dispatch_campaign_task.delay") as mock_delay:
        outcomes = await CampaignSchedulingService.dispatch_due_campaigns()
        matched = [o for o in outcomes if o.get("campaign_id") == camp_id]
        assert len(matched) == 0
        mock_delay.assert_not_called()

    # 4. If campaign was already transitioned to QUEUED by the scheduler, rescheduling is rejected
    await db_session.refresh(camp)
    camp.status = CampaignStatus.QUEUED.value
    await db_session.commit()

    resp_after_queued = await async_client.post(
        f"/api/v1/companies/{comp_id}/campaigns/{camp_id}/schedule",
        headers={"Authorization": f"Bearer {token}"},
        json={"scheduled_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()},
    )
    assert resp_after_queued.status_code == 400
    assert "only draft or scheduled" in resp_after_queued.json()["detail"].lower()


