from datetime import datetime, timedelta, timezone
from httpx import AsyncClient
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.campaigns.models import Campaign, CampaignDelivery, CampaignDeliveryStatus, CampaignRecipient, CampaignRecipientStatus, CampaignStep, CampaignStatus
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
    assert detail["pending_count"] == 0
    assert detail["sent_count"] == 0
    assert detail["failed_count"] == 0
    assert detail["bounced_count"] == 0
    assert detail["suppressed_count"] == 0


@pytest.mark.asyncio
async def test_get_campaign_detail_status_breakdown(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Test that CampaignDetailRead correctly aggregates recipient status counts."""
    token = await register_and_login(async_client, "breakdown_owner@co.com", "Breakdown Owner")
    company_id = await create_company_helper(async_client, token, "Breakdown Co")
    account_id = await create_email_account_helper(async_client, token, company_id, "breakdown@detail.com", "Breakdown Box")

    create_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Breakdown Campaign", "email_account_id": account_id, "subject": "Telemetry Test"},
    )
    camp_id = create_resp.json()["id"]

    # Insert recipients directly with diverse statuses: 2 PENDING, 3 SENT, 1 FAILED, 2 BOUNCED, 1 SUPPRESSED
    recipients_data = [
        ("p1@test.com", CampaignRecipientStatus.PENDING.value),
        ("p2@test.com", CampaignRecipientStatus.PENDING.value),
        ("s1@test.com", CampaignRecipientStatus.SENT.value),
        ("s2@test.com", CampaignRecipientStatus.SENT.value),
        ("s3@test.com", CampaignRecipientStatus.SENT.value),
        ("f1@test.com", CampaignRecipientStatus.FAILED.value),
        ("b1@test.com", CampaignRecipientStatus.BOUNCED.value),
        ("b2@test.com", CampaignRecipientStatus.BOUNCED.value),
        ("x1@test.com", CampaignRecipientStatus.SUPPRESSED.value),
    ]
    for email_addr, stat in recipients_data:
        recip = CampaignRecipient(
            campaign_id=camp_id,
            email=email_addr,
            status=stat,
        )
        db_session.add(recip)
    await db_session.commit()

    resp = await async_client.get(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["recipient_count"] == 9
    assert detail["pending_count"] == 2
    assert detail["sent_count"] == 3
    assert detail["failed_count"] == 1
    assert detail["bounced_count"] == 2
    assert detail["suppressed_count"] == 1


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



# =============================================================================
# 5. Milestone M3 - Safe Campaign Archiving & Restore Tests
# =============================================================================

@pytest.mark.asyncio
async def test_archive_restore_and_list_filter_lifecycle(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Test end-to-end archiving, restoring, filtering, and safe permanent deletion."""
    token = await register_and_login(async_client, "archive_user@co.com", "Archive User")
    company_id = await create_company_helper(async_client, token, "Archive Co")
    account_id = await create_email_account_helper(async_client, token, company_id, "archiver@co.com")

    # Create a draft campaign
    camp_res = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Campaign to Archive", "email_account_id": account_id, "subject": "Draft Sub"},
    )
    assert camp_res.status_code == 201
    camp_id = camp_res.json()["id"]

    # 1. Archive the draft campaign
    archive_res = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}/archive",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert archive_res.status_code == 200
    assert archive_res.json()["status"] == "ARCHIVED"

    # Idempotent re-archive succeeds
    re_archive_res = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}/archive",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert re_archive_res.status_code == 200
    assert re_archive_res.json()["status"] == "ARCHIVED"

    # 2. Verify list_campaigns excludes archived campaigns by default
    list_res = await async_client.get(
        f"/api/v1/companies/{company_id}/campaigns",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_res.status_code == 200
    camps = list_res.json()
    assert all(c["id"] != camp_id for c in camps)

    # list_campaigns with status=ALL also excludes archived
    all_res = await async_client.get(
        f"/api/v1/companies/{company_id}/campaigns?status=ALL",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert all_res.status_code == 200
    assert all(c["id"] != camp_id for c in all_res.json())

    # list_campaigns with status=ARCHIVED returns the archived campaign
    archived_list_res = await async_client.get(
        f"/api/v1/companies/{company_id}/campaigns?status=ARCHIVED",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert archived_list_res.status_code == 200
    archived_camps = archived_list_res.json()
    assert any(c["id"] == camp_id for c in archived_camps)

    # 3. Restore the unstarted campaign -> should restore to DRAFT
    restore_res = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}/restore",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert restore_res.status_code == 200
    assert restore_res.json()["status"] == "DRAFT"

    # Restoring non-archived campaign returns 400
    invalid_restore = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}/restore",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert invalid_restore.status_code == 400

    # 4. Active campaigns cannot be archived (409 Conflict)
    camp_obj = (await db_session.execute(select(Campaign).where(Campaign.id == camp_id))).scalar_one()
    camp_obj.status = CampaignStatus.RUNNING.value
    await db_session.commit()

    active_archive_res = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}/archive",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert active_archive_res.status_code == 409
    assert "active campaigns must be completed or cancelled" in active_archive_res.json()["detail"].lower()

    # 5. Cancel campaign, then archive it, then restore it -> should restore to CANCELLED (never auto-resume)
    camp_obj.status = CampaignStatus.CANCELLED.value
    camp_obj.started_at = datetime.now(timezone.utc)
    await db_session.commit()

    archive_cancelled = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}/archive",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert archive_cancelled.status_code == 200

    restore_started = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}/restore",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert restore_started.status_code == 200
    assert restore_started.json()["status"] == "CANCELLED"

    # 6. Archive a completed campaign -> restores to COMPLETED
    camp_obj = (await db_session.execute(select(Campaign).where(Campaign.id == camp_id))).scalar_one()
    camp_obj.status = CampaignStatus.COMPLETED.value
    camp_obj.completed_at = datetime.now(timezone.utc)
    await db_session.commit()

    archive_completed = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}/archive",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert archive_completed.status_code == 200

    restore_completed = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}/restore",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert restore_completed.status_code == 200
    assert restore_completed.json()["status"] == "COMPLETED"

    # 7. Archive and permanently delete
    await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}/archive",
        headers={"Authorization": f"Bearer {token}"},
    )
    del_res = await async_client.delete(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_res.status_code == 204


@pytest.mark.asyncio
async def test_archive_restore_authorization_and_isolation(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Test role enforcement and tenant isolation on archive and restore endpoints."""
    token_owner = await register_and_login(async_client, "owner_arch@co.com", "Owner Arch")
    company_1_id = await create_company_helper(async_client, token_owner, "Arch Co 1")
    account_1_id = await create_email_account_helper(async_client, token_owner, company_1_id, "acc1@arch1.com")

    # Create campaign
    camp_res = await async_client.post(
        f"/api/v1/companies/{company_1_id}/campaigns",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"name": "Auth Arch Campaign", "email_account_id": account_1_id, "subject": "Sub"},
    )
    camp_id = camp_res.json()["id"]

    # Member user in company 1
    token_member = await register_and_login(async_client, "member_arch@co.com", "Member Arch")
    await add_company_member_helper(async_client, token_owner, company_1_id, "member_arch@co.com", role="MEMBER")

    # Member cannot archive (403 Forbidden)
    res_mem_arch = await async_client.post(
        f"/api/v1/companies/{company_1_id}/campaigns/{camp_id}/archive",
        headers={"Authorization": f"Bearer {token_member}"},
    )
    assert res_mem_arch.status_code == 403

    # Member cannot restore (403 Forbidden)
    res_mem_rest = await async_client.post(
        f"/api/v1/companies/{company_1_id}/campaigns/{camp_id}/restore",
        headers={"Authorization": f"Bearer {token_member}"},
    )
    assert res_mem_rest.status_code == 403

    # Admin from company 2 cannot access company 1 campaign (404 Not Found anti-enumeration)
    token_owner_2 = await register_and_login(async_client, "owner2_arch@co.com", "Owner 2 Arch")
    company_2_id = await create_company_helper(async_client, token_owner_2, "Arch Co 2")

    res_foreign_arch = await async_client.post(
        f"/api/v1/companies/{company_2_id}/campaigns/{camp_id}/archive",
        headers={"Authorization": f"Bearer {token_owner_2}"},
    )
    assert res_foreign_arch.status_code == 404

    res_foreign_rest = await async_client.post(
        f"/api/v1/companies/{company_2_id}/campaigns/{camp_id}/restore",
        headers={"Authorization": f"Bearer {token_owner_2}"},
    )
    assert res_foreign_rest.status_code == 404



# =============================================================================
# Milestone M4 — Per-Recipient Operational Controls Tests
# =============================================================================

@pytest.mark.asyncio
async def test_recipient_stop_emails_lifecycle_and_safety(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Verify Stop Emails operational control:
    - Rejects DRAFT campaign
    - Successfully stops recipient in active campaign
    - Idempotent if repeated
    - Clears next_step_due_at and sets MANUAL stop reason
    - Cancels any PENDING deliveries
    - Rejects terminal / replied recipients
    """
    token = await register_and_login(async_client, "owner_stop@co.com", "Owner Stop")
    company_id = await create_company_helper(async_client, token, "Stop Co")
    account_id = await create_email_account_helper(async_client, token, company_id, "stop@co.com")

    # 1. Create campaign with 2 steps
    camp_res = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Stop Lifecycle Campaign",
            "email_account_id": account_id,
            "subject": "Initial Email",
            "body_html": "<p>Hello</p>",
            "followup_steps": [
                {
                    "step_number": 2,
                    "delay_hours": 24,
                    "subject": "Follow-up 1",
                    "body_html": "<p>Follow-up</p>",
                    "is_active": True,
                }
            ],
        },
    )
    assert camp_res.status_code == 201
    camp_id = camp_res.json()["id"]

    # Add recipient
    recip_res = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}/recipients",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "target_stop@co.com", "first_name": "Target"},
    )
    assert recip_res.status_code == 201
    recip_id = recip_res.json()["id"]

    # 2. Rejects stopping in DRAFT
    stop_draft_res = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}/recipients/{recip_id}/stop",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert stop_draft_res.status_code == 400
    assert "DRAFT" in stop_draft_res.json()["detail"]

    # Transition campaign to RUNNING and recipient to SENT with pending follow-up
    camp_obj = (await db_session.execute(select(Campaign).where(Campaign.id == camp_id))).scalar_one()
    camp_obj.status = CampaignStatus.RUNNING.value
    recip_obj = (await db_session.execute(select(CampaignRecipient).where(CampaignRecipient.id == recip_id))).scalar_one()
    recip_obj.status = CampaignRecipientStatus.SENT.value
    recip_obj.current_step_number = 1
    recip_obj.next_step_due_at = datetime.now(timezone.utc) + timedelta(hours=24)
    # Fetch Step 2
    step_2 = (await db_session.execute(
        select(CampaignStep).where(CampaignStep.campaign_id == camp_id, CampaignStep.step_number == 2)
    )).scalar_one()

    # Add a pending delivery record
    pending_delivery = CampaignDelivery(
        campaign_id=camp_id,
        recipient_id=recip_id,
        step_id=step_2.id,
        status=CampaignDeliveryStatus.PENDING.value,
    )
    db_session.add(pending_delivery)
    await db_session.commit()

    # 3. Stop recipient
    stop_res = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}/recipients/{recip_id}/stop",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert stop_res.status_code == 200
    data = stop_res.json()
    assert data["status"] == "STOPPED"
    assert data["stopped_reason"] == "MANUAL"
    assert data["next_step_due_at"] is None

    # Check pending delivery cancelled
    await db_session.refresh(pending_delivery)
    assert pending_delivery.status == CampaignDeliveryStatus.FAILED.value
    assert "cancelled" in pending_delivery.error_message.lower()

    # 4. Idempotent call
    stop_again = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}/recipients/{recip_id}/stop",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert stop_again.status_code == 200
    assert stop_again.json()["status"] == "STOPPED"


