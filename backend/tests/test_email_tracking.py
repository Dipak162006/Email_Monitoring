from datetime import datetime, timedelta, timezone
import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from alembic import command
from alembic.config import Config

from app.core.config import Settings
from app.modules.campaigns.models import (
    Campaign,
    CampaignDelivery,
    CampaignDeliveryStatus,
    CampaignRecipient,
    CampaignRecipientStatus,
    CampaignStatus,
    CampaignStep,
)
from app.modules.companies.models import Company
from app.modules.email_accounts.models import EmailAccount
from app.modules.emails.models import (
    Email,
    EmailDirection,
    EmailStatus,
    EmailThread,
    EmailTrackingEvent,
    EmailTrackingToken,
    TrackingEventType,
    TrackingTokenType,
)
from app.modules.emails.tracking_service import EmailTrackingService


@pytest.mark.asyncio
async def test_secure_token_generation():
    """Verify cryptographically strong raw token generation."""
    t1 = EmailTrackingService.generate_raw_token()
    t2 = EmailTrackingService.generate_raw_token()

    assert isinstance(t1, str)
    assert len(t1) >= 40
    assert t1 != t2


@pytest.mark.asyncio
async def test_token_hash_persistence_and_no_raw_tokens(db_session: AsyncSession):
    """Verify raw tokens are never persisted in the database; only SHA-256 hashes are stored."""
    company = Company(name="Tracking Co 1")
    db_session.add(company)
    await db_session.flush()

    account = EmailAccount(
        company_id=company.id,
        name="Sender",
        email_address="sender@tracking.co",
        provider="CUSTOM",
        smtp_host="smtp.tracking.co",
    )
    db_session.add(account)
    await db_session.flush()

    thread = EmailThread(company_id=company.id, email_account_id=account.id, subject="Test Email", last_message_at=datetime.now(timezone.utc))
    db_session.add(thread)
    await db_session.flush()

    email_obj = Email(
        company_id=company.id,
        email_account_id=account.id,
        thread_id=thread.id,
        direction=EmailDirection.OUTGOING.value,
        status=EmailStatus.SENT.value,
        sender="sender@tracking.co",
        recipients=["lead@client.com"],
        subject="Test Tracking Email",
    )
    db_session.add(email_obj)
    await db_session.flush()

    token_rec, raw_token = await EmailTrackingService.create_tracking_token(
        db=db_session,
        company_id=company.id,
        email_id=email_obj.id,
        token_type=TrackingTokenType.OPEN,
    )
    await db_session.commit()

    # Raw token must not equal the stored token_hash
    assert raw_token != token_rec.token_hash
    assert len(token_rec.token_hash) == 64
    assert token_rec.token_hash == EmailTrackingService.hash_token(raw_token)

    # Verify directly from database
    row = (await db_session.execute(
        select(EmailTrackingToken).where(EmailTrackingToken.id == token_rec.id)
    )).scalar_one()

    assert row.token_hash == EmailTrackingService.hash_token(raw_token)
    assert not hasattr(row, "raw_token")


@pytest.mark.asyncio
async def test_hash_based_token_lookup_and_resolution(db_session: AsyncSession):
    """Verify resolving tokens via deterministic SHA-256 hash lookup."""
    company = Company(name="Tracking Co 2")
    db_session.add(company)
    await db_session.flush()

    account = EmailAccount(company_id=company.id, name="Sender", email_address="s@co2.com", provider="CUSTOM", smtp_host="smtp.co2.com")
    db_session.add(account)
    await db_session.flush()

    email_obj = Email(
        company_id=company.id,
        email_account_id=account.id,
        direction=EmailDirection.OUTGOING.value,
        status=EmailStatus.SENT.value,
        sender="s@co2.com",
        recipients=["lead@co2.com"],
        subject="Lookup Test",
    )
    db_session.add(email_obj)
    await db_session.flush()

    token_rec, raw_token = await EmailTrackingService.create_tracking_token(
        db=db_session,
        company_id=company.id,
        email_id=email_obj.id,
        token_type=TrackingTokenType.CLICK,
        destination_url="https://pulsemail.io/demo",
    )
    await db_session.commit()

    resolved = await EmailTrackingService.resolve_and_validate_token(
        db=db_session,
        raw_token=raw_token,
    )

    assert resolved is not None
    assert resolved.id == token_rec.id
    assert resolved.destination_url == "https://pulsemail.io/demo"
    assert resolved.token_type == TrackingTokenType.CLICK.value


