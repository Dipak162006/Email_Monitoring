import asyncio
from unittest.mock import AsyncMock, patch
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.email_accounts.models import EmailAccount
from app.modules.emails.models import Email, EmailDirection, EmailSignature, EmailStatus
from app.services.smtp.client import SMTPClient


# =============================================================================
# Helper Utilities
# =============================================================================

async def register_and_login(client: AsyncClient, email: str, name: str = "Test User") -> str:
    """Register and log in a user, returning their JWT access token."""
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123!", "full_name": name},
    )
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    return login_resp.json()["access_token"]


async def create_company_helper(client: AsyncClient, token: str, name: str = "Acme Corp") -> int:
    """Create a company and return its ID."""
    resp = await client.post(
        "/api/v1/companies/",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": name},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def create_account_helper(
    client: AsyncClient,
    token: str,
    company_id: int,
    name: str = "Support Desk",
    email: str = "support@acme.com",
    password: str = "Secret123!",
    smtp_host: str = "smtp.acme.com",
) -> int:
    """Create an email account with SMTP settings and return its ID."""
    resp = await client.post(
        f"/api/v1/companies/{company_id}/email-accounts",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": name,
            "email_address": email,
            "provider": "CUSTOM",
            "smtp_host": smtp_host,
            "smtp_port": 587,
            "smtp_security": "STARTTLS",
            "smtp_username": email,
            "smtp_password": password,
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def add_company_member_helper(
    client: AsyncClient,
    owner_token: str,
    company_id: int,
    user_email: str,
    role: str = "MEMBER",
) -> int:
    """Add a registered user to a company and return their user_id."""
    resp = await client.post(
        f"/api/v1/companies/{company_id}/members",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"email": user_email, "role": role},
    )
    assert resp.status_code == 201
    return resp.json()["user_id"]


async def grant_account_access_helper(
    client: AsyncClient,
    owner_token: str,
    company_id: int,
    account_id: int,
    user_id: int,
) -> None:
    """Grant a company member access to an email account."""
    resp = await client.post(
        f"/api/v1/companies/{company_id}/email-accounts/{account_id}/access",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"user_id": user_id},
    )
    assert resp.status_code == 201


# =============================================================================
# 1. CRUD Tests (1 - 5)
# =============================================================================

