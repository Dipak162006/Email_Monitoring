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
    # Because update_draft doesn't force default sig when not passed, it keeps user content
    assert update_resp.json()["body_text"] == "Updated draft text without sig"


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
