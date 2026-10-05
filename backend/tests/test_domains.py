from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from httpx import AsyncClient
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.companies.models import Company
from app.modules.domains.models import Domain, DomainVerificationStatus
from app.modules.domains.schemas import normalize_domain_name
from app.services.dns.exceptions import (
    DNSDomainNotFoundError,
    DNSTimeoutError,
    DNSNoAnswerError,
    DNSTemporaryError,
    DNSResolutionError,
)
from app.services.dns.resolver import (
    DNSResolver,
    DNSVerificationResult,
    verify_domain_dns,
)


@pytest.mark.asyncio
async def test_domain_persistence_and_company_relationship(db_session: AsyncSession):
    """Test that Domain model can be persisted and navigates to its Company."""
    company = Company(name="Test Org")
    db_session.add(company)
    await db_session.commit()
    await db_session.refresh(company)

    domain = Domain(company_id=company.id, domain_name="example.com")
    db_session.add(domain)
    await db_session.commit()
    await db_session.refresh(domain)

    assert domain.id is not None
    assert domain.domain_name == "example.com"
    assert domain.company_id == company.id

    # Verify query by ID with relationship loading
    result = await db_session.execute(
        select(Domain).options(selectinload(Domain.company)).where(Domain.id == domain.id)
    )
    loaded_domain = result.scalar_one()
    assert loaded_domain.company.id == company.id
    assert loaded_domain.company.name == "Test Org"

    # Verify navigation from company to domains
    comp_result = await db_session.execute(
        select(Company).options(selectinload(Company.domains)).where(Company.id == company.id)
    )
    loaded_company = comp_result.scalar_one()
    assert len(loaded_company.domains) == 1
    assert loaded_company.domains[0].domain_name == "example.com"


@pytest.mark.asyncio
async def test_domain_default_statuses(db_session: AsyncSession):
    """Test that all verification statuses default to PENDING upon creation."""
    company = Company(name="Status Org")
    db_session.add(company)
    await db_session.commit()
    await db_session.refresh(company)

    domain = Domain(company_id=company.id, domain_name="status-check.org")
    db_session.add(domain)
    await db_session.commit()
    await db_session.refresh(domain)

    assert domain.verification_status == DomainVerificationStatus.PENDING.value
    assert domain.spf_status == DomainVerificationStatus.PENDING.value
    assert domain.dkim_status == DomainVerificationStatus.PENDING.value
    assert domain.dmarc_status == DomainVerificationStatus.PENDING.value
    assert domain.mx_status == DomainVerificationStatus.PENDING.value


@pytest.mark.asyncio
async def test_domain_nullable_fields(db_session: AsyncSession):
    """Test nullable fields default to None and can be updated with valid values."""
    company = Company(name="Nullable Org")
    db_session.add(company)
    await db_session.commit()
    await db_session.refresh(company)

    domain = Domain(company_id=company.id, domain_name="nullable-test.com")
    db_session.add(domain)
    await db_session.commit()
    await db_session.refresh(domain)

    # Initial defaults should be None
    assert domain.dkim_selector is None
    assert domain.last_checked_at is None
    assert domain.verification_error is None

    # Update with values
    now_utc = datetime.now(timezone.utc)
    domain.dkim_selector = "mail2026"
    domain.last_checked_at = now_utc
    domain.verification_error = "DNS lookup timed out for MX record"
    await db_session.commit()
    await db_session.refresh(domain)

    assert domain.dkim_selector == "mail2026"
    assert domain.last_checked_at is not None
    assert domain.verification_error == "DNS lookup timed out for MX record"


@pytest.mark.asyncio
async def test_same_domain_under_different_companies_allowed(db_session: AsyncSession):
    """Test company-scoped uniqueness: same domain can exist under different companies."""
    company_a = Company(name="Company A")
    company_b = Company(name="Company B")
    db_session.add_all([company_a, company_b])
    await db_session.commit()
    await db_session.refresh(company_a)
    await db_session.refresh(company_b)

    domain_a = Domain(company_id=company_a.id, domain_name="shared-domain.io")
    domain_b = Domain(company_id=company_b.id, domain_name="shared-domain.io")
    db_session.add_all([domain_a, domain_b])
    await db_session.commit()
    await db_session.refresh(domain_a)
    await db_session.refresh(domain_b)

    assert domain_a.id is not None
    assert domain_b.id is not None
    assert domain_a.id != domain_b.id
    assert domain_a.domain_name == domain_b.domain_name
    assert domain_a.company_id != domain_b.company_id


@pytest.mark.asyncio
async def test_duplicate_domain_within_same_company_rejected(db_session: AsyncSession):
    """Test company-scoped uniqueness: duplicate domain under same company violates uq_company_domain_name."""
    company = Company(name="Unique Test Org")
    db_session.add(company)
    await db_session.commit()
    await db_session.refresh(company)

    domain_1 = Domain(company_id=company.id, domain_name="duplicate-test.com")
    db_session.add(domain_1)
    await db_session.commit()

    domain_2 = Domain(company_id=company.id, domain_name="duplicate-test.com")
    db_session.add(domain_2)

    with pytest.raises(IntegrityError) as exc_info:
        await db_session.commit()

    assert "uq_company_domain_name" in str(exc_info.value).lower() or "unique" in str(exc_info.value).lower()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_company_deletion_cascades_to_domains(db_session: AsyncSession):
    """Test that deleting a Company cascades and deletes all associated Domain records."""
    company = Company(name="Cascade Delete Org")
    db_session.add(company)
    await db_session.commit()
    await db_session.refresh(company)

    domain1 = Domain(company_id=company.id, domain_name="cascade1.org")
    domain2 = Domain(company_id=company.id, domain_name="cascade2.org")
    db_session.add_all([domain1, domain2])
    await db_session.commit()

    # Verify domains exist
    domains_before = (
        await db_session.execute(select(Domain).where(Domain.company_id == company.id))
    ).scalars().all()
    assert len(domains_before) == 2

    # Delete the company
    await db_session.delete(company)
    await db_session.commit()

    # Verify domains were cascade deleted
    domains_after = (
        await db_session.execute(select(Domain).where(Domain.company_id == company.id))
    ).scalars().all()
    assert len(domains_after) == 0