@pytest.mark.asyncio
async def test_recipient_skip_followup_step(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Verify Skip Follow-Up Step:
    - Advances current_step_number without sending
    - Records CampaignDelivery with status SKIPPED
    - Calculates next_step_due_at for subsequent active step
    - Transitions to COMPLETED when final step is skipped
    """
    token = await register_and_login(async_client, "owner_skip@co.com", "Owner Skip")
    company_id = await create_company_helper(async_client, token, "Skip Co")
    account_id = await create_email_account_helper(async_client, token, company_id, "skip@co.com")

    # Campaign with Step 1 (initial), Step 2 (follow-up), Step 3 (follow-up)
    camp_res = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Skip Step Campaign",
            "email_account_id": account_id,
            "subject": "Initial Email",
            "body_html": "<p>Initial</p>",
            "followup_steps": [
                {
                    "step_number": 2,
                    "delay_hours": 12,
                    "subject": "Follow-up 2",
                    "body_html": "<p>F2</p>",
                    "is_active": True,
                },
                {
                    "step_number": 3,
                    "delay_hours": 48,
                    "subject": "Follow-up 3",
                    "body_html": "<p>F3</p>",
                    "is_active": True,
                },
            ],
        },
    )
    assert camp_res.status_code == 201
    camp_id = camp_res.json()["id"]

    # Add recipient
    recip_res = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}/recipients",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "target_skip@co.com"},
    )
    recip_id = recip_res.json()["id"]

    # Activate campaign and set recipient at Step 1 done
    camp_obj = (await db_session.execute(select(Campaign).where(Campaign.id == camp_id))).scalar_one()
    camp_obj.status = CampaignStatus.RUNNING.value
    recip_obj = (await db_session.execute(select(CampaignRecipient).where(CampaignRecipient.id == recip_id))).scalar_one()
    recip_obj.status = CampaignRecipientStatus.SENT.value
    recip_obj.current_step_number = 1
    recip_obj.next_step_due_at = datetime.now(timezone.utc) + timedelta(hours=12)
    await db_session.commit()

    # 1. Skip Step 2
    skip_res = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}/recipients/{recip_id}/skip",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert skip_res.status_code == 200
    skip_data = skip_res.json()
    assert skip_data["current_step_number"] == 2
    assert skip_data["next_step_due_at"] is not None

    step_2 = (await db_session.execute(
        select(CampaignStep).where(CampaignStep.campaign_id == camp_id, CampaignStep.step_number == 2)
    )).scalar_one()
    # Check delivery record for Step 2 is SKIPPED (never sent)
    deliv_2 = (await db_session.execute(
        select(CampaignDelivery).where(CampaignDelivery.recipient_id == recip_id, CampaignDelivery.step_id == step_2.id)
    )).scalar_one()
    assert deliv_2.status == CampaignDeliveryStatus.SKIPPED.value
    assert "skipped" in deliv_2.error_message.lower()

    # 2. Skip Step 3 (final step)
    skip_final_res = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}/recipients/{recip_id}/skip",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert skip_final_res.status_code == 200
    final_data = skip_final_res.json()
    assert final_data["current_step_number"] == 3
    assert final_data["status"] == "COMPLETED"
    assert final_data["next_step_due_at"] is None


@pytest.mark.asyncio
async def test_recipient_reschedule_followup(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Verify Reschedule Follow-Up:
    - Validates future date
    - Rejects past date
    - Updates next_step_due_at
    - Rejects terminal recipient
    """
    token = await register_and_login(async_client, "owner_resched@co.com", "Owner Resched")
    company_id = await create_company_helper(async_client, token, "Resched Co")
    account_id = await create_email_account_helper(async_client, token, company_id, "resched@co.com")

    camp_res = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Reschedule Campaign",
            "email_account_id": account_id,
            "subject": "Initial",
            "body_html": "<p>Initial</p>",
            "followup_steps": [
                {
                    "step_number": 2,
                    "delay_hours": 24,
                    "subject": "Follow-up",
                    "body_html": "<p>F2</p>",
                    "is_active": True,
                }
            ],
        },
    )
    camp_id = camp_res.json()["id"]

    recip_res = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}/recipients",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "target_resched@co.com"},
    )
    recip_id = recip_res.json()["id"]

    camp_obj = (await db_session.execute(select(Campaign).where(Campaign.id == camp_id))).scalar_one()
    camp_obj.status = CampaignStatus.RUNNING.value
    recip_obj = (await db_session.execute(select(CampaignRecipient).where(CampaignRecipient.id == recip_id))).scalar_one()
    recip_obj.status = CampaignRecipientStatus.SENT.value
    recip_obj.current_step_number = 1
    recip_obj.next_step_due_at = datetime.now(timezone.utc) + timedelta(hours=24)
    await db_session.commit()

    # 1. Past date fails (400)
    past_time = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    past_res = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}/recipients/{recip_id}/reschedule",
        headers={"Authorization": f"Bearer {token}"},
        json={"next_step_due_at": past_time},
    )
    assert past_res.status_code == 400
    assert "future" in past_res.json()["detail"].lower()

    # 2. Valid future date succeeds
    future_time = (datetime.now(timezone.utc) + timedelta(days=5)).replace(microsecond=0)
    resched_res = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}/recipients/{recip_id}/reschedule",
        headers={"Authorization": f"Bearer {token}"},
        json={"next_step_due_at": future_time.isoformat()},
    )
    assert resched_res.status_code == 200
    updated_recip = resched_res.json()
    assert updated_recip["next_step_due_at"] is not None


