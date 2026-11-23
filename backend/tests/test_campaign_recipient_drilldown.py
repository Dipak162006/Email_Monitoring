"""Targeted tests for campaign opened/clicked recipient drilldown APIs (T5.4).

Verifies:
1. Opened recipient grouping and aggregation (total counts, first/last timestamps, masking).
2. Clicked recipient grouping and aggregation (CLICK event filtering).
3. Bot, non-bot, and unknown classification counts per recipient.
4. Campaign and company tenant isolation (cross-tenant access returns 404).
5. Pagination and stable ordering (most recent event first, tie-breaking).
6. Safe exclusion of missing, orphaned, or cross-campaign recipient associations.
"""
from datetime import datetime, timezone, timedelta
import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.companies.models import Company
from app.modules.campaigns.models import (
    Campaign,
    CampaignRecipient,
    CampaignDelivery,
    CampaignStep,
    CampaignStatus,
    CampaignRecipientStatus,
    CampaignDeliveryStatus,
)
from app.modules.campaigns.service import CampaignService, mask_email
from app.modules.email_accounts.models import EmailAccount
from app.modules.emails.models import (
    EmailTrackingEvent,
    TrackingEventType,
)


@pytest.fixture
async def drilldown_fixture(db_session: AsyncSession):
    """Seed test company, account, campaign, and 4 recipients."""
    company = Company(name="Drilldown Test Co")
    db_session.add(company)
    await db_session.flush()

    account = EmailAccount(
        company_id=company.id,
        name="Outbound Sender",
        email_address="outbound@drilldown.com",
    )
    db_session.add(account)
    await db_session.flush()

    campaign = Campaign(
        company_id=company.id,
        email_account_id=account.id,
        name="Summer Engagement Drilldown",
        status=CampaignStatus.RUNNING.value,
    )
    db_session.add(campaign)
    await db_session.flush()

    step = CampaignStep(
        campaign_id=campaign.id,
        step_number=1,
        subject="Drilldown Step 1",
    )
    db_session.add(step)
    await db_session.flush()

    recipients = []
    for i in range(1, 6):
        r = CampaignRecipient(
            campaign_id=campaign.id,
            email=f"recipient_{i}@example.com",
            status=CampaignRecipientStatus.SENT.value,
        )
        db_session.add(r)
        recipients.append(r)
    await db_session.flush()

    deliveries = []
    for r in recipients:
        d = CampaignDelivery(
            campaign_id=campaign.id,
            recipient_id=r.id,
            step_id=step.id,
            status=CampaignDeliveryStatus.SENT.value,
            sent_at=datetime.now(timezone.utc),
        )
        db_session.add(d)
        deliveries.append(d)

    await db_session.commit()

    return {
        "company": company,
        "account": account,
        "campaign": campaign,
        "step": step,
        "recipients": recipients,
        "deliveries": deliveries,
    }


def test_mask_email_utility():
    """Verify email masking safeguards recipient PII."""
    assert mask_email("alice@example.com") == "a***e@example.com"
    assert mask_email("bob@corp.org") == "b***b@corp.org"
    assert mask_email("jo@test.com") == "j***@test.com"
    assert mask_email("x@test.com") == "x***@test.com"
    assert mask_email("") is None
    assert mask_email(None) is None
    assert mask_email("invalid-email") is None