@pytest.mark.asyncio
async def test_01_create_signature(async_client: AsyncClient, db_session: AsyncSession):
    """1. Create signature via /api/v1/signatures and account-scoped route."""
    owner_token = await register_and_login(async_client, "sig_owner1@example.com")
    comp_id = await create_company_helper(async_client, owner_token, "Acme Signatures")
    acc_id = await create_account_helper(async_client, owner_token, comp_id, "Sales", "sales@acme.com")

    resp = await async_client.post(
        "/api/v1/signatures",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "name": "Standard Sales Sig",
            "email_account_id": acc_id,
            "body_text": "-- \nSales Team\nAcme Corp",
            "body_html": "<p>-- <br><b>Sales Team</b><br>Acme Corp</p>",
            "is_default": False,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Standard Sales Sig"
    assert data["email_account_id"] == acc_id
    assert data["company_id"] == comp_id
    assert data["is_default"] is False
    assert "-- \nSales Team" in data["body_text"]
    assert "<b>Sales Team</b>" in data["body_html"]


@pytest.mark.asyncio
async def test_02_list_signatures(async_client: AsyncClient, db_session: AsyncSession):
    """2. List signatures scoped to an account or company with pagination."""
    token = await register_and_login(async_client, "sig_owner2@example.com")
    comp_id = await create_company_helper(async_client, token)
    acc_id = await create_account_helper(async_client, token, comp_id, "Desk", "desk@acme.com")

    for i in range(3):
        await async_client.post(
            f"/api/v1/email-accounts/{acc_id}/signatures",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": f"Sig {i}", "body_text": f"Text {i}"},
        )

    resp = await async_client.get(
        f"/api/v1/email-accounts/{acc_id}/signatures?limit=2&offset=0",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert len(data["signatures"]) == 2


@pytest.mark.asyncio
async def test_03_get_signature_by_id(async_client: AsyncClient, db_session: AsyncSession):
    """3. Retrieve an existing signature by ID."""
    token = await register_and_login(async_client, "sig_owner3@example.com")
    comp_id = await create_company_helper(async_client, token)
    acc_id = await create_account_helper(async_client, token, comp_id)

    create_resp = await async_client.post(
        "/api/v1/signatures",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Direct Sig", "email_account_id": acc_id, "body_text": "Direct Body"},
    )
    sig_id = create_resp.json()["id"]

    get_resp = await async_client.get(
        f"/api/v1/signatures/{sig_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == sig_id
    assert get_resp.json()["body_text"] == "Direct Body"


@pytest.mark.asyncio
async def test_04_update_signature(async_client: AsyncClient, db_session: AsyncSession):
    """4. Update signature name, body_text, and body_html."""
    token = await register_and_login(async_client, "sig_owner4@example.com")
    comp_id = await create_company_helper(async_client, token)
    acc_id = await create_account_helper(async_client, token, comp_id)

    create_resp = await async_client.post(
        "/api/v1/signatures",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Old Sig", "email_account_id": acc_id, "body_text": "Old Text"},
    )
    sig_id = create_resp.json()["id"]

    patch_resp = await async_client.patch(
        f"/api/v1/signatures/{sig_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "New Sig", "body_text": "Updated Text", "body_html": "<p>Updated HTML</p>"},
    )
    assert patch_resp.status_code == 200
    data = patch_resp.json()
    assert data["name"] == "New Sig"
    assert data["body_text"] == "Updated Text"
    assert data["body_html"] == "<p>Updated HTML</p>"


@pytest.mark.asyncio
async def test_05_delete_signature(async_client: AsyncClient, db_session: AsyncSession):
    """5. Delete a signature, returning 204, then verify 404."""
    token = await register_and_login(async_client, "sig_owner5@example.com")
    comp_id = await create_company_helper(async_client, token)
    acc_id = await create_account_helper(async_client, token, comp_id)

    create_resp = await async_client.post(
        "/api/v1/signatures",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "To Delete", "email_account_id": acc_id, "body_text": "Delete me"},
    )
    sig_id = create_resp.json()["id"]

    del_resp = await async_client.delete(
        f"/api/v1/signatures/{sig_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_resp.status_code == 204

    get_resp = await async_client.get(
        f"/api/v1/signatures/{sig_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_resp.status_code == 404


# =============================================================================
# 2. Authorization Tests (6 - 8)
# =============================================================================

@pytest.mark.asyncio
async def test_06_unauthorized_member_access_rejected(async_client: AsyncClient, db_session: AsyncSession):
    """6. MEMBER without explicit EmailAccountAccess cannot create or read signatures."""
    owner_token = await register_and_login(async_client, "owner6@example.com")
    member_token = await register_and_login(async_client, "member6@example.com")

    comp_id = await create_company_helper(async_client, owner_token, "Lockdown Corp")
    acc_id = await create_account_helper(async_client, owner_token, comp_id)
    await add_company_member_helper(async_client, owner_token, comp_id, "member6@example.com", "MEMBER")

    # Member tries to create signature on ungranted account
    resp = await async_client.post(
        "/api/v1/signatures",
        headers={"Authorization": f"Bearer {member_token}"},
        json={"name": "Unauthorized Sig", "email_account_id": acc_id, "body_text": "Illegal"},
    )
    assert resp.status_code == 403

    # Owner creates signature
    sig_resp = await async_client.post(
        "/api/v1/signatures",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"name": "Owner Sig", "email_account_id": acc_id, "body_text": "Legal"},
    )
    sig_id = sig_resp.json()["id"]

    # Member tries to get signature
    get_resp = await async_client.get(
        f"/api/v1/signatures/{sig_id}",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert get_resp.status_code == 403


@pytest.mark.asyncio
async def test_07_cross_company_access_rejected(async_client: AsyncClient, db_session: AsyncSession):
    """7. User from Company A cannot create, read, update, or delete signatures of Company B."""
    token_a = await register_and_login(async_client, "user_a7@example.com")
    token_b = await register_and_login(async_client, "user_b7@example.com")

    comp_a = await create_company_helper(async_client, token_a, "Company A")
    comp_b = await create_company_helper(async_client, token_b, "Company B")

    acc_b = await create_account_helper(async_client, token_b, comp_b, "B Desk", "desk@b.com")

    # User A tries to create signature on Company B's account
    resp = await async_client.post(
        "/api/v1/signatures",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"name": "Infiltrator Sig", "email_account_id": acc_b, "body_text": "Cross"},
    )
    assert resp.status_code == 403

    # User B creates signature
    b_sig_resp = await async_client.post(
        "/api/v1/signatures",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"name": "Company B Sig", "email_account_id": acc_b, "body_text": "Valid B"},
    )
    b_sig_id = b_sig_resp.json()["id"]

    # User A tries to get User B's signature
    assert (await async_client.get(
        f"/api/v1/signatures/{b_sig_id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )).status_code == 403

    # User A tries to delete User B's signature
    assert (await async_client.delete(
        f"/api/v1/signatures/{b_sig_id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )).status_code == 403


@pytest.mark.asyncio
async def test_08_inactive_account_rejected(async_client: AsyncClient, db_session: AsyncSession):
    """8. Creating a signature on an inactive email account is rejected with 400 Bad Request."""
    token = await register_and_login(async_client, "owner8@example.com")
    comp_id = await create_company_helper(async_client, token)
    acc_id = await create_account_helper(async_client, token, comp_id)

    # Deactivate account directly in DB
    acc = await db_session.get(EmailAccount, acc_id)
    acc.is_active = False
    await db_session.commit()

    resp = await async_client.post(
        "/api/v1/signatures",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Inactive Sig", "email_account_id": acc_id, "body_text": "Inactive"},
    )
    assert resp.status_code == 400
    assert "inactive" in resp.json()["detail"].lower()


# =============================================================================
# 3. Default Signature Behavior Tests (9 - 13)
# =============================================================================

@pytest.mark.asyncio
async def test_09_set_default_signature_unsets_previous(async_client: AsyncClient, db_session: AsyncSession):
    """9. Setting a signature as default safely unsets any previous default for that account."""
    token = await register_and_login(async_client, "owner9@example.com")
    comp_id = await create_company_helper(async_client, token)
    acc_id = await create_account_helper(async_client, token, comp_id)

    sig1_resp = await async_client.post(
        "/api/v1/signatures",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Sig 1", "email_account_id": acc_id, "body_text": "Text 1", "is_default": True},
    )
    sig1_id = sig1_resp.json()["id"]
    assert sig1_resp.json()["is_default"] is True

    # Create Sig 2 with is_default=True -> unsets Sig 1
    sig2_resp = await async_client.post(
        "/api/v1/signatures",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Sig 2", "email_account_id": acc_id, "body_text": "Text 2", "is_default": True},
    )
    sig2_id = sig2_resp.json()["id"]
    assert sig2_resp.json()["is_default"] is True

    # Verify Sig 1 is now is_default=False
    sig1_check = await async_client.get(f"/api/v1/signatures/{sig1_id}", headers={"Authorization": f"Bearer {token}"})
    assert sig1_check.json()["is_default"] is False

    # Now call set-default on Sig 1
    set_def_resp = await async_client.post(
        f"/api/v1/signatures/{sig1_id}/set-default",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert set_def_resp.status_code == 200
    assert set_def_resp.json()["is_default"] is True

    # Sig 2 should now be unset
    sig2_check = await async_client.get(f"/api/v1/signatures/{sig2_id}", headers={"Authorization": f"Bearer {token}"})
    assert sig2_check.json()["is_default"] is False


@pytest.mark.asyncio
async def test_10_only_one_default_exists_per_account(async_client: AsyncClient, db_session: AsyncSession):
    """10. Multiple signatures on an account result in exactly one default."""
    token = await register_and_login(async_client, "owner10@example.com")
    comp_id = await create_company_helper(async_client, token)
    acc_id = await create_account_helper(async_client, token, comp_id)

    sig_ids = []
    for i in range(4):
        resp = await async_client.post(
            "/api/v1/signatures",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": f"Sig {i}", "email_account_id": acc_id, "body_text": f"Text {i}"},
        )
        sig_ids.append(resp.json()["id"])

    # Set third signature as default
    await async_client.post(
        f"/api/v1/signatures/{sig_ids[2]}/set-default",
        headers={"Authorization": f"Bearer {token}"},
    )

    # Check database directly
    stmt = select(EmailSignature).where(
        EmailSignature.email_account_id == acc_id,
        EmailSignature.is_default == True,
    )
    res = await db_session.execute(stmt)
    defaults = res.scalars().all()
    assert len(defaults) == 1
    assert defaults[0].id == sig_ids[2]


@pytest.mark.asyncio
async def test_11_get_default_signature_endpoint(async_client: AsyncClient, db_session: AsyncSession):
    """11. Retrieve the default signature via /signatures/default and account path."""
    token = await register_and_login(async_client, "owner11@example.com")
    comp_id = await create_company_helper(async_client, token)
    acc_id = await create_account_helper(async_client, token, comp_id)

    # Initially None
    resp = await async_client.get(
        f"/api/v1/signatures/default?email_account_id={acc_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json() is None

    # Create a default signature
    await async_client.post(
        "/api/v1/signatures",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Default Sig", "email_account_id": acc_id, "body_text": "I am default", "is_default": True},
    )

    resp2 = await async_client.get(
        f"/api/v1/email-accounts/{acc_id}/signatures/default",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 200
    assert resp2.json()["name"] == "Default Sig"
    assert resp2.json()["is_default"] is True


@pytest.mark.asyncio
async def test_12_default_cannot_be_set_across_accounts_companies(async_client: AsyncClient, db_session: AsyncSession):
    """12. An unauthorized user cannot set a signature as default on another company's account."""
    token_a = await register_and_login(async_client, "user_a12@example.com")
    token_b = await register_and_login(async_client, "user_b12@example.com")

    comp_b = await create_company_helper(async_client, token_b, "Company B")
    acc_b = await create_account_helper(async_client, token_b, comp_b)

    sig_resp = await async_client.post(
        "/api/v1/signatures",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"name": "Sig B", "email_account_id": acc_b, "body_text": "Text B"},
    )
    sig_b_id = sig_resp.json()["id"]

    # User A attempts to set default on Sig B
    resp = await async_client.post(
        f"/api/v1/signatures/{sig_b_id}/set-default",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp.status_code == 403


# =============================================================================
# 4. Content & Deduplication Tests (13 - 17)
# =============================================================================

@pytest.mark.asyncio
async def test_13_plain_text_signature_insertion(async_client: AsyncClient, db_session: AsyncSession):
    """13. Plain-text signature is cleanly appended to composed email body."""
    token = await register_and_login(async_client, "owner13@example.com")
    comp_id = await create_company_helper(async_client, token)
    acc_id = await create_account_helper(async_client, token, comp_id)

    sig_resp = await async_client.post(
        "/api/v1/signatures",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Plain Sig",
            "email_account_id": acc_id,
            "body_text": "-- \nAlice Smith\nAcme Corp",
            "is_default": True,
        },
    )

    with patch.object(SMTPClient, "send_email_sync", return_value=None):
        send_resp = await async_client.post(
            "/api/v1/emails/send",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email_account_id": acc_id,
                "to": ["client@partner.com"],
                "subject": "Greetings",
                "body_text": "Hello there, hope all is well.",
            },
        )
        assert send_resp.status_code == 201
        data = send_resp.json()
        assert "Hello there, hope all is well." in data["body_text"]
        assert "-- \nAlice Smith\nAcme Corp" in data["body_text"]


@pytest.mark.asyncio
async def test_14_html_signature_insertion(async_client: AsyncClient, db_session: AsyncSession):
    """14. HTML signature is cleanly inserted before </body> or appended to HTML email."""
    token = await register_and_login(async_client, "owner14@example.com")
    comp_id = await create_company_helper(async_client, token)
    acc_id = await create_account_helper(async_client, token, comp_id)

    await async_client.post(
        "/api/v1/signatures",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "HTML Sig",
            "email_account_id": acc_id,
            "body_html": "<div class='sig'>-- <br><b>Bob</b></div>",
            "is_default": True,
        },
    )

    with patch.object(SMTPClient, "send_email_sync", return_value=None):
        send_resp = await async_client.post(
            "/api/v1/emails/send",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email_account_id": acc_id,
                "to": ["partner@test.com"],
                "subject": "HTML Test",
                "body_html": "<html><body><p>Main content</p></body></html>",
            },
        )
        assert send_resp.status_code == 201
        data = send_resp.json()
        assert (
            '<div class="sig">-- <br><b>Bob</b></div>' in data["body_html"]
            or "<div class='sig'>-- <br><b>Bob</b></div>" in data["body_html"]
        )
        assert data["body_html"].endswith("</body></html>")


@pytest.mark.asyncio
async def test_15_both_text_and_html_signature_insertion(async_client: AsyncClient, db_session: AsyncSession):
    """15. When email has both body_text and body_html, both receive their respective signatures."""
    token = await register_and_login(async_client, "owner15@example.com")
    comp_id = await create_company_helper(async_client, token)
    acc_id = await create_account_helper(async_client, token, comp_id)

    await async_client.post(
        "/api/v1/signatures",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Dual Sig",
            "email_account_id": acc_id,
            "body_text": "-- \nDual Text Sig",
            "body_html": "<p>-- <br>Dual HTML Sig</p>",
            "is_default": True,
        },
    )

    with patch.object(SMTPClient, "send_email_sync", return_value=None):
        send_resp = await async_client.post(
            "/api/v1/emails/send",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email_account_id": acc_id,
                "to": ["partner@test.com"],
                "subject": "Dual Test",
                "body_text": "Text content",
                "body_html": "<p>HTML content</p>",
            },
        )
        assert send_resp.status_code == 201
        data = send_resp.json()
        assert "-- \nDual Text Sig" in data["body_text"]
        assert "<p>-- <br>Dual HTML Sig</p>" in data["body_html"]


@pytest.mark.asyncio
async def test_16_no_duplicate_signature_insertion(async_client: AsyncClient, db_session: AsyncSession):
    """16. If body already contains signature, do not duplicate it."""
    token = await register_and_login(async_client, "owner16@example.com")
    comp_id = await create_company_helper(async_client, token)
    acc_id = await create_account_helper(async_client, token, comp_id)

    sig_text = "-- \nCharlie Brown"
    await async_client.post(
        "/api/v1/signatures",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Charlie Sig",
            "email_account_id": acc_id,
            "body_text": sig_text,
            "is_default": True,
        },
    )

    with patch.object(SMTPClient, "send_email_sync", return_value=None):
        send_resp = await async_client.post(
            "/api/v1/emails/send",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email_account_id": acc_id,
                "to": ["test@test.com"],
                "subject": "Pre-signed",
                "body_text": f"Hey there!\n\n{sig_text}",
            },
        )
        assert send_resp.status_code == 201
        data = send_resp.json()
        # Ensure sig_text appears exactly once
        assert data["body_text"].count(sig_text) == 1


# =============================================================================
# 5. Integration Tests: Compose, Drafts, Templates (17 - 22)
# =============================================================================

@pytest.mark.asyncio
async def test_17_explicit_signature_selection_in_send(async_client: AsyncClient, db_session: AsyncSession):
    """17. When signature_id is provided in send_req, use that signature instead of default."""
    token = await register_and_login(async_client, "owner17@example.com")
    comp_id = await create_company_helper(async_client, token)
    acc_id = await create_account_helper(async_client, token, comp_id)

    # Default sig
    await async_client.post(
        "/api/v1/signatures",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Default Sig", "email_account_id": acc_id, "body_text": "DEFAULT_SIG", "is_default": True},
    )
    # Alternate sig
    alt_resp = await async_client.post(
        "/api/v1/signatures",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Alt Sig", "email_account_id": acc_id, "body_text": "ALT_SIG", "is_default": False},
    )
    alt_id = alt_resp.json()["id"]

    with patch.object(SMTPClient, "send_email_sync", return_value=None):
        send_resp = await async_client.post(
            "/api/v1/emails/send",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email_account_id": acc_id,
                "to": ["client@test.com"],
                "subject": "Explicit Sig Test",
                "body_text": "Message body",
                "signature_id": alt_id,
            },
        )
        assert send_resp.status_code == 201
        data = send_resp.json()
        assert "ALT_SIG" in data["body_text"]
        assert "DEFAULT_SIG" not in data["body_text"]


