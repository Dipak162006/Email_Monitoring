"""Targeted tests for campaign engagement metrics and classification analytics (T5.3).

Verifies:
1. Correct raw and unique open/click counts.
2. Correct bot/non-bot/unknown classification counts.
3. Campaign and company tenant isolation.
4. Zero-event campaign and safe division-by-zero rate handling.
5. Backward compatibility of CampaignAnalyticsResponse fields.
"""
from datetime import datetime, timezone
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
from app.modules.campaigns.service import CampaignService
from app.modules.email_accounts.models import EmailAccount
from app.modules.emails.models import (
    Email,
    EmailDirection,
    EmailStatus,
    EmailTrackingEvent,
    TrackingEventType,
)


@pytest.fixture
async def base_campaign_fixture(db_session: AsyncSession):
    """Seed test company, account, campaign with 2 steps, 3 recipients, and 3 deliveries."""
    company = Company(name="Engagement Metrics Co")
    db_session.add(company)
    await db_session.flush()

    account = EmailAccount(
        company_id=company.id,
        name="Sender Account",
        email_address="sender@metrics.com",
    )
    db_session.add(account)
    await db_session.flush()

    campaign = Campaign(
        company_id=company.id,
        email_account_id=account.id,
        name="Spring Engagement Campaign",
        status=CampaignStatus.RUNNING.value,
    )
    db_session.add(campaign)
    await db_session.flush()

    step1 = CampaignStep(
        campaign_id=campaign.id,
        step_number=1,
        subject="Initial Outreach",
    )
    step2 = CampaignStep(
        campaign_id=campaign.id,
        step_number=2,
        subject="Follow-up Message",
    )
    db_session.add_all([step1, step2])
    await db_session.flush()

    # 3 recipients
    recipients = []
    for i in range(1, 4):
        recip = CampaignRecipient(
            campaign_id=campaign.id,
            email=f"recipient_{i}@metrics.com",
            status=CampaignRecipientStatus.SENT.value,
        )
        db_session.add(recip)
        recipients.append(recip)
    await db_session.flush()

    # Deliveries for step 1
    deliveries = []
    for recip in recipients:
        email_rec = Email(
            company_id=company.id,
            email_account_id=account.id,
            direction=EmailDirection.OUTGOING.value,
            status=EmailStatus.SENT.value,
            sender="sender@metrics.com",
            recipients=[recip.email],
            subject="Initial Outreach",
        )
        db_session.add(email_rec)
        await db_session.flush()

        delivery = CampaignDelivery(
            campaign_id=campaign.id,
            recipient_id=recip.id,
            step_id=step1.id,
            email_id=email_rec.id,
            status=CampaignDeliveryStatus.SENT.value,
            sent_at=datetime.now(timezone.utc),
        )
        db_session.add(delivery)
        deliveries.append(delivery)

    await db_session.commit()

    return {
        "company": company,
        "campaign": campaign,
        "step1": step1,
        "step2": step2,
        "recipients": recipients,
        "deliveries": deliveries,
    }


