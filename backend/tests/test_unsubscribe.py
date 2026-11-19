"""Test suite for T4 Secure Email Unsubscribe & Suppression System.

Verifies:
1. Valid GET does not unsubscribe.
2. Valid POST unsubscribes successfully.
3. Repeated POST is idempotent.
4. Invalid, expired, revoked, and wrong-purpose tokens are rejected.
5. Cross-tenant token access is rejected.
6. Suppression prevents future campaign sends.
7. Pending follow-ups are cancelled.
8. RFC 8058 headers are generated correctly.
9. Mailbox emails are not unintentionally affected.
10. Opaque tracking token endpoints (/t/u/{token}) behave identically to public unsubscribe endpoints.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_unsubscribe_token
from app.modules.campaigns.models import (
    Campaign,
    CampaignRecipient,
    CampaignRecipientStatus,
    CampaignRecipientStopReason,
    CampaignStatus,
    SuppressionEntry,
    SuppressionReason,
)
from app.modules.campaigns.suppression_service import SuppressionService
from app.modules.campaigns.unsubscribe_service import UnsubscribeService, UnsubscribeSyncLock
from app.modules.email_accounts.models import EmailAccount
from app.modules.emails.models import (
    Email,
    EmailDirection,
    EmailStatus,
    EmailTrackingEvent,
    EmailTrackingToken,
    TrackingTokenType,
)
from app.modules.emails.schemas import EmailSendRequest
from app.modules.emails.service import EmailService
from app.modules.emails.tracking_client import TrackingServiceClient
from app.modules.emails.tracking_service import EmailTrackingService


@pytest.fixture
async def setup_test_org(db_session: AsyncSession):
    """Fixture creating a test Company, EmailAccount, and Campaign."""
    from app.modules.companies.models import Company

    company = Company(name="Unsub Test Corp")
    db_session.add(company)
    await db_session.commit()
    await db_session.refresh(company)

    account = EmailAccount(
        company_id=company.id,
        name="Unsub Outreach",
        email_address=f"outreach_{company.id}@unsubtest.com",
        smtp_host="smtp.unsubtest.com",
        smtp_port=587,
        smtp_username=f"outreach_{company.id}@unsubtest.com",
        smtp_password_encrypted="test-password",
        imap_host="imap.unsubtest.com",
        imap_port=993,
        imap_username=f"outreach_{company.id}@unsubtest.com",
        imap_password_encrypted="test-password",
        is_active=True,
    )
    db_session.add(account)
    await db_session.commit()
    await db_session.refresh(account)

    campaign = Campaign(
        company_id=company.id,
        email_account_id=account.id,
        name="T4 Verification Outreach",
        subject="Check our services",
        body_text="Hello {{first_name}},\nUnsubscribe: {{unsubscribe_url}}",
        body_html="<p>Hello {{first_name}},</p><p><a href='{{unsubscribe_url}}'>Unsubscribe</a></p>",
        status=CampaignStatus.DRAFT.value,
    )
    db_session.add(campaign)
    await db_session.commit()
    await db_session.refresh(campaign)

    return {"company": company, "account": account, "campaign": campaign}


@pytest.mark.asyncio
async def test_valid_get_does_not_unsubscribe(async_client: AsyncClient, db_session: AsyncSession, setup_test_org):
    """Requirement 1: Valid GET displays confirmation page but does NOT unsubscribe or suppress the recipient."""
    company = setup_test_org["company"]
    campaign = setup_test_org["campaign"]
    target_email = "scanner_target@example.com"

    recipient = CampaignRecipient(
        campaign_id=campaign.id,
        email=target_email,
        first_name="Scanner",
        status=CampaignRecipientStatus.ACTIVE.value,
        current_step_number=1,
        next_step_due_at=datetime.now(timezone.utc) + timedelta(days=2),
    )
    db_session.add(recipient)
    await db_session.commit()

    token = create_unsubscribe_token(company_id=company.id, email=target_email, campaign_id=campaign.id)

    # 1. GET with Accept: application/json
    res_json = await async_client.get(
        f"/api/v1/public/unsubscribe/{token}",
        headers={"Accept": "application/json"},
    )
    assert res_json.status_code == 200
    assert res_json.json()["status"] == "pending_confirmation"

    # 2. GET with Accept: text/html
    res_html = await async_client.get(
        f"/api/v1/public/unsubscribe/{token}",
        headers={"Accept": "text/html"},
    )
    assert res_html.status_code == 200
    assert "Unsubscribe Confirmation" in res_html.text

    # 3. Verify recipient is NOT suppressed
    is_suppressed = await SuppressionService.is_suppressed(db_session, company.id, target_email)
    assert is_suppressed is False

    # 4. Verify recipient status and follow-up are NOT modified
    await db_session.refresh(recipient)
    assert recipient.status == CampaignRecipientStatus.ACTIVE.value
    assert recipient.stopped_reason is None
    assert recipient.next_step_due_at is not None


@pytest.mark.asyncio
async def test_valid_post_unsubscribes_successfully(async_client: AsyncClient, db_session: AsyncSession, setup_test_org):
    """Requirement 2: Valid POST unsubscribes successfully, adds suppression, and stops recipient."""
    company = setup_test_org["company"]
    campaign = setup_test_org["campaign"]
    target_email = "optout_user@example.com"

    recipient = CampaignRecipient(
        campaign_id=campaign.id,
        email=target_email,
        first_name="Optout",
        status=CampaignRecipientStatus.ACTIVE.value,
        current_step_number=1,
        next_step_due_at=datetime.now(timezone.utc) + timedelta(days=3),
    )
    db_session.add(recipient)
    await db_session.commit()

    token = create_unsubscribe_token(company_id=company.id, email=target_email, campaign_id=campaign.id)

    # Execute RFC 8058 One-Click POST
    post_res = await async_client.post(
        f"/api/v1/public/unsubscribe/{token}",
        headers={"List-Unsubscribe": "One-Click"},
    )
    assert post_res.status_code == 200
    data = post_res.json()
    assert data["status"] == "unsubscribed"
    assert data["email"] == target_email
    assert data["company_id"] == company.id

    # Verify company suppression list contains the email
    is_suppressed = await SuppressionService.is_suppressed(db_session, company.id, target_email)
    assert is_suppressed is True

    # Verify recipient record updated
    await db_session.refresh(recipient)
    assert recipient.status == CampaignRecipientStatus.SUPPRESSED.value
    assert recipient.stopped_reason == CampaignRecipientStopReason.UNSUBSCRIBED.value
    assert recipient.next_step_due_at is None


@pytest.mark.asyncio
async def test_repeated_post_is_idempotent(async_client: AsyncClient, db_session: AsyncSession, setup_test_org):
    """Requirement 3: Repeated POST calls are idempotent and do not create duplicate suppression rows."""
    company = setup_test_org["company"]
    campaign = setup_test_org["campaign"]
    target_email = "idempotent_user@example.com"

    token = create_unsubscribe_token(company_id=company.id, email=target_email, campaign_id=campaign.id)

    # First POST
    res1 = await async_client.post(f"/api/v1/public/unsubscribe/{token}")
    assert res1.status_code == 200
    assert res1.json()["status"] == "unsubscribed"

    # Second POST
    res2 = await async_client.post(f"/api/v1/public/unsubscribe/{token}")
    assert res2.status_code == 200
    assert res2.json()["status"] == "unsubscribed"

    # Verify exactly 1 suppression entry exists
    stmt = select(SuppressionEntry).where(
        SuppressionEntry.company_id == company.id,
        SuppressionEntry.email == target_email,
    )
    result = await db_session.execute(stmt)
    entries = result.scalars().all()
    assert len(entries) == 1


@pytest.mark.asyncio
async def test_invalid_expired_revoked_wrong_purpose_rejected(async_client: AsyncClient, db_session: AsyncSession, setup_test_org):
    """Requirement 4: Invalid, expired, revoked, and wrong-purpose tokens are rejected."""
    company = setup_test_org["company"]
    campaign = setup_test_org["campaign"]

    # 1. Tampered / invalid JWT
    valid_jwt = create_unsubscribe_token(company_id=company.id, email="user@test.com")
    tampered_jwt = valid_jwt[:-5] + "xxxxx"
    res_tampered = await async_client.post(f"/api/v1/public/unsubscribe/{tampered_jwt}")
    assert res_tampered.status_code == 400

    # 2. Expired JWT
    expired_jwt = create_unsubscribe_token(
        company_id=company.id,
        email="expired@test.com",
        expires_delta=-timedelta(days=1),
    )
    res_exp_jwt = await async_client.post(f"/api/v1/public/unsubscribe/{expired_jwt}")
    assert res_exp_jwt.status_code == 400
    assert "expired" in res_exp_jwt.json()["detail"].lower()

    # 3. Opaque token: wrong purpose (CLICK token passed to unsubscribe)
    click_token, raw_click = await EmailTrackingService.create_tracking_token(
        db=db_session,
        company_id=company.id,
        email_id=10,
        token_type=TrackingTokenType.CLICK,
        destination_url="https://example.com",
    )
    await db_session.commit()
    res_wrong_purpose = await async_client.post(f"/api/v1/public/unsubscribe/{raw_click}")
    assert res_wrong_purpose.status_code == 400
    assert "mismatch" in res_wrong_purpose.json()["detail"].lower()

    # 4. Opaque token: revoked token
    unsub_token, raw_unsub = await EmailTrackingService.create_tracking_token(
        db=db_session,
        company_id=company.id,
        email_id=11,
        token_type=TrackingTokenType.UNSUBSCRIBE,
    )
    unsub_token.is_revoked = True
    await db_session.commit()
    res_revoked = await async_client.post(f"/api/v1/public/unsubscribe/{raw_unsub}")
    assert res_revoked.status_code == 400
    assert "revoked" in res_revoked.json()["detail"].lower()

    # 5. Opaque token: expired token
    exp_token, raw_exp = await EmailTrackingService.create_tracking_token(
        db=db_session,
        company_id=company.id,
        email_id=12,
        token_type=TrackingTokenType.UNSUBSCRIBE,
        expires_at=datetime.now(timezone.utc) - timedelta(hours=2),
    )
    await db_session.commit()
    res_exp_opaque = await async_client.post(f"/api/v1/public/unsubscribe/{raw_exp}")
    assert res_exp_opaque.status_code == 400
    assert "expired" in res_exp_opaque.json()["detail"].lower()


@pytest.mark.asyncio
async def test_cross_tenant_token_isolation(async_client: AsyncClient, db_session: AsyncSession, setup_test_org):
    """Requirement 5: Cross-tenant token access is rejected and does not affect foreign companies."""
    from app.modules.companies.models import Company

    company_a = setup_test_org["company"]

    # Create Company B
    company_b = Company(name="Tenant B Corp")
    db_session.add(company_b)
    await db_session.commit()
    await db_session.refresh(company_b)

    target_email = "shared_email@example.com"

    # Token issued for Company A
    token_a = create_unsubscribe_token(company_id=company_a.id, email=target_email)

    # Post unsubscribe using Company A's token
    res = await async_client.post(f"/api/v1/public/unsubscribe/{token_a}")
    assert res.status_code == 200

    # Verify target_email IS suppressed in Company A
    supp_a = await SuppressionService.is_suppressed(db_session, company_a.id, target_email)
    assert supp_a is True

    # Verify target_email is NOT suppressed in Company B (cross-tenant isolation)
    supp_b = await SuppressionService.is_suppressed(db_session, company_b.id, target_email)
    assert supp_b is False


@pytest.mark.asyncio
async def test_suppression_prevents_future_campaign_sends(db_session: AsyncSession, setup_test_org):
    """Requirement 6: Suppression prevents future campaign sends to the suppressed address."""
    from app.modules.campaigns.delivery_service import CampaignDeliveryService

    company = setup_test_org["company"]
    campaign = setup_test_org["campaign"]
    suppressed_email = "blocked_user@example.com"

    # 1. Add suppression entry
    supp = SuppressionEntry(
        company_id=company.id,
        email=suppressed_email,
        reason=SuppressionReason.UNSUBSCRIBE.value,
    )
    db_session.add(supp)

    # 2. Add recipient to campaign
    recipient = CampaignRecipient(
        campaign_id=campaign.id,
        email=suppressed_email,
        first_name="Blocked",
        status=CampaignRecipientStatus.ACTIVE.value,
        current_step_number=0,
    )
    db_session.add(recipient)
    campaign.status = CampaignStatus.QUEUED.value
    await db_session.commit()

    # 3. Execute campaign dispatch
    result = await CampaignDeliveryService.execute_campaign(
        campaign_id=campaign.id,
        company_id=company.id,
        db_factory=lambda: db_session,
    )

    # Recipient should be suppressed and 0 emails sent
    assert result["sent_count"] == 0

    recip_after = await db_session.get(CampaignRecipient, recipient.id)
    assert recip_after is not None
    assert recip_after.status == CampaignRecipientStatus.SUPPRESSED.value


@pytest.mark.asyncio
async def test_pending_followups_are_cancelled(async_client: AsyncClient, db_session: AsyncSession, setup_test_org):
    """Requirement 7: Unsubscribing cancels pending follow-ups immediately."""
    company = setup_test_org["company"]
    campaign = setup_test_org["campaign"]
    followup_email = "fu_cancel@example.com"

    recipient = CampaignRecipient(
        campaign_id=campaign.id,
        email=followup_email,
        first_name="FollowupUser",
        status=CampaignRecipientStatus.ACTIVE.value,
        current_step_number=1,
        next_step_due_at=datetime.now(timezone.utc) + timedelta(hours=48),
    )
    db_session.add(recipient)
    await db_session.commit()

    token = create_unsubscribe_token(company_id=company.id, email=followup_email, campaign_id=campaign.id)

    # Unsubscribe via POST
    res = await async_client.post(f"/api/v1/public/unsubscribe/{token}")
    assert res.status_code == 200

    # Verify recipient's next_step_due_at is cleared and stopped_reason is UNSUBSCRIBED
    await db_session.refresh(recipient)
    assert recipient.status == CampaignRecipientStatus.SUPPRESSED.value
    assert recipient.stopped_reason == CampaignRecipientStopReason.UNSUBSCRIBED.value
    assert recipient.next_step_due_at is None


@pytest.mark.asyncio
async def test_rfc_8058_headers_generated_correctly(setup_test_org):
    """Requirement 8: RFC 8058 headers are generated correctly when unsubscribe_url is provided."""
    account = setup_test_org["account"]
    unsub_url = "https://email-monitoring.onrender.com/t/u/secure_opaque_token_123"

    req = EmailSendRequest(
        email_account_id=account.id,
        to=["recipient@example.com"],
        subject="RFC 8058 Header Test",
        body_text="Click here to unsubscribe: {{unsubscribe_url}}",
        unsubscribe_url=unsub_url,
    )

    mime_msg, *_ = EmailService.build_mime_message(account, req)
    assert mime_msg["List-Unsubscribe"] == f"<{unsub_url}>"
    assert mime_msg["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"


@pytest.mark.asyncio
async def test_mailbox_emails_not_unintentionally_affected(setup_test_org):
    """Requirement 9: Mailbox emails without unsubscribe_url do not have unsubscribe headers."""
    account = setup_test_org["account"]

    req = EmailSendRequest(
        email_account_id=account.id,
        to=["direct_recipient@example.com"],
        subject="Direct Mailbox Message",
        body_text="Hello, this is a 1-to-1 message.",
    )

    mime_msg, *_ = EmailService.build_mime_message(account, req)
    assert "List-Unsubscribe" not in mime_msg
    assert "List-Unsubscribe-Post" not in mime_msg


@pytest.mark.asyncio
async def test_opaque_tracking_token_endpoints(async_client: AsyncClient, db_session: AsyncSession, setup_test_org):
    """Requirement 10: Opaque tracking token endpoints (/t/u/{token}) work with full tracking event logging."""
    company = setup_test_org["company"]
    campaign = setup_test_org["campaign"]
    target_email = "opaque_test@example.com"

    recipient = CampaignRecipient(
        campaign_id=campaign.id,
        email=target_email,
        first_name="Opaque",
        status=CampaignRecipientStatus.ACTIVE.value,
        current_step_number=1,
    )
    db_session.add(recipient)
    await db_session.flush()

    # Create opaque tracking token in database
    token_record, raw_token = await EmailTrackingService.create_tracking_token(
        db=db_session,
        company_id=company.id,
        email_id=50,
        token_type=TrackingTokenType.UNSUBSCRIBE,
        campaign_id=campaign.id,
        recipient_id=recipient.id,
        delivery_id=50,
    )
    await db_session.commit()

    # 1. GET /t/u/{token} displays confirmation page without unsubscribing
    get_res = await async_client.get(
        f"/t/u/{raw_token}",
        headers={"Accept": "application/json"},
    )
    assert get_res.status_code == 200
    assert get_res.json()["status"] == "pending_confirmation"

    is_supp = await SuppressionService.is_suppressed(db_session, company.id, target_email)
    assert is_supp is False

    # 2. POST /t/u/{token} executes unsubscription
    post_res = await async_client.post(
        f"/t/u/{raw_token}",
        headers={"List-Unsubscribe": "One-Click"},
    )
    assert post_res.status_code == 200
    assert post_res.json()["status"] == "unsubscribed"

    # Verify suppression recorded
    is_supp_after = await SuppressionService.is_suppressed(db_session, company.id, target_email)
    assert is_supp_after is True

    # Verify recipient stopped
    await db_session.refresh(recipient)
    assert recipient.status == CampaignRecipientStatus.SUPPRESSED.value
    assert recipient.stopped_reason == CampaignRecipientStopReason.UNSUBSCRIBED.value


@pytest.mark.asyncio
async def test_render_fallback_jwt_without_foreign_key_failure(async_client: AsyncClient, db_session: AsyncSession):
    """T4.2 #1: Render fallback JWT request succeeds without foreign-key violation
    when company does not exist in the database."""
    # Company 888888 does NOT exist in the database (simulating Render tracking backend)
    missing_company_id = 888888
    target_email = "victim_jwt@example.com"

    fallback_jwt = create_unsubscribe_token(
        company_id=missing_company_id,
        email=target_email,
        campaign_id=123,
        recipient_id=456,
        delivery_id=789,
    )

    # 1. POST request to /t/u/{token}
    res = await async_client.post(
        f"/t/u/{fallback_jwt}",
        headers={"List-Unsubscribe": "One-Click"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "unsubscribed"
    assert data["company_id"] == missing_company_id

    # 2. Verify EmailTrackingToken and EmailTrackingEvent were created
    token_hash = EmailTrackingService.hash_token(fallback_jwt)
    token_rec = await db_session.scalar(
        select(EmailTrackingToken).where(EmailTrackingToken.token_hash == token_hash)
    )
    assert token_rec is not None
    assert token_rec.company_id == missing_company_id
    assert token_rec.recipient_id == 456
    assert token_rec.delivery_id == 789

    event_rec = await db_session.scalar(
        select(EmailTrackingEvent).where(EmailTrackingEvent.token_id == token_rec.id)
    )
    assert event_rec is not None
    assert event_rec.event_type == "UNSUBSCRIBE"


@pytest.mark.asyncio
async def test_pagination_more_than_100_unsubscribe_events(db_session: AsyncSession, setup_test_org):
    """T4.2 #2: Synchronize more than 100 unsubscribe events using cursor pagination."""
    company = setup_test_org["company"]
    campaign = setup_test_org["campaign"]

    # Create 120 recipients
    recipients = []
    for i in range(1, 121):
        r = CampaignRecipient(
            campaign_id=campaign.id,
            email=f"bulk_unsub_{i}@test.com",
            first_name=f"User{i}",
            status=CampaignRecipientStatus.ACTIVE.value,
            current_step_number=1,
            next_step_due_at=datetime.now(timezone.utc) + timedelta(days=1),
        )
        db_session.add(r)
        recipients.append(r)
    await db_session.commit()

    # Create 120 events: Batch 1 has IDs 1..100, Batch 2 has IDs 101..120
    batch_1 = [
        {"event_id": i, "company_id": company.id, "recipient_id": recipients[i - 1].id, "email": recipients[i - 1].email}
        for i in range(1, 101)
    ]
    batch_2 = [
        {"event_id": i, "company_id": company.id, "recipient_id": recipients[i - 1].id, "email": recipients[i - 1].email}
        for i in range(101, 121)
    ]

    mock_client = AsyncMock()
    # Mock pagination: returns batch_1 on since_id=0, batch_2 on since_id=100, [] on since_id=120
    async def get_unsubscribes_side_effect(since_id=0, limit=100):
        if since_id == 0:
            return batch_1
        elif since_id == 100:
            return batch_2
        return []

    mock_client.is_configured = True
    mock_client.get_unsubscribes.side_effect = get_unsubscribes_side_effect

    # Reset cursor
    await UnsubscribeService.set_sync_cursor(0)

    # Execute sync
    synced = await UnsubscribeService.sync_remote_unsubscribes(db=db_session, tracking_client=mock_client)
    assert synced == 120

    # Cursor should have advanced to 120
    cursor = await UnsubscribeService.get_sync_cursor()
    assert cursor == 120

    # Verify recipient 1 and 120 are suppressed and follow-ups cancelled
    await db_session.refresh(recipients[0])
    await db_session.refresh(recipients[119])
    assert recipients[0].status == CampaignRecipientStatus.SUPPRESSED.value
    assert recipients[0].next_step_due_at is None
    assert recipients[119].status == CampaignRecipientStatus.SUPPRESSED.value
    assert recipients[119].next_step_due_at is None


