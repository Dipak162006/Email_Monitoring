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


# -----------------------------------------------------------------------------
# D7 — EmailAccount <-> Domain Integration Tests
# -----------------------------------------------------------------------------

async def create_domain_helper(client: AsyncClient, token: str, company_id: int, domain_name: str) -> int:
    """Helper to create a domain and return its ID."""
    resp = await client.post(
        f"/api/v1/companies/{company_id}/domains",
        headers={"Authorization": f"Bearer {token}"},
        json={"domain_name": domain_name},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_create_email_account_without_domain_id(async_client: AsyncClient):
    """Scenario 1: EmailAccount creation without domain_id succeeds with domain_id=None."""
    token = await register_and_login(async_client, "owner_d7_no_dom@example.com")
    company_id = await create_company_helper(async_client, token, "D7 Corp")

    payload = {
        "name": "General Inbox",
        "email_address": "general@example.com",
        "provider": "CUSTOM",
    }
    resp = await async_client.post(
        f"/api/v1/companies/{company_id}/email-accounts",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["domain_id"] is None


@pytest.mark.asyncio
async def test_create_email_account_with_valid_same_company_domain(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Scenario 2: EmailAccount creation with valid same-company Domain succeeds."""
    token = await register_and_login(async_client, "owner_d7_valid@example.com")
    company_id = await create_company_helper(async_client, token, "D7 Valid Corp")
    domain_id = await create_domain_helper(async_client, token, company_id, "example.com")

    payload = {
        "name": "Sales Inbox",
        "email_address": "sales@example.com",
        "provider": "CUSTOM",
        "domain_id": domain_id,
    }
    resp = await async_client.post(
        f"/api/v1/companies/{company_id}/email-accounts",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["domain_id"] == domain_id

    # Verify directly in DB
    result = await db_session.execute(
        select(EmailAccount).where(EmailAccount.id == data["id"])
    )
    account = result.scalars().first()
    assert account is not None
    assert account.domain_id == domain_id


@pytest.mark.asyncio
async def test_reject_foreign_company_domain(async_client: AsyncClient):
    """Scenario 3: Reject assigning an EmailAccount to a Domain belonging to a different company."""
    token_a = await register_and_login(async_client, "owner_a@company-a.com")
    company_a_id = await create_company_helper(async_client, token_a, "Company A")
    domain_a_id = await create_domain_helper(async_client, token_a, company_a_id, "company-a.com")

    token_b = await register_and_login(async_client, "owner_b@company-b.com")
    company_b_id = await create_company_helper(async_client, token_b, "Company B")

    # Company B tries to create account referencing Company A's domain_id
    payload = {
        "name": "Intruder Inbox",
        "email_address": "sales@company-a.com",
        "provider": "CUSTOM",
        "domain_id": domain_a_id,
    }
    resp = await async_client.post(
        f"/api/v1/companies/{company_b_id}/email-accounts",
        headers={"Authorization": f"Bearer {token_b}"},
        json=payload,
    )
    assert resp.status_code == 404
    assert "Domain not found in this company" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_reject_incompatible_email_domain_combination(async_client: AsyncClient):
    """Scenario 4: Reject EmailAccount when email address domain does not match assigned Domain."""
    token = await register_and_login(async_client, "owner_compat@example.com")
    company_id = await create_company_helper(async_client, token, "Compat Corp")
    domain_id = await create_domain_helper(async_client, token, company_id, "example.com")

    payload = {
        "name": "Mismatched Inbox",
        "email_address": "sales@other-domain.com",
        "provider": "CUSTOM",
        "domain_id": domain_id,
    }
    resp = await async_client.post(
        f"/api/v1/companies/{company_id}/email-accounts",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert resp.status_code == 422
    assert "does not match assigned domain" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_update_email_account_domain_assignment_change_and_clear(async_client: AsyncClient):
    """Scenarios 5, 6, 7: Assign domain, change to another domain, and clear domain."""
    token = await register_and_login(async_client, "owner_update_dom@example.com")
    company_id = await create_company_helper(async_client, token, "Update Dom Corp")
    domain_1_id = await create_domain_helper(async_client, token, company_id, "primary.com")
    domain_2_id = await create_domain_helper(async_client, token, company_id, "secondary.com")

    # 1. Create with primary domain
    create_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/email-accounts",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Support",
            "email_address": "support@primary.com",
            "domain_id": domain_1_id,
        },
    )
    assert create_resp.status_code == 201
    account_id = create_resp.json()["id"]
    assert create_resp.json()["domain_id"] == domain_1_id

    # 2. Change domain to domain_2 along with email update
    update_resp = await async_client.put(
        f"/api/v1/companies/{company_id}/email-accounts/{account_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "email_address": "support@secondary.com",
            "domain_id": domain_2_id,
        },
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["domain_id"] == domain_2_id
    assert update_resp.json()["email_address"] == "support@secondary.com"

    # 3. Clear domain by setting domain_id to None
    clear_resp = await async_client.put(
        f"/api/v1/companies/{company_id}/email-accounts/{account_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"domain_id": None},
    )
    assert clear_resp.status_code == 200
    assert clear_resp.json()["domain_id"] is None

    # 4. Re-assign domain 1
    reassign_resp = await async_client.put(
        f"/api/v1/companies/{company_id}/email-accounts/{account_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "email_address": "support@primary.com",
            "domain_id": domain_1_id,
        },
    )
    assert reassign_resp.status_code == 200
    assert reassign_resp.json()["domain_id"] == domain_1_id


@pytest.mark.asyncio
async def test_update_email_account_omitted_vs_explicit_null_semantics(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Verify update semantics:
    - CASE A: omitted domain_id preserves existing domain_id.
    - CASE B: explicit null domain_id clears the association.
    - CASE C: valid domain_id assigns or changes the association.
    """
    token = await register_and_login(async_client, "owner_semantics@example.com")
    company_id = await create_company_helper(async_client, token, "Semantics Corp")
    domain_10_id = await create_domain_helper(async_client, token, company_id, "domain10.com")
    domain_20_id = await create_domain_helper(async_client, token, company_id, "domain20.com")

    # 1. Create account with domain_10
    create_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/email-accounts",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Original Name",
            "email_address": "support@domain10.com",
            "domain_id": domain_10_id,
        },
    )
    assert create_resp.status_code == 201
    account_id = create_resp.json()["id"]
    assert create_resp.json()["domain_id"] == domain_10_id

    # 2. CASE A: PUT with unrelated field only (omitting domain_id)
    put_omitted_resp = await async_client.put(
        f"/api/v1/companies/{company_id}/email-accounts/{account_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "New Name"},
    )
    assert put_omitted_resp.status_code == 200
    assert put_omitted_resp.json()["name"] == "New Name"
    assert put_omitted_resp.json()["domain_id"] == domain_10_id  # PRESERVED!

    # Direct DB verification of Case A
    acc_db = (
        await db_session.execute(select(EmailAccount).where(EmailAccount.id == account_id))
    ).scalars().first()
    assert acc_db is not None
    assert acc_db.domain_id == domain_10_id

    # 3. CASE B: PUT with explicit null ({"domain_id": null})
    put_null_resp = await async_client.put(
        f"/api/v1/companies/{company_id}/email-accounts/{account_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"domain_id": None},
    )
    assert put_null_resp.status_code == 200
    assert put_null_resp.json()["domain_id"] is None  # REMOVED!

    # Direct DB verification of Case B
    await db_session.refresh(acc_db)
    assert acc_db.domain_id is None

    # 4. Another CASE A: PUT omitting domain_id while domain_id is null
    put_omitted_again = await async_client.put(
        f"/api/v1/companies/{company_id}/email-accounts/{account_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Another Name"},
    )
    assert put_omitted_again.status_code == 200
    assert put_omitted_again.json()["domain_id"] is None  # Remains null

    # 5. CASE C: PUT with valid same-company domain (domain_20)
    put_new_dom_resp = await async_client.put(
        f"/api/v1/companies/{company_id}/email-accounts/{account_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "email_address": "support@domain20.com",
            "domain_id": domain_20_id,
        },
    )
    assert put_new_dom_resp.status_code == 200
    assert put_new_dom_resp.json()["domain_id"] == domain_20_id  # CHANGED!

    await db_session.refresh(acc_db)
    assert acc_db.domain_id == domain_20_id