@pytest.mark.asyncio
async def test_domain_timestamps(db_session: AsyncSession):
    """Test that created_at and updated_at are automatically populated with timezone-aware datetimes."""
    company = Company(name="Timestamp Org")
    db_session.add(company)
    await db_session.commit()
    await db_session.refresh(company)

    domain = Domain(company_id=company.id, domain_name="timestamp-check.net")
    db_session.add(domain)
    await db_session.commit()
    await db_session.refresh(domain)

    assert domain.created_at is not None
    assert isinstance(domain.created_at, datetime)
    assert domain.created_at.tzinfo is not None

    assert domain.updated_at is not None
    assert isinstance(domain.updated_at, datetime)
    assert domain.updated_at.tzinfo is not None


# =============================================================================
# D3 API & Authorization Test Helpers
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


async def create_company_helper(client: AsyncClient, token: str, name: str = "Domain Test Co") -> int:
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
# D3 Normalization Unit Tests
# =============================================================================

def test_domain_normalization_unit():
    """Unit tests for deterministic domain normalization rules."""
    assert normalize_domain_name("  EXAMPLE.COM.  ") == "example.com"
    assert normalize_domain_name("Sub.Domain.Org.") == "sub.domain.org"
    assert normalize_domain_name("MY-DOMAIN.CO.UK") == "my-domain.co.uk"

    # Invalid formats
    invalid_cases = [
        "user@example.com",
        "https://example.com",
        "http://example.com",
        "example.com/path",
        "localhost",
        "ab",
        "-leading-hyphen.com",
        "trailing-hyphen-.com",
        "example..com",
        "192.168.1.1",
        "a" * 256 + ".com",
    ]
    for case in invalid_cases:
        with pytest.raises(ValueError):
            normalize_domain_name(case)


# =============================================================================
# D3 Create Tests
# =============================================================================