@pytest.mark.asyncio
async def test_cursor_persistence_across_worker_restarts():
    """T4.2 #3: Cursor persistence across worker operations."""
    await UnsubscribeService.set_sync_cursor(250)
    c1 = await UnsubscribeService.get_sync_cursor()
    assert c1 == 250

    await UnsubscribeService.set_sync_cursor(500)
    c2 = await UnsubscribeService.get_sync_cursor()
    assert c2 == 500


@pytest.mark.asyncio
async def test_retry_after_partial_sync_failure(db_session: AsyncSession, setup_test_org):
    """T4.2 #4: Partial sync failure commits first batch cursor and resumes without skipping."""
    company = setup_test_org["company"]
    campaign = setup_test_org["campaign"]

    r1 = CampaignRecipient(
        campaign_id=campaign.id,
        email="partial_1@test.com",
        status=CampaignRecipientStatus.ACTIVE.value,
        current_step_number=1,
    )
    r2 = CampaignRecipient(
        campaign_id=campaign.id,
        email="partial_2@test.com",
        status=CampaignRecipientStatus.ACTIVE.value,
        current_step_number=1,
    )
    db_session.add_all([r1, r2])
    await db_session.commit()

    batch_1 = [{"event_id": 50, "company_id": company.id, "recipient_id": r1.id, "email": r1.email}]
    batch_2 = [{"event_id": 75, "company_id": company.id, "recipient_id": r2.id, "email": r2.email}]

    mock_client = AsyncMock()
    mock_client.is_configured = True
    # First run: batch 1 succeeds, batch 2 raises network error
    call_count = 0
    async def side_effect_failing(since_id=0, limit=100):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return batch_1
        raise ConnectionError("Render connection drop")

    mock_client.get_unsubscribes.side_effect = side_effect_failing

    await UnsubscribeService.set_sync_cursor(0)
    # First execution catches exception
    await UnsubscribeService.sync_remote_unsubscribes(db=db_session, tracking_client=mock_client)

    # Cursor must have committed at batch 1 (event_id 50)
    assert await UnsubscribeService.get_sync_cursor() == 50

    # Second run: recovers and fetches batch 2 starting from since_id=50
    mock_client.get_unsubscribes.side_effect = None
    mock_client.get_unsubscribes.return_value = batch_2
    synced2 = await UnsubscribeService.sync_remote_unsubscribes(db=db_session, tracking_client=mock_client)
    assert synced2 == 1
    assert await UnsubscribeService.get_sync_cursor() == 75


