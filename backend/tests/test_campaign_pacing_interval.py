from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
from httpx import AsyncClient
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
from app.modules.campaigns.schemas import CampaignCreate, CampaignUpdate
from app.modules.campaigns.service import CampaignService
from app.workers import tasks
from tests.conftest import TestAsyncSessionLocal
from tests.test_campaign_delivery import (
    add_recipient_helper,
    create_company_helper,
    queue_campaign_helper,
    register_and_login,
    setup_delivery_campaign,
)


@pytest.fixture(autouse=True)
def configure_worker_db():
    """Ensure delivery engine worker tasks use the test database."""
    orig_session_maker = tasks.WorkerAsyncSessionLocal
    tasks.WorkerAsyncSessionLocal = TestAsyncSessionLocal
    yield
    tasks.WorkerAsyncSessionLocal = orig_session_maker



@pytest.mark.anyio
async def test_campaign_interval_default_and_custom_crud(async_client: AsyncClient, db_session: AsyncSession):
    """Verify that:
    - Default send_interval_seconds is 0 (backward compatible).
    - Custom send_interval_seconds can be set at creation.
    - Custom interval survives draft updates and partial updates preserve it.
    """
    token = await register_and_login(async_client, "interval_crud@test.com", "Interval User")
    company_id = await create_company_helper(async_client, token, "Interval Org")
    camp_id, acc_id = await setup_delivery_campaign(async_client, db_session, token, company_id)

    # 1. Verify default is 0
    get_res = await async_client.get(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_res.status_code == 200
    assert get_res.json()["send_interval_seconds"] == 0
    assert get_res.json()["next_send_at"] is None

    # 2. Update with custom 300s interval (5 minutes)
    patch_res = await async_client.patch(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"send_interval_seconds": 300},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["send_interval_seconds"] == 300

    # 2b. Verify detail GET endpoint explicitly returns the updated interval (C14.1 fix)
    get_res2 = await async_client.get(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_res2.status_code == 200
    assert get_res2.json()["send_interval_seconds"] == 300

    # 3. Partial update omitting send_interval_seconds preserves 300
    patch_res2 = await async_client.patch(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Renamed Interval Campaign"},
    )
    assert patch_res2.status_code == 200
    assert patch_res2.json()["name"] == "Renamed Interval Campaign"
    assert patch_res2.json()["send_interval_seconds"] == 300

    # 3b. Verify detail GET still preserves 300 after partial update of other fields
    get_res3 = await async_client.get(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_res3.status_code == 200
    assert get_res3.json()["name"] == "Renamed Interval Campaign"
    assert get_res3.json()["send_interval_seconds"] == 300

    # 4. Switching back to immediate (0s) updates and persists correctly
    patch_res3 = await async_client.patch(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"send_interval_seconds": 0},
    )
    assert patch_res3.status_code == 200
    assert patch_res3.json()["send_interval_seconds"] == 0

    get_res4 = await async_client.get(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_res4.status_code == 200
    assert get_res4.json()["send_interval_seconds"] == 0


@pytest.mark.anyio
async def test_campaign_interval_validation_rejects_invalid_values(async_client: AsyncClient, db_session: AsyncSession):
    """Verify that invalid interval values (negative, non-finite, > 86400) are rejected with 422."""
    token = await register_and_login(async_client, "interval_val@test.com", "Val User")
    company_id = await create_company_helper(async_client, token, "Val Org")
    camp_id, acc_id = await setup_delivery_campaign(async_client, db_session, token, company_id)

    # Negative value
    res_neg = await async_client.patch(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"send_interval_seconds": -10},
    )
    assert res_neg.status_code == 422

    # Exceeding 24 hours (86400s)
    res_large = await async_client.patch(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"send_interval_seconds": 90000},
    )
    assert res_large.status_code == 422

    # Boolean instead of integer
    res_bool = await async_client.patch(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"send_interval_seconds": True},
    )
    assert res_bool.status_code == 422