@pytest.mark.asyncio
async def test_18_draft_creation_with_default_and_explicit_signature(async_client: AsyncClient, db_session: AsyncSession):
    """18. Creating a draft automatically incorporates the default signature or explicit signature."""
    token = await register_and_login(async_client, "owner18@example.com")
    comp_id = await create_company_helper(async_client, token)
    acc_id = await create_account_helper(async_client, token, comp_id)

    await async_client.post(
        "/api/v1/signatures",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Draft Default", "email_account_id": acc_id, "body_text": "-- \nDraft Default", "is_default": True},
    )

    # Create draft without explicit signature -> picks up default
    draft_resp = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "email_account_id": acc_id,
            "to": ["recipient@draft.com"],
            "subject": "Draft Subject",
            "body_text": "Draft content",
        },
    )
    assert draft_resp.status_code == 201
    draft_data = draft_resp.json()
    assert "Draft content" in draft_data["body_text"]
    assert "-- \nDraft Default" in draft_data["body_text"]


@pytest.mark.asyncio
async def test_19_editing_draft_does_not_duplicate_signature(async_client: AsyncClient, db_session: AsyncSession):
    """19. Editing draft body text multiple times does not repeatedly append the signature."""
    token = await register_and_login(async_client, "owner19@example.com")
    comp_id = await create_company_helper(async_client, token)
    acc_id = await create_account_helper(async_client, token, comp_id)

    sig_text = "-- \nDraft Sig"
    await async_client.post(
        "/api/v1/signatures",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Sig", "email_account_id": acc_id, "body_text": sig_text, "is_default": True},
    )

    draft_resp = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={"email_account_id": acc_id, "subject": "Test", "body_text": "Initial text"},
    )
    draft_id = draft_resp.json()["id"]

    # Update draft body
    update_resp = await async_client.put(
        f"/api/v1/emails/drafts/{draft_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"body_text": "Updated draft text without sig"},
    )
    assert update_resp.status_code == 200
    # Because account has default sig, update_draft preserves default sig without duplication
    assert "Updated draft text without sig" in update_resp.json()["body_text"]
    assert "-- \nDraft Sig" in update_resp.json()["body_text"]
    assert update_resp.json()["body_text"].count("Draft Sig") == 1


@pytest.mark.asyncio
async def test_20_apply_signature_to_draft_endpoints(async_client: AsyncClient, db_session: AsyncSession):
    """20. Explicitly applying a signature to a draft via /apply-signature endpoints."""
    token = await register_and_login(async_client, "owner20@example.com")
    comp_id = await create_company_helper(async_client, token)
    acc_id = await create_account_helper(async_client, token, comp_id)

    sig_resp = await async_client.post(
        "/api/v1/signatures",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Post Sig", "email_account_id": acc_id, "body_text": "-- \nPost Signature"},
    )
    sig_id = sig_resp.json()["id"]

    draft_resp = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={"email_account_id": acc_id, "subject": "Apply Sig Test", "body_text": "Hello client"},
    )
    draft_id = draft_resp.json()["id"]

    apply_resp = await async_client.post(
        f"/api/v1/emails/drafts/{draft_id}/apply-signature/{sig_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert apply_resp.status_code == 200
    assert "-- \nPost Signature" in apply_resp.json()["body_text"]


@pytest.mark.asyncio
async def test_21_template_plus_signature_integration(async_client: AsyncClient, db_session: AsyncSession):
    """21. Applying a template to a draft automatically integrates the default or selected signature."""
    token = await register_and_login(async_client, "owner21@example.com")
    comp_id = await create_company_helper(async_client, token)
    acc_id = await create_account_helper(async_client, token, comp_id)

    # Create default signature for the account
    await async_client.post(
        "/api/v1/signatures",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Account Default", "email_account_id": acc_id, "body_text": "-- \nSupport Agent", "is_default": True},
    )

    # Create template
    tmpl_resp = await async_client.post(
        "/api/v1/emails/templates",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Welcome Template",
            "subject": "Welcome to our service",
            "body_text": "Thank you for signing up with us!",
        },
    )
    tmpl_id = tmpl_resp.json()["id"]

    # Create empty draft
    draft_resp = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={"email_account_id": acc_id},
    )
    draft_id = draft_resp.json()["id"]

    # Apply template to draft -> should also apply default signature
    apply_resp = await async_client.post(
        f"/api/v1/emails/drafts/{draft_id}/apply-template/{tmpl_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert apply_resp.status_code == 200
    data = apply_resp.json()
    assert data["subject"] == "Welcome to our service"
    assert "Thank you for signing up with us!" in data["body_text"]
    assert "-- \nSupport Agent" in data["body_text"]


@pytest.mark.asyncio
async def test_22_send_email_without_signatures_remains_unaffected(async_client: AsyncClient, db_session: AsyncSession):
    """22. Existing send email behavior remains intact when no signatures exist."""
    token = await register_and_login(async_client, "owner22@example.com")
    comp_id = await create_company_helper(async_client, token)
    acc_id = await create_account_helper(async_client, token, comp_id)

    with patch.object(SMTPClient, "send_email_sync", return_value=None):
        send_resp = await async_client.post(
            "/api/v1/emails/send",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email_account_id": acc_id,
                "to": ["regular@test.com"],
                "subject": "Clean Send",
                "body_text": "Just plain message content.",
            },
        )
        assert send_resp.status_code == 201
        data = send_resp.json()
        assert data["body_text"] == "Just plain message content."
        assert data["status"] == "SENT"


