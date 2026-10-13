from httpx import AsyncClient
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import User
from app.modules.campaigns.models import (
    Campaign,
    CampaignDelivery,
    CampaignRecipient,
    CampaignRecipientStatus,
    CampaignStatus,
    SuppressionEntry,
    SuppressionReason,
)
from app.modules.campaigns.preflight_service import CampaignPreflightService
from app.modules.campaigns.schemas import CampaignCreate
from app.modules.campaigns.service import CampaignService
from app.modules.campaigns.suppression_service import SuppressionService
from app.modules.companies.models import Company, CompanyRole, CompanyUser
from app.modules.domains.models import Domain, DomainVerificationStatus
from app.modules.email_accounts.models import EmailAccount
from app.modules.emails.models import Email


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


async def create_company_helper(client: AsyncClient, token: str, name: str = "Preflight Org") -> int:
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


async def create_domain_helper(
    client: AsyncClient,
    token: str,
    company_id: int,
    domain_name: str = "example.com",
) -> int:
    """Create a sending domain under a company and return its ID."""
    resp = await client.post(
        f"/api/v1/companies/{company_id}/domains",
        headers={"Authorization": f"Bearer {token}"},
        json={"domain_name": domain_name},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def create_email_account_helper(
    client: AsyncClient,
    token: str,
    company_id: int,
    email_address: str = "sender@example.com",
    name: str = "Primary Sender",
    domain_id: int = None,
) -> int:
    """Create an active email account under a company and return its ID."""
    payload = {
        "name": name,
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
    }
    if domain_id is not None:
        payload["domain_id"] = domain_id

    resp = await client.post(
        f"/api/v1/companies/{company_id}/email-accounts",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def create_campaign_helper(
    client: AsyncClient,
    token: str,
    company_id: int,
    email_account_id: int,
    name: str = "Product Launch",
    subject: str = "Welcome!",
    body_text: str = "Hello from our product launch.",
) -> int:
    """Create a DRAFT campaign and return its ID."""
    resp = await client.post(
        f"/api/v1/companies/{company_id}/campaigns",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": name,
            "email_account_id": email_account_id,
            "subject": subject,
            "body_text": body_text,
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def add_recipient_helper(
    client: AsyncClient,
    token: str,
    company_id: int,
    campaign_id: int,
    email: str,
) -> int:
    """Add a recipient to a campaign."""
    resp = await client.post(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/recipients",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": email},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


# =============================================================================
# 1. Campaign Eligibility and State Tests
# =============================================================================

@pytest.mark.asyncio
async def test_preflight_valid_campaign_eligible(async_client: AsyncClient, db_session: AsyncSession):
    """Test that a fully configured campaign with verified domain passes preflight with eligible=True."""
    token = await register_and_login(async_client, "owner_valid@org.com", "Owner Valid")
    company_id = await create_company_helper(async_client, token, "Valid Org")
    domain_id = await create_domain_helper(async_client, token, company_id, "org.com")

    # Set domain status to VERIFIED in DB
    domain = await db_session.get(Domain, domain_id)
    domain.verification_status = DomainVerificationStatus.VERIFIED.value
    await db_session.commit()

    account_id = await create_email_account_helper(
        async_client, token, company_id, email_address="sender@org.com", domain_id=domain_id
    )
    campaign_id = await create_campaign_helper(async_client, token, company_id, account_id)
    await add_recipient_helper(async_client, token, company_id, campaign_id, "lead1@customer.com")
    await add_recipient_helper(async_client, token, company_id, campaign_id, "lead2@customer.com")

    resp = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/preflight",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["eligible"] is True
    assert data["campaign_id"] == campaign_id
    assert data["recipient_count"] == 2
    assert data["eligible_recipient_count"] == 2
    assert data["suppressed_recipient_count"] == 0
    assert len(data["issues"]) == 0


@pytest.mark.asyncio
async def test_preflight_cross_company_isolation(async_client: AsyncClient):
    """Test that attempting to preflight another company's campaign returns 404 (anti-enumeration)."""
    token_a = await register_and_login(async_client, "owner_a_pf@org.com", "Owner A")
    company_a_id = await create_company_helper(async_client, token_a, "Org A")
    account_a_id = await create_email_account_helper(async_client, token_a, company_a_id, "sender@a.com")
    campaign_a_id = await create_campaign_helper(async_client, token_a, company_a_id, account_a_id)

    token_b = await register_and_login(async_client, "owner_b_pf@org.com", "Owner B")
    company_b_id = await create_company_helper(async_client, token_b, "Org B")

    # Try accessing Campaign A via Company B's endpoint
    resp = await async_client.post(
        f"/api/v1/companies/{company_b_id}/campaigns/{campaign_a_id}/preflight",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_preflight_terminal_and_running_campaigns_block(async_client: AsyncClient, db_session: AsyncSession):
    """Test that campaigns in terminal or running states produce blocking issues and eligible=False."""
    token = await register_and_login(async_client, "owner_term@org.com", "Owner Term")
    company_id = await create_company_helper(async_client, token, "Term Org")
    account_id = await create_email_account_helper(async_client, token, company_id, "sender@term.com")
    campaign_id = await create_campaign_helper(async_client, token, company_id, account_id)
    await add_recipient_helper(async_client, token, company_id, campaign_id, "user@customer.com")

    campaign = await db_session.get(Campaign, campaign_id)

    # 1. COMPLETED state
    campaign.status = CampaignStatus.COMPLETED.value
    await db_session.commit()

    resp = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/preflight",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["eligible"] is False
    codes = [i["code"] for i in data["issues"]]
    assert "CAMPAIGN_STATE_TERMINAL" in codes

    # 2. RUNNING state
    campaign.status = CampaignStatus.RUNNING.value
    await db_session.commit()

    resp_running = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/preflight",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_running.status_code == 200
    assert resp_running.json()["eligible"] is False
    codes = [i["code"] for i in resp_running.json()["issues"]]
    assert "CAMPAIGN_ALREADY_RUNNING" in codes


# =============================================================================
# 2. Sender Email Account Validation Tests
# =============================================================================

@pytest.mark.asyncio
async def test_preflight_inactive_sender_account_blocks(async_client: AsyncClient, db_session: AsyncSession):
    """Test that an inactive sender account produces a blocking issue."""
    token = await register_and_login(async_client, "owner_inactive_acc@org.com", "Owner Inactive")
    company_id = await create_company_helper(async_client, token, "Inactive Org")
    account_id = await create_email_account_helper(async_client, token, company_id, "sender@inactive.com")
    campaign_id = await create_campaign_helper(async_client, token, company_id, account_id)
    await add_recipient_helper(async_client, token, company_id, campaign_id, "user@cust.com")

    # Mark account inactive
    account = await db_session.get(EmailAccount, account_id)
    account.is_active = False
    await db_session.commit()

    resp = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/preflight",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["eligible"] is False
    codes = [i["code"] for i in data["issues"]]
    assert "SENDER_ACCOUNT_INACTIVE" in codes


@pytest.mark.asyncio
async def test_preflight_wrong_company_sender_account_blocks(async_client: AsyncClient, db_session: AsyncSession):
    """Test that a sender account referencing another company is blocked."""
    token = await register_and_login(async_client, "owner_acc_mismatch@org.com", "Owner Mismatch")
    company_a_id = await create_company_helper(async_client, token, "Company A")
    company_b_id = await create_company_helper(async_client, token, "Company B")

    account_b_id = await create_email_account_helper(async_client, token, company_b_id, "sender@b.com")
    account_a_id = await create_email_account_helper(async_client, token, company_a_id, "sender@a.com")

    campaign_id = await create_campaign_helper(async_client, token, company_a_id, account_a_id)
    await add_recipient_helper(async_client, token, company_a_id, campaign_id, "user@cust.com")

    # Directly alter campaign's email_account_id to Company B's account
    campaign = await db_session.get(Campaign, campaign_id)
    campaign.email_account_id = account_b_id
    await db_session.commit()

    resp = await async_client.post(
        f"/api/v1/companies/{company_a_id}/campaigns/{campaign_id}/preflight",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["eligible"] is False
    codes = [i["code"] for i in data["issues"]]
    assert "SENDER_ACCOUNT_WRONG_COMPANY" in codes


@pytest.mark.asyncio
async def test_preflight_unauthorized_email_account_blocks(async_client: AsyncClient, db_session: AsyncSession):
    """Test that evaluating preflight for a user not granted access to the account blocks execution."""
    token_owner = await register_and_login(async_client, "owner_perm@org.com", "Owner Perm")
    company_id = await create_company_helper(async_client, token_owner, "Perm Org")
    account_id = await create_email_account_helper(async_client, token_owner, company_id, "sender@perm.com")
    campaign_id = await create_campaign_helper(async_client, token_owner, company_id, account_id)
    await add_recipient_helper(async_client, token_owner, company_id, campaign_id, "user@cust.com")

    # Register regular member without explicit email account access
    token_member = await register_and_login(async_client, "member_noperm@org.com", "Member NoPerm")
    await add_company_member_helper(async_client, token_owner, company_id, "member_noperm@org.com", role="MEMBER")

    # Query the member user
    res = await db_session.execute(select(User).where(User.email == "member_noperm@org.com"))
    member_user = res.scalar_one()

    # Direct service call simulating member validation
    preflight_res = await CampaignPreflightService.validate_campaign(
        db=db_session,
        company_id=company_id,
        campaign_id=campaign_id,
        current_user=member_user,
        user_role="MEMBER",
    )
    assert preflight_res.eligible is False
    codes = [i.code for i in preflight_res.issues]
    assert "SENDER_ACCOUNT_UNAUTHORIZED" in codes


# =============================================================================
# 3. Domain Validation Tests
# =============================================================================

@pytest.mark.asyncio
async def test_preflight_domain_verification_statuses(async_client: AsyncClient, db_session: AsyncSession):
    """Test domain verification status handling: FAILED blocks; PENDING/WARNING warn; VERIFIED passes."""
    token = await register_and_login(async_client, "owner_dom_test@org.com", "Owner Dom")
    company_id = await create_company_helper(async_client, token, "Domain Status Org")
    domain_id = await create_domain_helper(async_client, token, company_id, "domstatus.com")
    account_id = await create_email_account_helper(
        async_client, token, company_id, "sender@domstatus.com", domain_id=domain_id
    )
    campaign_id = await create_campaign_helper(async_client, token, company_id, account_id)
    await add_recipient_helper(async_client, token, company_id, campaign_id, "cust@domstatus.com")

    domain = await db_session.get(Domain, domain_id)

    # Case A: FAILED blocks
    domain.verification_status = DomainVerificationStatus.FAILED.value
    await db_session.commit()

    resp_failed = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/preflight",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_failed.status_code == 200
    data_failed = resp_failed.json()
    assert data_failed["eligible"] is False
    assert any(i["code"] == "DOMAIN_VERIFICATION_FAILED" and i["blocking"] is True for i in data_failed["issues"])

    # Case B: PENDING warns (eligible remains True)
    domain.verification_status = DomainVerificationStatus.PENDING.value
    await db_session.commit()

    resp_pending = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/preflight",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_pending.status_code == 200
    data_pending = resp_pending.json()
    assert data_pending["eligible"] is True
    assert any(i["code"] == "DOMAIN_VERIFICATION_PENDING" and i["blocking"] is False for i in data_pending["issues"])

    # Case C: WARNING warns (eligible remains True)
    domain.verification_status = DomainVerificationStatus.WARNING.value
    await db_session.commit()

    resp_warning = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/preflight",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_warning.status_code == 200
    data_warning = resp_warning.json()
    assert data_warning["eligible"] is True
    assert any(i["code"] == "DOMAIN_VERIFICATION_WARNING" and i["blocking"] is False for i in data_warning["issues"])

    # Case D: VERIFIED passes with no domain issues
    domain.verification_status = DomainVerificationStatus.VERIFIED.value
    await db_session.commit()

    resp_verified = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/preflight",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_verified.status_code == 200
    data_verified = resp_verified.json()
    assert data_verified["eligible"] is True
    assert not any("DOMAIN" in i["code"] for i in data_verified["issues"])


@pytest.mark.asyncio
async def test_preflight_domain_mismatch_blocks(async_client: AsyncClient, db_session: AsyncSession):
    """Test that mismatch between sender email address domain and assigned domain blocks preflight."""
    token = await register_and_login(async_client, "owner_dom_mismatch@org.com", "Owner DomMis")
    company_id = await create_company_helper(async_client, token, "Mismatch Org")
    domain_id = await create_domain_helper(async_client, token, company_id, "correctdomain.com")
    account_id = await create_email_account_helper(
        async_client, token, company_id, "sender@correctdomain.com", domain_id=domain_id
    )
    campaign_id = await create_campaign_helper(async_client, token, company_id, account_id)
    await add_recipient_helper(async_client, token, company_id, campaign_id, "cust@lead.com")

    # Artificially alter email_address to a different domain directly in DB
    account = await db_session.get(EmailAccount, account_id)
    account.email_address = "sender@otherdomain.com"
    await db_session.commit()

    resp = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/preflight",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["eligible"] is False
    codes = [i["code"] for i in data["issues"]]
    assert "DOMAIN_MISMATCH" in codes


# =============================================================================
# 4. Recipient and Suppression Validation Tests
# =============================================================================

@pytest.mark.asyncio
async def test_preflight_zero_recipients_blocks(async_client: AsyncClient, db_session: AsyncSession):
    """Test that a campaign with zero recipients blocks preflight with NO_RECIPIENTS."""
    token = await register_and_login(async_client, "owner_zero_recip@org.com", "Owner Zero")
    company_id = await create_company_helper(async_client, token, "Zero Recip Org")
    account_id = await create_email_account_helper(async_client, token, company_id, "sender@zero.com")
    campaign_id = await create_campaign_helper(async_client, token, company_id, account_id)

    resp = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/preflight",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["eligible"] is False
    assert data["recipient_count"] == 0
    assert data["eligible_recipient_count"] == 0
    codes = [i["code"] for i in data["issues"]]
    assert "NO_RECIPIENTS" in codes


@pytest.mark.asyncio
async def test_preflight_all_recipients_suppressed_blocks(async_client: AsyncClient, db_session: AsyncSession):
    """Test that a campaign where all recipients are suppressed produces eligible=False and NO_ELIGIBLE_RECIPIENTS."""
    token = await register_and_login(async_client, "owner_all_supp@org.com", "Owner AllSupp")
    company_id = await create_company_helper(async_client, token, "All Supp Org")
    account_id = await create_email_account_helper(async_client, token, company_id, "sender@allsupp.com")
    campaign_id = await create_campaign_helper(async_client, token, company_id, account_id)

    # Add 2 recipients
    await add_recipient_helper(async_client, token, company_id, campaign_id, "supp1@target.com")
    await add_recipient_helper(async_client, token, company_id, campaign_id, "supp2@target.com")

    # Suppress both recipients in this company
    await async_client.post(
        f"/api/v1/companies/{company_id}/suppressions",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "supp1@target.com", "reason": "UNSUBSCRIBE"},
    )
    await async_client.post(
        f"/api/v1/companies/{company_id}/suppressions",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "supp2@target.com", "reason": "BOUNCE"},
    )

    resp = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/preflight",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["eligible"] is False
    assert data["recipient_count"] == 2
    assert data["eligible_recipient_count"] == 0
    assert data["suppressed_recipient_count"] == 2
    codes = [i["code"] for i in data["issues"]]
    assert "NO_ELIGIBLE_RECIPIENTS" in codes


@pytest.mark.asyncio
async def test_preflight_partially_suppressed_remains_eligible(async_client: AsyncClient):
    """Test that a campaign with some suppressed recipients remains eligible if at least 1 recipient is eligible."""
    token = await register_and_login(async_client, "owner_part_supp@org.com", "Owner PartSupp")
    company_id = await create_company_helper(async_client, token, "Part Supp Org")
    account_id = await create_email_account_helper(async_client, token, company_id, "sender@partsupp.com")
    campaign_id = await create_campaign_helper(async_client, token, company_id, account_id)

    await add_recipient_helper(async_client, token, company_id, campaign_id, "valid@target.com")
    await add_recipient_helper(async_client, token, company_id, campaign_id, "suppressed@target.com")

    # Suppress only one
    await async_client.post(
        f"/api/v1/companies/{company_id}/suppressions",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "suppressed@target.com", "reason": "MANUAL"},
    )

    resp = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/preflight",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["eligible"] is True
    assert data["recipient_count"] == 2
    assert data["eligible_recipient_count"] == 1
    assert data["suppressed_recipient_count"] == 1
    # RECIPIENTS_SUPPRESSED warning present
    assert any(i["code"] == "RECIPIENTS_SUPPRESSED" and i["blocking"] is False for i in data["issues"])


@pytest.mark.asyncio
async def test_preflight_suppression_is_company_isolated(async_client: AsyncClient):
    """Test that a suppression entry in Company B does not suppress a recipient in Company A."""
    token_a = await register_and_login(async_client, "owner_iso_a@org.com", "Owner Iso A")
    company_a_id = await create_company_helper(async_client, token_a, "Company A Iso")
    account_a_id = await create_email_account_helper(async_client, token_a, company_a_id, "sender@a-iso.com")
    campaign_a_id = await create_campaign_helper(async_client, token_a, company_a_id, account_a_id)
    await add_recipient_helper(async_client, token_a, company_a_id, campaign_a_id, "shared@external.com")

    token_b = await register_and_login(async_client, "owner_iso_b@org.com", "Owner Iso B")
    company_b_id = await create_company_helper(async_client, token_b, "Company B Iso")

    # Suppress shared@external.com in Company B
    await async_client.post(
        f"/api/v1/companies/{company_b_id}/suppressions",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"email": "shared@external.com", "reason": "COMPLAINT"},
    )

    # Preflight Company A: should NOT be suppressed
    resp = await async_client.post(
        f"/api/v1/companies/{company_a_id}/campaigns/{campaign_a_id}/preflight",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["eligible"] is True
    assert data["recipient_count"] == 1
    assert data["eligible_recipient_count"] == 1
    assert data["suppressed_recipient_count"] == 0


# =============================================================================
# 5. Content Validation Tests
# =============================================================================

@pytest.mark.asyncio
async def test_preflight_missing_subject_or_content_blocks(async_client: AsyncClient, db_session: AsyncSession):
    """Test that missing subject or empty body text and HTML blocks campaign preflight."""
    token = await register_and_login(async_client, "owner_content_test@org.com", "Owner Content")
    company_id = await create_company_helper(async_client, token, "Content Org")
    account_id = await create_email_account_helper(async_client, token, company_id, "sender@content.com")
    campaign_id = await create_campaign_helper(async_client, token, company_id, account_id)
    await add_recipient_helper(async_client, token, company_id, campaign_id, "cust@content.com")

    campaign = await db_session.get(Campaign, campaign_id)

    # 1. Missing subject
    campaign.subject = ""
    await db_session.commit()

    resp_no_subj = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/preflight",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_no_subj.status_code == 200
    data_no_subj = resp_no_subj.json()
    assert data_no_subj["eligible"] is False
    codes = [i["code"] for i in data_no_subj["issues"]]
    assert "MISSING_SUBJECT" in codes

    # 2. Missing body (both text and html empty)
    campaign.subject = "Valid Subject"
    campaign.body_text = None
    campaign.body_html = "   "
    await db_session.commit()

    resp_no_body = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/preflight",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_no_body.status_code == 200
    data_no_body = resp_no_body.json()
    assert data_no_body["eligible"] is False
    codes = [i["code"] for i in data_no_body["issues"]]
    assert "MISSING_CONTENT" in codes


# =============================================================================
# 6. Read-Only Guarantees Tests
# =============================================================================

@pytest.mark.asyncio
async def test_preflight_is_strictly_read_only(async_client: AsyncClient, db_session: AsyncSession):
    """Test that preflight produces zero side-effects across all campaign tables."""
    token = await register_and_login(async_client, "owner_readonly@org.com", "Owner Readonly")
    company_id = await create_company_helper(async_client, token, "Readonly Org")
    account_id = await create_email_account_helper(async_client, token, company_id, "sender@readonly.com")
    campaign_id = await create_campaign_helper(async_client, token, company_id, account_id)
    recip_id = await add_recipient_helper(async_client, token, company_id, campaign_id, "recip@readonly.com")

    # Add suppression entry
    await async_client.post(
        f"/api/v1/companies/{company_id}/suppressions",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "recip@readonly.com", "reason": "UNSUBSCRIBE"},
    )

    # Record states before preflight
    campaign_before = await db_session.get(Campaign, campaign_id)
    recip_before = await db_session.get(CampaignRecipient, recip_id)
    deliv_count_before = (await db_session.execute(select(CampaignDelivery))).scalars().all()
    emails_count_before = (await db_session.execute(select(Email))).scalars().all()

    assert campaign_before.status == CampaignStatus.DRAFT.value
    assert recip_before.status == CampaignRecipientStatus.PENDING.value

    # Execute preflight
    resp = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/preflight",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200

    # Query states after preflight
    await db_session.refresh(campaign_before)
    await db_session.refresh(recip_before)
    deliv_count_after = (await db_session.execute(select(CampaignDelivery))).scalars().all()
    emails_count_after = (await db_session.execute(select(Email))).scalars().all()

    # Invariants guaranteed:
    assert campaign_before.status == CampaignStatus.DRAFT.value
    assert recip_before.status == CampaignRecipientStatus.PENDING.value  # Recipient not modified to SUPPRESSED
    assert len(deliv_count_after) == len(deliv_count_before)  # Zero CampaignDelivery records created
    assert len(emails_count_after) == len(emails_count_before)  # Zero Email rows created


# =============================================================================
# 7. Authorization Tests
# =============================================================================

@pytest.mark.asyncio
async def test_preflight_authorization_rules(async_client: AsyncClient):
    """Test that OWNER/ADMIN can invoke preflight, while regular MEMBER is rejected with 403."""
    token_owner = await register_and_login(async_client, "owner_auth_pf@org.com", "Owner AuthPF")
    company_id = await create_company_helper(async_client, token_owner, "AuthPF Org")
    account_id = await create_email_account_helper(async_client, token_owner, company_id, "sender@authpf.com")
    campaign_id = await create_campaign_helper(async_client, token_owner, company_id, account_id)
    await add_recipient_helper(async_client, token_owner, company_id, campaign_id, "cust@authpf.com")

    # 1. OWNER can preflight
    resp_owner = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/preflight",
        headers={"Authorization": f"Bearer {token_owner}"},
    )
    assert resp_owner.status_code == 200

    # 2. ADMIN can preflight
    token_admin = await register_and_login(async_client, "admin_auth_pf@org.com", "Admin AuthPF")
    await add_company_member_helper(async_client, token_owner, company_id, "admin_auth_pf@org.com", role="ADMIN")
    resp_admin = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/preflight",
        headers={"Authorization": f"Bearer {token_admin}"},
    )
    assert resp_admin.status_code == 200

    # 3. MEMBER is rejected with 403 Forbidden
    token_member = await register_and_login(async_client, "member_auth_pf@org.com", "Member AuthPF")
    await add_company_member_helper(async_client, token_owner, company_id, "member_auth_pf@org.com", role="MEMBER")
    resp_member = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/preflight",
        headers={"Authorization": f"Bearer {token_member}"},
    )
    assert resp_member.status_code == 403
