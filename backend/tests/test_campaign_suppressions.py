from httpx import AsyncClient
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.campaigns.models import (
    Campaign,
    CampaignRecipient,
    CampaignRecipientStatus,
    CampaignStatus,
    SuppressionEntry,
    SuppressionReason,
)
from app.modules.campaigns.schemas import SuppressionCreate
from app.modules.campaigns.suppression_service import SuppressionService


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


async def create_company_helper(client: AsyncClient, token: str, name: str = "Suppression Co") -> int:
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


# =============================================================================
# 1. Basic CRUD Tests
# =============================================================================

@pytest.mark.asyncio
async def test_create_and_get_suppression(async_client: AsyncClient):
    """Test manual suppression entry creation and retrieval."""
    token = await register_and_login(async_client, "owner_supp_crud@co.com", "Owner Supp")
    company_id = await create_company_helper(async_client, token, "Supp CRUD Co")

    # 1. Create suppression entry
    payload = {
        "email": " Unsubscribe.User@Example.COM ",
        "reason": "UNSUBSCRIBE",
    }
    resp = await async_client.post(
        f"/api/v1/companies/{company_id}/suppressions",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"] is not None
    assert data["company_id"] == company_id
    assert data["email"] == "unsubscribe.user@example.com"
    assert data["reason"] == "UNSUBSCRIBE"
    supp_id = data["id"]

    # 2. Get suppression entry
    get_resp = await async_client.get(
        f"/api/v1/companies/{company_id}/suppressions/{supp_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == supp_id
    assert get_resp.json()["email"] == "unsubscribe.user@example.com"


@pytest.mark.asyncio
async def test_list_suppressions_pagination_search_and_filters(async_client: AsyncClient):
    """Test listing suppressions with pagination, search, and reason filtering."""
    token = await register_and_login(async_client, "owner_list_supp@co.com", "Owner List Supp")
    company_id = await create_company_helper(async_client, token, "List Supp Co")

    # Add 4 entries with different reasons
    reasons = ["BOUNCE", "UNSUBSCRIBE", "MANUAL", "COMPLAINT"]
    for i, r in enumerate(reasons):
        await async_client.post(
            f"/api/v1/companies/{company_id}/suppressions",
            headers={"Authorization": f"Bearer {token}"},
            json={"email": f"supp_user_{i}@example.com", "reason": r},
        )

    # 1. List all
    list_resp = await async_client.get(
        f"/api/v1/companies/{company_id}/suppressions",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 4

    # 2. Filter by reason
    bounce_resp = await async_client.get(
        f"/api/v1/companies/{company_id}/suppressions?reason=BOUNCE",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert bounce_resp.status_code == 200
    assert len(bounce_resp.json()) == 1
    assert bounce_resp.json()[0]["email"] == "supp_user_0@example.com"

    # 3. Search by substring
    search_resp = await async_client.get(
        f"/api/v1/companies/{company_id}/suppressions?search=user_2",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert search_resp.status_code == 200
    assert len(search_resp.json()) == 1
    assert search_resp.json()[0]["email"] == "supp_user_2@example.com"

    # 4. Pagination
    page_resp = await async_client.get(
        f"/api/v1/companies/{company_id}/suppressions?limit=2&offset=1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert page_resp.status_code == 200
    assert len(page_resp.json()) == 2


@pytest.mark.asyncio
async def test_delete_suppression(async_client: AsyncClient):
    """Test permanent removal of a company suppression entry."""
    token = await register_and_login(async_client, "owner_del_supp@co.com", "Owner Del Supp")
    company_id = await create_company_helper(async_client, token, "Del Supp Co")

    create_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/suppressions",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "to_delete@example.com", "reason": "MANUAL"},
    )
    supp_id = create_resp.json()["id"]

    # 1. Delete suppression
    del_resp = await async_client.delete(
        f"/api/v1/companies/{company_id}/suppressions/{supp_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_resp.status_code == 204

    # 2. Get deleted suppression -> 404
    get_resp = await async_client.get(
        f"/api/v1/companies/{company_id}/suppressions/{supp_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_resp.status_code == 404


# =============================================================================
# 2. Normalization & Uniqueness Tests
# =============================================================================

@pytest.mark.asyncio
async def test_suppression_normalization_and_duplicate_handling(async_client: AsyncClient):
    """Test normalization and rejection of duplicate suppressions within the same company."""
    token = await register_and_login(async_client, "owner_norm_supp@co.com", "Owner Norm Supp")
    company_id = await create_company_helper(async_client, token, "Norm Supp Co")

    # 1. First creation normalizes case and surrounding whitespace
    resp1 = await async_client.post(
        f"/api/v1/companies/{company_id}/suppressions",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "  SpamBot@Example.COM  ", "reason": "COMPLAINT"},
    )
    assert resp1.status_code == 201
    assert resp1.json()["email"] == "spambot@example.com"

    # 2. Second creation with same normalized email returns 409 Conflict
    resp2 = await async_client.post(
        f"/api/v1/companies/{company_id}/suppressions",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "spambot@example.com", "reason": "MANUAL"},
    )
    assert resp2.status_code == 409
    assert "already suppressed" in resp2.json()["detail"].lower()

    # 3. Invalid email format returns 422
    resp_invalid = await async_client.post(
        f"/api/v1/companies/{company_id}/suppressions",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "not-valid", "reason": "MANUAL"},
    )
    assert resp_invalid.status_code == 422


@pytest.mark.asyncio
async def test_same_email_suppressed_in_different_companies(async_client: AsyncClient):
    """Test that the same email can be suppressed independently in two different companies."""
    token_a = await register_and_login(async_client, "owner_multi_a@co.com", "Owner Multi A")
    co_a_id = await create_company_helper(async_client, token_a, "Multi Co A")

    token_b = await register_and_login(async_client, "owner_multi_b@co.com", "Owner Multi B")
    co_b_id = await create_company_helper(async_client, token_b, "Multi Co B")

    shared_email = "shared_suppressed@example.com"

    # Company A suppresses
    resp_a = await async_client.post(
        f"/api/v1/companies/{co_a_id}/suppressions",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"email": shared_email, "reason": "BOUNCE"},
    )
    assert resp_a.status_code == 201

    # Company B suppresses same email without conflict
    resp_b = await async_client.post(
        f"/api/v1/companies/{co_b_id}/suppressions",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"email": shared_email, "reason": "UNSUBSCRIBE"},
    )
    assert resp_b.status_code == 201
    assert resp_b.json()["company_id"] == co_b_id


# =============================================================================
# 3. Bulk Suppression Tests
# =============================================================================

@pytest.mark.asyncio
async def test_bulk_suppression_creation_and_deduplication(async_client: AsyncClient):
    """Test bulk suppression creation with intra-batch deduplication and existing entry skipping."""
    token = await register_and_login(async_client, "owner_bulk_supp@co.com", "Owner Bulk Supp")
    company_id = await create_company_helper(async_client, token, "Bulk Supp Co")

    # Seed one existing suppression entry
    await async_client.post(
        f"/api/v1/companies/{company_id}/suppressions",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "already_there@example.com", "reason": "MANUAL"},
    )

    # Bulk request containing:
    # - 1 already in DB
    # - 2 unique new emails
    # - 1 intra-batch duplicate
    payload = {
        "emails": [
            "  ALREADY_THERE@EXAMPLE.COM  ",
            "new_supp1@example.com",
            "NEW_SUPP1@example.com",
            "new_supp2@example.com",
        ],
        "reason": "BOUNCE",
    }
    resp = await async_client.post(
        f"/api/v1/companies/{company_id}/suppressions/bulk",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert resp.status_code == 201
    report = resp.json()
    assert report["total_submitted"] == 4
    assert report["inserted_count"] == 2  # new_supp1 and new_supp2
    assert report["skipped_count"] == 2  # already_there and duplicate new_supp1
    assert "already_there@example.com" in report["skipped_emails"]
    assert "new_supp1@example.com" in report["skipped_emails"]


# =============================================================================
# 4. Lookup Primitives & Recipient Interaction Tests
# =============================================================================

@pytest.mark.asyncio
async def test_service_level_is_suppressed_lookup(
    db_session: AsyncSession,
):
    """Test SuppressionService.is_suppressed lookup primitive and company scoping."""
    from app.modules.companies.models import Company

    co1 = Company(name="Lookup Co 1")
    co2 = Company(name="Lookup Co 2")
    db_session.add(co1)
    db_session.add(co2)
    await db_session.commit()
    await db_session.refresh(co1)
    await db_session.refresh(co2)
    co1_id = co1.id
    co2_id = co2.id

    # Direct DB seeding for Co1
    entry = SuppressionEntry(
        company_id=co1_id,
        email="target_lookup@example.com",
        reason=SuppressionReason.MANUAL.value,
    )
    db_session.add(entry)
    await db_session.commit()

    # 1. Suppressed in Co1 (including case/whitespace variants)
    assert await SuppressionService.is_suppressed(db_session, co1_id, "target_lookup@example.com") is True
    assert await SuppressionService.is_suppressed(db_session, co1_id, " TARGET_LOOKUP@EXAMPLE.COM ") is True

    # 2. Not suppressed in Co1
    assert await SuppressionService.is_suppressed(db_session, co1_id, "other@example.com") is False

    # 3. Not suppressed in Co2 (company isolation)
    assert await SuppressionService.is_suppressed(db_session, co2_id, "target_lookup@example.com") is False


@pytest.mark.asyncio
async def test_adding_suppression_does_not_modify_existing_campaign_recipient(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Test that adding an email to suppression does NOT mutate existing CampaignRecipient status."""
    token = await register_and_login(async_client, "owner_recip_iso@co.com", "Owner Recip Iso")
    company_id = await create_company_helper(async_client, token, "Recip Iso Co")

    # Create email account and campaign
    acc_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/email-accounts",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Box",
            "email_address": "box@recip-iso.com",
            "provider": "CUSTOM",
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "smtp_security": "STARTTLS",
            "smtp_username": "box@recip-iso.com",
            "smtp_password": "SecretPassword123!",
            "imap_host": "imap.example.com",
            "imap_port": 993,
            "imap_security": "SSL",
            "imap_username": "box@recip-iso.com",
            "imap_password": "SecretPassword123!",
        },
    )
    account_id = acc_resp.json()["id"]

    camp_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Suppression Test Camp", "email_account_id": account_id, "subject": "Sub"},
    )
    campaign_id = camp_resp.json()["id"]

    # Add recipient to campaign
    recip_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/recipients",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "candidate@example.com"},
    )
    recipient_id = recip_resp.json()["id"]
    assert recip_resp.json()["status"] == "PENDING"

    # Now manually suppress that email company-wide
    supp_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/suppressions",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "candidate@example.com", "reason": "UNSUBSCRIBE"},
    )
    assert supp_resp.status_code == 201

    # Verify recipient status in database remains PENDING (NOT retroactively changed to SUPPRESSED)
    recip_obj = (await db_session.execute(select(CampaignRecipient).where(CampaignRecipient.id == recipient_id))).scalar_one()
    assert recip_obj.status == CampaignRecipientStatus.PENDING.value

    # Verify lookup primitive detects recipient as suppressed without changing their status
    is_supp = await SuppressionService.is_recipient_suppressed(db_session, company_id, recip_obj)
    assert is_supp is True
    assert recip_obj.status == CampaignRecipientStatus.PENDING.value


# =============================================================================
# 5. Authorization Tests
# =============================================================================

@pytest.mark.asyncio
async def test_suppression_authorization_roles(async_client: AsyncClient):
    """Test role permissions: MEMBER can view; MEMBER cannot mutate (create, bulk create, delete)."""
    owner_token = await register_and_login(async_client, "owner_supp_auth@co.com", "Owner Supp Auth")
    company_id = await create_company_helper(async_client, owner_token, "Supp Auth Co")

    member_token = await register_and_login(async_client, "member_supp_auth@co.com", "Member Supp Auth")
    await add_company_member_helper(async_client, owner_token, company_id, "member_supp_auth@co.com", role="MEMBER")

    # Owner creates a suppression entry
    create_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/suppressions",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"email": "auth_test@example.com", "reason": "MANUAL"},
    )
    supp_id = create_resp.json()["id"]

    # 1. Member can list suppressions -> 200
    m_list = await async_client.get(
        f"/api/v1/companies/{company_id}/suppressions",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert m_list.status_code == 200
    assert len(m_list.json()) == 1

    # 2. Member can get suppression detail -> 200
    m_get = await async_client.get(
        f"/api/v1/companies/{company_id}/suppressions/{supp_id}",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert m_get.status_code == 200

    # 3. Member cannot create suppression -> 403 Forbidden
    m_create = await async_client.post(
        f"/api/v1/companies/{company_id}/suppressions",
        headers={"Authorization": f"Bearer {member_token}"},
        json={"email": "m_fail@example.com", "reason": "MANUAL"},
    )
    assert m_create.status_code == 403

    # 4. Member cannot bulk create suppressions -> 403 Forbidden
    m_bulk = await async_client.post(
        f"/api/v1/companies/{company_id}/suppressions/bulk",
        headers={"Authorization": f"Bearer {member_token}"},
        json={"emails": ["m_fail@example.com"], "reason": "MANUAL"},
    )
    assert m_bulk.status_code == 403

    # 5. Member cannot delete suppression -> 403 Forbidden
    m_del = await async_client.delete(
        f"/api/v1/companies/{company_id}/suppressions/{supp_id}",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert m_del.status_code == 403


# =============================================================================
# 6. Tenant Isolation Tests
# =============================================================================

@pytest.mark.asyncio
async def test_suppression_cross_company_isolation_anti_enumeration(async_client: AsyncClient):
    """Test that cross-company suppression operations return 404 anti-enumeration."""
    token_a = await register_and_login(async_client, "owner_anti_supp_a@co.com", "Owner Supp A")
    co_a_id = await create_company_helper(async_client, token_a, "Anti Supp Co A")

    token_b = await register_and_login(async_client, "owner_anti_supp_b@co.com", "Owner Supp B")
    co_b_id = await create_company_helper(async_client, token_b, "Anti Supp Co B")

    supp_a_id = (await async_client.post(
        f"/api/v1/companies/{co_a_id}/suppressions",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"email": "co_a_supp@example.com", "reason": "MANUAL"},
    )).json()["id"]

    # 1. Company B user attempts to retrieve Company A's suppression entry -> 404
    resp_get = await async_client.get(
        f"/api/v1/companies/{co_b_id}/suppressions/{supp_a_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp_get.status_code == 404

    # 2. Company B user attempts to delete Company A's suppression entry -> 404
    resp_del = await async_client.delete(
        f"/api/v1/companies/{co_b_id}/suppressions/{supp_a_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp_del.status_code == 404