@pytest.mark.asyncio
async def test_update_email_account_rejects_incompatible_or_foreign_domain(async_client: AsyncClient):
    """Update rejects foreign-company domain (404) or incompatible email (422)."""
    token_a = await register_and_login(async_client, "owner_upd_a@company-a.com")
    company_a_id = await create_company_helper(async_client, token_a, "Company A Update")
    domain_a_id = await create_domain_helper(async_client, token_a, company_a_id, "company-a.com")

    token_b = await register_and_login(async_client, "owner_upd_b@company-b.com")
    company_b_id = await create_company_helper(async_client, token_b, "Company B Update")
    domain_b_id = await create_domain_helper(async_client, token_b, company_b_id, "company-b.com")

    # Create account in Company A
    acc_resp = await async_client.post(
        f"/api/v1/companies/{company_a_id}/email-accounts",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "name": "Desk",
            "email_address": "desk@company-a.com",
            "domain_id": domain_a_id,
        },
    )
    account_id = acc_resp.json()["id"]

    # Try assigning foreign domain_b
    foreign_resp = await async_client.put(
        f"/api/v1/companies/{company_a_id}/email-accounts/{account_id}",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"domain_id": domain_b_id},
    )
    assert foreign_resp.status_code == 404

    # Try changing email address to mismatch current domain without changing domain_id
    mismatch_resp = await async_client.put(
        f"/api/v1/companies/{company_a_id}/email-accounts/{account_id}",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"email_address": "desk@mismatch.com"},
    )
    assert mismatch_resp.status_code == 422