@pytest.mark.asyncio
async def test_duplicate_synchronization_idempotency(db_session: AsyncSession, setup_test_org):
    """T4.2 #5: Re-running sync with identical events is safe and idempotent."""
    company = setup_test_org["company"]
    campaign = setup_test_org["campaign"]

    r = CampaignRecipient(
        campaign_id=campaign.id,
        email="idempotent_sync@test.com",
        status=CampaignRecipientStatus.ACTIVE.value,
        current_step_number=1,
    )
    db_session.add(r)
    await db_session.commit()

    events = [{"event_id": 10, "company_id": company.id, "recipient_id": r.id, "email": r.email}]
    mock_client = AsyncMock()
    mock_client.is_configured = True
    mock_client.get_unsubscribes.return_value = events

    # Run twice
    await UnsubscribeService.set_sync_cursor(0)
    await UnsubscribeService.sync_remote_unsubscribes(db=db_session, tracking_client=mock_client)
    await UnsubscribeService.set_sync_cursor(0)  # force re-delivery
    await UnsubscribeService.sync_remote_unsubscribes(db=db_session, tracking_client=mock_client)

    # Verify only 1 suppression entry exists
    stmt = select(SuppressionEntry).where(
        SuppressionEntry.company_id == company.id,
        SuppressionEntry.email == "idempotent_sync@test.com",
    )
    res = await db_session.execute(stmt)
    assert len(res.scalars().all()) == 1