# =============================================================================
# M11 Hardening Tests: Concurrency, Database Uniqueness, and HTML Sanitization
# =============================================================================

@pytest.mark.asyncio
async def test_23_database_level_single_default_enforcement(async_client: AsyncClient, db_session: AsyncSession):
    """23. Direct database attempt to insert two default signatures for the same account raises IntegrityError."""
    from sqlalchemy.exc import IntegrityError
    token = await register_and_login(async_client, "owner23@example.com")
    comp_id = await create_company_helper(async_client, token)
    acc_id = await create_account_helper(async_client, token, comp_id)

    # 1. First signature marked default via API
    resp1 = await async_client.post(
        "/api/v1/signatures",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Default 1", "email_account_id": acc_id, "body_text": "Sig 1", "is_default": True},
    )
    assert resp1.status_code == 201

    # 2. Attempt direct SQL insertion of a second default signature for the same account without unsetting the first
    sig2 = EmailSignature(
        company_id=comp_id,
        email_account_id=acc_id,
        name="Default 2 Bypassing Service",
        body_text="Sig 2",
        is_default=True,
    )
    db_session.add(sig2)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_24_concurrent_default_signature_operations(async_client: AsyncClient, db_session: AsyncSession):
    """24. Concurrent requests setting default signature for the same EmailAccount are serialized without violating uniqueness."""
    token = await register_and_login(async_client, "owner24@example.com")
    comp_id = await create_company_helper(async_client, token)
    acc_id = await create_account_helper(async_client, token, comp_id)

    # Create 3 non-default signatures
    sig_ids = []
    for i in range(3):
        resp = await async_client.post(
            "/api/v1/signatures",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": f"Sig {i}", "email_account_id": acc_id, "body_text": f"Sig Text {i}", "is_default": False},
        )
        assert resp.status_code == 201
        sig_ids.append(resp.json()["id"])

    # Launch concurrent requests setting each one as default
    async def set_default_task(sig_id: int):
        return await async_client.put(
            f"/api/v1/signatures/{sig_id}/set-default",
            headers={"Authorization": f"Bearer {token}"},
        )

    responses = await asyncio.gather(*(set_default_task(sid) for sid in sig_ids))
    # All responses must be either 200 OK or 409 Conflict (never 500)
    for resp in responses:
        assert resp.status_code in {200, 409}

    # Verify at the database level that exactly one default signature exists for this account
    stmt = select(EmailSignature).where(
        EmailSignature.email_account_id == acc_id,
        EmailSignature.is_default == True,
    )
    res = await db_session.execute(stmt)
    defaults = res.scalars().all()
    assert len(defaults) == 1


@pytest.mark.asyncio
async def test_25_different_email_accounts_each_have_own_default(async_client: AsyncClient, db_session: AsyncSession):
    """25. Multiple different EmailAccounts can each have their own default signature without collision."""
    token = await register_and_login(async_client, "owner25@example.com")
    comp_id = await create_company_helper(async_client, token)
    acc1_id = await create_account_helper(async_client, token, comp_id, name="Acc 1", email="acc1@acme.com")
    acc2_id = await create_account_helper(async_client, token, comp_id, name="Acc 2", email="acc2@acme.com")

    resp1 = await async_client.post(
        "/api/v1/signatures",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Acc1 Default", "email_account_id": acc1_id, "body_text": "Sig 1", "is_default": True},
    )
    assert resp1.status_code == 201

    resp2 = await async_client.post(
        "/api/v1/signatures",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Acc2 Default", "email_account_id": acc2_id, "body_text": "Sig 2", "is_default": True},
    )
    assert resp2.status_code == 201

    # Verify both defaults exist simultaneously
    stmt = select(EmailSignature).where(
        EmailSignature.email_account_id.in_([acc1_id, acc2_id]),
        EmailSignature.is_default == True,
    )
    res = await db_session.execute(stmt)
    defaults = res.scalars().all()
    assert len(defaults) == 2
    acc_ids = {d.email_account_id for d in defaults}
    assert acc_ids == {acc1_id, acc2_id}


@pytest.mark.asyncio
async def test_26_unsafe_html_is_sanitized_and_safe_formatting_preserved(async_client: AsyncClient, db_session: AsyncSession):
    """26. Unsafe HTML elements, scripts, and event handlers are sanitized while safe email formatting is preserved."""
    token = await register_and_login(async_client, "owner26@example.com")
    comp_id = await create_company_helper(async_client, token)
    acc_id = await create_account_helper(async_client, token, comp_id)

    raw_html = (
        "<p>Best regards,</p>"
        "<script>alert('pwned');</script>"
        "<div onclick=\"stealCookies()\"><strong>Jane Doe</strong></div>"
        "<img src=\"x\" onerror=\"malicious()\">"
        "<a href=\"javascript:alert('xss')\">Dangerous Link</a>"
        "<a href=\"https://legit.example.com\">Legit Link</a>"
        "<ul><li>Item 1</li><li>Item 2</li></ul>"
    )

    resp = await async_client.post(
        "/api/v1/signatures",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Sanitized Sig",
            "email_account_id": acc_id,
            "body_html": raw_html,
        },
    )
    assert resp.status_code == 201
    sanitized = resp.json()["body_html"]

    # 1. Unsafe content must be completely removed
    assert "<script>" not in sanitized
    assert "alert('pwned')" not in sanitized
    assert "onclick" not in sanitized
    assert "stealCookies" not in sanitized
    assert "onerror" not in sanitized
    assert "malicious" not in sanitized
    assert "javascript:" not in sanitized

    # 2. Safe formatting elements must remain
    assert "<p>Best regards,</p>" in sanitized
    assert "<strong>Jane Doe</strong>" in sanitized
    assert '<a href="https://legit.example.com">Legit Link</a>' in sanitized
    assert "<ul><li>Item 1</li><li>Item 2</li></ul>" in sanitized


@pytest.mark.asyncio
async def test_27_sanitized_html_reaches_composed_email_and_draft(async_client: AsyncClient, db_session: AsyncSession):
    """27. Outgoing emails and drafts apply the sanitized HTML signature without raw malicious scripts."""
    token = await register_and_login(async_client, "owner27@example.com")
    comp_id = await create_company_helper(async_client, token)
    acc_id = await create_account_helper(async_client, token, comp_id)

    malicious_sig = (
        "<div onload=\"alert(1)\">-- <br>"
        "<b>Executive Team</b>"
        "<script src=\"http://evil.com/leak.js\"></script>"
        "</div>"
    )

    sig_resp = await async_client.post(
        "/api/v1/signatures",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Malicious Test Sig",
            "email_account_id": acc_id,
            "body_html": malicious_sig,
            "is_default": True,
        },
    )
    assert sig_resp.status_code == 201

    # Send outgoing email
    with patch.object(SMTPClient, "send_email_sync", return_value=None):
        send_resp = await async_client.post(
            "/api/v1/emails/send",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email_account_id": acc_id,
                "to": ["partner@test.com"],
                "subject": "Safety Check",
                "body_html": "<html><body><p>Hello customer</p></body></html>",
            },
        )
        assert send_resp.status_code == 201
        data = send_resp.json()
        assert "<b>Executive Team</b>" in data["body_html"]
        assert "onload" not in data["body_html"]
        assert "leak.js" not in data["body_html"]
        assert "<script" not in data["body_html"]

    # Also test draft creation
    draft_resp = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "email_account_id": acc_id,
            "body_html": "<p>Draft body</p>",
        },
    )
    assert draft_resp.status_code == 201
    draft_data = draft_resp.json()
    assert "<b>Executive Team</b>" in draft_data["body_html"]
    assert "onload" not in draft_data["body_html"]
    assert "<script" not in draft_data["body_html"]