@pytest.mark.asyncio
async def test_owner_can_create_valid_domain(async_client: AsyncClient):
    """Test that a company OWNER can add a valid domain with initial PENDING status."""
    token = await register_and_login(async_client, "owner_create@domain.com")
    company_id = await create_company_helper(async_client, token, "Owner Corp")

    resp = await async_client.post(
        f"/api/v1/companies/{company_id}/domains",
        headers={"Authorization": f"Bearer {token}"},
        json={"domain_name": "owner-domain.com", "dkim_selector": "sig1"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["company_id"] == company_id
    assert data["domain_name"] == "owner-domain.com"
    assert data["dkim_selector"] == "sig1"
    assert data["verification_status"] == "PENDING"
    assert data["spf_status"] == "PENDING"
    assert data["dkim_status"] == "PENDING"
    assert data["dmarc_status"] == "PENDING"
    assert data["mx_status"] == "PENDING"
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data


@pytest.mark.asyncio
async def test_admin_can_create_valid_domain(async_client: AsyncClient):
    """Test that a company ADMIN can add a valid domain."""
    token_owner = await register_and_login(async_client, "owner_for_admin@domain.com")
    token_admin = await register_and_login(async_client, "admin_user@domain.com")
    company_id = await create_company_helper(async_client, token_owner, "Admin Corp")
    await add_company_member_helper(async_client, token_owner, company_id, "admin_user@domain.com", role="ADMIN")

    resp = await async_client.post(
        f"/api/v1/companies/{company_id}/domains",
        headers={"Authorization": f"Bearer {token_admin}"},
        json={"domain_name": "admin-domain.org"},
    )
    assert resp.status_code == 201
    assert resp.json()["domain_name"] == "admin-domain.org"


@pytest.mark.asyncio
async def test_member_cannot_create_domain(async_client: AsyncClient):
    """Test that a company MEMBER receives 403 Forbidden when attempting to create a domain."""
    token_owner = await register_and_login(async_client, "owner_for_mem@domain.com")
    token_member = await register_and_login(async_client, "member_user@domain.com")
    company_id = await create_company_helper(async_client, token_owner, "Member Corp")
    await add_company_member_helper(async_client, token_owner, company_id, "member_user@domain.com", role="MEMBER")

    resp = await async_client.post(
        f"/api/v1/companies/{company_id}/domains",
        headers={"Authorization": f"Bearer {token_member}"},
        json={"domain_name": "member-blocked.com"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Owner or Administrator privileges required for this action"


@pytest.mark.asyncio
async def test_domain_normalization_on_create_api(async_client: AsyncClient):
    """Test that domain names are normalized during API creation."""
    token = await register_and_login(async_client, "norm_owner@domain.com")
    company_id = await create_company_helper(async_client, token, "Norm Corp")

    resp = await async_client.post(
        f"/api/v1/companies/{company_id}/domains",
        headers={"Authorization": f"Bearer {token}"},
        json={"domain_name": "  UPPER-CASE.EXAMPLE.COM.  "},
    )
    assert resp.status_code == 201
    assert resp.json()["domain_name"] == "upper-case.example.com"


@pytest.mark.asyncio
async def test_invalid_domain_formats_rejected_with_422(async_client: AsyncClient):
    """Test that malformed domain strings are rejected with 422 Unprocessable Entity."""
    token = await register_and_login(async_client, "invalid_fmt_owner@domain.com")
    company_id = await create_company_helper(async_client, token, "Fmt Corp")

    invalid_domains = [
        "user@email.com",
        "https://domain.com",
        "http://domain.com",
        "domain.com/path",
        "localhost",
        "ab",
        "-badprefix.com",
        "badsuffix-.com",
        "empty..label.com",
        "127.0.0.1",
    ]

    for inv in invalid_domains:
        resp = await async_client.post(
            f"/api/v1/companies/{company_id}/domains",
            headers={"Authorization": f"Bearer {token}"},
            json={"domain_name": inv},
        )
        assert resp.status_code == 422, f"Expected 422 for invalid domain '{inv}', got {resp.status_code}"


@pytest.mark.asyncio
async def test_duplicate_domain_same_company_rejected_with_409(async_client: AsyncClient):
    """Test that creating a duplicate domain within the same company returns 409 Conflict."""
    token = await register_and_login(async_client, "dup_owner@domain.com")
    company_id = await create_company_helper(async_client, token, "Dup Corp")

    # Initial creation succeeds
    resp1 = await async_client.post(
        f"/api/v1/companies/{company_id}/domains",
        headers={"Authorization": f"Bearer {token}"},
        json={"domain_name": "unique-name.com"},
    )
    assert resp1.status_code == 201

    # Exact duplicate returns 409
    resp2 = await async_client.post(
        f"/api/v1/companies/{company_id}/domains",
        headers={"Authorization": f"Bearer {token}"},
        json={"domain_name": "unique-name.com"},
    )
    assert resp2.status_code == 409
    assert "already exists in this company" in resp2.json()["detail"]

    # Normalized duplicate returns 409
    resp3 = await async_client.post(
        f"/api/v1/companies/{company_id}/domains",
        headers={"Authorization": f"Bearer {token}"},
        json={"domain_name": "  UNIQUE-NAME.COM.  "},
    )
    assert resp3.status_code == 409
    assert "already exists in this company" in resp3.json()["detail"]


@pytest.mark.asyncio
async def test_same_domain_under_different_company_succeeds_api(async_client: AsyncClient):
    """Test that the same domain name can be registered under different companies via API."""
    token_a = await register_and_login(async_client, "co_a_owner@domain.com")
    token_b = await register_and_login(async_client, "co_b_owner@domain.com")
    company_a = await create_company_helper(async_client, token_a, "Multi Co A")
    company_b = await create_company_helper(async_client, token_b, "Multi Co B")

    resp_a = await async_client.post(
        f"/api/v1/companies/{company_a}/domains",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"domain_name": "shared-tenant.com"},
    )
    assert resp_a.status_code == 201

    resp_b = await async_client.post(
        f"/api/v1/companies/{company_b}/domains",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"domain_name": "shared-tenant.com"},
    )
    assert resp_b.status_code == 201
    assert resp_a.json()["id"] != resp_b.json()["id"]


# =============================================================================
# D3 List Tests
# =============================================================================

@pytest.mark.asyncio
async def test_member_admin_owner_can_list_domains(async_client: AsyncClient):
    """Test that OWNER, ADMIN, and MEMBER can all list company domains."""
    token_owner = await register_and_login(async_client, "list_owner@domain.com")
    token_admin = await register_and_login(async_client, "list_admin@domain.com")
    token_member = await register_and_login(async_client, "list_member@domain.com")
    company_id = await create_company_helper(async_client, token_owner, "List Corp")
    await add_company_member_helper(async_client, token_owner, company_id, "list_admin@domain.com", role="ADMIN")
    await add_company_member_helper(async_client, token_owner, company_id, "list_member@domain.com", role="MEMBER")

    # Create 2 domains
    await async_client.post(
        f"/api/v1/companies/{company_id}/domains",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"domain_name": "list-d1.com"},
    )
    await async_client.post(
        f"/api/v1/companies/{company_id}/domains",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"domain_name": "list-d2.com"},
    )

    # Owner lists
    resp_owner = await async_client.get(
        f"/api/v1/companies/{company_id}/domains",
        headers={"Authorization": f"Bearer {token_owner}"},
    )
    assert resp_owner.status_code == 200
    assert len(resp_owner.json()) == 2

    # Admin lists
    resp_admin = await async_client.get(
        f"/api/v1/companies/{company_id}/domains",
        headers={"Authorization": f"Bearer {token_admin}"},
    )
    assert resp_admin.status_code == 200
    assert len(resp_admin.json()) == 2

    # Member lists
    resp_member = await async_client.get(
        f"/api/v1/companies/{company_id}/domains",
        headers={"Authorization": f"Bearer {token_member}"},
    )
    assert resp_member.status_code == 200
    assert len(resp_member.json()) == 2


