from datetime import datetime, timedelta, timezone
from httpx import AsyncClient
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.campaigns.models import Campaign, CampaignStatus
from app.modules.campaigns.schemas import CampaignCreate, CampaignUpdate
from app.modules.campaigns.service import CampaignService
from app.modules.companies.models import Company, CompanyRole, CompanyUser
from app.modules.email_accounts.models import EmailAccount


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


async def create_company_helper(client: AsyncClient, token: str, name: str = "Campaign Org") -> int:
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


async def create_email_account_helper(
    client: AsyncClient,
    token: str,
    company_id: int,
    email_address: str = "sender@company.com",
    name: str = "Primary Sender",
) -> int:
    """Create an active email account under a company and return its ID."""
    resp = await client.post(
        f"/api/v1/companies/{company_id}/email-accounts",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": name,
            "email_address": email_address,
            "provider": "CUSTOM",
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "smtp_security": "STARTTLS",
            "smtp_username": email_address,
            "smtp_password": "SecretPassword123!",
            "imap_host": "imap.example.com",
            "imap_port": 993,
            "imap_security": "SSL",
            "imap_username": email_address,
            "imap_password": "SecretPassword123!",
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


# =============================================================================
# 1. Campaign CRUD Tests
# =============================================================================

@pytest.mark.asyncio
async def test_create_campaign_success(async_client: AsyncClient):
    """Test successful campaign creation by company owner with initial DRAFT status."""
    token = await register_and_login(async_client, "owner_crud@company.com", "Owner User")
    company_id = await create_company_helper(async_client, token, "CRUD Co")
    account_id = await create_email_account_helper(async_client, token, company_id)

    payload = {
        "name": "Q4 Outreach Campaign",
        "email_account_id": account_id,
        "subject": "Exclusive Year-End Update",
        "body_text": "Hello, here is our year-end update.",
        "body_html": "<p>Hello, here is our year-end update.</p>",
    }

    resp = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"] is not None
    assert data["company_id"] == company_id
    assert data["email_account_id"] == account_id
    assert data["name"] == "Q4 Outreach Campaign"
    assert data["subject"] == "Exclusive Year-End Update"
    assert data["body_text"] == "Hello, here is our year-end update."
    assert data["body_html"] == "<p>Hello, here is our year-end update.</p>"
    assert data["status"] == "DRAFT"
    assert data["scheduled_at"] is None
    assert data["started_at"] is None
    assert data["completed_at"] is None
    assert data["created_by_user_id"] is not None


@pytest.mark.asyncio
async def test_create_campaign_inactive_or_foreign_account_rejected(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Test that creating a campaign with an inactive or foreign email account is rejected."""
    token_a = await register_and_login(async_client, "owner_co_a@test.com", "Owner A")
    company_a_id = await create_company_helper(async_client, token_a, "Company A")
    account_a_id = await create_email_account_helper(async_client, token_a, company_a_id, "a@company.com")

    token_b = await register_and_login(async_client, "owner_co_b@test.com", "Owner B")
    company_b_id = await create_company_helper(async_client, token_b, "Company B")

    # 1. Foreign account: Company B attempts to create campaign with Company A's account
    resp_foreign = await async_client.post(
        f"/api/v1/companies/{company_b_id}/campaigns",
        headers={"Authorization": f"Bearer {token_b}"},
        json={
            "name": "Intruder Campaign",
            "email_account_id": account_a_id,
            "subject": "Hey",
        },
    )
    assert resp_foreign.status_code == 404

    # 2. Inactive account: Mark account_a as inactive directly in DB
    account_obj = (await db_session.execute(select(EmailAccount).where(EmailAccount.id == account_a_id))).scalar_one()
    account_obj.is_active = False
    await db_session.commit()

    resp_inactive = await async_client.post(
        f"/api/v1/companies/{company_a_id}/campaigns",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "name": "Inactive Account Campaign",
            "email_account_id": account_a_id,
            "subject": "Hey",
        },
    )
    assert resp_inactive.status_code == 400
    assert "inactive" in resp_inactive.json()["detail"].lower()


@pytest.mark.asyncio
async def test_list_campaigns_isolation_and_filters(async_client: AsyncClient):
    """Test listing campaigns with company isolation, status filtering, and pagination."""
    token_1 = await register_and_login(async_client, "list_owner1@co.com", "Owner 1")
    company_1_id = await create_company_helper(async_client, token_1, "Co 1")
    account_1_id = await create_email_account_helper(async_client, token_1, company_1_id, "acc1@co.com")

    token_2 = await register_and_login(async_client, "list_owner2@co.com", "Owner 2")
    company_2_id = await create_company_helper(async_client, token_2, "Co 2")
    account_2_id = await create_email_account_helper(async_client, token_2, company_2_id, "acc2@co.com")

    # Create 3 campaigns in Company 1
    for i in range(3):
        await async_client.post(
            f"/api/v1/companies/{company_1_id}/campaigns",
            headers={"Authorization": f"Bearer {token_1}"},
            json={"name": f"Campaign 1-{i}", "email_account_id": account_1_id, "subject": f"Sub {i}"},
        )

    # Create 1 campaign in Company 2
    await async_client.post(
        f"/api/v1/companies/{company_2_id}/campaigns",
        headers={"Authorization": f"Bearer {token_2}"},
        json={"name": "Campaign 2-0", "email_account_id": account_2_id, "subject": "Sub 2-0"},
    )

    # Company 1 lists: should see exactly 3
    resp1 = await async_client.get(
        f"/api/v1/companies/{company_1_id}/campaigns",
        headers={"Authorization": f"Bearer {token_1}"},
    )
    assert resp1.status_code == 200
    camps1 = resp1.json()
    assert len(camps1) == 3
    for c in camps1:
        assert c["company_id"] == company_1_id

    # Pagination: limit=2, offset=1
    resp_page = await async_client.get(
        f"/api/v1/companies/{company_1_id}/campaigns?limit=2&offset=1",
        headers={"Authorization": f"Bearer {token_1}"},
    )
    assert resp_page.status_code == 200
    camps_page = resp_page.json()
    assert len(camps_page) == 2

    # Status filter: status=DRAFT
    resp_filter = await async_client.get(
        f"/api/v1/companies/{company_1_id}/campaigns?status=DRAFT",
        headers={"Authorization": f"Bearer {token_1}"},
    )
    assert resp_filter.status_code == 200
    assert len(resp_filter.json()) == 3

    # Status filter non-existent status: returns empty list
    resp_empty = await async_client.get(
        f"/api/v1/companies/{company_1_id}/campaigns?status=COMPLETED",
        headers={"Authorization": f"Bearer {token_1}"},
    )
    assert resp_empty.status_code == 200
    assert len(resp_empty.json()) == 0


@pytest.mark.asyncio
async def test_get_campaign_detail(async_client: AsyncClient):
    """Test retrieving campaign detail schema including sender account information."""
    token = await register_and_login(async_client, "detail_owner@co.com", "Detail Owner")
    company_id = await create_company_helper(async_client, token, "Detail Co")
    account_id = await create_email_account_helper(async_client, token, company_id, "send@detail.com", "Sender Box")

    create_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Detail Campaign", "email_account_id": account_id, "subject": "Hello World"},
    )
    camp_id = create_resp.json()["id"]

    resp = await async_client.get(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["id"] == camp_id
    assert detail["name"] == "Detail Campaign"
    assert detail["email_account_name"] == "Sender Box"
    assert detail["email_account_address"] == "send@detail.com"
    assert detail["recipient_count"] == 0


@pytest.mark.asyncio
async def test_update_draft_campaign_and_reject_non_draft(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Test that only DRAFT campaigns can be modified and direct status edits are forbidden."""
    token = await register_and_login(async_client, "update_owner@co.com", "Update Owner")
    company_id = await create_company_helper(async_client, token, "Update Co")
    account_id = await create_email_account_helper(async_client, token, company_id)

    create_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Original Name", "email_account_id": account_id, "subject": "Original Subject"},
    )
    camp_id = create_resp.json()["id"]

    # 1. Valid update on DRAFT
    patch_resp = await async_client.patch(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Updated Name", "subject": "Updated Subject", "body_text": "Updated Body"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["name"] == "Updated Name"
    assert patch_resp.json()["subject"] == "Updated Subject"
    assert patch_resp.json()["body_text"] == "Updated Body"

    # 2. Attempting to directly patch status via extra forbid returns 422
    patch_status_resp = await async_client.patch(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"status": "RUNNING"},
    )
    assert patch_status_resp.status_code == 422

    # 3. Transition campaign to RUNNING via DB, then verify PATCH is rejected with 400
    camp_obj = (await db_session.execute(select(Campaign).where(Campaign.id == camp_id))).scalar_one()
    camp_obj.status = CampaignStatus.RUNNING.value
    await db_session.commit()

    patch_non_draft_resp = await async_client.patch(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Forbidden Edit"},
    )
    assert patch_non_draft_resp.status_code == 400
    assert "only draft" in patch_non_draft_resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_delete_campaign_eligibility_and_cascade(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Test deletion eligibility: DRAFT/COMPLETED/CANCELLED/FAILED succeed, active states return 409."""
    token = await register_and_login(async_client, "del_owner@co.com", "Del Owner")
    company_id = await create_company_helper(async_client, token, "Del Co")
    account_id = await create_email_account_helper(async_client, token, company_id)

    # 1. Create and delete DRAFT -> 204
    c1 = (await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Draft to Delete", "email_account_id": account_id, "subject": "Sub"},
    )).json()["id"]

    del_resp = await async_client.delete(
        f"/api/v1/companies/{company_id}/campaigns/{c1}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_resp.status_code == 204

    # Verify deleted
    get_resp = await async_client.get(
        f"/api/v1/companies/{company_id}/campaigns/{c1}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_resp.status_code == 404

    # 2. Reject deletion of active state (RUNNING, QUEUED, PAUSED) -> 409
    c2 = (await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Running to Delete", "email_account_id": account_id, "subject": "Sub"},
    )).json()["id"]

    camp_obj = (await db_session.execute(select(Campaign).where(Campaign.id == c2))).scalar_one()
    camp_obj.status = CampaignStatus.RUNNING.value
    await db_session.commit()

    del_running_resp = await async_client.delete(
        f"/api/v1/companies/{company_id}/campaigns/{c2}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_running_resp.status_code == 409
    assert "active campaigns" in del_running_resp.json()["detail"].lower()

    # 3. Allow deletion of terminal state (CANCELLED) -> 204
    camp_obj.status = CampaignStatus.CANCELLED.value
    await db_session.commit()

    del_cancelled_resp = await async_client.delete(
        f"/api/v1/companies/{company_id}/campaigns/{c2}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_cancelled_resp.status_code == 204


# =============================================================================
# 2. Authorization & Tenant Isolation Tests
# =============================================================================

@pytest.mark.asyncio
async def test_authorization_roles_and_permissions(async_client: AsyncClient):
    """Test role matrix: OWNER/ADMIN have full management; MEMBER has read-only access."""
    # 1. Setup company with Owner, Admin, Member
    owner_token = await register_and_login(async_client, "owner_roles@co.com", "Owner")
    company_id = await create_company_helper(async_client, owner_token, "Roles Co")
    account_id = await create_email_account_helper(async_client, owner_token, company_id)

    admin_token = await register_and_login(async_client, "admin_roles@co.com", "Admin")
    await add_company_member_helper(async_client, owner_token, company_id, "admin_roles@co.com", role="ADMIN")

    member_token = await register_and_login(async_client, "member_roles@co.com", "Member")
    await add_company_member_helper(async_client, owner_token, company_id, "member_roles@co.com", role="MEMBER")

    # 2. Admin creates campaign -> 201
    create_admin_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "Admin Campaign", "email_account_id": account_id, "subject": "Sub"},
    )
    assert create_admin_resp.status_code == 201
    camp_id = create_admin_resp.json()["id"]

    # 3. Member reads campaign -> 200
    read_member_resp = await async_client.get(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert read_member_resp.status_code == 200

    # 4. Member lists campaigns -> 200
    list_member_resp = await async_client.get(
        f"/api/v1/companies/{company_id}/campaigns",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert list_member_resp.status_code == 200
    assert len(list_member_resp.json()) == 1

    # 5. Member mutation attempts are rejected -> 403 Forbidden
    # Create
    m_create = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns",
        headers={"Authorization": f"Bearer {member_token}"},
        json={"name": "Member Campaign", "email_account_id": account_id, "subject": "Sub"},
    )
    assert m_create.status_code == 403

    # Update
    m_update = await async_client.patch(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}",
        headers={"Authorization": f"Bearer {member_token}"},
        json={"name": "Member Edit"},
    )
    assert m_update.status_code == 403

    # Schedule
    m_sched = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}/schedule",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert m_sched.status_code == 403

    # Delete
    m_del = await async_client.delete(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert m_del.status_code == 403


@pytest.mark.asyncio
async def test_cross_company_isolation_anti_enumeration(async_client: AsyncClient):
    """Test that cross-company access attempts return 404 with anti-enumeration protection."""
    token_a = await register_and_login(async_client, "owner_anti_a@co.com", "Owner A")
    company_a_id = await create_company_helper(async_client, token_a, "Anti Co A")
    account_a_id = await create_email_account_helper(async_client, token_a, company_a_id)

    token_b = await register_and_login(async_client, "owner_anti_b@co.com", "Owner B")
    company_b_id = await create_company_helper(async_client, token_b, "Anti Co B")

    camp_a = (await async_client.post(
        f"/api/v1/companies/{company_a_id}/campaigns",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"name": "Campaign Co A", "email_account_id": account_a_id, "subject": "Sub"},
    )).json()["id"]

    # Company B user attempts to access Company A's campaign through Company B's route
    get_resp = await async_client.get(
        f"/api/v1/companies/{company_b_id}/campaigns/{camp_a}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert get_resp.status_code == 404

    patch_resp = await async_client.patch(
        f"/api/v1/companies/{company_b_id}/campaigns/{camp_a}",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"name": "Hacked"},
    )
    assert patch_resp.status_code == 404

    del_resp = await async_client.delete(
        f"/api/v1/companies/{company_b_id}/campaigns/{camp_a}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert del_resp.status_code == 404

    sched_resp = await async_client.post(
        f"/api/v1/companies/{company_b_id}/campaigns/{camp_a}/schedule",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert sched_resp.status_code == 404


# =============================================================================
# 3. State Machine & Transition Service Tests
# =============================================================================

@pytest.mark.asyncio
async def test_state_machine_valid_transitions_and_timestamps(
    db_session: AsyncSession,
):
    """Test full lawful state transition pathways and automated timestamp setting."""
    company = Company(name="State Machine Co")
    db_session.add(company)
    await db_session.commit()
    await db_session.refresh(company)

    account = EmailAccount(
        company_id=company.id,
        name="State Sender",
        email_address="state@co.com",
    )
    db_session.add(account)
    await db_session.commit()
    await db_session.refresh(account)

    campaign = Campaign(
        company_id=company.id,
        email_account_id=account.id,
        name="State Campaign",
        status=CampaignStatus.DRAFT.value,
    )
    db_session.add(campaign)
    await db_session.commit()
    await db_session.refresh(campaign)

    # 1. DRAFT -> SCHEDULED
    t1 = await CampaignService.transition_state(db_session, company.id, campaign.id, CampaignStatus.SCHEDULED)
    assert t1.status == CampaignStatus.SCHEDULED.value

    # 2. SCHEDULED -> DRAFT (clears scheduled_at)
    campaign.scheduled_at = datetime.now(timezone.utc) + timedelta(days=1)
    await db_session.commit()
    t2 = await CampaignService.transition_state(db_session, company.id, campaign.id, CampaignStatus.DRAFT)
    assert t2.status == CampaignStatus.DRAFT.value
    assert t2.scheduled_at is None

    # 3. DRAFT -> QUEUED
    t3 = await CampaignService.transition_state(db_session, company.id, campaign.id, CampaignStatus.QUEUED)
    assert t3.status == CampaignStatus.QUEUED.value

    # 4. QUEUED -> RUNNING (sets started_at)
    assert campaign.started_at is None
    t4 = await CampaignService.transition_state(db_session, company.id, campaign.id, CampaignStatus.RUNNING)
    assert t4.status == CampaignStatus.RUNNING.value
    assert t4.started_at is not None

    # 5. RUNNING -> PAUSED
    t5 = await CampaignService.transition_state(db_session, company.id, campaign.id, CampaignStatus.PAUSED)
    assert t5.status == CampaignStatus.PAUSED.value

    # 6. PAUSED -> RUNNING
    t6 = await CampaignService.transition_state(db_session, company.id, campaign.id, CampaignStatus.RUNNING)
    assert t6.status == CampaignStatus.RUNNING.value

    # 7. RUNNING -> COMPLETED (sets completed_at)
    assert campaign.completed_at is None
    t7 = await CampaignService.transition_state(db_session, company.id, campaign.id, CampaignStatus.COMPLETED)
    assert t7.status == CampaignStatus.COMPLETED.value
    assert t7.completed_at is not None


@pytest.mark.asyncio
async def test_state_machine_invalid_transitions_and_terminal_protection(
    db_session: AsyncSession,
):
    """Test that unlawful state transitions and moves out of terminal states are rejected."""
    company = Company(name="Invalid State Co")
    db_session.add(company)
    await db_session.commit()
    await db_session.refresh(company)

    account = EmailAccount(
        company_id=company.id,
        name="Invalid Sender",
        email_address="invalid@co.com",
    )
    db_session.add(account)
    await db_session.commit()
    await db_session.refresh(account)

    campaign = Campaign(
        company_id=company.id,
        email_account_id=account.id,
        name="Invalid Campaign",
        status=CampaignStatus.DRAFT.value,
    )
    db_session.add(campaign)
    await db_session.commit()
    await db_session.refresh(campaign)

    # 1. DRAFT cannot directly jump to RUNNING or COMPLETED
    with pytest.raises(Exception) as exc1:
        await CampaignService.transition_state(db_session, company.id, campaign.id, CampaignStatus.RUNNING)
    assert "Invalid state transition" in str(exc1.value)

    with pytest.raises(Exception) as exc2:
        await CampaignService.transition_state(db_session, company.id, campaign.id, CampaignStatus.COMPLETED)
    assert "Invalid state transition" in str(exc2.value)

    # 2. Terminal state protection: COMPLETED cannot transition to anything
    campaign.status = CampaignStatus.COMPLETED.value
    await db_session.commit()

    for target in [CampaignStatus.RUNNING, CampaignStatus.DRAFT, CampaignStatus.QUEUED, CampaignStatus.CANCELLED]:
        with pytest.raises(Exception) as exc_term:
            await CampaignService.transition_state(db_session, company.id, campaign.id, target)
        assert "Invalid state transition" in str(exc_term.value)

    # 3. Terminal state CANCELLED cannot transition to anything
    campaign.status = CampaignStatus.CANCELLED.value
    await db_session.commit()
    with pytest.raises(Exception):
        await CampaignService.transition_state(db_session, company.id, campaign.id, CampaignStatus.RUNNING)

    # 4. Terminal state FAILED cannot transition to anything
    campaign.status = CampaignStatus.FAILED.value
    await db_session.commit()
    with pytest.raises(Exception):
        await CampaignService.transition_state(db_session, company.id, campaign.id, CampaignStatus.RUNNING)


# =============================================================================
# 4. State Action API Endpoints (Schedule, Pause, Resume, Cancel)
# =============================================================================

@pytest.mark.asyncio
async def test_schedule_endpoint_future_and_send_now(async_client: AsyncClient):
    """Test POST /schedule endpoint for both future scheduling and immediate queuing."""
    token = await register_and_login(async_client, "sched_owner@co.com", "Sched Owner")
    company_id = await create_company_helper(async_client, token, "Sched Co")
    account_id = await create_email_account_helper(async_client, token, company_id)

    # 1. Schedule with future datetime -> SCHEDULED
    c_future = (await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Future Campaign", "email_account_id": account_id, "subject": "Sub"},
    )).json()["id"]

    future_time = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    resp_future = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{c_future}/schedule",
        headers={"Authorization": f"Bearer {token}"},
        json={"scheduled_at": future_time},
    )
    assert resp_future.status_code == 200
    assert resp_future.json()["status"] == "SCHEDULED"
    assert resp_future.json()["scheduled_at"] is not None

    # 2. Schedule with past datetime -> 400
    past_time = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    c_past = (await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Past Campaign", "email_account_id": account_id, "subject": "Sub"},
    )).json()["id"]

    resp_past = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{c_past}/schedule",
        headers={"Authorization": f"Bearer {token}"},
        json={"scheduled_at": past_time},
    )
    assert resp_past.status_code == 400
    assert "must be in the future" in resp_past.json()["detail"].lower()

    # 3. Send-now (no scheduled_at provided) -> QUEUED
    c_now = (await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Now Campaign", "email_account_id": account_id, "subject": "Sub"},
    )).json()["id"]

    resp_now = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{c_now}/schedule",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert resp_now.status_code == 200
    assert resp_now.json()["status"] == "QUEUED"
    assert resp_now.json()["scheduled_at"] is None

    # 4. Scheduling a non-DRAFT campaign is rejected
    resp_re_sched = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{c_now}/schedule",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert resp_re_sched.status_code == 400
    assert "only draft" in resp_re_sched.json()["detail"].lower()


@pytest.mark.asyncio
async def test_pause_resume_cancel_endpoints(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Test pause, resume, and cancel state transition endpoints via API."""
    token = await register_and_login(async_client, "lifecycle_owner@co.com", "Lifecycle Owner")
    company_id = await create_company_helper(async_client, token, "Lifecycle Co")
    account_id = await create_email_account_helper(async_client, token, company_id)

    camp_id = (await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Lifecycle Campaign", "email_account_id": account_id, "subject": "Sub"},
    )).json()["id"]

    # 1. Invalid pause on DRAFT -> 400
    resp_pause_draft = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}/pause",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_pause_draft.status_code == 400
    assert "only running" in resp_pause_draft.json()["detail"].lower()

    # Move campaign to RUNNING via DB
    camp_obj = (await db_session.execute(select(Campaign).where(Campaign.id == camp_id))).scalar_one()
    camp_obj.status = CampaignStatus.RUNNING.value
    await db_session.commit()

    # 2. Valid pause on RUNNING -> PAUSED
    resp_pause = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}/pause",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_pause.status_code == 200
    assert resp_pause.json()["status"] == "PAUSED"

    # 3. Invalid resume on RUNNING (when already PAUSED, let's test invalid resume on DRAFT or RUNNING)
    # Valid resume on PAUSED -> RUNNING
    resp_resume = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}/resume",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_resume.status_code == 200
    assert resp_resume.json()["status"] == "RUNNING"

    # Invalid resume on RUNNING -> 400
    resp_resume_again = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}/resume",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_resume_again.status_code == 400
    assert "only paused" in resp_resume_again.json()["detail"].lower()

    # 4. Valid cancel on RUNNING -> CANCELLED
    resp_cancel = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}/cancel",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_cancel.status_code == 200
    assert resp_cancel.json()["status"] == "CANCELLED"

    # 5. Invalid cancel on already CANCELLED -> 400
    resp_cancel_again = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}/cancel",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_cancel_again.status_code == 400