@pytest.mark.asyncio
async def test_28_plain_text_signatures_not_broken(async_client: AsyncClient, db_session: AsyncSession):
    """28. Plain-text only signatures continue to work properly with compose and templates."""
    token = await register_and_login(async_client, "owner28@example.com")
    comp_id = await create_company_helper(async_client, token)
    acc_id = await create_account_helper(async_client, token, comp_id)

    sig_resp = await async_client.post(
        "/api/v1/signatures",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Plain Sig",
            "email_account_id": acc_id,
            "body_text": "-- \nPlain Text Engineer\nAcme Corp",
            "is_default": True,
        },
    )
    assert sig_resp.status_code == 201
    assert sig_resp.json()["body_html"] is None

    # Verify sending plain text email with default plain text signature
    with patch.object(SMTPClient, "send_email_sync", return_value=None):
        send_resp = await async_client.post(
            "/api/v1/emails/send",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email_account_id": acc_id,
                "to": ["partner@test.com"],
                "subject": "Plain Test",
                "body_text": "Hello there!",
            },
        )
        assert send_resp.status_code == 201
        data = send_resp.json()
        assert "Hello there!" in data["body_text"]
        assert "-- \nPlain Text Engineer\nAcme Corp" in data["body_text"]


@pytest.mark.asyncio
async def test_29_list_signatures_without_filter_regression(async_client: AsyncClient, db_session: AsyncSession):
    """29. Regression: GET /api/v1/signatures lists all accessible signatures without role AttributeError.
    
    Verifies:
    1. Authenticated user belonging to a company can call GET /api/v1/signatures without query params.
    2. Endpoint succeeds with HTTP 200 without raising AttributeError on comp_user role string.
    3. Returned signatures are correctly listed across accessible accounts.
    4. Account-scoped listing works via GET /api/v1/signatures?account_id=<authorized_account_id>
       and GET /api/v1/signatures?email_account_id=<authorized_account_id>.
    5. MEMBER role without full access only sees permitted account signatures.
    """
    token = await register_and_login(async_client, "owner29@example.com")
    comp_id = await create_company_helper(async_client, token, "Regress Corp")
    acc1_id = await create_account_helper(async_client, token, comp_id, "Support", "support@regress.com")
    acc2_id = await create_account_helper(async_client, token, comp_id, "Billing", "billing@regress.com")

    # Create signatures on both accounts
    sig1_resp = await async_client.post(
        "/api/v1/signatures",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Support Sig",
            "email_account_id": acc1_id,
            "body_text": "-- Support",
            "is_default": True,
        },
    )
    assert sig1_resp.status_code == 201
    sig1_id = sig1_resp.json()["id"]

    sig2_resp = await async_client.post(
        "/api/v1/signatures",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Billing Sig",
            "email_account_id": acc2_id,
            "body_text": "-- Billing",
            "is_default": False,
        },
    )
    assert sig2_resp.status_code == 201
    sig2_id = sig2_resp.json()["id"]

    # 1. Unfiltered listing: exercises CompanyService.get_user_companies() authorization path
    list_resp = await async_client.get(
        "/api/v1/signatures",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert list_data["total"] >= 2
    returned_ids = [s["id"] for s in list_data["signatures"]]
    assert sig1_id in returned_ids
    assert sig2_id in returned_ids

    # 2. Account-scoped listing using ?account_id=
    scoped_resp = await async_client.get(
        f"/api/v1/signatures?account_id={acc1_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert scoped_resp.status_code == 200
    scoped_data = scoped_resp.json()
    assert scoped_data["total"] == 1
    assert len(scoped_data["signatures"]) == 1
    assert scoped_data["signatures"][0]["id"] == sig1_id

    # 3. Account-scoped listing using ?email_account_id=
    scoped_resp2 = await async_client.get(
        f"/api/v1/signatures?email_account_id={acc2_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert scoped_resp2.status_code == 200
    scoped_data2 = scoped_resp2.json()
    assert scoped_data2["total"] == 1
    assert len(scoped_data2["signatures"]) == 1
    assert scoped_data2["signatures"][0]["id"] == sig2_id

    # 4. Member role with granted access only to acc1_id
    member_token = await register_and_login(async_client, "member29@example.com")
    member_user_id = await add_company_member_helper(async_client, token, comp_id, "member29@example.com", "MEMBER")
    await grant_account_access_helper(async_client, token, comp_id, acc1_id, member_user_id)

    member_list_resp = await async_client.get(
        "/api/v1/signatures",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert member_list_resp.status_code == 200
    member_data = member_list_resp.json()
    member_sig_ids = [s["id"] for s in member_data["signatures"]]
    assert sig1_id in member_sig_ids
    assert sig2_id not in member_sig_ids


# =============================================================================
# 6. Compose Draft Signature Propagation & MIME Regression Tests (30 - 33)
# =============================================================================

@pytest.mark.asyncio
async def test_30_draft_create_with_signature_id_and_mime_send(async_client: AsyncClient, db_session: AsyncSession):
    """30. Regression: Draft create with signature_id applies signature to body_text/body_html
    and sending draft generates MIME containing the signature.
    """
    token = await register_and_login(async_client, "owner30@example.com")
    comp_id = await create_company_helper(async_client, token, "Draft Sig Corp 30")
    acc1_id = await create_account_helper(async_client, token, comp_id, "Support", "support30@test.com")
    acc2_id = await create_account_helper(async_client, token, comp_id, "Sales", "sales30@test.com")

    # Create Signature A on Acc1
    sig_a_resp = await async_client.post(
        "/api/v1/signatures",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Sig A",
            "email_account_id": acc1_id,
            "body_text": "-- \nSupport Agent Alpha",
            "body_html": "<p>-- <br><b>Support Agent Alpha</b></p>",
            "is_default": False,
        },
    )
    assert sig_a_resp.status_code == 201
    sig_a_id = sig_a_resp.json()["id"]

    # Create Signature B on Acc2
    sig_b_resp = await async_client.post(
        "/api/v1/signatures",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Sig B",
            "email_account_id": acc2_id,
            "body_text": "-- \nSales Rep Beta",
            "body_html": "<p>-- <br><b>Sales Rep Beta</b></p>",
            "is_default": False,
        },
    )
    assert sig_b_resp.status_code == 201
    sig_b_id = sig_b_resp.json()["id"]

    # 1. Wrong-account signature is rejected on draft create
    wrong_acc_resp = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "email_account_id": acc1_id,
            "to": ["customer@test.com"],
            "subject": "Inquiry",
            "body_text": "Hello there",
            "signature_id": sig_b_id,
        },
    )
    assert wrong_acc_resp.status_code == 400
    assert "Signature does not belong to the selected email account" in wrong_acc_resp.json()["detail"]

    # 2. Draft create with signature_id on authorized account
    create_resp = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "email_account_id": acc1_id,
            "to": ["customer@test.com"],
            "subject": "Help Request",
            "body_text": "Hello customer,",
            "body_html": "<p>Hello customer,</p>",
            "signature_id": sig_a_id,
        },
    )
    assert create_resp.status_code == 201
    draft_data = create_resp.json()
    draft_id = draft_data["id"]

    # Verify signature is applied to both body_text and body_html
    assert "Hello customer," in draft_data["body_text"]
    assert "-- \nSupport Agent Alpha" in draft_data["body_text"]
    assert "<p>Hello customer,</p>" in draft_data["body_html"]
    assert "<b>Support Agent Alpha</b>" in draft_data["body_html"]

    # 3. Sending the resulting draft produces MIME containing the signature
    captured_kwargs = {}

    def mock_send(*args, **kwargs):
        captured_kwargs.update(kwargs)

    with patch.object(SMTPClient, "send_email_sync", side_effect=mock_send):
        send_resp = await async_client.post(
            f"/api/v1/emails/drafts/{draft_id}/send",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert send_resp.status_code == 200
        sent_data = send_resp.json()
        assert sent_data["status"] == "SENT"

        # Verify MIME message
        mime_msg = captured_kwargs["message"]
        assert mime_msg is not None

        plain_part = None
        html_part = None
        for part in mime_msg.walk():
            ct = part.get_content_type()
            if ct == "text/plain":
                plain_part = part.get_content()
            elif ct == "text/html":
                html_part = part.get_content()

        assert plain_part is not None
        assert "Hello customer," in plain_part
        assert "-- \nSupport Agent Alpha" in plain_part

        assert html_part is not None
        assert "Hello customer," in html_part
        assert "<b>Support Agent Alpha</b>" in html_part


@pytest.mark.asyncio
async def test_31_draft_update_with_signature_id_and_repeated_autosave(async_client: AsyncClient, db_session: AsyncSession):
    """31. Regression: Updating draft with signature_id applies signature,
    and repeated updates/autosaves do not duplicate the signature.
    """
    token = await register_and_login(async_client, "owner31@example.com")
    comp_id = await create_company_helper(async_client, token, "Draft Sig Corp 31")
    acc1_id = await create_account_helper(async_client, token, comp_id, "Support", "support31@test.com")
    acc2_id = await create_account_helper(async_client, token, comp_id, "Sales", "sales31@test.com")

    # Create Signature A on Acc1
    sig_a_resp = await async_client.post(
        "/api/v1/signatures",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Sig A 31",
            "email_account_id": acc1_id,
            "body_text": "-- \nSupport Lead 31",
            "body_html": "<p>-- <br><b>Support Lead 31</b></p>",
            "is_default": False,
        },
    )
    sig_a_id = sig_a_resp.json()["id"]

    # Create Signature B on Acc2
    sig_b_resp = await async_client.post(
        "/api/v1/signatures",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Sig B 31",
            "email_account_id": acc2_id,
            "body_text": "-- \nSales Lead 31",
            "body_html": "<p>-- <br><b>Sales Lead 31</b></p>",
            "is_default": False,
        },
    )
    sig_b_id = sig_b_resp.json()["id"]

    # 1. Create draft without signature
    draft_resp = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "email_account_id": acc1_id,
            "to": ["partner@test.com"],
            "subject": "Proposal",
            "body_text": "Draft v1 text",
            "body_html": "<p>Draft v1 text</p>",
        },
    )
    assert draft_resp.status_code == 201
    draft_id = draft_resp.json()["id"]
    assert "Support Lead 31" not in draft_resp.json()["body_text"]

    # 2. Reject wrong-account signature_id on draft update
    bad_update = await async_client.put(
        f"/api/v1/emails/drafts/{draft_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "signature_id": sig_b_id,
        },
    )
    assert bad_update.status_code == 400
    assert "Signature does not belong to this draft's email account" in bad_update.json()["detail"]

    # 3. User selects Signature A -> autosave update with signature_id
    update_1 = await async_client.put(
        f"/api/v1/emails/drafts/{draft_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "body_text": "Draft v1 text",
            "body_html": "<p>Draft v1 text</p>",
            "signature_id": sig_a_id,
        },
    )
    assert update_1.status_code == 200
    u1_data = update_1.json()
    assert "Draft v1 text" in u1_data["body_text"]
    assert "-- \nSupport Lead 31" in u1_data["body_text"]
    assert "<b>Support Lead 31</b>" in u1_data["body_html"]

    # 4. User continues typing -> second autosave update with more text and same signature_id
    update_2 = await async_client.put(
        f"/api/v1/emails/drafts/{draft_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "body_text": "Draft v1 text with more info added",
            "body_html": "<p>Draft v1 text with more info added</p>",
            "signature_id": sig_a_id,
        },
    )
    assert update_2.status_code == 200
    u2_data = update_2.json()
    assert "Draft v1 text with more info added" in u2_data["body_text"]
    # Verify signature appears EXACTLY ONCE
    assert u2_data["body_text"].count("Support Lead 31") == 1
    assert u2_data["body_html"].count("Support Lead 31") == 1

    # 5. Third autosave (e.g. subject changed or attachment added) -> repeated update
    update_3 = await async_client.put(
        f"/api/v1/emails/drafts/{draft_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "subject": "Proposal - Final Version",
            "body_text": "Draft v1 text with more info added",
            "body_html": "<p>Draft v1 text with more info added</p>",
            "signature_id": sig_a_id,
        },
    )
    assert update_3.status_code == 200
    u3_data = update_3.json()
    assert u3_data["subject"] == "Proposal - Final Version"
    assert u3_data["body_text"].count("Support Lead 31") == 1
    assert u3_data["body_html"].count("Support Lead 31") == 1

    # 6. Send draft and verify final MIME
    captured_kwargs = {}

    def mock_send(*args, **kwargs):
        captured_kwargs.update(kwargs)

    with patch.object(SMTPClient, "send_email_sync", side_effect=mock_send):
        send_resp = await async_client.post(
            f"/api/v1/emails/drafts/{draft_id}/send",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert send_resp.status_code == 200

        mime_msg = captured_kwargs["message"]
        for part in mime_msg.walk():
            if part.get_content_type() == "text/plain":
                plain_part = part.get_content()
                assert "Draft v1 text with more info added" in plain_part
                assert plain_part.count("Support Lead 31") == 1
            elif part.get_content_type() == "text/html":
                html_part = part.get_content()
                assert "Draft v1 text with more info added" in html_part
                assert html_part.count("Support Lead 31") == 1


@pytest.mark.asyncio
async def test_32_draft_close_reopen_and_send_preserves_signature(async_client: AsyncClient, db_session: AsyncSession):
    """32. Regression: Reopening an existing draft with an applied signature
    and sending it preserves the signature without duplicates.
    """
    token = await register_and_login(async_client, "owner32@example.com")
    comp_id = await create_company_helper(async_client, token, "Draft Sig Corp 32")
    acc_id = await create_account_helper(async_client, token, comp_id, "Desk", "desk32@test.com")

    # Create Signature
    sig_resp = await async_client.post(
        "/api/v1/signatures",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Sig 32",
            "email_account_id": acc_id,
            "body_text": "-- \nDesk Officer 32",
            "body_html": "<p>-- <br><b>Desk Officer 32</b></p>",
            "is_default": False,
        },
    )
    sig_id = sig_resp.json()["id"]

    # Create draft with Signature
    draft_resp = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "email_account_id": acc_id,
            "to": ["recipient32@test.com"],
            "subject": "Reopen Test",
            "body_text": "Original draft body text",
            "body_html": "<p>Original draft body text</p>",
            "signature_id": sig_id,
        },
    )
    assert draft_resp.status_code == 201
    draft_id = draft_resp.json()["id"]

    # Simulate close and reopen: GET the draft
    get_resp = await async_client.get(
        f"/api/v1/emails/drafts/{draft_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_resp.status_code == 200
    reopened_draft = get_resp.json()
    assert "Original draft body text" in reopened_draft["body_text"]
    assert "Desk Officer 32" in reopened_draft["body_text"]
    assert "Desk Officer 32" in reopened_draft["body_html"]

    # In Compose, reopened draft body contains the signature.
    # User edits more text and autosaves:
    edited_text = "Original draft body text with additions\n\n-- \nDesk Officer 32"
    edited_html = "<p>Original draft body text with additions</p><br><br><p>-- <br><b>Desk Officer 32</b></p>"
    update_resp = await async_client.put(
        f"/api/v1/emails/drafts/{draft_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "body_text": edited_text,
            "body_html": edited_html,
            "signature_id": sig_id,  # Even if signature_id is passed again
        },
    )
    assert update_resp.status_code == 200
    updated_data = update_resp.json()
    assert updated_data["body_text"].count("Desk Officer 32") == 1
    assert updated_data["body_html"].count("Desk Officer 32") == 1

    # Send the reopened draft and verify MIME
    captured_kwargs = {}

    def mock_send(*args, **kwargs):
        captured_kwargs.update(kwargs)

    with patch.object(SMTPClient, "send_email_sync", side_effect=mock_send):
        send_resp = await async_client.post(
            f"/api/v1/emails/drafts/{draft_id}/send",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert send_resp.status_code == 200

        mime_msg = captured_kwargs["message"]
        for part in mime_msg.walk():
            if part.get_content_type() == "text/plain":
                plain_part = part.get_content()
                assert "Original draft body text with additions" in plain_part
                assert plain_part.count("Desk Officer 32") == 1
            elif part.get_content_type() == "text/html":
                html_part = part.get_content()
                assert "Original draft body text with additions" in html_part
                assert html_part.count("Desk Officer 32") == 1


@pytest.mark.asyncio
async def test_33_template_plus_signature_in_draft_send(async_client: AsyncClient, db_session: AsyncSession):
    """33. Regression: Combining rich template HTML with a selected signature in a draft
    preserves template styling and appends the signature cleanly in sent MIME.
    """
    token = await register_and_login(async_client, "owner33@example.com")
    comp_id = await create_company_helper(async_client, token, "Draft Sig Corp 33")
    acc_id = await create_account_helper(async_client, token, comp_id, "Desk", "desk33@test.com")

    # Create Signature
    sig_resp = await async_client.post(
        "/api/v1/signatures",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Sig 33",
            "email_account_id": acc_id,
            "body_text": "-- \nEngineer 33",
            "body_html": "<p>-- <br><b>Engineer 33</b></p>",
            "is_default": False,
        },
    )
    sig_id = sig_resp.json()["id"]

    # Create HTML Template
    template_html = "<div style=\"background-color:#f0f4f8;padding:20px;\"><h2>Newsletter Update</h2><p>Welcome to our monthly digest!</p></div>"
    tmpl_resp = await async_client.post(
        "/api/v1/emails/templates",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Monthly Digest",
            "subject": "Monthly Digest",
            "body_html": template_html,
            "body_text": "Newsletter Update - Welcome to our monthly digest!",
        },
    )
    assert tmpl_resp.status_code == 201
    tmpl_id = tmpl_resp.json()["id"]

    # Create draft with template body and signature_id
    draft_resp = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "email_account_id": acc_id,
            "to": ["subscriber@test.com"],
            "subject": "Monthly Digest",
            "body_html": template_html,
            "body_text": "Newsletter Update - Welcome to our monthly digest!",
            "signature_id": sig_id,
        },
    )
    assert draft_resp.status_code == 201
    draft_data = draft_resp.json()
    draft_id = draft_data["id"]

    # Verify both template and signature exist in the draft
    assert "Newsletter Update" in draft_data["body_html"]
    assert "<b>Engineer 33</b>" in draft_data["body_html"]
    assert "Newsletter Update" in draft_data["body_text"]
    assert "-- \nEngineer 33" in draft_data["body_text"]

    # Send draft via SMTP and verify final MIME
    captured_kwargs = {}

    def mock_send(*args, **kwargs):
        captured_kwargs.update(kwargs)

    with patch.object(SMTPClient, "send_email_sync", side_effect=mock_send):
        send_resp = await async_client.post(
            f"/api/v1/emails/drafts/{draft_id}/send",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert send_resp.status_code == 200

        mime_msg = captured_kwargs["message"]
        for part in mime_msg.walk():
            if part.get_content_type() == "text/plain":
                plain_part = part.get_content()
                assert "Newsletter Update" in plain_part
                assert "-- \nEngineer 33" in plain_part
                assert plain_part.count("Engineer 33") == 1
            elif part.get_content_type() == "text/html":
                html_part = part.get_content()
                assert "Newsletter Update" in html_part
                assert "<b>Engineer 33</b>" in html_part
                assert html_part.count("Engineer 33") == 1


@pytest.mark.asyncio
async def test_34_default_signature_draft_autosave_lifecycle(async_client: AsyncClient, db_session: AsyncSession):
    """34. Comprehensive regression test for default signature during draft creation, autosave,
    account switching, explicit override, and MIME sending.
    """
    token = await register_and_login(async_client, "owner34@example.com")
    comp_id = await create_company_helper(async_client, token, "Draft Sig Corp 34")
    acc_a_id = await create_account_helper(async_client, token, comp_id, "Desk A", "desk_a@corp34.com")
    acc_b_id = await create_account_helper(async_client, token, comp_id, "Desk B", "desk_b@corp34.com")
    acc_c_id = await create_account_helper(async_client, token, comp_id, "Desk C", "desk_c@corp34.com")

    # Account A: Default Signature A
    sig_a_resp = await async_client.post(
        "/api/v1/signatures",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Default Sig A",
            "email_account_id": acc_a_id,
            "body_text": "-- \nSupport Team Alpha",
            "body_html": "<p>-- <br><b>Support Team Alpha</b></p>",
            "is_default": True,
        },
    )
    sig_a_id = sig_a_resp.json()["id"]

    # Account A: Explicit Secondary Signature (Non-default)
    sig_custom_resp = await async_client.post(
        "/api/v1/signatures",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Custom Sig A",
            "email_account_id": acc_a_id,
            "body_text": "-- \nExecutive Escort Alpha",
            "body_html": "<p>-- <br><b>Executive Escort Alpha</b></p>",
            "is_default": False,
        },
    )
    sig_custom_id = sig_custom_resp.json()["id"]

    # Account B: Default Signature B
    sig_b_resp = await async_client.post(
        "/api/v1/signatures",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Default Sig B",
            "email_account_id": acc_b_id,
            "body_text": "-- \nBilling Team Beta",
            "body_html": "<p>-- <br><b>Billing Team Beta</b></p>",
            "is_default": True,
        },
    )
    sig_b_id = sig_b_resp.json()["id"]

    # -------------------------------------------------------------------------
    # Test 1: Default signature applied during draft creation
    # -------------------------------------------------------------------------
    create_resp = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "email_account_id": acc_a_id,
            "to": ["client@example.com"],
            "subject": "Initial Discussion",
            "body_text": "Hello client,",
            "body_html": "<p>Hello client,</p>",
        },
    )
    assert create_resp.status_code == 201
    draft_data = create_resp.json()
    draft_id = draft_data["id"]
    assert "Hello client," in draft_data["body_text"]
    assert "-- \nSupport Team Alpha" in draft_data["body_text"]
    assert "<b>Support Team Alpha</b>" in draft_data["body_html"]

    # -------------------------------------------------------------------------
    # Test 2: Default signature survives draft update/autosave
    # -------------------------------------------------------------------------
    update_1 = await async_client.put(
        f"/api/v1/emails/drafts/{draft_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "body_text": "Hello client, here is paragraph 2.",
            "body_html": "<p>Hello client, here is paragraph 2.</p>",
        },
    )
    assert update_1.status_code == 200
    u1_data = update_1.json()
    assert "paragraph 2" in u1_data["body_text"]
    assert "-- \nSupport Team Alpha" in u1_data["body_text"]
    assert "<b>Support Team Alpha</b>" in u1_data["body_html"]

    # -------------------------------------------------------------------------
    # Test 3: Multiple draft updates do not duplicate default signature
    # -------------------------------------------------------------------------
    update_2 = await async_client.put(
        f"/api/v1/emails/drafts/{draft_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "body_text": "Hello client, here is paragraph 2 and 3.",
            "body_html": "<p>Hello client, here is paragraph 2 and 3.</p>",
        },
    )
    assert update_2.status_code == 200
    u2_data = update_2.json()
    assert u2_data["body_text"].count("Support Team Alpha") == 1
    assert u2_data["body_html"].count("Support Team Alpha") == 1

    # Metadata update
    update_3 = await async_client.put(
        f"/api/v1/emails/drafts/{draft_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"subject": "Updated Discussion Subject"},
    )
    assert update_3.status_code == 200
    u3_data = update_3.json()
    assert u3_data["subject"] == "Updated Discussion Subject"
    assert u3_data["body_text"].count("Support Team Alpha") == 1
    assert u3_data["body_html"].count("Support Team Alpha") == 1

    # -------------------------------------------------------------------------
    # Test 6: Sending draft after autosave contains default signature in MIME
    # -------------------------------------------------------------------------
    captured_kwargs = {}

    def mock_send(*args, **kwargs):
        captured_kwargs.update(kwargs)

    with patch.object(SMTPClient, "send_email_sync", side_effect=mock_send):
        send_resp = await async_client.post(
            f"/api/v1/emails/drafts/{draft_id}/send",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert send_resp.status_code == 200

        mime_msg = captured_kwargs["message"]
        for part in mime_msg.walk():
            if part.get_content_type() == "text/plain":
                plain_part = part.get_content()
                assert "Support Team Alpha" in plain_part
                assert plain_part.count("Support Team Alpha") == 1
            elif part.get_content_type() == "text/html":
                html_part = part.get_content()
                assert "Support Team Alpha" in html_part
                assert html_part.count("Support Team Alpha") == 1

    # -------------------------------------------------------------------------
    # Test 4: Explicit signature overrides default signature
    # -------------------------------------------------------------------------
    draft4_resp = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "email_account_id": acc_a_id,
            "to": ["vip@example.com"],
            "subject": "VIP Offer",
            "body_text": "VIP Content",
            "body_html": "<p>VIP Content</p>",
            "signature_id": sig_custom_id,
        },
    )
    assert draft4_resp.status_code == 201
    d4_data = draft4_resp.json()
    draft4_id = d4_data["id"]
    assert "Executive Escort Alpha" in d4_data["body_text"]
    assert "Support Team Alpha" not in d4_data["body_text"]

    d4_update = await async_client.put(
        f"/api/v1/emails/drafts/{draft4_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "body_text": "VIP Content updated",
            "body_html": "<p>VIP Content updated</p>",
            "signature_id": sig_custom_id,
        },
    )
    assert d4_update.status_code == 200
    d4_up_data = d4_update.json()
    assert d4_up_data["body_text"].count("Executive Escort Alpha") == 1
    assert "Support Team Alpha" not in d4_up_data["body_text"]

    # -------------------------------------------------------------------------
    # Test 5: No default + no explicit signature produces no signature
    # -------------------------------------------------------------------------
    draft5_resp = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "email_account_id": acc_c_id,
            "to": ["plain@example.com"],
            "subject": "Plain Message",
            "body_text": "Clean body without signature",
            "body_html": "<p>Clean body without signature</p>",
        },
    )
    assert draft5_resp.status_code == 201
    d5_data = draft5_resp.json()
    draft5_id = d5_data["id"]
    assert d5_data["body_text"] == "Clean body without signature"
    assert d5_data["body_html"] == "<p>Clean body without signature</p>"

    d5_update = await async_client.put(
        f"/api/v1/emails/drafts/{draft5_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "body_text": "Clean body updated",
            "body_html": "<p>Clean body updated</p>",
        },
    )
    assert d5_update.status_code == 200
    assert d5_update.json()["body_text"] == "Clean body updated"
    assert d5_update.json()["body_html"] == "<p>Clean body updated</p>"

    # -------------------------------------------------------------------------
    # Test 7: Switching email accounts uses the correct account default
    # -------------------------------------------------------------------------
    draft7_resp = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "email_account_id": acc_a_id,
            "to": ["partner@example.com"],
            "subject": "Switch Account Test",
            "body_text": "Message to be switched",
            "body_html": "<p>Message to be switched</p>",
        },
    )
    assert draft7_resp.status_code == 201
    draft7_id = draft7_resp.json()["id"]
    assert "Support Team Alpha" in draft7_resp.json()["body_text"]

    switch_resp = await async_client.put(
        f"/api/v1/emails/drafts/{draft7_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "email_account_id": acc_b_id,
            "body_text": "Message to be switched",
            "body_html": "<p>Message to be switched</p>",
        },
    )
    assert switch_resp.status_code == 200
    switch_data = switch_resp.json()
    assert switch_data["email_account_id"] == acc_b_id
    assert "Billing Team Beta" in switch_data["body_text"]
    assert "<b>Billing Team Beta</b>" in switch_data["body_html"]
    assert "Support Team Alpha" not in switch_data["body_text"]

    # -------------------------------------------------------------------------
    # Test 8: Unauthorized/wrong-account signature remains rejected on update
    # -------------------------------------------------------------------------
    bad_up = await async_client.put(
        f"/api/v1/emails/drafts/{draft7_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "signature_id": sig_a_id,
        },
    )
    assert bad_up.status_code == 400
    assert "Signature does not belong to this draft's email account" in bad_up.json()["detail"]


