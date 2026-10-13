from unittest.mock import MagicMock, patch
from httpx import AsyncClient
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import User
from app.modules.campaigns.models import (
    Campaign,
    CampaignDelivery,
    CampaignDeliveryStatus,
    CampaignRecipient,
    CampaignStatus,
)
from app.modules.campaigns.schemas import CampaignCreate
from app.modules.campaigns.service import CampaignService
from app.modules.companies.models import Company, CompanyRole, CompanyUser
from app.modules.domains.models import Domain, DomainVerificationStatus
from app.modules.email_accounts.models import EmailAccount
from app.modules.emails.models import Email
from app.workers.campaign_tasks import (
    _async_dispatch_campaign_task,
    dispatch_campaign_task,
)
from app.workers.celery_app import celery_app
from tests.conftest import TestAsyncSessionLocal


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


async def create_company_helper(client: AsyncClient, token: str, name: str = "Dispatch Org") -> int:
    """Create a company under the authenticated user and return its ID."""
    resp = await client.post(
        "/api/v1/companies/",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": name},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def add_company_member_helper(
    client: AsyncClient,
    token_owner: str,
    company_id: int,
    email: str,
    role: str = "MEMBER",
) -> None:
    """Add a user to a company with the given role."""
    resp = await client.post(
        f"/api/v1/companies/{company_id}/members",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"email": email, "role": role},
    )
    assert resp.status_code == 201


async def create_domain_helper(
    client: AsyncClient,
    token: str,
    company_id: int,
    domain_name: str = "dispatch-test.com",
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
    email_address: str = "sender@dispatch-test.com",
    name: str = "Dispatch Sender",
    domain_id: int = None,
) -> int:
    """Create an active email account under a company and return its ID."""
    payload = {
        "name": name,
        "email_address": email_address,
        "provider": "CUSTOM",
        "smtp_host": "smtp.dispatch-test.com",
        "smtp_port": 587,
        "smtp_security": "STARTTLS",
        "smtp_username": email_address,
        "smtp_password": "SecretPassword123!",
        "imap_host": "imap.dispatch-test.com",
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


async def setup_ready_campaign(
    client: AsyncClient,
    db: AsyncSession,
    owner_token: str,
    company_id: int,
    name: str = "Ready Campaign",
) -> tuple[int, int]:
    """Create a fully preflight-eligible campaign with a verified domain, sender account, and recipients."""
    dom_id = await create_domain_helper(client, owner_token, company_id, "dispatch-test.com")

    # Mark domain verified directly in DB for preflight compliance
    dom_res = await db.execute(select(Domain).where(Domain.id == dom_id))
    domain = dom_res.scalar_one()
    domain.verification_status = DomainVerificationStatus.VERIFIED.value
    await db.commit()

    acc_id = await create_email_account_helper(
        client,
        owner_token,
        company_id,
        "sender@dispatch-test.com",
        domain_id=dom_id,
    )

    create_resp = await client.post(
        f"/api/v1/companies/{company_id}/campaigns",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "name": name,
            "email_account_id": acc_id,
            "subject": "Product Announcement",
            "body_text": "Hello world, check out our product!",
        },
    )
    assert create_resp.status_code == 201
    camp_id = create_resp.json()["id"]

    # Add recipients
    recip_resp = await client.post(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}/recipients",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"email": "alice@customer.com", "first_name": "Alice"},
    )
    assert recip_resp.status_code == 201

    return camp_id, acc_id


# =============================================================================
# 1. Dispatch API & Authorization Tests
# =============================================================================

