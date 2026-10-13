from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from httpx import AsyncClient
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import User
from app.modules.campaigns.delivery_service import (
    CampaignDeliveryService,
    render_content_for_recipient,
)
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
from app.modules.companies.models import Company, CompanyRole, CompanyUser
from app.modules.domains.models import Domain, DomainVerificationStatus
from app.modules.email_accounts.models import EmailAccount
from app.modules.emails.models import Email
from app.services.smtp.exceptions import SMTPSendError
from app.services.transport.base import EmailTransport
from app.services.transport.exceptions import TransportSendError
from app.workers import tasks
from app.workers.campaign_tasks import (
    _async_dispatch_campaign_task,
    dispatch_campaign_task,
)
from tests.conftest import TestAsyncSessionLocal


# =============================================================================
# Test Setup & Fixtures
# =============================================================================

@pytest.fixture(autouse=True)
def configure_worker_db():
    """Ensure delivery engine worker tasks use the test database."""
    orig_session_maker = tasks.WorkerAsyncSessionLocal
    tasks.WorkerAsyncSessionLocal = TestAsyncSessionLocal
    yield
    tasks.WorkerAsyncSessionLocal = orig_session_maker


# =============================================================================
# Helper Utilities
# =============================================================================

async def register_and_login(client: AsyncClient, email: str, name: str = "Test User") -> str:
    """Register and authenticate a user, returning their JWT bearer access token."""
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123!", "full_name": name},
    )
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    return login_resp.json()["access_token"]