@pytest.mark.asyncio
async def test_list_domains_is_company_scoped(async_client: AsyncClient):
    """Test that listing domains returns only domains for the specified company."""
    token_a = await register_and_login(async_client, "co1_list@domain.com")
    token_b = await register_and_login(async_client, "co2_list@domain.com")
    co_1 = await create_company_helper(async_client, token_a, "Scoped Co 1")
    co_2 = await create_company_helper(async_client, token_b, "Scoped Co 2")

    await async_client.post(
        f"/api/v1/companies/{co_1}/domains",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"domain_name": "co1-only.com"},
    )
    await async_client.post(
        f"/api/v1/companies/{co_2}/domains",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"domain_name": "co2-only.com"},
    )

    resp_1 = await async_client.get(
        f"/api/v1/companies/{co_1}/domains",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    domains_1 = resp_1.json()
    assert len(domains_1) == 1
    assert domains_1[0]["domain_name"] == "co1-only.com"


# =============================================================================
# D3 Detail Tests
# =============================================================================

@pytest.mark.asyncio
async def test_authorized_member_can_retrieve_domain(async_client: AsyncClient):
    """Test that an authorized member can view domain details."""
    token_owner = await register_and_login(async_client, "detail_owner@domain.com")
    token_member = await register_and_login(async_client, "detail_member@domain.com")
    company_id = await create_company_helper(async_client, token_owner, "Detail Corp")
    await add_company_member_helper(async_client, token_owner, company_id, "detail_member@domain.com", role="MEMBER")

    create_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/domains",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"domain_name": "detail-test.com", "dkim_selector": "sel1"},
    )
    domain_id = create_resp.json()["id"]

    resp = await async_client.get(
        f"/api/v1/companies/{company_id}/domains/{domain_id}",
        headers={"Authorization": f"Bearer {token_member}"},
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == domain_id
    assert resp.json()["domain_name"] == "detail-test.com"
    assert resp.json()["dkim_selector"] == "sel1"


@pytest.mark.asyncio
async def test_get_foreign_company_domain_returns_404(async_client: AsyncClient):
    """Test anti-enumeration: requesting another company's domain ID returns 404."""
    token_a = await register_and_login(async_client, "enum_a@domain.com")
    token_b = await register_and_login(async_client, "enum_b@domain.com")
    co_a = await create_company_helper(async_client, token_a, "AntiEnum Co A")
    co_b = await create_company_helper(async_client, token_b, "AntiEnum Co B")

    # Create domain in Co B
    create_resp = await async_client.post(
        f"/api/v1/companies/{co_b}/domains",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"domain_name": "secret-b.com"},
    )
    domain_b_id = create_resp.json()["id"]

    # User A tries to query Co B's domain ID via Co A route -> 404 Not Found
    resp1 = await async_client.get(
        f"/api/v1/companies/{co_a}/domains/{domain_b_id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp1.status_code == 404
    assert resp1.json()["detail"] == "Domain not found"

    # User A tries to query Co B directly without membership -> 404 Not Found
    resp2 = await async_client.get(
        f"/api/v1/companies/{co_b}/domains/{domain_b_id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp2.status_code == 404
    assert resp2.json()["detail"] == "Company not found"


@pytest.mark.asyncio
async def test_get_nonexistent_domain_returns_404(async_client: AsyncClient):
    """Test requesting a nonexistent domain returns 404."""
    token = await register_and_login(async_client, "nonexistent@domain.com")
    company_id = await create_company_helper(async_client, token, "Nonexistent Corp")

    resp = await async_client.get(
        f"/api/v1/companies/{company_id}/domains/999999",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Domain not found"


# =============================================================================
# D3 Update Tests
# =============================================================================

@pytest.mark.asyncio
async def test_owner_and_admin_can_update_dkim_selector(async_client: AsyncClient):
    """Test that OWNER and ADMIN can update dkim_selector, resetting DKIM status to PENDING."""
    token_owner = await register_and_login(async_client, "update_owner@domain.com")
    token_admin = await register_and_login(async_client, "update_admin@domain.com")
    company_id = await create_company_helper(async_client, token_owner, "Update Corp")
    await add_company_member_helper(async_client, token_owner, company_id, "update_admin@domain.com", role="ADMIN")

    create_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/domains",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"domain_name": "update-test.com", "dkim_selector": "old_sel"},
    )
    domain_id = create_resp.json()["id"]

    # Owner updates selector
    resp_owner = await async_client.patch(
        f"/api/v1/companies/{company_id}/domains/{domain_id}",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"dkim_selector": "owner_sel"},
    )
    assert resp_owner.status_code == 200
    assert resp_owner.json()["dkim_selector"] == "owner_sel"
    assert resp_owner.json()["dkim_status"] == "PENDING"
    assert resp_owner.json()["verification_status"] == "PENDING"

    # Admin updates selector
    resp_admin = await async_client.patch(
        f"/api/v1/companies/{company_id}/domains/{domain_id}",
        headers={"Authorization": f"Bearer {token_admin}"},
        json={"dkim_selector": "admin_sel"},
    )
    assert resp_admin.status_code == 200
    assert resp_admin.json()["dkim_selector"] == "admin_sel"


@pytest.mark.asyncio
async def test_member_cannot_update_domain(async_client: AsyncClient):
    """Test that MEMBER receives 403 Forbidden on update."""
    token_owner = await register_and_login(async_client, "upd_owner_for_mem@domain.com")
    token_member = await register_and_login(async_client, "upd_member@domain.com")
    company_id = await create_company_helper(async_client, token_owner, "Upd Mem Corp")
    await add_company_member_helper(async_client, token_owner, company_id, "upd_member@domain.com", role="MEMBER")

    create_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/domains",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"domain_name": "mem-no-upd.com"},
    )
    domain_id = create_resp.json()["id"]

    resp = await async_client.patch(
        f"/api/v1/companies/{company_id}/domains/{domain_id}",
        headers={"Authorization": f"Bearer {token_member}"},
        json={"dkim_selector": "hacked"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Owner or Administrator privileges required for this action"


@pytest.mark.asyncio
async def test_domain_name_cannot_be_updated_and_extra_fields_rejected(async_client: AsyncClient):
    """Test that domain_name is immutable and extra fields are forbidden on PATCH."""
    token = await register_and_login(async_client, "immutable_owner@domain.com")
    company_id = await create_company_helper(async_client, token, "Immutable Corp")

    create_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/domains",
        headers={"Authorization": f"Bearer {token}"},
        json={"domain_name": "immutable.com"},
    )
    domain_id = create_resp.json()["id"]

    # Attempt to change domain_name -> 422
    resp_name = await async_client.patch(
        f"/api/v1/companies/{company_id}/domains/{domain_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"domain_name": "changed-domain.com"},
    )
    assert resp_name.status_code == 422

    # Attempt to pass extra field -> 422
    resp_extra = await async_client.patch(
        f"/api/v1/companies/{company_id}/domains/{domain_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"extra_field": "disallowed"},
    )
    assert resp_extra.status_code == 422


@pytest.mark.asyncio
async def test_selector_update_does_not_trigger_dns(async_client: AsyncClient):
    """Test that updating dkim_selector preserves PENDING and executes without DNS queries."""
    token = await register_and_login(async_client, "dns_check_owner@domain.com")
    company_id = await create_company_helper(async_client, token, "Dns Check Corp")

    create_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/domains",
        headers={"Authorization": f"Bearer {token}"},
        json={"domain_name": "no-dns-run.com", "dkim_selector": "s1"},
    )
    domain_id = create_resp.json()["id"]

    patch_resp = await async_client.patch(
        f"/api/v1/companies/{company_id}/domains/{domain_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"dkim_selector": "s2"},
    )
    assert patch_resp.status_code == 200
    data = patch_resp.json()
    assert data["dkim_selector"] == "s2"
    assert data["verification_status"] == "PENDING"
    assert data["spf_status"] == "PENDING"
    assert data["dkim_status"] == "PENDING"
    assert data["dmarc_status"] == "PENDING"
    assert data["mx_status"] == "PENDING"
    assert data["last_checked_at"] is None


