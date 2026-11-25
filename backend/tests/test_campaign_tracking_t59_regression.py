"""T5.9 Campaign Tracking Full Audit & Correction Regression Tests.

Verifies:
1. GoogleImageProxy classified as UNKNOWN (is_bot=None).
2. Standard interactive browsers (Chrome, Firefox, Safari, Edge) classified as NON_BOT (is_bot=False).
3. Self-reply detection: incoming replies from an address matching the campaign's sending account
   are properly detected and attributed when that address is an enrolled recipient (e.g. self-test).
4. Sequence accounting & funnel consistency:
   - Step 2 tag-skipped deliveries are not hidden from the sequence metrics.
   - Recipients who stopped/replied/unsubscribed at Step 1 are excluded from subsequent step recipient funnels.
5. Exact consistency between get_campaign_analytics and get_campaign_emails_drilldown.
"""
from datetime import datetime, timezone
import pytest
from httpx import AsyncClient
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
)
from app.modules.campaigns.service import CampaignService
from app.modules.companies.models import Company
from app.modules.email_accounts.models import EmailAccount
from app.modules.emails.bot_classifier import BotClassifier
from app.modules.emails.models import Email, EmailDirection, EmailStatus, EmailTrackingEvent, TrackingEventType


def test_bot_classifier_google_image_proxy_is_unknown():
    """Verify Gmail / Google Image Proxy UA is classified as UNKNOWN (is_bot=None)."""
    gmail_ua = "Mozilla/5.0 (Windows NT 5.1; rv:11.0) Gecko Firefox/11.0 (via ggpht.com GoogleImageProxy)"
    res = BotClassifier.classify(user_agent=gmail_ua, event_type=TrackingEventType.OPEN)
    assert res.is_bot is None
    assert res.bot_reason == "google_image_proxy"
    assert res.bot_confidence is None


def test_bot_classifier_standard_browsers_are_non_bot():
    """Verify standard authentic human browsers are classified as NON_BOT (is_bot=False)."""
    chrome_ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    res = BotClassifier.classify(user_agent=chrome_ua, event_type=TrackingEventType.OPEN)
    assert res.is_bot is False
    assert res.bot_reason is None
    assert res.bot_confidence == 0.85

    firefox_ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/119.0"
    res_ff = BotClassifier.classify(user_agent=firefox_ua, event_type=TrackingEventType.CLICK)
    assert res_ff.is_bot is False
    assert res_ff.bot_reason is None
    assert res_ff.bot_confidence == 0.85