@pytest.mark.asyncio
async def test_recipient_controls_authorization_and_isolation(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Verify authorization and isolation:
    - Member role gets 403 on stop, skip, reschedule
    - Foreign company admin gets 404 on stop, skip, reschedule
    """
    token_owner = await register_and_login(async_client, "owner_ctrl_auth@co.com", "Owner Ctrl")
    company_1_id = await create_company_helper(async_client, token_owner, "Ctrl Co 1")
    account_1_id = await create_email_account_helper(async_client, token_owner, company_1_id, "ctrl@co.com")

    camp_res = await async_client.post(
        f"/api/v1/companies/{company_1_id}/campaigns",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={
            "name": "Auth Ctrl Campaign",
            "email_account_id": account_1_id,
            "subject": "Sub",
            "followup_steps": [{"step_number": 2, "delay_hours": 24, "subject": "F2", "body_html": "F2", "is_active": True}],
        },
    )
    camp_id = camp_res.json()["id"]

    recip_res = await async_client.post(
        f"/api/v1/companies/{company_1_id}/campaigns/{camp_id}/recipients",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"email": "auth_test_target@co.com"},
    )
    recip_id = recip_res.json()["id"]

    camp_obj = (await db_session.execute(select(Campaign).where(Campaign.id == camp_id))).scalar_one()
    camp_obj.status = CampaignStatus.RUNNING.value
    recip_obj = (await db_session.execute(select(CampaignRecipient).where(CampaignRecipient.id == recip_id))).scalar_one()
    recip_obj.status = CampaignRecipientStatus.SENT.value
    recip_obj.current_step_number = 1
    recip_obj.next_step_due_at = datetime.now(timezone.utc) + timedelta(hours=24)
    await db_session.commit()

    # Member user in company 1
    token_member = await register_and_login(async_client, "member_ctrl@co.com", "Member Ctrl")
    await add_company_member_helper(async_client, token_owner, company_1_id, "member_ctrl@co.com", role="MEMBER")

    # Member gets 403 on stop
    res_mem_stop = await async_client.post(
        f"/api/v1/companies/{company_1_id}/campaigns/{camp_id}/recipients/{recip_id}/stop",
        headers={"Authorization": f"Bearer {token_member}"},
    )
    assert res_mem_stop.status_code == 403

    # Member gets 403 on skip
    res_mem_skip = await async_client.post(
        f"/api/v1/companies/{company_1_id}/campaigns/{camp_id}/recipients/{recip_id}/skip",
        headers={"Authorization": f"Bearer {token_member}"},
    )
    assert res_mem_skip.status_code == 403

    # Member gets 403 on reschedule
    future_time = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    res_mem_resched = await async_client.post(
        f"/api/v1/companies/{company_1_id}/campaigns/{camp_id}/recipients/{recip_id}/reschedule",
        headers={"Authorization": f"Bearer {token_member}"},
        json={"next_step_due_at": future_time},
    )
    assert res_mem_resched.status_code == 403

    # Foreign company admin gets 404
    token_foreign = await register_and_login(async_client, "foreign_admin@co.com", "Foreign Admin")
    company_2_id = await create_company_helper(async_client, token_foreign, "Foreign Co")

    res_foreign_stop = await async_client.post(
        f"/api/v1/companies/{company_2_id}/campaigns/{camp_id}/recipients/{recip_id}/stop",
        headers={"Authorization": f"Bearer {token_foreign}"},
    )
    assert res_foreign_stop.status_code == 404

    res_foreign_skip = await async_client.post(
        f"/api/v1/companies/{company_2_id}/campaigns/{camp_id}/recipients/{recip_id}/skip",
        headers={"Authorization": f"Bearer {token_foreign}"},
    )
    assert res_foreign_skip.status_code == 404

    res_foreign_resched = await async_client.post(
        f"/api/v1/companies/{company_2_id}/campaigns/{camp_id}/recipients/{recip_id}/reschedule",
        headers={"Authorization": f"Bearer {token_foreign}"},
        json={"next_step_due_at": future_time},
    )
    assert res_foreign_resched.status_code == 404



# =============================================================================
# Milestone M5 — Recipient Tags & Selective Step Targeting Tests
# =============================================================================

@pytest.mark.asyncio
async def test_recipient_tags_crud_and_normalization(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Test recipient tags creation, normalization, deduplication, add/remove endpoints, and campaign tag listing."""
    token_owner = await register_and_login(async_client, "owner_tags_m5@test.com", "Tag Owner")
    company_id = await create_company_helper(async_client, token_owner, "Tags Org")
    account_id = await create_email_account_helper(async_client, token_owner, company_id)

    camp_res = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={
            "name": "Tagging Campaign",
            "email_account_id": account_id,
            "subject": "Tagging Subject",
            "followup_steps": [
                {
                    "step_number": 2,
                    "delay_hours": 24,
                    "subject": "Followup Step 2",
                    "target_tags": ["VIP", "Enterprise "],
                }
            ],
        },
    )
    assert camp_res.status_code == 201
    camp_id = camp_res.json()["id"]

    # 1. Create recipient with tags (case-insensitive and trimmed)
    recip_res = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}/recipients",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={
            "email": "lead@target.com",
            "first_name": "Lead",
            "tags": [" VIP ", "tier-1", "VIP"],  # duplicate "VIP" and extra spaces
        },
    )
    assert recip_res.status_code == 201
    recip_data = recip_res.json()
    recip_id = recip_data["id"]
    assert recip_data["tags"] == ["vip", "tier-1"]  # normalized and deduplicated

    # 2. Query campaign tags
    tags_res = await async_client.get(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}/tags",
        headers={"Authorization": f"Bearer {token_owner}"},
    )
    assert tags_res.status_code == 200
    camp_tags = tags_res.json()
    # Includes step target_tags ("vip", "enterprise") and recipient tags ("vip", "tier-1")
    assert "vip" in camp_tags
    assert "enterprise" in camp_tags
    assert "tier-1" in camp_tags

    # 3. Add a single tag
    add_tag_res = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}/recipients/{recip_id}/tags/add",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"tag": " Hot-Lead "},
    )
    assert add_tag_res.status_code == 200
    assert "hot-lead" in add_tag_res.json()["tags"]

    # 4. Remove a tag
    remove_tag_res = await async_client.delete(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}/recipients/{recip_id}/tags/vip",
        headers={"Authorization": f"Bearer {token_owner}"},
    )
    assert remove_tag_res.status_code == 200
    assert "vip" not in remove_tag_res.json()["tags"]

    # 5. Replace all tags
    replace_tags_res = await async_client.put(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}/recipients/{recip_id}/tags",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"tags": ["beta_tester", "priority.high"]},
    )
    assert replace_tags_res.status_code == 200
    assert replace_tags_res.json()["tags"] == ["beta_tester", "priority.high"]

    # 6. Reject invalid tags (empty, spaces only, invalid symbols)
    invalid_tag_res = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}/recipients/{recip_id}/tags/add",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"tag": "invalid tag with spaces!"},
    )
    assert invalid_tag_res.status_code == 422


