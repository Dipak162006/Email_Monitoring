"""Targeted tests for event quarantine durability and migration safety (T5.2.2).

Verifies:
1. Invalid event creates a durable quarantine record.
2. Duplicate quarantined event does not create duplicates.
3. Quarantine persistence failure prevents cursor advancement.
4. Valid sibling events still synchronize alongside quarantined events.
5. Migration 027 downgrade refuses to destroy data when NULL records exist.
6. Model metadata matches physical token_id schema (no stale FK, nullable).
"""
from datetime import datetime, timezone
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import User
from app.modules.companies.models import Company
from app.modules.campaigns.models import (
    Campaign,
    CampaignRecipient,
    CampaignDelivery,
    CampaignStatus,
    CampaignRecipientStatus,
    CampaignDeliveryStatus,
)
from app.modules.email_accounts.models import EmailAccount
from app.modules.emails.models import (
    EmailTrackingEvent,
    TrackingEventQuarantine,
    TrackingEventType,
)
from app.modules.campaigns.tracking_sync_service import TrackingEventSyncService
from app.modules.emails.tracking_client import TrackingServiceClient


@pytest.fixture
async def setup_test_campaign(db_session: AsyncSession):
    """Seed test fixtures for multi-tenant campaign event testing."""
    company = Company(name="Quarantine Test Co")
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
        name="Quarantine Audit Campaign",
        status=CampaignStatus.RUNNING.value,
    )
    db_session.add(campaign)
    await db_session.flush()

    recipient = CampaignRecipient(
        campaign_id=campaign.id,
        email="recipient_target@example.com",
        status=CampaignRecipientStatus.SENT.value,
    )
    db_session.add(recipient)
    await db_session.flush()

    delivery = CampaignDelivery(
        campaign_id=campaign.id,
        recipient_id=recipient.id,
        status=CampaignDeliveryStatus.SENT.value,
    )
    db_session.add(delivery)
    await db_session.commit()

    return {
        "company": company,
        "campaign": campaign,
        "recipient": recipient,
        "delivery": delivery,
    }


@pytest.mark.asyncio
async def test_invalid_event_creates_durable_quarantine_record(
    db_session: AsyncSession,
    setup_test_campaign: dict,
):
    """1. Verify invalid event creates a durable quarantine record with zero PII."""
    data = setup_test_campaign
    await TrackingEventSyncService.set_sync_cursor(0)

    # Remote event has a tenant mismatch: recipient belongs to another non-existent campaign 99999
    invalid_event = {
        "event_id": 801,
        "company_id": data["company"].id,
        "campaign_id": 99999,  # Mismatched / non-existent campaign
        "recipient_id": data["recipient"].id,
        "delivery_id": data["delivery"].id,
        "event_type": "OPEN",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "is_bot": False,
        "bot_reason": None,
        "recipient_email": "should_not_be_stored@example.com",
        "raw_token": "secret_token_value_abc",
    }

    mock_client = AsyncMock(spec=TrackingServiceClient)
    mock_client.is_configured = True
    mock_client.get_tracking_events.side_effect = [
        [invalid_event],
        [],
    ]

    synced_count = await TrackingEventSyncService.sync_tracking_events(
        db_session,
        tracking_client=mock_client,
    )

    # Ingestion count for normal events should be 0
    assert synced_count == 0

    # Verify quarantine record was durably written to PostgreSQL
    res = await db_session.execute(
        select(TrackingEventQuarantine).where(TrackingEventQuarantine.remote_event_id == 801)
    )
    quarantine_record = res.scalar_one_or_none()
    assert quarantine_record is not None
    assert quarantine_record.remote_event_id == 801
    assert quarantine_record.company_id == data["company"].id
    assert "Campaign id=99999 does not exist locally" in quarantine_record.reason
    assert quarantine_record.replay_status == "pending"

    # Verify zero PII in payload
    payload = quarantine_record.payload
    assert "recipient_email" not in payload
    assert "raw_token" not in payload

    # Verify cursor advanced past the quarantined event
    cursor = await TrackingEventSyncService.get_sync_cursor()
    assert cursor == 801


@pytest.mark.asyncio
async def test_duplicate_quarantined_event_does_not_create_duplicates(
    db_session: AsyncSession,
    setup_test_campaign: dict,
):
    """2. Verify duplicate quarantined event does not create duplicate quarantine rows."""
    data = setup_test_campaign

    invalid_event = {
        "event_id": 802,
        "company_id": 88888,  # Non-existent company
        "campaign_id": data["campaign"].id,
        "recipient_id": data["recipient"].id,
        "delivery_id": data["delivery"].id,
        "event_type": "CLICK",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "is_bot": None,
    }

    mock_client = AsyncMock(spec=TrackingServiceClient)
    mock_client.is_configured = True
    mock_client.get_tracking_events.side_effect = [
        [invalid_event],
        [],
    ]

    await TrackingEventSyncService.set_sync_cursor(0)
    await TrackingEventSyncService.sync_tracking_events(db_session, tracking_client=mock_client)

    # Reset cursor and re-run with same event
    await TrackingEventSyncService.set_sync_cursor(0)
    mock_client.get_tracking_events.side_effect = [
        [invalid_event],
        [],
    ]
    await TrackingEventSyncService.sync_tracking_events(db_session, tracking_client=mock_client)

    # Verify exactly 1 quarantine record exists for remote_event_id=802
    res = await db_session.execute(
        select(TrackingEventQuarantine).where(TrackingEventQuarantine.remote_event_id == 802)
    )
    records = res.scalars().all()
    assert len(records) == 1


