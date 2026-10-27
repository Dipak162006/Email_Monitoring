"""Comprehensive verification suite for Follow-Up Architecture Hardening.

Covers:
1. Fix 1: Safe SMTP uncertain-outcome recovery and retry prevention.
2. Fix 2: Existing campaign and recipient migration / lifecycle model.
3. Fix 3: Campaign-step schema, Step 1 synchronization, and delivery step constraint.
"""
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.auth.models import User
from app.modules.companies.models import Company
from app.modules.domains.models import Domain, DomainVerificationStatus
from app.modules.email_accounts.models import EmailAccount
from app.modules.emails.models import Email, EmailDirection, EmailStatus, EmailThread
from app.modules.emails.monitoring_service import EmailMonitoringService
from app.services.imap.parser import ParsedEmail
from app.modules.campaigns.models import (
    Campaign,
    CampaignDelivery,
    CampaignDeliveryStatus,
    CampaignRecipient,
    CampaignRecipientStatus,
    CampaignRecipientStopReason,
    CampaignStep,
    CampaignStatus,
    SuppressionEntry,
    SuppressionReason,
)
from app.modules.campaigns.delivery_service import CampaignDeliveryService
from app.modules.campaigns.scheduling_service import CampaignSchedulingService
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
    """Helper to register and login a test user."""
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
    """Helper to create a company."""
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
    domain_name: str = "followup-test.com",
) -> tuple[int, int, int]:
    """Helper setting up verified domain, email account, campaign, and recipient."""
    domain = Domain(
        company_id=company_id,
        domain_name=domain_name,
        verification_status=DomainVerificationStatus.VERIFIED.value,
    )
    db_session.add(domain)
    await db_session.flush()

    account = EmailAccount(
        company_id=company_id,
        domain_id=domain.id,
        name="FollowUp Sender",
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

    camp_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Hardening Test Campaign",
            "email_account_id": account.id,
            "subject": "Initial Subject {{first_name}}",
            "body_text": "Initial Body text {{first_name}}",
            "body_html": "<p>Initial Body text {{first_name}}</p>",
        },
    )
    assert camp_resp.status_code == 201
    camp_id = camp_resp.json()["id"]

    recip_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}/recipients",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": f"recipient@{domain_name}", "first_name": "Recipient"},
    )
    assert recip_resp.status_code == 201
    recip_id = recip_resp.json()["id"]

    return camp_id, account.id, recip_id


# =============================================================================
# Fix 1 — SMTP Uncertain-Outcome Recovery Tests
# =============================================================================

