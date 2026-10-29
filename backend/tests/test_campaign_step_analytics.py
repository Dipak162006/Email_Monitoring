from datetime import datetime, timezone
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
from app.modules.emails.models import EmailThread


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
    assert s1["delivery_rate"] == 60.0 # 3/5 * 100 = 60.0%
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
    assert s2["delivery_rate"] == 33.3 # 1/3 * 100 = 33.3%
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