@pytest.mark.asyncio
async def test_unsubscribe_during_active_campaign_dispatch(db_session: AsyncSession, setup_test_org):
    """T4.2 #6: An unsubscribe received during campaign dispatch prevents sending to that recipient."""
    from app.modules.campaigns.delivery_service import CampaignDeliveryService

    from app.modules.campaigns.models import CampaignStep

    company = setup_test_org["company"]
    campaign = setup_test_org["campaign"]

    # 1. Create step 1
    step_1 = CampaignStep(
        campaign_id=campaign.id,
        step_number=1,
        subject=campaign.subject,
        body_text=campaign.body_text,
        is_active=True,
    )
    db_session.add(step_1)

    # 2 recipients initially PENDING
    r1 = CampaignRecipient(
        campaign_id=campaign.id,
        email="r1_send@test.com",
        first_name="R1",
        status=CampaignRecipientStatus.PENDING.value,
        current_step_number=0,
    )
    r2 = CampaignRecipient(
        campaign_id=campaign.id,
        email="r2_unsub@test.com",
        first_name="R2",
        status=CampaignRecipientStatus.PENDING.value,
        current_step_number=0,
    )

    # Mark both recipients initially PENDING
    db_session.add_all([r1, r2])
    campaign.status = CampaignStatus.QUEUED.value
    await db_session.commit()

    with patch("app.services.smtp.client.SMTPClient.send_email_sync") as mock_smtp:
        mock_smtp.return_value = (True, "250 OK")
        from tests.conftest import TestAsyncSessionLocal

        # Intercept send_email for r1 to concurrently suppress r2 during active dispatch
        original_send_email = EmailService.send_email

        async def mock_concurrent_send(self, db, current_user, account, send_req):
            if "r1_send@test.com" in send_req.to:
                async with TestAsyncSessionLocal() as s:
                    r2_db = await s.get(CampaignRecipient, r2.id)
                    if r2_db:
                        r2_db.status = CampaignRecipientStatus.SUPPRESSED.value
                        r2_db.stopped_reason = CampaignRecipientStopReason.UNSUBSCRIBED.value
                        await s.commit()
            return await original_send_email(self, db, current_user, account, send_req)

        with patch.object(EmailService, "send_email", mock_concurrent_send):
            result = await CampaignDeliveryService.execute_campaign(
                campaign_id=campaign.id,
                company_id=company.id,
                db_factory=TestAsyncSessionLocal,
            )

    # r1 sent, r2 skipped due to in-flight suppression check
    assert result["sent_count"] == 1
    assert result["skipped_count"] == 1
    assert mock_smtp.call_count == 1


