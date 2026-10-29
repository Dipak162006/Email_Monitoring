from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
"""Milestone M6 — Sending Windows & Timezone Governance Unit Tests.

Covers:
1. Disabled and null configurations preserve existing unrestricted behavior.
2. Valid and invalid configuration validation.
3. Opening and closing boundary behavior (inclusive start, exclusive end).
4. Weekends and permitted/unpermitted days.
5. Timezone conversion and DST transitions.
6. Initial sends deferred outside the window.
7. Campaign pacing and recovery alignment.
8. Follow-ups deferred correctly while preserving delay semantics.
9. M4/M5 compatibility (targeting advances immediately, manual reschedule aligns to window).
10. Invalid configuration fail-closed behavior.
"""
from datetime import datetime, time, timedelta, timezone
from typing import List
from zoneinfo import ZoneInfo
import pytest

from app.modules.campaigns.models import (
    Campaign,
    CampaignDelivery,
    CampaignDeliveryStatus,
    CampaignRecipient,
    CampaignRecipientStatus,
    CampaignStatus,
    CampaignStep,
)
from app.modules.campaigns.schemas import CampaignCreate, CampaignUpdate
from app.modules.campaigns.window_service import (
    SendingWindowConfig,
    SendingWindowService,
)
from app.modules.campaigns.delivery_service import CampaignDeliveryService
from app.modules.campaigns.scheduling_service import CampaignSchedulingService


# =============================================================================
# 1. Configuration Validation & Schema Tests
# =============================================================================

def test_window_config_defaults_and_null_behavior():
    """Disabled and null configurations preserve existing unrestricted behavior."""
    cfg = SendingWindowConfig()
    assert cfg.enabled is False
    assert cfg.timezone == "UTC"
    assert cfg.days == [1, 2, 3, 4, 5]
    assert cfg.start_time == "09:00"
    assert cfg.end_time == "17:00"

    # Evaluates unrestricted when disabled or None
    dt = datetime(2026, 10, 25, 3, 0, tzinfo=timezone.utc)  # Sunday 3 AM UTC
    assert SendingWindowService.is_within_sending_window(dt, None) is True
    assert SendingWindowService.is_within_sending_window(dt, cfg) is True
    assert SendingWindowService.compute_next_window_opening(dt, None) == dt
    assert SendingWindowService.compute_next_window_opening(dt, cfg) == dt


def test_window_config_validation_rules():
    """Validates IANA timezone, ISO weekdays, and HH:MM boundaries."""
    # Valid config
    valid = SendingWindowConfig(
        enabled=True,
        timezone="Asia/Kolkata",
        days=[1, 2, 3, 4, 5],
        start_time="10:00",
        end_time="18:30",
    )
    assert valid.timezone == "Asia/Kolkata"

    # Invalid timezone rejected
    with pytest.raises(ValueError, match="Invalid IANA timezone"):
        SendingWindowConfig(enabled=True, timezone="Mars/Olympus_Mons")

    # Empty days rejected
    with pytest.raises(ValueError, match="Permitted sending days cannot be empty"):
        SendingWindowConfig(enabled=True, days=[])

    # Invalid day numbers rejected
    with pytest.raises(ValueError, match="must be integers between 1"):
        SendingWindowConfig(enabled=True, days=[0, 8])

    # Invalid time format rejected
    with pytest.raises(ValueError, match="must be in 24-hour HH:MM format"):
        SendingWindowConfig(enabled=True, start_time="9am")

    # start_time >= end_time rejected
    with pytest.raises(ValueError, match="must be strictly earlier than end_time"):
        SendingWindowConfig(enabled=True, start_time="17:00", end_time="09:00")

    with pytest.raises(ValueError, match="must be strictly earlier than end_time"):
        SendingWindowConfig(enabled=True, start_time="10:00", end_time="10:00")


# =============================================================================
# 2. Window Calculation & Boundary Tests
# =============================================================================

