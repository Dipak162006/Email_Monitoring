from datetime import timedelta
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.security import create_access_token
from app.modules.auth.models import User


@pytest.mark.asyncio
async def test_successful_registration(async_client: AsyncClient, db_session: AsyncSession):
    """Test registering a new user with valid email and password."""
    payload = {
        "email": "alice@company.com",
        "password": "SecurePassword123!",
        "full_name": "Alice Smith",
    }
    response = await async_client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "alice@company.com"
    assert data["full_name"] == "Alice Smith"
    assert data["is_active"] is True
    assert "id" in data
    assert "password" not in data
    assert "hashed_password" not in data

    # Verify user was saved to database
    result = await db_session.execute(select(User).where(User.email == "alice@company.com"))
    user = result.scalars().first()
    assert user is not None
    assert user.full_name == "Alice Smith"


@pytest.mark.asyncio
async def test_duplicate_registration(async_client: AsyncClient):
    """Test that registering an already-registered email returns 409 Conflict."""
    payload = {
        "email": "duplicate@company.com",
        "password": "Password123!",
        "full_name": "Duplicate User",
    }
    first_resp = await async_client.post("/api/v1/auth/register", json=payload)
    assert first_resp.status_code == 201

    second_resp = await async_client.post("/api/v1/auth/register", json=payload)
    assert second_resp.status_code == 409
    assert second_resp.json()["detail"] == "A user with this email already exists"


@pytest.mark.asyncio
async def test_password_is_not_stored_as_plaintext(async_client: AsyncClient, db_session: AsyncSession):
    """Test that the plaintext password is never stored directly in the database."""
    plain_password = "MySuperSecretPlainPassword!"
    payload = {
        "email": "security_test@company.com",
        "password": plain_password,
    }
    response = await async_client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201

    result = await db_session.execute(select(User).where(User.email == "security_test@company.com"))
    user = result.scalars().first()
    assert user is not None
    assert user.hashed_password != plain_password
    assert user.hashed_password.startswith("$2b$") or user.hashed_password.startswith("$2a$")


@pytest.mark.asyncio
async def test_successful_login(async_client: AsyncClient):
    """Test logging in with correct credentials returns a valid JWT token."""
    register_payload = {
        "email": "bob@company.com",
        "password": "BobsPassword123!",
        "full_name": "Bob Jones",
    }
    await async_client.post("/api/v1/auth/register", json=register_payload)

    login_payload = {
        "email": "bob@company.com",
        "password": "BobsPassword123!",
    }
    login_resp = await async_client.post("/api/v1/auth/login", json=login_payload)
    assert login_resp.status_code == 200
    data = login_resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] > 0


@pytest.mark.asyncio
async def test_invalid_credentials(async_client: AsyncClient):
    """Test login failure with incorrect password and non-existent email."""
    # Register user first
    await async_client.post(
        "/api/v1/auth/register",
        json={"email": "charlie@company.com", "password": "CorrectPassword123!"},
    )

    # Wrong password
    wrong_pw_resp = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "charlie@company.com", "password": "WrongPassword!"},
    )
    assert wrong_pw_resp.status_code == 401
    assert wrong_pw_resp.json()["detail"] == "Incorrect email or password"

    # Nonexistent user
    nonexistent_resp = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@company.com", "password": "AnyPassword123!"},
    )
    assert nonexistent_resp.status_code == 401
    assert nonexistent_resp.json()["detail"] == "Incorrect email or password"


@pytest.mark.asyncio
async def test_valid_authenticated_me_request(async_client: AsyncClient):
    """Test accessing /api/v1/auth/me with a valid Bearer token."""
    await async_client.post(
        "/api/v1/auth/register",
        json={"email": "david@company.com", "password": "DavidsPassword123!", "full_name": "David Miller"},
    )

    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "david@company.com", "password": "DavidsPassword123!"},
    )
    token = login_resp.json()["access_token"]

    me_resp = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data["email"] == "david@company.com"
    assert me_data["full_name"] == "David Miller"


@pytest.mark.asyncio
async def test_missing_authentication_rejected(async_client: AsyncClient):
    """Test that requests to protected endpoints without Authorization header are rejected."""
    response = await async_client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert "detail" in response.json()


@pytest.mark.asyncio
async def test_invalid_token_rejected(async_client: AsyncClient):
    """Test that requests with an invalid/malformed token are rejected."""
    response = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer invalid.malformed.token"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid authentication token"


@pytest.mark.asyncio
async def test_expired_token_rejected(async_client: AsyncClient):
    """Test that requests with an expired JWT token are rejected."""
    # Register user
    await async_client.post(
        "/api/v1/auth/register",
        json={"email": "expired_test@company.com", "password": "Password123!"},
    )

    # Generate an expired token (expired 10 minutes ago)
    expired_token = create_access_token(
        subject="expired_test@company.com",
        expires_delta=timedelta(minutes=-10),
    )

    response = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Token has expired"