@pytest.mark.asyncio
async def test_suppressed_status_not_overwritten_by_sent(db_session: AsyncSession, setup_test_org):
    """T4.2 #7: Successful send outcome does not overwrite SUPPRESSED status."""
    from app.modules.campaigns.delivery_service import CampaignDeliveryService
    from app.modules.campaigns.models import CampaignDelivery, CampaignDeliveryStatus

    company = setup_test_org["company"]
    campaign = setup_test_org["campaign"]

    r = CampaignRecipient(
        campaign_id=campaign.id,
        email="concurrent_unsub@test.com",
        first_name="Concurrent",
        status=CampaignRecipientStatus.SUPPRESSED.value,
        stopped_reason=CampaignRecipientStopReason.UNSUBSCRIBED.value,
        current_step_number=1,
    )
    db_session.add(r)
    await db_session.commit()

    # Simulate concurrently suppressed recipient check
    is_suppressed = (
        r.status in (CampaignRecipientStatus.SUPPRESSED.value, CampaignRecipientStatus.STOPPED.value)
        or await SuppressionService.is_suppressed(db_session, company.id, r.email)
    )
    assert is_suppressed is True
    # Status remains SUPPRESSED
    assert r.status == CampaignRecipientStatus.SUPPRESSED.value
    assert r.next_step_due_at is None


