import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.companies.models import Company, CompanyRole, CompanyUser


async def register_and_login(client: AsyncClient, email: str, name: str = "Test User") -> str:
    """Helper to register and login a user, returning their JWT bearer token."""
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123!", "full_name": name},
    )
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    return login_resp.json()["access_token"]


@pytest.mark.asyncio
async def test_authenticated_user_can_create_company(async_client: AsyncClient, db_session: AsyncSession):
    """Test that an authenticated user can create a company and automatically becomes OWNER."""
    token = await register_and_login(async_client, "owner@company.com", "Company Owner")

    create_resp = await async_client.post(
        "/api/v1/companies/",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "SevenCore Technologies"},
    )
    assert create_resp.status_code == 201
    data = create_resp.json()
    assert data["name"] == "SevenCore Technologies"
    assert data["is_active"] is True
    assert data["role"] == "OWNER"
    assert "id" in data

    # Verify in database
    company_id = data["id"]
    db_company = (await db_session.execute(select(Company).where(Company.id == company_id))).scalars().first()
    assert db_company is not None
    assert db_company.name == "SevenCore Technologies"

    # Verify CompanyUser membership in database
    membership = (
        await db_session.execute(select(CompanyUser).where(CompanyUser.company_id == company_id))
    ).scalars().first()
    assert membership is not None
    assert membership.role == CompanyRole.OWNER.value


@pytest.mark.asyncio
async def test_unauthenticated_user_cannot_create_company(async_client: AsyncClient):
    """Test that unauthenticated requests to create a company are rejected with 401."""
    resp = await async_client.post(
        "/api/v1/companies/",
        json={"name": "Unauthorized Company"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_member_can_retrieve_their_company(async_client: AsyncClient):
    """Test that a member can retrieve company details by ID."""
    token = await register_and_login(async_client, "alice@company.com", "Alice")
    create_resp = await async_client.post(
        "/api/v1/companies/",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Acme Corp"},
    )
    company_id = create_resp.json()["id"]

    get_resp = await async_client.get(
        f"/api/v1/companies/{company_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["id"] == company_id
    assert data["name"] == "Acme Corp"
    assert data["role"] == "OWNER"


@pytest.mark.asyncio
async def test_user_cannot_retrieve_unauthorized_company(async_client: AsyncClient):
    """Test that a user cannot access a company they are not a member of (403 Forbidden)."""
    # User A creates Company 1
    token_a = await register_and_login(async_client, "usera@company.com", "User A")
    resp_a = await async_client.post(
        "/api/v1/companies/",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"name": "Company Alpha"},
    )
    company_1_id = resp_a.json()["id"]

    # User B creates Company 2
    token_b = await register_and_login(async_client, "userb@company.com", "User B")
    await async_client.post(
        "/api/v1/companies/",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"name": "Company Beta"},
    )

    # User B tries to access Company 1
    unauthorized_resp = await async_client.get(
        f"/api/v1/companies/{company_1_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert unauthorized_resp.status_code == 403
    assert unauthorized_resp.json()["detail"] == "You do not have access to this company"


@pytest.mark.asyncio
async def test_company_data_isolation_in_listing(async_client: AsyncClient):
    """Test that listing companies only returns the companies the user belongs to."""
    token_a = await register_and_login(async_client, "user1@company.com", "User 1")
    token_b = await register_and_login(async_client, "user2@company.com", "User 2")

    # User A creates 2 companies
    await async_client.post(
        "/api/v1/companies/",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"name": "Company One"},
    )
    await async_client.post(
        "/api/v1/companies/",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"name": "Company Two"},
    )

    # User B creates 1 company
    await async_client.post(
        "/api/v1/companies/",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"name": "Company Three"},
    )

    # User A lists companies -> should see exactly 2 companies
    list_a = await async_client.get("/api/v1/companies/", headers={"Authorization": f"Bearer {token_a}"})
    assert list_a.status_code == 200
    names_a = [c["name"] for c in list_a.json()]
    assert sorted(names_a) == ["Company One", "Company Two"]

    # User B lists companies -> should see exactly 1 company
    list_b = await async_client.get("/api/v1/companies/", headers={"Authorization": f"Bearer {token_b}"})
    assert list_b.status_code == 200
    names_b = [c["name"] for c in list_b.json()]
    assert names_b == ["Company Three"]