# =============================================================================
# D3 Delete Tests
# =============================================================================

@pytest.mark.asyncio
async def test_owner_and_admin_can_delete_domain(async_client: AsyncClient):
    """Test that OWNER and ADMIN can delete a domain, and subsequent lookups return 404."""
    token_owner = await register_and_login(async_client, "del_owner@domain.com")
    token_admin = await register_and_login(async_client, "del_admin@domain.com")
    company_id = await create_company_helper(async_client, token_owner, "Delete Corp")
    await add_company_member_helper(async_client, token_owner, company_id, "del_admin@domain.com", role="ADMIN")

    # Domain for owner to delete
    resp1 = await async_client.post(
        f"/api/v1/companies/{company_id}/domains",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"domain_name": "to-delete-1.com"},
    )
    d1_id = resp1.json()["id"]

    # Domain for admin to delete
    resp2 = await async_client.post(
        f"/api/v1/companies/{company_id}/domains",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"domain_name": "to-delete-2.com"},
    )
    d2_id = resp2.json()["id"]

    # Owner deletes d1
    del_resp1 = await async_client.delete(
        f"/api/v1/companies/{company_id}/domains/{d1_id}",
        headers={"Authorization": f"Bearer {token_owner}"},
    )
    assert del_resp1.status_code == 204

    # Admin deletes d2
    del_resp2 = await async_client.delete(
        f"/api/v1/companies/{company_id}/domains/{d2_id}",
        headers={"Authorization": f"Bearer {token_admin}"},
    )
    assert del_resp2.status_code == 204

    # Verify both are deleted
    get1 = await async_client.get(
        f"/api/v1/companies/{company_id}/domains/{d1_id}",
        headers={"Authorization": f"Bearer {token_owner}"},
    )
    assert get1.status_code == 404

    get2 = await async_client.get(
        f"/api/v1/companies/{company_id}/domains/{d2_id}",
        headers={"Authorization": f"Bearer {token_owner}"},
    )
    assert get2.status_code == 404