@pytest.mark.anyio
async def test_paced_delivery_enforces_interval_between_recipients(async_client: AsyncClient, db_session: AsyncSession):
    """Verify paced delivery mechanics:
    1. First recipient sends immediately and sets next_send_at = t0 + interval.
    2. Attempting to execute before interval has elapsed returns WAITING_INTERVAL without sending.
    3. When now_utc >= next_send_at, second recipient is sent and next_send_at updated.
    4. Worker does not sleep; tasks are scheduled asynchronously.
    """
    token = await register_and_login(async_client, "paced_exec@test.com", "Paced User")
    company_id = await create_company_helper(async_client, token, "Paced Org")
    camp_id, _ = await setup_delivery_campaign(async_client, db_session, token, company_id)

    # Set 60-second sending interval
    await async_client.patch(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"send_interval_seconds": 60},
    )

    r1_id = await add_recipient_helper(async_client, token, company_id, camp_id, "recip1@test.com", first_name="R1")
    r2_id = await add_recipient_helper(async_client, token, company_id, camp_id, "recip2@test.com", first_name="R2")
    await queue_campaign_helper(db_session, camp_id)

    t0 = datetime(2026, 10, 13, 10, 0, 0, tzinfo=timezone.utc)

    # First send at t0
    with patch("app.services.smtp.client.SMTPClient.send_email_sync"), \
         patch("app.workers.campaign_tasks.dispatch_campaign_task.apply_async") as mock_apply_async:
        res1 = await CampaignDeliveryService.execute_campaign(
            campaign_id=camp_id,
            company_id=company_id,
            now_utc=t0,
        )

        assert res1["status"] == "RUNNING"
        assert res1["sent_count"] == 1
        assert res1["remaining_pending"] == 1
        assert mock_apply_async.called

    # Verify recipient 1 is SENT and next_send_at is t0 + 60s
    async with TestAsyncSessionLocal() as db:
        camp = await db.scalar(select(Campaign).where(Campaign.id == camp_id))
        assert camp.next_send_at == t0 + timedelta(seconds=60)
        assert camp.status == CampaignStatus.RUNNING.value

        d1 = await db.scalar(select(CampaignDelivery).where(CampaignDelivery.recipient_id == r1_id))
        assert d1.status == CampaignDeliveryStatus.SENT.value

    # Attempt to execute at t0 + 30s (interval NOT elapsed)
    t_early = t0 + timedelta(seconds=30)
    with patch("app.services.smtp.client.SMTPClient.send_email_sync") as mock_smtp, \
         patch("app.workers.campaign_tasks.dispatch_campaign_task.apply_async") as mock_apply_async:
        res_early = await CampaignDeliveryService.execute_campaign(
            campaign_id=camp_id,
            company_id=company_id,
            now_utc=t_early,
        )

        assert res_early["status"] == "WAITING_INTERVAL"
        assert res_early["delay_seconds"] == 30
        assert not mock_smtp.called

    # Execute at t0 + 60s (interval has elapsed)
    t_due = t0 + timedelta(seconds=60)
    with patch("app.services.smtp.client.SMTPClient.send_email_sync") as mock_smtp:
        res2 = await CampaignDeliveryService.execute_campaign(
            campaign_id=camp_id,
            company_id=company_id,
            now_utc=t_due,
        )

        assert res2["status"] == CampaignStatus.COMPLETED.value
        assert res2["sent_count"] == 1

    # Verify recipient 2 is SENT and campaign is COMPLETED with next_send_at cleared
    async with TestAsyncSessionLocal() as db:
        camp = await db.scalar(select(Campaign).where(Campaign.id == camp_id))
        assert camp.status == CampaignStatus.COMPLETED.value
        assert camp.next_send_at is None

        d2 = await db.scalar(select(CampaignDelivery).where(CampaignDelivery.recipient_id == r2_id))
        assert d2.status == CampaignDeliveryStatus.SENT.value


@pytest.mark.anyio
async def test_paced_campaign_pause_resume_cancel(async_client: AsyncClient, db_session: AsyncSession):
    """Verify that Pause prevents paced sends and Resume recalculates eligibility."""
    token = await register_and_login(async_client, "paced_lifecycle@test.com", "Lifecycle User")
    company_id = await create_company_helper(async_client, token, "Lifecycle Org")
    camp_id, _ = await setup_delivery_campaign(async_client, db_session, token, company_id)

    await async_client.patch(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"send_interval_seconds": 120},
    )

    r1_id = await add_recipient_helper(async_client, token, company_id, camp_id, "lc1@test.com")
    r2_id = await add_recipient_helper(async_client, token, company_id, camp_id, "lc2@test.com")
    await queue_campaign_helper(db_session, camp_id)

    t0 = datetime(2026, 10, 13, 11, 0, 0, tzinfo=timezone.utc)

    # Send recipient 1
    with patch("app.services.smtp.client.SMTPClient.send_email_sync"), \
         patch("app.workers.campaign_tasks.dispatch_campaign_task.apply_async"):
        await CampaignDeliveryService.execute_campaign(
            campaign_id=camp_id,
            company_id=company_id,
            now_utc=t0,
        )

    # Pause campaign
    pause_res = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}/pause",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert pause_res.status_code == 200
    assert pause_res.json()["status"] == "PAUSED"

    # Execution during pause is skipped
    with patch("app.services.smtp.client.SMTPClient.send_email_sync") as mock_smtp:
        skip_res = await CampaignDeliveryService.execute_campaign(
            campaign_id=camp_id,
            company_id=company_id,
            now_utc=t0 + timedelta(seconds=130),
        )
        assert skip_res["status"] == "SKIPPED"
        assert not mock_smtp.called

    # Resume campaign
    resume_res = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}/resume",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resume_res.status_code == 200
    assert resume_res.json()["status"] == "RUNNING"


@pytest.mark.anyio
async def test_recover_due_paced_campaigns(async_client: AsyncClient, db_session: AsyncSession):
    """Verify that recover_due_paced_campaigns recovers due RUNNING campaigns whose task was lost."""
    token = await register_and_login(async_client, "paced_recovery@test.com", "Recovery User")
    company_id = await create_company_helper(async_client, token, "Recovery Org")
    camp_id, _ = await setup_delivery_campaign(async_client, db_session, token, company_id)

    await async_client.patch(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"send_interval_seconds": 60},
    )

    await add_recipient_helper(async_client, token, company_id, camp_id, "rec1@test.com")
    await queue_campaign_helper(db_session, camp_id)

    # Manually transition to RUNNING with next_send_at in past
    t_past = datetime(2026, 10, 13, 8, 0, 0, tzinfo=timezone.utc)
    async with TestAsyncSessionLocal() as db:
        camp = await db.scalar(select(Campaign).where(Campaign.id == camp_id))
        camp.status = CampaignStatus.RUNNING.value
        camp.next_send_at = t_past
        await db.commit()

    with patch("app.workers.campaign_tasks.dispatch_campaign_task.delay") as mock_delay:
        t_now = datetime(2026, 10, 13, 8, 5, 0, tzinfo=timezone.utc)
        recovered = await CampaignSchedulingService.recover_due_paced_campaigns(
            now_utc=t_now,
        )
        assert len(recovered) == 1
        assert recovered[0]["campaign_id"] == camp_id
        assert recovered[0]["status"] == "ENQUEUED"
        assert mock_delay.called