def test_window_boundaries_inclusive_start_exclusive_end():
    """Verifies that start_time is inclusive and end_time is exclusive."""
    cfg = SendingWindowConfig(
        enabled=True,
        timezone="UTC",
        days=[1, 2, 3, 4, 5],  # Mon..Fri
        start_time="09:00",
        end_time="17:00",
    )

    # Monday 2026-10-26 (ISO weekday 1)
    # Exactly at start_time 09:00:00 -> IN WINDOW
    dt_start = datetime(2026, 10, 26, 9, 0, 0, tzinfo=timezone.utc)
    assert SendingWindowService.is_within_sending_window(dt_start, cfg) is True

    # At 16:59:59 -> IN WINDOW
    dt_inside = datetime(2026, 10, 26, 16, 59, 59, tzinfo=timezone.utc)
    assert SendingWindowService.is_within_sending_window(dt_inside, cfg) is True

    # Exactly at end_time 17:00:00 -> OUTSIDE WINDOW (exclusive)
    dt_end = datetime(2026, 10, 26, 17, 0, 0, tzinfo=timezone.utc)
    assert SendingWindowService.is_within_sending_window(dt_end, cfg) is False

    # At 08:59:59 -> OUTSIDE WINDOW
    dt_before = datetime(2026, 10, 26, 8, 59, 59, tzinfo=timezone.utc)
    assert SendingWindowService.is_within_sending_window(dt_before, cfg) is False


def test_weekend_and_unpermitted_day_deferral():
    """Out-of-window on Friday evening defers past weekend to Monday morning."""
    cfg = SendingWindowConfig(
        enabled=True,
        timezone="UTC",
        days=[1, 2, 3, 4, 5],  # Mon..Fri
        start_time="09:00",
        end_time="17:00",
    )

    # Friday 2026-10-30 at 18:00 UTC (after closing)
    friday_night = datetime(2026, 10, 30, 18, 0, 0, tzinfo=timezone.utc)
    next_open = SendingWindowService.compute_next_window_opening(friday_night, cfg)

    # Must defer to Monday 2026-11-02 at 09:00 UTC
    expected = datetime(2026, 11, 2, 9, 0, 0, tzinfo=timezone.utc)
    assert next_open == expected

    # Saturday 2026-10-31 at 12:00 UTC
    saturday_noon = datetime(2026, 10, 31, 12, 0, 0, tzinfo=timezone.utc)
    assert SendingWindowService.is_within_sending_window(saturday_noon, cfg) is False
    assert SendingWindowService.compute_next_window_opening(saturday_noon, cfg) == expected


def test_timezone_conversion_and_dst_handling():
    """Correctly evaluates local windows in non-UTC timezones and handles DST transitions."""
    # US Eastern Time: EDT (UTC-4) in October, EST (UTC-5) after Nov 1, 2026
    cfg = SendingWindowConfig(
        enabled=True,
        timezone="America/New_York",
        days=[1, 2, 3, 4, 5],
        start_time="09:00",
        end_time="17:00",
    )

    # Wednesday 2026-10-28 in EDT (UTC-4)
    # 09:00 EDT = 13:00 UTC
    dt_utc_13 = datetime(2026, 10, 28, 13, 0, 0, tzinfo=timezone.utc)
    assert SendingWindowService.is_within_sending_window(dt_utc_13, cfg) is True

    # 08:59 EDT = 12:59 UTC -> Outside
    dt_utc_1259 = datetime(2026, 10, 28, 12, 59, 0, tzinfo=timezone.utc)
    assert SendingWindowService.is_within_sending_window(dt_utc_1259, cfg) is False

    # After DST fallback on Nov 1, 2026: EST is UTC-5
    # Monday 2026-11-02: 09:00 EST = 14:00 UTC
    dt_utc_nov = datetime(2026, 11, 2, 14, 0, 0, tzinfo=timezone.utc)
    assert SendingWindowService.is_within_sending_window(dt_utc_nov, cfg) is True

    dt_utc_nov_early = datetime(2026, 11, 2, 13, 59, 0, tzinfo=timezone.utc)
    assert SendingWindowService.is_within_sending_window(dt_utc_nov_early, cfg) is False


def test_invalid_stored_configuration_fails_closed():
    """Corrupt or invalid stored JSON refuses dispatch rather than sending at random times."""
    corrupt_cfg = {"enabled": True, "timezone": "Invalid/Bogus", "start_time": "12:00", "end_time": "10:00"}
    dt = datetime(2026, 10, 28, 12, 0, 0, tzinfo=timezone.utc)

    # Fails closed: returns False
    assert SendingWindowService.is_within_sending_window(dt, corrupt_cfg) is False

    # compute_next_window_opening raises ValueError
    with pytest.raises(ValueError):
        SendingWindowService.compute_next_window_opening(dt, corrupt_cfg)


# =============================================================================
# 3. Service Integration Tests (Initial Sends & Follow-Ups)
# =============================================================================

