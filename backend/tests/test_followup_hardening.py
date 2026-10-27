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
from app.modules.emails.models import Email, EmailDirection, EmailStatus
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
from tests.conftest import TestAsyncSessionLocal


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