@pytest.mark.asyncio
async def test_35_copy_signature_authorization_isolation_idempotency_preservation(
    async_client: AsyncClient,
) -> None:
    """Test 35: Copy signature cross-account endpoint verifies:
    1. Authorized cross-account copy within same company succeeds.
    2. Idempotency: repeating copy returns identical existing signature without creating duplicates.
    3. Company isolation: copying to an account in another company returns HTTP 400.
    4. Member without access to target account: rejected with HTTP 403.
    5. Preserves existing default signature on target account.
    """
    # 1. Setup Company A with two accounts (acc_1, acc_2) and User Owner
    owner_email = "owner_copy@test.com"
    owner_token = await register_and_login(async_client, owner_email)
    comp_a_id = await create_company_helper(async_client, owner_token, "Copy Comp A")
    acc_1_id = await create_account_helper(async_client, owner_token, comp_a_id, "Acc 1", "acc1@compa.com")
    acc_2_id = await create_account_helper(async_client, owner_token, comp_a_id, "Acc 2", "acc2@compa.com")

    # Set existing default signature on acc_2 to test preservation
    sig_existing_resp = await async_client.post(
        "/api/v1/signatures",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "email_account_id": acc_2_id,
            "name": "Existing Account 2 Default",
            "body_text": "Acc 2 Original Signature",
            "is_default": True,
        },
    )
    assert sig_existing_resp.status_code == 201
    existing_sig_2_id = sig_existing_resp.json()["id"]

    # Create source signature on acc_1
    sig_src_resp = await async_client.post(
        "/api/v1/signatures",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "email_account_id": acc_1_id,
            "name": "Sales Official",
            "body_text": "Dipak Odhavani - Sales",
            "body_html": "<b>Dipak Odhavani - Sales</b>",
            "is_default": True,
        },
    )
    assert sig_src_resp.status_code == 201
    src_sig_id = sig_src_resp.json()["id"]

    # 2. Test Success & Preservation: Copy to acc_2 without make_default
    copy_resp = await async_client.post(
        f"/api/v1/signatures/{src_sig_id}/copy",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "target_email_account_id": acc_2_id,
            "make_default": False,
        },
    )
    assert copy_resp.status_code == 201
    copied_data = copy_resp.json()
    assert copied_data["email_account_id"] == acc_2_id
    assert copied_data["name"] == "Sales Official"
    assert copied_data["is_default"] is False  # Preserved!

    # Verify acc_2 default is still existing_sig_2_id
    acc2_default = await async_client.get(
        f"/api/v1/signatures/default?email_account_id={acc_2_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert acc2_default.status_code == 200
    assert acc2_default.json()["id"] == existing_sig_2_id

    # 3. Test Idempotency: copying again returns the exact same signature without creating duplicate
    copy_again_resp = await async_client.post(
        f"/api/v1/signatures/{src_sig_id}/copy",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"target_email_account_id": acc_2_id},
    )
    assert copy_again_resp.status_code == 201
    assert copy_again_resp.json()["id"] == copied_data["id"]

    # Verify list for acc_2 has exactly 2 signatures (original default + copied one), not 3
    list_acc2 = await async_client.get(
        f"/api/v1/signatures?email_account_id={acc_2_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert list_acc2.status_code == 200
    assert len(list_acc2.json()["signatures"]) == 2

    # 4. Test Cross-Company Isolation: attempt copying to account in Company B
    comp_b_id = await create_company_helper(async_client, owner_token, "Copy Comp B")
    acc_b_id = await create_account_helper(async_client, owner_token, comp_b_id, "Acc B", "acc@compb.com")

    cross_resp = await async_client.post(
        f"/api/v1/signatures/{src_sig_id}/copy",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"target_email_account_id": acc_b_id},
    )
    assert cross_resp.status_code == 400
    assert "different company" in cross_resp.json()["detail"].lower()

    # 5. Test Authorization: member without access to target account
    member_email = "member_copy@test.com"
    member_token = await register_and_login(async_client, member_email)
    member_user_id = await add_company_member_helper(async_client, owner_token, comp_a_id, member_email, "MEMBER")
    # Grant access only to acc_1, not acc_2
    await grant_account_access_helper(async_client, owner_token, comp_a_id, acc_1_id, member_user_id)

    unauth_resp = await async_client.post(
        f"/api/v1/signatures/{src_sig_id}/copy",
        headers={"Authorization": f"Bearer {member_token}"},
        json={"target_email_account_id": acc_2_id},
    )
    assert unauth_resp.status_code == 403

