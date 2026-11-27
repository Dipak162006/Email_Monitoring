import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.campaigns.models import Campaign, CampaignRecipient, CampaignStatus
from app.modules.email_accounts.models import EmailAccount
from app.modules.recipient_lists.models import RecipientList, RecipientListMember


# =============================================================================
# Helper Utilities
# =============================================================================

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
    assert resp.status_code == 201
    return resp.json()["id"]


async def add_company_member_helper(
    client: AsyncClient,
    token_owner: str,
    company_id: int,
    email: str,
    role: str = "MEMBER",
) -> None:
    """Helper to add a user to a company with an assigned role."""
    resp = await client.post(
        f"/api/v1/companies/{company_id}/members",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"email": email, "role": role},
    )
    assert resp.status_code == 201


# =============================================================================
# 1. Recipient List CRUD Operations Tests
# =============================================================================

@pytest.mark.asyncio
async def test_create_recipient_list(async_client: AsyncClient):
    token = await register_and_login(async_client, "owner_rl@test.com", "Owner RL")
    company_id = await create_company_helper(async_client, token, "RL Co")

    resp = await async_client.post(
        f"/api/v1/companies/{company_id}/recipient-lists",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Tech Founders Q1", "description": "Key prospects in tech"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Tech Founders Q1"
    assert data["description"] == "Key prospects in tech"
    assert data["company_id"] == company_id
    assert data["recipient_count"] == 0
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data


@pytest.mark.asyncio
async def test_create_recipient_list_duplicate_name_rejected(async_client: AsyncClient):
    token = await register_and_login(async_client, "owner_dup@test.com")
    company_id = await create_company_helper(async_client, token, "Dup List Co")

    resp1 = await async_client.post(
        f"/api/v1/companies/{company_id}/recipient-lists",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Venture Capitalists"},
    )
    assert resp1.status_code == 201

    # Second creation with identical name in the same company must fail with 409 Conflict
    resp2 = await async_client.post(
        f"/api/v1/companies/{company_id}/recipient-lists",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Venture Capitalists"},
    )
    assert resp2.status_code == 409
    assert "already exists" in resp2.json()["detail"]


@pytest.mark.asyncio
async def test_list_recipient_lists_pagination_and_search(async_client: AsyncClient):
    token = await register_and_login(async_client, "owner_list@test.com")
    company_id = await create_company_helper(async_client, token, "Pagination Co")

    # Create 3 lists
    for name, desc in [
        ("Alpha Group", "Engineers"),
        ("Beta Group", "Product managers"),
        ("Gamma Group", "Designers"),
    ]:
        await async_client.post(
            f"/api/v1/companies/{company_id}/recipient-lists",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": name, "description": desc},
        )

    # Test list without search
    resp = await async_client.get(
        f"/api/v1/companies/{company_id}/recipient-lists?limit=2&offset=0",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert len(data["items"]) == 2
    assert data["limit"] == 2
    assert data["offset"] == 0

    # Test search by name
    search_resp = await async_client.get(
        f"/api/v1/companies/{company_id}/recipient-lists?search=Beta",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert search_resp.status_code == 200
    search_data = search_resp.json()
    assert search_data["total"] == 1
    assert search_data["items"][0]["name"] == "Beta Group"

    # Test search by description
    desc_search = await async_client.get(
        f"/api/v1/companies/{company_id}/recipient-lists?search=Designers",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert desc_search.status_code == 200
    assert desc_search.json()["total"] == 1
    assert desc_search.json()["items"][0]["name"] == "Gamma Group"


@pytest.mark.asyncio
async def test_get_and_update_recipient_list(async_client: AsyncClient):
    token = await register_and_login(async_client, "owner_upd@test.com")
    company_id = await create_company_helper(async_client, token, "Update Co")

    create_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/recipient-lists",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Initial Name", "description": "Initial Desc"},
    )
    list_id = create_resp.json()["id"]

    # Get single list
    get_resp = await async_client.get(
        f"/api/v1/companies/{company_id}/recipient-lists/{list_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == "Initial Name"

    # Update list
    patch_resp = await async_client.patch(
        f"/api/v1/companies/{company_id}/recipient-lists/{list_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Updated Name", "description": "Updated Desc"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["name"] == "Updated Name"
    assert patch_resp.json()["description"] == "Updated Desc"


@pytest.mark.asyncio
async def test_delete_recipient_list(async_client: AsyncClient):
    token = await register_and_login(async_client, "owner_del@test.com")
    company_id = await create_company_helper(async_client, token, "Delete Co")

    create_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/recipient-lists",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "To Be Deleted"},
    )
    list_id = create_resp.json()["id"]

    # Add a member
    await async_client.post(
        f"/api/v1/companies/{company_id}/recipient-lists/{list_id}/members",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "member_del@example.com"},
    )

    # Delete list
    del_resp = await async_client.delete(
        f"/api/v1/companies/{company_id}/recipient-lists/{list_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_resp.status_code == 204

    # Verify 404 after deletion
    get_resp = await async_client.get(
        f"/api/v1/companies/{company_id}/recipient-lists/{list_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_resp.status_code == 404


# =============================================================================
# 2. Member Operations Tests
# =============================================================================

@pytest.mark.asyncio
async def test_add_and_get_members(async_client: AsyncClient):
    token = await register_and_login(async_client, "owner_mem@test.com")
    company_id = await create_company_helper(async_client, token, "Members Co")

    list_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/recipient-lists",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "VIP Customers"},
    )
    list_id = list_resp.json()["id"]

    # Add Member
    add_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/recipient-lists/{list_id}/members",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "alice@company.org", "first_name": "Alice", "last_name": "Smith"},
    )
    assert add_resp.status_code == 201
    member_data = add_resp.json()
    assert member_data["email"] == "alice@company.org"
    assert member_data["first_name"] == "Alice"
    assert member_data["last_name"] == "Smith"
    member_id = member_data["id"]

    # Check that recipient_count on the list is now 1
    get_list_resp = await async_client.get(
        f"/api/v1/companies/{company_id}/recipient-lists/{list_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_list_resp.json()["recipient_count"] == 1

    # Get single member
    get_mem_resp = await async_client.get(
        f"/api/v1/companies/{company_id}/recipient-lists/{list_id}/members/{member_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_mem_resp.status_code == 200
    assert get_mem_resp.json()["email"] == "alice@company.org"


@pytest.mark.asyncio
async def test_update_and_remove_member(async_client: AsyncClient):
    token = await register_and_login(async_client, "owner_upd_mem@test.com")
    company_id = await create_company_helper(async_client, token, "Member Update Co")

    list_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/recipient-lists",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Prospects"},
    )
    list_id = list_resp.json()["id"]

    add_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/recipient-lists/{list_id}/members",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "bob@old.com", "first_name": "Bob"},
    )
    member_id = add_resp.json()["id"]

    # Update member email and last name
    patch_resp = await async_client.patch(
        f"/api/v1/companies/{company_id}/recipient-lists/{list_id}/members/{member_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "bob@new.com", "last_name": "Jones"},
    )
    assert patch_resp.status_code == 200
    updated_data = patch_resp.json()
    assert updated_data["email"] == "bob@new.com"
    assert updated_data["first_name"] == "Bob"
    assert updated_data["last_name"] == "Jones"

    # Remove member
    del_resp = await async_client.delete(
        f"/api/v1/companies/{company_id}/recipient-lists/{list_id}/members/{member_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_resp.status_code == 204

    # Verify 404 after deletion
    get_resp = await async_client.get(
        f"/api/v1/companies/{company_id}/recipient-lists/{list_id}/members/{member_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_resp.status_code == 404


# =============================================================================
# 3. Validation and Duplicates Handling Tests
# =============================================================================

@pytest.mark.asyncio
async def test_email_validation_and_normalization(async_client: AsyncClient):
    token = await register_and_login(async_client, "owner_norm@test.com")
    company_id = await create_company_helper(async_client, token, "Norm Co")

    list_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/recipient-lists",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Normalization Test List"},
    )
    list_id = list_resp.json()["id"]

    # Missing email field -> 422
    resp_missing = await async_client.post(
        f"/api/v1/companies/{company_id}/recipient-lists/{list_id}/members",
        headers={"Authorization": f"Bearer {token}"},
        json={"first_name": "NoEmail"},
    )
    assert resp_missing.status_code == 422

    # Invalid email format -> 422
    resp_invalid = await async_client.post(
        f"/api/v1/companies/{company_id}/recipient-lists/{list_id}/members",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "not-an-email"},
    )
    assert resp_invalid.status_code == 422

    # Normalization check: uppercase and leading/trailing whitespace
    resp_norm = await async_client.post(
        f"/api/v1/companies/{company_id}/recipient-lists/{list_id}/members",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "   User.Normalized@Example.COM   ", "first_name": "  User  "},
    )
    assert resp_norm.status_code == 201
    norm_data = resp_norm.json()
    assert norm_data["email"] == "user.normalized@example.com"
    assert norm_data["first_name"] == "User"

    # Duplicate rejection with case variation -> 409
    resp_dup = await async_client.post(
        f"/api/v1/companies/{company_id}/recipient-lists/{list_id}/members",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "USER.NORMALIZED@example.com"},
    )
    assert resp_dup.status_code == 409
    assert "already exists" in resp_dup.json()["detail"]


