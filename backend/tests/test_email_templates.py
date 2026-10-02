from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.emails.models import Email, EmailDirection, EmailStatus, EmailTemplate, EmailThread
from app.services.smtp.adapter import StandardSMTPAdapter
from app.services.smtp.client import SMTPClient


# =============================================================================
# Helper Utilities
# =============================================================================

async def register_and_login(client: AsyncClient, email: str, name: str = "Test User") -> str:
    """Register and log in a user, returning their JWT bearer token."""
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
    """Create a company and return its ID."""
    resp = await client.post(
        "/api/v1/companies/",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": name},
    )
    return resp.json()["id"]


async def create_account_helper(
    client: AsyncClient,
    token: str,
    company_id: int,
    name: str = "Support Desk",
    email: str = "support@company.com",
    password: str = "Secret123!",
    smtp_host: str = "smtp.company.com",
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


async def create_draft_helper(
    client: AsyncClient,
    token: str,
    account_id: int,
    subject: str = "Initial Draft Subject",
    body_text: str = "Initial draft body text",
    body_html: str = "<p>Initial draft HTML</p>",
    to: list = None,
    thread_id: int = None,
    in_reply_to: str = None,
) -> int:
    """Create a draft and return its ID."""
    resp = await client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "email_account_id": account_id,
            "to": to or ["customer@example.com"],
            "subject": subject,
            "body_text": body_text,
            "body_html": body_html,
            "thread_id": thread_id,
            "in_reply_to": in_reply_to,
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


# =============================================================================
# 1. Template Creation Tests (1 - 4)
# =============================================================================

@pytest.mark.asyncio
async def test_01_create_template(async_client: AsyncClient, db_session: AsyncSession):
    """1. Create template with standard name and subject."""
    token = await register_and_login(async_client, "tmpl_user_01@test.com")
    comp_id = await create_company_helper(async_client, token, "Tmpl Co 01")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support01@tmpl.com")

    resp = await async_client.post(
        f"/api/v1/companies/{comp_id}/emails/templates",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Welcome Template",
            "subject": "Welcome to our Service",
            "body_text": "Hello, welcome to our platform!",
            "email_account_id": acc_id,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"] is not None
    assert data["name"] == "Welcome Template"
    assert data["subject"] == "Welcome to our Service"
    assert data["body_text"] == "Hello, welcome to our platform!"
    assert data["body_html"] is None
    assert data["company_id"] == comp_id
    assert data["email_account_id"] == acc_id
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_02_create_template_plain_text(async_client: AsyncClient, db_session: AsyncSession):
    """2. Create template with plain-text content only."""
    token = await register_and_login(async_client, "tmpl_user_02@test.com")
    comp_id = await create_company_helper(async_client, token, "Tmpl Co 02")

    resp = await async_client.post(
        f"/api/v1/companies/{comp_id}/templates",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Plain Text Only",
            "subject": "Plain Subject",
            "body_text": "Only plain text content here.",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["body_text"] == "Only plain text content here."
    assert data["body_html"] is None


@pytest.mark.asyncio
async def test_03_create_template_html_content(async_client: AsyncClient, db_session: AsyncSession):
    """3. Create template with HTML content only."""
    token = await register_and_login(async_client, "tmpl_user_03@test.com")
    comp_id = await create_company_helper(async_client, token, "Tmpl Co 03")

    resp = await async_client.post(
        "/api/v1/emails/templates",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "HTML Only Template",
            "subject": "HTML Notice",
            "body_html": "<h1>Important Announcement</h1><p>Details here.</p>",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["body_text"] is None
    assert data["body_html"] == "<h1>Important Announcement</h1><p>Details here.</p>"


@pytest.mark.asyncio
async def test_04_create_template_subject_and_both_bodies(async_client: AsyncClient, db_session: AsyncSession):
    """4. Create template with subject, plain text, and HTML body."""
    token = await register_and_login(async_client, "tmpl_user_04@test.com")
    comp_id = await create_company_helper(async_client, token, "Tmpl Co 04")

    resp = await async_client.post(
        f"/api/v1/companies/{comp_id}/emails/templates",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Full Multi-part Template",
            "subject": "Multi-part Subject",
            "body_text": "Plain fallback text",
            "body_html": "<p>Rich formatted body</p>",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Full Multi-part Template"
    assert data["subject"] == "Multi-part Subject"
    assert data["body_text"] == "Plain fallback text"
    assert data["body_html"] == "<p>Rich formatted body</p>"


# =============================================================================
# 2. Template Retrieval, List, Update, Delete & Toggle (5 - 9)
# =============================================================================

@pytest.mark.asyncio
async def test_05_list_templates(async_client: AsyncClient, db_session: AsyncSession):
    """5. List templates with pagination, active filter, and company scoping."""
    token = await register_and_login(async_client, "tmpl_user_05@test.com")
    comp_id = await create_company_helper(async_client, token, "Tmpl Co 05")

    # Create 3 templates
    for i in range(3):
        await async_client.post(
            f"/api/v1/companies/{comp_id}/templates",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": f"Template {i+1}", "subject": f"Subject {i+1}", "is_active": i < 2},
        )

    # List all in company
    resp = await async_client.get(
        f"/api/v1/companies/{comp_id}/templates",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert len(data["templates"]) == 3

    # Filter by is_active=true
    resp_active = await async_client.get(
        f"/api/v1/companies/{comp_id}/templates?is_active=true",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_active.status_code == 200
    assert resp_active.json()["total"] == 2

    # Filter with limit=1, offset=1
    resp_page = await async_client.get(
        f"/api/v1/companies/{comp_id}/templates?limit=1&offset=1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_page.status_code == 200
    assert len(resp_page.json()["templates"]) == 1


@pytest.mark.asyncio
async def test_06_retrieve_template_by_id(async_client: AsyncClient, db_session: AsyncSession):
    """6. Retrieve template by ID."""
    token = await register_and_login(async_client, "tmpl_user_06@test.com")
    comp_id = await create_company_helper(async_client, token, "Tmpl Co 06")

    create_resp = await async_client.post(
        f"/api/v1/companies/{comp_id}/templates",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Fetch Me", "subject": "Specific Subject", "body_text": "Sample Body"},
    )
    tmpl_id = create_resp.json()["id"]

    # Global endpoint
    resp = await async_client.get(
        f"/api/v1/emails/templates/{tmpl_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == tmpl_id
    assert resp.json()["name"] == "Fetch Me"

    # Company-scoped endpoint
    resp_comp = await async_client.get(
        f"/api/v1/companies/{comp_id}/emails/templates/{tmpl_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_comp.status_code == 200
    assert resp_comp.json()["id"] == tmpl_id


@pytest.mark.asyncio
async def test_07_update_template(async_client: AsyncClient, db_session: AsyncSession):
    """7. Update template name, subject, body_text, body_html, and active status."""
    token = await register_and_login(async_client, "tmpl_user_07@test.com")
    comp_id = await create_company_helper(async_client, token, "Tmpl Co 07")

    create_resp = await async_client.post(
        f"/api/v1/companies/{comp_id}/templates",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Old Name", "subject": "Old Subject", "body_text": "Old text"},
    )
    tmpl_id = create_resp.json()["id"]

    update_resp = await async_client.put(
        f"/api/v1/emails/templates/{tmpl_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "New Updated Name",
            "subject": "New Subject",
            "body_text": "Updated body text",
            "body_html": "<p>Added HTML</p>",
            "is_active": False,
        },
    )
    assert update_resp.status_code == 200
    data = update_resp.json()
    assert data["name"] == "New Updated Name"
    assert data["subject"] == "New Subject"
    assert data["body_text"] == "Updated body text"
    assert data["body_html"] == "<p>Added HTML</p>"
    assert data["is_active"] is False


@pytest.mark.asyncio
async def test_08_delete_template(async_client: AsyncClient, db_session: AsyncSession):
    """8. Delete template using standard deletion (hard delete)."""
    token = await register_and_login(async_client, "tmpl_user_08@test.com")
    comp_id = await create_company_helper(async_client, token, "Tmpl Co 08")

    create_resp = await async_client.post(
        f"/api/v1/companies/{comp_id}/templates",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "To Be Deleted", "subject": "Subject"},
    )
    tmpl_id = create_resp.json()["id"]

    # Delete template
    del_resp = await async_client.delete(
        f"/api/v1/emails/templates/{tmpl_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_resp.status_code == 204

    # Subsequent GET returns 404
    get_resp = await async_client.get(
        f"/api/v1/emails/templates/{tmpl_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_09_activate_deactivate_template(async_client: AsyncClient, db_session: AsyncSession):
    """9. Activate and deactivate template via toggle endpoint."""
    token = await register_and_login(async_client, "tmpl_user_09@test.com")
    comp_id = await create_company_helper(async_client, token, "Tmpl Co 09")

    create_resp = await async_client.post(
        f"/api/v1/companies/{comp_id}/templates",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Toggle Template", "subject": "Subject", "is_active": True},
    )
    tmpl_id = create_resp.json()["id"]

    # Deactivate
    deact_resp = await async_client.patch(
        f"/api/v1/emails/templates/{tmpl_id}/active",
        headers={"Authorization": f"Bearer {token}"},
        json={"is_active": False},
    )
    assert deact_resp.status_code == 200
    assert deact_resp.json()["is_active"] is False

    # Toggle back to active without body
    act_resp = await async_client.patch(
        f"/api/v1/emails/templates/{tmpl_id}/active",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert act_resp.status_code == 200
    assert act_resp.json()["is_active"] is True


# =============================================================================
# 3. Authorization & Cross-Company Security Tests (10 - 14)
# =============================================================================

@pytest.mark.asyncio
async def test_10_unauthorized_user_cannot_create_template(async_client: AsyncClient, db_session: AsyncSession):
    """10. Unauthorized user cannot create template for a company they do not belong to."""
    token_owner = await register_and_login(async_client, "tmpl_user_10_owner@test.com")
    comp_id = await create_company_helper(async_client, token_owner, "Tmpl Co 10")

    token_unauth = await register_and_login(async_client, "tmpl_user_10_stranger@test.com")

    resp = await async_client.post(
        f"/api/v1/companies/{comp_id}/templates",
        headers={"Authorization": f"Bearer {token_unauth}"},
        json={"name": "Illegal Template", "subject": "Subject"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_11_unauthorized_user_cannot_retrieve_template(async_client: AsyncClient, db_session: AsyncSession):
    """11. Unauthorized user cannot retrieve template belonging to another company."""
    token_owner = await register_and_login(async_client, "tmpl_user_11_owner@test.com")
    comp_id = await create_company_helper(async_client, token_owner, "Tmpl Co 11")

    create_resp = await async_client.post(
        f"/api/v1/companies/{comp_id}/templates",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"name": "Private Template", "subject": "Subject"},
    )
    tmpl_id = create_resp.json()["id"]

    token_unauth = await register_and_login(async_client, "tmpl_user_11_stranger@test.com")
    resp = await async_client.get(
        f"/api/v1/emails/templates/{tmpl_id}",
        headers={"Authorization": f"Bearer {token_unauth}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_12_unauthorized_user_cannot_update_template(async_client: AsyncClient, db_session: AsyncSession):
    """12. Unauthorized user cannot update another company's template."""
    token_owner = await register_and_login(async_client, "tmpl_user_12_owner@test.com")
    comp_id = await create_company_helper(async_client, token_owner, "Tmpl Co 12")

    create_resp = await async_client.post(
        f"/api/v1/companies/{comp_id}/templates",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"name": "Protected Template", "subject": "Subject"},
    )
    tmpl_id = create_resp.json()["id"]

    token_unauth = await register_and_login(async_client, "tmpl_user_12_stranger@test.com")
    resp = await async_client.put(
        f"/api/v1/emails/templates/{tmpl_id}",
        headers={"Authorization": f"Bearer {token_unauth}"},
        json={"name": "Hacked Template"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_13_unauthorized_user_cannot_delete_template(async_client: AsyncClient, db_session: AsyncSession):
    """13. Unauthorized user cannot delete another company's template."""
    token_owner = await register_and_login(async_client, "tmpl_user_13_owner@test.com")
    comp_id = await create_company_helper(async_client, token_owner, "Tmpl Co 13")

    create_resp = await async_client.post(
        f"/api/v1/companies/{comp_id}/templates",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"name": "Protected Template", "subject": "Subject"},
    )
    tmpl_id = create_resp.json()["id"]

    token_unauth = await register_and_login(async_client, "tmpl_user_13_stranger@test.com")
    resp = await async_client.delete(
        f"/api/v1/emails/templates/{tmpl_id}",
        headers={"Authorization": f"Bearer {token_unauth}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_14_cross_company_template_access_is_rejected(async_client: AsyncClient, db_session: AsyncSession):
    """14. Cross-company template route access is strictly rejected."""
    token_a = await register_and_login(async_client, "tmpl_user_14_a@test.com")
    comp_a = await create_company_helper(async_client, token_a, "Company A")

    token_b = await register_and_login(async_client, "tmpl_user_14_b@test.com")
    comp_b = await create_company_helper(async_client, token_b, "Company B")

    create_resp = await async_client.post(
        f"/api/v1/companies/{comp_a}/templates",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"name": "Company A Template", "subject": "Subject A"},
    )
    tmpl_id = create_resp.json()["id"]

    # User B requests template A via Company B scoped endpoint
    resp = await async_client.get(
        f"/api/v1/companies/{comp_b}/templates/{tmpl_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp.status_code in [403, 404]


# =============================================================================
# 4. Template -> Draft Application Tests (15 - 26)
# =============================================================================

@pytest.mark.asyncio
async def test_15_inactive_template_cannot_be_applied(async_client: AsyncClient, db_session: AsyncSession):
    """15. Inactive template cannot be applied to a draft (400 Bad Request)."""
    token = await register_and_login(async_client, "tmpl_user_15@test.com")
    comp_id = await create_company_helper(async_client, token, "Tmpl Co 15")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support15@tmpl.com")
    draft_id = await create_draft_helper(async_client, token, acc_id)

    tmpl_resp = await async_client.post(
        f"/api/v1/companies/{comp_id}/templates",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Inactive Template", "subject": "Subject", "is_active": False},
    )
    tmpl_id = tmpl_resp.json()["id"]

    apply_resp = await async_client.post(
        f"/api/v1/emails/drafts/{draft_id}/apply-template/{tmpl_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert apply_resp.status_code == 400
    assert "inactive" in apply_resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_16_authorized_template_applied_to_draft(async_client: AsyncClient, db_session: AsyncSession):
    """16. Authorized active template can be successfully applied to an active draft."""
    token = await register_and_login(async_client, "tmpl_user_16@test.com")
    comp_id = await create_company_helper(async_client, token, "Tmpl Co 16")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support16@tmpl.com")
    draft_id = await create_draft_helper(async_client, token, acc_id)

    tmpl_resp = await async_client.post(
        f"/api/v1/companies/{comp_id}/templates",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Standard Welcome",
            "subject": "New Template Subject",
            "body_text": "New Template Body Text",
            "body_html": "<p>New Template HTML</p>",
        },
    )
    tmpl_id = tmpl_resp.json()["id"]

    apply_resp = await async_client.post(
        f"/api/v1/emails/drafts/{draft_id}/apply-template/{tmpl_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert apply_resp.status_code == 200
    data = apply_resp.json()
    assert data["id"] == draft_id
    assert data["subject"] == "New Template Subject"
    assert data["body_text"] == "New Template Body Text"
    assert data["body_html"] == "<p>New Template HTML</p>"
    assert data["status"] == "DRAFT"


@pytest.mark.asyncio
async def test_17_18_19_template_copies_subject_text_html(async_client: AsyncClient, db_session: AsyncSession):
    """17, 18, 19. Applying template copies subject, body_text, and body_html exactly."""
    token = await register_and_login(async_client, "tmpl_user_17@test.com")
    comp_id = await create_company_helper(async_client, token, "Tmpl Co 17")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support17@tmpl.com")
    draft_id = await create_draft_helper(
        async_client,
        token,
        acc_id,
        subject="Old Subject",
        body_text="Old Text",
        body_html="<p>Old HTML</p>",
    )

    tmpl_resp = await async_client.post(
        f"/api/v1/companies/{comp_id}/templates",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Replacer Template",
            "subject": "Copied Subject",
            "body_text": "Copied Text Content",
            "body_html": "<div>Copied HTML Content</div>",
        },
    )
    tmpl_id = tmpl_resp.json()["id"]

    apply_resp = await async_client.post(
        f"/api/v1/emails/drafts/{draft_id}/apply-template/{tmpl_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert apply_resp.status_code == 200
    data = apply_resp.json()
    # 17: copies subject
    assert data["subject"] == "Copied Subject"
    # 18: copies body_text
    assert data["body_text"] == "Copied Text Content"
    # 19: copies body_html
    assert data["body_html"] == "<div>Copied HTML Content</div>"


@pytest.mark.asyncio
async def test_20_applying_template_preserves_recipients(async_client: AsyncClient, db_session: AsyncSession):
    """20. Applying template preserves all recipients (to, cc, bcc, reply_to)."""
    token = await register_and_login(async_client, "tmpl_user_20@test.com")
    comp_id = await create_company_helper(async_client, token, "Tmpl Co 20")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support20@tmpl.com")

    # Create draft with to, cc, bcc
    draft_resp = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "email_account_id": acc_id,
            "to": ["dest1@example.com", "dest2@example.com"],
            "cc": ["cc1@example.com"],
            "bcc": ["bcc1@example.com"],
            "reply_to": "reply@example.com",
            "subject": "Before Subject",
        },
    )
    draft_id = draft_resp.json()["id"]

    tmpl_resp = await async_client.post(
        f"/api/v1/companies/{comp_id}/templates",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Content Only Template", "subject": "After Subject", "body_text": "New body"},
    )
    tmpl_id = tmpl_resp.json()["id"]

    apply_resp = await async_client.post(
        f"/api/v1/emails/drafts/{draft_id}/apply-template/{tmpl_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert apply_resp.status_code == 200
    data = apply_resp.json()
    # Content replaced
    assert data["subject"] == "After Subject"
    assert data["body_text"] == "New body"
    # Recipients preserved
    assert data["recipients"] == ["dest1@example.com", "dest2@example.com"]
    assert data["cc"] == ["cc1@example.com"]
    assert data["bcc"] == ["bcc1@example.com"]
    assert data["reply_to"] == "reply@example.com"


@pytest.mark.asyncio
async def test_21_applying_template_preserves_thread_metadata(async_client: AsyncClient, db_session: AsyncSession):
    """21. Applying template preserves thread/reply metadata (thread_id, in_reply_to, references_header)."""
    token = await register_and_login(async_client, "tmpl_user_21@test.com")
    comp_id = await create_company_helper(async_client, token, "Tmpl Co 21")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support21@tmpl.com")

    # Create thread directly in DB
    thread = EmailThread(
        company_id=comp_id,
        email_account_id=acc_id,
        subject="Parent Conversation",
        message_count=1,
        has_reply=False,
        last_message_at=datetime.now(timezone.utc),
    )
    db_session.add(thread)
    await db_session.flush()

    # Create parent email in the thread
    parent_email = Email(
        company_id=comp_id,
        email_account_id=acc_id,
        thread_id=thread.id,
        message_id="<parent123@domain.com>",
        direction=EmailDirection.INCOMING.value,
        status=EmailStatus.RECEIVED.value,
        sender="customer@domain.com",
        recipients=["support21@tmpl.com"],
        subject="Parent Conversation",
        is_deleted=False,
    )
    db_session.add(parent_email)
    await db_session.commit()
    await db_session.refresh(thread)

    draft_id = await create_draft_helper(
        async_client,
        token,
        acc_id,
        thread_id=thread.id,
        in_reply_to="<parent123@domain.com>",
    )

    tmpl_resp = await async_client.post(
        f"/api/v1/companies/{comp_id}/templates",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Reply Template", "subject": "Re: Parent Conversation", "body_text": "Thank you for reaching out."},
    )
    tmpl_id = tmpl_resp.json()["id"]

    apply_resp = await async_client.post(
        f"/api/v1/emails/drafts/{draft_id}/apply-template/{tmpl_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert apply_resp.status_code == 200
    data = apply_resp.json()
    assert data["thread_id"] == thread.id
    assert data["in_reply_to"] == "<parent123@domain.com>"
    assert data["subject"] == "Re: Parent Conversation"


@pytest.mark.asyncio
async def test_22_23_template_does_not_send_or_change_draft_status(async_client: AsyncClient, db_session: AsyncSession):
    """22, 23. Applying template does not call SMTP and does not change status from DRAFT."""
    token = await register_and_login(async_client, "tmpl_user_22@test.com")
    comp_id = await create_company_helper(async_client, token, "Tmpl Co 22")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support22@tmpl.com")
    draft_id = await create_draft_helper(async_client, token, acc_id)

    tmpl_resp = await async_client.post(
        f"/api/v1/companies/{comp_id}/templates",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Safe Template", "subject": "No Send", "body_text": "Content"},
    )
    tmpl_id = tmpl_resp.json()["id"]

    # Mock StandardSMTPAdapter.send to ensure it is never called
    with patch.object(StandardSMTPAdapter, "send", new_callable=AsyncMock) as mock_send:
        apply_resp = await async_client.post(
            f"/api/v1/emails/drafts/{draft_id}/apply-template/{tmpl_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert apply_resp.status_code == 200
        mock_send.assert_not_called()

    data = apply_resp.json()
    assert data["status"] == "DRAFT"
    assert data["sent_at"] is None


@pytest.mark.asyncio
async def test_24_applying_template_does_not_modify_thread_metrics(async_client: AsyncClient, db_session: AsyncSession):
    """24. Applying template does not modify thread metrics (message_count and has_reply)."""
    token = await register_and_login(async_client, "tmpl_user_24@test.com")
    comp_id = await create_company_helper(async_client, token, "Tmpl Co 24")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support24@tmpl.com")

    thread = EmailThread(
        company_id=comp_id,
        email_account_id=acc_id,
        subject="Metrics Thread",
        message_count=1,
        has_reply=False,
        last_message_at=datetime.now(timezone.utc),
    )
    db_session.add(thread)
    await db_session.commit()
    await db_session.refresh(thread)

    draft_id = await create_draft_helper(async_client, token, acc_id, thread_id=thread.id)

    tmpl_resp = await async_client.post(
        f"/api/v1/companies/{comp_id}/templates",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Tmpl", "subject": "Subject", "body_text": "Body"},
    )
    tmpl_id = tmpl_resp.json()["id"]

    await async_client.post(
        f"/api/v1/emails/drafts/{draft_id}/apply-template/{tmpl_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    # Refresh thread from DB and verify metrics
    await db_session.refresh(thread)
    assert thread.message_count == 1
    assert thread.has_reply is False



@pytest.mark.asyncio
async def test_25_applying_template_to_deleted_or_non_draft_rejected(async_client: AsyncClient, db_session: AsyncSession):
    """25. Applying template to a deleted draft or non-draft (SENT) email is rejected."""
    token = await register_and_login(async_client, "tmpl_user_25@test.com")
    comp_id = await create_company_helper(async_client, token, "Tmpl Co 25")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support25@tmpl.com")

    tmpl_resp = await async_client.post(
        f"/api/v1/companies/{comp_id}/templates",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Tmpl 25", "subject": "Subject", "body_text": "Body"},
    )
    tmpl_id = tmpl_resp.json()["id"]

    # Case A: Deleted draft
    draft_id = await create_draft_helper(async_client, token, acc_id)
    await async_client.delete(
        f"/api/v1/emails/drafts/{draft_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    apply_del = await async_client.post(
        f"/api/v1/emails/drafts/{draft_id}/apply-template/{tmpl_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert apply_del.status_code == 400

    # Case B: SENT email (not draft)
    sent_email = Email(
        company_id=comp_id,
        email_account_id=acc_id,
        direction=EmailDirection.OUTGOING.value,
        status=EmailStatus.SENT.value,
        sender="support25@tmpl.com",
        recipients=["customer@test.com"],
        subject="Already Sent",
        is_deleted=False,
    )
    db_session.add(sent_email)
    await db_session.commit()
    await db_session.refresh(sent_email)

    apply_sent = await async_client.post(
        f"/api/v1/emails/drafts/{sent_email.id}/apply-template/{tmpl_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert apply_sent.status_code == 400


@pytest.mark.asyncio
async def test_26_applying_template_from_another_company_or_account_rejected(async_client: AsyncClient, db_session: AsyncSession):
    """26. Applying template from another company or a different email account is rejected."""
    # Setup Company A
    token_a = await register_and_login(async_client, "tmpl_user_26_a@test.com")
    comp_a = await create_company_helper(async_client, token_a, "Company 26 A")
    acc_a1 = await create_account_helper(async_client, token_a, comp_a, email="acc1@comp26a.com")
    acc_a2 = await create_account_helper(async_client, token_a, comp_a, email="acc2@comp26a.com")
    draft_a1 = await create_draft_helper(async_client, token_a, acc_a1)

    # Setup Company B
    token_b = await register_and_login(async_client, "tmpl_user_26_b@test.com")
    comp_b = await create_company_helper(async_client, token_b, "Company 26 B")
    tmpl_b_resp = await async_client.post(
        f"/api/v1/companies/{comp_b}/templates",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"name": "Company B Template", "subject": "Subject B", "body_text": "Body B"},
    )
    tmpl_b_id = tmpl_b_resp.json()["id"]

    # Attempt 1: Cross-company template application (User A tries to apply Company B's template)
    resp_cross_comp = await async_client.post(
        f"/api/v1/emails/drafts/{draft_a1}/apply-template/{tmpl_b_id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp_cross_comp.status_code in [400, 403, 404]

    # Attempt 2: Account-scoped template on a different account
    # Create template scoped strictly to acc_a2
    tmpl_a2_resp = await async_client.post(
        f"/api/v1/companies/{comp_a}/templates",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "name": "Acc2 Template",
            "subject": "Acc2 Subject",
            "body_text": "Acc2 Text",
            "email_account_id": acc_a2,
        },
    )
    tmpl_a2_id = tmpl_a2_resp.json()["id"]

    # Try applying Acc2 template to draft created on Acc1
    resp_cross_acc = await async_client.post(
        f"/api/v1/emails/drafts/{draft_a1}/apply-template/{tmpl_a2_id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp_cross_acc.status_code == 400
    assert "account" in resp_cross_acc.json()["detail"].lower()


@pytest.mark.asyncio
async def test_27_member_with_access_can_create_and_apply_template(async_client: AsyncClient, db_session: AsyncSession):
    """27. Company MEMBER with granted account access can create, view, and apply account template."""
    owner_token = await register_and_login(async_client, "tmpl_user_27_owner@test.com")
    comp_id = await create_company_helper(async_client, owner_token, "Company 27")
    acc_id = await create_account_helper(async_client, owner_token, comp_id, email="support27@comp.com")

    member_token = await register_and_login(async_client, "tmpl_user_27_member@test.com")
    member_user_id = await add_company_member_helper(
        async_client, owner_token, comp_id, "tmpl_user_27_member@test.com", role="MEMBER"
    )
    await grant_account_access_helper(async_client, owner_token, comp_id, acc_id, member_user_id)

    # Member creates draft
    draft_id = await create_draft_helper(async_client, member_token, acc_id)

    # Member creates template for this account
    tmpl_resp = await async_client.post(
        f"/api/v1/companies/{comp_id}/templates",
        headers={"Authorization": f"Bearer {member_token}"},
        json={
            "name": "Member Created Template",
            "subject": "Subject from Member",
            "body_text": "Member text",
            "email_account_id": acc_id,
        },
    )
    assert tmpl_resp.status_code == 201
    tmpl_id = tmpl_resp.json()["id"]

    # Member applies template
    apply_resp = await async_client.post(
        f"/api/v1/emails/drafts/{draft_id}/apply-template/{tmpl_id}",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert apply_resp.status_code == 200
    assert apply_resp.json()["subject"] == "Subject from Member"


@pytest.mark.asyncio
async def test_28_member_without_access_cannot_create_or_access_account_template(async_client: AsyncClient, db_session: AsyncSession):
    """28. Company MEMBER without access to account cannot create or access account-scoped template."""
    owner_token = await register_and_login(async_client, "tmpl_user_28_owner@test.com")
    comp_id = await create_company_helper(async_client, owner_token, "Company 28")
    acc_id = await create_account_helper(async_client, owner_token, comp_id, email="support28@comp.com")

    member_token = await register_and_login(async_client, "tmpl_user_28_member@test.com")
    await add_company_member_helper(
        async_client, owner_token, comp_id, "tmpl_user_28_member@test.com", role="MEMBER"
    )
    # Notice: DO NOT grant account access to member

    # Member tries to create template scoped to acc_id
    resp = await async_client.post(
        f"/api/v1/companies/{comp_id}/templates",
        headers={"Authorization": f"Bearer {member_token}"},
        json={
            "name": "Unauthorized Template",
            "subject": "Forbidden Subject",
            "email_account_id": acc_id,
        },
    )
    assert resp.status_code == 403


# =============================================================================
# 8. Regression Tests: Inactive Exclusion, Account Scoping, Rich MIME & HTML (29 - 33)
# =============================================================================

@pytest.mark.asyncio
async def test_29_compose_active_templates_filter_and_account_scoping(async_client: AsyncClient, db_session: AsyncSession):
    """29. Inactive templates are excluded from Compose's active-template API query.
    Global active templates + active templates for selected account are returned.
    Inactive global templates, inactive account templates, and other accounts' templates are excluded.
    """
    token = await register_and_login(async_client, "tmpl_user_29@test.com")
    comp_id = await create_company_helper(async_client, token, "Company 29")
    acc1_id = await create_account_helper(async_client, token, comp_id, name="Acc 1", email="acc1_29@comp.com")
    acc2_id = await create_account_helper(async_client, token, comp_id, name="Acc 2", email="acc2_29@comp.com")

    # 1. Global Active Template
    resp_g_act = await async_client.post(
        f"/api/v1/companies/{comp_id}/templates",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Global Active", "subject": "Sub G Act", "body_text": "Text", "is_active": True},
    )
    assert resp_g_act.status_code == 201
    g_act_id = resp_g_act.json()["id"]

    # 2. Global Inactive Template
    resp_g_inact = await async_client.post(
        f"/api/v1/companies/{comp_id}/templates",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Global Inactive", "subject": "Sub G Inact", "body_text": "Text", "is_active": False},
    )
    assert resp_g_inact.status_code == 201
    g_inact_id = resp_g_inact.json()["id"]

    # 3. Acc1 Active Template
    resp_a1_act = await async_client.post(
        f"/api/v1/companies/{comp_id}/templates",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Acc1 Active", "subject": "Sub A1 Act", "body_text": "Text", "email_account_id": acc1_id, "is_active": True},
    )
    assert resp_a1_act.status_code == 201
    a1_act_id = resp_a1_act.json()["id"]

    # 4. Acc1 Inactive Template
    resp_a1_inact = await async_client.post(
        f"/api/v1/companies/{comp_id}/templates",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Acc1 Inactive", "subject": "Sub A1 Inact", "body_text": "Text", "email_account_id": acc1_id, "is_active": False},
    )
    assert resp_a1_inact.status_code == 201
    a1_inact_id = resp_a1_inact.json()["id"]

    # 5. Acc2 Active Template
    resp_a2_act = await async_client.post(
        f"/api/v1/companies/{comp_id}/templates",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Acc2 Active", "subject": "Sub A2 Act", "body_text": "Text", "email_account_id": acc2_id, "is_active": True},
    )
    assert resp_a2_act.status_code == 201
    a2_act_id = resp_a2_act.json()["id"]

    # Query templates for Compose when Acc1 is selected (is_active=true & email_account_id=acc1_id)
    resp = await async_client.get(
        f"/api/v1/templates?email_account_id={acc1_id}&is_active=true",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    returned_ids = [t["id"] for t in resp.json()["templates"]]

    # Must include Global Active and Acc1 Active
    assert g_act_id in returned_ids
    assert a1_act_id in returned_ids

    # Must NOT include Inactive templates
    assert g_inact_id not in returned_ids
    assert a1_inact_id not in returned_ids

    # Must NOT include templates scoped to another account (Acc2)
    assert a2_act_id not in returned_ids


@pytest.mark.asyncio
async def test_30_mime_level_multipart_alternative_rich_email(async_client: AsyncClient, db_session: AsyncSession):
    """30. MIME-level regression test:
    Construct rich email with body_text and body_html.
    Verify:
    1. multipart/alternative when both representations exist
    2. contains text/plain part with readable fallback
    3. contains text/html part with unescaped HTML elements (<h1 style="...">, <strong>Alex</strong>)
    4. plain-text fallback remains readable
    """
    from app.modules.email_accounts.models import EmailAccount
    from app.modules.emails.schemas import EmailSendRequest
    from app.modules.emails.service import EmailService

    account = EmailAccount(
        id=999,
        company_id=1,
        name="PulseMail Sender",
        email_address="sender@pulsemail.io",
        smtp_host="smtp.pulsemail.io",
        smtp_port=587,
        is_active=True,
    )

    body_text_sample = "Hello Alex,\nWelcome to PulseMail.\nThank you for joining us."
    body_html_sample = '<h1 style="color:#4f46e5;">Welcome to PulseMail</h1>\n<p>Hello <strong>Alex</strong>,</p>\n<p>Thank you for joining us.</p>'

    send_req = EmailSendRequest(
        email_account_id=account.id,
        to=["alex@example.com"],
        subject="Welcome to PulseMail",
        body_text=body_text_sample,
        body_html=body_html_sample,
    )

    svc = EmailService(smtp_adapter=AsyncMock())
    mime_msg, message_id, recipients, in_reply_to, references = svc.build_mime_message(
        account=account,
        send_req=send_req,
    )

    # 1. Must be multipart/alternative
    assert mime_msg.is_multipart() is True
    assert mime_msg.get_content_type() == "multipart/alternative"

    # 2 & 3. Inspect parts
    payload_parts = mime_msg.get_payload()
    assert len(payload_parts) == 2

    plain_part = payload_parts[0]
    html_part = payload_parts[1]

    assert plain_part.get_content_type() == "text/plain"
    assert html_part.get_content_type() == "text/html"

    plain_content = plain_part.get_content()
    html_content = html_part.get_content()

    # 4. Verify HTML tags preserved and unescaped
    assert '<h1 style="color:#4f46e5;">Welcome to PulseMail</h1>' in html_content
    assert "<strong>Alex</strong>" in html_content
    assert "Thank you for joining us." in html_content
    assert "&lt;h1" not in html_content

    # 5. Verify plain text readable fallback
    assert "Hello Alex," in plain_content
    assert "Thank you for joining us." in plain_content


@pytest.mark.asyncio
async def test_31_template_to_draft_to_mime_end_to_end(async_client: AsyncClient, db_session: AsyncSession):
    """31. End-to-End: Create rich HTML template -> Apply to Draft -> Verify Draft DB body_html -> Send Draft -> Verify MIME."""
    token = await register_and_login(async_client, "tmpl_user_31@test.com")
    comp_id = await create_company_helper(async_client, token, "Company 31")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support31@comp.com")

    html_content = '<h1 style="color:#4f46e5;">Welcome to PulseMail</h1><p>Hello <strong>Alex</strong>,</p><p>Thank you for joining us.</p>'

    # 1. Create rich HTML template
    tmpl_resp = await async_client.post(
        f"/api/v1/companies/{comp_id}/templates",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Rich Onboarding Template",
            "subject": "Welcome to PulseMail!",
            "body_html": html_content,
            "body_text": "Welcome to PulseMail! Hello Alex, Thank you for joining us.",
            "email_account_id": acc_id,
            "is_active": True,
        },
    )
    assert tmpl_resp.status_code == 201
    tmpl_data = tmpl_resp.json()
    assert tmpl_data["body_html"] == html_content
    assert tmpl_data["body_text"] is not None
    assert "Welcome to PulseMail" in tmpl_data["body_text"]
    tmpl_id = tmpl_data["id"]

    # 2. Create draft
    draft_id = await create_draft_helper(async_client, token, acc_id)

    # 3. Apply template to draft
    apply_resp = await async_client.post(
        f"/api/v1/emails/drafts/{draft_id}/apply-template/{tmpl_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert apply_resp.status_code == 200
    applied_data = apply_resp.json()
    assert applied_data["subject"] == "Welcome to PulseMail!"
    assert applied_data["body_html"] == html_content
    assert applied_data["body_text"] is not None

    # 4. Verify draft in DB
    db_draft = await db_session.get(Email, draft_id)
    assert db_draft is not None
    assert db_draft.body_html == html_content
    assert "<h1" in db_draft.body_html
    assert "<strong>Alex</strong>" in db_draft.body_html

    # 5. Send draft with mocked SMTP adapter
    mock_send = AsyncMock()
    with patch("app.modules.emails.draft_service.StandardSMTPAdapter") as mock_adapter_cls:
        instance = mock_adapter_cls.return_value
        instance.send = mock_send

        send_resp = await async_client.post(
            f"/api/v1/emails/drafts/{draft_id}/send",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert send_resp.status_code == 200
        assert mock_send.await_count == 1

        call_kwargs = mock_send.call_args.kwargs
        captured_mime = call_kwargs["message"]

        # Verify MIME structure
        assert captured_mime.is_multipart() is True
        assert captured_mime.get_content_type() == "multipart/alternative"

        parts = captured_mime.get_payload()
        assert len(parts) == 2
        assert parts[0].get_content_type() == "text/plain"
        assert parts[1].get_content_type() == "text/html"

        html_payload = parts[1].get_content()
        assert '<h1 style="color:#4f46e5;">Welcome to PulseMail</h1>' in html_payload
        assert "<strong>Alex</strong>" in html_payload
        assert "&lt;h1" not in html_payload


@pytest.mark.asyncio
async def test_32_inactive_template_rejected_on_apply(async_client: AsyncClient, db_session: AsyncSession):
    """32. Backend rejects applying inactive templates even if requested directly."""
    token = await register_and_login(async_client, "tmpl_user_32@test.com")
    comp_id = await create_company_helper(async_client, token, "Company 32")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support32@comp.com")

    # Create inactive template
    tmpl_resp = await async_client.post(
        f"/api/v1/companies/{comp_id}/templates",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Inactive Template",
            "subject": "Inactive",
            "body_text": "Content",
            "is_active": False,
        },
    )
    assert tmpl_resp.status_code == 201
    tmpl_id = tmpl_resp.json()["id"]

    draft_id = await create_draft_helper(async_client, token, acc_id)

    # Attempt to apply inactive template
    resp = await async_client.post(
        f"/api/v1/emails/drafts/{draft_id}/apply-template/{tmpl_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400
    assert "inactive" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_33_rich_template_survives_draft_autosave(async_client: AsyncClient, db_session: AsyncSession):
    """33. Rich template body_html and body_text survive draft creation and autosave updates."""
    token = await register_and_login(async_client, "tmpl_user_33@test.com")
    comp_id = await create_company_helper(async_client, token, "Company 33")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support33@comp.com")

    rich_html = '<h1 style="color:#4f46e5;">Product Update</h1><p>Check out our <strong>new features</strong>.</p><a href="https://example.com">Learn More</a>'
    plain_text = "Product Update Check out our new features. Learn More"

    # Autosave create payload
    create_resp = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "email_account_id": acc_id,
            "to": ["client@example.com"],
            "subject": "Product Update",
            "body_html": rich_html,
            "body_text": plain_text,
        },
    )
    assert create_resp.status_code == 201
    draft_id = create_resp.json()["id"]

    # Verify retrieval
    get_resp = await async_client.get(
        f"/api/v1/emails/drafts/{draft_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["body_html"] == rich_html
    assert get_resp.json()["body_text"] == plain_text

    # Autosave update payload sending both updated body_html and body_text (as Compose does)
    updated_html = '<h1 style="color:#4f46e5;">Product Update v2</h1><p>Added <strong>more details</strong>.</p>'
    updated_text = "Product Update v2 Added more details."
    update_resp = await async_client.put(
        f"/api/v1/emails/drafts/{draft_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "subject": "Product Update v2",
            "body_html": updated_html,
            "body_text": updated_text,
        },
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["body_html"] == updated_html
    assert update_resp.json()["body_text"] == updated_text


@pytest.mark.asyncio
async def test_34_full_html_template_with_meta_and_style_sends_non_empty_mime(async_client: AsyncClient, db_session: AsyncSession):
    """34. Regression test: Full HTML template with DOCTYPE, meta, style, and tables
    must not have its body emptied by sanitization, autosave, or send, and must generate
    a valid non-empty multipart/alternative MIME message.
    """
    token = await register_and_login(async_client, "tmpl_user_34@test.com")
    comp_id = await create_company_helper(async_client, token, "Company 34")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support34@comp.com")

    full_template_html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Special Product Offer</title>
    <style>
        body { margin: 0; padding: 0; background-color: #f4f4f7; }
        .main { background-color: #ffffff; max-width: 600px; }
        .btn { background-color: #007bff; color: #ffffff; }
    </style>
</head>
<body>
    <table class="main" width="100%">
        <tr>
            <td>
                <h1>Special Product Offer</h1>
                <p>Upgrade your daily routine with our newly released item.</p>
                <a href="https://example.com" class="btn">Shop Now</a>
            </td>
        </tr>
    </table>
</body>
</html>"""

    # 1. Create draft simulating Compose autosave with template content
    create_draft_resp = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "email_account_id": acc_id,
            "to": ["customer34@example.com"],
            "subject": "Special Product Offer",
            "body_html": full_template_html,
        },
    )
    assert create_draft_resp.status_code == 201
    draft_id = create_draft_resp.json()["id"]

    # 2. Verify draft content in database is non-empty and retains HTML elements
    db_draft = await db_session.get(Email, draft_id)
    assert db_draft is not None
    assert db_draft.body_html is not None
    assert len(db_draft.body_html) > 100
    assert "Special Product Offer" in db_draft.body_html
    assert "<table" in db_draft.body_html
    assert "<style>" in db_draft.body_html
    assert db_draft.body_text is not None
    assert "Special Product Offer" in db_draft.body_text
    # Ensure CSS was not dumped into plain text
    assert "background-color: #f4f4f7" not in db_draft.body_text

    # 3. Transmit draft via SMTP and inspect the generated MIME message
    mock_send = AsyncMock()
    with patch("app.modules.emails.draft_service.StandardSMTPAdapter") as mock_adapter_cls:
        instance = mock_adapter_cls.return_value
        instance.send = mock_send

        send_resp = await async_client.post(
            f"/api/v1/emails/drafts/{draft_id}/send",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert send_resp.status_code == 200
        assert mock_send.await_count == 1

        call_kwargs = mock_send.call_args.kwargs
        mime_msg = call_kwargs["message"]

        # Validate MIME is multipart/alternative
        assert mime_msg.is_multipart() is True
        assert mime_msg.get_content_type() == "multipart/alternative"

        parts = mime_msg.get_payload()
        assert len(parts) == 2

        plain_part = parts[0]
        html_part = parts[1]

        assert plain_part.get_content_type() == "text/plain"
        assert html_part.get_content_type() == "text/html"

        plain_text = plain_part.get_content()
        html_text = html_part.get_content()

        # Both parts must be non-empty and contain the template message
        assert len(plain_text.strip()) > 0
        assert len(html_text.strip()) > 0
        assert "Special Product Offer" in html_text
        assert "Upgrade your daily routine" in html_text
        assert "<table" in html_text
        assert "<style>" in html_text
        assert "Special Product Offer" in plain_text


@pytest.mark.asyncio
async def test_35_template_styling_and_css_inlining_preserved_in_mime(async_client: AsyncClient, db_session: AsyncSession):
    """35. Regression test: Template styling & CSS inlining preserved in final MIME HTML for email clients.
    Verifies:
    1. Final MIME HTML part is not empty.
    2. HTML structure (table, tr, td, h1, p, a, etc.) is preserved.
    3. Relevant presentation/styling from <style> classes (.main, .header, .btn, etc.) is inlined into style="..." attributes.
    4. The HTML sent by SMTP contains the expected inline styling (background-color, max-width, margin, padding, color).
    5. Responsive <style> block is preserved alongside inline styles.
    """
    token = await register_and_login(async_client, "tmpl_user_35@test.com")
    comp_id = await create_company_helper(async_client, token, "Company 35")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support35@comp.com")

    styled_template_html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Promotional Campaign</title>
    <style>
        body { margin: 0; padding: 0; background-color: #f4f4f7; font-family: Arial, sans-serif; }
        .wrapper { width: 100%; background-color: #f4f4f7; padding-bottom: 40px; }
        .main { background-color: #ffffff; margin: 0 auto; width: 100%; max-width: 600px; color: #333333; }
        .header { background-color: #1a1a1a; padding: 20px 0; text-align: center; }
        .header h1 { color: #ffffff; font-size: 24px; margin: 0; }
        .content { padding: 30px 40px; text-align: center; }
        .content h2 { font-size: 22px; color: #111111; margin-top: 0; }
        .btn { background-color: #007bff; color: #ffffff !important; padding: 12px 25px; border-radius: 4px; display: inline-block; text-decoration: none; }
        @media only screen and (max-width: 600px) {
            .main { width: 100% !important; }
        }
    </style>
</head>
<body>
    <table class="wrapper" width="100%" cellpadding="0" cellspacing="0">
        <tr>
            <td align="center">
                <table class="main" width="100%" cellpadding="0" cellspacing="0">
                    <tr>
                        <td class="header">
                            <h1>Acme Inc</h1>
                        </td>
                    </tr>
                    <tr>
                        <td class="content">
                            <h2>Special Spring Offer</h2>
                            <p>Get 20% off all subscriptions this week only.</p>
                            <a href="https://example.com/shop" class="btn" target="_blank">Claim Offer</a>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>"""

    # 1. Create template via API
    tmpl_resp = await async_client.post(
        f"/api/v1/companies/{comp_id}/templates",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Promotional Spring Offer",
            "subject": "Exclusive Spring Offer Inside",
            "body_html": styled_template_html,
            "email_account_id": acc_id,
            "is_active": True,
        },
    )
    assert tmpl_resp.status_code == 201
    tmpl_data = tmpl_resp.json()

    # Verify template in DB has inlined styles on elements
    db_html = tmpl_data["body_html"]
    assert "background-color: #1a1a1a" in db_html
    assert "max-width: 600px" in db_html
    assert "color: #ffffff" in db_html

    # 2. Create Draft using this template
    draft_resp = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "email_account_id": acc_id,
            "to": ["target_customer@example.com"],
            "subject": "Exclusive Spring Offer Inside",
            "body_html": db_html,
        },
    )
    assert draft_resp.status_code == 201
    draft_id = draft_resp.json()["id"]

    # 3. Transmit draft via SMTP and inspect the generated MIME HTML part
    mock_send = AsyncMock()
    with patch("app.modules.emails.draft_service.StandardSMTPAdapter") as mock_adapter_cls:
        instance = mock_adapter_cls.return_value
        instance.send = mock_send

        send_resp = await async_client.post(
            f"/api/v1/emails/drafts/{draft_id}/send",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert send_resp.status_code == 200
        assert mock_send.await_count == 1

        call_kwargs = mock_send.call_args.kwargs
        mime_msg = call_kwargs["message"]

        # Validate MIME properties
        assert mime_msg.is_multipart() is True
        assert mime_msg.get_content_type() == "multipart/alternative"

        html_part = mime_msg.get_body(preferencelist=("html",))
        assert html_part is not None
        mime_html = html_part.get_content()

        # 1. Final MIME HTML part is not empty
        assert len(mime_html.strip()) > 0

        # 2. Important HTML structure is preserved
        assert "<table" in mime_html
        assert "</table>" in mime_html
        assert "<tr" in mime_html
        assert "<td" in mime_html
        assert "<h1" in mime_html
        assert "<h2" in mime_html
        assert "<p" in mime_html
        assert "<a href=" in mime_html

        # 3. Relevant styling and presentation is preserved via inline styles
        # Centered container styling on .main table
        assert 'class="main"' in mime_html
        assert "max-width: 600px" in mime_html
        assert "margin: 0 auto" in mime_html
        assert "background-color: #ffffff" in mime_html

        # Header background and padding
        assert 'class="header"' in mime_html
        assert "background-color: #1a1a1a" in mime_html
        assert "padding: 20px 0" in mime_html
        assert "text-align: center" in mime_html

        # Heading color and typography
        assert "color: #ffffff" in mime_html
        assert "font-size: 24px" in mime_html

        # Button styling: background color, padding, border-radius, display
        assert 'class="btn"' in mime_html
        assert "background-color: #007bff" in mime_html
        assert "padding: 12px 25px" in mime_html
        assert "border-radius: 4px" in mime_html
        assert "display: inline-block" in mime_html
        assert "text-decoration: none" in mime_html

        # 4. Responsive @media query stays in <style> block for supporting clients
        assert "@media" in mime_html


@pytest.mark.asyncio
async def test_36_security_sanitization_blocks_malicious_inlined_and_stylesheet_css(async_client: AsyncClient):
    """36. Regression test: Security sanitization still blocks unsafe HTML, scripts, and CSS injections."""
    from app.core.sanitizer import sanitize_html

    # Unsafe script tags, event handlers, and javascript URLs
    malicious_html = """<!DOCTYPE html>
<html>
<head>
    <style>
        .pwn { background-image: url('javascript:alert(1)'); }
        .expr { width: expression(alert(2)); }
        @import url('https://evil.com/leak.css');
    </style>
</head>
<body>
    <script>alert('xss');</script>
    <div class="pwn" onclick="steal()">Click me</div>
    <div class="expr" style="background: expression(alert(3));">Bad style</div>
    <a href="javascript:alert(4)">Malicious link</a>
    <img src="javascript:alert(5)" onerror="alert(6)">
</body>
</html>"""

    sanitized = sanitize_html(malicious_html)
    assert sanitized is not None

    # Verify all malicious attack vectors are completely stripped/blocked
    assert "<script" not in sanitized.lower()
    assert "onclick" not in sanitized.lower()
    assert "onerror" not in sanitized.lower()
    assert "javascript:" not in sanitized.lower()
    assert "expression(" not in sanitized.lower()
    assert "@import" not in sanitized.lower() or "/* @import blocked */" in sanitized
    assert "href=\"javascript:" not in sanitized.lower()
    assert "src=\"javascript:" not in sanitized.lower()


@pytest.mark.asyncio
async def test_37_company_wide_template_mutations_restricted_to_admin_and_owner(async_client: AsyncClient):
    """37. Regression test: Creating, updating, toggling, and deleting company-wide templates requires OWNER or ADMIN."""
    owner_token = await register_and_login(async_client, "tmpl_user_37_owner@test.com")
    comp_id = await create_company_helper(async_client, owner_token, "Company 37")

    member_token = await register_and_login(async_client, "tmpl_user_37_member@test.com")
    admin_token = await register_and_login(async_client, "tmpl_user_37_admin@test.com")

    await add_company_member_helper(async_client, owner_token, comp_id, "tmpl_user_37_member@test.com", role="MEMBER")
    await add_company_member_helper(async_client, owner_token, comp_id, "tmpl_user_37_admin@test.com", role="ADMIN")

    # 1. MEMBER tries to create company-wide template (email_account_id=None) -> 403 Forbidden
    resp = await async_client.post(
        f"/api/v1/companies/{comp_id}/templates",
        headers={"Authorization": f"Bearer {member_token}"},
        json={
            "name": "Member Company Template",
            "subject": "Forbidden Subject",
            "body_text": "Forbidden body",
            "email_account_id": None,
        },
    )
    assert resp.status_code == 403
    assert "Owner or Administrator privileges required" in resp.json()["detail"]

    # 2. OWNER can create company-wide template -> 201 Created
    owner_create_resp = await async_client.post(
        f"/api/v1/companies/{comp_id}/templates",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "name": "Owner Company Template",
            "subject": "Owner Subject",
            "body_text": "Owner body",
            "email_account_id": None,
        },
    )
    assert owner_create_resp.status_code == 201
    template_id = owner_create_resp.json()["id"]

    # 3. ADMIN can create company-wide template -> 201 Created
    admin_create_resp = await async_client.post(
        f"/api/v1/companies/{comp_id}/templates",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "name": "Admin Company Template",
            "subject": "Admin Subject",
            "body_text": "Admin body",
            "email_account_id": None,
        },
    )
    assert admin_create_resp.status_code == 201

    # 4. MEMBER tries to update company-wide template -> 403 Forbidden
    member_update_resp = await async_client.put(
        f"/api/v1/companies/{comp_id}/templates/{template_id}",
        headers={"Authorization": f"Bearer {member_token}"},
        json={"name": "Hacked Template Name"},
    )
    assert member_update_resp.status_code == 403
    assert "Owner or Administrator privileges required" in member_update_resp.json()["detail"]

    # 5. ADMIN can update company-wide template -> 200 OK
    admin_update_resp = await async_client.put(
        f"/api/v1/companies/{comp_id}/templates/{template_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "Updated by Admin"},
    )
    assert admin_update_resp.status_code == 200
    assert admin_update_resp.json()["name"] == "Updated by Admin"

    # 6. MEMBER tries to toggle active state on company-wide template -> 403 Forbidden
    member_toggle_resp = await async_client.patch(
        f"/api/v1/companies/{comp_id}/templates/{template_id}/active",
        headers={"Authorization": f"Bearer {member_token}"},
        json={"is_active": False},
    )
    assert member_toggle_resp.status_code == 403
    assert "Owner or Administrator privileges required" in member_toggle_resp.json()["detail"]

    # 7. OWNER can toggle active state -> 200 OK
    owner_toggle_resp = await async_client.patch(
        f"/api/v1/companies/{comp_id}/templates/{template_id}/active",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"is_active": False},
    )
    assert owner_toggle_resp.status_code == 200
    assert owner_toggle_resp.json()["is_active"] is False

    # 8. MEMBER tries to delete company-wide template -> 403 Forbidden
    member_delete_resp = await async_client.delete(
        f"/api/v1/companies/{comp_id}/templates/{template_id}",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert member_delete_resp.status_code == 403
    assert "Owner or Administrator privileges required" in member_delete_resp.json()["detail"]

    # 9. ADMIN can delete company-wide template -> 204 No Content
    admin_delete_resp = await async_client.delete(
        f"/api/v1/companies/{comp_id}/templates/{template_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert admin_delete_resp.status_code == 204


@pytest.mark.asyncio
async def test_38_member_with_account_access_can_mutate_account_scoped_template(async_client: AsyncClient):
    """38. Regression test: MEMBER with granted account access can manage account-scoped templates, but not other accounts."""
    owner_token = await register_and_login(async_client, "tmpl_user_38_owner@test.com")
    comp_id = await create_company_helper(async_client, owner_token, "Company 38")
    acc_id_granted = await create_account_helper(async_client, owner_token, comp_id, email="granted38@comp.com")
    acc_id_denied = await create_account_helper(async_client, owner_token, comp_id, email="denied38@comp.com")

    member_token = await register_and_login(async_client, "tmpl_user_38_member@test.com")
    member_user_id = await add_company_member_helper(async_client, owner_token, comp_id, "tmpl_user_38_member@test.com", role="MEMBER")
    await grant_account_access_helper(async_client, owner_token, comp_id, acc_id_granted, member_user_id)

    # Member creates template for granted account -> 201 Created
    create_resp = await async_client.post(
        f"/api/v1/companies/{comp_id}/templates",
        headers={"Authorization": f"Bearer {member_token}"},
        json={
            "name": "Granted Account Template",
            "subject": "Granted Subject",
            "body_text": "Granted body",
            "email_account_id": acc_id_granted,
        },
    )
    assert create_resp.status_code == 201
    tmpl_id = create_resp.json()["id"]

    # Member updates template -> 200 OK
    update_resp = await async_client.put(
        f"/api/v1/companies/{comp_id}/templates/{tmpl_id}",
        headers={"Authorization": f"Bearer {member_token}"},
        json={"name": "Updated Granted Template"},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["name"] == "Updated Granted Template"

    # Member tries to reassign template to denied account -> 403 Forbidden
    reassign_resp = await async_client.put(
        f"/api/v1/companies/{comp_id}/templates/{tmpl_id}",
        headers={"Authorization": f"Bearer {member_token}"},
        json={"email_account_id": acc_id_denied},
    )
    assert reassign_resp.status_code == 403

    # Member toggles active state -> 200 OK
    toggle_resp = await async_client.patch(
        f"/api/v1/companies/{comp_id}/templates/{tmpl_id}/active",
        headers={"Authorization": f"Bearer {member_token}"},
        json={"is_active": False},
    )
    assert toggle_resp.status_code == 200

    # Member deletes template -> 204 No Content
    del_resp = await async_client.delete(
        f"/api/v1/companies/{comp_id}/templates/{tmpl_id}",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert del_resp.status_code == 204