@pytest.mark.asyncio
async def test_add_company_member_and_duplicate_rejection(async_client: AsyncClient):
    """Test adding a member to a company and rejecting duplicate membership."""
    token_owner = await register_and_login(async_client, "boss@company.com", "Boss")
    await register_and_login(async_client, "worker@company.com", "Worker")

    create_resp = await async_client.post(
        "/api/v1/companies/",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"name": "Collaborative Corp"},
    )
    company_id = create_resp.json()["id"]

    # Add worker as MEMBER
    add_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/members",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"email": "worker@company.com", "role": "MEMBER"},
    )
    assert add_resp.status_code == 201
    assert add_resp.json()["email"] == "worker@company.com"
    assert add_resp.json()["role"] == "MEMBER"

    # Attempt to add same worker again -> 409 Conflict
    dup_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/members",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"email": "worker@company.com", "role": "MEMBER"},
    )
    assert dup_resp.status_code == 409
    assert dup_resp.json()["detail"] == "User is already a member of this company"


@pytest.mark.asyncio
async def test_nonexistent_company_returns_404(async_client: AsyncClient):
    """Test that requesting a non-existent company ID returns 404 Not Found."""
    token = await register_and_login(async_client, "user_404@company.com")
    resp = await async_client.get(
        "/api/v1/companies/99999",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Company not found"


@pytest.mark.asyncio
async def test_update_member_role_and_owner_protection(async_client: AsyncClient, db_session: AsyncSession):
    """Test updating member role between ADMIN and MEMBER, and ensuring OWNER is protected."""
    token_owner = await register_and_login(async_client, "owner_role@company.com", "Owner")
    token_member = await register_and_login(async_client, "member_role@company.com", "Member")
    
    # Create company
    c_resp = await async_client.post(
        "/api/v1/companies/",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"name": "Role Test Co"},
    )
    company_id = c_resp.json()["id"]

    # Add member
    add_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/members",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"email": "member_role@company.com", "role": "MEMBER"},
    )
    member_user_id = add_resp.json()["user_id"]

    # 1. Owner promotes Member to ADMIN
    update_resp = await async_client.put(
        f"/api/v1/companies/{company_id}/members/{member_user_id}/role",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"role": "ADMIN"},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["role"] == "ADMIN"

    # 2. Promoted Admin demotes themselves or another back to MEMBER
    demote_resp = await async_client.put(
        f"/api/v1/companies/{company_id}/members/{member_user_id}/role",
        headers={"Authorization": f"Bearer {token_member}"},
        json={"role": "MEMBER"},
    )
    assert demote_resp.status_code == 200
    assert demote_resp.json()["role"] == "MEMBER"

    # 3. Regular MEMBER cannot update roles (403 Forbidden)
    forbidden_resp = await async_client.put(
        f"/api/v1/companies/{company_id}/members/{member_user_id}/role",
        headers={"Authorization": f"Bearer {token_member}"},
        json={"role": "ADMIN"},
    )
    assert forbidden_resp.status_code == 403

    # 4. Attempt to modify OWNER's role -> 403 Forbidden
    # Fetch owner user ID
    members_resp = await async_client.get(
        f"/api/v1/companies/{company_id}/members",
        headers={"Authorization": f"Bearer {token_owner}"},
    )
    owner_member = next(m for m in members_resp.json() if m["role"] == "OWNER")
    owner_user_id = owner_member["user_id"]

    owner_protect_resp = await async_client.put(
        f"/api/v1/companies/{company_id}/members/{owner_user_id}/role",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"role": "ADMIN"},
    )
    assert owner_protect_resp.status_code == 403
    assert "Cannot modify the role of the workspace Owner" in owner_protect_resp.json()["detail"]


