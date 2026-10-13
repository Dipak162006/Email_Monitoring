import io
from httpx import AsyncClient
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.campaigns.models import Campaign, CampaignRecipient, CampaignStatus


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


async def create_company_helper(client: AsyncClient, token: str, name: str = "Recipient Co") -> int:
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
    email_address: str = "sender@recipient-test.com",
) -> int:
    """Create an active email account under a company and return its ID."""
    resp = await client.post(
        f"/api/v1/companies/{company_id}/email-accounts",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Sender Account",
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


async def create_draft_campaign_helper(
    client: AsyncClient,
    token: str,
    company_id: int,
    account_id: int,
    name: str = "Test Campaign",
) -> int:
    """Create a draft campaign and return its ID."""
    resp = await client.post(
        f"/api/v1/companies/{company_id}/campaigns",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": name, "email_account_id": account_id, "subject": "Subject"},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


# =============================================================================
# 1. Basic Recipient CRUD Tests
# =============================================================================

@pytest.mark.asyncio
async def test_add_and_get_single_recipient(async_client: AsyncClient):
    """Test adding a single recipient and retrieving their details."""
    token = await register_and_login(async_client, "owner_recip_crud@co.com", "Owner Recip")
    company_id = await create_company_helper(async_client, token, "Recip Co")
    account_id = await create_email_account_helper(async_client, token, company_id)
    campaign_id = await create_draft_campaign_helper(async_client, token, company_id, account_id)

    # 1. Add single recipient
    payload = {
        "email": " alice.smith@example.com ",
        "first_name": "Alice",
        "last_name": "Smith",
        "custom_variables": {"tier": "gold", "discount": 20},
    }
    resp = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/recipients",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"] is not None
    assert data["campaign_id"] == campaign_id
    assert data["email"] == "alice.smith@example.com"  # Normalized lowercase + trimmed
    assert data["first_name"] == "Alice"
    assert data["last_name"] == "Smith"
    assert data["custom_variables"] == {"tier": "gold", "discount": 20}
    assert data["status"] == "PENDING"
    recip_id = data["id"]

    # 2. Get recipient detail
    get_resp = await async_client.get(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/recipients/{recip_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == recip_id
    assert get_resp.json()["email"] == "alice.smith@example.com"

    # 3. Campaign detail reflects recipient_count = 1
    camp_resp = await async_client.get(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert camp_resp.status_code == 200
    assert camp_resp.json()["recipient_count"] == 1


@pytest.mark.asyncio
async def test_list_recipients_pagination_and_search(async_client: AsyncClient):
    """Test listing recipients with pagination, search, and status filtering."""
    token = await register_and_login(async_client, "owner_list_recip@co.com", "Owner List")
    company_id = await create_company_helper(async_client, token, "List Recip Co")
    account_id = await create_email_account_helper(async_client, token, company_id)
    campaign_id = await create_draft_campaign_helper(async_client, token, company_id, account_id)

    # Add 5 recipients
    for i in range(5):
        await async_client.post(
            f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/recipients",
            headers={"Authorization": f"Bearer {token}"},
            json={"email": f"user{i}@example.com", "first_name": f"User{i}"},
        )

    # 1. List all
    list_resp = await async_client.get(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/recipients",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_resp.status_code == 200
    recips = list_resp.json()
    assert len(recips) == 5

    # 2. Pagination: limit=2, offset=2
    page_resp = await async_client.get(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/recipients?limit=2&offset=2",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert page_resp.status_code == 200
    assert len(page_resp.json()) == 2

    # 3. Substring search on email
    search_resp = await async_client.get(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/recipients?search=user3",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert search_resp.status_code == 200
    assert len(search_resp.json()) == 1
    assert search_resp.json()[0]["email"] == "user3@example.com"

    # 4. Status filter
    status_resp = await async_client.get(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/recipients?status=PENDING",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert status_resp.status_code == 200
    assert len(status_resp.json()) == 5


@pytest.mark.asyncio
async def test_update_and_delete_recipient(async_client: AsyncClient):
    """Test updating and deleting a recipient in a DRAFT campaign."""
    token = await register_and_login(async_client, "owner_up_del@co.com", "Owner UpDel")
    company_id = await create_company_helper(async_client, token, "UpDel Co")
    account_id = await create_email_account_helper(async_client, token, company_id)
    campaign_id = await create_draft_campaign_helper(async_client, token, company_id, account_id)

    # Create recipient
    recip_id = (await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/recipients",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "original@example.com", "first_name": "Original"},
    )).json()["id"]

    # 1. Update recipient fields
    patch_resp = await async_client.patch(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/recipients/{recip_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "updated@example.com", "first_name": "Updated", "last_name": "Person"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["email"] == "updated@example.com"
    assert patch_resp.json()["first_name"] == "Updated"
    assert patch_resp.json()["last_name"] == "Person"

    # 2. Delete recipient
    del_resp = await async_client.delete(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/recipients/{recip_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_resp.status_code == 204

    # 3. Verify recipient is gone -> 404
    get_resp = await async_client.get(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/recipients/{recip_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_resp.status_code == 404


# =============================================================================
# 2. Normalization & Validation Tests
# =============================================================================

@pytest.mark.asyncio
async def test_email_normalization_and_validation_rejections(async_client: AsyncClient):
    """Test that email addresses are properly normalized and invalid formats are rejected."""
    token = await register_and_login(async_client, "owner_norm@co.com", "Owner Norm")
    company_id = await create_company_helper(async_client, token, "Norm Co")
    account_id = await create_email_account_helper(async_client, token, company_id)
    campaign_id = await create_draft_campaign_helper(async_client, token, company_id, account_id)

    # 1. Mixed case and whitespace normalized
    resp_norm = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/recipients",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "  USER.NAME+tag@EXAMPLE.COM  "},
    )
    assert resp_norm.status_code == 201
    assert resp_norm.json()["email"] == "user.name+tag@example.com"

    # 2. Invalid syntax: missing domain dot
    resp_bad1 = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/recipients",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "invalid@domain"},
    )
    assert resp_bad1.status_code == 422

    # 3. Invalid syntax: bare string
    resp_bad2 = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/recipients",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "not-an-email"},
    )
    assert resp_bad2.status_code == 422

    # 4. Empty string
    resp_bad3 = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/recipients",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "   "},
    )
    assert resp_bad3.status_code == 422


# =============================================================================
# 3. Deduplication Tests
# =============================================================================

@pytest.mark.asyncio
async def test_single_and_bulk_deduplication(async_client: AsyncClient):
    """Test duplicate rejection for single additions and batch deduplication for bulk."""
    token = await register_and_login(async_client, "owner_dedup@co.com", "Owner Dedup")
    company_id = await create_company_helper(async_client, token, "Dedup Co")
    account_id = await create_email_account_helper(async_client, token, company_id)
    campaign_id = await create_draft_campaign_helper(async_client, token, company_id, account_id)

    # 1. Add single recipient
    await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/recipients",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "target@example.com"},
    )

    # 2. Attempt adding exact same email with different casing/whitespace -> 409 Conflict
    resp_dup = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/recipients",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "  TARGET@EXAMPLE.COM  "},
    )
    assert resp_dup.status_code == 409
    assert "already exists" in resp_dup.json()["detail"].lower()

    # 3. Bulk creation with intra-batch duplicate AND already-existing DB duplicate
    bulk_payload = {
        "recipients": [
            {"email": "TARGET@example.com", "first_name": "Already in DB"},
            {"email": "new1@example.com", "first_name": "First New"},
            {"email": "NEW1@example.com", "first_name": "Intra-batch duplicate"},
            {"email": "new2@example.com", "first_name": "Second New"},
        ]
    }
    resp_bulk = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/recipients/bulk",
        headers={"Authorization": f"Bearer {token}"},
        json=bulk_payload,
    )
    assert resp_bulk.status_code == 201
    bulk_data = resp_bulk.json()
    assert bulk_data["total_submitted"] == 4
    assert bulk_data["inserted_count"] == 2  # new1 and new2
    assert bulk_data["skipped_count"] == 2  # target@ and duplicate new1@
    assert "target@example.com" in bulk_data["skipped_emails"]
    assert "new1@example.com" in bulk_data["skipped_emails"]


# =============================================================================
# 4. CSV Import Tests
# =============================================================================

@pytest.mark.asyncio
async def test_csv_recipient_import(async_client: AsyncClient):
    """Test importing recipients via CSV file upload, checking duplicates, syntax errors, and empty files."""
    token = await register_and_login(async_client, "owner_csv@co.com", "Owner CSV")
    company_id = await create_company_helper(async_client, token, "CSV Co")
    account_id = await create_email_account_helper(async_client, token, company_id)
    campaign_id = await create_draft_campaign_helper(async_client, token, company_id, account_id)

    # Seed one recipient directly
    await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/recipients",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "existing@example.com"},
    )

    # 1. Valid CSV with duplicates and an invalid row
    csv_text = """email,first_name,last_name,custom_variables
valid1@example.com,John,Doe,"{""tag"": ""lead""}"
EXISTING@example.com,Pre,Existing,
valid2@example.com,Jane,Smith,
VALID1@EXAMPLE.COM,Duplicate,John,
invalid-email-address,Bad,Format,
valid3@example.com,Bob,Taylor,
"""
    files = {"file": ("recipients.csv", csv_text.encode("utf-8"), "text/csv")}
    resp = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/recipients/import",
        headers={"Authorization": f"Bearer {token}"},
        files=files,
    )
    assert resp.status_code == 200
    report = resp.json()
    assert report["inserted_count"] == 3  # valid1, valid2, valid3
    assert report["skipped_duplicates_count"] == 2  # existing@ and duplicate valid1@
    assert report["invalid_rows_count"] == 1  # invalid-email-address
    assert "existing@example.com" in report["skipped_emails"]
    assert "valid1@example.com" in report["skipped_emails"]

    # 2. Empty CSV -> 400 Bad Request
    empty_files = {"file": ("empty.csv", b"", "text/csv")}
    resp_empty = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/recipients/import",
        headers={"Authorization": f"Bearer {token}"},
        files=empty_files,
    )
    assert resp_empty.status_code == 400
    assert "empty" in resp_empty.json()["detail"].lower()

    # 3. CSV missing email column header -> 400 Bad Request
    no_email_csv = """name,company
Alice,Acme Corp
"""
    no_email_files = {"file": ("no_email.csv", no_email_csv.encode("utf-8"), "text/csv")}
    resp_no_email = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/recipients/import",
        headers={"Authorization": f"Bearer {token}"},
        files=no_email_files,
    )
    assert resp_no_email.status_code == 400
    assert "email" in resp_no_email.json()["detail"].lower()


# =============================================================================
# 5. Authorization Tests
# =============================================================================

@pytest.mark.asyncio
async def test_recipient_authorization_roles(async_client: AsyncClient):
    """Test role permissions: MEMBER can view; MEMBER cannot mutate (create/update/delete/import)."""
    owner_token = await register_and_login(async_client, "owner_recip_auth@co.com", "Owner Auth")
    company_id = await create_company_helper(async_client, owner_token, "Recip Auth Co")
    account_id = await create_email_account_helper(async_client, owner_token, company_id)
    campaign_id = await create_draft_campaign_helper(async_client, owner_token, company_id, account_id)

    member_token = await register_and_login(async_client, "member_recip_auth@co.com", "Member Auth")
    await add_company_member_helper(async_client, owner_token, company_id, "member_recip_auth@co.com", role="MEMBER")

    # Owner adds a recipient
    recip_id = (await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/recipients",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"email": "member_view@example.com"},
    )).json()["id"]

    # 1. Member can view list -> 200
    m_list = await async_client.get(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/recipients",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert m_list.status_code == 200
    assert len(m_list.json()) == 1

    # 2. Member can view detail -> 200
    m_get = await async_client.get(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/recipients/{recip_id}",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert m_get.status_code == 200

    # 3. Member cannot create recipient -> 403 Forbidden
    m_create = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/recipients",
        headers={"Authorization": f"Bearer {member_token}"},
        json={"email": "forbidden@example.com"},
    )
    assert m_create.status_code == 403

    # 4. Member cannot update recipient -> 403 Forbidden
    m_update = await async_client.patch(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/recipients/{recip_id}",
        headers={"Authorization": f"Bearer {member_token}"},
        json={"first_name": "Hacked"},
    )
    assert m_update.status_code == 403

    # 5. Member cannot delete recipient -> 403 Forbidden
    m_del = await async_client.delete(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/recipients/{recip_id}",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert m_del.status_code == 403

    # 6. Member cannot import CSV -> 403 Forbidden
    files = {"file": ("recip.csv", b"email\ntest@co.com\n", "text/csv")}
    m_import = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/recipients/import",
        headers={"Authorization": f"Bearer {member_token}"},
        files=files,
    )
    assert m_import.status_code == 403


# =============================================================================
# 6. Tenant and Campaign Isolation Tests
# =============================================================================

@pytest.mark.asyncio
async def test_tenant_and_campaign_isolation_anti_enumeration(async_client: AsyncClient):
    """Test that cross-company or cross-campaign recipient access returns 404 anti-enumeration."""
    token_a = await register_and_login(async_client, "owner_iso_a@co.com", "Owner Iso A")
    company_a_id = await create_company_helper(async_client, token_a, "Iso Co A")
    account_a_id = await create_email_account_helper(async_client, token_a, company_a_id, "a@co.com")
    camp_a1 = await create_draft_campaign_helper(async_client, token_a, company_a_id, account_a_id, "Camp A1")
    camp_a2 = await create_draft_campaign_helper(async_client, token_a, company_a_id, account_a_id, "Camp A2")

    token_b = await register_and_login(async_client, "owner_iso_b@co.com", "Owner Iso B")
    company_b_id = await create_company_helper(async_client, token_b, "Iso Co B")

    # Recipient in Campaign A1
    recip_a1 = (await async_client.post(
        f"/api/v1/companies/{company_a_id}/campaigns/{camp_a1}/recipients",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"email": "a1@example.com"},
    )).json()["id"]

    # 1. Cross-company access: Company B tries to access Campaign A1's recipient -> 404
    resp_cross_co = await async_client.get(
        f"/api/v1/companies/{company_b_id}/campaigns/{camp_a1}/recipients/{recip_a1}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp_cross_co.status_code == 404

    # 2. Cross-campaign access within same company: Accessing recip_a1 through camp_a2 route -> 404
    resp_cross_camp = await async_client.get(
        f"/api/v1/companies/{company_a_id}/campaigns/{camp_a2}/recipients/{recip_a1}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp_cross_camp.status_code == 404

    # 3. Cross-campaign mutation rejection: Updating recip_a1 through camp_a2 route -> 404
    resp_cross_patch = await async_client.patch(
        f"/api/v1/companies/{company_a_id}/campaigns/{camp_a2}/recipients/{recip_a1}",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"first_name": "Invalid"},
    )
    assert resp_cross_patch.status_code == 404


# =============================================================================
# 7. Campaign State Safety Tests
# =============================================================================

@pytest.mark.asyncio
async def test_campaign_state_safety_rejects_mutations_outside_draft(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Test that adding, updating, deleting, or importing recipients is rejected when campaign is not DRAFT."""
    token = await register_and_login(async_client, "owner_state_safe@co.com", "Owner StateSafe")
    company_id = await create_company_helper(async_client, token, "StateSafe Co")
    account_id = await create_email_account_helper(async_client, token, company_id)
    campaign_id = await create_draft_campaign_helper(async_client, token, company_id, account_id)

    # Add recipient while DRAFT
    recip_id = (await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/recipients",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "stable@example.com"},
    )).json()["id"]

    # Transition campaign to SCHEDULED, QUEUED, RUNNING, PAUSED in DB
    for non_draft_status in [
        CampaignStatus.SCHEDULED.value,
        CampaignStatus.QUEUED.value,
        CampaignStatus.RUNNING.value,
        CampaignStatus.PAUSED.value,
    ]:
        camp_obj = (await db_session.execute(select(Campaign).where(Campaign.id == campaign_id))).scalar_one()
        camp_obj.status = non_draft_status
        await db_session.commit()

        # Reject add
        r_add = await async_client.post(
            f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/recipients",
            headers={"Authorization": f"Bearer {token}"},
            json={"email": f"fail_{non_draft_status}@example.com"},
        )
        assert r_add.status_code == 400
        assert "only be modified when campaign is in draft" in r_add.json()["detail"].lower()

        # Reject update
        r_up = await async_client.patch(
            f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/recipients/{recip_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"first_name": "Change"},
        )
        assert r_up.status_code == 400

        # Reject delete
        r_del = await async_client.delete(
            f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/recipients/{recip_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r_del.status_code == 400

        # Reject import
        files = {"file": ("imp.csv", b"email\nfail@example.com\n", "text/csv")}
        r_imp = await async_client.post(
            f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/recipients/import",
            headers={"Authorization": f"Bearer {token}"},
            files=files,
        )
        assert r_imp.status_code == 400


# =============================================================================
# 8. Status Protection Tests
# =============================================================================

@pytest.mark.asyncio
async def test_recipient_status_is_read_only_via_crud(async_client: AsyncClient):
    """Test that recipient status is strictly PENDING on creation and cannot be patched directly."""
    token = await register_and_login(async_client, "owner_status_safe@co.com", "Owner StatusSafe")
    company_id = await create_company_helper(async_client, token, "StatusSafe Co")
    account_id = await create_email_account_helper(async_client, token, company_id)
    campaign_id = await create_draft_campaign_helper(async_client, token, company_id, account_id)

    # 1. Create with attempt to override status in payload -> rejected by extra forbid or ignored
    resp_create = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/recipients",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "status_check@example.com", "status": "SENT"},
    )
    assert resp_create.status_code == 422

    # Normal create
    recip_id = (await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/recipients",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "status_check@example.com"},
    )).json()["id"]

    # 2. Patch attempt with status -> 422 Unprocessable Entity
    resp_patch = await async_client.patch(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/recipients/{recip_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"status": "SENT"},
    )
    assert resp_patch.status_code == 422