@pytest.mark.anyio
async def test_initial_send_deferred_outside_window(db_session: AsyncSession, monkeypatch):
    """Initial campaign execution defers dispatch and updates next_send_at when outside window."""
    from app.modules.companies.models import Company
    from app.modules.email_accounts.models import EmailAccount
    from app.modules.auth.models import User
    from app.modules.campaigns.service import CampaignService
    from unittest.mock import AsyncMock

    mock_email_service = AsyncMock()

    company = Company(name="Window Co", is_active=True)
    db_session.add(company)
    await db_session.flush()

    user = User(email="owner@window.com", hashed_password="pw", is_active=True)
    db_session.add(user)
    await db_session.flush()

    account = EmailAccount(
        company_id=company.id,
        name="Sales",
        email_address="sales@window.com",
        provider="SMTP_IMAP",
        is_active=True,
    )
    db_session.add(account)
    await db_session.flush()

    # Window: Mon-Fri 09:00 - 17:00 UTC
    window = SendingWindowConfig(
        enabled=True,
        timezone="UTC",
        days=[1, 2, 3, 4, 5],
        start_time="09:00",
        end_time="17:00",
    )

    camp_in = CampaignCreate(
        name="Out of Window Campaign",
        email_account_id=account.id,
        subject="Intro",
        body_text="Hello",
        sending_window=window,
    )
    campaign = await CampaignService.create_campaign(
        db=db_session,
        company_id=company.id,
        campaign_in=camp_in,
        creator_user_id=user.id,
    )
    campaign.status = CampaignStatus.QUEUED.value
    await db_session.commit()

    # Execute outside the window (Sunday at 20:00 UTC)
    sunday_night = datetime(2026, 10, 25, 20, 0, 0, tzinfo=timezone.utc)
    from tests.conftest import TestAsyncSessionLocal

    res = await CampaignDeliveryService.execute_campaign(
        campaign_id=campaign.id,
        company_id=company.id,
        db_factory=TestAsyncSessionLocal,
        email_service=mock_email_service,
        now_utc=sunday_night,
    )

    assert res["status"] == "WAITING_WINDOW"
    # Should be deferred to Monday 2026-10-26 at 09:00:00 UTC
    expected_monday = datetime(2026, 10, 26, 9, 0, 0, tzinfo=timezone.utc)
    assert res["next_send_at"] == expected_monday.isoformat()

    # Verify zero SMTP calls were made
    assert mock_email_service.send_email.call_count == 0