@pytest.mark.asyncio
async def test_purpose_validation(db_session: AsyncSession):
    """Verify token purpose validation prevents cross-purpose exploitation."""
    company = Company(name="Tracking Co 3")
    db_session.add(company)
    await db_session.flush()

    account = EmailAccount(company_id=company.id, name="Sender", email_address="s@co3.com", provider="CUSTOM", smtp_host="smtp.co3.com")
    db_session.add(account)
    await db_session.flush()

    email_obj = Email(company_id=company.id, email_account_id=account.id, sender="s@co3.com", recipients=["lead@co3.com"], subject="Purpose Test")
    db_session.add(email_obj)
    await db_session.flush()

    open_token_rec, open_raw = await EmailTrackingService.create_tracking_token(
        db=db_session,
        company_id=company.id,
        email_id=email_obj.id,
        token_type=TrackingTokenType.OPEN,
    )
    click_token_rec, click_raw = await EmailTrackingService.create_tracking_token(
        db=db_session,
        company_id=company.id,
        email_id=email_obj.id,
        token_type=TrackingTokenType.CLICK,
        destination_url="https://example.com",
    )
    await db_session.commit()

    # OPEN token cannot be validated as CLICK
    assert await EmailTrackingService.resolve_and_validate_token(
        db=db_session,
        raw_token=open_raw,
        expected_type=TrackingTokenType.CLICK,
    ) is None

    # CLICK token cannot be validated as OPEN
    assert await EmailTrackingService.resolve_and_validate_token(
        db=db_session,
        raw_token=click_raw,
        expected_type=TrackingTokenType.OPEN,
    ) is None

    # Matching types succeed
    assert (await EmailTrackingService.resolve_and_validate_token(
        db=db_session,
        raw_token=open_raw,
        expected_type=TrackingTokenType.OPEN,
    )).id == open_token_rec.id

    assert (await EmailTrackingService.resolve_and_validate_token(
        db=db_session,
        raw_token=click_raw,
        expected_type=TrackingTokenType.CLICK,
    )).id == click_token_rec.id

    # Invalid purpose on creation raises ValueError
    with pytest.raises(ValueError, match="Invalid token purpose"):
        await EmailTrackingService.create_tracking_token(
            db=db_session,
            company_id=company.id,
            email_id=email_obj.id,
            token_type="INVALID_PURPOSE",
        )

    # Click token without destination raises ValueError
    with pytest.raises(ValueError, match="destination_url is required"):
        await EmailTrackingService.create_tracking_token(
            db=db_session,
            company_id=company.id,
            email_id=email_obj.id,
            token_type=TrackingTokenType.CLICK,
            destination_url=None,
        )


@pytest.mark.asyncio
async def test_expired_token_rejection(db_session: AsyncSession):
    """Verify expired tokens fail validation safely."""
    company = Company(name="Tracking Co 4")
    db_session.add(company)
    await db_session.flush()

    account = EmailAccount(company_id=company.id, name="Sender", email_address="s@co4.com", provider="CUSTOM", smtp_host="smtp.co4.com")
    db_session.add(account)
    await db_session.flush()

    email_obj = Email(company_id=company.id, email_account_id=account.id, sender="s@co4.com", recipients=["lead@co4.com"], subject="Expiry Test")
    db_session.add(email_obj)
    await db_session.flush()

    # Already expired token
    token_rec, raw_token = await EmailTrackingService.create_tracking_token(
        db=db_session,
        company_id=company.id,
        email_id=email_obj.id,
        token_type=TrackingTokenType.OPEN,
        expires_in=timedelta(seconds=-10),
    )
    await db_session.commit()

    assert await EmailTrackingService.resolve_and_validate_token(
        db=db_session,
        raw_token=raw_token,
    ) is None


@pytest.mark.asyncio
async def test_revoked_token_rejection(db_session: AsyncSession):
    """Verify revoked tokens fail validation safely."""
    company = Company(name="Tracking Co 5")
    db_session.add(company)
    await db_session.flush()

    account = EmailAccount(company_id=company.id, name="Sender", email_address="s@co5.com", provider="CUSTOM", smtp_host="smtp.co5.com")
    db_session.add(account)
    await db_session.flush()

    email_obj = Email(company_id=company.id, email_account_id=account.id, sender="s@co5.com", recipients=["lead@co5.com"], subject="Revocation Test")
    db_session.add(email_obj)
    await db_session.flush()

    token_rec, raw_token = await EmailTrackingService.create_tracking_token(
        db=db_session,
        company_id=company.id,
        email_id=email_obj.id,
        token_type=TrackingTokenType.OPEN,
    )
    await db_session.commit()

    # Initially valid
    assert (await EmailTrackingService.resolve_and_validate_token(db=db_session, raw_token=raw_token)) is not None

    # Revoke
    await EmailTrackingService.revoke_token(db=db_session, token=token_rec)
    await db_session.commit()

    # Now rejected
    assert (await EmailTrackingService.resolve_and_validate_token(db=db_session, raw_token=raw_token)) is None