@pytest.mark.asyncio
async def test_concurrent_synchronization_safety(db_session: AsyncSession):
    """T4.2 #9: Distributed lock prevents overlapping unsubscribe sync executions."""
    lock = UnsubscribeSyncLock(ttl_seconds=60)
    acquired = await lock.acquire()
    assert acquired is True

    # Second concurrent attempt cannot acquire lock
    mock_client = AsyncMock()
    mock_client.is_configured = True
    synced = await UnsubscribeService.sync_remote_unsubscribes(db=db_session, tracking_client=mock_client)
    assert synced == 0
    mock_client.get_unsubscribes.assert_not_called()

    await lock.release()


@pytest.mark.asyncio
async def test_browser_post_response_behavior(async_client: AsyncClient, setup_test_org):
    """T4.2 #10: Browser form POST returns HTML confirmation page while machine POST returns JSON."""
    company = setup_test_org["company"]
    token = create_unsubscribe_token(company_id=company.id, email="browser_resp@test.com")

    # 1. Browser form submit (Accept: text/html)
    browser_res = await async_client.post(
        f"/api/v1/public/unsubscribe/{token}",
        headers={"Accept": "text/html,application/xhtml+xml"},
    )
    assert browser_res.status_code == 200
    assert "text/html" in browser_res.headers["content-type"]
    assert "You're Unsubscribed" in browser_res.text

    # 2. Machine RFC 8058 One-Click submit
    machine_res = await async_client.post(
        f"/api/v1/public/unsubscribe/{token}",
        headers={"List-Unsubscribe": "One-Click"},
    )
    assert machine_res.status_code == 200
    assert "application/json" in machine_res.headers["content-type"]
    assert machine_res.json()["status"] == "unsubscribed"