@pytest.mark.asyncio
async def test_opened_recipient_grouping_and_aggregation(
    db_session: AsyncSession,
    drilldown_fixture: dict,
):
    """1. Verify opened recipient grouping, event counts, first/last timestamps, and email masking."""
    data = drilldown_fixture
    company_id = data["company"].id
    campaign_id = data["campaign"].id
    r1, r2, r3, r4, r5 = data["recipients"]
    d1, d2 = data["deliveries"][:2]

    now = datetime.now(timezone.utc)
    t1 = now - timedelta(hours=3)
    t2 = now - timedelta(hours=2)
    t3 = now - timedelta(hours=1)
    t4 = now - timedelta(minutes=30)

    # Recipient 1 has 3 OPEN events
    ev1 = EmailTrackingEvent(
        company_id=company_id,
        campaign_id=campaign_id,
        recipient_id=r1.id,
        delivery_id=d1.id,
        event_type=TrackingEventType.OPEN.value,
        occurred_at=t1,
    )
    ev2 = EmailTrackingEvent(
        company_id=company_id,
        campaign_id=campaign_id,
        recipient_id=r1.id,
        delivery_id=d1.id,
        event_type=TrackingEventType.OPEN.value,
        occurred_at=t2,
    )
    ev3 = EmailTrackingEvent(
        company_id=company_id,
        campaign_id=campaign_id,
        recipient_id=r1.id,
        delivery_id=d1.id,
        event_type=TrackingEventType.OPEN.value,
        occurred_at=t3,
    )

    # Recipient 2 has 1 OPEN event
    ev4 = EmailTrackingEvent(
        company_id=company_id,
        campaign_id=campaign_id,
        recipient_id=r2.id,
        delivery_id=d2.id,
        event_type=TrackingEventType.OPEN.value,
        occurred_at=t4,
    )

    # Recipient 3 has 0 open events
    # Unsubscribe event for r1 (must NOT appear in open drilldown)
    ev_unsub = EmailTrackingEvent(
        company_id=company_id,
        campaign_id=campaign_id,
        recipient_id=r1.id,
        delivery_id=d1.id,
        event_type=TrackingEventType.UNSUBSCRIBE.value,
        occurred_at=now,
    )

    db_session.add_all([ev1, ev2, ev3, ev4, ev_unsub])
    await db_session.commit()

    resp = await CampaignService.get_campaign_recipient_engagement(
        db=db_session,
        company_id=company_id,
        campaign_id=campaign_id,
        event_type="OPEN",
    )

    assert resp.campaign_id == campaign_id
    assert resp.event_type == "OPEN"
    assert resp.total == 2
    assert len(resp.items) == 2

    # Ordering is most recent last_event_at first: r2 (t4) comes before r1 (t3)
    item_r2, item_r1 = resp.items

    assert item_r2.recipient_id == r2.id
    assert item_r2.masked_email == "r***2@example.com"
    assert item_r2.total_events_count == 1
    assert item_r2.first_event_at == t4
    assert item_r2.last_event_at == t4

    assert item_r1.recipient_id == r1.id
    assert item_r1.masked_email == "r***1@example.com"
    assert item_r1.total_events_count == 3
    assert item_r1.first_event_at == t1
    assert item_r1.last_event_at == t3


@pytest.mark.asyncio
async def test_clicked_recipient_grouping_and_aggregation(
    db_session: AsyncSession,
    drilldown_fixture: dict,
):
    """2. Verify clicked recipient grouping filters strictly to CLICK events."""
    data = drilldown_fixture
    company_id = data["company"].id
    campaign_id = data["campaign"].id
    r1, r2, r3, r4, r5 = data["recipients"]
    d1, d2, d3 = data["deliveries"][:3]

    now = datetime.now(timezone.utc)

    # Recipient 1: 1 OPEN, 1 CLICK
    ev_open_r1 = EmailTrackingEvent(
        company_id=company_id,
        campaign_id=campaign_id,
        recipient_id=r1.id,
        delivery_id=d1.id,
        event_type=TrackingEventType.OPEN.value,
        occurred_at=now - timedelta(hours=2),
    )
    ev_click_r1 = EmailTrackingEvent(
        company_id=company_id,
        campaign_id=campaign_id,
        recipient_id=r1.id,
        delivery_id=d1.id,
        event_type=TrackingEventType.CLICK.value,
        occurred_at=now - timedelta(hours=1),
    )

    # Recipient 2: 2 OPENS, 0 CLICKS
    ev_open_r2 = EmailTrackingEvent(
        company_id=company_id,
        campaign_id=campaign_id,
        recipient_id=r2.id,
        delivery_id=d2.id,
        event_type=TrackingEventType.OPEN.value,
        occurred_at=now - timedelta(hours=2),
    )

    # Recipient 3: 0 OPENS, 2 CLICKS
    ev_click_r3_1 = EmailTrackingEvent(
        company_id=company_id,
        campaign_id=campaign_id,
        recipient_id=r3.id,
        delivery_id=d3.id,
        event_type=TrackingEventType.CLICK.value,
        occurred_at=now - timedelta(minutes=45),
    )
    ev_click_r3_2 = EmailTrackingEvent(
        company_id=company_id,
        campaign_id=campaign_id,
        recipient_id=r3.id,
        delivery_id=d3.id,
        event_type=TrackingEventType.CLICK.value,
        occurred_at=now - timedelta(minutes=15),
    )

    db_session.add_all([ev_open_r1, ev_click_r1, ev_open_r2, ev_click_r3_1, ev_click_r3_2])
    await db_session.commit()

    resp = await CampaignService.get_campaign_recipient_engagement(
        db=db_session,
        company_id=company_id,
        campaign_id=campaign_id,
        event_type="CLICK",
    )

    assert resp.total == 2
    recipient_ids = [item.recipient_id for item in resp.items]
    assert r1.id in recipient_ids
    assert r3.id in recipient_ids
    assert r2.id not in recipient_ids  # Recipient 2 only opened, never clicked


