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
