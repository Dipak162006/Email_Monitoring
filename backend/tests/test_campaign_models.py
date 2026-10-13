from datetime import datetime, timezone
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.auth.models import User
from app.modules.campaigns.models import (
    Campaign,
    CampaignDelivery,
    CampaignDeliveryStatus,
    CampaignRecipient,
    CampaignRecipientStatus,
    CampaignStatus,
    SuppressionEntry,
    SuppressionReason,
)
from app.modules.companies.models import Company
from app.modules.email_accounts.models import EmailAccount, EmailProvider
from app.modules.emails.models import Email, EmailDirection, EmailStatus, EmailThread


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def create_test_fixtures(db: AsyncSession):
    """Helper to create a Company, User, and EmailAccount for campaign tests."""
    company = Company(name="Acme Corp")
    db.add(company)
    await db.flush()

    user = User(
        email="owner@acme.com",
        hashed_password="hashed_pw_dummy",
        full_name="Alice Owner",
    )
    db.add(user)
    await db.flush()

    account = EmailAccount(
        company_id=company.id,
        name="Sales Outreach",
        email_address="sales@acme.com",
        provider=EmailProvider.CUSTOM.value,
        smtp_host="smtp.acme.com",
        smtp_port=587,
    )
    db.add(account)
    await db.flush()

    return company, user, account


# ---------------------------------------------------------------------------
# Targeted Model Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_campaign_persistence_and_defaults(db_session: AsyncSession):
    """Test Campaign model persistence, default status DRAFT, timestamps, and relationships."""
    company, user, account = await create_test_fixtures(db_session)

    campaign = Campaign(
        company_id=company.id,
        email_account_id=account.id,
        name="Q4 Outreach",
        subject="Special Partnership Offer",
        body_text="Hi there,\nWe would love to connect.",
        body_html="<p>Hi there,</p><p>We would love to connect.</p>",
        created_by_user_id=user.id,
    )
    db_session.add(campaign)
    await db_session.commit()
    await db_session.refresh(campaign)

    assert campaign.id is not None
    assert campaign.name == "Q4 Outreach"
    assert campaign.status == CampaignStatus.DRAFT.value
    assert campaign.created_at is not None
    assert campaign.updated_at is not None
    assert campaign.scheduled_at is None
    assert campaign.started_at is None
    assert campaign.completed_at is None

    # Relationship verification
    query = (
        select(Campaign)
        .options(
            selectinload(Campaign.company),
            selectinload(Campaign.email_account),
            selectinload(Campaign.created_by_user),
        )
        .where(Campaign.id == campaign.id)
    )
    result = await db_session.execute(query)
    loaded = result.scalar_one()

    assert loaded.company.name == "Acme Corp"
    assert loaded.email_account.email_address == "sales@acme.com"
    assert loaded.created_by_user.email == "owner@acme.com"


@pytest.mark.asyncio
async def test_campaign_recipient_persistence_and_defaults(db_session: AsyncSession):
    """Test CampaignRecipient defaults to PENDING and handles custom_variables JSON."""
    company, _, account = await create_test_fixtures(db_session)

    campaign = Campaign(
        company_id=company.id,
        email_account_id=account.id,
        name="Lead Nurturing",
    )
    db_session.add(campaign)
    await db_session.flush()

    recipient = CampaignRecipient(
        campaign_id=campaign.id,
        email="prospect@client.com",
        first_name="Bob",
        last_name="Smith",
        custom_variables={"company": "Client Inc", "role": "VP Engineering"},
    )
    db_session.add(recipient)
    await db_session.commit()
    await db_session.refresh(recipient)

    assert recipient.id is not None
    assert recipient.email == "prospect@client.com"
    assert recipient.status == CampaignRecipientStatus.PENDING.value
    assert recipient.first_name == "Bob"
    assert recipient.last_name == "Smith"
    assert recipient.custom_variables == {"company": "Client Inc", "role": "VP Engineering"}
    assert recipient.created_at is not None

    # Navigation from recipient to campaign
    rec_query = (
        select(CampaignRecipient)
        .options(selectinload(CampaignRecipient.campaign))
        .where(CampaignRecipient.id == recipient.id)
    )
    rec_res = await db_session.execute(rec_query)
    loaded_rec = rec_res.scalar_one()
    assert loaded_rec.campaign.id == campaign.id