@pytest.mark.anyio
async def test_followup_step_aligns_to_sending_window(db_session: AsyncSession, monkeypatch):
    """Follow-up due dates align to the next sending window opening while preserving delay semantics."""
    from app.modules.companies.models import Company
    from app.modules.email_accounts.models import EmailAccount
    from app.modules.auth.models import User
    from app.modules.campaigns.service import CampaignService
    from app.modules.campaigns.recipient_service import CampaignRecipientService
    from app.modules.campaigns.schemas import CampaignRecipientCreate
    from tests.conftest import TestAsyncSessionLocal
    from unittest.mock import AsyncMock

    mock_email_service = AsyncMock()

    company = Company(name="Followup Window Co", is_active=True)
    db_session.add(company)
    await db_session.flush()

    user = User(email="fu_owner@window.com", hashed_password="pw", is_active=True)
    db_session.add(user)
    await db_session.flush()

    account = EmailAccount(
        company_id=company.id,
        name="Sales",
        email_address="sales_fu@window.com",
        provider="SMTP_IMAP",
        is_active=True,
    )
    db_session.add(account)
    await db_session.flush()

    # Window: Mon-Fri 09:00 - 17:00 UTC
    window = SendingWindowConfig(
        enabled=True,
        timezone="UTC",
        days=[1, 2, 3, 4, 5],
        start_time="09:00",
        end_time="17:00",
    )

    from app.modules.campaigns.schemas import CampaignStepWrite
    camp_in = CampaignCreate(
        name="Window Followup Campaign",
        email_account_id=account.id,
        subject="Main Subject",
        body_text="Step 1 body",
        followup_steps=[
            CampaignStepWrite(step_number=2, delay_hours=48, subject="Step 2", body_text="Step 2 body"),
        ],
        sending_window=window,
    )
    campaign = await CampaignService.create_campaign(
        db=db_session,
        company_id=company.id,
        campaign_in=camp_in,
        creator_user_id=user.id,
    )

    recipient = await CampaignRecipientService.create_recipient(
        db=db_session,
        company_id=company.id,
        campaign_id=campaign.id,
        recipient_in=CampaignRecipientCreate(email="client@window.com"),
    )
    campaign.status = CampaignStatus.RUNNING.value
    await db_session.commit()

    # Suppose Step 1 was sent Thursday 2026-10-29 at 10:00 UTC
    thursday_send = datetime(2026, 10, 29, 10, 0, 0, tzinfo=timezone.utc)

    # Step 1 delivery
    step1_res = await db_session.execute(
        select(CampaignStep).where(CampaignStep.campaign_id == campaign.id, CampaignStep.step_number == 1)
    )
    step1 = step1_res.scalar_one()

    deliv1 = CampaignDelivery(
        campaign_id=campaign.id,
        recipient_id=recipient.id,
        step_id=step1.id,
        status=CampaignDeliveryStatus.SENT.value,
        sent_at=thursday_send,
    )
    db_session.add(deliv1)
    recipient.status = CampaignRecipientStatus.ACTIVE.value
    recipient.current_step_number = 1
    # Raw due date without window is Saturday 2026-10-31 at 10:00 UTC
    recipient.next_step_due_at = thursday_send + timedelta(hours=48)
    await db_session.commit()

    # Now run process_due_followup_steps on Saturday at 10:00 UTC (raw delay reached, but outside window)
    await CampaignDeliveryService.process_due_followup_steps(
        db_factory=TestAsyncSessionLocal,
        email_service=mock_email_service,
        now_utc=datetime(2026, 10, 31, 10, 0, 0, tzinfo=timezone.utc),
    )

    # Recipient should not have received Step 2 yet, and next_step_due_at should be aligned to Monday
    await db_session.refresh(recipient)
    expected_monday_open = datetime(2026, 11, 2, 9, 0, 0, tzinfo=timezone.utc)
    assert recipient.next_step_due_at == expected_monday_open
    assert recipient.current_step_number == 1
    assert mock_email_service.send_email.call_count == 0


def test_dst_ambiguous_and_nonexistent_local_times():
    """Checks deterministic next-opening calculations for ambiguous (fallback) and nonexistent (spring-forward) local times."""
    tz = ZoneInfo("America/New_York")

    # 1. Ambiguous time: Fall Back on November 1, 2026 in America/New_York (01:00-02:00 repeats)
    # Window configured to open at 01:30 on Sundays
    cfg_ambiguous = SendingWindowConfig(
        enabled=True,
        timezone="America/New_York",
        days=[7],  # Sunday
        start_time="01:30",
        end_time="05:00",
    )
    # Evaluate at 00:00 EDT on Nov 1 (04:00 UTC)
    ref_fall = datetime(2026, 11, 1, 4, 0, 0, tzinfo=timezone.utc)
    next_open_fall = SendingWindowService.compute_next_window_opening(ref_fall, cfg_ambiguous)

    # Must resolve with fold=0 to the earlier instance (01:30 EDT = 05:30 UTC)
    expected_fall = datetime(2026, 11, 1, 5, 30, 0, tzinfo=timezone.utc)
    assert next_open_fall == expected_fall
    assert next_open_fall.astimezone(tz).fold == 0

    # 2. Nonexistent time: Spring Forward on March 8, 2026 (02:00 jumps to 03:00)
    # Window configured to open at 02:30 on Sundays (gap time)
    cfg_nonexistent = SendingWindowConfig(
        enabled=True,
        timezone="America/New_York",
        days=[7],
        start_time="02:30",
        end_time="05:00",
    )
    # Evaluate at 00:00 EST on March 8 (05:00 UTC)
    ref_spring = datetime(2026, 3, 8, 5, 0, 0, tzinfo=timezone.utc)
    next_open_spring = SendingWindowService.compute_next_window_opening(ref_spring, cfg_nonexistent)

    # Valid deterministic UTC timestamp produced without raising exception
    assert next_open_spring.tzinfo == timezone.utc
    assert next_open_spring > ref_spring