@pytest.mark.asyncio
async def test_remove_member_and_cleanup_email_access(async_client: AsyncClient, db_session: AsyncSession):
    """Test removing a member, verifying email-account access cleanup while preserving user."""
    from app.modules.auth.models import User
    from app.modules.email_accounts.models import EmailAccountAccess

    token_owner = await register_and_login(async_client, "owner_rm@company.com", "Owner RM")
    token_target = await register_and_login(async_client, "target_rm@company.com", "Target RM")

    # Create company
    c_resp = await async_client.post(
        "/api/v1/companies/",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"name": "Removal Corp"},
    )
    company_id = c_resp.json()["id"]

    # Add target member
    add_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/members",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"email": "target_rm@company.com", "role": "MEMBER"},
    )
    target_user_id = add_resp.json()["user_id"]

    # Create email account for company
    acc_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/email-accounts",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={
            "name": "Support Inbox",
            "email_address": "support@removalcorp.com",
            "provider": "CUSTOM",
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "imap_host": "imap.example.com",
            "imap_port": 993,
        },
    )
    assert acc_resp.status_code == 201
    account_id = acc_resp.json()["id"]

    # Grant target user access to this email account
    grant_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/email-accounts/{account_id}/access",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"user_id": target_user_id},
    )
    assert grant_resp.status_code == 201

    # Verify company-wide email accounts access endpoint
    access_list_resp = await async_client.get(
        f"/api/v1/companies/{company_id}/email-accounts-access",
        headers={"Authorization": f"Bearer {token_owner}"},
    )
    assert access_list_resp.status_code == 200
    accesses = access_list_resp.json()
    assert len(accesses) == 1
    assert accesses[0]["user_id"] == target_user_id
    assert accesses[0]["email_account_id"] == account_id

    # 1. Target member cannot remove other members (403)
    unauth_rm = await async_client.delete(
        f"/api/v1/companies/{company_id}/members/{target_user_id}",
        headers={"Authorization": f"Bearer {token_target}"},
    )
    assert unauth_rm.status_code == 403

    # 2. Owner removes target member
    rm_resp = await async_client.delete(
        f"/api/v1/companies/{company_id}/members/{target_user_id}",
        headers={"Authorization": f"Bearer {token_owner}"},
    )
    assert rm_resp.status_code == 204

    # 3. Verify member is no longer in company members list
    members_after = await async_client.get(
        f"/api/v1/companies/{company_id}/members",
        headers={"Authorization": f"Bearer {token_owner}"},
    )
    assert all(m["user_id"] != target_user_id for m in members_after.json())

    # 4. Verify explicit EmailAccountAccess was deleted
    access_after = await async_client.get(
        f"/api/v1/companies/{company_id}/email-accounts-access",
        headers={"Authorization": f"Bearer {token_owner}"},
    )
    assert len(access_after.json()) == 0

    # 5. Verify target User record still exists in users table (not deleted)
    user_record = (
        await db_session.execute(select(User).where(User.id == target_user_id))
    ).scalars().first()
    assert user_record is not None
    assert user_record.email == "target_rm@company.com"

    # 6. Verify Owner cannot be removed
    members_resp = await async_client.get(
        f"/api/v1/companies/{company_id}/members",
        headers={"Authorization": f"Bearer {token_owner}"},
    )
    owner_user_id = next(m["user_id"] for m in members_resp.json() if m["role"] == "OWNER")
    rm_owner_resp = await async_client.delete(
        f"/api/v1/companies/{company_id}/members/{owner_user_id}",
        headers={"Authorization": f"Bearer {token_owner}"},
    )
    assert rm_owner_resp.status_code in [400, 403]

