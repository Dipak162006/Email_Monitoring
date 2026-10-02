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


# =============================================================================
# M15: User Profile & Password Change Tests
# =============================================================================

@pytest.mark.asyncio
async def test_update_profile_success(async_client: AsyncClient, db_session: AsyncSession):
    """Test that an authenticated user can update their display name."""
    await async_client.post(
        "/api/v1/auth/register",
        json={"email": "profile_user@company.com", "password": "Password123!", "full_name": "Original Name"},
    )
    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "profile_user@company.com", "password": "Password123!"},
    )
    token = login_resp.json()["access_token"]

    # Update profile
    patch_resp = await async_client.patch(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"full_name": "Updated Display Name"},
    )
    assert patch_resp.status_code == 200
    data = patch_resp.json()
    assert data["full_name"] == "Updated Display Name"
    assert data["email"] == "profile_user@company.com"

    # Verify persistence via GET /me
    me_resp = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["full_name"] == "Updated Display Name"


@pytest.mark.asyncio
async def test_update_profile_trimming_and_validation(async_client: AsyncClient):
    """Test name trimming and validation rules (non-empty, max 255 chars)."""
    await async_client.post(
        "/api/v1/auth/register",
        json={"email": "val_user@company.com", "password": "Password123!", "full_name": "Val User"},
    )
    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "val_user@company.com", "password": "Password123!"},
    )
    token = login_resp.json()["access_token"]

    # Trimming check
    trim_resp = await async_client.patch(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"full_name": "   Padded Name   "},
    )
    assert trim_resp.status_code == 200
    assert trim_resp.json()["full_name"] == "Padded Name"

    # Empty string check
    empty_resp = await async_client.patch(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"full_name": ""},
    )
    assert empty_resp.status_code == 422

    # Whitespace only check
    ws_resp = await async_client.patch(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"full_name": "     "},
    )
    assert ws_resp.status_code == 422

    # Oversized name check (>255 chars)
    over_resp = await async_client.patch(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"full_name": "A" * 256},
    )
    assert over_resp.status_code == 422


@pytest.mark.asyncio
async def test_update_profile_rejects_extra_fields(async_client: AsyncClient):
    """Test that extra or immutable fields (email, id, is_superuser) are strictly forbidden."""
    await async_client.post(
        "/api/v1/auth/register",
        json={"email": "extra_fields@company.com", "password": "Password123!", "full_name": "Extra User"},
    )
    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "extra_fields@company.com", "password": "Password123!"},
    )
    token = login_resp.json()["access_token"]

    extra_resp = await async_client.patch(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"full_name": "Valid Name", "email": "hacked@company.com", "is_superuser": True},
    )
    assert extra_resp.status_code == 422


@pytest.mark.asyncio
async def test_update_profile_unauthenticated(async_client: AsyncClient):
    """Test that unauthenticated requests to PATCH /api/v1/auth/me are rejected with 401."""
    response = await async_client.patch("/api/v1/auth/me", json={"full_name": "New Name"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_change_password_success(async_client: AsyncClient):
    """Test successful password change and verification that new password works while old fails."""
    await async_client.post(
        "/api/v1/auth/register",
        json={"email": "pwd_user@company.com", "password": "OldPassword123!", "full_name": "Pwd User"},
    )
    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "pwd_user@company.com", "password": "OldPassword123!"},
    )
    token = login_resp.json()["access_token"]

    # Change password
    change_resp = await async_client.post(
        "/api/v1/auth/me/password",
        headers={"Authorization": f"Bearer {token}"},
        json={"current_password": "OldPassword123!", "new_password": "NewSecretPassword123!"},
    )
    assert change_resp.status_code == 200
    assert change_resp.json() == {"message": "Password changed successfully"}

    # Old password fails login
    old_login = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "pwd_user@company.com", "password": "OldPassword123!"},
    )
    assert old_login.status_code == 401

    # New password succeeds login
    new_login = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "pwd_user@company.com", "password": "NewSecretPassword123!"},
    )
    assert new_login.status_code == 200
    assert "access_token" in new_login.json()


