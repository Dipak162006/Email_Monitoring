"""Tests verifying campaign lifecycle completion logic with automated follow-ups.

Guarantees:
1. Initial email delivered while follow-ups remain pending: campaign must not be marked COMPLETED.
2. All eligible follow-ups finished: campaign transitions to COMPLETED.
3. Cancelled campaigns must not be incorrectly completed.
"""
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
import pytest
from httpx import AsyncClient
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.email_accounts.models import EmailAccount
from app.modules.campaigns.models import (
    Campaign,
    CampaignDelivery,
    CampaignDeliveryStatus,
    CampaignRecipient,
    CampaignRecipientStatus,
    CampaignRecipientStopReason,
    CampaignStep,
    CampaignStatus,
)
from app.modules.campaigns.delivery_service import CampaignDeliveryService
from app.modules.campaigns.service import CampaignService
from app.workers import tasks
from tests.conftest import TestAsyncSessionLocal


@pytest.fixture(autouse=True)
def configure_worker_db():
    """Ensure delivery engine worker tasks use the test database."""
    orig_session_maker = tasks.WorkerAsyncSessionLocal
    tasks.WorkerAsyncSessionLocal = TestAsyncSessionLocal
    yield
    tasks.WorkerAsyncSessionLocal = orig_session_maker


async def register_and_login(async_client: AsyncClient, email: str, full_name: str = "Test Owner") -> str:
    pwd = "ValidPass123!@#"
    reg_resp = await async_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": pwd, "full_name": full_name},
    )
    assert reg_resp.status_code == 201
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


async def create_verified_email_account(db: AsyncSession, company_id: int, email: str) -> EmailAccount:
    account = EmailAccount(
        company_id=company_id,
        email_address=email,
        name="Outreach Sender",
        provider="CUSTOM",
        is_active=True,
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_username=email,
        smtp_password_encrypted="enc_pass",
        smtp_security="STARTTLS",
    )
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return account


