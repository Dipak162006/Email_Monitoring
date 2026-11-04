from datetime import datetime, timezone
from httpx import AsyncClient
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.campaigns.models import (
    Campaign,
    CampaignDelivery,
    CampaignDeliveryStatus,
    CampaignRecipient,
    CampaignRecipientStatus,
    CampaignStep,
    CampaignStatus,
    SuppressionEntry,
)
from app.modules.campaigns.service import CampaignService
from app.modules.email_accounts.models import EmailAccount
from app.modules.emails.models import Email, EmailDirection, EmailThread


async def register_and_login(client: AsyncClient, email: str, name: str = "Test User") -> str:
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123!", "full_name": name},
    )
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    return login_resp.json()["access_token"]


async def create_company_helper(client: AsyncClient, token: str, name: str = "Drilldown Co") -> int:
    resp = await client.post(
        "/api/v1/companies/",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": name},
    )
    return resp.json()["id"]


async def create_account_helper(client: AsyncClient, token: str, company_id: int, email: str = "sender@company.com") -> int:
    resp = await client.post(
        f"/api/v1/companies/{company_id}/email-accounts",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Sender Account",
            "email_address": email,
            "provider": "CUSTOM",
            "smtp_host": "smtp.company.com",
            "smtp_port": 587,
            "smtp_security": "STARTTLS",
            "smtp_username": email,
            "smtp_password": "Password123!",
            "imap_host": "imap.company.com",
            "imap_port": 993,
            "imap_security": "SSL",
            "imap_username": email,
            "imap_password": "Password123!",
        },
    )
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_drilldown_counts_and_replies_and_bounces(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Verify Campaign Emails drill-down feature:
    - 4 recipients -> Recipients = 4
    - 4 initial + 1 follow-up -> Sent = 5 (delivery records, not unique recipients)
    - 1 genuine inbound reply -> Replies = 1
    - 1 bounce fixture -> Bounced = 1
    - 1 failed fixture -> Failed = 1
    - Search & pagination work without changing overall card metrics
    - Company isolation enforced
    """
    token = await register_and_login(async_client, "owner_dd@test.com")
    company_id = await create_company_helper(async_client, token, "Co DD")
    account_id = await create_account_helper(async_client, token, company_id, email="campaign_sender@test.com")

    # 1. Create Campaign with 2 Steps
    campaign = Campaign(
        company_id=company_id,
        name="DD-TEST-CAMPAIGN-01",
        subject="Drilldown Test Initial",
        body_text="Hello Initial",
        status=CampaignStatus.RUNNING.value,
        email_account_id=account_id,
    )
    db_session.add(campaign)
    await db_session.flush()

    step1 = CampaignStep(
        campaign_id=campaign.id,
        step_number=1,
        delay_hours=0,
        subject="Step 1 Subject",
        body_text="Body 1",
    )
    step2 = CampaignStep(
        campaign_id=campaign.id,
        step_number=2,
        delay_hours=24,
        subject="Step 2 Subject",
        body_text="Body 2",
    )
    db_session.add_all([step1, step2])
    await db_session.flush()

    # 2. Add 4 recipients
    r1 = CampaignRecipient(campaign_id=campaign.id, email="lead1@target.com", first_name="Lead", last_name="One", status=CampaignRecipientStatus.SENT.value, current_step_number=2)
    r2 = CampaignRecipient(campaign_id=campaign.id, email="lead2@target.com", first_name="Lead", last_name="Two", status=CampaignRecipientStatus.STOPPED.value, current_step_number=1, stopped_reason="REPLIED")
    r3 = CampaignRecipient(campaign_id=campaign.id, email="lead3@target.com", first_name="Lead", last_name="Three", status=CampaignRecipientStatus.SENT.value, current_step_number=1)
    r4 = CampaignRecipient(campaign_id=campaign.id, email="lead4@target.com", first_name="Lead", last_name="Four", status=CampaignRecipientStatus.SENT.value, current_step_number=1)
    db_session.add_all([r1, r2, r3, r4])
    await db_session.flush()

    # 3. Create threads and 4 initial deliveries (Step 1) + 1 follow-up delivery (Step 2 to r1) = 5 SENT deliveries
    now = datetime.now(timezone.utc)
    th1 = EmailThread(company_id=company_id, email_account_id=account_id, subject="Step 1 Subject", last_message_at=now)
    th2 = EmailThread(company_id=company_id, email_account_id=account_id, subject="Step 1 Subject", last_message_at=now)
    th3 = EmailThread(company_id=company_id, email_account_id=account_id, subject="Step 1 Subject", last_message_at=now)
    th4 = EmailThread(company_id=company_id, email_account_id=account_id, subject="Step 1 Subject", last_message_at=now)
    db_session.add_all([th1, th2, th3, th4])
    await db_session.flush()

    d1_1 = CampaignDelivery(campaign_id=campaign.id, recipient_id=r1.id, step_id=step1.id, status=CampaignDeliveryStatus.SENT.value, message_id="<msg-dd-1-1@company.com>", thread_id=th1.id, sent_at=datetime.now(timezone.utc))
    d1_2 = CampaignDelivery(campaign_id=campaign.id, recipient_id=r1.id, step_id=step2.id, status=CampaignDeliveryStatus.SENT.value, message_id="<msg-dd-1-2@company.com>", thread_id=th1.id, sent_at=datetime.now(timezone.utc))
    d2_1 = CampaignDelivery(campaign_id=campaign.id, recipient_id=r2.id, step_id=step1.id, status=CampaignDeliveryStatus.SENT.value, message_id="<msg-dd-2-1@company.com>", thread_id=th2.id, sent_at=datetime.now(timezone.utc))
    d3_1 = CampaignDelivery(campaign_id=campaign.id, recipient_id=r3.id, step_id=step1.id, status=CampaignDeliveryStatus.SENT.value, message_id="<msg-dd-3-1@company.com>", thread_id=th3.id, sent_at=datetime.now(timezone.utc))
    d4_1 = CampaignDelivery(campaign_id=campaign.id, recipient_id=r4.id, step_id=step1.id, status=CampaignDeliveryStatus.SENT.value, message_id="<msg-dd-4-1@company.com>", thread_id=th4.id, sent_at=datetime.now(timezone.utc))

    db_session.add_all([d1_1, d1_2, d2_1, d3_1, d4_1])
    await db_session.flush()

    # 4. Inbound Genuine Reply from lead2 (references d2_1)
    reply_email = Email(
        company_id=company_id,
        email_account_id=account_id,
        direction=EmailDirection.INCOMING.value,
        sender="Lead Two <lead2@target.com>",
        recipients=["campaign_sender@test.com"],
        subject="Re: Step 1 Subject",
        in_reply_to="<msg-dd-2-1@company.com>",
        thread_id=th2.id,
        received_at=datetime.now(timezone.utc),
    )
    # Also add an unrelated email that should NOT be counted as a reply
    unrelated_email = Email(
        company_id=company_id,
        email_account_id=account_id,
        direction=EmailDirection.INCOMING.value,
        sender="stranger@other.com",
        recipients=["campaign_sender@test.com"],
        subject="Unrelated spam",
        in_reply_to="<random-unrelated-msg@elsewhere.com>",
        received_at=datetime.now(timezone.utc),
    )
    # Also add an internal email sent from the campaign sender account (should NOT count as reply)
    internal_email = Email(
        company_id=company_id,
        email_account_id=account_id,
        direction=EmailDirection.INCOMING.value,
        sender="campaign_sender@test.com",
        recipients=["campaign_sender@test.com"],
        subject="Internal note",
        in_reply_to="<msg-dd-1-1@company.com>",
        thread_id=th1.id,
        received_at=datetime.now(timezone.utc),
    )
    # Also add a stranger email that matches campaign subject exactly ("Re: Step 1 Subject")
    # but has no message-ID or thread link to this campaign (MUST NOT BE ATTRIBUTED)
    subject_only_email = Email(
        company_id=company_id,
        email_account_id=account_id,
        direction=EmailDirection.INCOMING.value,
        sender="unrelated_person@nowhere.com",
        recipients=["campaign_sender@test.com"],
        subject="Re: Step 1 Subject",
        in_reply_to="<external-non-campaign-id@random.com>",
        received_at=datetime.now(timezone.utc),
    )
    db_session.add_all([reply_email, unrelated_email, internal_email, subject_only_email])
    await db_session.commit()

    # Test API endpoints
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Recipients
    res_recip = await async_client.get(f"/api/v1/companies/{company_id}/campaigns/{campaign.id}/emails?status=recipients", headers=headers)
    assert res_recip.status_code == 200
    data_recip = res_recip.json()
    assert data_recip["summary"]["recipients_count"] == 4
    assert data_recip["summary"]["sent_count"] == 5
    assert data_recip["summary"]["replies_count"] == 1
    assert data_recip["summary"]["bounced_count"] == 0
    assert data_recip["summary"]["failed_count"] == 0
    assert data_recip["total"] == 4
    assert len(data_recip["items"]) == 4

    # 2. Sent (Should have 5 delivery items, 4 step 1 + 1 step 2)
    res_sent = await async_client.get(f"/api/v1/companies/{company_id}/campaigns/{campaign.id}/emails?status=sent", headers=headers)
    assert res_sent.status_code == 200
    data_sent = res_sent.json()
    assert data_sent["summary"]["sent_count"] == 5
    assert data_sent["total"] == 5
    assert len(data_sent["items"]) == 5
    step_numbers = [item["step_number"] for item in data_sent["items"]]
    assert step_numbers.count(1) == 4
    assert step_numbers.count(2) == 1

    # 3. Replies (Should return exactly 1 genuine reply; internal and unrelated excluded)
    res_rep = await async_client.get(f"/api/v1/companies/{company_id}/campaigns/{campaign.id}/emails?status=replies", headers=headers)
    assert res_rep.status_code == 200
    data_rep = res_rep.json()
    assert data_rep["summary"]["replies_count"] == 1
    assert data_rep["total"] == 1
    assert len(data_rep["items"]) == 1
    reply_item = data_rep["items"][0]
    assert reply_item["email"] == "lead2@target.com"
    assert reply_item["step_number"] == 1
    assert reply_item["subject"] == "Re: Step 1 Subject"

    # 4. Empty Bounced and Failed return 200 with empty list (no 500 error!)
    res_bounced = await async_client.get(f"/api/v1/companies/{company_id}/campaigns/{campaign.id}/emails?status=bounced", headers=headers)
    assert res_bounced.status_code == 200
    assert res_bounced.json()["total"] == 0
    assert len(res_bounced.json()["items"]) == 0

    res_failed = await async_client.get(f"/api/v1/companies/{company_id}/campaigns/{campaign.id}/emails?status=failed", headers=headers)
    assert res_failed.status_code == 200
    assert res_failed.json()["total"] == 0
    assert len(res_failed.json()["items"]) == 0

    # 5. Search filtering (Searching "lead1" in sent returns 2 items without altering summary.sent_count)
    res_search = await async_client.get(f"/api/v1/companies/{company_id}/campaigns/{campaign.id}/emails?status=sent&search=lead1", headers=headers)
    assert res_search.status_code == 200
    data_search = res_search.json()
    assert data_search["summary"]["sent_count"] == 5  # Overall metric unchanged
    assert data_search["total"] == 2                 # Matching filtered count
    assert len(data_search["items"]) == 2

    # 6. Invalid status validation (Returns HTTP 400)
    res_invalid = await async_client.get(f"/api/v1/companies/{company_id}/campaigns/{campaign.id}/emails?status=bogus", headers=headers)
    assert res_invalid.status_code == 400

    # 7. Add Bounced and Failed deliveries to verify positive fixtures
    r5 = CampaignRecipient(campaign_id=campaign.id, email="bounced_lead@test.com", first_name="Bounced", last_name="Lead", status=CampaignRecipientStatus.BOUNCED.value)
    r6 = CampaignRecipient(campaign_id=campaign.id, email="failed_lead@test.com", first_name="Failed", last_name="Lead", status=CampaignRecipientStatus.FAILED.value)
    db_session.add_all([r5, r6])
    await db_session.flush()

    d_bounce = CampaignDelivery(
        campaign_id=campaign.id,
        recipient_id=r5.id,
        step_id=step1.id,
        status=CampaignDeliveryStatus.BOUNCED.value,
        bounced_at=datetime.now(timezone.utc),
        error_message="550 5.1.1 User unknown",
    )
    # Add a delivery that failed but ALSO recorded a bounce timestamp (must only appear in bounced, NOT failed)
    r7 = CampaignRecipient(campaign_id=campaign.id, email="late_bounce@test.com", first_name="Late", last_name="Bounce", status=CampaignRecipientStatus.BOUNCED.value)
    db_session.add(r7)
    await db_session.flush()

    d_late_bounce = CampaignDelivery(
        campaign_id=campaign.id,
        recipient_id=r7.id,
        step_id=step1.id,
        status=CampaignDeliveryStatus.FAILED.value,
        bounced_at=datetime.now(timezone.utc),
        error_message="554 Delivery failed permanent bounce",
    )
    d_fail = CampaignDelivery(
        campaign_id=campaign.id,
        recipient_id=r6.id,
        step_id=step1.id,
        status=CampaignDeliveryStatus.FAILED.value,
        attempt_count=3,
        error_message="Connection timed out after 3 retries",
    )
    # Add multiple suppression entries for the same email to verify joins do not duplicate records
    suppr1 = SuppressionEntry(
        company_id=company_id,
        email="bounced_lead@test.com",
        reason="HARD_BOUNCE",
    )
    suppr2 = SuppressionEntry(
        company_id=company_id,
        email="late_bounce@test.com",
        reason="MANUAL_ADMIN",
    )
    db_session.add_all([d_bounce, d_late_bounce, d_fail, suppr1, suppr2])
    await db_session.commit()

    # Check Bounced page now returns 2 bounces (d_bounce + d_late_bounce; no row duplication from multiple suppressions)
    res_b_after = await async_client.get(f"/api/v1/companies/{company_id}/campaigns/{campaign.id}/emails?status=bounced", headers=headers)
    assert res_b_after.status_code == 200
    data_b_after = res_b_after.json()
    assert data_b_after["summary"]["bounced_count"] == 2
    assert data_b_after["total"] == 2
    b_emails = [item["email"] for item in data_b_after["items"]]
    assert "bounced_lead@test.com" in b_emails
    assert "late_bounce@test.com" in b_emails
    # Verify no duplicate rows for bounced_lead@test.com
    assert b_emails.count("bounced_lead@test.com") == 1

    # Check Failed page returns ONLY d_fail (1 logical delivery, attempt_count=3; d_late_bounce excluded because it bounced)
    res_f_after = await async_client.get(f"/api/v1/companies/{company_id}/campaigns/{campaign.id}/emails?status=failed", headers=headers)
    assert res_f_after.status_code == 200
    data_f_after = res_f_after.json()
    assert data_f_after["summary"]["failed_count"] == 1
    assert data_f_after["total"] == 1
    f_item = data_f_after["items"][0]
    assert f_item["email"] == "failed_lead@test.com"
    assert f_item["attempt_count"] == 3
    # Verify d_late_bounce is NOT in failed
    failed_emails = [item["email"] for item in data_f_after["items"]]
    assert "late_bounce@test.com" not in failed_emails

    # 8. Company isolation: user from another company receives 404/403
    token_other = await register_and_login(async_client, "other_owner@test.com")
    co_other = await create_company_helper(async_client, token_other, "Other Co")
    res_iso = await async_client.get(f"/api/v1/companies/{co_other}/campaigns/{campaign.id}/emails?status=recipients", headers={"Authorization": f"Bearer {token_other}"})
    assert res_iso.status_code in (404, 403)