@pytest.mark.asyncio
async def test_raw_and_unique_open_click_counts(
    db_session: AsyncSession,
    base_campaign_fixture: dict,
):
    """1. Verify correct raw and unique open/click counts and rate calculations."""
    data = base_campaign_fixture
    company_id = data["company"].id
    campaign_id = data["campaign"].id
    r1, r2, r3 = data["recipients"]
    d1, d2, d3 = data["deliveries"]

    # Recipient 1: 2 OPEN events, 1 CLICK event
    ev1 = EmailTrackingEvent(
        company_id=company_id,
        campaign_id=campaign_id,
        recipient_id=r1.id,
        delivery_id=d1.id,
        event_type=TrackingEventType.OPEN.value,
        occurred_at=datetime.now(timezone.utc),
    )
    ev2 = EmailTrackingEvent(
        company_id=company_id,
        campaign_id=campaign_id,
        recipient_id=r1.id,
        delivery_id=d1.id,
        event_type=TrackingEventType.OPEN.value,
        occurred_at=datetime.now(timezone.utc),
    )
    ev3 = EmailTrackingEvent(
        company_id=company_id,
        campaign_id=campaign_id,
        recipient_id=r1.id,
        delivery_id=d1.id,
        event_type=TrackingEventType.CLICK.value,
        occurred_at=datetime.now(timezone.utc),
    )

    # Recipient 2: 1 OPEN event, 2 CLICK events
    ev4 = EmailTrackingEvent(
        company_id=company_id,
        campaign_id=campaign_id,
        recipient_id=r2.id,
        delivery_id=d2.id,
        event_type=TrackingEventType.OPEN.value,
        occurred_at=datetime.now(timezone.utc),
    )
    ev5 = EmailTrackingEvent(
        company_id=company_id,
        campaign_id=campaign_id,
        recipient_id=r2.id,
        delivery_id=d2.id,
        event_type=TrackingEventType.CLICK.value,
        occurred_at=datetime.now(timezone.utc),
    )
    ev6 = EmailTrackingEvent(
        company_id=company_id,
        campaign_id=campaign_id,
        recipient_id=r2.id,
        delivery_id=d2.id,
        event_type=TrackingEventType.CLICK.value,
        occurred_at=datetime.now(timezone.utc),
    )

    # Unsubscribe event for recipient 1 (must NOT be counted in open/click metrics)
    ev_unsub = EmailTrackingEvent(
        company_id=company_id,
        campaign_id=campaign_id,
        recipient_id=r1.id,
        delivery_id=d1.id,
        event_type=TrackingEventType.UNSUBSCRIBE.value,
        occurred_at=datetime.now(timezone.utc),
    )

    db_session.add_all([ev1, ev2, ev3, ev4, ev5, ev6, ev_unsub])
    await db_session.commit()

    analytics = await CampaignService.get_campaign_analytics(
        db=db_session,
        company_id=company_id,
        campaign_id=campaign_id,
    )

    # Raw counts: 3 opens (2 from r1, 1 from r2), 3 clicks (1 from r1, 2 from r2)
    assert analytics.raw_open_count == 3
    assert analytics.raw_click_count == 3

    # Unique recipient counts: r1 and r2
    assert analytics.unique_open_recipients == 2
    assert analytics.unique_click_recipients == 2

    # Denominator for open_rate and click_rate is unique_recipients_sent (3 unique recipients with SENT delivery)
    assert analytics.total_sent_count == 3
    assert analytics.unique_recipients_sent == 3
    assert analytics.open_rate == round((2 / 3) * 100, 2)
    assert analytics.click_rate == round((2 / 3) * 100, 2)

    # Structured engagement sub-object matches
    assert analytics.engagement is not None
    assert analytics.engagement.unique_recipients_sent == 3
    assert analytics.engagement.raw_open_count == 3
    assert analytics.engagement.unique_open_recipients == 2
    assert analytics.engagement.raw_click_count == 3
    assert analytics.engagement.unique_click_recipients == 2
    assert analytics.engagement.unique_clicked_destinations is None