@pytest.mark.asyncio
async def test_initial_email_delivered_while_followups_remain_pending_campaign_not_completed(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Initial email delivered while follow-up steps remain pending: campaign must remain RUNNING, not COMPLETED."""
    token = await register_and_login(async_client, "owner_pending_fu@test.com", "FU Owner")
    comp_id = await create_company_helper(async_client, token, "Pending FU Co")
    account = await create_verified_email_account(db_session, comp_id, "sender_fu@test.com")

    # Create campaign with Step 1 and Step 2 (delay 48h)
    create_resp = await async_client.post(
        f"/api/v1/companies/{comp_id}/campaigns",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Multi-Step Campaign",
            "email_account_id": account.id,
            "subject": "Introductory Pitch",
            "body_text": "Step 1 content",
            "followup_steps": [
                {
                    "step_number": 2,
                    "delay_hours": 48,
                    "subject": "Follow-Up #1",
                    "body_text": "Did you receive my previous email?",
                }
            ],
        },
    )
    assert create_resp.status_code == 201
    camp_id = create_resp.json()["id"]

    recip_resp = await async_client.post(
        f"/api/v1/companies/{comp_id}/campaigns/{camp_id}/recipients",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "prospect@client.com", "first_name": "Prospect"},
    )
    assert recip_resp.status_code == 201
    recip_id = recip_resp.json()["id"]

    # Queue campaign for execution
    camp_res = await db_session.execute(select(Campaign).where(Campaign.id == camp_id))
    camp = camp_res.scalar_one()
    camp.status = CampaignStatus.QUEUED.value
    await db_session.commit()

    # Execute initial email (Step 1)
    with patch("app.services.smtp.client.SMTPClient.send_email_sync"):
        result = await CampaignDeliveryService.execute_campaign(
            campaign_id=camp_id,
            company_id=comp_id,
            db_factory=TestAsyncSessionLocal,
        )
    assert result["sent_count"] == 1

    # Refresh campaign and verify state
    await db_session.refresh(camp)
    # CRITICAL: Campaign must remain in RUNNING status, NOT prematurely marked COMPLETED
    assert camp.status == CampaignStatus.RUNNING.value
    assert camp.completed_at is None

    # Verify recipient has Step 2 scheduled
    recip_res = await db_session.execute(select(CampaignRecipient).where(CampaignRecipient.id == recip_id))
    recip = recip_res.scalar_one()
    assert recip.status == CampaignRecipientStatus.SENT.value
    assert recip.current_step_number == 1
    assert recip.next_step_due_at is not None


@pytest.mark.asyncio
async def test_all_eligible_followups_finished_campaign_becomes_completed(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """When all eligible follow-ups have finished dispatching, the campaign must transition to COMPLETED."""
    token = await register_and_login(async_client, "owner_finish_fu@test.com", "Finish Owner")
    comp_id = await create_company_helper(async_client, token, "Finish FU Co")
    account = await create_verified_email_account(db_session, comp_id, "sender_finish@test.com")

    # Create campaign with Step 1 and Step 2 (delay 48h)
    create_resp = await async_client.post(
        f"/api/v1/companies/{comp_id}/campaigns",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Two-Step Sequence",
            "email_account_id": account.id,
            "subject": "Initial Email",
            "body_text": "Initial body",
            "followup_steps": [
                {
                    "step_number": 2,
                    "delay_hours": 48,
                    "subject": "Final Follow-up",
                    "body_text": "Follow-up body",
                }
            ],
        },
    )
    assert create_resp.status_code == 201
    camp_id = create_resp.json()["id"]

    recip_resp = await async_client.post(
        f"/api/v1/companies/{comp_id}/campaigns/{camp_id}/recipients",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "lead@company.com", "first_name": "Lead"},
    )
    assert recip_resp.status_code == 201
    recip_id = recip_resp.json()["id"]

    camp_res = await db_session.execute(select(Campaign).where(Campaign.id == camp_id))
    camp = camp_res.scalar_one()
    camp.status = CampaignStatus.QUEUED.value
    await db_session.commit()

    # 1. Execute initial email (Step 1)
    with patch("app.services.smtp.client.SMTPClient.send_email_sync"):
        await CampaignDeliveryService.execute_campaign(
            campaign_id=camp_id,
            company_id=comp_id,
            db_factory=TestAsyncSessionLocal,
        )

    await db_session.refresh(camp)
    assert camp.status == CampaignStatus.RUNNING.value

    # Obtain delivery time
    deliv_res = await db_session.execute(
        select(CampaignDelivery).where(
            CampaignDelivery.campaign_id == camp_id,
            CampaignDelivery.recipient_id == recip_id,
        )
    )
    step1_deliv = deliv_res.scalar_one()

    # 2. Advance time past 48h and execute Step 2
    with patch("app.services.smtp.client.SMTPClient.send_email_sync"):
        due_res = await CampaignDeliveryService.process_due_followup_steps(
            db_factory=TestAsyncSessionLocal,
            now_utc=step1_deliv.sent_at + timedelta(hours=50),
        )
    assert len(due_res) == 1
    assert due_res[0]["step_number"] == 2
    assert due_res[0]["status"] == "SENT"

    # 3. Verify campaign transitions to COMPLETED now that all follow-ups have finished
    await db_session.refresh(camp)
    assert camp.status == CampaignStatus.COMPLETED.value
    assert camp.completed_at is not None

    # Verify recipient is COMPLETED with no remaining scheduled step
    recip_res = await db_session.execute(select(CampaignRecipient).where(CampaignRecipient.id == recip_id))
    recip = recip_res.scalar_one()
    assert recip.status == CampaignRecipientStatus.COMPLETED.value
    assert recip.next_step_due_at is None


@pytest.mark.asyncio
async def test_cancelled_campaign_must_not_be_incorrectly_completed(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Cancelled campaigns must not be processed for follow-ups or marked COMPLETED."""
    token = await register_and_login(async_client, "owner_cancelled_fu@test.com", "Cancel Owner")
    comp_id = await create_company_helper(async_client, token, "Cancel FU Co")
    account = await create_verified_email_account(db_session, comp_id, "sender_cancel@test.com")

    # Create campaign with follow-up
    create_resp = await async_client.post(
        f"/api/v1/companies/{comp_id}/campaigns",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Cancel Test Campaign",
            "email_account_id": account.id,
            "subject": "Initial Pitch",
            "body_text": "Step 1 content",
            "followup_steps": [
                {
                    "step_number": 2,
                    "delay_hours": 24,
                    "subject": "Step 2 Follow-up",
                    "body_text": "Step 2 content",
                }
            ],
        },
    )
    assert create_resp.status_code == 201
    camp_id = create_resp.json()["id"]

    recip_resp = await async_client.post(
        f"/api/v1/companies/{comp_id}/campaigns/{camp_id}/recipients",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "target@client.com"},
    )
    assert recip_resp.status_code == 201
    recip_id = recip_resp.json()["id"]

    camp_res = await db_session.execute(select(Campaign).where(Campaign.id == camp_id))
    camp = camp_res.scalar_one()
    camp.status = CampaignStatus.QUEUED.value
    await db_session.commit()

    # Step 1 executed
    with patch("app.services.smtp.client.SMTPClient.send_email_sync"):
        await CampaignDeliveryService.execute_campaign(
            campaign_id=camp_id,
            company_id=comp_id,
            db_factory=TestAsyncSessionLocal,
        )

    await db_session.refresh(camp)
    assert camp.status == CampaignStatus.RUNNING.value

    # Cancel the campaign while follow-up is pending
    cancelled_camp = await CampaignService.cancel_campaign(db_session, comp_id, camp_id)
    assert cancelled_camp.status == CampaignStatus.CANCELLED.value

    # Verify recipient's next_step_due_at was cleared and marked STOPPED
    recip_res = await db_session.execute(select(CampaignRecipient).where(CampaignRecipient.id == recip_id))
    recip = recip_res.scalar_one()
    assert recip.next_step_due_at is None
    assert recip.status == CampaignRecipientStatus.STOPPED.value
    assert recip.stopped_reason == CampaignRecipientStopReason.CAMPAIGN_CANCELLED.value

    # Running follow-ups must not process any emails for cancelled campaign
    with patch("app.services.smtp.client.SMTPClient.send_email_sync"):
        due_res = await CampaignDeliveryService.process_due_followup_steps(
            db_factory=TestAsyncSessionLocal,
            now_utc=datetime.now(timezone.utc) + timedelta(days=5),
        )
    assert len(due_res) == 0

    # Explicit completion check must not complete a cancelled campaign
    comp_status = await CampaignDeliveryService.check_and_finalize_campaign_completion(
        campaign_id=camp_id,
        db_factory=TestAsyncSessionLocal,
    )
    assert comp_status == CampaignStatus.CANCELLED.value

    await db_session.refresh(camp)
    assert camp.status == CampaignStatus.CANCELLED.value

    # State transition from CANCELLED to COMPLETED is forbidden
    with pytest.raises(HTTPException) as exc_info:
        await CampaignService.transition_state(
            db=db_session,
            company_id=comp_id,
            campaign_id=camp_id,
            target_status=CampaignStatus.COMPLETED,
        )
    assert exc_info.value.status_code == 400