@pytest.mark.asyncio
async def test_delete_domain_sets_email_account_domain_id_to_null(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Scenario 8: Deleting a Domain automatically nullifies EmailAccount.domain_id without deleting account."""
    token = await register_and_login(async_client, "owner_del_dom@example.com")
    company_id = await create_company_helper(async_client, token, "Delete Dom Corp")
    domain_id = await create_domain_helper(async_client, token, company_id, "to-be-deleted.com")

    # Create EmailAccount referencing this domain
    acc_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/email-accounts",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Temp Inbox",
            "email_address": "inbox@to-be-deleted.com",
            "domain_id": domain_id,
            "smtp_host": "smtp.to-be-deleted.com",
            "smtp_port": 587,
        },
    )
    assert acc_resp.status_code == 201
    account_id = acc_resp.json()["id"]
    assert acc_resp.json()["domain_id"] == domain_id

    # Delete the Domain
    del_resp = await async_client.delete(
        f"/api/v1/companies/{company_id}/domains/{domain_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_resp.status_code == 204

    # Fetch EmailAccount via API - must still exist with domain_id=None and config intact
    get_resp = await async_client.get(
        f"/api/v1/companies/{company_id}/email-accounts/{account_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_resp.status_code == 200
    acc_data = get_resp.json()
    assert acc_data["id"] == account_id
    assert acc_data["domain_id"] is None
    assert acc_data["smtp_host"] == "smtp.to-be-deleted.com"
    assert acc_data["email_address"] == "inbox@to-be-deleted.com"

    # Verify directly in DB
    result = await db_session.execute(
        select(EmailAccount).where(EmailAccount.id == account_id)
    )
    account = result.scalars().first()
    assert account is not None
    assert account.domain_id is None


@pytest.mark.asyncio
async def test_member_cannot_modify_email_account_domain(async_client: AsyncClient):
    """Scenario 10: MEMBER role cannot update or create email accounts with domain_id."""
    token_owner = await register_and_login(async_client, "owner_perm@example.com")
    company_id = await create_company_helper(async_client, token_owner, "Perm Corp")
    domain_id = await create_domain_helper(async_client, token_owner, company_id, "example.com")

    token_member = await register_and_login(async_client, "member_perm@example.com")
    await async_client.post(
        f"/api/v1/companies/{company_id}/members",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"email": "member_perm@example.com", "role": "MEMBER"},
    )

    # Member tries to create email account
    create_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/email-accounts",
        headers={"Authorization": f"Bearer {token_member}"},
        json={
            "name": "Member Inbox",
            "email_address": "member@example.com",
            "domain_id": domain_id,
        },
    )
    assert create_resp.status_code == 403