@pytest.mark.asyncio
async def test_self_reply_and_sequence_funnel_consistency(db_session: AsyncSession):
    """Verify reply detection when sending account is also a recipient,

    and verify sequence step funnels accurately reflect skipped deliveries
    and exclude stopped recipients from subsequent step funnels.
    """
    now = datetime.now(timezone.utc)

    # 1. Create Company
    company = Company(name="T5.9 Regression Test Co")
    db_session.add(company)
    await db_session.flush()
    company_id = company.id

    # 2. Create Email Account (sending account)
    account = EmailAccount(
        company_id=company_id,
        name="Self Test Account",
        email_address="sender@company.com",
        smtp_host="smtp.company.com",
        smtp_port=587,
        smtp_username="sender@company.com",
        smtp_password_encrypted="dummy",
        is_active=True,
    )
    db_session.add(account)
    await db_session.flush()

    # 2. Create Campaign with 3 steps
    campaign = Campaign(
        company_id=company_id,
        email_account_id=account.id,
        name="T5.9 Sequence & Reply Test Campaign",
        subject="Initial Outreach",
        body_text="Hello",
        body_html="<p>Hello</p>",
        status="COMPLETED",
    )
    db_session.add(campaign)
    await db_session.flush()

    step1 = CampaignStep(campaign_id=campaign.id, step_number=1, subject="Step 1", delay_hours=0, is_active=True)
    step2 = CampaignStep(campaign_id=campaign.id, step_number=2, subject="Step 2", delay_hours=24, is_active=True, target_tags=["vip"])
    step3 = CampaignStep(campaign_id=campaign.id, step_number=3, subject="Step 3", delay_hours=48, is_active=True)
    db_session.add_all([step1, step2, step3])
    await db_session.flush()

    # 3. Create 3 recipients:
    # r1: external recipient, replied to step 1
    # r2: self recipient (sender@company.com), replied to step 1
    # r3: regular recipient, no tags, reaches step 2 (skipped due to vip tag) and sent in step 3
    r1 = CampaignRecipient(
        campaign_id=campaign.id,
        email="external@lead.com",
        first_name="External",
        status=CampaignRecipientStatus.STOPPED.value,
        stopped_reason=CampaignRecipientStopReason.REPLIED.value,
        replied_at=now,
        current_step_number=1,
    )
    r2 = CampaignRecipient(
        campaign_id=campaign.id,
        email="sender@company.com",  # Same as sending account!
        first_name="Self",
        status=CampaignRecipientStatus.STOPPED.value,
        stopped_reason=CampaignRecipientStopReason.REPLIED.value,
        replied_at=now,
        current_step_number=1,
    )
    r3 = CampaignRecipient(
        campaign_id=campaign.id,
        email="regular@lead.com",
        first_name="Regular",
        status=CampaignRecipientStatus.SENT.value,
        current_step_number=3,
    )
    db_session.add_all([r1, r2, r3])
    await db_session.flush()

    # 4. Deliveries:
    # Step 1: sent to r1, r2, r3
    d1_r1 = CampaignDelivery(campaign_id=campaign.id, recipient_id=r1.id, step_id=step1.id, status=CampaignDeliveryStatus.SENT.value, sent_at=now, message_id="<msg-step1-r1@test>")
    d1_r2 = CampaignDelivery(campaign_id=campaign.id, recipient_id=r2.id, step_id=step1.id, status=CampaignDeliveryStatus.SENT.value, sent_at=now, message_id="<msg-step1-r2@test>")
    d1_r3 = CampaignDelivery(campaign_id=campaign.id, recipient_id=r3.id, step_id=step1.id, status=CampaignDeliveryStatus.SENT.value, sent_at=now, message_id="<msg-step1-r3@test>")
    # Step 2: evaluated for r3, skipped due to missing 'vip' tag
    d2_r3 = CampaignDelivery(campaign_id=campaign.id, recipient_id=r3.id, step_id=step2.id, status=CampaignDeliveryStatus.SKIPPED.value, sent_at=now)
    # Step 3: sent to r3
    d3_r3 = CampaignDelivery(campaign_id=campaign.id, recipient_id=r3.id, step_id=step3.id, status=CampaignDeliveryStatus.SENT.value, sent_at=now, message_id="<msg-step3-r3@test>")

    db_session.add_all([d1_r1, d1_r2, d1_r3, d2_r3, d3_r3])
    await db_session.flush()

    # 5. Incoming reply emails:
    # Reply 1: from external@lead.com
    reply1 = Email(
        company_id=company_id,
        email_account_id=account.id,
        message_id="<reply1@test>",
        in_reply_to="<msg-step1-r1@test>",
        direction=EmailDirection.INCOMING.value,
        status=EmailStatus.RECEIVED.value,
        sender="external@lead.com",
        recipients=["sender@company.com"],
        subject="Re: Step 1",
        received_at=now,
    )
    # Reply 2: from sender@company.com (self-reply to campaign delivery)
    reply2 = Email(
        company_id=company_id,
        email_account_id=account.id,
        message_id="<reply2@test>",
        in_reply_to="<msg-step1-r2@test>",
        direction=EmailDirection.INCOMING.value,
        status=EmailStatus.RECEIVED.value,
        sender="sender@company.com",
        recipients=["sender@company.com"],
        subject="Re: Step 1 Self Reply",
        received_at=now,
    )
    db_session.add_all([reply1, reply2])
    await db_session.commit()

    # 6. Test get_campaign_analytics
    analytics = await CampaignService.get_campaign_analytics(
        campaign_id=campaign.id,
        company_id=company_id,
        db=db_session,
    )
    assert analytics.total_recipients == 3
    assert analytics.unique_recipients_sent == 3
    assert analytics.total_sent_count == 4  # 3 in step 1 + 1 in step 3
    assert analytics.unique_replied_count == 2  # Both r1 and r2 counted!

    # Step Funnel Assertions:
    # Step 1: 3 targeted, 3 sent, 2 replies
    s1 = next(s for s in analytics.steps if s.step_number == 1)
    assert s1.targeted_count == 3
    assert s1.sent_count == 3
    assert s1.skipped_count == 0
    assert s1.replied_count == 2

    # Step 2: 1 targeted (r3), 0 sent, 1 skipped! (r1 and r2 stopped, not targeted)
    s2 = next(s for s in analytics.steps if s.step_number == 2)
    assert s2.targeted_count == 1
    assert s2.sent_count == 0
    assert s2.skipped_count == 1

    # Step 3: 1 targeted (r3), 1 sent, 0 skipped! (r1 and r2 stopped, not targeted)
    s3 = next(s for s in analytics.steps if s.step_number == 3)
    assert s3.targeted_count == 1
    assert s3.sent_count == 1
    assert s3.skipped_count == 0

    # 7. Test get_campaign_emails_drilldown
    drilldown = await CampaignService.get_campaign_emails_drilldown(
        campaign_id=campaign.id,
        company_id=company_id,
        status="replies",
        limit=20,
        offset=0,
        db=db_session,
    )
    # Drilldown replies MUST match analytics unique_replied_count exactly!
    assert drilldown["summary"]["replies_count"] == 2
    assert drilldown["total"] == 2
    assert len(drilldown["items"]) == 2
    drilldown_senders = {item["email"] for item in drilldown["items"]}
    assert drilldown_senders == {"external@lead.com", "sender@company.com"}