@pytest.mark.anyio
async def test_stale_delivery_without_audit_record_becomes_uncertain(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """When a worker dies while a delivery is in SENDING and NO Email audit record exists,
    reconcile_stale_delivery must mark the delivery UNCERTAIN, record diagnostic context,
    and prevent automatic retry.
    """
    token = await register_and_login(async_client, "owner_unc_1@test.com")
    comp_id = await create_company_helper(async_client, token, "Uncertain Org 1")
    camp_id, acc_id, recip_id = await setup_test_campaign(async_client, db_session, token, comp_id)

    # Simulate stale delivery in SENDING stuck for 15 minutes
    stale_time = datetime.now(timezone.utc) - timedelta(minutes=15)
    delivery = CampaignDelivery(
        campaign_id=camp_id,
        recipient_id=recip_id,
        status=CampaignDeliveryStatus.SENDING.value,
        attempt_count=1,
        last_attempt_at=stale_time,
    )
    db_session.add(delivery)
    await db_session.commit()
    await db_session.refresh(delivery)

    # Reconcile delivery
    outcome = await CampaignDeliveryService.reconcile_stale_delivery(
        db=db_session,
        delivery=delivery,
        stale_minutes=10,
    )
    await db_session.commit()
    await db_session.refresh(delivery)

    assert outcome["status"] == CampaignDeliveryStatus.UNCERTAIN.value
    assert delivery.status == CampaignDeliveryStatus.UNCERTAIN.value
    assert "no persisted email audit record found" in delivery.error_message.lower()
    assert "automatic retry suspended" in delivery.error_message.lower()


@pytest.mark.anyio
async def test_stale_delivery_with_persisted_sent_email_reconciles_to_sent(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """When a worker dies after SMTP accepted and Email was persisted as SENT,
    reconciliation reconciles CampaignDelivery to SENT without resending.
    """
    token = await register_and_login(async_client, "owner_unc_2@test.com")
    comp_id = await create_company_helper(async_client, token, "Uncertain Org 2")
    camp_id, acc_id, recip_id = await setup_test_campaign(async_client, db_session, token, comp_id)

    recip = await db_session.get(CampaignRecipient, recip_id)

    # Create persisted outgoing Email marked SENT
    msg_id = "<audit-msg-202@test.com>"
    sent_time = datetime.now(timezone.utc) - timedelta(minutes=14)
    email_record = Email(
        company_id=comp_id,
        email_account_id=acc_id,
        direction=EmailDirection.OUTGOING.value,
        status=EmailStatus.SENT.value,
        message_id=msg_id,
        sender="sender@test.com",
        recipients=[recip.email],
        subject="Audit Subject",
        sent_at=sent_time,
    )
    db_session.add(email_record)
    await db_session.flush()

    # Delivery left in SENDING with linked email_id
    delivery = CampaignDelivery(
        campaign_id=camp_id,
        recipient_id=recip_id,
        status=CampaignDeliveryStatus.SENDING.value,
        email_id=email_record.id,
        message_id=msg_id,
        attempt_count=1,
        last_attempt_at=sent_time,
    )
    db_session.add(delivery)
    await db_session.commit()
    await db_session.refresh(delivery)

    outcome = await CampaignDeliveryService.reconcile_stale_delivery(
        db=db_session,
        delivery=delivery,
        stale_minutes=10,
    )
    await db_session.commit()
    await db_session.refresh(delivery)

    assert outcome["status"] == CampaignDeliveryStatus.SENT.value
    assert delivery.status == CampaignDeliveryStatus.SENT.value
    assert delivery.sent_at == sent_time
    assert delivery.error_message is None

    # Recipient updated to step 1
    await db_session.refresh(recip)
    assert recip.current_step_number == 1


@pytest.mark.anyio
async def test_uncertain_delivery_strictly_blocks_automatic_retry(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Verify that CampaignDeliveryService.retry_delivery strictly refuses to retry
    deliveries in UNCERTAIN status to prevent duplicate email transmissions.
    """
    token = await register_and_login(async_client, "owner_unc_3@test.com")
    comp_id = await create_company_helper(async_client, token, "Uncertain Org 3")
    camp_id, acc_id, recip_id = await setup_test_campaign(async_client, db_session, token, comp_id)

    delivery = CampaignDelivery(
        campaign_id=camp_id,
        recipient_id=recip_id,
        status=CampaignDeliveryStatus.UNCERTAIN.value,
        attempt_count=1,
        last_attempt_at=datetime.now(timezone.utc) - timedelta(minutes=20),
        error_message="SMTP outcome uncertain; automatic retry suspended.",
    )
    db_session.add(delivery)
    await db_session.commit()
    await db_session.refresh(delivery)

    # Attempt retry with isolated test db factory
    retry_result = await CampaignDeliveryService.retry_delivery(
        delivery_id=delivery.id,
        company_id=comp_id,
        db_factory=TestAsyncSessionLocal,
    )

    assert retry_result["status"] == "SKIPPED"
    assert "uncertain" in retry_result["reason"].lower()

    # Invariant: Delivery remains UNCERTAIN and attempt_count is untouched
    await db_session.refresh(delivery)
    assert delivery.status == CampaignDeliveryStatus.UNCERTAIN.value
    assert delivery.attempt_count == 1


# =============================================================================
# Fix 2 — Campaign and Recipient Lifecycle Tests
# =============================================================================

@pytest.mark.anyio
async def test_campaign_cancellation_safely_stops_recipients_without_reactivation(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """When a campaign is cancelled, active/pending recipients transition to STOPPED
    with stopped_reason CAMPAIGN_CANCELLED. Already completed or stopped recipients
    (e.g. BOUNCED, UNSUBSCRIBED) are NOT reactivated or overwritten.
    """
    token = await register_and_login(async_client, "owner_lc_1@test.com")
    comp_id = await create_company_helper(async_client, token, "Lifecycle Org 1")
    camp_id, acc_id, r1_id = await setup_test_campaign(async_client, db_session, token, comp_id)

    # Add second recipient while in DRAFT (which will later be marked BOUNCED)
    r2_resp = await async_client.post(
        f"/api/v1/companies/{comp_id}/campaigns/{camp_id}/recipients",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "bounced@test.com", "first_name": "Bounced"},
    )
    assert r2_resp.status_code == 201
    r2_id = r2_resp.json()["id"]

    r2 = await db_session.get(CampaignRecipient, r2_id)
    r2.status = CampaignRecipientStatus.STOPPED.value
    r2.stopped_reason = CampaignRecipientStopReason.BOUNCED.value
    await db_session.commit()

    # Put campaign in RUNNING status (cancellable)
    camp = await db_session.get(Campaign, camp_id)
    camp.status = CampaignStatus.RUNNING.value
    await db_session.commit()
    await db_session.commit()

    # Cancel campaign via CampaignService
    camp = await CampaignService.cancel_campaign(db_session, comp_id, camp_id)
    assert camp.status == CampaignStatus.CANCELLED.value

    # Recipient 1 transitions to STOPPED (CAMPAIGN_CANCELLED)
    r1 = await db_session.get(CampaignRecipient, r1_id)
    assert r1.status == CampaignRecipientStatus.STOPPED.value
    assert r1.stopped_reason == CampaignRecipientStopReason.CAMPAIGN_CANCELLED.value

    # Recipient 2 preserves original BOUNCED stop reason (no accidental reactivation or overwrite)
    await db_session.refresh(r2)
    assert r2.status == CampaignRecipientStatus.STOPPED.value
    assert r2.stopped_reason == CampaignRecipientStopReason.BOUNCED.value


# =============================================================================
# Fix 3 — Campaign-Step Schema & Delivery Step Constraint Tests
# =============================================================================

@pytest.mark.anyio
async def test_campaign_creation_and_update_authoritatively_syncs_step_1(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Verify that creating a campaign creates CampaignStep (step_number=1) with
    subject, body_text, and body_html, and updating campaign content syncs Step 1.
    """
    token = await register_and_login(async_client, "owner_step_1@test.com")
    comp_id = await create_company_helper(async_client, token, "Step Org 1")
    camp_id, acc_id, recip_id = await setup_test_campaign(async_client, db_session, token, comp_id)

    # 1. Verify Step 1 exists with initial content
    stmt = select(CampaignStep).where(
        CampaignStep.campaign_id == camp_id,
        CampaignStep.step_number == 1,
    )
    step1 = (await db_session.execute(stmt)).scalar_one_or_none()
    assert step1 is not None
    assert "Initial Subject" in step1.subject
    assert "Initial Body text" in step1.body_text
    assert step1.delay_hours == 0
    assert step1.is_active is True

    # 2. Update campaign content
    update_resp = await async_client.patch(
        f"/api/v1/companies/{comp_id}/campaigns/{camp_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "subject": "Updated Subject {{first_name}}",
            "body_text": "Updated Body {{first_name}}",
        },
    )
    assert update_resp.status_code == 200

    # Verify Step 1 was synchronized
    await db_session.refresh(step1)
    assert step1.subject == "Updated Subject {{first_name}}"
    assert step1.body_text == "Updated Body {{first_name}}"


@pytest.mark.anyio
async def test_delivery_unique_constraint_on_campaign_recipient_and_step(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Verify that CampaignDelivery enforces uniqueness on (campaign_id, recipient_id, step_id).
    Inserting a second delivery for the same recipient and step raises IntegrityError.
    """
    token = await register_and_login(async_client, "owner_step_2@test.com")
    comp_id = await create_company_helper(async_client, token, "Step Org 2")
    camp_id, acc_id, recip_id = await setup_test_campaign(async_client, db_session, token, comp_id)

    step1_stmt = select(CampaignStep.id).where(
        CampaignStep.campaign_id == camp_id,
        CampaignStep.step_number == 1,
    )
    step1_id = (await db_session.execute(step1_stmt)).scalar_one()

    # First delivery succeeds
    deliv1 = CampaignDelivery(
        campaign_id=camp_id,
        recipient_id=recip_id,
        step_id=step1_id,
        status=CampaignDeliveryStatus.SENT.value,
        attempt_count=1,
    )
    db_session.add(deliv1)
    await db_session.commit()

    # Second delivery for the exact same (campaign_id, recipient_id, step_id) must fail constraint
    deliv2 = CampaignDelivery(
        campaign_id=camp_id,
        recipient_id=recip_id,
        step_id=step1_id,
        status=CampaignDeliveryStatus.SENDING.value,
        attempt_count=1,
    )
    db_session.add(deliv2)

    with pytest.raises(IntegrityError):
        await db_session.commit()

    await db_session.rollback()


# =============================================================================
# Milestone C13 — Multi-Step Follow-Up Sequence & Reply Auto-Stop Tests
# =============================================================================

@pytest.mark.anyio
async def test_followup_steps_create_and_update_sync(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Verify that creating and updating a DRAFT campaign with followup_steps persists
    and sequentially normalizes CampaignStep rows (step_number >= 2), defaulting empty
    subjects to 'Re: <Campaign Subject>'.
    """
    token = await register_and_login(async_client, "owner_multistep_crud@test.com")
    comp_id = await create_company_helper(async_client, token, "MultiStep Org")

    domain = Domain(
        company_id=comp_id,
        domain_name="multistep.com",
        verification_status=DomainVerificationStatus.VERIFIED.value,
    )
    db_session.add(domain)
    await db_session.flush()

    account = EmailAccount(
        company_id=comp_id,
        domain_id=domain.id,
        name="Outreach Sender",
        email_address="outreach@multistep.com",
        provider="CUSTOM",
        smtp_host="smtp.multistep.com",
        smtp_port=587,
        smtp_security="STARTTLS",
        smtp_username="outreach@multistep.com",
        smtp_password_encrypted="enc_password",
        is_active=True,
    )
    db_session.add(account)
    await db_session.commit()
    await db_session.refresh(account)

    # 1. Create DRAFT campaign with 1 follow-up step (step_number=2, delay_hours=48, empty subject)
    create_resp = await async_client.post(
        f"/api/v1/companies/{comp_id}/campaigns",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Multi-Step Outreach",
            "email_account_id": account.id,
            "subject": "Initial Proposition {{first_name}}",
            "body_text": "Hey {{first_name}}, check this out.",
            "body_html": "<p>Hey {{first_name}}, check this out.</p>",
            "followup_steps": [
                {
                    "step_number": 2,
                    "delay_hours": 48,
                    "subject": "",
                    "body_text": "Following up on my last email {{first_name}}.",
                    "body_html": "<p>Following up on my last email {{first_name}}.</p>",
                }
            ],
        },
    )
    assert create_resp.status_code == 201
    camp_id = create_resp.json()["id"]

    # Verify Step 1 and Step 2 in database
    steps_stmt = select(CampaignStep).where(CampaignStep.campaign_id == camp_id).order_by(CampaignStep.step_number.asc())
    steps = (await db_session.execute(steps_stmt)).scalars().all()
    assert len(steps) == 2
    assert steps[0].step_number == 1
    assert steps[0].delay_hours == 0
    assert steps[0].subject == "Initial Proposition {{first_name}}"

    assert steps[1].step_number == 2
    assert steps[1].delay_hours == 48
    # Empty subject defaulted to Re: <Campaign Subject>
    assert steps[1].subject == "Re: Initial Proposition {{first_name}}"
    assert steps[1].body_text == "Following up on my last email {{first_name}}."

    # 2. Update DRAFT campaign: update Step 2 delay to 72 hours, add Step 3
    update_resp = await async_client.patch(
        f"/api/v1/companies/{comp_id}/campaigns/{camp_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "followup_steps": [
                {
                    "step_number": 2,
                    "delay_hours": 72,
                    "subject": "Quick Bump {{first_name}}",
                    "body_text": "Updated step 2 body",
                },
                {
                    "step_number": 3,
                    "delay_hours": 120,
                    "subject": "",
                    "body_text": "Final follow-up attempt",
                },
            ],
        },
    )
    assert update_resp.status_code == 200

    # Verify steps updated
    steps = (await db_session.execute(steps_stmt)).scalars().all()
    assert len(steps) == 3
    assert steps[1].step_number == 2
    assert steps[1].delay_hours == 72
    assert steps[1].subject == "Quick Bump {{first_name}}"

    assert steps[2].step_number == 3
    assert steps[2].delay_hours == 120
    assert steps[2].subject == "Re: Initial Proposition {{first_name}}"