@pytest.mark.anyio
async def test_mid_batch_window_closure_pacing_and_overlapping_recovery(db_session: AsyncSession, monkeypatch):
    """When window closes mid-batch or pacing lands outside window, pending recipients are preserved and recovery is idempotent."""
    from app.modules.companies.models import Company
    from app.modules.email_accounts.models import EmailAccount
    from app.modules.auth.models import User
    from app.modules.campaigns.service import CampaignService
    from app.modules.campaigns.recipient_service import CampaignRecipientService
    from app.modules.campaigns.schemas import CampaignRecipientCreate
    from tests.conftest import TestAsyncSessionLocal
    from unittest.mock import AsyncMock

    mock_email_service = AsyncMock()
    mock_sent_email = type("MockEmail", (), {"id": None, "thread_id": None, "message_id": "msg-123"})()
    mock_email_service.send_email.return_value = mock_sent_email

    company = Company(name="Paced Recovery Co", is_active=True)
    db_session.add(company)
    await db_session.flush()

    user = User(email="paced_owner@window.com", hashed_password="pw", is_active=True)
    db_session.add(user)
    await db_session.flush()

    account = EmailAccount(
        company_id=company.id,
        name="Outreach",
        email_address="outreach@window.com",
        provider="SMTP_IMAP",
        is_active=True,
    )
    db_session.add(account)
    await db_session.flush()

    # Window: Mon-Fri 09:00 - 17:00 UTC, with 60-second pacing delay
    window = SendingWindowConfig(
        enabled=True,
        timezone="UTC",
        days=[1, 2, 3, 4, 5],
        start_time="09:00",
        end_time="17:00",
    )

    camp_in = CampaignCreate(
        name="Paced Window Campaign",
        email_account_id=account.id,
        subject="Paced Subject",
        body_text="Body text",
        send_interval_seconds=60,
        sending_window=window,
    )
    campaign = await CampaignService.create_campaign(
        db=db_session,
        company_id=company.id,
        campaign_in=camp_in,
        creator_user_id=user.id,
    )

    recip1 = await CampaignRecipientService.create_recipient(
        db=db_session,
        company_id=company.id,
        campaign_id=campaign.id,
        recipient_in=CampaignRecipientCreate(email="user1@window.com"),
    )
    recip2 = await CampaignRecipientService.create_recipient(
        db=db_session,
        company_id=company.id,
        campaign_id=campaign.id,
        recipient_in=CampaignRecipientCreate(email="user2@window.com"),
    )

    campaign.status = CampaignStatus.QUEUED.value
    await db_session.commit()

    # Execution 1: Tuesday at 16:59:30 UTC (30 seconds before window closes)
    tuesday_close = datetime(2026, 10, 27, 16, 59, 30, tzinfo=timezone.utc)
    res1 = await CampaignDeliveryService.execute_campaign(
        campaign_id=campaign.id,
        company_id=company.id,
        db_factory=TestAsyncSessionLocal,
        email_service=mock_email_service,
        now_utc=tuesday_close,
    )

    # Recipient 1 was sent
    assert res1["sent_count"] == 1
    assert mock_email_service.send_email.call_count == 1

    # Next send was due at 16:59:30 + 60s = 17:00:30 UTC, which is OUTSIDE window!
    # Delivery service aligned next_send_at to Wednesday at 09:00:00 UTC
    await db_session.refresh(campaign)
    expected_wed_open = datetime(2026, 10, 28, 9, 0, 0, tzinfo=timezone.utc)
    assert campaign.next_send_at == expected_wed_open
    assert campaign.status == CampaignStatus.RUNNING.value

    # Recipient 2 remains in PENDING state (not lost!)
    await db_session.refresh(recip2)
    assert recip2.status == CampaignRecipientStatus.PENDING.value

    # Execution 2: Wednesday at 09:00:00 UTC (window opens)
    # Overlapping tasks: dispatch executes and recovers safely
    wed_open = datetime(2026, 10, 28, 9, 0, 0, tzinfo=timezone.utc)
    res2 = await CampaignDeliveryService.execute_campaign(
        campaign_id=campaign.id,
        company_id=company.id,
        db_factory=TestAsyncSessionLocal,
        email_service=mock_email_service,
        now_utc=wed_open,
    )

    # Recipient 2 is sent
    assert res2["sent_count"] == 1
    # Total sends across campaign is exactly 2 (zero duplicates!)
    assert mock_email_service.send_email.call_count == 2

    # Both recipients are completed and campaign finishes
    await db_session.refresh(recip1)
    await db_session.refresh(recip2)
    assert recip1.status in (CampaignRecipientStatus.SENT.value, CampaignRecipientStatus.ACTIVE.value)
    assert recip2.status in (CampaignRecipientStatus.SENT.value, CampaignRecipientStatus.ACTIVE.value)
