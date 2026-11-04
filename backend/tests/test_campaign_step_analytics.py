from datetime import datetime, timezone, timedelta
from httpx import AsyncClient
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
from app.modules.campaigns.service import CampaignService
from app.modules.emails.models import EmailThread, Email, EmailDirection


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


async def create_company_helper(client: AsyncClient, token: str, name: str = "Analytics Co") -> int:
    resp = await client.post(
        "/api/v1/companies/",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": name},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def create_email_account_helper(
    client: AsyncClient,
    token: str,
    company_id: int,
    email_address: str = "analytics_sender@company.com",
) -> int:
    resp = await client.post(
        f"/api/v1/companies/{company_id}/email-accounts",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Sender",
            "email_address": email_address,
            "provider": "CUSTOM",
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "smtp_security": "STARTTLS",
            "smtp_username": email_address,
            "smtp_password": "SecretPassword123!",
            "imap_host": "imap.example.com",
            "imap_port": 993,
            "imap_security": "SSL",
            "imap_username": email_address,
            "imap_password": "SecretPassword123!",
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_step_analytics_empty_campaign(async_client: AsyncClient, db_session: AsyncSession):
    """Test step-level analytics on an empty campaign with no recipients or deliveries."""
    token = await register_and_login(async_client, "owner_empty_analytics@company.com")
    company_id = await create_company_helper(async_client, token, "Empty Co")
    account_id = await create_email_account_helper(async_client, token, company_id)

    # Create campaign
    resp = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Empty Draft",
            "email_account_id": account_id,
            "subject": "Initial Subject",
            "body_text": "Body",
        },
    )
    assert resp.status_code == 201
    campaign_id = resp.json()["id"]

    # Query analytics
    analytics_resp = await async_client.get(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/analytics",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert analytics_resp.status_code == 200
    data = analytics_resp.json()

    assert data["campaign_id"] == campaign_id
    assert data["total_recipients"] == 0
    assert data["total_steps"] == 1
    assert len(data["steps"]) == 1

    step1 = data["steps"][0]
    assert step1["step_number"] == 1
    assert step1["targeted_count"] == 0
    assert step1["sent_count"] == 0
    assert step1["bounced_count"] == 0
    assert step1["replied_count"] == 0
    assert step1["pending_count"] == 0
    assert step1["delivery_rate"] == 0.0
    assert step1["reply_rate"] == 0.0
    assert step1["bounce_rate"] == 0.0
    assert "Open and click tracking metrics are omitted" in data["omitted_metrics_notice"]


@pytest.mark.asyncio
async def test_step_analytics_multi_step_funnel_and_outcomes(async_client: AsyncClient, db_session: AsyncSession):
    """Test multi-step funnel with tag targeting, replies, bounces, skips, and pending progressions."""
    token = await register_and_login(async_client, "owner_funnel@company.com")
    company_id = await create_company_helper(async_client, token, "Funnel Co")
    account_id = await create_email_account_helper(async_client, token, company_id)

    # Create campaign with 2 steps (Step 1 and Step 2 with target_tags=['vip'])
    resp = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Multi-Step Campaign",
            "email_account_id": account_id,
            "subject": "Intro Email",
            "body_text": "Intro Body",
            "followup_steps": [
                {
                    "step_number": 2,
                    "delay_hours": 48,
                    "subject": "VIP Follow-Up",
                    "body_text": "Exclusive follow-up",
                    "target_tags": ["vip"],
                }
            ],
        },
    )
    assert resp.status_code == 201
    campaign_id = resp.json()["id"]

    # Retrieve steps
    steps = (
        await db_session.execute(
            select(CampaignStep)
            .where(CampaignStep.campaign_id == campaign_id)
            .order_by(CampaignStep.step_number.asc())
        )
    ).scalars().all()
    assert len(steps) == 2
    step1_id = steps[0].id
    step2_id = steps[1].id

    # Create thread for reply tracking
    thread1 = EmailThread(
        company_id=company_id,
        email_account_id=account_id,
        subject="Intro Email",
        has_reply=True,
        last_message_at=datetime.now(timezone.utc),
    )
    db_session.add(thread1)
    await db_session.flush()

    # Create Recipients:
    # r1: tags=['vip'], step 1 sent, step 2 sent, replied on step 2
    r1 = CampaignRecipient(
        campaign_id=campaign_id,
        email="r1_vip@test.com",
        custom_variables={"tags": ["vip"]},
        status=CampaignRecipientStatus.STOPPED.value,
        stopped_reason=CampaignRecipientStopReason.REPLIED.value,
        current_step_number=2,
        replied_at=datetime.now(timezone.utc),
    )
    # r2: tags=[], step 1 sent and bounced
    r2 = CampaignRecipient(
        campaign_id=campaign_id,
        email="r2_bounced@test.com",
        custom_variables={"tags": []},
        status=CampaignRecipientStatus.STOPPED.value,
        stopped_reason=CampaignRecipientStopReason.BOUNCED.value,
        current_step_number=1,
    )
    # r3: tags=['vip'], step 1 sent, step 2 pending
    r3 = CampaignRecipient(
        campaign_id=campaign_id,
        email="r3_vip_pending@test.com",
        custom_variables={"tags": ["vip"]},
        status=CampaignRecipientStatus.ACTIVE.value,
        current_step_number=1,
    )
    # r4: tags=['vip'], step 1 skipped
    r4 = CampaignRecipient(
        campaign_id=campaign_id,
        email="r4_skipped@test.com",
        custom_variables={"tags": ["vip"]},
        status=CampaignRecipientStatus.ACTIVE.value,
        current_step_number=1,
    )
    # r5: tags=['standard'], step 1 sent, replied on step 1 (thread reply)
    r5 = CampaignRecipient(
        campaign_id=campaign_id,
        email="r5_standard@test.com",
        custom_variables={"tags": ["standard"]},
        status=CampaignRecipientStatus.STOPPED.value,
        stopped_reason=CampaignRecipientStopReason.REPLIED.value,
        current_step_number=1,
        replied_at=datetime.now(timezone.utc),
    )

    db_session.add_all([r1, r2, r3, r4, r5])
    await db_session.flush()

    # Create Deliveries:
    # r1: Step 1 SENT, Step 2 SENT
    d1_step1 = CampaignDelivery(
        campaign_id=campaign_id,
        recipient_id=r1.id,
        step_id=step1_id,
        status=CampaignDeliveryStatus.SENT.value,
        sent_at=datetime.now(timezone.utc),
    )
    d1_step2 = CampaignDelivery(
        campaign_id=campaign_id,
        recipient_id=r1.id,
        step_id=step2_id,
        status=CampaignDeliveryStatus.SENT.value,
        sent_at=datetime.now(timezone.utc),
    )
    # r2: Step 1 BOUNCED
    d2_step1 = CampaignDelivery(
        campaign_id=campaign_id,
        recipient_id=r2.id,
        step_id=step1_id,
        status=CampaignDeliveryStatus.BOUNCED.value,
        bounced_at=datetime.now(timezone.utc),
    )
    # r3: Step 1 SENT, Step 2 PENDING
    d3_step1 = CampaignDelivery(
        campaign_id=campaign_id,
        recipient_id=r3.id,
        step_id=step1_id,
        status=CampaignDeliveryStatus.SENT.value,
        sent_at=datetime.now(timezone.utc),
    )
    d3_step2 = CampaignDelivery(
        campaign_id=campaign_id,
        recipient_id=r3.id,
        step_id=step2_id,
        status=CampaignDeliveryStatus.PENDING.value,
    )
    # r4: Step 1 SKIPPED
    d4_step1 = CampaignDelivery(
        campaign_id=campaign_id,
        recipient_id=r4.id,
        step_id=step1_id,
        status=CampaignDeliveryStatus.SKIPPED.value,
    )
    # r5: Step 1 SENT with thread1 (has_reply=True)
    d5_step1 = CampaignDelivery(
        campaign_id=campaign_id,
        recipient_id=r5.id,
        step_id=step1_id,
        status=CampaignDeliveryStatus.SENT.value,
        sent_at=datetime.now(timezone.utc),
        thread_id=thread1.id,
    )

    db_session.add_all([d1_step1, d1_step2, d2_step1, d3_step1, d3_step2, d4_step1, d5_step1])
    await db_session.commit()

    # Fetch Analytics
    analytics_resp = await async_client.get(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/analytics",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert analytics_resp.status_code == 200
    data = analytics_resp.json()

    assert data["total_recipients"] == 5
    assert data["total_steps"] == 2
    steps_data = data["steps"]

    # Step 1 Verification:
    s1 = steps_data[0]
    assert s1["step_number"] == 1
    assert s1["targeted_count"] == 5
    assert s1["sent_count"] == 3       # r1, r3, r5
    assert s1["bounced_count"] == 1    # r2
    assert s1["skipped_count"] == 1    # r4
    assert s1["replied_count"] == 1    # r5 replied after Step 1 (r1 replied after Step 2)
    assert s1["delivered_count"] == 2
    assert s1["delivery_rate"] == 66.7 # (3 sent - 1 bounced) / 3 * 100 = 66.7%
    assert s1["reply_rate"] == 33.3    # 1/3 * 100 = 33.3%
    assert s1["bounce_rate"] == 33.3   # 1/3 * 100 = 33.3%

    # Step 2 Verification (targeted only to ['vip']):
    s2 = steps_data[1]
    assert s2["step_number"] == 2
    assert s2["target_tags"] == ["vip"]
    assert s2["targeted_count"] == 3   # r1, r3, r4 have 'vip'
    assert s2["sent_count"] == 1       # r1
    assert s2["pending_count"] == 2    # r3 has PENDING delivery, r4 is active awaiting Step 2
    assert s2["replied_count"] == 1    # r1 replied after Step 2
    assert s2["delivered_count"] == 1
    assert s2["delivery_rate"] == 100.0 # 1 delivered / 1 sent * 100 = 100.0%
    assert s2["reply_rate"] == 100.0   # 1/1 * 100 = 100.0%
    assert s2["bounce_rate"] == 0.0


@pytest.mark.asyncio
async def test_step_analytics_company_isolation(async_client: AsyncClient):
    """Test that campaign analytics cannot be accessed across different company tenants."""
    token1 = await register_and_login(async_client, "owner_co1@company.com")
    co1_id = await create_company_helper(async_client, token1, "Company 1")
    acc1_id = await create_email_account_helper(async_client, token1, co1_id)

    token2 = await register_and_login(async_client, "owner_co2@company.com")
    co2_id = await create_company_helper(async_client, token2, "Company 2")

    # Co1 creates campaign
    resp = await async_client.post(
        f"/api/v1/companies/{co1_id}/campaigns",
        headers={"Authorization": f"Bearer {token1}"},
        json={
            "name": "Co1 Campaign",
            "email_account_id": acc1_id,
            "subject": "Co1 Subject",
            "body_text": "Co1 Body",
        },
    )
    assert resp.status_code == 201
    campaign_id = resp.json()["id"]

    # Co2 user attempts to fetch Co1's campaign analytics
    cross_resp = await async_client.get(
        f"/api/v1/companies/{co2_id}/campaigns/{campaign_id}/analytics",
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert cross_resp.status_code == 404


@pytest.mark.asyncio
async def test_step_analytics_consecutive_tag_mismatch_and_pending_progression(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Test pending_count correctness with consecutive tag-mismatched steps.
    
    Verifies that:
    - An active recipient awaiting their next eligible step across consecutive mismatched
      steps is counted as pending ONLY on their next eligible step.
    - An active recipient with no remaining matching steps is pending on 0 steps.
    - sum(pending_count) across all steps for a recipient is at most 1 (no duplicate pending).
    """
    token = await register_and_login(async_client, "owner_mismatch@company.com")
    company_id = await create_company_helper(async_client, token, "Mismatch Co")
    account_id = await create_email_account_helper(async_client, token, company_id)

    # 4-step campaign:
    # Step 1: untargeted
    # Step 2: tag 'vip'
    # Step 3: tag 'enterprise'
    # Step 4: tag 'smb'
    resp = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "4-Step Segmented Campaign",
            "email_account_id": account_id,
            "subject": "Step 1 Subject",
            "body_text": "Step 1 Body",
            "followup_steps": [
                {"step_number": 2, "delay_hours": 24, "subject": "S2", "body_text": "B2", "target_tags": ["vip"]},
                {"step_number": 3, "delay_hours": 48, "subject": "S3", "body_text": "B3", "target_tags": ["enterprise"]},
                {"step_number": 4, "delay_hours": 72, "subject": "S4", "body_text": "B4", "target_tags": ["smb"]},
            ],
        },
    )
    assert resp.status_code == 201
    campaign_id = resp.json()["id"]

    steps = (
        await db_session.execute(
            select(CampaignStep)
            .where(CampaignStep.campaign_id == campaign_id)
            .order_by(CampaignStep.step_number.asc())
        )
    ).scalars().all()
    assert len(steps) == 4

    # Recipient A: tag 'smb'. Completed Step 1 (current_step_number = 1).
    # Steps 2 and 3 do NOT match. Step 4 matches. Next eligible step is Step 4.
    r_a = CampaignRecipient(
        campaign_id=campaign_id,
        email="smb_user@company.com",
        custom_variables={"tags": ["smb"]},
        status=CampaignRecipientStatus.ACTIVE.value,
        current_step_number=1,
    )
    # Recipient B: tag 'vip'. Completed Step 1 (current_step_number = 1).
    # Step 2 matches. Next eligible step is Step 2.
    r_b = CampaignRecipient(
        campaign_id=campaign_id,
        email="vip_user@company.com",
        custom_variables={"tags": ["vip"]},
        status=CampaignRecipientStatus.ACTIVE.value,
        current_step_number=1,
    )
    # Recipient C: no tags. Completed Step 1 (current_step_number = 1).
    # None of Steps 2, 3, 4 match. Has no future eligible steps.
    r_c = CampaignRecipient(
        campaign_id=campaign_id,
        email="untagged_user@company.com",
        custom_variables={"tags": []},
        status=CampaignRecipientStatus.ACTIVE.value,
        current_step_number=1,
    )

    db_session.add_all([r_a, r_b, r_c])
    await db_session.flush()

    # Step 1 SENT deliveries for all 3
    for r in [r_a, r_b, r_c]:
        d = CampaignDelivery(
            campaign_id=campaign_id,
            recipient_id=r.id,
            step_id=steps[0].id,
            status=CampaignDeliveryStatus.SENT.value,
            sent_at=datetime.now(timezone.utc),
        )
        db_session.add(d)

    await db_session.commit()

    analytics_resp = await async_client.get(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/analytics",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert analytics_resp.status_code == 200
    data = analytics_resp.json()

    s1, s2, s3, s4 = data["steps"]

    # Step 1: all 3 sent, 0 pending
    assert s1["sent_count"] == 3
    assert s1["pending_count"] == 0

    # Step 2 (targets 'vip'): targeted by r_b only. Pending count is 1 (r_b).
    assert s2["targeted_count"] == 1
    assert s2["pending_count"] == 1

    # Step 3 (targets 'enterprise'): targeted by no one.
    assert s3["targeted_count"] == 0
    assert s3["pending_count"] == 0

    # Step 4 (targets 'smb'): targeted by r_a only. Next eligible step for r_a is Step 4.
    assert s4["targeted_count"] == 1
    assert s4["pending_count"] == 1

    # Verify no recipient is counted as pending on multiple steps:
    total_pending = sum(s["pending_count"] for s in data["steps"])
    assert total_pending == 2  # r_a on Step 4 + r_b on Step 2 (r_c is on no future steps)


@pytest.mark.asyncio
async def test_step_analytics_reply_attribution_and_sent_bound(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Test reply attribution invariants:
    - replid_count <= sent_count for every step
    - Reply attributed to single highest actually sent step (not skipped/pending steps)
    - Replies are not double-counted across steps
    - Conflicting reply indicators all trigger attribution without multiple increments
    - Recipient with reply indicators but 0 sent steps has replied_count == 0 (no unsent attribution)
    """
    token = await register_and_login(async_client, "owner_reply_bound@company.com")
    company_id = await create_company_helper(async_client, token, "Reply Bound Co")
    account_id = await create_email_account_helper(async_client, token, company_id)

    resp = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Reply Attribution Campaign",
            "email_account_id": account_id,
            "subject": "S1 Subject",
            "body_text": "S1 Body",
            "followup_steps": [
                {"step_number": 2, "delay_hours": 24, "subject": "S2", "body_text": "B2"},
                {"step_number": 3, "delay_hours": 48, "subject": "S3", "body_text": "B3"},
            ],
        },
    )
    assert resp.status_code == 201
    campaign_id = resp.json()["id"]

    steps = (
        await db_session.execute(
            select(CampaignStep)
            .where(CampaignStep.campaign_id == campaign_id)
            .order_by(CampaignStep.step_number.asc())
        )
    ).scalars().all()
    assert len(steps) == 3

    # Thread with has_reply = True
    thread_replied = EmailThread(
        company_id=company_id,
        email_account_id=account_id,
        subject="S1 Subject",
        has_reply=True,
        last_message_at=datetime.now(timezone.utc),
    )
    db_session.add(thread_replied)
    await db_session.flush()

    # Recipient 1: Step 1 SENT, Step 2 SENT, Step 3 SKIPPED. Stopped as REPLIED.
    # Highest SENT step is Step 2. Reply must be attributed to Step 2 (not Step 1 or Step 3).
    r1 = CampaignRecipient(
        campaign_id=campaign_id,
        email="r1_multistep@company.com",
        status=CampaignRecipientStatus.STOPPED.value,
        stopped_reason=CampaignRecipientStopReason.REPLIED.value,
        replied_at=datetime.now(timezone.utc),
        current_step_number=3,
    )
    # Recipient 2: Step 1 SENT. Thread has_reply is True, but replied_at is None.
    # Indicator disagreement: still triggers reply attribution to Step 1.
    r2 = CampaignRecipient(
        campaign_id=campaign_id,
        email="r2_threadreply@company.com",
        status=CampaignRecipientStatus.ACTIVE.value,
        current_step_number=1,
    )
    # Recipient 3: Unusual history: replied_at is set, but 0 deliveries were SENT.
    # Must NOT attribute to any step, ensuring replied_count <= sent_count on all steps.
    r3 = CampaignRecipient(
        campaign_id=campaign_id,
        email="r3_nosend@company.com",
        status=CampaignRecipientStatus.STOPPED.value,
        stopped_reason=CampaignRecipientStopReason.REPLIED.value,
        replied_at=datetime.now(timezone.utc),
        current_step_number=1,
    )

    db_session.add_all([r1, r2, r3])
    await db_session.flush()

    # Deliveries for r1:
    d1_s1 = CampaignDelivery(
        campaign_id=campaign_id,
        recipient_id=r1.id,
        step_id=steps[0].id,
        status=CampaignDeliveryStatus.SENT.value,
        sent_at=datetime.now(timezone.utc),
    )
    d1_s2 = CampaignDelivery(
        campaign_id=campaign_id,
        recipient_id=r1.id,
        step_id=steps[1].id,
        status=CampaignDeliveryStatus.SENT.value,
        sent_at=datetime.now(timezone.utc),
    )
    d1_s3 = CampaignDelivery(
        campaign_id=campaign_id,
        recipient_id=r1.id,
        step_id=steps[2].id,
        status=CampaignDeliveryStatus.SKIPPED.value,
    )
    # Deliveries for r2:
    d2_s1 = CampaignDelivery(
        campaign_id=campaign_id,
        recipient_id=r2.id,
        step_id=steps[0].id,
        status=CampaignDeliveryStatus.SENT.value,
        sent_at=datetime.now(timezone.utc),
        thread_id=thread_replied.id,
    )

    db_session.add_all([d1_s1, d1_s2, d1_s3, d2_s1])
    await db_session.commit()

    analytics_resp = await async_client.get(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/analytics",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert analytics_resp.status_code == 200
    data = analytics_resp.json()

    s1, s2, s3 = data["steps"]

    # Verify replied_count <= sent_count on EVERY step:
    for s in [s1, s2, s3]:
        assert s["replied_count"] <= s["sent_count"]

    # Step 1: sent to r1 and r2 (sent_count = 2). Reply from r2 is attributed here.
    assert s1["sent_count"] == 2
    assert s1["replied_count"] == 1
    assert s1["reply_rate"] == 50.0

    # Step 2: sent only to r1 (sent_count = 1). Reply from r1 is attributed here (highest sent step).
    assert s2["sent_count"] == 1
    assert s2["replied_count"] == 1
    assert s2["reply_rate"] == 100.0

    # Step 3: r1 was SKIPPED (sent_count = 0). replied_count = 0.
    assert s3["sent_count"] == 0
    assert s3["skipped_count"] == 1
    assert s3["replied_count"] == 0
    assert s3["reply_rate"] == 0.0

    # Total replies across all steps equals 2 (r1 + r2; r3 with 0 sends is not counted in any step):
    total_step_replies = sum(s["replied_count"] for s in data["steps"])
    assert total_step_replies == 2


@pytest.mark.asyncio
async def test_step_analytics_stopped_completed_and_advanced_recipients(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Test that stopped recipients (manual, bounce, unsub), completed sequences,
    and recipients who already advanced beyond a step are NEVER counted as pending.
    """
    token = await register_and_login(async_client, "owner_stopped_test@company.com")
    company_id = await create_company_helper(async_client, token, "Stopped Co")
    account_id = await create_email_account_helper(async_client, token, company_id)

    resp = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Lifecycle Guards Campaign",
            "email_account_id": account_id,
            "subject": "Step 1",
            "body_text": "Body 1",
            "followup_steps": [
                {"step_number": 2, "delay_hours": 24, "subject": "Step 2", "body_text": "Body 2"},
            ],
        },
    )
    assert resp.status_code == 201
    campaign_id = resp.json()["id"]

    steps = (
        await db_session.execute(
            select(CampaignStep)
            .where(CampaignStep.campaign_id == campaign_id)
            .order_by(CampaignStep.step_number.asc())
        )
    ).scalars().all()
    assert len(steps) == 2

    # 1. Stopped manually
    r_stopped = CampaignRecipient(
        campaign_id=campaign_id,
        email="stopped_user@company.com",
        status=CampaignRecipientStatus.STOPPED.value,
        stopped_reason=CampaignRecipientStopReason.MANUAL.value,
        current_step_number=1,
    )
    # 2. Completed sequence
    r_completed = CampaignRecipient(
        campaign_id=campaign_id,
        email="completed_user@company.com",
        status=CampaignRecipientStatus.COMPLETED.value,
        current_step_number=2,
    )
    # 3. Advanced beyond Step 1 (current_step_number = 2)
    r_advanced = CampaignRecipient(
        campaign_id=campaign_id,
        email="advanced_user@company.com",
        status=CampaignRecipientStatus.ACTIVE.value,
        current_step_number=2,
    )

    db_session.add_all([r_stopped, r_completed, r_advanced])
    await db_session.flush()

    # r_stopped has a stale PENDING delivery in DB on Step 2 (e.g. created before stop)
    # The analytics service must recognize that the recipient is stopped and not count them as pending!
    d_stale_pending = CampaignDelivery(
        campaign_id=campaign_id,
        recipient_id=r_stopped.id,
        step_id=steps[1].id,
        status=CampaignDeliveryStatus.PENDING.value,
    )
    db_session.add(d_stale_pending)
    await db_session.commit()

    analytics_resp = await async_client.get(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/analytics",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert analytics_resp.status_code == 200
    data = analytics_resp.json()

    s1, s2 = data["steps"]

    # Step 1: None of the three are pending Step 1 (all are at current_step_number >= 1)
    assert s1["pending_count"] == 0

    # Step 2:
    # r_stopped is stopped -> NOT pending
    # r_completed is completed -> NOT pending
    # r_advanced is at step 2 and completed all steps -> NOT pending
    assert s2["pending_count"] == 0


@pytest.mark.asyncio
async def test_step_analytics_header_based_reply_attribution_and_multi_reply(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Test header-based reply attribution and multi-step reply deduplication:
    1. Inbound reply to Step 1 arriving AFTER Step 2 was sent is attributed to Step 1 (not Step 2).
    2. Inbound reply to Step 2 is attributed to Step 2.
    3. One recipient replying to both Step 1 and Step 2 increments replied_count on both steps,
       but campaign unique_replied_count increments by only 1.
    4. Unmatched reply with non-existent message-id is not arbitrarily assigned to Step 1.
    """
    token = await register_and_login(async_client, "header_attr_user@company.com")
    company_id = await create_company_helper(async_client, token, "Header Attr Co")
    account_id = await create_email_account_helper(async_client, token, company_id)

    resp = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Header Attribution Test Campaign",
            "email_account_id": account_id,
            "subject": "Initial Email Subject",
            "body_text": "Step 1 Body",
            "followup_steps": [
                {"step_number": 2, "delay_hours": 24, "subject": "Follow-Up 1 Subject", "body_text": "Step 2 Body"}
            ],
        },
    )
    assert resp.status_code == 201
    campaign_id = resp.json()["id"]

    steps = (
        await db_session.execute(
            select(CampaignStep)
            .where(CampaignStep.campaign_id == campaign_id)
            .order_by(CampaignStep.step_number.asc())
        )
    ).scalars().all()
    assert len(steps) == 2

    # Recipients
    r1 = CampaignRecipient(
        campaign_id=campaign_id,
        email="lead_alpha@client.com",
        first_name="Alpha",
        status=CampaignRecipientStatus.ACTIVE.value,
        current_step_number=2,
    )
    r2 = CampaignRecipient(
        campaign_id=campaign_id,
        email="lead_beta@client.com",
        first_name="Beta",
        status=CampaignRecipientStatus.ACTIVE.value,
        current_step_number=2,
    )
    r3_unmatched = CampaignRecipient(
        campaign_id=campaign_id,
        email="lead_gamma@client.com",
        first_name="Gamma",
        status=CampaignRecipientStatus.ACTIVE.value,
        current_step_number=1,
    )
    db_session.add_all([r1, r2, r3_unmatched])
    await db_session.flush()

    day1 = datetime(2026, 11, 1, 10, 0, tzinfo=timezone.utc)
    day2 = datetime(2026, 11, 2, 10, 0, tzinfo=timezone.utc)
    day2_reply1 = datetime(2026, 11, 2, 14, 0, tzinfo=timezone.utc)
    day2_reply2 = datetime(2026, 11, 2, 16, 0, tzinfo=timezone.utc)

    # Deliveries
    # r1 Step 1 and Step 2
    d1_s1 = CampaignDelivery(
        campaign_id=campaign_id,
        recipient_id=r1.id,
        step_id=steps[0].id,
        status=CampaignDeliveryStatus.SENT.value,
        sent_at=day1,
        message_id="<s1_msg_alpha@company.com>",
    )
    d1_s2 = CampaignDelivery(
        campaign_id=campaign_id,
        recipient_id=r1.id,
        step_id=steps[1].id,
        status=CampaignDeliveryStatus.SENT.value,
        sent_at=day2,
        message_id="<s2_msg_alpha@company.com>",
    )
    # r2 Step 1 and Step 2
    d2_s1 = CampaignDelivery(
        campaign_id=campaign_id,
        recipient_id=r2.id,
        step_id=steps[0].id,
        status=CampaignDeliveryStatus.SENT.value,
        sent_at=day1,
        message_id="<s1_msg_beta@company.com>",
    )
    d2_s2 = CampaignDelivery(
        campaign_id=campaign_id,
        recipient_id=r2.id,
        step_id=steps[1].id,
        status=CampaignDeliveryStatus.SENT.value,
        sent_at=day2,
        message_id="<s2_msg_beta@company.com>",
    )
    # r3 Step 1
    d3_s1 = CampaignDelivery(
        campaign_id=campaign_id,
        recipient_id=r3_unmatched.id,
        step_id=steps[0].id,
        status=CampaignDeliveryStatus.SENT.value,
        sent_at=day1,
        message_id="<s1_msg_gamma@company.com>",
    )
    db_session.add_all([d1_s1, d1_s2, d2_s1, d2_s2, d3_s1])
    await db_session.flush()

    # Inbound email 1: r1 replies at 2pm on Day 2 referencing Step 1 (after Step 2 was already sent at 10am)
    reply_r1_s1 = Email(
        company_id=company_id,
        email_account_id=account_id,
        direction=EmailDirection.INCOMING.value,
        sender="lead_alpha@client.com",
        recipients=["sender@company.com"],
        subject="Re: Initial Email Subject",
        in_reply_to="<s1_msg_alpha@company.com>",
        references_header="<s1_msg_alpha@company.com>",
        message_id="<reply_r1_s1@client.com>",
        sent_at=day2_reply1,
        received_at=day2_reply1,
    )
    # Inbound email 2: r2 replies referencing Step 2
    reply_r2_s2 = Email(
        company_id=company_id,
        email_account_id=account_id,
        direction=EmailDirection.INCOMING.value,
        sender="lead_beta@client.com",
        recipients=["sender@company.com"],
        subject="Re: Follow-Up 1 Subject",
        in_reply_to="<s2_msg_beta@company.com>",
        references_header="<s1_msg_beta@company.com> <s2_msg_beta@company.com>",
        message_id="<reply_r2_s2@client.com>",
        sent_at=day2_reply2,
        received_at=day2_reply2,
    )
    # Inbound email 3: r1 also replies to Step 2
    reply_r1_s2 = Email(
        company_id=company_id,
        email_account_id=account_id,
        direction=EmailDirection.INCOMING.value,
        sender="lead_alpha@client.com",
        recipients=["sender@company.com"],
        subject="Re: Follow-Up 1 Subject",
        in_reply_to="<s2_msg_alpha@company.com>",
        references_header="<s1_msg_alpha@company.com> <s2_msg_alpha@company.com>",
        message_id="<reply_r1_s2@client.com>",
        sent_at=day2_reply2,
        received_at=day2_reply2,
    )
    # Inbound email 4: Unmatched email from unknown source / unrelated thread
    unmatched_email = Email(
        company_id=company_id,
        email_account_id=account_id,
        direction=EmailDirection.INCOMING.value,
        sender="stranger@other.com",
        recipients=["sender@company.com"],
        subject="Random question",
        in_reply_to="<completely_unrelated@random.com>",
        references_header="<completely_unrelated@random.com>",
        message_id="<random_msg@other.com>",
        sent_at=day2_reply2,
        received_at=day2_reply2,
    )

    db_session.add_all([reply_r1_s1, reply_r2_s2, reply_r1_s2, unmatched_email])
    await db_session.commit()

    analytics_resp = await async_client.get(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/analytics",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert analytics_resp.status_code == 200
    data = analytics_resp.json()

    # Total recipients: 3 (r1, r2, r3)
    assert data["total_recipients"] == 3
    # Step 1 sent to r1, r2, r3 = 3
    assert data["initial_sent_count"] == 3
    # Step 2 sent to r1, r2 = 2
    assert data["followup_sent_count"] == 2
    assert data["total_sent_count"] == 5

    # Unique recipients replied: exactly 2 (r1 and r2), stranger not counted, r1 counted once
    assert data["unique_replied_count"] == 2

    s1 = data["steps"][0]
    s2 = data["steps"][1]

    # Step 1: replied_count == 1 (r1 replied to Step 1 via in_reply_to)
    assert s1["step_number"] == 1
    assert s1["sent_count"] == 3
    assert s1["replied_count"] == 1
    assert s1["reply_rate"] == round((1 / 3) * 100, 1)

    # Step 2: replied_count == 2 (both r1 and r2 replied to Step 2 via in_reply_to)
    assert s2["step_number"] == 2
    assert s2["sent_count"] == 2
    assert s2["replied_count"] == 2
    assert s2["reply_rate"] == 100.0

    # Unmatched reply was NOT assigned to any step arbitrarily
    assert s1["replied_count"] + s2["replied_count"] == 3


from unittest.mock import AsyncMock, patch
from app.modules.email_accounts.models import EmailAccount
from app.services.imap.parser import ParsedEmail
from app.modules.emails.monitoring_service import EmailMonitoringService
from app.modules.campaigns.delivery_service import CampaignDeliveryService
from app.modules.campaigns.recipient_service import CampaignRecipientService
from tests.conftest import TestAsyncSessionLocal


@pytest.mark.asyncio
async def test_reply_detection_ignores_internal_connected_account_and_outbound(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """1. An outbound campaign email received in another connected internal mailbox
    must NOT trigger false reply detection."""
    token = await register_and_login(async_client, "owner_internal_test@company.com")
    company_id = await create_company_helper(async_client, token, "Internal Test Co")

    # Account 1: Campaign sender
    acc1_id = await create_email_account_helper(async_client, token, company_id, "camp_sender@company.com")
    # Account 2: Internal connected recipient mailbox
    acc2_id = await create_email_account_helper(async_client, token, company_id, "internal_lead@company.com")

    # Campaign
    camp_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Internal Connected Account Test",
            "email_account_id": acc1_id,
            "subject": "Initial Subject",
            "body_text": "Body",
        },
    )
    assert camp_resp.status_code == 201
    campaign_id = camp_resp.json()["id"]

    step = (await db_session.execute(select(CampaignStep).where(CampaignStep.campaign_id == campaign_id))).scalar_one()

    recipient = CampaignRecipient(
        campaign_id=campaign_id,
        email="internal_lead@company.com",
        status=CampaignRecipientStatus.ACTIVE.value,
        current_step_number=1,
    )
    db_session.add(recipient)
    await db_session.flush()

    delivery = CampaignDelivery(
        campaign_id=campaign_id,
        recipient_id=recipient.id,
        step_id=step.id,
        status=CampaignDeliveryStatus.SENT.value,
        message_id="<step1_msg_internal@company.com>",
        sent_at=datetime.now(timezone.utc),
    )
    db_session.add(delivery)
    await db_session.commit()

    acc2 = await db_session.get(EmailAccount, acc2_id)
    assert acc2 is not None

    # Scenario: Account 2 receives the outbound email from Account 1 with Step 1 message_id in In-Reply-To
    parsed_outbound_synced = ParsedEmail(
        message_id="<outbound_followup@company.com>",
        in_reply_to="<step1_msg_internal@company.com>",
        references_header="<step1_msg_internal@company.com>",
        sender="Campaign Sender <camp_sender@company.com>",
        recipients=["internal_lead@company.com"],
        cc=None,
        bcc=None,
        reply_to=None,
        subject="Re: Initial Subject",
        body_text="Follow up body",
        body_html=None,
        date=datetime.now(timezone.utc),
    )

    matched = await EmailMonitoringService.match_and_process_campaign_reply(
        db=db_session,
        account=acc2,
        parsed=parsed_outbound_synced,
        thread_id=None,
        is_reply_to_outgoing=False,
    )
    # Must NOT be recognized as a reply because sender is the campaign sender, not the recipient
    assert matched == 0

    await db_session.refresh(recipient)
    assert recipient.replied_at is None
    assert recipient.stopped_reason is None

    # Check analytics endpoint
    analytics_resp = await async_client.get(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/analytics",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert analytics_resp.status_code == 200
    data = analytics_resp.json()
    assert data["unique_replied_count"] == 0
    assert data["steps"][0]["replied_count"] == 0


@pytest.mark.asyncio
async def test_earlier_manual_reschedule_not_overwritten_by_worker(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """2. A manual reschedule to an earlier time must NOT be overwritten by the worker
    with the step's default delay."""
    token = await register_and_login(async_client, "owner_resched_test@company.com")
    company_id = await create_company_helper(async_client, token, "Resched Test Co")
    account_id = await create_email_account_helper(async_client, token, company_id)

    resp = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Reschedule Persistence Test",
            "email_account_id": account_id,
            "subject": "Initial Subject",
            "body_text": "Body 1",
            "followup_steps": [
                {"step_number": 2, "delay_hours": 24, "subject": "Step 2 Subject", "body_text": "Body 2"}
            ],
        },
    )
    assert resp.status_code == 201
    campaign_id = resp.json()["id"]

    camp = await db_session.get(Campaign, campaign_id)
    camp.status = CampaignStatus.RUNNING.value
    await db_session.commit()

    steps = (
        await db_session.execute(
            select(CampaignStep).where(CampaignStep.campaign_id == campaign_id).order_by(CampaignStep.step_number)
        )
    ).scalars().all()

    now_sim = datetime.now(timezone.utc)
    t0 = now_sim - timedelta(hours=1)
    t_resched = now_sim + timedelta(minutes=5)

    recipient = CampaignRecipient(
        campaign_id=campaign_id,
        email="lead_resched@client.com",
        status=CampaignRecipientStatus.SENT.value,
        current_step_number=1,
        next_step_due_at=t0 + timedelta(hours=24),  # Default 24h
    )
    db_session.add(recipient)
    await db_session.flush()

    d1 = CampaignDelivery(
        campaign_id=campaign_id,
        recipient_id=recipient.id,
        step_id=steps[0].id,
        status=CampaignDeliveryStatus.SENT.value,
        message_id="<step1_lead_resched@company.com>",
        sent_at=t0,
    )
    db_session.add(d1)
    await db_session.commit()

    # User manually reschedules next step to earlier future time
    resched_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/recipients/{recipient.id}/reschedule",
        headers={"Authorization": f"Bearer {token}"},
        json={"next_step_due_at": t_resched.isoformat()},
    )
    assert resched_resp.status_code == 200

    await db_session.refresh(recipient)
    assert recipient.next_step_due_at == t_resched

    # Worker executes when t_resched has arrived
    mock_email_svc = AsyncMock()
    mock_sent_email = AsyncMock()
    mock_sent_email.id = None
    mock_sent_email.thread_id = None
    mock_sent_email.message_id = "<step2_sent@company.com>"
    mock_email_svc.send_email.return_value = mock_sent_email

    def test_db_factory():
        from app.core.database import AsyncSessionLocal
        return AsyncSessionLocal()

    dispatched = await CampaignDeliveryService.process_due_followup_steps(
        db_factory=TestAsyncSessionLocal,
        email_service=mock_email_svc,
        now_utc=now_sim + timedelta(minutes=6),
    )

    assert len(dispatched) == 1
    assert dispatched[0]["recipient_id"] == recipient.id
    assert dispatched[0]["status"] == "SENT"
    assert dispatched[0]["step_number"] == 2

    # Verify recipient advanced to step 2 and completed, NOT reverted to 24h
    await db_session.refresh(recipient)
    assert recipient.current_step_number == 2
    assert recipient.status == CampaignRecipientStatus.COMPLETED.value
    assert recipient.next_step_due_at is None