@pytest.mark.asyncio
async def test_change_password_incorrect_current_password(async_client: AsyncClient):
    """Test that incorrect current password returns 400 Bad Request."""
    await async_client.post(
        "/api/v1/auth/register",
        json={"email": "wrong_pwd@company.com", "password": "CorrectPassword123!"},
    )
    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "wrong_pwd@company.com", "password": "CorrectPassword123!"},
    )
    token = login_resp.json()["access_token"]

    change_resp = await async_client.post(
        "/api/v1/auth/me/password",
        headers={"Authorization": f"Bearer {token}"},
        json={"current_password": "IncorrectPassword123!", "new_password": "NewSecretPassword123!"},
    )
    assert change_resp.status_code == 400
    assert change_resp.json()["detail"] == "Incorrect current password"


@pytest.mark.asyncio
async def test_change_password_length_validation(async_client: AsyncClient):
    """Test that new password must be between 8 and 128 characters."""
    await async_client.post(
        "/api/v1/auth/register",
        json={"email": "len_pwd@company.com", "password": "InitialPassword123!"},
    )
    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "len_pwd@company.com", "password": "InitialPassword123!"},
    )
    token = login_resp.json()["access_token"]

    # Too short (< 8 chars)
    short_resp = await async_client.post(
        "/api/v1/auth/me/password",
        headers={"Authorization": f"Bearer {token}"},
        json={"current_password": "InitialPassword123!", "new_password": "short"},
    )
    assert short_resp.status_code == 422

    # Too long (> 128 chars)
    long_resp = await async_client.post(
        "/api/v1/auth/me/password",
        headers={"Authorization": f"Bearer {token}"},
        json={"current_password": "InitialPassword123!", "new_password": "A" * 129},
    )
    assert long_resp.status_code == 422


@pytest.mark.asyncio
async def test_change_password_rejects_extra_fields_and_unauthenticated(async_client: AsyncClient):
    """Test that password change requires auth and forbids extra fields like user_id."""
    # Unauthenticated
    unauth_resp = await async_client.post(
        "/api/v1/auth/me/password",
        json={"current_password": "SomePassword123!", "new_password": "NewPassword123!"},
    )
    assert unauth_resp.status_code == 401

    # Extra fields forbidden (e.g. attempting to supply a target user ID)
    await async_client.post(
        "/api/v1/auth/register",
        json={"email": "extra_pwd@company.com", "password": "InitialPassword123!"},
    )
    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "extra_pwd@company.com", "password": "InitialPassword123!"},
    )
    token = login_resp.json()["access_token"]

    extra_resp = await async_client.post(
        "/api/v1/auth/me/password",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "current_password": "InitialPassword123!",
            "new_password": "NewPassword123!",
            "target_user_id": 1,
            "user_id": 1,
        },
    )
    assert extra_resp.status_code == 422


@pytest.mark.asyncio
async def test_user_cannot_modify_another_user_account(async_client: AsyncClient):
    """Test that modifying a profile or changing a password only affects the authenticated user."""
    # Register User A
    await async_client.post(
        "/api/v1/auth/register",
        json={"email": "usera@company.com", "password": "PasswordUserA123!", "full_name": "User Alpha"},
    )
    login_a = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "usera@company.com", "password": "PasswordUserA123!"},
    )
    token_a = login_a.json()["access_token"]

    # Register User B
    await async_client.post(
        "/api/v1/auth/register",
        json={"email": "userb@company.com", "password": "PasswordUserB123!", "full_name": "User Beta"},
    )
    login_b = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "userb@company.com", "password": "PasswordUserB123!"},
    )
    token_b = login_b.json()["access_token"]

    # User A updates profile
    patch_a = await async_client.patch(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"full_name": "User Alpha Modified"},
    )
    assert patch_a.status_code == 200

    # User B profile must remain unchanged
    me_b = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert me_b.status_code == 200
    assert me_b.json()["full_name"] == "User Beta"
    assert me_b.json()["email"] == "userb@company.com"

    # User A changes password
    pwd_a = await async_client.post(
        "/api/v1/auth/me/password",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"current_password": "PasswordUserA123!", "new_password": "NewPasswordUserA123!"},
    )
    assert pwd_a.status_code == 200

    # User B can still log in with their original password
    login_b_check = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "userb@company.com", "password": "PasswordUserB123!"},
    )
    assert login_b_check.status_code == 200