@pytest.mark.asyncio
async def test_update_draft_campaign_with_invalid_email_account(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Test updating campaign email_account_id rejects foreign or inactive accounts."""
    token = await register_and_login(async_client, "up_acc_owner@co.com", "Up Acc Owner")
    company_1_id = await create_company_helper(async_client, token, "Up Acc Co 1")
    account_1_id = await create_email_account_helper(async_client, token, company_1_id, "acc1@co1.com")

    token_2 = await register_and_login(async_client, "up_acc_owner2@co.com", "Up Acc Owner 2")
    company_2_id = await create_company_helper(async_client, token_2, "Up Acc Co 2")
    account_2_id = await create_email_account_helper(async_client, token_2, company_2_id, "acc2@co2.com")

    # Create campaign in company 1
    camp_id = (await async_client.post(
        f"/api/v1/companies/{company_1_id}/campaigns",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Campaign to Update Account", "email_account_id": account_1_id, "subject": "Sub"},
    )).json()["id"]

    # 1. Update with foreign account (account from company 2) -> 404
    resp_foreign = await async_client.patch(
        f"/api/v1/companies/{company_1_id}/campaigns/{camp_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"email_account_id": account_2_id},
    )
    assert resp_foreign.status_code == 404

    # 2. Update with inactive account -> 400
    account_obj = (await db_session.execute(select(EmailAccount).where(EmailAccount.id == account_1_id))).scalar_one()
    account_obj.is_active = False
    await db_session.commit()

    resp_inactive = await async_client.patch(
        f"/api/v1/companies/{company_1_id}/campaigns/{camp_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"email_account_id": account_1_id},
    )
    assert resp_inactive.status_code == 400
    assert "inactive" in resp_inactive.json()["detail"].lower()

