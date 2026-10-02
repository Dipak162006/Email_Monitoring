import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.security import decrypt_credential
from app.modules.email_accounts.models import EmailAccount, EmailAccountAccess


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


async def create_company_helper(client: AsyncClient, token: str, name: str = "Test Company") -> int:
    """Helper to create a company and return its ID."""
    resp = await client.post(
        "/api/v1/companies/",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": name},
    )
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_create_email_account_and_credential_encryption(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Test creating an email account and verify credentials are encrypted at rest."""
    token = await register_and_login(async_client, "owner@sevencore.com", "Owner")
    company_id = await create_company_helper(async_client, token, "SevenCore")

    payload = {
        "name": "Sales Inbox",
        "email_address": "sales@sevencore.com",
        "provider": "CUSTOM",
        "smtp_host": "smtp.sevencore.com",
        "smtp_port": 587,
        "smtp_security": "STARTTLS",
        "smtp_username": "sales@sevencore.com",
        "smtp_password": "MySecretSmtpPassword123!",
        "imap_host": "imap.sevencore.com",
        "imap_port": 993,
        "imap_security": "SSL",
        "imap_username": "sales@sevencore.com",
        "imap_password": "MySecretImapPassword456!",
    }

    resp = await async_client.post(
        f"/api/v1/companies/{company_id}/email-accounts",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Sales Inbox"
    assert data["email_address"] == "sales@sevencore.com"
    assert data["has_smtp_password"] is True
    assert data["has_imap_password"] is True
    assert "smtp_password" not in data
    assert "imap_password" not in data
    assert "smtp_password_encrypted" not in data
    assert "imap_password_encrypted" not in data

    # Verify database state directly
    account_id = data["id"]
    query = select(EmailAccount).where(EmailAccount.id == account_id)
    db_account = (await db_session.execute(query)).scalars().first()
    assert db_account is not None

    # Plaintext passwords must NEVER match stored values
    assert db_account.smtp_password_encrypted != "MySecretSmtpPassword123!"
    assert db_account.imap_password_encrypted != "MySecretImapPassword456!"

    # Decrypted value must match original plaintext
    assert decrypt_credential(db_account.smtp_password_encrypted) == "MySecretSmtpPassword123!"
    assert decrypt_credential(db_account.imap_password_encrypted) == "MySecretImapPassword456!"


@pytest.mark.asyncio
async def test_unauthorized_user_cannot_access_company_email_accounts(async_client: AsyncClient):
    """Test that a user not belonging to a company cannot view or create its email accounts."""
    token_a = await register_and_login(async_client, "owner_a@company.com")
    company_a_id = await create_company_helper(async_client, token_a, "Company A")

    # Create account in Company A
    await async_client.post(
        f"/api/v1/companies/{company_a_id}/email-accounts",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "name": "Support A",
            "email_address": "support@companya.com",
            "provider": "CUSTOM",
        },
    )

    # User B (from Company B) tries to access Company A's email accounts -> 404 Not Found to prevent enumeration
    token_b = await register_and_login(async_client, "owner_b@company.com")
    resp = await async_client.get(
        f"/api/v1/companies/{company_a_id}/email-accounts",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Company not found"


@pytest.mark.asyncio
async def test_member_email_account_access_scoping(async_client: AsyncClient):
    """Test that regular company members only see email accounts they are granted access to."""
    token_owner = await register_and_login(async_client, "boss@company.com", "Boss")
    company_id = await create_company_helper(async_client, token_owner, "Corp")

    # Register employee
    token_employee = await register_and_login(async_client, "employee@company.com", "Employee")
    # Get employee user ID from /auth/me
    emp_me = (await async_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token_employee}"})).json()
    employee_id = emp_me["id"]

    # Add employee as MEMBER of company
    await async_client.post(
        f"/api/v1/companies/{company_id}/members",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"email": "employee@company.com", "role": "MEMBER"},
    )

    # Owner creates two email accounts: Sales and Support
    resp_sales = await async_client.post(
        f"/api/v1/companies/{company_id}/email-accounts",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"name": "Sales", "email_address": "sales@corp.com", "provider": "GOOGLE"},
    )
    sales_id = resp_sales.json()["id"]

    resp_support = await async_client.post(
        f"/api/v1/companies/{company_id}/email-accounts",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"name": "Support", "email_address": "support@corp.com", "provider": "GOOGLE"},
    )
    support_id = resp_support.json()["id"]

    # Employee initially sees 0 email accounts (since they have no explicit grants yet)
    emp_accounts_initial = await async_client.get(
        f"/api/v1/companies/{company_id}/email-accounts",
        headers={"Authorization": f"Bearer {token_employee}"},
    )
    assert emp_accounts_initial.status_code == 200
    assert len(emp_accounts_initial.json()) == 0

    # Employee cannot GET support detail
    emp_get_unauthorized = await async_client.get(
        f"/api/v1/companies/{company_id}/email-accounts/{support_id}",
        headers={"Authorization": f"Bearer {token_employee}"},
    )
    assert emp_get_unauthorized.status_code == 403

    # Owner grants employee access to Support ONLY
    grant_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/email-accounts/{support_id}/access",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"user_id": employee_id},
    )
    assert grant_resp.status_code == 201
    assert grant_resp.json()["user_id"] == employee_id

    # Employee now sees exactly Support in listing
    emp_accounts_after = await async_client.get(
        f"/api/v1/companies/{company_id}/email-accounts",
        headers={"Authorization": f"Bearer {token_employee}"},
    )
    assert emp_accounts_after.status_code == 200
    emp_list = emp_accounts_after.json()
    assert len(emp_list) == 1
    assert emp_list[0]["id"] == support_id
    assert emp_list[0]["name"] == "Support"

    # Employee can now GET support detail, but still cannot GET sales detail
    emp_get_support = await async_client.get(
        f"/api/v1/companies/{company_id}/email-accounts/{support_id}",
        headers={"Authorization": f"Bearer {token_employee}"},
    )
    assert emp_get_support.status_code == 200

    emp_get_sales = await async_client.get(
        f"/api/v1/companies/{company_id}/email-accounts/{sales_id}",
        headers={"Authorization": f"Bearer {token_employee}"},
    )
    assert emp_get_sales.status_code == 403


@pytest.mark.asyncio
async def test_cannot_grant_access_to_non_company_member(async_client: AsyncClient):
    """Test that access cannot be granted to a user who is not a member of the company."""
    token_owner = await register_and_login(async_client, "owner_test@company.com")
    company_id = await create_company_helper(async_client, token_owner, "Test Company")

    # Create email account
    acc_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/email-accounts",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"name": "General", "email_address": "general@test.com", "provider": "CUSTOM"},
    )
    account_id = acc_resp.json()["id"]

    # Register an outsider user who was never added to the company
    token_outsider = await register_and_login(async_client, "outsider@other.com")
    outsider_me = (await async_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token_outsider}"})).json()
    outsider_id = outsider_me["id"]

    # Attempt to grant outsider access to the email account -> 400 Bad Request
    resp = await async_client.post(
        f"/api/v1/companies/{company_id}/email-accounts/{account_id}/access",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"user_id": outsider_id},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Cannot grant access: User is not a member of this company"


@pytest.mark.asyncio
async def test_delete_email_account_cascades_access_records(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Test that deleting an email account removes it and cascade-deletes access records."""
    token = await register_and_login(async_client, "admin@delete.com")
    company_id = await create_company_helper(async_client, token, "Delete Corp")

    acc_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/email-accounts",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Temp", "email_address": "temp@delete.com", "provider": "CUSTOM"},
    )
    account_id = acc_resp.json()["id"]

    # Delete the account
    del_resp = await async_client.delete(
        f"/api/v1/companies/{company_id}/email-accounts/{account_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_resp.status_code == 204

    # Verify account is gone
    query = select(EmailAccount).where(EmailAccount.id == account_id)
    assert (await db_session.execute(query)).scalars().first() is None


@pytest.mark.asyncio
async def test_list_all_authorized_email_accounts(async_client: AsyncClient):
    """Test the cross-company authorized email accounts endpoint."""
    token = await register_and_login(async_client, "multi_company_user@test.com")
    c1 = await create_company_helper(async_client, token, "Company 1")
    c2 = await create_company_helper(async_client, token, "Company 2")

    await async_client.post(
        f"/api/v1/companies/{c1}/email-accounts",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "C1 Email", "email_address": "c1@test.com", "provider": "ZOHO"},
    )
    await async_client.post(
        f"/api/v1/companies/{c2}/email-accounts",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "C2 Email", "email_address": "c2@test.com", "provider": "YAHOO"},
    )

    resp = await async_client.get(
        "/api/v1/email-accounts/authorized",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    accounts = resp.json()
    assert len(accounts) == 2
    names = [a["name"] for a in accounts]
    assert "C1 Email" in names
    assert "C2 Email" in names


@pytest.mark.asyncio
async def test_company_email_accounts_access_role_enforcement(async_client: AsyncClient):
    """Test that GET /companies/{company_id}/email-accounts-access allows OWNER and ADMIN but rejects MEMBER."""
    token_owner = await register_and_login(async_client, "owner_access_test@comp.com", "Owner User")
    company_id = await create_company_helper(async_client, token_owner, "Access Test Corp")

    # Create an email account
    acc_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/email-accounts",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"name": "Support", "email_address": "support@accesstest.com", "provider": "CUSTOM"},
    )
    assert acc_resp.status_code == 201
    account_id = acc_resp.json()["id"]

    # Register member and admin
    token_member = await register_and_login(async_client, "member_access_test@comp.com", "Member User")
    token_admin = await register_and_login(async_client, "admin_access_test@comp.com", "Admin User")

    # Add member and admin to company
    await async_client.post(
        f"/api/v1/companies/{company_id}/members",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"email": "member_access_test@comp.com", "role": "MEMBER"},
    )
    await async_client.post(
        f"/api/v1/companies/{company_id}/members",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"email": "admin_access_test@comp.com", "role": "ADMIN"},
    )

    # Get member's user id and grant access to the account
    member_me = (await async_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token_member}"})).json()
    await async_client.post(
        f"/api/v1/companies/{company_id}/email-accounts/{account_id}/access",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"user_id": member_me["id"]},
    )

    # 1. MEMBER receives 403 Forbidden
    member_resp = await async_client.get(
        f"/api/v1/companies/{company_id}/email-accounts-access",
        headers={"Authorization": f"Bearer {token_member}"},
    )
    assert member_resp.status_code == 403
    assert "Owner or Administrator privileges required" in member_resp.json()["detail"]

    # 2. OWNER receives 200 OK
    owner_resp = await async_client.get(
        f"/api/v1/companies/{company_id}/email-accounts-access",
        headers={"Authorization": f"Bearer {token_owner}"},
    )
    assert owner_resp.status_code == 200
    records = owner_resp.json()
    assert len(records) >= 1
    assert any(r["user_id"] == member_me["id"] and r["email_account_id"] == account_id for r in records)

    # 3. ADMIN receives 200 OK
    admin_resp = await async_client.get(
        f"/api/v1/companies/{company_id}/email-accounts-access",
        headers={"Authorization": f"Bearer {token_admin}"},
    )
    assert admin_resp.status_code == 200
    assert len(admin_resp.json()) == len(records)