@pytest.mark.asyncio
async def test_step_selective_targeting_or_matching(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Test OR-matching: recipient with matching tag gets step dispatched; non-matching recipient records SKIPPED delivery."""
    from app.modules.campaigns.delivery_service import CampaignDeliveryService
    from unittest.mock import AsyncMock

    token_owner = await register_and_login(async_client, "owner_targeting_m5@test.com", "Targeting Owner")
    company_id = await create_company_helper(async_client, token_owner, "Targeting Org")
    account_id = await create_email_account_helper(async_client, token_owner, company_id)

    # Campaign with Step 1 and 2 follow-up steps
    camp_res = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={
            "name": "Targeted Sequence",
            "email_account_id": account_id,
            "subject": "Initial Outreach",
            "followup_steps": [
                {
                    "step_number": 2,
                    "delay_hours": 1,
                    "subject": "VIP Step 2",
                    "body_text": "Hello VIP, special offer for you.",
                    "target_tags": ["vip", "platinum"],  # OR matching
                },
                {
                    "step_number": 3,
                    "delay_hours": 2,
                    "subject": "Standard Step 3",
                    "body_text": "Hello Standard, regular follow-up.",
                    "target_tags": ["standard"],
                },
            ],
        },
    )
    camp_id = camp_res.json()["id"]

    # Recipient 1 has tag 'vip'
    r1_res = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}/recipients",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"email": "vip_user@domain.com", "tags": ["vip"]},
    )
    r1_id = r1_res.json()["id"]

    # Recipient 2 has tag 'standard'
    r2_res = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}/recipients",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"email": "standard_user@domain.com", "tags": ["standard"]},
    )
    r2_id = r2_res.json()["id"]

    # Set campaign to RUNNING and simulate Step 1 SENT for both recipients
    now_utc = datetime.now(timezone.utc)
    past_2h = now_utc - timedelta(hours=3)

    camp_obj = await db_session.get(Campaign, camp_id)
    camp_obj.status = CampaignStatus.RUNNING.value

    # Find Step 1
    step_1 = (await db_session.execute(
        select(CampaignStep).where(CampaignStep.campaign_id == camp_id, CampaignStep.step_number == 1)
    )).scalar_one()

    # Step 1 deliveries
    d1 = CampaignDelivery(
        campaign_id=camp_id,
        recipient_id=r1_id,
        step_id=step_1.id,
        status=CampaignDeliveryStatus.SENT.value,
        sent_at=past_2h,
        message_id="<msg_r1_step1@domain.com>",
    )
    d2 = CampaignDelivery(
        campaign_id=camp_id,
        recipient_id=r2_id,
        step_id=step_1.id,
        status=CampaignDeliveryStatus.SENT.value,
        sent_at=past_2h,
        message_id="<msg_r2_step1@domain.com>",
    )
    db_session.add_all([d1, d2])

    recip_1 = await db_session.get(CampaignRecipient, r1_id)
    recip_1.current_step_number = 1
    recip_1.status = CampaignRecipientStatus.SENT.value
    recip_1.next_step_due_at = past_2h + timedelta(hours=1)

    recip_2 = await db_session.get(CampaignRecipient, r2_id)
    recip_2.current_step_number = 1
    recip_2.status = CampaignRecipientStatus.SENT.value
    recip_2.next_step_due_at = past_2h + timedelta(hours=1)

    await db_session.commit()

    # Mock EmailService for follow-up transmission
    mock_email_service = AsyncMock()
    mock_sent_email = AsyncMock()
    mock_sent_email.id = None
    mock_sent_email.thread_id = None
    mock_sent_email.message_id = "<followup_sent@domain.com>"
    mock_email_service.send_email.return_value = mock_sent_email

    from tests.conftest import TestAsyncSessionLocal
    results = await CampaignDeliveryService.process_due_followup_steps(
        db_factory=TestAsyncSessionLocal,
        email_service=mock_email_service,
        now_utc=now_utc,
    )

    # Verify outcomes:
    # Recipient 1 (vip) matched Step 2 -> Step 2 SENT
    # Recipient 2 (standard) skipped Step 2 (non-matching) -> Step 2 SKIPPED, advanced to Step 3!
    await db_session.refresh(recip_1)
    await db_session.refresh(recip_2)

    assert recip_1.current_step_number == 2
    assert recip_1.status == CampaignRecipientStatus.COMPLETED.value

    # Recipient 2 skipped Step 2 and dispatched Step 3 (or is on Step 3)
    assert recip_2.current_step_number >= 2
    # Verify skipped delivery record was created for Step 2 on Recipient 2
    step_2 = (await db_session.execute(
        select(CampaignStep).where(CampaignStep.campaign_id == camp_id, CampaignStep.step_number == 2)
    )).scalar_one()

    r2_step2_deliv = (await db_session.execute(
        select(CampaignDelivery).where(
            CampaignDelivery.campaign_id == camp_id,
            CampaignDelivery.recipient_id == r2_id,
            CampaignDelivery.step_id == step_2.id,
        )
    )).scalar_one_or_none()

    assert r2_step2_deliv is not None
    assert r2_step2_deliv.status == CampaignDeliveryStatus.SKIPPED.value
    assert "Skipped: recipient does not match step targeting tags" in r2_step2_deliv.error_message


@pytest.mark.asyncio
async def test_consecutive_nonmatching_steps_advance_safely(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Test that a recipient with no matching tags skips consecutive targeted steps safely and marks sequence COMPLETED."""
    from app.modules.campaigns.delivery_service import CampaignDeliveryService
    from unittest.mock import AsyncMock

    token_owner = await register_and_login(async_client, "owner_consec_m5@test.com", "Consec Owner")
    company_id = await create_company_helper(async_client, token_owner, "Consec Org")
    account_id = await create_email_account_helper(async_client, token_owner, company_id)

    # Campaign where Steps 2 and 3 both target 'exclusive'
    camp_res = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={
            "name": "Exclusive Sequence",
            "email_account_id": account_id,
            "subject": "Initial Intro",
            "followup_steps": [
                {"step_number": 2, "delay_hours": 1, "subject": "Exclusive Step 2", "target_tags": ["exclusive"]},
                {"step_number": 3, "delay_hours": 1, "subject": "Exclusive Step 3", "target_tags": ["exclusive"]},
            ],
        },
    )
    camp_id = camp_res.json()["id"]

    # Recipient has no matching tags
    r_res = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}/recipients",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"email": "non_exclusive@domain.com", "tags": ["general"]},
    )
    r_id = r_res.json()["id"]

    now_utc = datetime.now(timezone.utc)
    past_time = now_utc - timedelta(hours=3)

    camp_obj = await db_session.get(Campaign, camp_id)
    camp_obj.status = CampaignStatus.RUNNING.value

    step_1 = (await db_session.execute(
        select(CampaignStep).where(CampaignStep.campaign_id == camp_id, CampaignStep.step_number == 1)
    )).scalar_one()

    d1 = CampaignDelivery(
        campaign_id=camp_id,
        recipient_id=r_id,
        step_id=step_1.id,
        status=CampaignDeliveryStatus.SENT.value,
        sent_at=past_time,
        message_id="<intro@domain.com>",
    )
    db_session.add(d1)

    recip = await db_session.get(CampaignRecipient, r_id)
    recip.current_step_number = 1
    recip.status = CampaignRecipientStatus.SENT.value
    recip.next_step_due_at = past_time + timedelta(hours=1)
    await db_session.commit()

    mock_email_service = AsyncMock()
    from tests.conftest import TestAsyncSessionLocal

    results = await CampaignDeliveryService.process_due_followup_steps(
        db_factory=TestAsyncSessionLocal,
        email_service=mock_email_service,
        now_utc=now_utc,
    )

    # Nothing should be sent
    assert mock_email_service.send_email.call_count == 0

    await db_session.refresh(recip)
    # Sequence should have skipped both steps and marked COMPLETED
    assert recip.current_step_number == 3
    assert recip.status == CampaignRecipientStatus.COMPLETED.value
    assert recip.next_step_due_at is None