async def create_company_helper(client: AsyncClient, token: str, name: str = "Delivery Org") -> int:
    """Create a company under the authenticated user and return its ID."""
    resp = await client.post(
        "/api/v1/companies/",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": name},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def create_domain_helper(
    client: AsyncClient,
    token: str,
    company_id: int,
    domain_name: str = "delivery-test.com",
) -> int:
    """Create a sending domain under a company and return its ID."""
    resp = await client.post(
        f"/api/v1/companies/{company_id}/domains",
        headers={"Authorization": f"Bearer {token}"},
        json={"domain_name": domain_name},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def create_email_account_helper(
    client: AsyncClient,
    token: str,
    company_id: int,
    email_address: str = "sender@delivery-test.com",
    name: str = "Delivery Sender",
    domain_id: int = None,
) -> int:
    """Create an active email account under a company and return its ID."""
    payload = {
        "name": name,
        "email_address": email_address,
        "provider": "CUSTOM",
        "smtp_host": "smtp.delivery-test.com",
        "smtp_port": 587,
        "smtp_security": "STARTTLS",
        "smtp_username": email_address,
        "smtp_password": "SecretPassword123!",
        "imap_host": "imap.delivery-test.com",
        "imap_port": 993,
        "imap_security": "SSL",
        "imap_username": email_address,
        "imap_password": "SecretPassword123!",
    }
    if domain_id is not None:
        payload["domain_id"] = domain_id

    resp = await client.post(
        f"/api/v1/companies/{company_id}/email-accounts",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def setup_delivery_campaign(
    client: AsyncClient,
    db: AsyncSession,
    owner_token: str,
    company_id: int,
    subject: str = "Hello {{first_name}}",
    body_text: str = "Welcome {{first_name}} to our service!",
) -> tuple[int, int]:
    """Create a fully preflight-eligible campaign in DRAFT status with verified domain and sender."""
    dom_id = await create_domain_helper(client, owner_token, company_id, "delivery-test.com")

    # Mark domain verified directly in DB for preflight compliance
    dom_res = await db.execute(select(Domain).where(Domain.id == dom_id))
    domain = dom_res.scalar_one()
    domain.verification_status = DomainVerificationStatus.VERIFIED.value
    await db.commit()

    acc_id = await create_email_account_helper(
        client,
        owner_token,
        company_id,
        "sender@delivery-test.com",
        domain_id=dom_id,
    )

    create_resp = await client.post(
        f"/api/v1/companies/{company_id}/campaigns",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "name": "Outreach Campaign",
            "email_account_id": acc_id,
            "subject": subject,
            "body_text": body_text,
            "body_html": f"<p>{body_text}</p>",
        },
    )
    assert create_resp.status_code == 201
    camp_id = create_resp.json()["id"]

    return camp_id, acc_id


async def add_recipient_helper(
    client: AsyncClient,
    token: str,
    company_id: int,
    campaign_id: int,
    email: str,
    first_name: str = None,
) -> int:
    """Add a recipient to a campaign in DRAFT state and return their ID."""
    resp = await client.post(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/recipients",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": email, "first_name": first_name},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def queue_campaign_helper(db: AsyncSession, campaign_id: int) -> None:
    """Transition campaign to QUEUED state for delivery execution."""
    camp_res = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    camp = camp_res.scalar_one()
    camp.status = CampaignStatus.QUEUED.value
    await db.commit()


# =============================================================================
# 1. Merge-Tag Rendering Tests
# =============================================================================

def test_merge_tag_rendering_with_first_name():
    """Verify that {{first_name}} is replaced with recipient's first_name."""
    recip = CampaignRecipient(campaign_id=1, email="test@test.com", first_name="Alice")
    assert render_content_for_recipient("Hello {{first_name}}!", recip) == "Hello Alice!"
    assert render_content_for_recipient("Hello {{ first_name }}!", recip) == "Hello Alice!"


def test_merge_tag_rendering_fallback_empty():
    """Verify that {{first_name}} safely defaults to empty string when first_name is None."""
    recip = CampaignRecipient(campaign_id=1, email="test@test.com", first_name=None)
    assert render_content_for_recipient("Hello {{first_name}}!", recip) == "Hello !"
    assert render_content_for_recipient(None, recip) is None


# =============================================================================
# 2. Campaign Execution & Delivery Linkage Tests
# =============================================================================

@pytest.mark.anyio
async def test_campaign_delivery_success_flow_and_linkage(async_client: AsyncClient, db_session: AsyncSession):
    """Verify the full successful delivery flow:
    - QUEUED campaign transitions to RUNNING -> COMPLETED
    - Exactly one CampaignDelivery per recipient
    - CampaignDelivery is linked to Email (email_id, thread_id, message_id)
    - Merge tag {{first_name}} is rendered per recipient
    - Message-ID is unique per recipient
    - Both recipient and delivery statuses become SENT
    """
    owner_token = await register_and_login(async_client, "owner_deliv1@test.com", "Owner One")
    company_id = await create_company_helper(async_client, owner_token, "Delivery Org 1")
    camp_id, _ = await setup_delivery_campaign(
        async_client,
        db_session,
        owner_token,
        company_id,
        subject="Hello {{first_name}}",
        body_text="Hi {{first_name}}, check out our update!",
    )

    r1_id = await add_recipient_helper(async_client, owner_token, company_id, camp_id, "alice@customer.com", first_name="Alice")
    r2_id = await add_recipient_helper(async_client, owner_token, company_id, camp_id, "bob@customer.com", first_name="Bob")
    await queue_campaign_helper(db_session, camp_id)

    with patch("app.services.smtp.client.SMTPClient.send_email_sync"):
        result = await CampaignDeliveryService.execute_campaign(
            campaign_id=camp_id,
            company_id=company_id,
        )

    assert result["status"] == CampaignStatus.COMPLETED.value
    assert result["sent_count"] == 2
    assert result["failed_count"] == 0
    assert result["skipped_count"] == 0

    # 1. Verify Campaign State
    camp_res = await db_session.execute(select(Campaign).where(Campaign.id == camp_id))
    camp = camp_res.scalar_one()
    assert camp.status == CampaignStatus.COMPLETED.value
    assert camp.started_at is not None
    assert camp.completed_at is not None

    # 2. Verify Deliveries in DB
    deliv_res = await db_session.execute(
        select(CampaignDelivery).where(CampaignDelivery.campaign_id == camp_id).order_by(CampaignDelivery.recipient_id.asc())
    )
    deliveries = list(deliv_res.scalars().all())
    assert len(deliveries) == 2

    d_alice, d_bob = deliveries[0], deliveries[1]
    assert d_alice.status == CampaignDeliveryStatus.SENT.value
    assert d_bob.status == CampaignDeliveryStatus.SENT.value
    assert d_alice.sent_at is not None
    assert d_bob.sent_at is not None
    assert d_alice.attempt_count == 1
    assert d_bob.attempt_count == 1

    # Verify distinct unique Message-IDs
    assert d_alice.message_id is not None
    assert d_bob.message_id is not None
    assert d_alice.message_id != d_bob.message_id

    # Verify linkages to Email and EmailThread
    assert d_alice.email_id is not None
    assert d_alice.thread_id is not None
    assert d_bob.email_id is not None
    assert d_bob.thread_id is not None

    # Verify rendered content in Email audit records
    email_alice = await db_session.get(Email, d_alice.email_id)
    email_bob = await db_session.get(Email, d_bob.email_id)

    assert email_alice.subject == "Hello Alice"
    assert email_alice.body_text == "Hi Alice, check out our update!"
    assert email_bob.subject == "Hello Bob"
    assert email_bob.body_text == "Hi Bob, check out our update!"

    # 3. Verify Recipients status updated to SENT
    r1 = await db_session.get(CampaignRecipient, r1_id)
    r2 = await db_session.get(CampaignRecipient, r2_id)
    assert r1.status == CampaignRecipientStatus.SENT.value
    assert r2.status == CampaignRecipientStatus.SENT.value


@pytest.mark.anyio
async def test_delivery_uses_email_transport_abstraction(async_client: AsyncClient, db_session: AsyncSession):
    """Verify that email delivery passes through EmailTransport abstraction, not a duplicate SMTP path."""
    owner_token = await register_and_login(async_client, "owner_deliv2@test.com", "Owner Two")
    company_id = await create_company_helper(async_client, owner_token, "Delivery Org 2")
    camp_id, _ = await setup_delivery_campaign(async_client, db_session, owner_token, company_id)
    await add_recipient_helper(async_client, owner_token, company_id, camp_id, "carol@customer.com", first_name="Carol")
    await queue_campaign_helper(db_session, camp_id)

    with patch("app.services.transport.smtp.SMTPTransport.send") as mock_transport_send:
        # Mock successful transport result
        from app.services.transport.models import EmailTransportResult
        mock_transport_send.return_value = EmailTransportResult(success=True, message_id="<test-id@delivery-test.com>")

        result = await CampaignDeliveryService.execute_campaign(
            campaign_id=camp_id,
            company_id=company_id,
        )

        assert result["status"] == CampaignStatus.COMPLETED.value
        assert result["sent_count"] == 1
        # EmailTransport was invoked
        mock_transport_send.assert_called_once()


# =============================================================================
# 3. Failure Isolation & Error Tracking Tests
# =============================================================================

@pytest.mark.anyio
async def test_failed_recipient_does_not_halt_campaign_and_records_failure(async_client: AsyncClient, db_session: AsyncSession):
    """Verify failure isolation:
    - Recipient A succeeds
    - Recipient B fails with transport exception
    - Recipient C succeeds
    - B's failure does NOT stop C from being delivered
    - B is marked FAILED with error message, A and C are marked SENT
    - Campaign finalizes as COMPLETED because partial delivery succeeded
    """
    owner_token = await register_and_login(async_client, "owner_deliv3@test.com", "Owner Three")
    company_id = await create_company_helper(async_client, owner_token, "Delivery Org 3")
    camp_id, _ = await setup_delivery_campaign(async_client, db_session, owner_token, company_id)

    r_a = await add_recipient_helper(async_client, owner_token, company_id, camp_id, "a@customer.com", first_name="A")
    r_b = await add_recipient_helper(async_client, owner_token, company_id, camp_id, "b@customer.com", first_name="B")
    r_c = await add_recipient_helper(async_client, owner_token, company_id, camp_id, "c@customer.com", first_name="C")
    await queue_campaign_helper(db_session, camp_id)

    # Define mock send that fails only on recipient B
    def side_effect_send(*args, **kwargs):
        to_addrs = kwargs.get("to_addrs") or (args[7] if len(args) > 7 else [])
        if any("b@customer.com" in str(addr) for addr in to_addrs):
            raise SMTPSendError("Mailbox unavailable / rejected")
        return None

    with patch("app.services.smtp.client.SMTPClient.send_email_sync", side_effect=side_effect_send):
        result = await CampaignDeliveryService.execute_campaign(
            campaign_id=camp_id,
            company_id=company_id,
        )

    assert result["status"] == CampaignStatus.COMPLETED.value
    assert result["sent_count"] == 2
    assert result["failed_count"] == 1

    # Check recipient B delivery
    deliv_b_res = await db_session.execute(
        select(CampaignDelivery).where(CampaignDelivery.campaign_id == camp_id, CampaignDelivery.recipient_id == r_b)
    )
    d_b = deliv_b_res.scalar_one()
    assert d_b.status == CampaignDeliveryStatus.FAILED.value
    assert "SMTP transmission failed" in d_b.error_message
    assert d_b.attempt_count == 1

    # Check recipient A and C deliveries
    deliv_a_res = await db_session.execute(
        select(CampaignDelivery).where(CampaignDelivery.campaign_id == camp_id, CampaignDelivery.recipient_id == r_a)
    )
    assert deliv_a_res.scalar_one().status == CampaignDeliveryStatus.SENT.value

    deliv_c_res = await db_session.execute(
        select(CampaignDelivery).where(CampaignDelivery.campaign_id == camp_id, CampaignDelivery.recipient_id == r_c)
    )
    assert deliv_c_res.scalar_one().status == CampaignDeliveryStatus.SENT.value

    # Recipient status in DB
    recip_b = await db_session.get(CampaignRecipient, r_b)
    assert recip_b.status == CampaignRecipientStatus.FAILED.value


@pytest.mark.anyio
async def test_all_recipients_failed_finalizes_campaign_as_failed(async_client: AsyncClient, db_session: AsyncSession):
    """Verify that if all recipients fail, the campaign transitions to FAILED."""
    owner_token = await register_and_login(async_client, "owner_deliv4@test.com", "Owner Four")
    company_id = await create_company_helper(async_client, owner_token, "Delivery Org 4")
    camp_id, _ = await setup_delivery_campaign(async_client, db_session, owner_token, company_id)
    await add_recipient_helper(async_client, owner_token, company_id, camp_id, "fail@customer.com", first_name="Fail")
    await queue_campaign_helper(db_session, camp_id)

    with patch("app.services.smtp.client.SMTPClient.send_email_sync", side_effect=TransportSendError("SMTP host unreachable")):
        result = await CampaignDeliveryService.execute_campaign(
            campaign_id=camp_id,
            company_id=company_id,
        )

    assert result["status"] == CampaignStatus.FAILED.value
    assert result["sent_count"] == 0
    assert result["failed_count"] == 1

    camp = await db_session.get(Campaign, camp_id)
    assert camp.status == CampaignStatus.FAILED.value


# =============================================================================
# 4. Duplicate Protection & Suppression Tests
# =============================================================================

@pytest.mark.anyio
async def test_already_sent_recipient_is_not_resent(async_client: AsyncClient, db_session: AsyncSession):
    """Verify that a recipient who already has a SENT CampaignDelivery is not sent again."""
    owner_token = await register_and_login(async_client, "owner_deliv5@test.com", "Owner Five")
    company_id = await create_company_helper(async_client, owner_token, "Delivery Org 5")
    camp_id, _ = await setup_delivery_campaign(async_client, db_session, owner_token, company_id)

    r_sent = await add_recipient_helper(async_client, owner_token, company_id, camp_id, "already_sent@customer.com", first_name="Done")
    r_new = await add_recipient_helper(async_client, owner_token, company_id, camp_id, "pending@customer.com", first_name="New")

    # Manually create a SENT delivery for r_sent
    existing_deliv = CampaignDelivery(
        campaign_id=camp_id,
        recipient_id=r_sent,
        status=CampaignDeliveryStatus.SENT.value,
        sent_at=datetime.now(timezone.utc),
        attempt_count=1,
    )
    db_session.add(existing_deliv)
    await db_session.commit()

    await queue_campaign_helper(db_session, camp_id)

    with patch("app.services.smtp.client.SMTPClient.send_email_sync") as mock_smtp:
        result = await CampaignDeliveryService.execute_campaign(
            campaign_id=camp_id,
            company_id=company_id,
        )

    assert result["sent_count"] == 1
    assert result["skipped_count"] == 1
    # Only 1 send occurred (for r_new)
    assert mock_smtp.call_count == 1


@pytest.mark.anyio
async def test_suppressed_recipient_prevented_from_delivery(async_client: AsyncClient, db_session: AsyncSession):
    """Verify that a recipient whose email address is in the suppression list is skipped."""
    owner_token = await register_and_login(async_client, "owner_deliv6@test.com", "Owner Six")
    company_id = await create_company_helper(async_client, owner_token, "Delivery Org 6")
    camp_id, _ = await setup_delivery_campaign(async_client, db_session, owner_token, company_id)

    r_valid = await add_recipient_helper(async_client, owner_token, company_id, camp_id, "valid@customer.com", first_name="Valid")
    r_supp = await add_recipient_helper(async_client, owner_token, company_id, camp_id, "suppressed@customer.com", first_name="Suppressed")

    # Add suppressed@customer.com to company suppression list
    supp_entry = SuppressionEntry(
        company_id=company_id,
        email="suppressed@customer.com",
        reason=SuppressionReason.MANUAL.value,
    )
    db_session.add(supp_entry)
    await db_session.commit()

    await queue_campaign_helper(db_session, camp_id)

    with patch("app.services.smtp.client.SMTPClient.send_email_sync") as mock_smtp:
        result = await CampaignDeliveryService.execute_campaign(
            campaign_id=camp_id,
            company_id=company_id,
        )

    assert result["sent_count"] == 1
    assert result["skipped_count"] == 1
    assert result["status"] == CampaignStatus.COMPLETED.value
    # Only the valid recipient was sent
    assert mock_smtp.call_count == 1

    # Invariant: No CampaignDelivery record created for suppressed recipient
    supp_deliv_res = await db_session.execute(
        select(CampaignDelivery).where(CampaignDelivery.campaign_id == camp_id, CampaignDelivery.recipient_id == r_supp)
    )
    assert supp_deliv_res.scalar_one_or_none() is None

    # Invariant: Suppressed recipient is persisted with status SUPPRESSED, not PENDING
    supp_recip = await db_session.get(CampaignRecipient, r_supp)
    assert supp_recip.status == CampaignRecipientStatus.SUPPRESSED.value

    # Invariant: Campaign reached terminal COMPLETED status
    camp = await db_session.get(Campaign, camp_id)
    assert camp.status == CampaignStatus.COMPLETED.value


@pytest.mark.anyio
async def test_campaign_with_suppressed_recipients_completes_and_lists_suppressed_status(
    async_client: AsyncClient, db_session: AsyncSession
):
    """Bug Fix C11.4: Verify a campaign with eligible and suppressed recipients reaches COMPLETED
    and recipient-list API reflects SUPPRESSED statuses instead of remaining PENDING.
    """
    owner_token = await register_and_login(async_client, "owner_deliv_c11_4@test.com", "Owner C11_4")
    company_id = await create_company_helper(async_client, owner_token, "Delivery Org C11_4")
    camp_id, _ = await setup_delivery_campaign(async_client, db_session, owner_token, company_id)

    # Add 4 eligible and 6 suppressed recipients (matching C11.4 problem description)
    eligible_ids = []
    for i in range(4):
        rid = await add_recipient_helper(
            async_client, owner_token, company_id, camp_id, f"eligible_{i}@test.com", first_name=f"Eligible{i}"
        )
        eligible_ids.append(rid)

    suppressed_ids = []
    for i in range(6):
        email = f"suppressed_{i}@test.com"
        rid = await add_recipient_helper(
            async_client, owner_token, company_id, camp_id, email, first_name=f"Suppressed{i}"
        )
        suppressed_ids.append(rid)
        db_session.add(
            SuppressionEntry(
                company_id=company_id,
                email=email,
                reason=SuppressionReason.BOUNCE.value,
            )
        )
    await db_session.commit()

    await queue_campaign_helper(db_session, camp_id)

    with patch("app.services.smtp.client.SMTPClient.send_email_sync") as mock_smtp:
        result = await CampaignDeliveryService.execute_campaign(
            campaign_id=camp_id,
            company_id=company_id,
        )

    # 4 sent, 6 skipped/suppressed, campaign COMPLETED
    assert result["sent_count"] == 4
    assert result["skipped_count"] == 6
    assert result["status"] == CampaignStatus.COMPLETED.value
    assert mock_smtp.call_count == 4

    camp = await db_session.get(Campaign, camp_id)
    assert camp.status == CampaignStatus.COMPLETED.value

    # Verify recipient-list API returns 4 SENT and 6 SUPPRESSED, 0 PENDING
    list_resp = await async_client.get(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}/recipients?limit=50",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert list_resp.status_code == 200
    recipients_data = list_resp.json()
    assert len(recipients_data) == 10

    sent_items = [r for r in recipients_data if r["status"] == "SENT"]
    suppressed_items = [r for r in recipients_data if r["status"] == "SUPPRESSED"]
    pending_items = [r for r in recipients_data if r["status"] == "PENDING"]

    assert len(sent_items) == 4
    assert len(suppressed_items) == 6
    assert len(pending_items) == 0


@pytest.mark.anyio
async def test_active_sending_delivery_prevents_premature_campaign_completion(
    async_client: AsyncClient, db_session: AsyncSession
):
    """Verify that an in-flight SENDING delivery prevents marking the campaign COMPLETED."""
    owner_token = await register_and_login(async_client, "owner_deliv_inflight@test.com", "Owner Inflight")
    company_id = await create_company_helper(async_client, owner_token, "Delivery Org Inflight")
    camp_id, _ = await setup_delivery_campaign(async_client, db_session, owner_token, company_id)

    r1 = await add_recipient_helper(async_client, owner_token, company_id, camp_id, "done@test.com", first_name="Done")
    r2 = await add_recipient_helper(async_client, owner_token, company_id, camp_id, "sending@test.com", first_name="Sending")

    # r1 already sent
    db_session.add(
        CampaignDelivery(
            campaign_id=camp_id,
            recipient_id=r1,
            status=CampaignDeliveryStatus.SENT.value,
            sent_at=datetime.now(timezone.utc),
            attempt_count=1,
        )
    )
    # r2 actively in SENDING state
    db_session.add(
        CampaignDelivery(
            campaign_id=camp_id,
            recipient_id=r2,
            status=CampaignDeliveryStatus.SENDING.value,
            attempt_count=1,
        )
    )
    # r1 is marked SENT, r2 is still marked PENDING
    recip1 = await db_session.get(CampaignRecipient, r1)
    recip1.status = CampaignRecipientStatus.SENT.value
    recip2 = await db_session.get(CampaignRecipient, r2)
    recip2.status = CampaignRecipientStatus.PENDING.value
    await db_session.commit()

    await queue_campaign_helper(db_session, camp_id)

    with patch("app.services.smtp.client.SMTPClient.send_email_sync") as mock_smtp:
        result = await CampaignDeliveryService.execute_campaign(
            campaign_id=camp_id,
            company_id=company_id,
        )

    # In-flight delivery preserves RUNNING status, no additional send attempted
    assert result["status"] == CampaignStatus.RUNNING.value
    assert mock_smtp.call_count == 0

    camp = await db_session.get(Campaign, camp_id)
    assert camp.status == CampaignStatus.RUNNING.value


# =============================================================================
# 5. Isolation & Celery Worker Integration Tests
# =============================================================================

@pytest.mark.anyio
async def test_cross_company_isolation(async_client: AsyncClient, db_session: AsyncSession):
    """Verify that an attempt to execute a campaign with mismatched company_id returns NOT_FOUND."""
    owner_token = await register_and_login(async_client, "owner_deliv7@test.com", "Owner Seven")
    company_id = await create_company_helper(async_client, owner_token, "Delivery Org 7")
    camp_id, _ = await setup_delivery_campaign(async_client, db_session, owner_token, company_id)
    await queue_campaign_helper(db_session, camp_id)

    result = await CampaignDeliveryService.execute_campaign(
        campaign_id=camp_id,
        company_id=99999,  # Mismatched company
    )
    assert result["status"] == "NOT_FOUND"


@pytest.mark.anyio
async def test_ineligible_campaign_state_skipped(async_client: AsyncClient, db_session: AsyncSession):
    """Verify that campaigns in non-QUEUED states (e.g. DRAFT) are skipped by the delivery engine."""
    owner_token = await register_and_login(async_client, "owner_deliv8@test.com", "Owner Eight")
    company_id = await create_company_helper(async_client, owner_token, "Delivery Org 8")
    camp_id, _ = await setup_delivery_campaign(async_client, db_session, owner_token, company_id)
    # Campaign stays in DRAFT

    with patch("app.services.smtp.client.SMTPClient.send_email_sync") as mock_smtp:
        result = await CampaignDeliveryService.execute_campaign(
            campaign_id=camp_id,
            company_id=company_id,
        )
        assert result["status"] == "SKIPPED"
        mock_smtp.assert_not_called()


@pytest.mark.anyio
async def test_celery_worker_task_executes_delivery_engine(async_client: AsyncClient, db_session: AsyncSession):
    """Verify that the Celery worker task executes the campaign delivery engine to completion."""
    owner_token = await register_and_login(async_client, "owner_deliv9@test.com", "Owner Nine")
    company_id = await create_company_helper(async_client, owner_token, "Delivery Org 9")
    camp_id, _ = await setup_delivery_campaign(async_client, db_session, owner_token, company_id)
    await add_recipient_helper(async_client, owner_token, company_id, camp_id, "worker@customer.com", first_name="Worker")
    await queue_campaign_helper(db_session, camp_id)

    with patch("app.services.smtp.client.SMTPClient.send_email_sync"):
        result = await _async_dispatch_campaign_task(campaign_id=camp_id, company_id=company_id)
        assert result["status"] == CampaignStatus.COMPLETED.value
        assert result["sent_count"] == 1

    # Confirm delivery created and marked SENT
    deliv_res = await db_session.execute(
        select(CampaignDelivery).where(CampaignDelivery.campaign_id == camp_id)
    )
    deliv = deliv_res.scalar_one()
    assert deliv.status == CampaignDeliveryStatus.SENT.value
    assert deliv.email_id is not None