@pytest.mark.asyncio
async def test_member_cannot_delete_domain(async_client: AsyncClient):
    """Test that MEMBER receives 403 Forbidden when attempting to delete a domain."""
    token_owner = await register_and_login(async_client, "del_owner_mem@domain.com")
    token_member = await register_and_login(async_client, "del_mem@domain.com")
    company_id = await create_company_helper(async_client, token_owner, "Del Mem Corp")
    await add_company_member_helper(async_client, token_owner, company_id, "del_mem@domain.com", role="MEMBER")

    create_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/domains",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"domain_name": "nodelete-mem.com"},
    )
    domain_id = create_resp.json()["id"]

    resp = await async_client.delete(
        f"/api/v1/companies/{company_id}/domains/{domain_id}",
        headers={"Authorization": f"Bearer {token_member}"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Owner or Administrator privileges required for this action"


@pytest.mark.asyncio
async def test_delete_foreign_or_nonexistent_domain_returns_404(async_client: AsyncClient):
    """Test that attempting to delete a foreign or nonexistent domain returns 404."""
    token_a = await register_and_login(async_client, "del_foreign_a@domain.com")
    token_b = await register_and_login(async_client, "del_foreign_b@domain.com")
    co_a = await create_company_helper(async_client, token_a, "Del Foreign Co A")
    co_b = await create_company_helper(async_client, token_b, "Del Foreign Co B")

    # Create domain in Co B
    create_resp = await async_client.post(
        f"/api/v1/companies/{co_b}/domains",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"domain_name": "target-foreign.com"},
    )
    domain_b_id = create_resp.json()["id"]

    # Co A owner tries to delete Co B domain via Co A route -> 404
    resp1 = await async_client.delete(
        f"/api/v1/companies/{co_a}/domains/{domain_b_id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp1.status_code == 404

    # Delete nonexistent domain ID -> 404
    resp2 = await async_client.delete(
        f"/api/v1/companies/{co_a}/domains/999999",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp2.status_code == 404


# =============================================================================
# D4 DNS Verification Unit & Resolver Tests (Mocked DNS)
# =============================================================================

def test_dns_mx_verification_valid_and_missing():
    """Test MX verification: at least one MX yields VERIFIED; none yields FAILED."""
    mock_res = MagicMock(spec=DNSResolver)
    
    # Valid MX
    mock_res.resolve_mx.return_value = ["mail.example.com"]
    mock_res.resolve_txt.return_value = []
    res_valid = verify_domain_dns("example.com", resolver=mock_res)
    assert res_valid.mx_status == DomainVerificationStatus.VERIFIED.value

    # Missing MX (NoAnswer / empty)
    mock_res.resolve_mx.return_value = []
    res_missing = verify_domain_dns("example.com", resolver=mock_res)
    assert res_missing.mx_status == DomainVerificationStatus.FAILED.value
    assert "MX record not found" in res_missing.verification_error


def test_dns_spf_verification_valid_and_missing():
    """Test SPF verification: TXT starting with v=spf1 yields VERIFIED; else FAILED."""
    mock_res = MagicMock(spec=DNSResolver)
    mock_res.resolve_mx.return_value = ["mail.example.com"]

    # Valid SPF
    mock_res.resolve_txt.return_value = ["v=spf1 include:_spf.google.com ~all"]
    res_valid = verify_domain_dns("example.com", resolver=mock_res)
    assert res_valid.spf_status == DomainVerificationStatus.VERIFIED.value

    # Missing / unrelated TXT
    mock_res.resolve_txt.return_value = ["unrelated-txt-record"]
    res_missing = verify_domain_dns("example.com", resolver=mock_res)
    assert res_missing.spf_status == DomainVerificationStatus.FAILED.value
    assert "SPF record not found" in res_missing.verification_error


def test_dns_dkim_verification_scenarios():
    """Test DKIM verification with selector, without selector, and with invalid record."""
    mock_res = MagicMock(spec=DNSResolver)
    mock_res.resolve_mx.return_value = ["mail.example.com"]

    # 1. Missing selector -> PENDING
    mock_res.resolve_txt.return_value = ["v=spf1 ~all"]
    res_no_sel = verify_domain_dns("example.com", dkim_selector=None, resolver=mock_res)
    assert res_no_sel.dkim_status == DomainVerificationStatus.PENDING.value
    assert "DKIM verification skipped: no selector configured" in res_no_sel.verification_error

    # 2. Valid selector and valid DKIM TXT -> VERIFIED
    def resolve_txt_side_effect(name: str):
        if "s1._domainkey" in name:
            return ["v=DKIM1; k=rsa; p=MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQ..."]
        return ["v=spf1 ~all"]
    mock_res.resolve_txt.side_effect = resolve_txt_side_effect

    res_valid_dkim = verify_domain_dns("example.com", dkim_selector="s1", resolver=mock_res)
    assert res_valid_dkim.dkim_status == DomainVerificationStatus.VERIFIED.value

    # 3. Valid selector but missing DKIM TXT -> FAILED
    def resolve_txt_no_dkim(name: str):
        if "s1._domainkey" in name:
            return []
        return ["v=spf1 ~all"]
    mock_res.resolve_txt.side_effect = resolve_txt_no_dkim

    res_invalid_dkim = verify_domain_dns("example.com", dkim_selector="s1", resolver=mock_res)
    assert res_invalid_dkim.dkim_status == DomainVerificationStatus.FAILED.value
    assert "DKIM record not found for selector 's1'" in res_invalid_dkim.verification_error


def test_dns_dmarc_verification_policies():
    """Test DMARC verification: p=reject/quarantine -> VERIFIED; p=none -> WARNING; missing -> FAILED."""
    mock_res = MagicMock(spec=DNSResolver)
    mock_res.resolve_mx.return_value = ["mail.example.com"]

    # p=reject -> VERIFIED
    mock_res.resolve_txt.side_effect = lambda name: ["v=DMARC1; p=reject; rua=mailto:dmarc@ex.com"] if "_dmarc" in name else ["v=spf1 ~all"]
    res_reject = verify_domain_dns("example.com", dkim_selector=None, resolver=mock_res)
    assert res_reject.dmarc_status == DomainVerificationStatus.VERIFIED.value

    # p=quarantine -> VERIFIED
    mock_res.resolve_txt.side_effect = lambda name: ["v=DMARC1; p=quarantine"] if "_dmarc" in name else ["v=spf1 ~all"]
    res_quar = verify_domain_dns("example.com", dkim_selector=None, resolver=mock_res)
    assert res_quar.dmarc_status == DomainVerificationStatus.VERIFIED.value

    # p=none -> WARNING
    mock_res.resolve_txt.side_effect = lambda name: ["v=DMARC1; p=none; sp=none"] if "_dmarc" in name else ["v=spf1 ~all"]
    res_none = verify_domain_dns("example.com", dkim_selector=None, resolver=mock_res)
    assert res_none.dmarc_status == DomainVerificationStatus.WARNING.value
    assert "DMARC policy is set to p=none" in res_none.verification_error

    # missing DMARC -> FAILED
    mock_res.resolve_txt.side_effect = lambda name: [] if "_dmarc" in name else ["v=spf1 ~all"]
    res_missing = verify_domain_dns("example.com", dkim_selector=None, resolver=mock_res)
    assert res_missing.dmarc_status == DomainVerificationStatus.FAILED.value
    assert "DMARC record not found" in res_missing.verification_error


def test_dns_overall_status_calculations():
    """Test overall status determination based on component statuses."""
    mock_res = MagicMock(spec=DNSResolver)

    # 1. All valid (MX + SPF + DKIM + DMARC) -> VERIFIED
    mock_res.resolve_mx.return_value = ["mail.example.com"]
    mock_res.resolve_txt.side_effect = lambda name: (
        ["v=DKIM1; p=key"] if "s1._domainkey" in name else
        ["v=DMARC1; p=reject"] if "_dmarc" in name else
        ["v=spf1 -all"]
    )
    res_all_valid = verify_domain_dns("example.com", dkim_selector="s1", resolver=mock_res)
    assert res_all_valid.verification_status == DomainVerificationStatus.VERIFIED.value
    assert res_all_valid.verification_error is None

    # 2. Missing DKIM selector + MX/SPF/DMARC valid -> WARNING
    mock_res.resolve_txt.side_effect = lambda name: (
        ["v=DMARC1; p=reject"] if "_dmarc" in name else ["v=spf1 -all"]
    )
    res_no_sel = verify_domain_dns("example.com", dkim_selector=None, resolver=mock_res)
    assert res_no_sel.verification_status == DomainVerificationStatus.WARNING.value
    assert "DKIM verification skipped: no selector configured" in res_no_sel.verification_error

    # 3. Missing MX (hard failure) -> FAILED
    mock_res.resolve_mx.return_value = []
    res_no_mx = verify_domain_dns("example.com", dkim_selector="s1", resolver=mock_res)
    assert res_no_mx.verification_status == DomainVerificationStatus.FAILED.value
    assert "MX record not found" in res_no_mx.verification_error

    # 4. Missing SPF (hard failure) -> FAILED
    mock_res.resolve_mx.return_value = ["mail.example.com"]
    mock_res.resolve_txt.side_effect = lambda name: []
    res_no_spf = verify_domain_dns("example.com", dkim_selector="s1", resolver=mock_res)
    assert res_no_spf.verification_status == DomainVerificationStatus.FAILED.value
    assert "SPF record not found" in res_no_spf.verification_error

    # 5. DMARC warning (p=none) while hard requirements pass -> WARNING
    mock_res.resolve_txt.side_effect = lambda name: (
        ["v=DKIM1; p=key"] if "s1._domainkey" in name else
        ["v=DMARC1; p=none"] if "_dmarc" in name else
        ["v=spf1 -all"]
    )
    res_dmarc_warn = verify_domain_dns("example.com", dkim_selector="s1", resolver=mock_res)
    assert res_dmarc_warn.verification_status == DomainVerificationStatus.WARNING.value
    assert "DMARC policy is set to p=none (warning)" in res_dmarc_warn.verification_error


def test_dns_failures_nxdomain_timeout_noanswer_errors():
    """Test safe handling of DNS exceptions (NXDOMAIN, Timeout, Temporary, Unexpected)."""
    mock_res = MagicMock(spec=DNSResolver)

    # NXDOMAIN
    mock_res.resolve_mx.side_effect = DNSDomainNotFoundError("NXDOMAIN")
    res_nx = verify_domain_dns("nonexistent.com", resolver=mock_res)
    assert res_nx.verification_status == DomainVerificationStatus.FAILED.value
    assert res_nx.verification_error == "DNS lookup failed: domain does not exist."
    assert res_nx.last_checked_at is not None

    # Timeout
    mock_res.resolve_mx.side_effect = DNSTimeoutError("Timeout")
    res_timeout = verify_domain_dns("timeout.com", resolver=mock_res)
    assert res_timeout.verification_status == DomainVerificationStatus.FAILED.value
    assert res_timeout.verification_error == "DNS resolution timed out."

    # Temporary Error
    mock_res.resolve_mx.side_effect = DNSTemporaryError("Temporary")
    res_temp = verify_domain_dns("temp-fail.com", resolver=mock_res)
    assert res_temp.verification_status == DomainVerificationStatus.FAILED.value
    assert res_temp.verification_error == "Temporary DNS resolution error."

    # Unexpected Exception
    mock_res.resolve_mx.side_effect = RuntimeError("Socket exploded")
    res_unexpected = verify_domain_dns("crash.com", resolver=mock_res)
    assert res_unexpected.verification_status == DomainVerificationStatus.FAILED.value
    assert res_unexpected.verification_error == "Unexpected DNS resolution failure."


# =============================================================================
# D4 POST /verify API & Authorization Tests (Mocked DNS)
# =============================================================================

@pytest.mark.asyncio
async def test_verify_api_owner_success_and_persistence(async_client: AsyncClient, db_session: AsyncSession):
    """Test that OWNER can trigger verification, updating DB fields and returning 200 OK."""
    token = await register_and_login(async_client, "owner_verify@domain.com")
    company_id = await create_company_helper(async_client, token, "Verify Owner Corp")

    create_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/domains",
        headers={"Authorization": f"Bearer {token}"},
        json={"domain_name": "verified-corp.com", "dkim_selector": "mail1"},
    )
    domain_id = create_resp.json()["id"]

    # Mock verify_domain_dns to return full VERIFIED result
    verified_result = DNSVerificationResult(
        mx_status=DomainVerificationStatus.VERIFIED.value,
        spf_status=DomainVerificationStatus.VERIFIED.value,
        dkim_status=DomainVerificationStatus.VERIFIED.value,
        dmarc_status=DomainVerificationStatus.VERIFIED.value,
        verification_status=DomainVerificationStatus.VERIFIED.value,
        verification_error=None,
        last_checked_at=datetime.now(timezone.utc),
    )

    with patch("app.services.dns.resolver.verify_domain_dns", return_value=verified_result):
        resp = await async_client.post(
            f"/api/v1/companies/{company_id}/domains/{domain_id}/verify",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["verification_status"] == "VERIFIED"
    assert data["mx_status"] == "VERIFIED"
    assert data["spf_status"] == "VERIFIED"
    assert data["dkim_status"] == "VERIFIED"
    assert data["dmarc_status"] == "VERIFIED"
    assert data["verification_error"] is None
    assert data["last_checked_at"] is not None

    # Check persistence directly in database
    db_domain = (await db_session.execute(select(Domain).where(Domain.id == domain_id))).scalar_one()
    assert db_domain.verification_status == DomainVerificationStatus.VERIFIED.value
    assert db_domain.last_checked_at is not None


@pytest.mark.asyncio
async def test_verify_api_admin_can_verify(async_client: AsyncClient):
    """Test that ADMIN can trigger verification."""
    token_owner = await register_and_login(async_client, "owner_admin_verify@domain.com")
    token_admin = await register_and_login(async_client, "admin_verifier@domain.com")
    company_id = await create_company_helper(async_client, token_owner, "Verify Admin Corp")
    await add_company_member_helper(async_client, token_owner, company_id, "admin_verifier@domain.com", role="ADMIN")

    create_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/domains",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"domain_name": "admin-verified.com"},
    )
    domain_id = create_resp.json()["id"]

    warn_result = DNSVerificationResult(
        mx_status=DomainVerificationStatus.VERIFIED.value,
        spf_status=DomainVerificationStatus.VERIFIED.value,
        dkim_status=DomainVerificationStatus.PENDING.value,
        dmarc_status=DomainVerificationStatus.VERIFIED.value,
        verification_status=DomainVerificationStatus.WARNING.value,
        verification_error="DKIM verification skipped: no selector configured.",
        last_checked_at=datetime.now(timezone.utc),
    )

    with patch("app.services.dns.resolver.verify_domain_dns", return_value=warn_result):
        resp = await async_client.post(
            f"/api/v1/companies/{company_id}/domains/{domain_id}/verify",
            headers={"Authorization": f"Bearer {token_admin}"},
        )
    assert resp.status_code == 200
    assert resp.json()["verification_status"] == "WARNING"


@pytest.mark.asyncio
async def test_verify_api_member_forbidden(async_client: AsyncClient):
    """Test that MEMBER receives 403 Forbidden when requesting verification."""
    token_owner = await register_and_login(async_client, "owner_for_verify_mem@domain.com")
    token_member = await register_and_login(async_client, "mem_verifier@domain.com")
    company_id = await create_company_helper(async_client, token_owner, "Verify Mem Corp")
    await add_company_member_helper(async_client, token_owner, company_id, "mem_verifier@domain.com", role="MEMBER")

    create_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/domains",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"domain_name": "mem-unverified.com"},
    )
    domain_id = create_resp.json()["id"]

    resp = await async_client.post(
        f"/api/v1/companies/{company_id}/domains/{domain_id}/verify",
        headers={"Authorization": f"Bearer {token_member}"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Owner or Administrator privileges required for this action"


@pytest.mark.asyncio
async def test_verify_api_foreign_domain_returns_404(async_client: AsyncClient):
    """Test anti-enumeration: attempting to verify a foreign domain ID returns 404."""
    token_a = await register_and_login(async_client, "verify_foreign_a@domain.com")
    token_b = await register_and_login(async_client, "verify_foreign_b@domain.com")
    co_a = await create_company_helper(async_client, token_a, "Verify Foreign Co A")
    co_b = await create_company_helper(async_client, token_b, "Verify Foreign Co B")

    create_resp = await async_client.post(
        f"/api/v1/companies/{co_b}/domains",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"domain_name": "target-verify-foreign.com"},
    )
    domain_b_id = create_resp.json()["id"]

    # User A tries to verify Co B's domain via Co A route -> 404 Not Found
    resp1 = await async_client.post(
        f"/api/v1/companies/{co_a}/domains/{domain_b_id}/verify",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp1.status_code == 404
    assert resp1.json()["detail"] == "Domain not found"

    # User A tries to verify via Co B route directly -> 404 Not Found
    resp2 = await async_client.post(
        f"/api/v1/companies/{co_b}/domains/{domain_b_id}/verify",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp2.status_code == 404
    assert resp2.json()["detail"] == "Company not found"


# =============================================================================
# D5 Hardening & Resilience Regression Tests
# =============================================================================

def test_dns_resolver_txt_unexpected_error_handling():
    """Test that unexpected exceptions during TXT checks for SPF/DKIM/DMARC fail safely without crashing."""
    mock_res = MagicMock(spec=DNSResolver)
    mock_res.resolve_mx.return_value = ["mail.example.com"]
    mock_res.resolve_txt.side_effect = RuntimeError("DNS TXT network driver fault")

    result = verify_domain_dns("faulty-dns.com", dkim_selector="s1", resolver=mock_res)
    assert result.mx_status == DomainVerificationStatus.VERIFIED.value
    assert result.spf_status == DomainVerificationStatus.FAILED.value
    assert result.dkim_status == DomainVerificationStatus.FAILED.value
    assert result.dmarc_status == DomainVerificationStatus.FAILED.value
    assert result.verification_status == DomainVerificationStatus.FAILED.value
    assert "SPF DNS lookup failed" in result.verification_error
    assert "DKIM DNS lookup failed" in result.verification_error
    assert "DMARC DNS lookup failed" in result.verification_error


@pytest.mark.asyncio
async def test_verify_domain_db_error_triggers_rollback(db_session: AsyncSession):
    """Test that database commit failure in verify_domain triggers session rollback and raises."""
    from app.modules.domains.service import DomainService

    company = Company(name="Rollback Test Co")
    db_session.add(company)
    await db_session.commit()
    await db_session.refresh(company)

    domain = Domain(company_id=company.id, domain_name="rollback-test.org")
    db_session.add(domain)
    await db_session.commit()
    await db_session.refresh(domain)

    # Patch db_session.commit to raise an exception
    with patch.object(db_session, "commit", side_effect=RuntimeError("Simulated DB disk failure")):
        with patch.object(db_session, "rollback", wraps=db_session.rollback) as mock_rollback:
            with pytest.raises(RuntimeError, match="Simulated DB disk failure"):
                await DomainService.verify_domain(
                    db=db_session,
                    company_id=company.id,
                    domain_id=domain.id,
                )
            mock_rollback.assert_awaited_once()