@pytest.mark.asyncio
async def test_campaign_delivery_persistence_and_defaults(db_session: AsyncSession):
    """Test CampaignDelivery defaults to PENDING, attempt_count 0, and relationships."""
    company, user, account = await create_test_fixtures(db_session)

    campaign = Campaign(
        company_id=company.id,
        email_account_id=account.id,
        name="Newsletter Blast",
    )
    db_session.add(campaign)
    await db_session.flush()

    recipient = CampaignRecipient(
        campaign_id=campaign.id,
        email="subscriber@domain.com",
    )
    db_session.add(recipient)
    await db_session.flush()

    # Optional EmailThread and Email records
    thread = EmailThread(
        company_id=company.id,
        email_account_id=account.id,
        subject="Newsletter Blast",
        last_message_at=datetime.now(timezone.utc),
    )
    db_session.add(thread)
    await db_session.flush()

    email = Email(
        company_id=company.id,
        email_account_id=account.id,
        user_id=user.id,
        thread_id=thread.id,
        message_id="<test-msg-id-123@domain.com>",
        direction=EmailDirection.OUTGOING.value,
        status=EmailStatus.SENT.value,
        sender="sales@acme.com",
        recipients=["subscriber@domain.com"],
        subject="Newsletter Blast",
        body_text="Hello",
    )
    db_session.add(email)
    await db_session.flush()

    delivery = CampaignDelivery(
        campaign_id=campaign.id,
        recipient_id=recipient.id,
        email_id=email.id,
        thread_id=thread.id,
        message_id="<test-msg-id-123@domain.com>",
    )
    db_session.add(delivery)
    await db_session.commit()
    await db_session.refresh(delivery)

    assert delivery.id is not None
    assert delivery.status == CampaignDeliveryStatus.PENDING.value
    assert delivery.attempt_count == 0
    assert delivery.last_attempt_at is None
    assert delivery.sent_at is None
    assert delivery.bounced_at is None
    assert delivery.error_message is None
    assert delivery.created_at is not None

    # Relationship loading
    del_query = (
        select(CampaignDelivery)
        .options(
            selectinload(CampaignDelivery.campaign),
            selectinload(CampaignDelivery.recipient),
            selectinload(CampaignDelivery.email),
            selectinload(CampaignDelivery.thread),
        )
        .where(CampaignDelivery.id == delivery.id)
    )
    del_res = await db_session.execute(del_query)
    loaded_del = del_res.scalar_one()

    assert loaded_del.campaign.id == campaign.id
    assert loaded_del.recipient.email == "subscriber@domain.com"
    assert loaded_del.email.id == email.id
    assert loaded_del.thread.id == thread.id


@pytest.mark.asyncio
async def test_suppression_entry_persistence_and_defaults(db_session: AsyncSession):
    """Test SuppressionEntry defaults reason to MANUAL and enforces uniqueness."""
    company, _, _ = await create_test_fixtures(db_session)

    suppression = SuppressionEntry(
        company_id=company.id,
        email="unsub@external.com",
    )
    db_session.add(suppression)
    await db_session.commit()
    await db_session.refresh(suppression)

    assert suppression.id is not None
    assert suppression.email == "unsub@external.com"
    assert suppression.reason == SuppressionReason.MANUAL.value
    assert suppression.created_at is not None

    # Navigation from suppression entry to company
    sup_query = (
        select(SuppressionEntry)
        .options(selectinload(SuppressionEntry.company))
        .where(SuppressionEntry.id == suppression.id)
    )
    sup_res = await db_session.execute(sup_query)
    loaded_sup = sup_res.scalar_one()
    assert loaded_sup.company.id == company.id
    assert loaded_sup.company.name == "Acme Corp"


@pytest.mark.asyncio
async def test_unique_campaign_recipient_email_constraint(db_session: AsyncSession):
    """Test UNIQUE(campaign_id, email) prevents duplicate recipients within the same campaign."""
    company, _, account = await create_test_fixtures(db_session)

    camp_a = Campaign(company_id=company.id, email_account_id=account.id, name="Campaign A")
    camp_b = Campaign(company_id=company.id, email_account_id=account.id, name="Campaign B")
    db_session.add_all([camp_a, camp_b])
    await db_session.flush()

    rec1 = CampaignRecipient(campaign_id=camp_a.id, email="shared@target.com")
    db_session.add(rec1)
    await db_session.commit()

    # Same email in different campaign should succeed
    rec_diff_camp = CampaignRecipient(campaign_id=camp_b.id, email="shared@target.com")
    db_session.add(rec_diff_camp)
    await db_session.commit()
    assert rec_diff_camp.id is not None

    # Duplicate in same campaign must fail
    rec_duplicate = CampaignRecipient(campaign_id=camp_a.id, email="shared@target.com")
    db_session.add(rec_duplicate)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_unique_campaign_delivery_per_recipient_constraint(db_session: AsyncSession):
    """Test UNIQUE(campaign_id, recipient_id) prevents duplicate deliveries for a recipient in a campaign."""
    company, _, account = await create_test_fixtures(db_session)

    campaign = Campaign(company_id=company.id, email_account_id=account.id, name="Campaign A")
    db_session.add(campaign)
    await db_session.flush()

    recipient = CampaignRecipient(campaign_id=campaign.id, email="target@domain.com")
    db_session.add(recipient)
    await db_session.flush()

    deliv1 = CampaignDelivery(campaign_id=campaign.id, recipient_id=recipient.id)
    db_session.add(deliv1)
    await db_session.commit()

    # Duplicate delivery for same campaign and recipient must fail
    deliv2 = CampaignDelivery(campaign_id=campaign.id, recipient_id=recipient.id)
    db_session.add(deliv2)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_unique_company_suppression_email_constraint(db_session: AsyncSession):
    """Test UNIQUE(company_id, email) prevents duplicate suppression entries for the same company."""
    company_a = Company(name="Org A")
    company_b = Company(name="Org B")
    db_session.add_all([company_a, company_b])
    await db_session.flush()

    sup_a = SuppressionEntry(company_id=company_a.id, email="bounced@domain.com")
    db_session.add(sup_a)
    await db_session.commit()

    # Same email in different company should succeed
    sup_b = SuppressionEntry(company_id=company_b.id, email="bounced@domain.com")
    db_session.add(sup_b)
    await db_session.commit()
    assert sup_b.id is not None

    # Duplicate suppression in same company must fail
    sup_dup = SuppressionEntry(company_id=company_a.id, email="bounced@domain.com")
    db_session.add(sup_dup)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_campaign_cascade_delete(db_session: AsyncSession):
    """Test deleting a Campaign cascades and removes its CampaignRecipients and CampaignDeliveries."""
    company, _, account = await create_test_fixtures(db_session)

    campaign = Campaign(company_id=company.id, email_account_id=account.id, name="Temp Campaign")
    db_session.add(campaign)
    await db_session.flush()

    recipient = CampaignRecipient(campaign_id=campaign.id, email="lead@temp.com")
    db_session.add(recipient)
    await db_session.flush()

    delivery = CampaignDelivery(campaign_id=campaign.id, recipient_id=recipient.id)
    db_session.add(delivery)
    await db_session.commit()

    camp_id = campaign.id
    rec_id = recipient.id
    del_id = delivery.id

    # Delete Campaign
    await db_session.delete(campaign)
    await db_session.commit()

    # Verify recipients and deliveries are cascade deleted
    rec_check = await db_session.execute(select(CampaignRecipient).where(CampaignRecipient.id == rec_id))
    assert rec_check.scalars().first() is None

    del_check = await db_session.execute(select(CampaignDelivery).where(CampaignDelivery.id == del_id))
    assert del_check.scalars().first() is None


