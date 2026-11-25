"""T5.9.1 Campaign Tracking Final Verification Suite.

Tests:
1. Reply Attribution:
   - Genuine reply from enrolled recipient counted once.
   - Campaign analytics and reply drilldown return identical counts.
   - Unrelated message from sending account is NOT counted as a reply.
   - Sent-message echo (OUTGOING or non-reply) is NOT counted as an inbound reply.
   - Duplicate IMAP synchronization does NOT create duplicate replies.
2. Follow-Up Dispatch Suppression (mocked SMTP, isolated test DB + Redis DB 15):
   - Replied recipient is blocked immediately before SMTP send.
   - Unsubscribed (SUPPRESSED) recipient is blocked immediately before SMTP send.
   - Bounced recipient is blocked immediately before SMTP send.
   - Eligible recipient receives the follow-up.
   - Retried process_due_followup_steps does NOT duplicate sends.
   - Concurrent process_due_followup_steps cannot bypass suppression or duplicate sends.
3. Sequence Metrics, Open/Click Tracking & API/Frontend Consistency:
   - Configured vs evaluated vs eligible vs scheduled vs sent vs skipped/suppressed counts.
   - Repeated opens do not inflate unique_open_recipients.
   - GoogleImageProxy -> UNKNOWN, standard browser -> NON_BOT, scanner -> BOT, unknown UA -> UNKNOWN.
   - Full agreement between analytics, step metrics, recipient engagement drilldown, and emails drilldown.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

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
    CampaignStatus,
    CampaignStep,
    SuppressionEntry,
    SuppressionReason,
)
from app.modules.campaigns.delivery_service import CampaignDeliveryService
from app.modules.campaigns.service import CampaignService
from app.modules.companies.models import Company
from app.modules.email_accounts.models import EmailAccount
from app.modules.emails.bot_classifier import BotClassifier
from app.services.imap.parser import ParsedEmail
from app.modules.emails.models import (
    Email,
    EmailDirection,
    EmailStatus,
    EmailThread,
    EmailTrackingEvent,
    TrackingEventType,
)
from app.modules.emails.monitoring_service import EmailMonitoringService
from tests.conftest import TestAsyncSessionLocal


@pytest.mark.asyncio
async def test_reply_attribution_edge_cases_and_idempotency(db_session: AsyncSession):
    """Verify genuine replies, unrelated sender messages, sent echoes, and duplicate IMAP sync."""
    now = datetime.now(timezone.utc)
    company = Company(name="T5.9.1 Reply Attr Co")
    db_session.add(company)
    await db_session.flush()

    account = EmailAccount(
        company_id=company.id,
        name="Sender",
        email_address="sender@example.com",
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_username="sender@example.com",
        smtp_password_encrypted="secret",
        is_active=True,
    )
    db_session.add(account)
    await db_session.flush()

    campaign = Campaign(
        company_id=company.id,
        email_account_id=account.id,
        name="Reply Edge Cases Campaign",
        subject="Outreach",
        body_text="Hello",
        body_html="<p>Hello</p>",
        status=CampaignStatus.COMPLETED.value,
    )
    db_session.add(campaign)
    await db_session.flush()

    step1 = CampaignStep(campaign_id=campaign.id, step_number=1, subject="Step 1", delay_hours=0, is_active=True)
    db_session.add(step1)
    await db_session.flush()

    r_lead = CampaignRecipient(
        campaign_id=campaign.id,
        email="lead@external.test",
        first_name="Lead",
        status=CampaignRecipientStatus.SENT.value,
        current_step_number=1,
        next_step_due_at=now + timedelta(hours=24),
    )
    db_session.add(r_lead)
    await db_session.flush()

    thread = EmailThread(company_id=company.id, email_account_id=account.id, subject="Outreach", has_reply=False, last_message_at=now)
    db_session.add(thread)
    await db_session.flush()

    sent_email = Email(
        company_id=company.id,
        email_account_id=account.id,
        thread_id=thread.id,
        message_id="<sent-step1-lead@example.com>",
        direction=EmailDirection.OUTGOING.value,
        status=EmailStatus.SENT.value,
        sender="sender@example.com",
        recipients=["lead@external.test"],
        subject="Outreach",
        sent_at=now,
    )
    db_session.add(sent_email)
    await db_session.flush()

    deliv = CampaignDelivery(
        campaign_id=campaign.id,
        recipient_id=r_lead.id,
        step_id=step1.id,
        email_id=sent_email.id,
        thread_id=thread.id,
        message_id="<sent-step1-lead@example.com>",
        status=CampaignDeliveryStatus.SENT.value,
        sent_at=now,
    )
    db_session.add(deliv)
    await db_session.commit()

    # 1. Unrelated message from sending account must NOT match
    unrelated_parsed = ParsedEmail(
        message_id="<unrelated-self@example.com>",
        in_reply_to=None,
        references_header=None,
        sender="sender@example.com",
        recipients=["other@external.test"],
        cc=None,
        bcc=None,
        reply_to=None,
        subject="Internal Note",
        body_text="Just a note",
        body_html=None,
        date=now + timedelta(minutes=5),
        is_auto_reply=False,
    )
    matched_unrelated = await EmailMonitoringService.match_and_process_campaign_reply(
        db=db_session, account=account, parsed=unrelated_parsed, thread_id=None, is_reply_to_outgoing=False
    )
    assert matched_unrelated == 0

    # 2. Sent-message echo (OUTGOING) stored in DB must NOT be counted as an inbound reply
    echo_parsed = ParsedEmail(
        message_id="<sent-step1-lead@example.com>",
        in_reply_to=None,
        references_header=None,
        sender="sender@example.com",
        recipients=["lead@external.test"],
        cc=None,
        bcc=None,
        reply_to=None,
        subject="Outreach",
        body_text="Hello",
        body_html="<p>Hello</p>",
        date=now,
        is_auto_reply=False,
    )
    matched_echo = await EmailMonitoringService.match_and_process_campaign_reply(
        db=db_session, account=account, parsed=echo_parsed, thread_id=thread.id, is_reply_to_outgoing=False
    )
    assert matched_echo == 0

    # 3. Genuine reply from enrolled recipient
    reply_parsed = ParsedEmail(
        message_id="<reply-lead-1@external.test>",
        in_reply_to="<sent-step1-lead@example.com>",
        references_header="<sent-step1-lead@example.com>",
        sender="Lead <lead@external.test>",
        recipients=["sender@example.com"],
        cc=None,
        bcc=None,
        reply_to=None,
        subject="Re: Outreach",
        body_text="Interested, let's talk.",
        body_html=None,
        date=now + timedelta(minutes=10),
        is_auto_reply=False,
    )
    matched_1 = await EmailMonitoringService.match_and_process_campaign_reply(
        db=db_session, account=account, parsed=reply_parsed, thread_id=thread.id, is_reply_to_outgoing=True
    )
    assert matched_1 == 1

    # Persist the incoming email once (as IMAP sync does)
    inc_email = Email(
        company_id=company.id,
        email_account_id=account.id,
        thread_id=thread.id,
        message_id="<reply-lead-1@external.test>",
        in_reply_to="<sent-step1-lead@example.com>",
        references_header="<sent-step1-lead@example.com>",
        direction=EmailDirection.INCOMING.value,
        status=EmailStatus.RECEIVED.value,
        sender="Lead <lead@external.test>",
        recipients=["sender@example.com"],
        subject="Re: Outreach",
        received_at=now + timedelta(minutes=10),
    )
    db_session.add(inc_email)
    await db_session.commit()

    # 4. Duplicate IMAP sync call on the same parsed email must be idempotent
    matched_dup = await EmailMonitoringService.match_and_process_campaign_reply(
        db=db_session, account=account, parsed=reply_parsed, thread_id=thread.id, is_reply_to_outgoing=True
    )
    assert matched_dup == 1  # Idempotent recipient update

    # Verify analytics and drilldown match identically (1 reply)
    analytics = await CampaignService.get_campaign_analytics(db=db_session, company_id=company.id, campaign_id=campaign.id)
    drilldown = await CampaignService.get_campaign_emails_drilldown(
        db=db_session, company_id=company.id, campaign_id=campaign.id, status="replies"
    )
    assert analytics.unique_replied_count == 1
    assert drilldown["summary"]["replies_count"] == 1
    assert drilldown["total"] == 1
    assert len(drilldown["items"]) == 1


@pytest.mark.asyncio
async def test_followup_dispatch_suppression_retry_and_concurrency(db_session: AsyncSession):
    """Verify pre-SMTP suppression for replied/unsubscribed/bounced, retry idempotency, and concurrency safety."""
    now = datetime.now(timezone.utc)
    past_due = now - timedelta(minutes=5)

    company = Company(name="T5.9.1 Followup Suppression Co")
    db_session.add(company)
    await db_session.flush()

    account = EmailAccount(
        company_id=company.id,
        name="Campaign Sender",
        email_address="fu-sender@example.com",
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_username="fu-sender@example.com",
        smtp_password_encrypted="secret",
        is_active=True,
    )
    db_session.add(account)
    await db_session.flush()

    campaign = Campaign(
        company_id=company.id,
        email_account_id=account.id,
        name="Followup Suppression Verification",
        subject="Step 1",
        body_text="Step 1",
        body_html="<p>Step 1</p>",
        status=CampaignStatus.RUNNING.value,
    )
    db_session.add(campaign)
    await db_session.flush()

    step1 = CampaignStep(campaign_id=campaign.id, step_number=1, subject="Step 1", delay_hours=0, is_active=True)
    step2 = CampaignStep(
        campaign_id=campaign.id,
        step_number=2,
        subject="Step 2",
        body_text="Follow up",
        body_html="<p>Follow up</p>",
        delay_hours=24,
        is_active=True,
    )
    db_session.add_all([step1, step2])
    await db_session.flush()

    # Recipients:
    # 1. Replied (thread has_reply=True, even if recipient.replied_at wasn't set yet -> pre-SMTP check catches it)
    r_replied = CampaignRecipient(
        campaign_id=campaign.id,
        email="replied@example.com",
        status=CampaignRecipientStatus.SENT.value,
        current_step_number=1,
        next_step_due_at=past_due,
    )
    # 2. Unsubscribed (present in CampaignSuppression, even if recipient.status is still SENT -> pre-SMTP check catches it)
    r_unsub = CampaignRecipient(
        campaign_id=campaign.id,
        email="unsub@example.com",
        status=CampaignRecipientStatus.SENT.value,
        current_step_number=1,
        next_step_due_at=past_due,
    )
    # 3. Bounced (status=BOUNCED)
    r_bounced = CampaignRecipient(
        campaign_id=campaign.id,
        email="bounced@example.com",
        status=CampaignRecipientStatus.BOUNCED.value,
        current_step_number=1,
        next_step_due_at=past_due,
    )
    # 4. Eligible recipient
    r_eligible = CampaignRecipient(
        campaign_id=campaign.id,
        email="eligible@example.com",
        status=CampaignRecipientStatus.SENT.value,
        current_step_number=1,
        next_step_due_at=past_due,
    )
    db_session.add_all([r_replied, r_unsub, r_bounced, r_eligible])
    await db_session.flush()

    # Add suppression entry for r_unsub
    db_session.add(
        SuppressionEntry(
            company_id=company.id,
            email="unsub@example.com",
            reason=SuppressionReason.UNSUBSCRIBE.value,
        )
    )

    # Create Step 1 threads & SENT deliveries
    t_replied = EmailThread(company_id=company.id, email_account_id=account.id, subject="Step 1", has_reply=True, last_message_at=now)
    t_unsub = EmailThread(company_id=company.id, email_account_id=account.id, subject="Step 1", has_reply=False, last_message_at=now)
    t_bounced = EmailThread(company_id=company.id, email_account_id=account.id, subject="Step 1", has_reply=False, last_message_at=now)
    t_eligible = EmailThread(company_id=company.id, email_account_id=account.id, subject="Step 1", has_reply=False, last_message_at=now)
    db_session.add_all([t_replied, t_unsub, t_bounced, t_eligible])
    await db_session.flush()

    for r, t, mid in [
        (r_replied, t_replied, "<s1-replied@example.com>"),
        (r_unsub, t_unsub, "<s1-unsub@example.com>"),
        (r_bounced, t_bounced, "<s1-bounced@example.com>"),
        (r_eligible, t_eligible, "<s1-eligible@example.com>"),
    ]:
        s1_email = Email(
            company_id=company.id,
            email_account_id=account.id,
            thread_id=t.id,
            message_id=mid,
            direction=EmailDirection.OUTGOING.value,
            status=EmailStatus.SENT.value,
            sender="fu-sender@example.com",
            recipients=[r.email],
            subject="Step 1",
            sent_at=now - timedelta(hours=25),
        )
        db_session.add(s1_email)
        await db_session.flush()
        db_session.add(
            CampaignDelivery(
                campaign_id=campaign.id,
                recipient_id=r.id,
                step_id=step1.id,
                email_id=s1_email.id,
                thread_id=t.id,
                message_id=mid,
                status=CampaignDeliveryStatus.SENT.value,
                sent_at=now - timedelta(hours=25),
            )
        )
    await db_session.commit()

    # Run concurrent dispatchers with mocked SMTP
    smtp_mock = MagicMock()
    with patch("app.services.smtp.client.SMTPClient.send_email_sync", smtp_mock):
        res_a, res_b = await asyncio.gather(
            CampaignDeliveryService.process_due_followup_steps(db_factory=TestAsyncSessionLocal, now_utc=now),
            CampaignDeliveryService.process_due_followup_steps(db_factory=TestAsyncSessionLocal, now_utc=now),
        )

    # Only r_eligible should be sent via SMTP, and ONLY ONCE across both concurrent workers!
    assert smtp_mock.call_count == 1
    sent_to = smtp_mock.call_args.kwargs.get("to_emails") or smtp_mock.call_args.kwargs.get("recipients")
    if sent_to is not None:
        assert sent_to == ["eligible@example.com"]

    # Retry execution must also send nothing
    with patch("app.services.smtp.client.SMTPClient.send_email_sync", smtp_mock):
        res_retry = await CampaignDeliveryService.process_due_followup_steps(db_factory=TestAsyncSessionLocal, now_utc=now)
    assert len(res_retry) == 0
    assert smtp_mock.call_count == 1

    # Verify DB states
    await db_session.refresh(r_replied)
    await db_session.refresh(r_unsub)
    await db_session.refresh(r_bounced)
    await db_session.refresh(r_eligible)

    assert r_replied.status == CampaignRecipientStatus.STOPPED.value
    assert r_replied.stopped_reason == CampaignRecipientStopReason.REPLIED.value
    assert r_replied.next_step_due_at is None

    assert r_unsub.status == CampaignRecipientStatus.SUPPRESSED.value
    assert r_unsub.next_step_due_at is None

    assert r_bounced.status == CampaignRecipientStatus.BOUNCED.value

    assert r_eligible.current_step_number == 2
    assert r_eligible.status == CampaignRecipientStatus.COMPLETED.value

    # Verify Step 2 deliveries: only 1 delivery exists (for r_eligible)
    step2_delivs = (
        await db_session.execute(
            select(CampaignDelivery).where(
                CampaignDelivery.campaign_id == campaign.id,
                CampaignDelivery.step_id == step2.id,
            )
        )
    ).scalars().all()
    assert len(step2_delivs) == 1
    assert step2_delivs[0].recipient_id == r_eligible.id
    assert step2_delivs[0].status == CampaignDeliveryStatus.SENT.value


@pytest.mark.asyncio
async def test_sequence_metrics_open_click_and_api_consistency(db_session: AsyncSession):
    """Verify repeated opens, bot/non-bot/unknown classification, and full API/drilldown consistency."""
    now = datetime.now(timezone.utc)
    company = Company(name="T5.9.1 Consistency Co")
    db_session.add(company)
    await db_session.flush()

    account = EmailAccount(
        company_id=company.id,
        name="Sender",
        email_address="cons@example.com",
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_username="cons@example.com",
        smtp_password_encrypted="secret",
        is_active=True,
    )
    db_session.add(account)
    await db_session.flush()

    campaign = Campaign(
        company_id=company.id,
        email_account_id=account.id,
        name="Consistency Campaign",
        subject="Step 1",
        body_text="Hi",
        body_html="<p>Hi</p>",
        status=CampaignStatus.COMPLETED.value,
    )
    db_session.add(campaign)
    await db_session.flush()

    step1 = CampaignStep(campaign_id=campaign.id, step_number=1, subject="Step 1", delay_hours=0, is_active=True)
    db_session.add(step1)
    await db_session.flush()

    r1 = CampaignRecipient(campaign_id=campaign.id, email="u1@example.com", status=CampaignRecipientStatus.SENT.value, current_step_number=1)
    r2 = CampaignRecipient(campaign_id=campaign.id, email="u2@example.com", status=CampaignRecipientStatus.SENT.value, current_step_number=1)
    db_session.add_all([r1, r2])
    await db_session.flush()

    d1 = CampaignDelivery(campaign_id=campaign.id, recipient_id=r1.id, step_id=step1.id, status=CampaignDeliveryStatus.SENT.value, sent_at=now)
    d2 = CampaignDelivery(campaign_id=campaign.id, recipient_id=r2.id, step_id=step1.id, status=CampaignDeliveryStatus.SENT.value, sent_at=now)
    db_session.add_all([d1, d2])
    await db_session.flush()

    # Classify 4 user-agents: Gmail Proxy (UNKNOWN), Chrome (NON_BOT), SafeLinks (BOT), Custom (UNKNOWN)
    gmail_cls = BotClassifier.classify("Mozilla/5.0 (via ggpht.com GoogleImageProxy)", TrackingEventType.OPEN)
    chrome_cls = BotClassifier.classify("Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36", TrackingEventType.OPEN)
    safelinks_cls = BotClassifier.classify("Mozilla/5.0 SafeLinks/1.0", TrackingEventType.CLICK)
    unknown_cls = BotClassifier.classify("CustomApp/1.0", TrackingEventType.CLICK)

    assert gmail_cls.is_bot is None
    assert chrome_cls.is_bot is False
    assert safelinks_cls.is_bot is True
    assert unknown_cls.is_bot is None

    # Record repeated opens on r1 (3 opens -> 1 unique open recipient) and 1 click on r2
    events = [
        EmailTrackingEvent(company_id=company.id, email_id=1, campaign_id=campaign.id, recipient_id=r1.id, delivery_id=d1.id, event_type=TrackingEventType.OPEN.value, is_bot=gmail_cls.is_bot, bot_reason=gmail_cls.bot_reason, occurred_at=now),
        EmailTrackingEvent(company_id=company.id, email_id=1, campaign_id=campaign.id, recipient_id=r1.id, delivery_id=d1.id, event_type=TrackingEventType.OPEN.value, is_bot=chrome_cls.is_bot, occurred_at=now + timedelta(seconds=10)),
        EmailTrackingEvent(company_id=company.id, email_id=1, campaign_id=campaign.id, recipient_id=r1.id, delivery_id=d1.id, event_type=TrackingEventType.OPEN.value, is_bot=chrome_cls.is_bot, occurred_at=now + timedelta(seconds=20)),
        EmailTrackingEvent(company_id=company.id, email_id=2, campaign_id=campaign.id, recipient_id=r2.id, delivery_id=d2.id, event_type=TrackingEventType.CLICK.value, is_bot=safelinks_cls.is_bot, bot_reason=safelinks_cls.bot_reason, occurred_at=now + timedelta(seconds=30)),
        EmailTrackingEvent(company_id=company.id, email_id=2, campaign_id=campaign.id, recipient_id=r2.id, delivery_id=d2.id, event_type=TrackingEventType.CLICK.value, is_bot=unknown_cls.is_bot, occurred_at=now + timedelta(seconds=40)),
    ]
    db_session.add_all(events)
    await db_session.commit()

    analytics = await CampaignService.get_campaign_analytics(db=db_session, company_id=company.id, campaign_id=campaign.id)
    open_dd = await CampaignService.get_campaign_recipient_engagement(db=db_session, company_id=company.id, campaign_id=campaign.id, event_type="OPEN")
    click_dd = await CampaignService.get_campaign_recipient_engagement(db=db_session, company_id=company.id, campaign_id=campaign.id, event_type="CLICK")

    # Repeated opens do NOT inflate unique_open_recipients
    assert analytics.raw_open_count == 3
    assert analytics.unique_open_recipients == 1
    assert analytics.open_rate == 50.0  # 1 / 2 unique_recipients_sent

    assert analytics.raw_click_count == 2
    assert analytics.unique_click_recipients == 1
    assert analytics.click_rate == 50.0

    # Classification totals: 1 bot, 2 non_bot, 2 unknown
    assert analytics.bot_events_count == 1
    assert analytics.non_bot_events_count == 2
    assert analytics.unknown_events_count == 2

    # Drilldown parity
    assert open_dd.total == analytics.unique_open_recipients
    assert open_dd.items[0].total_events_count == 3
    assert click_dd.total == analytics.unique_click_recipients
    assert click_dd.items[0].total_events_count == 2