@pytest.mark.asyncio
async def test_quarantine_persistence_failure_prevents_cursor_advancement(
    db_session: AsyncSession,
    setup_test_campaign: dict,
):
    """3. Verify failure to persist quarantine rolls back and prevents cursor advancement."""
    data = setup_test_campaign
    await TrackingEventSyncService.set_sync_cursor(100)

    invalid_event = {
        "event_id": 803,
        "company_id": 99999,
        "event_type": "OPEN",
    }

    mock_client = AsyncMock(spec=TrackingServiceClient)
    mock_client.is_configured = True
    mock_client.get_tracking_events.side_effect = [
        [invalid_event],
        [],
    ]

    # Patch db_session.execute to simulate a database failure during quarantine insert
    original_execute = db_session.execute

    async def fail_quarantine_execute(stmt, *args, **kwargs):
        # Fail when executing insert on TrackingEventQuarantine
        if "tracking_event_quarantine" in str(stmt).lower():
            raise RuntimeError("Simulated PostgreSQL disk failure during quarantine insert")
        return await original_execute(stmt, *args, **kwargs)

    with patch.object(db_session, "execute", side_effect=fail_quarantine_execute):
        result = await TrackingEventSyncService.sync_tracking_events(
            db_session,
            tracking_client=mock_client,
        )
        assert result == 0

    # Verify cursor remains unchanged at 100
    cursor = await TrackingEventSyncService.get_sync_cursor()
    assert cursor == 100


@pytest.mark.asyncio
async def test_valid_sibling_events_still_synchronize(
    db_session: AsyncSession,
    setup_test_campaign: dict,
):
    """4. Verify valid sibling events synchronize even when an invalid sibling is quarantined."""
    data = setup_test_campaign
    await TrackingEventSyncService.set_sync_cursor(0)

    event_invalid = {
        "event_id": 804,
        "company_id": 99999,  # Invalid company
        "event_type": "OPEN",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
    }
    event_valid = {
        "event_id": 805,
        "company_id": data["company"].id,
        "campaign_id": data["campaign"].id,
        "recipient_id": data["recipient"].id,
        "delivery_id": data["delivery"].id,
        "event_type": "CLICK",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "is_bot": False,
        "bot_reason": None,
        "bot_confidence": 0.0,
    }

    mock_client = AsyncMock(spec=TrackingServiceClient)
    mock_client.is_configured = True
    mock_client.get_tracking_events.side_effect = [
        [event_invalid, event_valid],
        [],
    ]

    synced_count = await TrackingEventSyncService.sync_tracking_events(
        db_session,
        tracking_client=mock_client,
    )

    assert synced_count == 1

    # Verify invalid event is in quarantine
    q_res = await db_session.execute(
        select(TrackingEventQuarantine).where(TrackingEventQuarantine.remote_event_id == 804)
    )
    assert q_res.scalar_one_or_none() is not None

    # Verify valid event is in email_tracking_events
    e_res = await db_session.execute(
        select(EmailTrackingEvent).where(EmailTrackingEvent.remote_event_id == 805)
    )
    valid_record = e_res.scalar_one_or_none()
    assert valid_record is not None
    assert valid_record.event_type == "CLICK"

    # Verify cursor advanced to highest batch id
    cursor = await TrackingEventSyncService.get_sync_cursor()
    assert cursor == 805


def test_downgrade_refuses_to_destroy_data_when_null_records_exist():
    """5. Verify migration 027 downgrade refuses to proceed when NULL records exist."""
    import importlib.util
    from pathlib import Path

    migration_path = Path(__file__).parent.parent / "alembic" / "versions" / "027_tracking_events_remote_id.py"
    spec = importlib.util.spec_from_file_location("m027", migration_path)
    m027 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m027)

    mock_conn = MagicMock()
    # Simulate presence of rows with NULL token_id
    mock_conn.execute.return_value.scalar.return_value = 5

    with patch("alembic.op.get_bind", return_value=mock_conn):
        with pytest.raises(RuntimeError) as exc_info:
            m027.downgrade()

        assert "Cannot safely downgrade migration 027" in str(exc_info.value)
        assert "contains 5 row(s) with NULL token_id or email_id" in str(exc_info.value)


def test_model_metadata_matches_physical_token_id_schema():
    """6. Verify EmailTrackingEvent model metadata aligns with physical database schema."""
    token_id_col = EmailTrackingEvent.__table__.columns["token_id"]
    email_id_col = EmailTrackingEvent.__table__.columns["email_id"]
    remote_event_id_col = EmailTrackingEvent.__table__.columns["remote_event_id"]

    # Verify token_id is nullable and has NO foreign key constraint
    assert token_id_col.nullable is True
    assert len(token_id_col.foreign_keys) == 0

    # Verify email_id is nullable and has NO foreign key constraint
    assert email_id_col.nullable is True
    assert len(email_id_col.foreign_keys) == 0

    # Verify remote_event_id is nullable, unique, and indexed
    assert remote_event_id_col.nullable is True
    assert remote_event_id_col.unique is True
    assert remote_event_id_col.index is True