@pytest.mark.asyncio
async def test_bot_non_bot_unknown_classification_counts(
    db_session: AsyncSession,
    base_campaign_fixture: dict,
):
    """2. Verify conservative bot, non-bot, and unknown classification counts."""
    data = base_campaign_fixture
    company_id = data["company"].id
    campaign_id = data["campaign"].id
    r1 = data["recipients"][0]
    d1 = data["deliveries"][0]

    # Bot open & click
    ev_bot_open = EmailTrackingEvent(
        company_id=company_id,
        campaign_id=campaign_id,
        recipient_id=r1.id,
        delivery_id=d1.id,
        event_type=TrackingEventType.OPEN.value,
        is_bot=True,
        bot_reason="AppleImageProxy",
        bot_confidence=1.0,
    )
    ev_bot_click = EmailTrackingEvent(
        company_id=company_id,
        campaign_id=campaign_id,
        recipient_id=r1.id,
        delivery_id=d1.id,
        event_type=TrackingEventType.CLICK.value,
        is_bot=True,
        bot_reason="Google-Proxy",
        bot_confidence=0.95,
    )

    # Non-bot open & click
    ev_non_bot_open = EmailTrackingEvent(
        company_id=company_id,
        campaign_id=campaign_id,
        recipient_id=r1.id,
        delivery_id=d1.id,
        event_type=TrackingEventType.OPEN.value,
        is_bot=False,
        bot_reason=None,
    )
    ev_non_bot_click = EmailTrackingEvent(
        company_id=company_id,
        campaign_id=campaign_id,
        recipient_id=r1.id,
        delivery_id=d1.id,
        event_type=TrackingEventType.CLICK.value,
        is_bot=False,
        bot_reason=None,
    )

    # Unknown classification open & click
    ev_unknown_open = EmailTrackingEvent(
        company_id=company_id,
        campaign_id=campaign_id,
        recipient_id=r1.id,
        delivery_id=d1.id,
        event_type=TrackingEventType.OPEN.value,
        is_bot=None,
    )
    ev_unknown_click = EmailTrackingEvent(
        company_id=company_id,
        campaign_id=campaign_id,
        recipient_id=r1.id,
        delivery_id=d1.id,
        event_type=TrackingEventType.CLICK.value,
        is_bot=None,
    )

    # Bot unsubscribe event (must NOT be counted in engagement classification)
    ev_unsub_bot = EmailTrackingEvent(
        company_id=company_id,
        campaign_id=campaign_id,
        recipient_id=r1.id,
        delivery_id=d1.id,
        event_type=TrackingEventType.UNSUBSCRIBE.value,
        is_bot=True,
    )

    db_session.add_all([
        ev_bot_open,
        ev_bot_click,
        ev_non_bot_open,
        ev_non_bot_click,
        ev_unknown_open,
        ev_unknown_click,
        ev_unsub_bot,
    ])
    await db_session.commit()

    analytics = await CampaignService.get_campaign_analytics(
        db=db_session,
        company_id=company_id,
        campaign_id=campaign_id,
    )

    # Overall totals across OPEN + CLICK (excluding UNSUBSCRIBE)
    assert analytics.bot_events_count == 2
    assert analytics.non_bot_events_count == 2
    assert analytics.unknown_events_count == 2

    # Granular classification breakdown
    assert analytics.classification is not None
    assert analytics.classification.bot_events_count == 2
    assert analytics.classification.non_bot_events_count == 2
    assert analytics.classification.unknown_events_count == 2

    assert analytics.classification.bot_open_count == 1
    assert analytics.classification.non_bot_open_count == 1
    assert analytics.classification.unknown_open_count == 1

    assert analytics.classification.bot_click_count == 1
    assert analytics.classification.non_bot_click_count == 1
    assert analytics.classification.unknown_click_count == 1


