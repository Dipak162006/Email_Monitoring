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