@pytest.mark.asyncio
async def test_invalid_tokens_fail_safely(db_session: AsyncSession):
    """Verify malformed, blank, or unknown tokens fail safely without exceptions."""
    assert await EmailTrackingService.resolve_and_validate_token(db=db_session, raw_token="") is None
    assert await EmailTrackingService.resolve_and_validate_token(db=db_session, raw_token="   ") is None
    assert await EmailTrackingService.resolve_and_validate_token(db=db_session, raw_token="completely_random_token_12345") is None


@pytest.mark.asyncio
async def test_tenant_and_email_isolation(db_session: AsyncSession):
    """Verify tenant and message context checks reject mismatched tokens."""
    company1 = Company(name="Company 1")
    company2 = Company(name="Company 2")
    db_session.add_all([company1, company2])
    await db_session.flush()

    account = EmailAccount(company_id=company1.id, name="Sender", email_address="s@co1.com", provider="CUSTOM", smtp_host="smtp.co1.com")
    db_session.add(account)
    await db_session.flush()

    email1 = Email(company_id=company1.id, email_account_id=account.id, sender="s@co1.com", recipients=["a@a.com"], subject="Email 1")
    email2 = Email(company_id=company1.id, email_account_id=account.id, sender="s@co1.com", recipients=["b@b.com"], subject="Email 2")
    db_session.add_all([email1, email2])
    await db_session.flush()

    token_rec, raw_token = await EmailTrackingService.create_tracking_token(
        db=db_session,
        company_id=company1.id,
        email_id=email1.id,
        token_type=TrackingTokenType.OPEN,
    )
    await db_session.commit()

    # Mismatched company rejected
    assert await EmailTrackingService.resolve_and_validate_token(
        db=db_session,
        raw_token=raw_token,
        expected_company_id=company2.id,
    ) is None

    # Mismatched email rejected
    assert await EmailTrackingService.resolve_and_validate_token(
        db=db_session,
        raw_token=raw_token,
        expected_email_id=email2.id,
    ) is None

    # Correct company and email accepted
    assert (await EmailTrackingService.resolve_and_validate_token(
        db=db_session,
        raw_token=raw_token,
        expected_company_id=company1.id,
        expected_email_id=email1.id,
    )).id == token_rec.id


@pytest.mark.asyncio
async def test_multiple_click_tokens_per_email(db_session: AsyncSession):
    """Verify an email can support multiple independent tracked links with distinct tokens."""
    company = Company(name="Multi Click Co")
    db_session.add(company)
    await db_session.flush()

    account = EmailAccount(company_id=company.id, name="Sender", email_address="s@mco.com", provider="CUSTOM", smtp_host="smtp.mco.com")
    db_session.add(account)
    await db_session.flush()

    email_obj = Email(company_id=company.id, email_account_id=account.id, sender="s@mco.com", recipients=["c@c.com"], subject="Multi Link")
    db_session.add(email_obj)
    await db_session.flush()

    rec1, raw1 = await EmailTrackingService.create_tracking_token(
        db=db_session,
        company_id=company.id,
        email_id=email_obj.id,
        token_type=TrackingTokenType.CLICK,
        destination_url="https://pulsemail.io/page-1",
    )
    rec2, raw2 = await EmailTrackingService.create_tracking_token(
        db=db_session,
        company_id=company.id,
        email_id=email_obj.id,
        token_type=TrackingTokenType.CLICK,
        destination_url="https://pulsemail.io/page-2",
    )
    await db_session.commit()

    assert rec1.id != rec2.id
    assert raw1 != raw2
    assert rec1.token_hash != rec2.token_hash

    res1 = await EmailTrackingService.resolve_and_validate_token(db=db_session, raw_token=raw1)
    res2 = await EmailTrackingService.resolve_and_validate_token(db=db_session, raw_token=raw2)

    assert res1.destination_url == "https://pulsemail.io/page-1"
    assert res2.destination_url == "https://pulsemail.io/page-2"