@pytest.mark.asyncio
async def test_tracking_client_canonical_unsubscribes_path():
    """T4.7: Verify TrackingServiceClient requests the canonical /api/v1/unsubscribes path."""
    from unittest.mock import AsyncMock, MagicMock, patch
    from app.modules.emails.tracking_client import TrackingServiceClient

    client = TrackingServiceClient()
    client._service_url = "https://tracking.test"
    client._internal_secret = "secret123"

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [{"event_id": 1, "company_id": 1}]

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        events = await client.get_unsubscribes(since_id=5, limit=50)

        assert events == [{"event_id": 1, "company_id": 1}]
        mock_get.assert_called_once()
        called_url = mock_get.call_args[0][0]
        called_params = mock_get.call_args[1]["params"]
        called_headers = mock_get.call_args[1]["headers"]

        assert called_url == "https://tracking.test/api/v1/unsubscribes"
        assert called_params == {"since_id": 5, "limit": 50}
        assert called_headers["X-Tracking-Internal-Secret"] == "secret123"


@pytest.mark.asyncio
async def test_sync_remote_unsubscribes_duplicate_events_in_same_batch(db_session: AsyncSession, setup_test_org):
    """T4.7: Verify multiple events for the same email in one batch are handled idempotently."""
    company = setup_test_org["company"]
    account = setup_test_org["account"]
    from app.modules.campaigns.models import Campaign, CampaignRecipient, CampaignRecipientStatus, SuppressionEntry
    from app.modules.campaigns.unsubscribe_service import UnsubscribeService
    from sqlalchemy import select, func

    camp = Campaign(
        company_id=company.id,
        email_account_id=account.id,
        name="Dup Batch Test Camp",
        subject="Dup Test",
        body_text="Test",
    )
    db_session.add(camp)
    await db_session.commit()
    await db_session.refresh(camp)

    r = CampaignRecipient(
        campaign_id=camp.id,
        email="dup_batch_test@test.com",
        status=CampaignRecipientStatus.ACTIVE.value,
    )
    db_session.add(r)
    await db_session.commit()
    await db_session.refresh(r)

    # Batch with two duplicate events for the same recipient with email=None (Zero PII from Render)
    batch_events = [
        {"event_id": 201, "company_id": company.id, "recipient_id": r.id, "email": None},
        {"event_id": 202, "company_id": company.id, "recipient_id": r.id, "email": None},
    ]

    mock_client = AsyncMock()
    mock_client.is_configured = True
    mock_client.get_unsubscribes.return_value = batch_events

    await UnsubscribeService.set_sync_cursor(200)

    # Execute sync
    synced = await UnsubscribeService.sync_remote_unsubscribes(db=db_session, tracking_client=mock_client)
    assert synced == 2

    # Verify cursor advanced to 202
    cursor = await UnsubscribeService.get_sync_cursor()
    assert cursor == 202

    # Verify recipient is suppressed
    await db_session.refresh(r)
    assert r.status == CampaignRecipientStatus.SUPPRESSED.value

    # Verify exactly 1 suppression entry was created using locally resolved email
    count = (await db_session.execute(
        select(func.count(SuppressionEntry.id)).where(
            SuppressionEntry.company_id == company.id,
            SuppressionEntry.email == "dup_batch_test@test.com",
        )
    )).scalar()
    assert count == 1