@pytest.mark.asyncio
async def test_email_and_thread_set_null_on_campaign_delivery(db_session: AsyncSession):
    """Test deleting an Email or EmailThread sets email_id / thread_id to NULL on CampaignDelivery."""
    company, user, account = await create_test_fixtures(db_session)

    campaign = Campaign(company_id=company.id, email_account_id=account.id, name="Audit Campaign")
    db_session.add(campaign)
    await db_session.flush()

    recipient = CampaignRecipient(campaign_id=campaign.id, email="audit@test.com")
    db_session.add(recipient)
    await db_session.flush()

    thread = EmailThread(
        company_id=company.id,
        email_account_id=account.id,
        subject="Audit Campaign",
        last_message_at=datetime.now(timezone.utc),
    )
    db_session.add(thread)
    await db_session.flush()

    email = Email(
        company_id=company.id,
        email_account_id=account.id,
        user_id=user.id,
        thread_id=thread.id,
        direction=EmailDirection.OUTGOING.value,
        status=EmailStatus.SENT.value,
        sender="sales@acme.com",
        recipients=["audit@test.com"],
        subject="Audit Campaign",
    )
    db_session.add(email)
    await db_session.flush()

    delivery = CampaignDelivery(
        campaign_id=campaign.id,
        recipient_id=recipient.id,
        email_id=email.id,
        thread_id=thread.id,
    )
    db_session.add(delivery)
    await db_session.commit()

    del_id = delivery.id
    email_id = email.id

    # Delete the Email
    await db_session.delete(email)
    await db_session.commit()

    # Delivery must still exist with email_id set to NULL by DB
    await db_session.refresh(delivery)
    assert delivery.email_id is None
    assert delivery.thread_id == thread.id

    # Delete the Thread
    await db_session.delete(thread)
    await db_session.commit()

    # Delivery must still exist with thread_id set to NULL by DB
    await db_session.refresh(delivery)
    assert delivery.thread_id is None
    assert delivery.id == del_id


@pytest.mark.asyncio
async def test_email_account_restrict_delete_with_campaign(db_session: AsyncSession):
    """Test deleting an EmailAccount referenced by an active Campaign is RESTRICTED."""
    company, _, account = await create_test_fixtures(db_session)

    campaign = Campaign(company_id=company.id, email_account_id=account.id, name="Bound Campaign")
    db_session.add(campaign)
    await db_session.commit()

    # Attempting to delete EmailAccount must fail because of ON DELETE RESTRICT
    await db_session.delete(account)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


def test_migration_015_upgrade_downgrade_cycle():
    """Test that migration 015 can be downgraded to 014 and re-upgraded to 015 cleanly."""
    from pathlib import Path
    from alembic import command
    from alembic.config import Config

    alembic_ini_path = Path(__file__).resolve().parent.parent / "alembic.ini"
    alembic_cfg = Config(str(alembic_ini_path))

    # Downgrade 015 -> 014
    command.downgrade(alembic_cfg, "014_email_accounts_domain_id")

    # Upgrade 014 -> 015
    command.upgrade(alembic_cfg, "015_create_campaigns_tables")