@pytest.mark.anyio
async def test_dispatch_campaign_success(async_client: AsyncClient, db_session: AsyncSession):
    """Verify that an eligible DRAFT campaign can be dispatched by an Owner/Admin,
    transitions to QUEUED, returns a structured response, and enqueues the Celery task."""
    owner_token = await register_and_login(async_client, "owner_disp1@test.com", "Owner One")
    company_id = await create_company_helper(async_client, owner_token, "Disp Org 1")
    camp_id, _ = await setup_ready_campaign(async_client, db_session, owner_token, company_id)

    mock_celery_task = MagicMock()
    mock_celery_task.id = "celery-task-uuid-12345"

    with patch("app.modules.campaigns.dispatch_service.dispatch_campaign_task.delay", return_value=mock_celery_task) as mock_delay:
        resp = await async_client.post(
            f"/api/v1/companies/{company_id}/campaigns/{camp_id}/dispatch",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()

        assert data["campaign_id"] == camp_id
        assert data["company_id"] == company_id
        assert data["status"] == "QUEUED"
        assert data["task_id"] == "celery-task-uuid-12345"
        assert data["eligible_recipient_count"] == 1
        assert data["total_recipient_count"] == 1
        assert "dispatched_at" in data

        # Verify Celery delay was called once with primitive IDs
        mock_delay.assert_called_once_with(
            campaign_id=camp_id,
            company_id=company_id,
        )

    # Verify state in database
    camp_res = await db_session.execute(select(Campaign).where(Campaign.id == camp_id))
    camp_db = camp_res.scalar_one()
    assert camp_db.status == "QUEUED"

    # Verify invariant: zero CampaignDelivery rows created
    deliv_res = await db_session.execute(select(CampaignDelivery).where(CampaignDelivery.campaign_id == camp_id))
    assert len(deliv_res.scalars().all()) == 0

    # Verify invariant: zero Email rows created
    email_res = await db_session.execute(select(Email).where(Email.company_id == company_id))
    assert len(email_res.scalars().all()) == 0


@pytest.mark.anyio
async def test_dispatch_campaign_requires_owner_or_admin(async_client: AsyncClient, db_session: AsyncSession):
    """Verify that a MEMBER receives 403 Forbidden and cannot dispatch a campaign."""
    owner_token = await register_and_login(async_client, "owner_disp2@test.com", "Owner Two")
    member_token = await register_and_login(async_client, "member_disp2@test.com", "Member Two")
    company_id = await create_company_helper(async_client, owner_token, "Disp Org 2")
    await add_company_member_helper(async_client, owner_token, company_id, "member_disp2@test.com", "MEMBER")

    camp_id, _ = await setup_ready_campaign(async_client, db_session, owner_token, company_id)

    with patch("app.modules.campaigns.dispatch_service.dispatch_campaign_task.delay") as mock_delay:
        resp = await async_client.post(
            f"/api/v1/companies/{company_id}/campaigns/{camp_id}/dispatch",
            headers={"Authorization": f"Bearer {member_token}"},
        )
        assert resp.status_code == 403
        mock_delay.assert_not_called()

    # Campaign must remain in DRAFT
    camp_res = await db_session.execute(select(Campaign).where(Campaign.id == camp_id))
    assert camp_res.scalar_one().status == "DRAFT"


@pytest.mark.anyio
async def test_dispatch_campaign_cross_company_isolation(async_client: AsyncClient, db_session: AsyncSession):
    """Verify that a company cannot dispatch another company's campaign (404 anti-enumeration)."""
    token_a = await register_and_login(async_client, "owner_org_a@test.com", "Owner A")
    token_b = await register_and_login(async_client, "owner_org_b@test.com", "Owner B")
    company_a = await create_company_helper(async_client, token_a, "Company A")
    company_b = await create_company_helper(async_client, token_b, "Company B")

    camp_a, _ = await setup_ready_campaign(async_client, db_session, token_a, company_a)

    with patch("app.modules.campaigns.dispatch_service.dispatch_campaign_task.delay") as mock_delay:
        resp = await async_client.post(
            f"/api/v1/companies/{company_b}/campaigns/{camp_a}/dispatch",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp.status_code == 404
        mock_delay.assert_not_called()


# =============================================================================
# 2. Preflight & Eligibility Tests
# =============================================================================

@pytest.mark.anyio
async def test_dispatch_blocked_preflight_prevents_dispatch(async_client: AsyncClient, db_session: AsyncSession):
    """Verify that a campaign with blocking preflight issues (e.g., no recipients, missing subject)
    is rejected with 400 Bad Request and not enqueued."""
    owner_token = await register_and_login(async_client, "owner_disp3@test.com", "Owner Three")
    company_id = await create_company_helper(async_client, owner_token, "Disp Org 3")

    dom_id = await create_domain_helper(async_client, owner_token, company_id, "dispatch-blocked.com")
    acc_id = await create_email_account_helper(async_client, owner_token, company_id, "sender@dispatch-blocked.com", domain_id=dom_id)

    # Create campaign without recipients and empty subject
    create_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "name": "Empty Campaign",
            "email_account_id": acc_id,
            "subject": "",
            "body_text": "Some text",
        },
    )
    camp_id = create_resp.json()["id"]

    with patch("app.modules.campaigns.dispatch_service.dispatch_campaign_task.delay") as mock_delay:
        resp = await async_client.post(
            f"/api/v1/companies/{company_id}/campaigns/{camp_id}/dispatch",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert resp.status_code == 400
        assert "preflight validation failed" in resp.json()["detail"].lower()
        mock_delay.assert_not_called()

    # In DB, campaign remains DRAFT
    camp_res = await db_session.execute(select(Campaign).where(Campaign.id == camp_id))
    assert camp_res.scalar_one().status == "DRAFT"


# =============================================================================
# 3. State & Duplicate Protection Tests
# =============================================================================

@pytest.mark.anyio
async def test_dispatch_already_queued_returns_conflict(async_client: AsyncClient, db_session: AsyncSession):
    """Verify that attempting to dispatch an already QUEUED campaign returns 409 Conflict
    and does NOT enqueue a duplicate Celery task."""
    owner_token = await register_and_login(async_client, "owner_disp4@test.com", "Owner Four")
    company_id = await create_company_helper(async_client, owner_token, "Disp Org 4")
    camp_id, _ = await setup_ready_campaign(async_client, db_session, owner_token, company_id)

    # Transition to QUEUED directly
    camp_res = await db_session.execute(select(Campaign).where(Campaign.id == camp_id))
    camp = camp_res.scalar_one()
    camp.status = CampaignStatus.QUEUED.value
    await db_session.commit()

    with patch("app.modules.campaigns.dispatch_service.dispatch_campaign_task.delay") as mock_delay:
        resp = await async_client.post(
            f"/api/v1/companies/{company_id}/campaigns/{camp_id}/dispatch",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert resp.status_code == 409
        assert "already queued" in resp.json()["detail"].lower()
        mock_delay.assert_not_called()


@pytest.mark.anyio
async def test_dispatch_running_or_terminal_states_rejected(async_client: AsyncClient, db_session: AsyncSession):
    """Verify that RUNNING, COMPLETED, CANCELLED, and FAILED campaigns cannot be dispatched."""
    owner_token = await register_and_login(async_client, "owner_disp5@test.com", "Owner Five")
    company_id = await create_company_helper(async_client, owner_token, "Disp Org 5")
    camp_id, _ = await setup_ready_campaign(async_client, db_session, owner_token, company_id)

    # 1. RUNNING -> 409 Conflict
    camp_res = await db_session.execute(select(Campaign).where(Campaign.id == camp_id))
    camp = camp_res.scalar_one()
    camp.status = CampaignStatus.RUNNING.value
    await db_session.commit()

    resp = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}/dispatch",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 409

    # 2. Terminal states -> 400 Bad Request
    for term_status in [CampaignStatus.COMPLETED.value, CampaignStatus.CANCELLED.value, CampaignStatus.FAILED.value]:
        camp.status = term_status
        await db_session.commit()

        resp = await async_client.post(
            f"/api/v1/companies/{company_id}/campaigns/{camp_id}/dispatch",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert resp.status_code == 400
        assert "terminal state" in resp.json()["detail"].lower()


@pytest.mark.anyio
async def test_dispatch_scheduled_campaign_transitions_to_queued(async_client: AsyncClient, db_session: AsyncSession):
    """Verify that a campaign in SCHEDULED status can be dispatched, transitioning to QUEUED."""
    owner_token = await register_and_login(async_client, "owner_disp6@test.com", "Owner Six")
    company_id = await create_company_helper(async_client, owner_token, "Disp Org 6")
    camp_id, _ = await setup_ready_campaign(async_client, db_session, owner_token, company_id)

    # Transition to SCHEDULED
    camp_res = await db_session.execute(select(Campaign).where(Campaign.id == camp_id))
    camp = camp_res.scalar_one()
    camp.status = CampaignStatus.SCHEDULED.value
    await db_session.commit()

    with patch("app.modules.campaigns.dispatch_service.dispatch_campaign_task.delay") as mock_delay:
        mock_delay.return_value = MagicMock(id="scheduled-to-queued-task")
        resp = await async_client.post(
            f"/api/v1/companies/{company_id}/campaigns/{camp_id}/dispatch",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "QUEUED"
        mock_delay.assert_called_once()

    await db_session.refresh(camp)
    assert camp.status == "QUEUED"


# =============================================================================
# 4. Celery Safety & Broker Failure Handling Tests
# =============================================================================

@pytest.mark.anyio
async def test_dispatch_celery_broker_failure_reverts_state(async_client: AsyncClient, db_session: AsyncSession):
    """Verify that if Celery task enqueuing fails (e.g. Redis unreachable), the campaign
    status is safely reverted back to its previous state (not left orphaned in QUEUED)
    and 503 is returned."""
    owner_token = await register_and_login(async_client, "owner_disp7@test.com", "Owner Seven")
    company_id = await create_company_helper(async_client, owner_token, "Disp Org 7")
    camp_id, _ = await setup_ready_campaign(async_client, db_session, owner_token, company_id)

    with patch("app.modules.campaigns.dispatch_service.dispatch_campaign_task.delay", side_effect=Exception("Redis broker connection timeout")):
        resp = await async_client.post(
            f"/api/v1/companies/{company_id}/campaigns/{camp_id}/dispatch",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert resp.status_code == 503
        assert "failed to enqueue" in resp.json()["detail"].lower()

    # Verify campaign reverted to DRAFT in database
    camp_res = await db_session.execute(select(Campaign).where(Campaign.id == camp_id))
    assert camp_res.scalar_one().status == "DRAFT"


# =============================================================================
# 5. Celery Worker Task Unit Tests
# =============================================================================

@pytest.mark.anyio
async def test_celery_worker_task_execution(async_client: AsyncClient, db_session: AsyncSession):
    """Verify the Celery worker task execution logic when invoked on a QUEUED campaign."""
    owner_token = await register_and_login(async_client, "owner_disp8@test.com", "Owner Eight")
    company_id = await create_company_helper(async_client, owner_token, "Disp Org 8")
    camp_id, _ = await setup_ready_campaign(async_client, db_session, owner_token, company_id)

    # Set status to QUEUED
    camp_res = await db_session.execute(select(Campaign).where(Campaign.id == camp_id))
    camp = camp_res.scalar_one()
    camp.status = CampaignStatus.QUEUED.value
    await db_session.commit()

    # Configure worker db to use test db session maker
    from app.workers import tasks
    orig_session_maker = tasks.WorkerAsyncSessionLocal
    tasks.WorkerAsyncSessionLocal = TestAsyncSessionLocal

    try:
        # Run worker async core with mocked SMTP
        with patch("app.services.smtp.client.SMTPClient.send_email_sync"):
            result = await _async_dispatch_campaign_task(campaign_id=camp_id, company_id=company_id)
            assert result["status"] == CampaignStatus.COMPLETED.value
            assert result["campaign_id"] == camp_id
            assert result["company_id"] == company_id
            assert result["sent_count"] >= 1

        # Verify tenant mismatch returns NOT_FOUND
        mismatch_result = await _async_dispatch_campaign_task(campaign_id=camp_id, company_id=99999)
        assert mismatch_result["status"] == "NOT_FOUND"

        # Verify non-queued campaign is skipped
        camp.status = CampaignStatus.DRAFT.value
        await db_session.commit()
        skip_result = await _async_dispatch_campaign_task(campaign_id=camp_id, company_id=company_id)
        assert skip_result["status"] == "SKIPPED"

    finally:
        tasks.WorkerAsyncSessionLocal = orig_session_maker


@pytest.mark.anyio
async def test_celery_worker_task_executes_delivery_and_creates_campaign_deliveries(async_client: AsyncClient, db_session: AsyncSession):
    """Verify that Celery worker task executes campaign delivery and creates CampaignDelivery rows."""
    owner_token = await register_and_login(async_client, "owner_disp9@test.com", "Owner Nine")
    company_id = await create_company_helper(async_client, owner_token, "Disp Org 9")
    camp_id, _ = await setup_ready_campaign(async_client, db_session, owner_token, company_id)

    camp_res = await db_session.execute(select(Campaign).where(Campaign.id == camp_id))
    camp = camp_res.scalar_one()
    camp.status = CampaignStatus.QUEUED.value
    await db_session.commit()

    from app.workers import tasks
    orig_session_maker = tasks.WorkerAsyncSessionLocal
    tasks.WorkerAsyncSessionLocal = TestAsyncSessionLocal

    try:
        with patch("app.services.smtp.client.SMTPClient.send_email_sync") as mock_smtp:
            result = await _async_dispatch_campaign_task(campaign_id=camp_id, company_id=company_id)
            assert result["status"] == CampaignStatus.COMPLETED.value

            # Invariant: SMTP was called and CampaignDelivery records created
            assert mock_smtp.called
            deliv_res = await db_session.execute(select(CampaignDelivery).where(CampaignDelivery.campaign_id == camp_id))
            deliveries = deliv_res.scalars().all()
            assert len(deliveries) > 0
            assert all(d.status == CampaignDeliveryStatus.SENT.value for d in deliveries)

    finally:
        tasks.WorkerAsyncSessionLocal = orig_session_maker