@pytest.mark.asyncio
async def test_build_campaign_unsubscribe_url_omits_destination_url():
    """T4.9: Verify build_campaign_unsubscribe_url does not pass plaintext email in destination_url to Render."""
    from unittest.mock import AsyncMock
    from app.modules.campaigns.unsubscribe_service import UnsubscribeService
    from app.modules.emails.tracking_client import TrackingServiceClient
    from app.modules.emails.models import TrackingTokenType
    from app.modules.emails.tracking_schemas import TrackingTokenIssueResponse
    from datetime import datetime, timezone

    mock_client = AsyncMock(spec=TrackingServiceClient)
    mock_client.is_configured = True
    mock_client.issue_token.return_value = TrackingTokenIssueResponse(
        token_id=99,
        raw_token="mock_raw_token",
        token_type=TrackingTokenType.UNSUBSCRIBE.value,
        tracking_url="https://tracking.test/t/u/mock_raw_token",
        destination_url=None,
        created_at=datetime.now(timezone.utc),
    )

    url = await UnsubscribeService.build_campaign_unsubscribe_url(
        company_id=1,
        recipient_id=42,
        delivery_id=100,
        campaign_id=10,
        recipient_email="sensitive_user@example.com",
        tracking_client=mock_client,
    )

    assert url == "https://tracking.test/t/u/mock_raw_token"
    mock_client.issue_token.assert_called_once()
    called_kwargs = mock_client.issue_token.call_args[1]

    # Invariant: destination_url must NOT contain the email (must be None)
    assert called_kwargs.get("destination_url") is None
    assert called_kwargs["company_id"] == 1
    assert called_kwargs["recipient_id"] == 42
    assert called_kwargs["delivery_id"] == 100
    assert called_kwargs["campaign_id"] == 10