@pytest.mark.asyncio
async def test_bot_non_bot_unknown_counts_and_timestamps(
    db_session: AsyncSession,
    drilldown_fixture: dict,
):
    """3. Verify bot, non-bot, and unknown classification counts and timestamps per recipient."""
    data = drilldown_fixture
    company_id = data["company"].id
    campaign_id = data["campaign"].id
    r1 = data["recipients"][0]
    d1 = data["deliveries"][0]

    t_base = datetime.now(timezone.utc) - timedelta(hours=5)

    ev_bot = EmailTrackingEvent(
        company_id=company_id,
        campaign_id=campaign_id,
        recipient_id=r1.id,
        delivery_id=d1.id,
        event_type=TrackingEventType.OPEN.value,
        is_bot=True,
        bot_reason="AppleImageProxy",
        occurred_at=t_base,  # Earliest
    )
    ev_non_bot_1 = EmailTrackingEvent(
        company_id=company_id,
        campaign_id=campaign_id,
        recipient_id=r1.id,
        delivery_id=d1.id,
        event_type=TrackingEventType.OPEN.value,
        is_bot=False,
        occurred_at=t_base + timedelta(hours=1),
    )
    ev_non_bot_2 = EmailTrackingEvent(
        company_id=company_id,
        campaign_id=campaign_id,
        recipient_id=r1.id,
        delivery_id=d1.id,
        event_type=TrackingEventType.OPEN.value,
        is_bot=False,
        occurred_at=t_base + timedelta(hours=2),
    )
    ev_unknown = EmailTrackingEvent(
        company_id=company_id,
        campaign_id=campaign_id,
        recipient_id=r1.id,
        delivery_id=d1.id,
        event_type=TrackingEventType.OPEN.value,
        is_bot=None,
        occurred_at=t_base + timedelta(hours=3),  # Latest
    )

    db_session.add_all([ev_bot, ev_non_bot_1, ev_non_bot_2, ev_unknown])
    await db_session.commit()

    resp = await CampaignService.get_campaign_recipient_engagement(
        db=db_session,
        company_id=company_id,
        campaign_id=campaign_id,
        event_type="OPEN",
    )

    assert resp.total == 1
    item = resp.items[0]
    assert item.recipient_id == r1.id
    assert item.total_events_count == 4
    assert item.bot_events_count == 1
    assert item.non_bot_events_count == 2
    assert item.unknown_events_count == 1
    assert item.first_event_at == t_base
    assert item.last_event_at == t_base + timedelta(hours=3)