@pytest.mark.asyncio
async def test_same_email_in_different_lists_allowed(async_client: AsyncClient):
    token = await register_and_login(async_client, "owner_multi@test.com")
    company_id = await create_company_helper(async_client, token, "Multi List Co")

    l1 = (await async_client.post(
        f"/api/v1/companies/{company_id}/recipient-lists",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "List 1"},
    )).json()["id"]

    l2 = (await async_client.post(
        f"/api/v1/companies/{company_id}/recipient-lists",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "List 2"},
    )).json()["id"]

    # Same email in List 1 and List 2 should succeed
    r1 = await async_client.post(
        f"/api/v1/companies/{company_id}/recipient-lists/{l1}/members",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "contact@crosslist.com"},
    )
    assert r1.status_code == 201

    r2 = await async_client.post(
        f"/api/v1/companies/{company_id}/recipient-lists/{l2}/members",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "contact@crosslist.com"},
    )
    assert r2.status_code == 201


# =============================================================================
# 4. Tenant Isolation and Role Security Tests
# =============================================================================

@pytest.mark.asyncio
async def test_tenant_isolation_cross_tenant_access_denied(async_client: AsyncClient):
    token1 = await register_and_login(async_client, "tenant1@test.com")
    c1 = await create_company_helper(async_client, token1, "Tenant 1 Co")

    token2 = await register_and_login(async_client, "tenant2@test.com")
    c2 = await create_company_helper(async_client, token2, "Tenant 2 Co")

    # Tenant 1 creates a list
    list1_resp = await async_client.post(
        f"/api/v1/companies/{c1}/recipient-lists",
        headers={"Authorization": f"Bearer {token1}"},
        json={"name": "Secret List C1"},
    )
    list1_id = list1_resp.json()["id"]

    # Add member to Tenant 1 list
    await async_client.post(
        f"/api/v1/companies/{c1}/recipient-lists/{list1_id}/members",
        headers={"Authorization": f"Bearer {token1}"},
        json={"email": "c1_member@tenant1.com"},
    )

    # Tenant 2 tries to GET Tenant 1 list -> 404 (anti-enumeration)
    resp_cross_get = await async_client.get(
        f"/api/v1/companies/{c2}/recipient-lists/{list1_id}",
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert resp_cross_get.status_code == 404

    # Tenant 2 tries to PATCH Tenant 1 list -> 404
    resp_cross_patch = await async_client.patch(
        f"/api/v1/companies/{c2}/recipient-lists/{list1_id}",
        headers={"Authorization": f"Bearer {token2}"},
        json={"name": "Hacked Name"},
    )
    assert resp_cross_patch.status_code == 404

    # Tenant 2 tries to DELETE Tenant 1 list -> 404
    resp_cross_del = await async_client.delete(
        f"/api/v1/companies/{c2}/recipient-lists/{list1_id}",
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert resp_cross_del.status_code == 404

    # Tenant 2 tries to access Tenant 1 members -> 404
    resp_cross_members = await async_client.get(
        f"/api/v1/companies/{c2}/recipient-lists/{list1_id}/members",
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert resp_cross_members.status_code == 404

    # Tenant 2 tries to access Tenant 1 company endpoint directly with Tenant 2 token -> 404/403
    resp_wrong_company = await async_client.get(
        f"/api/v1/companies/{c1}/recipient-lists",
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert resp_wrong_company.status_code in [403, 404]


@pytest.mark.asyncio
async def test_role_authorization_member_cannot_modify(async_client: AsyncClient):
    owner_token = await register_and_login(async_client, "owner_role@test.com")
    company_id = await create_company_helper(async_client, owner_token, "Role Test Co")

    member_token = await register_and_login(async_client, "regular_member@test.com")
    await add_company_member_helper(
        async_client,
        owner_token,
        company_id,
        "regular_member@test.com",
        role="MEMBER",
    )

    # Owner creates list
    list_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/recipient-lists",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"name": "Owner Created List"},
    )
    list_id = list_resp.json()["id"]

    # Regular MEMBER cannot create lists -> 403 Forbidden
    member_create_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/recipient-lists",
        headers={"Authorization": f"Bearer {member_token}"},
        json={"name": "Unauthorized List"},
    )
    assert member_create_resp.status_code == 403

    # Regular MEMBER can read lists -> 200 OK
    member_read_resp = await async_client.get(
        f"/api/v1/companies/{company_id}/recipient-lists",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert member_read_resp.status_code == 200

    # Regular MEMBER cannot delete list -> 403 Forbidden
    member_del_resp = await async_client.delete(
        f"/api/v1/companies/{company_id}/recipient-lists/{list_id}",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert member_del_resp.status_code == 403


# =============================================================================
# 5. Data Safety & Campaign Independence Tests
# =============================================================================

@pytest.mark.asyncio
async def test_list_and_member_deletion_does_not_affect_campaign_recipients(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    token = await register_and_login(async_client, "owner_safety@test.com")
    company_id = await create_company_helper(async_client, token, "Safety Co")

    # 1. Create a recipient list and member
    list_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/recipient-lists",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Audience Source"},
    )
    list_id = list_resp.json()["id"]

    mem_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/recipient-lists/{list_id}/members",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "lead@customer.com", "first_name": "Lead", "last_name": "One"},
    )
    member_id = mem_resp.json()["id"]

    # 2. Setup an email account and draft campaign directly in DB
    email_acc = EmailAccount(
        company_id=company_id,
        name="Sender Account",
        email_address="sender@safety.com",
        smtp_host="smtp.safety.com",
        smtp_port=587,
        smtp_username="sender",
        smtp_password_encrypted="enc_password",
    )
    db_session.add(email_acc)
    await db_session.commit()
    await db_session.refresh(email_acc)

    campaign = Campaign(
        company_id=company_id,
        email_account_id=email_acc.id,
        name="Independent Campaign",
        status=CampaignStatus.DRAFT.value,
    )
    db_session.add(campaign)
    await db_session.commit()
    await db_session.refresh(campaign)

    # 3. Add recipient directly to campaign (snapshot copy simulation)
    campaign_recipient = CampaignRecipient(
        campaign_id=campaign.id,
        email="lead@customer.com",
        first_name="Lead",
        last_name="One",
    )
    db_session.add(campaign_recipient)
    await db_session.commit()
    await db_session.refresh(campaign_recipient)

    # 4. Delete list member from recipient list
    del_mem_resp = await async_client.delete(
        f"/api/v1/companies/{company_id}/recipient-lists/{list_id}/members/{member_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_mem_resp.status_code == 204

    # Verify campaign recipient record remains intact in DB!
    cr_check1 = await db_session.scalar(
        select(CampaignRecipient).where(CampaignRecipient.id == campaign_recipient.id)
    )
    assert cr_check1 is not None
    assert cr_check1.email == "lead@customer.com"

    # 5. Delete the entire recipient list
    del_list_resp = await async_client.delete(
        f"/api/v1/companies/{company_id}/recipient-lists/{list_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_list_resp.status_code == 204

    # Verify campaign recipient record STILL remains completely intact!
    cr_check2 = await db_session.scalar(
        select(CampaignRecipient).where(CampaignRecipient.id == campaign_recipient.id)
    )
    assert cr_check2 is not None
    assert cr_check2.email == "lead@customer.com"


# =============================================================================
# 6. CSV Import Tests
# =============================================================================

@pytest.mark.asyncio
async def test_import_members_csv_success_and_distinctions(async_client: AsyncClient):
    token = await register_and_login(async_client, "owner_csv@test.com")
    company_id = await create_company_helper(async_client, token, "CSV Co")

    list_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/recipient-lists",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "CSV Target List"},
    )
    list_id = list_resp.json()["id"]

    # Pre-insert one existing member in this list
    await async_client.post(
        f"/api/v1/companies/{company_id}/recipient-lists/{list_id}/members",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "existing@test.com", "first_name": "Old", "last_name": "Member"},
    )

    # Prepare CSV content:
    # Row 1: header
    # Row 2: existing@test.com (already in DB)
    # Row 3: new1@test.com (valid new)
    # Row 4: new2@test.com (valid new)
    # Row 5: NEW1@TEST.COM (duplicate in file)
    # Row 6: invalid-email (invalid row)
    # Row 7: (missing email, invalid row)
    csv_data = (
        "email,first_name,last_name\n"
        "existing@test.com,Existing,User\n"
        "new1@test.com,New,One\n"
        "new2@test.com,New,Two\n"
        "NEW1@TEST.COM,New,Duplicate\n"
        "invalid-email,Invalid,Row\n"
        ",Missing,Email\n"
    )

    files = {"file": ("contacts.csv", csv_data.encode("utf-8"), "text/csv")}
    resp = await async_client.post(
        f"/api/v1/companies/{company_id}/recipient-lists/{list_id}/members/import",
        headers={"Authorization": f"Bearer {token}"},
        files=files,
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["total_rows"] == 6
    assert data["imported_count"] == 2
    assert data["file_duplicates_count"] == 1
    assert data["existing_duplicates_count"] == 1
    assert data["invalid_rows_count"] == 2
    assert len(data["invalid_rows"]) == 2

    # Verify list count updated
    get_list = await async_client.get(
        f"/api/v1/companies/{company_id}/recipient-lists/{list_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_list.json()["recipient_count"] == 3  # 1 pre-existing + 2 newly imported


@pytest.mark.asyncio
async def test_import_members_csv_requires_admin_or_owner(async_client: AsyncClient):
    token_owner = await register_and_login(async_client, "owner_csv_auth@test.com")
    token_member = await register_and_login(async_client, "member_csv_auth@test.com")
    company_id = await create_company_helper(async_client, token_owner, "Auth CSV Co")
    await add_company_member_helper(async_client, token_owner, company_id, "member_csv_auth@test.com", "MEMBER")

    list_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/recipient-lists",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"name": "Auth List"},
    )
    list_id = list_resp.json()["id"]

    csv_data = "email,first_name,last_name\nvalid@test.com,Valid,User\n"
    files = {"file": ("test.csv", csv_data.encode("utf-8"), "text/csv")}

    # Member role must receive 403 Forbidden
    resp = await async_client.post(
        f"/api/v1/companies/{company_id}/recipient-lists/{list_id}/members/import",
        headers={"Authorization": f"Bearer {token_member}"},
        files=files,
    )
    assert resp.status_code == 403