@pytest.mark.asyncio
async def test_record_tracking_event(db_session: AsyncSession):
    """Verify appending tracking interaction events."""
    company = Company(name="Event Co")
    db_session.add(company)
    await db_session.flush()

    account = EmailAccount(company_id=company.id, name="Sender", email_address="s@eco.com", provider="CUSTOM", smtp_host="smtp.eco.com")
    db_session.add(account)
    await db_session.flush()

    campaign = Campaign(company_id=company.id, email_account_id=account.id, name="Event Campaign", subject="Subject", body_text="Body", status=CampaignStatus.RUNNING.value)
    db_session.add(campaign)
    await db_session.flush()

    step = CampaignStep(campaign_id=campaign.id, step_number=1, delay_hours=0, subject="Subject", body_text="Body")
    recipient = CampaignRecipient(campaign_id=campaign.id, email="event_recip@eco.com", status=CampaignRecipientStatus.SENT.value)
    db_session.add_all([step, recipient])
    await db_session.flush()

    email_obj = Email(company_id=company.id, email_account_id=account.id, sender="s@eco.com", recipients=["event_recip@eco.com"], subject="Subject")
    db_session.add(email_obj)
    await db_session.flush()

    delivery = CampaignDelivery(
        campaign_id=campaign.id,
        recipient_id=recipient.id,
        step_id=step.id,
        email_id=email_obj.id,
        status=CampaignDeliveryStatus.SENT.value,
    )
    db_session.add(delivery)
    await db_session.flush()

    token_rec, raw_token = await EmailTrackingService.create_tracking_token(
        db=db_session,
        company_id=company.id,
        email_id=email_obj.id,
        campaign_id=campaign.id,
        recipient_id=recipient.id,
        delivery_id=delivery.id,
        token_type=TrackingTokenType.OPEN,
    )
    await db_session.flush()

    event = await EmailTrackingService.record_tracking_event(
        db=db_session,
        token=token_rec,
        event_type=TrackingEventType.OPEN,
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        ip_address="192.0.2.1",
        is_bot=False,
    )
    await db_session.commit()

    assert event.id is not None
    assert event.token_id == token_rec.id
    assert event.company_id == company.id
    assert event.email_id == email_obj.id
    assert event.campaign_id == campaign.id
    assert event.recipient_id == recipient.id
    assert event.delivery_id == delivery.id
    assert event.event_type == "OPEN"
    assert event.ip_address == "192.0.2.1"
    assert event.is_bot is False


def test_tracking_base_url_configuration_and_validation():
    """Verify TRACKING_BASE_URL setting behavior and production HTTPS validation."""
    # Development mode allows None and provides fallback
    dev_settings = Settings(APP_ENV="development", TRACKING_BASE_URL=None)
    assert dev_settings.get_tracking_base_url() == "http://localhost:8000"

    # Development mode allows custom HTTP or HTTPS
    dev_custom = Settings(APP_ENV="development", TRACKING_BASE_URL="http://track.local:8000/")
    assert dev_custom.get_tracking_base_url() == "http://track.local:8000"

    # Production mode without TRACKING_BASE_URL fails validation
    with pytest.raises(ValidationError) as exc_info:
        Settings(APP_ENV="production", TRACKING_BASE_URL=None)
    assert "TRACKING_BASE_URL is required in production" in str(exc_info.value)

    # Production mode with HTTP fails validation
    with pytest.raises(ValidationError) as exc_info:
        Settings(APP_ENV="production", TRACKING_BASE_URL="http://insecure-tracking.pulsemail.io")
    assert "must use HTTPS in production" in str(exc_info.value)

    # Production mode with HTTPS succeeds
    prod_valid = Settings(APP_ENV="production", TRACKING_BASE_URL="https://track.pulsemail.io/")
    assert prod_valid.get_tracking_base_url() == "https://track.pulsemail.io"


@pytest.mark.asyncio
async def test_alembic_tracking_migration(test_alembic_config: Config):
    """Verify that Alembic can upgrade to 024_email_tracking_tables and downgrade cleanly."""
    from tests.conftest import test_async_engine

    await test_async_engine.dispose()
    command.stamp(test_alembic_config, "head")
    # Downgrade to 023 (drops tracking tables)
    command.downgrade(test_alembic_config, "023_email_attachment_disposition")
    # Upgrade back to 024 (creates tracking tables)
    command.upgrade(test_alembic_config, "head")
    await test_async_engine.dispose()