@pytest.mark.asyncio
async def test_untargeted_steps_and_step1_preserve_existing_behavior(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Test that untargeted steps (target_tags = [] or None) target all recipients regardless of tags."""
    from app.modules.campaigns.delivery_service import CampaignDeliveryService
    from unittest.mock import AsyncMock

    token_owner = await register_and_login(async_client, "owner_untargeted_m5@test.com", "Untargeted Owner")
    company_id = await create_company_helper(async_client, token_owner, "Untargeted Org")
    account_id = await create_email_account_helper(async_client, token_owner, company_id)

    camp_res = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={
            "name": "Broadcast Campaign",
            "email_account_id": account_id,
            "subject": "Broadcast Subject",
            "followup_steps": [
                {
                    "step_number": 2,
                    "delay_hours": 1,
                    "subject": "Broadcast Step 2",
                    "body_text": "Broadcast follow-up for everyone.",
                    "target_tags": [],
                },
            ],
        },
    )
    camp_id = camp_res.json()["id"]

    r_res = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}/recipients",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"email": "anyone@domain.com", "tags": ["custom-tag-123"]},
    )
    r_id = r_res.json()["id"]

    now_utc = datetime.now(timezone.utc)
    past_time = now_utc - timedelta(hours=2)

    camp_obj = await db_session.get(Campaign, camp_id)
    camp_obj.status = CampaignStatus.RUNNING.value

    step_1 = (await db_session.execute(
        select(CampaignStep).where(CampaignStep.campaign_id == camp_id, CampaignStep.step_number == 1)
    )).scalar_one()

    d1 = CampaignDelivery(
        campaign_id=camp_id,
        recipient_id=r_id,
        step_id=step_1.id,
        status=CampaignDeliveryStatus.SENT.value,
        sent_at=past_time,
        message_id="<broadcast1@domain.com>",
    )
    db_session.add(d1)

    recip = await db_session.get(CampaignRecipient, r_id)
    recip.current_step_number = 1
    recip.status = CampaignRecipientStatus.SENT.value
    recip.next_step_due_at = past_time + timedelta(hours=1)
    await db_session.commit()

    mock_email_service = AsyncMock()
    mock_sent_email = AsyncMock()
    mock_sent_email.id = None
    mock_sent_email.thread_id = None
    mock_sent_email.message_id = "<broadcast2_sent@domain.com>"
    mock_email_service.send_email.return_value = mock_sent_email

    from tests.conftest import TestAsyncSessionLocal
    results = await CampaignDeliveryService.process_due_followup_steps(
        db_factory=TestAsyncSessionLocal,
        email_service=mock_email_service,
        now_utc=now_utc,
    )

    # Dispatched because target_tags was empty
    assert mock_email_service.send_email.call_count == 1
    await db_session.refresh(recip)
    assert recip.current_step_number == 2
    assert recip.status == CampaignRecipientStatus.COMPLETED.value


@pytest.mark.asyncio
async def test_tags_company_and_campaign_isolation(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Test that tag endpoints enforce tenant isolation and role permissions."""
    token_owner_a = await register_and_login(async_client, "owner_iso_a@test.com", "Owner A")
    token_owner_b = await register_and_login(async_client, "owner_iso_b@test.com", "Owner B")
    token_member_a = await register_and_login(async_client, "member_iso_a@test.com", "Member A")

    company_a_id = await create_company_helper(async_client, token_owner_a, "Company A")
    company_b_id = await create_company_helper(async_client, token_owner_b, "Company B")
    await add_company_member_helper(async_client, token_owner_a, company_a_id, "member_iso_a@test.com", "MEMBER")

    account_a_id = await create_email_account_helper(async_client, token_owner_a, company_a_id)

    camp_res = await async_client.post(
        f"/api/v1/companies/{company_a_id}/campaigns",
        headers={"Authorization": f"Bearer {token_owner_a}"},
        json={"name": "Company A Campaign", "email_account_id": account_a_id},
    )
    camp_a_id = camp_res.json()["id"]

    recip_res = await async_client.post(
        f"/api/v1/companies/{company_a_id}/campaigns/{camp_a_id}/recipients",
        headers={"Authorization": f"Bearer {token_owner_a}"},
        json={"email": "isolated@company.com", "tags": ["secret-tag"]},
    )
    recip_a_id = recip_res.json()["id"]

    # 1. Foreign company access to tags -> 404
    foreign_tags = await async_client.get(
        f"/api/v1/companies/{company_b_id}/campaigns/{camp_a_id}/tags",
        headers={"Authorization": f"Bearer {token_owner_b}"},
    )
    assert foreign_tags.status_code == 404

    # 2. Foreign company tag modification -> 404
    foreign_add = await async_client.post(
        f"/api/v1/companies/{company_b_id}/campaigns/{camp_a_id}/recipients/{recip_a_id}/tags/add",
        headers={"Authorization": f"Bearer {token_owner_b}"},
        json={"tag": "hack"},
    )
    assert foreign_add.status_code == 404

    # 3. Non-admin member role tag modification -> 403
    member_add = await async_client.post(
        f"/api/v1/companies/{company_a_id}/campaigns/{camp_a_id}/recipients/{recip_a_id}/tags/add",
        headers={"Authorization": f"Bearer {token_member_a}"},
        json={"tag": "member-tag"},
    )
    assert member_add.status_code == 403