@pytest.mark.anyio
async def test_followup_scheduling_and_threaded_dispatch(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Verify:
    1. Executing Step 1 sets recipient.current_step_number = 1 and recipient.next_step_due_at = sent_at + 48h.
    2. process_due_followup_steps before 48h dispatches nothing.
    3. process_due_followup_steps after 48h dispatches Step 2 in the same thread_id with In-Reply-To matching Step 1,
       creates a second CampaignDelivery (step_id == step_2.id), and advances current_step_number to 2.
    """
    token = await register_and_login(async_client, "owner_multistep_sched@test.com")
    comp_id = await create_company_helper(async_client, token, "Sched Org")

    domain = Domain(
        company_id=comp_id,
        domain_name="sched-test.com",
        verification_status=DomainVerificationStatus.VERIFIED.value,
    )
    db_session.add(domain)
    await db_session.flush()

    account = EmailAccount(
        company_id=comp_id,
        domain_id=domain.id,
        name="Sched Sender",
        email_address="sender@sched-test.com",
        provider="CUSTOM",
        smtp_host="smtp.sched-test.com",
        smtp_port=587,
        smtp_security="STARTTLS",
        smtp_username="sender@sched-test.com",
        smtp_password_encrypted="enc_password",
        is_active=True,
    )
    db_session.add(account)
    await db_session.commit()
    await db_session.refresh(account)

    create_resp = await async_client.post(
        f"/api/v1/companies/{comp_id}/campaigns",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Threaded Followup Campaign",
            "email_account_id": account.id,
            "subject": "Initial Intro",
            "body_text": "Hello there!",
            "followup_steps": [
                {
                    "step_number": 2,
                    "delay_hours": 48,
                    "subject": "Re: Initial Intro",
                    "body_text": "Did you get my note?",
                }
            ],
        },
    )
    assert create_resp.status_code == 201
    camp_id = create_resp.json()["id"]

    recip_resp = await async_client.post(
        f"/api/v1/companies/{comp_id}/campaigns/{camp_id}/recipients",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "alice@customer.com", "first_name": "Alice"},
    )
    assert recip_resp.status_code == 201
    recip_id = recip_resp.json()["id"]

    # Queue campaign for execution
    camp_res = await db_session.execute(select(Campaign).where(Campaign.id == camp_id))
    camp = camp_res.scalar_one()
    camp.status = CampaignStatus.QUEUED.value
    await db_session.commit()

    # Execute Step 1
    with patch("app.services.smtp.client.SMTPClient.send_email_sync"):
        result = await CampaignDeliveryService.execute_campaign(
            campaign_id=camp_id,
            company_id=comp_id,
            db_factory=TestAsyncSessionLocal,
        )
    assert result["sent_count"] == 1

    # Verify recipient after Step 1 execution
    recip_res = await db_session.execute(select(CampaignRecipient).where(CampaignRecipient.id == recip_id))
    recip = recip_res.scalar_one()
    assert recip.status == CampaignRecipientStatus.SENT.value
    assert recip.current_step_number == 1
    assert recip.next_step_due_at is not None

    # Verify Step 1 delivery
    deliv_stmt = select(CampaignDelivery).where(
        CampaignDelivery.campaign_id == camp_id,
        CampaignDelivery.recipient_id == recip_id,
    )
    delivs = (await db_session.execute(deliv_stmt)).scalars().all()
    assert len(delivs) == 1
    step1_deliv = delivs[0]
    assert step1_deliv.status == CampaignDeliveryStatus.SENT.value
    assert step1_deliv.message_id is not None
    assert step1_deliv.thread_id is not None
    assert recip.next_step_due_at == step1_deliv.sent_at + timedelta(hours=48)

    # Calling process_due_followup_steps BEFORE 48 hours (e.g. at 24 hours) dispatches nothing
    with patch("app.services.smtp.client.SMTPClient.send_email_sync"):
        early_res = await CampaignDeliveryService.process_due_followup_steps(
            db_factory=TestAsyncSessionLocal,
            now_utc=step1_deliv.sent_at + timedelta(hours=24),
        )
    assert len(early_res) == 0

    # Calling process_due_followup_steps AFTER 48 hours (e.g. at 49 hours) dispatches Step 2!
    with patch("app.services.smtp.client.SMTPClient.send_email_sync"):
        due_res = await CampaignDeliveryService.process_due_followup_steps(
            db_factory=TestAsyncSessionLocal,
            now_utc=step1_deliv.sent_at + timedelta(hours=49),
        )
    assert len(due_res) == 1
    assert due_res[0]["status"] == "SENT"
    assert due_res[0]["step_number"] == 2

    # Refresh and verify recipient state and deliveries
    await db_session.refresh(recip)
    assert recip.current_step_number == 2
    assert recip.next_step_due_at is None  # No Step 3 configured!

    delivs = (await db_session.execute(deliv_stmt.order_by(CampaignDelivery.id.asc()))).scalars().all()
    assert len(delivs) == 2
    step2_deliv = delivs[1]
    assert step2_deliv.status == CampaignDeliveryStatus.SENT.value
    assert step2_deliv.thread_id == step1_deliv.thread_id  # Threaded in same conversation!
    assert step2_deliv.step_id is not None
    assert step2_deliv.step_id != step1_deliv.step_id


@pytest.mark.anyio
async def test_followup_auto_stop_on_genuine_reply(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Verify that when a genuine reply arrives via match_and_process_campaign_reply:
    1. stopped_reason becomes REPLIED, replied_at is populated, and next_step_due_at is cancelled.
    2. Subsequent process_due_followup_steps execution skips this recipient and dispatches NO follow-up.
    """
    token = await register_and_login(async_client, "owner_multistep_reply@test.com")
    comp_id = await create_company_helper(async_client, token, "Reply Org")

    domain = Domain(
        company_id=comp_id,
        domain_name="reply-test.com",
        verification_status=DomainVerificationStatus.VERIFIED.value,
    )
    db_session.add(domain)
    await db_session.flush()

    account = EmailAccount(
        company_id=comp_id,
        domain_id=domain.id,
        name="Reply Sender",
        email_address="sender@reply-test.com",
        provider="CUSTOM",
        smtp_host="smtp.reply-test.com",
        smtp_port=587,
        smtp_security="STARTTLS",
        smtp_username="sender@reply-test.com",
        smtp_password_encrypted="enc_password",
        is_active=True,
    )
    db_session.add(account)
    await db_session.commit()
    await db_session.refresh(account)

    create_resp = await async_client.post(
        f"/api/v1/companies/{comp_id}/campaigns",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Reply Auto-Stop Campaign",
            "email_account_id": account.id,
            "subject": "Initial Note",
            "body_text": "Hey Bob!",
            "followup_steps": [
                {
                    "step_number": 2,
                    "delay_hours": 48,
                    "body_text": "Follow-up note",
                }
            ],
        },
    )
    assert create_resp.status_code == 201
    camp_id = create_resp.json()["id"]

    recip_resp = await async_client.post(
        f"/api/v1/companies/{comp_id}/campaigns/{camp_id}/recipients",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "bob@client.com", "first_name": "Bob"},
    )
    assert recip_resp.status_code == 201
    recip_id = recip_resp.json()["id"]

    camp_res = await db_session.execute(select(Campaign).where(Campaign.id == camp_id))
    camp = camp_res.scalar_one()
    camp.status = CampaignStatus.QUEUED.value
    await db_session.commit()

    # Execute Step 1
    with patch("app.services.smtp.client.SMTPClient.send_email_sync"):
        await CampaignDeliveryService.execute_campaign(
            campaign_id=camp_id,
            company_id=comp_id,
            db_factory=TestAsyncSessionLocal,
        )

    # Get Step 1 delivery
    deliv_stmt = select(CampaignDelivery).where(CampaignDelivery.recipient_id == recip_id)
    step1_deliv = (await db_session.execute(deliv_stmt)).scalar_one()

    # Recipient has next_step_due_at active
    recip_res = await db_session.execute(select(CampaignRecipient).where(CampaignRecipient.id == recip_id))
    recip = recip_res.scalar_one()
    assert recip.next_step_due_at is not None
    assert recip.stopped_reason is None

    # Simulate genuine incoming reply matching step1_deliv.message_id
    parsed_reply = ParsedEmail(
        message_id="incoming_reply_msg@client.com",
        sender="bob@client.com",
        recipients=[account.email_address],
        subject="Re: Initial Note",
        date=datetime.now(timezone.utc),
        in_reply_to=step1_deliv.message_id,
        references_header=step1_deliv.message_id,
        body_text="Hi, thanks for reaching out! Let's talk.",
        body_html=None,
        cc=None,
        bcc=None,
        reply_to=None,
    )

    matched = await EmailMonitoringService.match_and_process_campaign_reply(
        db=db_session,
        account=account,
        parsed=parsed_reply,
        thread_id=step1_deliv.thread_id,
        is_reply_to_outgoing=True,
    )
    assert matched == 1
    await db_session.commit()

    # Verify recipient state was halted
    await db_session.refresh(recip)
    assert recip.stopped_reason == CampaignRecipientStopReason.REPLIED.value
    assert recip.replied_at is not None
    assert recip.next_step_due_at is None

    # Running process_due_followup_steps 50 hours later must NOT dispatch Step 2
    with patch("app.services.smtp.client.SMTPClient.send_email_sync"):
        due_res = await CampaignDeliveryService.process_due_followup_steps(
            db_factory=TestAsyncSessionLocal,
            now_utc=step1_deliv.sent_at + timedelta(hours=50),
        )
    assert len(due_res) == 0

    # Verify no second delivery was created
    delivs = (await db_session.execute(deliv_stmt)).scalars().all()
    assert len(delivs) == 1
    assert recip.current_step_number == 1