@pytest.mark.asyncio
async def test_drilldown_campaign_and_company_isolation(
    db_session: AsyncSession,
    drilldown_fixture: dict,
):
    """4. Verify strict campaign and company tenant isolation for drilldown endpoints."""
    data = drilldown_fixture
    company_a_id = data["company"].id
    campaign_a_id = data["campaign"].id

    # Create Company B and Campaign B
    company_b = Company(name="Tenant Drilldown Co B")
    db_session.add(company_b)
    await db_session.flush()

    account_b = EmailAccount(
        company_id=company_b.id,
        name="Account B",
        email_address="sender_b@example.com",
    )
    db_session.add(account_b)
    await db_session.flush()

    campaign_b = Campaign(
        company_id=company_b.id,
        email_account_id=account_b.id,
        name="Campaign B",
        status=CampaignStatus.RUNNING.value,
    )
    db_session.add(campaign_b)
    await db_session.flush()

    recip_b = CampaignRecipient(
        campaign_id=campaign_b.id,
        email="b_lead@example.com",
        status=CampaignRecipientStatus.SENT.value,
    )
    db_session.add(recip_b)
    await db_session.flush()

    ev_b = EmailTrackingEvent(
        company_id=company_b.id,
        campaign_id=campaign_b.id,
        recipient_id=recip_b.id,
        event_type=TrackingEventType.OPEN.value,
        occurred_at=datetime.now(timezone.utc),
    )
    db_session.add(ev_b)
    await db_session.commit()

    # Query Company A / Campaign A -> should return 0 items
    resp_a = await CampaignService.get_campaign_recipient_engagement(
        db=db_session,
        company_id=company_a_id,
        campaign_id=campaign_a_id,
        event_type="OPEN",
    )
    assert resp_a.total == 0
    assert len(resp_a.items) == 0

    # Cross-tenant query attempt: Company A querying Campaign B raises 404
    with pytest.raises(HTTPException) as exc_info:
        await CampaignService.get_campaign_recipient_engagement(
            db=db_session,
            company_id=company_a_id,
            campaign_id=campaign_b.id,
            event_type="OPEN",
        )
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_pagination_and_stable_ordering(
    db_session: AsyncSession,
    drilldown_fixture: dict,
):
    """5. Verify pagination and stable descending ordering by most recent event."""
    data = drilldown_fixture
    company_id = data["company"].id
    campaign_id = data["campaign"].id
    recipients = data["recipients"]  # 5 recipients

    now = datetime.now(timezone.utc)
    # Stagger event times for recipients: r1 (t-5h), r2 (t-4h), r3 (t-3h), r4 (t-2h), r5 (t-1h)
    events = []
    for i, r in enumerate(recipients, start=1):
        ev = EmailTrackingEvent(
            company_id=company_id,
            campaign_id=campaign_id,
            recipient_id=r.id,
            event_type=TrackingEventType.OPEN.value,
            occurred_at=now - timedelta(hours=6 - i),
        )
        events.append(ev)
    db_session.add_all(events)
    await db_session.commit()

    # Page 1: limit 2, offset 0 -> Expected r5, r4 (most recent first)
    page1 = await CampaignService.get_campaign_recipient_engagement(
        db=db_session,
        company_id=company_id,
        campaign_id=campaign_id,
        event_type="OPEN",
        limit=2,
        offset=0,
    )
    assert page1.total == 5
    assert len(page1.items) == 2
    assert page1.items[0].recipient_id == recipients[4].id  # r5
    assert page1.items[1].recipient_id == recipients[3].id  # r4

    # Page 2: limit 2, offset 2 -> Expected r3, r2
    page2 = await CampaignService.get_campaign_recipient_engagement(
        db=db_session,
        company_id=company_id,
        campaign_id=campaign_id,
        event_type="OPEN",
        limit=2,
        offset=2,
    )
    assert page2.total == 5
    assert len(page2.items) == 2
    assert page2.items[0].recipient_id == recipients[2].id  # r3
    assert page2.items[1].recipient_id == recipients[1].id  # r2

    # Page 3: limit 2, offset 4 -> Expected r1
    page3 = await CampaignService.get_campaign_recipient_engagement(
        db=db_session,
        company_id=company_id,
        campaign_id=campaign_id,
        event_type="OPEN",
        limit=2,
        offset=4,
    )
    assert page3.total == 5
    assert len(page3.items) == 1
    assert page3.items[0].recipient_id == recipients[0].id  # r1


@pytest.mark.asyncio
async def test_missing_or_invalid_recipient_association_handling(
    db_session: AsyncSession,
    drilldown_fixture: dict,
):
    """6. Verify events with null recipient_id, orphaned recipient_id, or cross-campaign recipient are excluded."""
    data = drilldown_fixture
    company_id = data["company"].id
    campaign_id = data["campaign"].id
    valid_recipient = data["recipients"][0]

    # Create another campaign with its own recipient
    other_campaign = Campaign(
        company_id=company_id,
        email_account_id=data["account"].id,
        name="Other Campaign",
        status=CampaignStatus.RUNNING.value,
    )
    db_session.add(other_campaign)
    await db_session.flush()

    other_recipient = CampaignRecipient(
        campaign_id=other_campaign.id,
        email="other_recip@example.com",
        status=CampaignRecipientStatus.SENT.value,
    )
    db_session.add(other_recipient)
    await db_session.flush()

    now = datetime.now(timezone.utc)

    # 1. Event with NULL recipient_id
    ev_null_recip = EmailTrackingEvent(
        company_id=company_id,
        campaign_id=campaign_id,
        recipient_id=None,
        event_type=TrackingEventType.OPEN.value,
        occurred_at=now,
    )

    # 2. Event with orphaned/non-existent recipient_id
    ev_orphan_recip = EmailTrackingEvent(
        company_id=company_id,
        campaign_id=campaign_id,
        recipient_id=999999,
        event_type=TrackingEventType.OPEN.value,
        occurred_at=now,
    )

    # 3. Event with recipient belonging to another campaign
    ev_cross_campaign_recip = EmailTrackingEvent(
        company_id=company_id,
        campaign_id=campaign_id,  # Event tagged with this campaign
        recipient_id=other_recipient.id,  # But recipient belongs to other_campaign
        event_type=TrackingEventType.OPEN.value,
        occurred_at=now,
    )

    # 4. Valid event
    ev_valid = EmailTrackingEvent(
        company_id=company_id,
        campaign_id=campaign_id,
        recipient_id=valid_recipient.id,
        event_type=TrackingEventType.OPEN.value,
        occurred_at=now,
    )

    db_session.add_all([
        ev_null_recip,
        ev_orphan_recip,
        ev_cross_campaign_recip,
        ev_valid,
    ])
    await db_session.commit()

    resp = await CampaignService.get_campaign_recipient_engagement(
        db=db_session,
        company_id=company_id,
        campaign_id=campaign_id,
        event_type="OPEN",
    )

    # Only the valid recipient should be included
    assert resp.total == 1
    assert len(resp.items) == 1
    assert resp.items[0].recipient_id == valid_recipient.id