@pytest.mark.asyncio
async def test_manually_stopped_recipient_preserves_initial_sent_counts(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """3. A recipient manually stopped after Step 1 must remain included in Initial Sent."""
    token = await register_and_login(async_client, "owner_stopped_test@company.com")
    company_id = await create_company_helper(async_client, token, "Stopped Test Co")
    account_id = await create_email_account_helper(async_client, token, company_id)

    resp = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Stopped Count Test",
            "email_account_id": account_id,
            "subject": "Initial Subject",
            "body_text": "Body 1",
            "followup_steps": [
                {"step_number": 2, "delay_hours": 24, "subject": "Step 2", "body_text": "Body 2"}
            ],
        },
    )
    assert resp.status_code == 201
    campaign_id = resp.json()["id"]

    camp = await db_session.get(Campaign, campaign_id)
    camp.status = CampaignStatus.RUNNING.value
    await db_session.commit()

    step1 = (await db_session.execute(select(CampaignStep).where(CampaignStep.campaign_id == campaign_id, CampaignStep.step_number == 1))).scalar_one()

    r1 = CampaignRecipient(
        campaign_id=campaign_id,
        email="lead_1@client.com",
        status=CampaignRecipientStatus.SENT.value,
        current_step_number=1,
    )
    r2 = CampaignRecipient(
        campaign_id=campaign_id,
        email="lead_2@client.com",
        status=CampaignRecipientStatus.SENT.value,
        current_step_number=1,
    )
    db_session.add_all([r1, r2])
    await db_session.flush()

    d1 = CampaignDelivery(
        campaign_id=campaign_id,
        recipient_id=r1.id,
        step_id=step1.id,
        status=CampaignDeliveryStatus.SENT.value,
        message_id="<s1_lead1@co.com>",
        sent_at=datetime.now(timezone.utc),
    )
    d2 = CampaignDelivery(
        campaign_id=campaign_id,
        recipient_id=r2.id,
        step_id=step1.id,
        status=CampaignDeliveryStatus.SENT.value,
        message_id="<s1_lead2@co.com>",
        sent_at=datetime.now(timezone.utc),
    )
    db_session.add_all([d1, d2])
    await db_session.commit()

    # Manually stop r1
    stop_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/recipients/{r1.id}/stop",
        headers={"Authorization": f"Bearer {token}"},
        json={"reason": "MANUAL"},
    )
    assert stop_resp.status_code == 200

    # 1. Check campaign detail endpoint
    detail_resp = await async_client.get(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert detail_resp.status_code == 200
    camp_detail = detail_resp.json()
    assert camp_detail["sent_count"] == 2  # Both r1 and r2 received Step 1
    assert camp_detail["initial_sent_count"] == 2
    assert camp_detail["suppressed_count"] == 1

    # 2. Check analytics endpoint
    analytics_resp = await async_client.get(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/analytics",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert analytics_resp.status_code == 200
    an_data = analytics_resp.json()
    assert an_data["initial_sent_count"] == 2
    assert an_data["steps"][0]["sent_count"] == 2


@pytest.mark.asyncio
async def test_exact_manual_qa_campaign_01_scenario(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """4. Exact test scenario from MANUAL-QA-CAMPAIGN-01:
    - 4 recipients, Step 1 and Step 2.
    - All 4 receive Step 1.
    - Recipient 1 (Yahoo): genuine reply received -> STOPPED (REPLIED).
    - Recipient 2 (Zoho): skip next follow-up -> Step 2 SKIPPED, COMPLETED.
    - Recipient 3 (Gmail 1): manually stopped -> STOPPED (MANUAL).
    - Recipient 4 (Gmail 2): Step 2 rescheduled and sent -> COMPLETED.
    - Connected account imports Step 2 into internal inbox -> NOT counted as reply.
    """
    token = await register_and_login(async_client, "qa_owner@company.com")
    company_id = await create_company_helper(async_client, token, "QA Ground Truth Co")

    # Campaign sender
    acc_sender_id = await create_email_account_helper(async_client, token, company_id, "sgarden2006@gmail.com")
    # Connected account for Recipient 4
    acc_recip4_id = await create_email_account_helper(async_client, token, company_id, "odhavanidipak@gmail.com")

    resp = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "MANUAL-QA-CAMPAIGN-01",
            "email_account_id": acc_sender_id,
            "subject": "PulseMail Manual Campaign Test",
            "body_text": "Body 1",
            "followup_steps": [
                {"step_number": 2, "delay_hours": 1, "subject": "Re: PulseMail Manual Campaign Test", "body_text": "Body 2"}
            ],
        },
    )
    assert resp.status_code == 201
    campaign_id = resp.json()["id"]

    steps = (
        await db_session.execute(
            select(CampaignStep).where(CampaignStep.campaign_id == campaign_id).order_by(CampaignStep.step_number)
        )
    ).scalars().all()
    s1, s2 = steps[0], steps[1]

    r1_yahoo = CampaignRecipient(
        campaign_id=campaign_id,
        email="dipakodhavani@yahoo.com",
        status=CampaignRecipientStatus.SENT.value,
        current_step_number=1,
    )
    r2_zoho = CampaignRecipient(
        campaign_id=campaign_id,
        email="dipakodhavani@zohomail.in",
        status=CampaignRecipientStatus.SENT.value,
        current_step_number=1,
    )
    r3_gmail1 = CampaignRecipient(
        campaign_id=campaign_id,
        email="dipakodhavani@gmail.com",
        status=CampaignRecipientStatus.SENT.value,
        current_step_number=1,
    )
    r4_gmail2 = CampaignRecipient(
        campaign_id=campaign_id,
        email="odhavanidipak@gmail.com",
        status=CampaignRecipientStatus.SENT.value,
        current_step_number=1,
    )
    db_session.add_all([r1_yahoo, r2_zoho, r3_gmail1, r4_gmail2])
    await db_session.flush()

    t_s1 = datetime(2026, 11, 3, 9, 14, tzinfo=timezone.utc)
    t_s2 = datetime(2026, 11, 3, 10, 15, tzinfo=timezone.utc)

    # Deliveries for Step 1
    d1_s1 = CampaignDelivery(
        campaign_id=campaign_id, recipient_id=r1_yahoo.id, step_id=s1.id,
        status=CampaignDeliveryStatus.SENT.value, sent_at=t_s1, message_id="<s1_yahoo@gmail.com>"
    )
    d2_s1 = CampaignDelivery(
        campaign_id=campaign_id, recipient_id=r2_zoho.id, step_id=s1.id,
        status=CampaignDeliveryStatus.SENT.value, sent_at=t_s1, message_id="<s1_zoho@gmail.com>"
    )
    d3_s1 = CampaignDelivery(
        campaign_id=campaign_id, recipient_id=r3_gmail1.id, step_id=s1.id,
        status=CampaignDeliveryStatus.SENT.value, sent_at=t_s1, message_id="<s1_gmail1@gmail.com>"
    )
    d4_s1 = CampaignDelivery(
        campaign_id=campaign_id, recipient_id=r4_gmail2.id, step_id=s1.id,
        status=CampaignDeliveryStatus.SENT.value, sent_at=t_s1, message_id="<s1_gmail2@gmail.com>"
    )
    db_session.add_all([d1_s1, d2_s1, d3_s1, d4_s1])
    await db_session.flush()

    # Action 1: Yahoo recipient replies genuinely
    r1_yahoo.stopped_reason = CampaignRecipientStopReason.REPLIED.value
    r1_yahoo.replied_at = datetime(2026, 11, 3, 9, 19, tzinfo=timezone.utc)
    yahoo_inbound = Email(
        company_id=company_id,
        email_account_id=acc_sender_id,
        direction=EmailDirection.INCOMING.value,
        sender="dipakodhavani@yahoo.com",
        recipients=["sgarden2006@gmail.com"],
        subject="Re: PulseMail Manual Campaign Test",
        in_reply_to="<s1_yahoo@gmail.com>",
        references_header="<s1_yahoo@gmail.com>",
        message_id="<yahoo_reply@mail.yahoo.com>",
        sent_at=r1_yahoo.replied_at,
        received_at=r1_yahoo.replied_at,
    )
    db_session.add(yahoo_inbound)

    # Action 2: Zoho recipient skips next follow-up
    r2_zoho.status = CampaignRecipientStatus.COMPLETED.value
    r2_zoho.current_step_number = 2
    d2_s2_skip = CampaignDelivery(
        campaign_id=campaign_id, recipient_id=r2_zoho.id, step_id=s2.id,
        status=CampaignDeliveryStatus.SKIPPED.value, error_message="Step skipped by administrator"
    )
    db_session.add(d2_s2_skip)

    # Action 3: Gmail 1 recipient manually stopped
    r3_gmail1.status = CampaignRecipientStatus.STOPPED.value
    r3_gmail1.stopped_reason = "MANUAL"

    # Action 4: Gmail 2 recipient follow-up sent
    r4_gmail2.status = CampaignRecipientStatus.COMPLETED.value
    r4_gmail2.current_step_number = 2
    d4_s2 = CampaignDelivery(
        campaign_id=campaign_id, recipient_id=r4_gmail2.id, step_id=s2.id,
        status=CampaignDeliveryStatus.SENT.value, sent_at=t_s2, message_id="<s2_gmail2@gmail.com>"
    )
    db_session.add(d4_s2)

    # Action 5: Step 2 delivery is imported into connected account 4's inbox (EmailDirection.INCOMING)
    # The sender is the campaign sender!
    imported_outbound_to_acc4 = Email(
        company_id=company_id,
        email_account_id=acc_recip4_id,
        direction=EmailDirection.INCOMING.value,
        sender="Shadow Garden <sgarden2006@gmail.com>",
        recipients=["odhavanidipak@gmail.com"],
        subject="Re: PulseMail Manual Campaign Test",
        in_reply_to="<s1_gmail2@gmail.com>",
        references_header="<s1_gmail2@gmail.com>",
        message_id="<s2_gmail2@gmail.com>",
        sent_at=t_s2,
        received_at=t_s2,
    )
    db_session.add(imported_outbound_to_acc4)
    await db_session.commit()

    # Check Analytics
    analytics_resp = await async_client.get(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/analytics",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert analytics_resp.status_code == 200
    analytics = analytics_resp.json()

    # Ground Truth Assertions:
    assert analytics["total_recipients"] == 4
    assert analytics["initial_sent_count"] == 4
    assert analytics["followup_sent_count"] == 1
    assert analytics["total_sent_count"] == 5
    # Crucial: Exactly 1 unique reply (Yahoo), Gmail 2 was excluded despite matching in_reply_to!
    assert analytics["unique_replied_count"] == 1

    s1_metrics = analytics["steps"][0]
    assert s1_metrics["step_number"] == 1
    assert s1_metrics["sent_count"] == 4
    assert s1_metrics["replied_count"] == 1
    assert s1_metrics["reply_rate"] == 25.0

    s2_metrics = analytics["steps"][1]
    assert s2_metrics["step_number"] == 2
    assert s2_metrics["sent_count"] == 1
    assert s2_metrics["replied_count"] == 0
    assert s2_metrics["reply_rate"] == 0.0

    # Check Campaign Detail Read
    detail_resp = await async_client.get(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["initial_sent_count"] == 4
    assert detail["sent_count"] == 4
    assert detail["followup_sent_count"] == 1
    assert detail["total_sent_count"] == 5
    assert detail["unique_replied_count"] == 1



@pytest.mark.asyncio
async def test_historical_stale_reply_flag_without_genuine_inbound_is_not_counted_as_reply(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Test that a recipient with a stale historical replied_at / stopped_reason='REPLIED'
    (e.g. from an internal outbound echo or corrupted status) is NOT counted as a reply
    when no genuine inbound email or thread reply exists.
    Ensures perfect consistency between get_campaign_analytics and get_recipient_status_counts.
    """
    token = await register_and_login(async_client, "owner_stale_reply_test@company.com")
    company_id = await create_company_helper(async_client, token, "Stale Reply Co")
    account_id = await create_email_account_helper(async_client, token, company_id, "camp_sender@co.com")

    resp = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Stale Flag Verification Campaign",
            "email_account_id": account_id,
            "subject": "Stale Subject",
            "body_text": "Body 1",
            "followup_steps": [
                {"step_number": 2, "delay_hours": 24, "subject": "Step 2", "body_text": "Body 2"}
            ],
        },
    )
    assert resp.status_code == 201
    campaign_id = resp.json()["id"]

    steps = (
        await db_session.execute(
            select(CampaignStep).where(CampaignStep.campaign_id == campaign_id).order_by(CampaignStep.step_number)
        )
    ).scalars().all()
    s1, s2 = steps[0], steps[1]

    # Recipient 1: Stale flag on COMPLETED recipient with delivery thread has_reply == False
    r1_stale = CampaignRecipient(
        campaign_id=campaign_id,
        email="lead_stale@client.com",
        status=CampaignRecipientStatus.COMPLETED.value,
        current_step_number=2,
        stopped_reason=CampaignRecipientStopReason.REPLIED.value,  # Stale flag!
        replied_at=datetime(2026, 11, 3, 10, 0, tzinfo=timezone.utc),
    )
    # Recipient 2: Genuine reply with verified delivery thread has_reply == True
    r2_genuine = CampaignRecipient(
        campaign_id=campaign_id,
        email="lead_genuine@client.com",
        status=CampaignRecipientStatus.STOPPED.value,
        current_step_number=1,
        stopped_reason=CampaignRecipientStopReason.REPLIED.value,
        replied_at=datetime(2026, 11, 3, 9, 30, tzinfo=timezone.utc),
    )
    db_session.add_all([r1_stale, r2_genuine])
    await db_session.flush()

    # Threads
    th_stale = EmailThread(
        company_id=company_id,
        email_account_id=account_id,
        subject="Stale Subject",
        has_reply=False,  # Explicitly has_reply == False!
        last_message_at=datetime(2026, 11, 3, 9, 0, tzinfo=timezone.utc),
    )
    th_genuine = EmailThread(
        company_id=company_id,
        email_account_id=account_id,
        subject="Stale Subject",
        has_reply=True,  # Genuine thread reply!
        last_message_at=datetime(2026, 11, 3, 9, 30, tzinfo=timezone.utc),
    )
    db_session.add_all([th_stale, th_genuine])
    await db_session.flush()

    # Deliveries
    d1_s1 = CampaignDelivery(
        campaign_id=campaign_id, recipient_id=r1_stale.id, step_id=s1.id,
        status=CampaignDeliveryStatus.SENT.value, thread_id=th_stale.id,
        message_id="<s1_stale@co.com>", sent_at=datetime(2026, 11, 3, 9, 0, tzinfo=timezone.utc),
    )
    d1_s2 = CampaignDelivery(
        campaign_id=campaign_id, recipient_id=r1_stale.id, step_id=s2.id,
        status=CampaignDeliveryStatus.SENT.value, thread_id=th_stale.id,
        message_id="<s2_stale@co.com>", sent_at=datetime(2026, 11, 3, 10, 0, tzinfo=timezone.utc),
    )
    d2_s1 = CampaignDelivery(
        campaign_id=campaign_id, recipient_id=r2_genuine.id, step_id=s1.id,
        status=CampaignDeliveryStatus.SENT.value, thread_id=th_genuine.id,
        message_id="<s1_genuine@co.com>", sent_at=datetime(2026, 11, 3, 9, 0, tzinfo=timezone.utc),
    )
    db_session.add_all([d1_s1, d1_s2, d2_s1])

    # Genuine inbound email from lead_genuine@client.com
    inbound_email = Email(
        company_id=company_id,
        email_account_id=account_id,
        direction=EmailDirection.INCOMING.value,
        sender="lead_genuine@client.com",
        recipients=["camp_sender@co.com"],
        subject="Re: Stale Subject",
        in_reply_to="<s1_genuine@co.com>",
        references_header="<s1_genuine@co.com>",
        message_id="<inbound_gen@client.com>",
        sent_at=datetime(2026, 11, 3, 9, 30, tzinfo=timezone.utc),
        received_at=datetime(2026, 11, 3, 9, 30, tzinfo=timezone.utc),
    )
    db_session.add(inbound_email)
    await db_session.commit()

    # 1. Verify Campaign Detail Read (get_recipient_status_counts)
    detail_resp = await async_client.get(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    # Must be 1 (only lead_genuine, NOT lead_stale)
    assert detail["unique_replied_count"] == 1

    # 2. Verify Analytics Read (get_campaign_analytics)
    analytics_resp = await async_client.get(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/analytics",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert analytics_resp.status_code == 200
    analytics = analytics_resp.json()

    assert analytics["total_recipients"] == 2
    assert analytics["initial_sent_count"] == 2
    assert analytics["followup_sent_count"] == 1
    assert analytics["total_sent_count"] == 3
    # Exactly 1 unique reply
    assert analytics["unique_replied_count"] == 1

    # Step 1: 1 reply (genuine)
    assert analytics["steps"][0]["sent_count"] == 2
    assert analytics["steps"][0]["replied_count"] == 1
    assert analytics["steps"][0]["reply_rate"] == 50.0

    # Step 2: 0 replies (stale recipient was NOT credited with reply on Step 2!)
    assert analytics["steps"][1]["sent_count"] == 1
    assert analytics["steps"][1]["replied_count"] == 0
    assert analytics["steps"][1]["reply_rate"] == 0.0

    # Delivery trend: exactly 1 reply
    assert len(analytics["delivery_trend"]) == 1
    assert analytics["delivery_trend"][0]["replied_count"] == 1



@pytest.mark.asyncio
async def test_reply_transitions_recipient_to_stopped_and_finalizes_campaign(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """M21.2 Fix 1 & 2: Recipient status transitions from SENT/ACTIVE to STOPPED (REPLIED)
    and the campaign automatically transitions to COMPLETED when no further work remains.
    """
    token = await register_and_login(async_client, "owner_reply_stop@company.com")
    company_id = await create_company_helper(async_client, token, "Reply Stop Co")
    account_id = await create_email_account_helper(async_client, token, company_id, email_address="outbound_reply_sender@company.com")

    campaign = Campaign(
        company_id=company_id,
        email_account_id=account_id,
        name="Auto-Complete Single Step Campaign",
        subject="Hello",
        body_html="<p>Test</p>",
        status=CampaignStatus.RUNNING.value,
    )
    db_session.add(campaign)
    await db_session.flush()

    step1 = CampaignStep(
        campaign_id=campaign.id,
        step_number=1,
        subject="Step 1",
        body_html="<p>Step 1 content</p>",
        delay_hours=0,
        is_active=True,
    )
    recipient = CampaignRecipient(
        campaign_id=campaign.id,
        email="customer_reply@client.com",
        current_step_number=1,
        status=CampaignRecipientStatus.SENT.value,  # Was SENT on Step 1
        stopped_reason=None,
        next_step_due_at=None,  # No further steps
    )
    db_session.add_all([step1, recipient])
    await db_session.flush()

    delivery = CampaignDelivery(
        campaign_id=campaign.id,
        recipient_id=recipient.id,
        step_id=step1.id,
        status=CampaignDeliveryStatus.SENT.value,
        message_id="<step1_deliv@company.com>",
        sent_at=datetime.now(timezone.utc) - timedelta(hours=2),
    )
    db_session.add(delivery)
    await db_session.commit()

    # Simulate inbound reply processed by EmailMonitoringService
    from app.modules.emails.monitoring_service import EmailMonitoringService
    from app.services.imap.parser import ParsedEmail

    account = await db_session.get(EmailAccount, account_id)
    parsed = ParsedEmail(
        message_id="<reply_01@client.com>",
        in_reply_to="<step1_deliv@company.com>",
        references_header="<step1_deliv@company.com>",
        sender="customer_reply@client.com",
        recipients=["outbound_reply_sender@company.com"],
        cc=None,
        bcc=None,
        reply_to=None,
        subject="Re: Hello",
        body_text="Yes I am interested!",
        body_html=None,
        date=datetime.now(timezone.utc),
    )

    matched = await EmailMonitoringService.match_and_process_campaign_reply(
        db=db_session,
        account=account,
        parsed=parsed,
        thread_id=None,
        is_reply_to_outgoing=False,
    )
    await db_session.commit()
    assert matched == 1

    # Verify recipient transitioned to STOPPED with REPLIED reason
    await db_session.refresh(recipient)
    assert recipient.status == CampaignRecipientStatus.STOPPED.value
    assert recipient.stopped_reason == CampaignRecipientStopReason.REPLIED.value
    assert recipient.replied_at is not None

    # Verify campaign was automatically finalized to COMPLETED
    await db_session.refresh(campaign)
    assert campaign.status == CampaignStatus.COMPLETED.value


@pytest.mark.asyncio
async def test_campaign_does_not_finalize_with_future_scheduled_followups(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """M21.2 Fix 2 safety check: Never prematurely complete a RUNNING campaign
    if there is future eligible or scheduled follow-up work.
    """
    token = await register_and_login(async_client, "owner_future_check@company.com")
    company_id = await create_company_helper(async_client, token, "Future Check Co")
    account_id = await create_email_account_helper(async_client, token, company_id, email_address="sender_future@company.com")

    campaign = Campaign(
        company_id=company_id,
        email_account_id=account_id,
        name="Two-Step In-Progress Campaign",
        subject="Two Steps",
        body_html="<p>Test</p>",
        status=CampaignStatus.RUNNING.value,
    )
    db_session.add(campaign)
    await db_session.flush()

    s1 = CampaignStep(campaign_id=campaign.id, step_number=1, subject="S1", body_html="S1", delay_hours=0, is_active=True)
    s2 = CampaignStep(campaign_id=campaign.id, step_number=2, subject="S2", body_html="S2", delay_hours=24, is_active=True)
    db_session.add_all([s1, s2])
    await db_session.flush()

    # r1 replied and is STOPPED
    r1 = CampaignRecipient(
        campaign_id=campaign.id,
        email="r1_replied@client.com",
        current_step_number=1,
        status=CampaignRecipientStatus.STOPPED.value,
        stopped_reason=CampaignRecipientStopReason.REPLIED.value,
        replied_at=datetime.now(timezone.utc),
        next_step_due_at=None,
    )
    # r2 finished step 1 and has step 2 scheduled in the future!
    r2 = CampaignRecipient(
        campaign_id=campaign.id,
        email="r2_scheduled@client.com",
        current_step_number=1,
        status=CampaignRecipientStatus.SENT.value,
        stopped_reason=None,
        next_step_due_at=datetime.now(timezone.utc) + timedelta(hours=20),
    )
    db_session.add_all([r1, r2])
    await db_session.flush()

    d1 = CampaignDelivery(
        campaign_id=campaign.id, recipient_id=r1.id, step_id=s1.id,
        status=CampaignDeliveryStatus.SENT.value, message_id="<d1@company.com>",
    )
    d2 = CampaignDelivery(
        campaign_id=campaign.id, recipient_id=r2.id, step_id=s1.id,
        status=CampaignDeliveryStatus.SENT.value, message_id="<d2@company.com>",
    )
    db_session.add_all([d1, d2])
    await db_session.commit()

    # Attempt campaign completion check
    from app.modules.campaigns.delivery_service import CampaignDeliveryService
    status_result = await CampaignDeliveryService.check_and_finalize_campaign_completion(
        campaign_id=campaign.id,
        db=db_session,
    )

    # Must remain RUNNING because r2 has a scheduled follow-up
    assert status_result == CampaignStatus.RUNNING.value
    await db_session.refresh(campaign)
    assert campaign.status == CampaignStatus.RUNNING.value


@pytest.mark.asyncio
async def test_campaign_status_summary_endpoint(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """M21.2 Fix 5: GET /companies/{company_id}/campaigns/summary
    aggregates company-wide campaign counts grouped by status.
    """
    token = await register_and_login(async_client, "owner_summary_test@company.com")
    company_id = await create_company_helper(async_client, token, "Summary Co")
    account_id = await create_email_account_helper(async_client, token, company_id, email_address="summary_sender_acct@company.com")

    # Create campaigns across multiple statuses
    c_draft = Campaign(company_id=company_id, email_account_id=account_id, name="Draft C", status=CampaignStatus.DRAFT.value)
    c_running = Campaign(company_id=company_id, email_account_id=account_id, name="Running C", status=CampaignStatus.RUNNING.value)
    c_queued = Campaign(company_id=company_id, email_account_id=account_id, name="Queued C", status=CampaignStatus.QUEUED.value)
    c_sched = Campaign(company_id=company_id, email_account_id=account_id, name="Sched C", status=CampaignStatus.SCHEDULED.value)
    c_comp = Campaign(company_id=company_id, email_account_id=account_id, name="Comp C", status=CampaignStatus.COMPLETED.value)
    c_arch = Campaign(company_id=company_id, email_account_id=account_id, name="Arch C", status=CampaignStatus.ARCHIVED.value)

    db_session.add_all([c_draft, c_running, c_queued, c_sched, c_comp, c_arch])
    await db_session.commit()

    resp = await async_client.get(
        f"/api/v1/companies/{company_id}/campaigns/summary",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    summary = resp.json()

    # Active = RUNNING (1) + QUEUED (1) = 2
    assert summary["active_count"] == 2
    assert summary["scheduled_count"] == 1
    assert summary["draft_count"] == 1
    assert summary["completed_count"] == 1
    assert summary["total_count"] == 5  # Excluding ARCHIVED


@pytest.mark.asyncio
async def test_references_header_reply_candidate_attribution(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """M21.2 Fix 6: Inbound reply where in_reply_to is missing/empty
    is loaded via References-header SQL candidate matching and attributed to the exact step.
    """
    token = await register_and_login(async_client, "owner_ref_test@company.com")
    company_id = await create_company_helper(async_client, token, "Ref Attribution Co")
    account_id = await create_email_account_helper(async_client, token, company_id, email_address="ref_sender_acct@company.com")

    campaign = Campaign(
        company_id=company_id,
        email_account_id=account_id,
        name="References Header Attribution Campaign",
        subject="Ref Subject",
        body_html="<p>Test</p>",
        status=CampaignStatus.RUNNING.value,
    )
    db_session.add(campaign)
    await db_session.flush()

    s1 = CampaignStep(campaign_id=campaign.id, step_number=1, subject="Ref S1", body_html="S1", delay_hours=0, is_active=True)
    recip = CampaignRecipient(
        campaign_id=campaign.id,
        email="ref_lead@client.com",
        current_step_number=1,
        status=CampaignRecipientStatus.SENT.value,
        stopped_reason=None,
    )
    db_session.add_all([s1, recip])
    await db_session.flush()

    deliv = CampaignDelivery(
        campaign_id=campaign.id,
        recipient_id=recip.id,
        step_id=s1.id,
        status=CampaignDeliveryStatus.SENT.value,
        message_id="<step1_unique_delivery_id_999@company.com>",
        sent_at=datetime(2026, 11, 4, 8, 0, tzinfo=timezone.utc),
    )
    db_session.add(deliv)

    # Inbound email with In-Reply-To as None, but References has the message ID!
    inbound_email = Email(
        company_id=company_id,
        email_account_id=account_id,
        direction=EmailDirection.INCOMING.value,
        sender="ref_lead@client.com",
        recipients=["ref_sender_acct@company.com"],
        subject="Re: Ref Subject",
        in_reply_to=None,  # Intentionally None!
        references_header="<some_old_msg_id> <step1_unique_delivery_id_999@company.com>",
        message_id="<inbound_reply_ref_only@client.com>",
        sent_at=datetime(2026, 11, 4, 8, 30, tzinfo=timezone.utc),
        received_at=datetime(2026, 11, 4, 8, 30, tzinfo=timezone.utc),
    )
    db_session.add(inbound_email)
    await db_session.commit()

    # Query analytics API
    resp = await async_client.get(
        f"/api/v1/companies/{company_id}/campaigns/{campaign.id}/analytics",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    analytics = resp.json()

    assert analytics["unique_replied_count"] == 1
    assert analytics["steps"][0]["replied_count"] == 1
    assert analytics["steps"][0]["reply_rate"] == 100.0