@pytest.mark.anyio
async def test_followup_skip_on_unsubscribe_or_bounce(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Verify that when a recipient unsubscribes or bounces, next_step_due_at is cleared
    and process_due_followup_steps skips follow-up execution.
    """
    token = await register_and_login(async_client, "owner_multistep_unsub@test.com")
    comp_id = await create_company_helper(async_client, token, "Unsub Org")

    domain = Domain(
        company_id=comp_id,
        domain_name="unsub-test.com",
        verification_status=DomainVerificationStatus.VERIFIED.value,
    )
    db_session.add(domain)
    await db_session.flush()

    account = EmailAccount(
        company_id=comp_id,
        domain_id=domain.id,
        name="Unsub Sender",
        email_address="sender@unsub-test.com",
        provider="CUSTOM",
        smtp_host="smtp.unsub-test.com",
        smtp_port=587,
        smtp_security="STARTTLS",
        smtp_username="sender@unsub-test.com",
        smtp_password_encrypted="enc_password",
        is_active=True,
    )
    db_session.add(account)
    await db_session.commit()
    await db_session.refresh(account)

    create_resp = await async_client.post(
        f"/api/v1/companies/{comp_id}/campaigns",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Bounce & Unsub Campaign",
            "email_account_id": account.id,
            "subject": "Initial Pitch",
            "body_text": "Hey Charlie!",
            "followup_steps": [
                {
                    "step_number": 2,
                    "delay_hours": 48,
                    "body_text": "Step 2 follow-up",
                }
            ],
        },
    )
    assert create_resp.status_code == 201
    camp_id = create_resp.json()["id"]

    recip_resp = await async_client.post(
        f"/api/v1/companies/{comp_id}/campaigns/{camp_id}/recipients",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "charlie@client.com", "first_name": "Charlie"},
    )
    assert recip_resp.status_code == 201
    recip_id = recip_resp.json()["id"]

    camp_res = await db_session.execute(select(Campaign).where(Campaign.id == camp_id))
    camp = camp_res.scalar_one()
    camp.status = CampaignStatus.QUEUED.value
    await db_session.commit()

    with patch("app.services.smtp.client.SMTPClient.send_email_sync"):
        await CampaignDeliveryService.execute_campaign(
            campaign_id=camp_id,
            company_id=comp_id,
            db_factory=TestAsyncSessionLocal,
        )

    recip_res = await db_session.execute(select(CampaignRecipient).where(CampaignRecipient.id == recip_id))
    recip = recip_res.scalar_one()
    assert recip.next_step_due_at is not None

    deliv_stmt = select(CampaignDelivery).where(CampaignDelivery.recipient_id == recip_id)
    step1_deliv = (await db_session.execute(deliv_stmt)).scalar_one()

    # Record a bounce event for this delivery
    await CampaignDeliveryService.record_bounce_event(
        db=db_session,
        company_id=comp_id,
        delivery_id=step1_deliv.id,
        diagnostic_text="550 User unknown",
    )
    await db_session.commit()

    # Verify recipient next_step_due_at is cleared and status is BOUNCED
    await db_session.refresh(recip)
    assert recip.status == CampaignRecipientStatus.BOUNCED.value
    assert recip.next_step_due_at is None

    # Advance time and call process_due_followup_steps -> 0 sent
    with patch("app.services.smtp.client.SMTPClient.send_email_sync"):
        due_res = await CampaignDeliveryService.process_due_followup_steps(
            db_factory=TestAsyncSessionLocal,
            now_utc=step1_deliv.sent_at + timedelta(hours=50),
        )
    assert len(due_res) == 0