@pytest.mark.asyncio
async def test_campaign_and_company_isolation(
    db_session: AsyncSession,
    base_campaign_fixture: dict,
):
    """3. Verify strict campaign and company tenant isolation."""
    data = base_campaign_fixture
    company_a_id = data["company"].id
    campaign_a_id = data["campaign"].id

    # Create Company B with Campaign B
    company_b = Company(name="Tenant Isolation Co B")
    db_session.add(company_b)
    await db_session.flush()

    account_b = EmailAccount(
        company_id=company_b.id,
        name="Account B",
        email_address="b@tenant.com",
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

    # Add tracking event for Campaign B
    ev_b = EmailTrackingEvent(
        company_id=company_b.id,
        campaign_id=campaign_b.id,
        event_type=TrackingEventType.OPEN.value,
        is_bot=False,
    )
    db_session.add(ev_b)
    await db_session.commit()

    # Analytics for Campaign A should have 0 events from Campaign B
    analytics_a = await CampaignService.get_campaign_analytics(
        db=db_session,
        company_id=company_a_id,
        campaign_id=campaign_a_id,
    )
    assert analytics_a.raw_open_count == 0
    assert analytics_a.bot_events_count == 0
    assert analytics_a.non_bot_events_count == 0

    # Cross-tenant query attempt: Company A querying Campaign B raises HTTP 404
    with pytest.raises(HTTPException) as exc_info:
        await CampaignService.get_campaign_analytics(
            db=db_session,
            company_id=company_a_id,
            campaign_id=campaign_b.id,
        )
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_zero_event_campaign_and_division_by_zero_handling(
    db_session: AsyncSession,
):
    """4. Verify zero-event campaign and safe division-by-zero handling."""
    company = Company(name="Zero Events Co")
    db_session.add(company)
    await db_session.flush()

    account = EmailAccount(
        company_id=company.id,
        name="Empty Sender",
        email_address="empty@example.com",
    )
    db_session.add(account)
    await db_session.flush()

    campaign = Campaign(
        company_id=company.id,
        email_account_id=account.id,
        name="Brand New Empty Campaign",
        status=CampaignStatus.DRAFT.value,
    )
    db_session.add(campaign)
    await db_session.commit()

    analytics = await CampaignService.get_campaign_analytics(
        db=db_session,
        company_id=company.id,
        campaign_id=campaign.id,
    )

    # Safe zero values for all rates and counts without ZeroDivisionError
    assert analytics.total_recipients == 0
    assert analytics.total_sent_count == 0
    assert analytics.delivered_count == 0
    assert analytics.bounced_count == 0
    assert analytics.failed_count == 0
    assert analytics.suppressed_count == 0

    assert analytics.raw_open_count == 0
    assert analytics.unique_open_recipients == 0
    assert analytics.open_rate == 0.0

    assert analytics.raw_click_count == 0
    assert analytics.unique_click_recipients == 0
    assert analytics.click_rate == 0.0

    assert analytics.bot_events_count == 0
    assert analytics.non_bot_events_count == 0
    assert analytics.unknown_events_count == 0

    assert analytics.delivery is not None
    assert analytics.delivery.delivery_rate == 0.0
    assert analytics.engagement is not None
    assert analytics.engagement.click_to_open_rate == 0.0


@pytest.mark.asyncio
async def test_existing_analytics_response_compatibility(
    db_session: AsyncSession,
    base_campaign_fixture: dict,
):
    """5. Verify backward compatibility of CampaignAnalyticsResponse fields."""
    data = base_campaign_fixture
    company_id = data["company"].id
    campaign_id = data["campaign"].id

    analytics = await CampaignService.get_campaign_analytics(
        db=db_session,
        company_id=company_id,
        campaign_id=campaign_id,
    )

    # Legacy fields required by frontend and API consumers
    assert analytics.campaign_id == campaign_id
    assert analytics.campaign_name == "Spring Engagement Campaign"
    assert analytics.campaign_status == CampaignStatus.RUNNING.value
    assert analytics.total_recipients == 3
    assert analytics.total_steps == 2
    assert analytics.initial_sent_count == 3
    assert analytics.followup_sent_count == 0
    assert analytics.total_sent_count == 3
    assert analytics.unique_replied_count == 0
    assert isinstance(analytics.steps, list)
    assert len(analytics.steps) == 2
    assert isinstance(analytics.delivery_trend, list)

    # Per-step analytics contains valid step properties
    step1 = analytics.steps[0]
    assert step1.step_number == 1
    assert step1.sent_count == 3
    assert step1.delivery_rate >= 0.0
    assert step1.reply_rate == 0.0
    assert step1.bounce_rate == 0.0

    # Ensure model serialization to dict works cleanly without schema validation errors
    dumped = analytics.model_dump()
    assert "delivery" in dumped
    assert "engagement" in dumped
    assert "classification" in dumped
    assert "raw_open_count" in dumped
    assert "raw_click_count" in dumped
    assert "open_rate" in dumped
    assert "click_rate" in dumped


@pytest.mark.asyncio
async def test_multiple_sends_to_same_recipient_count_as_one_unique_recipient_sent(
    db_session: AsyncSession,
):
    """6. Verify multiple sends to the same recipient count as 1 unique recipient sent,
    and open/click rates use unique_recipients_sent as their denominator.
    """
    company = Company(name="Multi Step Co")
    db_session.add(company)
    await db_session.flush()

    account = EmailAccount(
        company_id=company.id,
        name="Multi Step Sender",
        email_address="multisender@example.com",
    )
    db_session.add(account)
    await db_session.flush()

    campaign = Campaign(
        company_id=company.id,
        email_account_id=account.id,
        name="Multi Step Campaign",
        status=CampaignStatus.RUNNING.value,
    )
    db_session.add(campaign)
    await db_session.flush()

    step1 = CampaignStep(campaign_id=campaign.id, step_number=1, subject="Step 1")
    step2 = CampaignStep(campaign_id=campaign.id, step_number=2, subject="Step 2")
    db_session.add_all([step1, step2])
    await db_session.flush()

    recipient = CampaignRecipient(
        campaign_id=campaign.id,
        email="solo_lead@target.com",
        status=CampaignRecipientStatus.SENT.value,
    )
    db_session.add(recipient)
    await db_session.flush()

    # Create 2 separate sent deliveries to the SAME recipient across step 1 and step 2
    deliv1 = CampaignDelivery(
        campaign_id=campaign.id,
        recipient_id=recipient.id,
        step_id=step1.id,
        status=CampaignDeliveryStatus.SENT.value,
        sent_at=datetime.now(timezone.utc),
    )
    deliv2 = CampaignDelivery(
        campaign_id=campaign.id,
        recipient_id=recipient.id,
        step_id=step2.id,
        status=CampaignDeliveryStatus.SENT.value,
        sent_at=datetime.now(timezone.utc),
    )
    db_session.add_all([deliv1, deliv2])
    await db_session.flush()

    # The recipient opens once
    ev_open = EmailTrackingEvent(
        company_id=company.id,
        campaign_id=campaign.id,
        recipient_id=recipient.id,
        delivery_id=deliv1.id,
        event_type=TrackingEventType.OPEN.value,
    )
    db_session.add(ev_open)
    await db_session.commit()

    analytics = await CampaignService.get_campaign_analytics(
        db=db_session,
        company_id=company.id,
        campaign_id=campaign.id,
    )

    # Total sends across steps = 2, but unique recipients sent = 1
    assert analytics.total_sent_count == 2
    assert analytics.unique_recipients_sent == 1
    assert analytics.unique_open_recipients == 1

    # Recipient-level open rate must be 100.0% (1 / 1 * 100), NOT 50.0% (1 / 2 * 100)
    assert analytics.open_rate == 100.0
    assert analytics.engagement.open_rate == 100.0


@pytest.mark.asyncio
async def test_estimated_delivery_is_not_represented_as_confirmed_delivery(
    db_session: AsyncSession,
    base_campaign_fixture: dict,
):
    """7. Verify estimated delivery metric is explicitly documented and exposed as an estimate."""
    data = base_campaign_fixture
    company_id = data["company"].id
    campaign_id = data["campaign"].id

    analytics = await CampaignService.get_campaign_analytics(
        db=db_session,
        company_id=company_id,
        campaign_id=campaign_id,
    )

    # Verify both estimated_delivered_count and delivered_count exist and match (sent - bounced)
    expected_delivered = analytics.total_sent_count - analytics.bounced_count
    assert analytics.estimated_delivered_count == expected_delivered
    assert analytics.delivered_count == expected_delivered
    assert analytics.delivery.estimated_delivered_count == expected_delivered

    # Verify schema descriptions do not claim confirmed mailbox delivery
    from app.modules.campaigns.schemas import CampaignDeliveryMetrics, CampaignAnalyticsResponse
    deliv_desc = CampaignDeliveryMetrics.model_fields["estimated_delivered_count"].description
    assert "estimate only" in deliv_desc.lower()
    assert "not confirmed mailbox delivery" in deliv_desc.lower()

    resp_desc = CampaignAnalyticsResponse.model_fields["delivered_count"].description
    assert "actual mailbox receipt is not tracked" in resp_desc.lower()


@pytest.mark.asyncio
async def test_step_level_multiple_sends_to_same_recipient_uses_distinct_denominator(
    db_session: AsyncSession,
):
    """8. T5.5.2: Verify step-level engagement metrics use distinct-recipient denominator."""
    company = Company(name="Step Metrics Denominator Co")
    db_session.add(company)
    await db_session.flush()

    account = EmailAccount(
        company_id=company.id,
        name="Step Sender",
        email_address="sender@stepmetrics.com",
    )
    db_session.add(account)
    await db_session.flush()

    campaign = Campaign(
        company_id=company.id,
        email_account_id=account.id,
        name="Step Denominator Campaign",
        status=CampaignStatus.RUNNING.value,
    )
    db_session.add(campaign)
    await db_session.flush()

    step1 = CampaignStep(
        campaign_id=campaign.id,
        step_number=1,
        subject="Step 1 Outreach",
        delay_hours=0,
    )
    db_session.add(step1)
    await db_session.flush()

    recip1 = CampaignRecipient(
        campaign_id=campaign.id,
        email="recip1@test.com",
        status=CampaignRecipientStatus.SENT.value,
    )
    recip2 = CampaignRecipient(
        campaign_id=campaign.id,
        email="recip2@test.com",
        status=CampaignRecipientStatus.SENT.value,
    )
    db_session.add_all([recip1, recip2])
    await db_session.flush()

    # Step 1: recip1 and recip2 receive SENT deliveries
    # Total sent = 2, Unique recipients sent = 2
    deliv1 = CampaignDelivery(
        campaign_id=campaign.id,
        step_id=step1.id,
        recipient_id=recip1.id,
        status=CampaignDeliveryStatus.SENT.value,
        sent_at=datetime.now(timezone.utc),
    )
    deliv2 = CampaignDelivery(
        campaign_id=campaign.id,
        step_id=step1.id,
        recipient_id=recip2.id,
        status=CampaignDeliveryStatus.SENT.value,
        sent_at=datetime.now(timezone.utc),
    )
    db_session.add_all([deliv1, deliv2])
    await db_session.flush()

    # Only recip1 opens and clicks
    ev_open = EmailTrackingEvent(
        company_id=company.id,
        campaign_id=campaign.id,
        recipient_id=recip1.id,
        delivery_id=deliv1.id,
        event_type=TrackingEventType.OPEN.value,
    )
    ev_click = EmailTrackingEvent(
        company_id=company.id,
        campaign_id=campaign.id,
        recipient_id=recip1.id,
        delivery_id=deliv1.id,
        event_type=TrackingEventType.CLICK.value,
    )
    db_session.add_all([ev_open, ev_click])
    await db_session.commit()

    analytics = await CampaignService.get_campaign_analytics(
        db=db_session,
        company_id=company.id,
        campaign_id=campaign.id,
    )

    assert len(analytics.steps) == 1
    s1 = analytics.steps[0]

    # total_sent is 2, unique_recipients_sent is 2
    assert s1.sent_count == 2
    assert s1.unique_recipients_sent == 2

    # 1 unique open / 2 unique sent = 50.0%
    assert s1.unique_open_recipients == 1
    assert s1.open_rate == 50.0

    # 1 unique click / 2 unique sent = 50.0%
    assert s1.unique_click_recipients == 1
    assert s1.click_rate == 50.0

    # CTOR: 1 unique click / 1 unique open = 100.0%
    assert s1.click_to_open_rate == 100.0

    # Campaign-level metrics preserved
    assert analytics.total_sent_count == 2
    assert analytics.unique_recipients_sent == 2
    assert analytics.open_rate == 50.0
    assert analytics.click_rate == 50.0


@pytest.mark.asyncio
async def test_step_level_zero_denominator_returns_zero(
    db_session: AsyncSession,
):
    """9. T5.5.2: Verify zero denominator in step returns 0.0 without division error."""
    company = Company(name="Step Zero Co")
    db_session.add(company)
    await db_session.flush()

    account = EmailAccount(
        company_id=company.id,
        name="Sender",
        email_address="zero@step.com",
    )
    db_session.add(account)
    await db_session.flush()

    campaign = Campaign(
        company_id=company.id,
        email_account_id=account.id,
        name="Zero Step Campaign",
        status=CampaignStatus.DRAFT.value,
    )
    db_session.add(campaign)
    await db_session.flush()

    step1 = CampaignStep(
        campaign_id=campaign.id,
        step_number=1,
        subject="Draft Step",
        delay_hours=0,
    )
    db_session.add(step1)
    await db_session.commit()

    analytics = await CampaignService.get_campaign_analytics(
        db=db_session,
        company_id=company.id,
        campaign_id=campaign.id,
    )

    assert len(analytics.steps) == 1
    s = analytics.steps[0]
    assert s.sent_count == 0
    assert s.unique_recipients_sent == 0
    assert s.open_rate == 0.0
    assert s.click_rate == 0.0
    assert s.click_to_open_rate == 0.0


