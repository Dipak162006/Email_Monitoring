"""T5.2 Local Tracking Event Synchronization & Ingestion Pipeline Tests.

Verifies:
1. Successful paginated event synchronization (OPEN & CLICK).
2. Duplicate event ingestion does not create duplicate rows (PostgreSQL ON CONFLICT idempotency).
3. Cursor advances after commit but not after failed ingestion.
4. Invalid tenant associations are rejected safely.
5. Existing unsubscribe synchronization remains operational.
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.campaigns.models import (
    Campaign,
    CampaignDelivery,
    CampaignDeliveryStatus,
    CampaignRecipient,
    CampaignRecipientStatus,
    CampaignStatus,
    CampaignStep,
)
from app.modules.campaigns.tracking_sync_service import (
    InteractionSyncLock,
    TrackingEventSyncService,
)
from app.modules.campaigns.unsubscribe_service import UnsubscribeService
from app.modules.companies.models import Company
from app.modules.email_accounts.models import EmailAccount
from app.modules.emails.models import (
    Email,
    EmailDirection,
    EmailStatus,
    EmailTrackingEvent,
    TrackingEventType,
    TrackingTokenType,
)
from app.modules.emails.tracking_client import TrackingServiceClient


@pytest.fixture
async def sample_campaign_data(db_session: AsyncSession):
    """Set up valid company, email account, campaign, step, recipient, and delivery records."""
    company = Company(name="Sync Co 1")
    db_session.add(company)
    await db_session.flush()

    account = EmailAccount(
        company_id=company.id,
        name="Default Sender",
        email_address="sender@example.com",
    )
    db_session.add(account)
    await db_session.flush()

    campaign = Campaign(
        company_id=company.id,
        email_account_id=account.id,
        name="Q4 Enterprise Outreach",
        status=CampaignStatus.RUNNING.value,
    )
    db_session.add(campaign)
    await db_session.flush()

    step = CampaignStep(
        campaign_id=campaign.id,
        step_number=1,
        subject="Hello {{ first_name }}",
        body_text="Hi there",
    )
    db_session.add(step)
    await db_session.flush()

    recipient = CampaignRecipient(
        campaign_id=campaign.id,
        email="lead@targetcorp.com",
        first_name="Jane",
        status=CampaignRecipientStatus.PENDING.value,
    )
    db_session.add(recipient)
    await db_session.flush()

    email_rec = Email(
        company_id=company.id,
        email_account_id=account.id,
        direction=EmailDirection.OUTGOING.value,
        status=EmailStatus.SENT.value,
        sender="sender@example.com",
        recipients=["lead@targetcorp.com"],
        subject="Hello Jane",
        body_text="Hi there",
    )
    db_session.add(email_rec)
    await db_session.flush()

    delivery = CampaignDelivery(
        campaign_id=campaign.id,
        recipient_id=recipient.id,
        step_id=step.id,
        email_id=email_rec.id,
        status=CampaignDeliveryStatus.SENT.value,
        sent_at=datetime.now(timezone.utc),
    )
    db_session.add(delivery)
    await db_session.commit()

    return {
        "company": company,
        "campaign": campaign,
        "step": step,
        "recipient": recipient,
        "email": email_rec,
        "delivery": delivery,
    }


@pytest.mark.asyncio
async def test_successful_paginated_event_synchronization(
    db_session: AsyncSession, sample_campaign_data: dict
):
    """1. Successful paginated event synchronization across multiple pages."""
    data = sample_campaign_data
    company_id = data["company"].id
    campaign_id = data["campaign"].id
    recipient_id = data["recipient"].id
    delivery_id = data["delivery"].id
    email_id = data["email"].id

    page_1 = [
        {
            "event_id": 101,
            "company_id": company_id,
            "campaign_id": campaign_id,
            "recipient_id": recipient_id,
            "delivery_id": delivery_id,
            "event_type": "OPEN",
            "occurred_at": "2026-11-20T10:00:00Z",
            "is_bot": True,
            "bot_reason": "apple_mpp",
            "bot_confidence": 0.95,
        },
        {
            "event_id": 102,
            "company_id": company_id,
            "campaign_id": campaign_id,
            "recipient_id": recipient_id,
            "delivery_id": delivery_id,
            "event_type": "CLICK",
            "occurred_at": "2026-11-20T10:01:00Z",
            "is_bot": True,
            "bot_reason": "microsoft_safelinks",
            "bot_confidence": 0.90,
        },
    ]
    page_2 = [
        {
            "event_id": 103,
            "company_id": company_id,
            "campaign_id": campaign_id,
            "recipient_id": recipient_id,
            "delivery_id": delivery_id,
            "event_type": "OPEN",
            "occurred_at": "2026-11-20T10:02:00Z",
            "is_bot": None,
            "bot_reason": None,
            "bot_confidence": None,
        }
    ]

    mock_client = AsyncMock(spec=TrackingServiceClient)
    mock_client.is_configured = True

    async def get_tracking_events_side_effect(since_id=0, limit=100, types=None, company_id=None):
        if since_id == 0:
            return page_1
        elif since_id == 102:
            return page_2
        return []

    mock_client.get_tracking_events.side_effect = get_tracking_events_side_effect

    # Reset cursor
    await TrackingEventSyncService.set_sync_cursor(0)

    # Execute sync with batch_limit=2 to trigger pagination
    synced_count = await TrackingEventSyncService.sync_tracking_events(
        db=db_session,
        tracking_client=mock_client,
        batch_limit=2,
    )
    assert synced_count == 3

    # Assert cursor advanced to highest ID
    final_cursor = await TrackingEventSyncService.get_sync_cursor()
    assert final_cursor == 103

    # Verify persisted events in local DB
    stmt = (
        select(EmailTrackingEvent)
        .where(EmailTrackingEvent.company_id == company_id)
        .order_by(EmailTrackingEvent.remote_event_id.asc())
    )
    events = (await db_session.execute(stmt)).scalars().all()
    assert len(events) == 3

    assert events[0].remote_event_id == 101
    assert events[0].event_type == "OPEN"
    assert events[0].is_bot is True
    assert events[0].bot_reason == "apple_mpp"
    assert events[0].email_id == email_id

    assert events[1].remote_event_id == 102
    assert events[1].event_type == "CLICK"
    assert events[1].is_bot is True
    assert events[1].bot_reason == "microsoft_safelinks"

    assert events[2].remote_event_id == 103
    assert events[2].event_type == "OPEN"
    assert events[2].is_bot is None
    assert events[2].bot_reason is None


@pytest.mark.asyncio
async def test_duplicate_event_ingestion_idempotency(
    db_session: AsyncSession, sample_campaign_data: dict
):
    """2. Duplicate event ingestion does not create duplicate rows."""
    data = sample_campaign_data
    company_id = data["company"].id
    campaign_id = data["campaign"].id
    recipient_id = data["recipient"].id
    delivery_id = data["delivery"].id

    batch = [
        {
            "event_id": 201,
            "company_id": company_id,
            "campaign_id": campaign_id,
            "recipient_id": recipient_id,
            "delivery_id": delivery_id,
            "event_type": "OPEN",
            "occurred_at": "2026-11-20T11:00:00Z",
            "is_bot": None,
        }
    ]

    mock_client = AsyncMock(spec=TrackingServiceClient)
    mock_client.is_configured = True
    mock_client.get_tracking_events.return_value = batch

    # First run
    await TrackingEventSyncService.set_sync_cursor(0)
    synced1 = await TrackingEventSyncService.sync_tracking_events(
        db=db_session,
        tracking_client=mock_client,
        batch_limit=10,
    )
    assert synced1 == 1

    # Simulate re-delivery or cursor rewind
    await TrackingEventSyncService.set_sync_cursor(0)
    synced2 = await TrackingEventSyncService.sync_tracking_events(
        db=db_session,
        tracking_client=mock_client,
        batch_limit=10,
    )
    # The batch was processed without error
    assert synced2 == 1

    # Assert exactly 1 row exists with remote_event_id = 201
    stmt = (
        select(EmailTrackingEvent)
        .where(EmailTrackingEvent.remote_event_id == 201)
    )
    events = (await db_session.execute(stmt)).scalars().all()
    assert len(events) == 1


@pytest.mark.asyncio
async def test_cursor_advances_after_commit_not_after_failure(
    db_session: AsyncSession, sample_campaign_data: dict
):
    """3. Cursor advances after commit but not after failed ingestion."""
    data = sample_campaign_data
    company_id = data["company"].id

    batch_ok = [
        {
            "event_id": 301,
            "company_id": company_id,
            "campaign_id": data["campaign"].id,
            "recipient_id": data["recipient"].id,
            "delivery_id": data["delivery"].id,
            "event_type": "OPEN",
            "occurred_at": "2026-11-20T12:00:00Z",
        }
    ]
    batch_failing = [
        {
            "event_id": 302,
            "company_id": company_id,
            "campaign_id": data["campaign"].id,
            "recipient_id": data["recipient"].id,
            "delivery_id": data["delivery"].id,
            "event_type": "CLICK",
            "occurred_at": "2026-11-20T12:01:00Z",
        }
    ]

    mock_client = AsyncMock(spec=TrackingServiceClient)
    mock_client.is_configured = True

    # 1. Successful run -> advances to 301
    mock_client.get_tracking_events.return_value = batch_ok
    await TrackingEventSyncService.set_sync_cursor(0)
    synced = await TrackingEventSyncService.sync_tracking_events(
        db=db_session,
        tracking_client=mock_client,
        batch_limit=10,
    )
    assert synced == 1
    assert await TrackingEventSyncService.get_sync_cursor() == 301

    # 2. Failing transaction -> cursor remains at 301
    mock_client.get_tracking_events.return_value = batch_failing
    with patch.object(db_session, "commit", side_effect=RuntimeError("Simulated DB Disk Crash")):
        synced_fail = await TrackingEventSyncService.sync_tracking_events(
            db=db_session,
            tracking_client=mock_client,
            batch_limit=10,
        )
        assert synced_fail == 0
        # Cursor MUST NOT advance past 301
        assert await TrackingEventSyncService.get_sync_cursor() == 301


@pytest.mark.asyncio
async def test_invalid_tenant_associations_rejected_safely(
    db_session: AsyncSession, sample_campaign_data: dict
):
    """4. Invalid tenant associations are rejected safely without corrupting data."""
    data = sample_campaign_data
    company_a = data["company"].id

    # Create Company B
    company_b = Company(name="Tenant B")
    db_session.add(company_b)
    await db_session.flush()

    campaign_b = Campaign(
        company_id=company_b.id,
        email_account_id=data["campaign"].email_account_id,
        name="Campaign B",
        status=CampaignStatus.RUNNING.value,
    )
    db_session.add(campaign_b)
    await db_session.commit()

    invalid_events = [
        # Non-existent company
        {
            "event_id": 401,
            "company_id": 999999,
            "campaign_id": data["campaign"].id,
            "event_type": "OPEN",
        },
        # Cross-tenant mismatch: company_a specified, but campaign belongs to company_b
        {
            "event_id": 402,
            "company_id": company_a,
            "campaign_id": campaign_b.id,
            "event_type": "OPEN",
        },
        # Cross-campaign mismatch: recipient belongs to campaign A, but campaign B specified
        {
            "event_id": 403,
            "company_id": company_b.id,
            "campaign_id": campaign_b.id,
            "recipient_id": data["recipient"].id,
            "event_type": "OPEN",
        },
        # Unsupported event type
        {
            "event_id": 404,
            "company_id": company_a,
            "campaign_id": data["campaign"].id,
            "event_type": "MALICIOUS_TYPE",
        },
    ]

    mock_client = AsyncMock(spec=TrackingServiceClient)
    mock_client.is_configured = True
    mock_client.get_tracking_events.return_value = invalid_events

    await TrackingEventSyncService.set_sync_cursor(400)
    synced = await TrackingEventSyncService.sync_tracking_events(
        db=db_session,
        tracking_client=mock_client,
        batch_limit=10,
    )
    assert synced == 0

    # Ensure none of the invalid events were written to EmailTrackingEvent
    stmt = (
        select(EmailTrackingEvent)
        .where(EmailTrackingEvent.remote_event_id.in_([401, 402, 403, 404]))
    )
    inserted = (await db_session.execute(stmt)).scalars().all()
    assert len(inserted) == 0


@pytest.mark.asyncio
async def test_existing_unsubscribe_sync_remains_operational(
    db_session: AsyncSession, sample_campaign_data: dict
):
    """5. Existing unsubscribe synchronization and cursor remain operational and isolated."""
    data = sample_campaign_data
    company_id = data["company"].id
    recipient = data["recipient"]

    unsub_event = [
        {
            "event_id": 501,
            "company_id": company_id,
            "campaign_id": data["campaign"].id,
            "recipient_id": recipient.id,
            "email": recipient.email,
        }
    ]

    mock_client = AsyncMock(spec=TrackingServiceClient)
    mock_client.is_configured = True
    mock_client.get_unsubscribes.return_value = unsub_event

    await UnsubscribeService.set_sync_cursor(0)
    await TrackingEventSyncService.set_sync_cursor(999)

    synced_unsub = await UnsubscribeService.sync_remote_unsubscribes(
        db=db_session,
        tracking_client=mock_client,
    )
    assert synced_unsub == 1

    # Verify recipient suppressed
    await db_session.refresh(recipient)
    assert recipient.status == CampaignRecipientStatus.SUPPRESSED.value

    # Verify cursors are independent
    unsub_cursor = await UnsubscribeService.get_sync_cursor()
    interaction_cursor = await TrackingEventSyncService.get_sync_cursor()

    assert unsub_cursor == 501
    assert interaction_cursor == 999  # Untouched by unsubscribe sync!