@pytest.mark.asyncio
async def test_drilldown_step_number_filtering(
    db_session: AsyncSession,
    drilldown_fixture: dict,
):
    """7. Verify step_number parameter filters recipient drilldown to events linked to deliveries of that step."""
    data = drilldown_fixture
    company_id = data["company"].id
    campaign = data["campaign"]
    step1 = data["step"]  # Step 1
    r1 = data["recipients"][0]
    r2 = data["recipients"][1]
    d1 = data["deliveries"][0]  # delivery for r1, step1

    # Create Step 2 (Follow-up) and Delivery for r2
    step2 = CampaignStep(
        campaign_id=campaign.id,
        step_number=2,
        subject="Drilldown Step 2 Follow-Up",
    )
    db_session.add(step2)
    await db_session.flush()

    d2 = CampaignDelivery(
        campaign_id=campaign.id,
        recipient_id=r2.id,
        step_id=step2.id,
        status=CampaignDeliveryStatus.SENT.value,
        sent_at=datetime.now(timezone.utc),
    )
    db_session.add(d2)
    await db_session.flush()

    now = datetime.now(timezone.utc)
    ev_step1 = EmailTrackingEvent(
        company_id=company_id,
        campaign_id=campaign.id,
        recipient_id=r1.id,
        delivery_id=d1.id,
        event_type=TrackingEventType.OPEN.value,
        occurred_at=now - timedelta(hours=1),
    )
    ev_step2 = EmailTrackingEvent(
        company_id=company_id,
        campaign_id=campaign.id,
        recipient_id=r2.id,
        delivery_id=d2.id,
        event_type=TrackingEventType.OPEN.value,
        occurred_at=now,
    )
    db_session.add_all([ev_step1, ev_step2])
    await db_session.commit()

    # Query All Campaign Emails (step_number=None) -> returns both r1 and r2
    resp_all = await CampaignService.get_campaign_recipient_engagement(
        db=db_session,
        company_id=company_id,
        campaign_id=campaign.id,
        event_type="OPEN",
    )
    assert resp_all.total == 2

    # Query Step 1 only -> returns only r1
    resp_step1 = await CampaignService.get_campaign_recipient_engagement(
        db=db_session,
        company_id=company_id,
        campaign_id=campaign.id,
        event_type="OPEN",
        step_number=1,
    )
    assert resp_step1.total == 1
    assert len(resp_step1.items) == 1
    assert resp_step1.items[0].recipient_id == r1.id

    # Query Step 2 only -> returns only r2
    resp_step2 = await CampaignService.get_campaign_recipient_engagement(
        db=db_session,
        company_id=company_id,
        campaign_id=campaign.id,
        event_type="OPEN",
        step_number=2,
    )
    assert resp_step2.total == 1
    assert len(resp_step2.items) == 1
    assert resp_step2.items[0].recipient_id == r2.id

    # Query non-existent step -> returns 0
    resp_nonexistent = await CampaignService.get_campaign_recipient_engagement(
        db=db_session,
        company_id=company_id,
        campaign_id=campaign.id,
        event_type="OPEN",
        step_number=99,
    )
    assert resp_nonexistent.total == 0
    assert len(resp_nonexistent.items) == 0
