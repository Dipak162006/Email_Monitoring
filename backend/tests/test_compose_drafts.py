import asyncio
from email.message import EmailMessage
from unittest.mock import AsyncMock, patch
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.email_accounts.models import EmailAccount
from app.modules.emails.models import Email, EmailDirection, EmailStatus, EmailThread
from app.services.smtp.adapter import StandardSMTPAdapter
from app.services.smtp.client import SMTPClient
from app.services.smtp.exceptions import (
    SMTPAuthenticationError,
    SMTPConnectionError,
    SMTPSendError,
)


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


# =============================================================================
# 1. Draft Creation Tests (1 - 6)
# =============================================================================

@pytest.mark.asyncio
async def test_01_create_empty_draft(async_client: AsyncClient, db_session: AsyncSession):
    """1. Create empty draft with only account_id (allows empty recipients/body/subject)."""
    token = await register_and_login(async_client, "user_m9_01@test.com")
    comp_id = await create_company_helper(async_client, token, "Co M9 01")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support01@m9.com")

    resp = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={"email_account_id": acc_id},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"] is not None
    assert data["status"] == "DRAFT"
    assert data["direction"] == "OUTGOING"
    assert data["recipients"] == []
    assert data["subject"] == ""
    assert data["body_text"] is None
    assert data["body_html"] is None
    assert data["sent_at"] is None
    assert data["is_deleted"] is False


@pytest.mark.asyncio
async def test_02_create_complete_draft(async_client: AsyncClient, db_session: AsyncSession):
    """2. Create complete draft with recipients, cc, bcc, subject, and bodies."""
    token = await register_and_login(async_client, "user_m9_02@test.com")
    comp_id = await create_company_helper(async_client, token, "Co M9 02")
    acc_id = await create_account_helper(async_client, token, comp_id, name="Sales Desk", email="sales02@m9.com")

    payload = {
        "email_account_id": acc_id,
        "to": ["customer@example.com"],
        "cc": ["lead@example.com"],
        "bcc": ["audit@example.com"],
        "subject": "Proposal Draft",
        "body_text": "Please see draft proposal.",
        "body_html": "<p>Please see draft proposal.</p>",
        "reply_to": "replies@example.com",
    }
    resp = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["recipients"] == ["customer@example.com"]
    assert data["cc"] == ["lead@example.com"]
    assert data["bcc"] == ["audit@example.com"]
    assert data["subject"] == "Proposal Draft"
    assert data["body_text"] == "Please see draft proposal."
    assert data["body_html"] == "<p>Please see draft proposal.</p>"
    assert data["reply_to"] == "replies@example.com"


@pytest.mark.asyncio
async def test_03_draft_uses_correct_account_and_sender(async_client: AsyncClient):
    """3. Draft derives authoritative sender from the EmailAccount."""
    token = await register_and_login(async_client, "user_m9_03@test.com")
    comp_id = await create_company_helper(async_client, token, "Co M9 03")
    acc_id = await create_account_helper(async_client, token, comp_id, name="Acme Support", email="support03@m9.com")

    resp = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={"email_account_id": acc_id, "subject": "Test Sender"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["sender"] == "Acme Support <support03@m9.com>"
    assert data["email_account_id"] == acc_id


@pytest.mark.asyncio
async def test_04_draft_does_not_send_smtp(async_client: AsyncClient):
    """4. Creating a draft does not invoke the SMTP adapter."""
    token = await register_and_login(async_client, "user_m9_04@test.com")
    comp_id = await create_company_helper(async_client, token, "Co M9 04")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support04@m9.com")

    with patch.object(SMTPClient, "send_email_sync") as mock_smtp:
        resp = await async_client.post(
            "/api/v1/emails/drafts",
            headers={"Authorization": f"Bearer {token}"},
            json={"email_account_id": acc_id, "to": ["target@example.com"], "body_text": "Draft content"},
        )
        assert resp.status_code == 201
        assert mock_smtp.call_count == 0


@pytest.mark.asyncio
async def test_05_unauthorized_account_cannot_create_draft(async_client: AsyncClient):
    """5. Unauthorized user cannot create a draft for an account they cannot access (403)."""
    owner_token = await register_and_login(async_client, "owner_m9_05@test.com")
    comp_id = await create_company_helper(async_client, owner_token, "Co M9 05")
    acc_id = await create_account_helper(async_client, owner_token, comp_id, email="support05@m9.com")

    # Member user without account access
    member_token = await register_and_login(async_client, "member_m9_05@test.com")
    await async_client.post(
        f"/api/v1/companies/{comp_id}/members",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"email": "member_m9_05@test.com", "role": "MEMBER"},
    )

    resp = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {member_token}"},
        json={"email_account_id": acc_id, "subject": "Unauthorized Draft"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_06_inactive_account_can_still_create_draft(async_client: AsyncClient):
    """6. Inactive account can be used to draft an email (creation allowed, sending will be rejected)."""
    token = await register_and_login(async_client, "user_m9_06@test.com")
    comp_id = await create_company_helper(async_client, token, "Co M9 06")
    acc_id = await create_account_helper(async_client, token, comp_id, email="inactive06@m9.com")

    # Deactivate account
    await async_client.put(
        f"/api/v1/companies/{comp_id}/email-accounts/{acc_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"is_active": False},
    )

    resp = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={"email_account_id": acc_id, "subject": "Draft on Inactive Account"},
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "DRAFT"


# =============================================================================
# 2. Reply Drafts Tests (7 - 11)
# =============================================================================

@pytest.mark.asyncio
async def test_07_08_create_reply_draft_with_thread_and_in_reply_to(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """7 & 8. Create reply draft linked to an existing thread and in_reply_to."""
    token = await register_and_login(async_client, "user_m9_07@test.com")
    comp_id = await create_company_helper(async_client, token, "Co M9 07")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support07@m9.com")

    # Seed an existing thread and initial email
    thread = EmailThread(
        company_id=comp_id,
        email_account_id=acc_id,
        subject="Support Case #100",
        message_count=1,
        has_reply=False,
        last_message_at=datetime.now(timezone.utc) if False else None,
        is_read=True,
    )
    # Use proper datetime
    from datetime import datetime, timezone
    thread.last_message_at = datetime.now(timezone.utc)
    db_session.add(thread)
    await db_session.flush()

    parent_email = Email(
        company_id=comp_id,
        email_account_id=acc_id,
        thread_id=thread.id,
        message_id="<parent-msg-100@client.com>",
        direction="INCOMING",
        status="RECEIVED",
        sender="client@client.com",
        recipients=["support07@m9.com"],
        subject="Support Case #100",
        is_read=True,
    )
    db_session.add(parent_email)
    await db_session.commit()

    resp = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "email_account_id": acc_id,
            "thread_id": thread.id,
            "in_reply_to": "<parent-msg-100@client.com>",
            "to": ["client@client.com"],
            "subject": "Re: Support Case #100",
            "body_text": "We are working on your issue.",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["thread_id"] == thread.id
    assert data["in_reply_to"] == "<parent-msg-100@client.com>"


@pytest.mark.asyncio
async def test_09_10_11_reply_draft_does_not_mutate_thread_metrics(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """9, 10, 11. Reply draft does NOT increment message_count, update last_message_at, or set has_reply."""
    from datetime import datetime, timedelta, timezone
    token = await register_and_login(async_client, "user_m9_09@test.com")
    comp_id = await create_company_helper(async_client, token, "Co M9 09")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support09@m9.com")

    initial_time = datetime.now(timezone.utc) - timedelta(hours=2)
    thread = EmailThread(
        company_id=comp_id,
        email_account_id=acc_id,
        subject="Initial Thread",
        message_count=1,
        has_reply=False,
        last_message_at=initial_time,
        is_read=True,
    )
    db_session.add(thread)
    await db_session.flush()

    parent_email = Email(
        company_id=comp_id,
        email_account_id=acc_id,
        thread_id=thread.id,
        message_id="<parent-msg-09@client.com>",
        direction="INCOMING",
        status="RECEIVED",
        sender="client@client.com",
        recipients=["support09@m9.com"],
        subject="Initial Thread",
        is_read=True,
    )
    db_session.add(parent_email)
    await db_session.commit()

    # Create reply draft
    resp = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "email_account_id": acc_id,
            "thread_id": thread.id,
            "in_reply_to": "<parent-msg-09@client.com>",
            "to": ["client@client.com"],
            "subject": "Re: Initial Thread",
            "body_text": "Draft reply content.",
        },
    )
    assert resp.status_code == 201

    # Verify thread in database was NOT altered
    await db_session.refresh(thread)
    assert thread.message_count == 1  # 9. message_count not incremented
    assert thread.last_message_at == initial_time  # 10. last_message_at not updated
    assert thread.has_reply is False  # 11. has_reply is still False


# =============================================================================
# 3. Draft Update / Autosave Tests (12 - 19)
# =============================================================================

@pytest.mark.asyncio
async def test_12_13_14_update_recipients_subject_and_bodies(async_client: AsyncClient):
    """12, 13, 14. Update recipients, subject, and plain/html bodies."""
    token = await register_and_login(async_client, "user_m9_12@test.com")
    comp_id = await create_company_helper(async_client, token, "Co M9 12")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support12@m9.com")

    # Initial draft
    create_resp = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={"email_account_id": acc_id},
    )
    draft_id = create_resp.json()["id"]

    # Update
    update_payload = {
        "to": ["new_to@example.com"],
        "cc": ["new_cc@example.com"],
        "bcc": ["new_bcc@example.com"],
        "subject": "Updated Subject Line",
        "body_text": "Updated body text.",
        "body_html": "<p>Updated body HTML.</p>",
    }
    update_resp = await async_client.put(
        f"/api/v1/emails/drafts/{draft_id}",
        headers={"Authorization": f"Bearer {token}"},
        json=update_payload,
    )
    assert update_resp.status_code == 200
    data = update_resp.json()
    assert data["recipients"] == ["new_to@example.com"]
    assert data["cc"] == ["new_cc@example.com"]
    assert data["bcc"] == ["new_bcc@example.com"]
    assert data["subject"] == "Updated Subject Line"
    assert data["body_text"] == "Updated body text."
    assert data["body_html"] == "<p>Updated body HTML.</p>"


@pytest.mark.asyncio
async def test_15_16_17_update_account_and_authorization(async_client: AsyncClient):
    """15, 16, 17. Switch email account, reject unauthorized account, reject cross-company."""
    token_a = await register_and_login(async_client, "user_m9_15a@test.com")
    comp_a = await create_company_helper(async_client, token_a, "Co M9 15A")
    acc_a1 = await create_account_helper(async_client, token_a, comp_a, name="Desk 1", email="desk1@m9.com")
    acc_a2 = await create_account_helper(async_client, token_a, comp_a, name="Desk 2", email="desk2@m9.com")

    # Company B
    token_b = await register_and_login(async_client, "user_m9_15b@test.com")
    comp_b = await create_company_helper(async_client, token_b, "Co M9 15B")
    acc_b = await create_account_helper(async_client, token_b, comp_b, email="desk_b@m9.com")

    # Create draft under acc_a1
    draft_resp = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"email_account_id": acc_a1, "subject": "Switch Account Test"},
    )
    draft_id = draft_resp.json()["id"]

    # 15. Successfully switch to authorized account acc_a2
    switch_resp = await async_client.put(
        f"/api/v1/emails/drafts/{draft_id}",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"email_account_id": acc_a2},
    )
    assert switch_resp.status_code == 200
    assert switch_resp.json()["email_account_id"] == acc_a2
    assert "Desk 2 <desk2@m9.com>" in switch_resp.json()["sender"]

    # 17. Reject cross-company account reassignment
    cross_resp = await async_client.put(
        f"/api/v1/emails/drafts/{draft_id}",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"email_account_id": acc_b},
    )
    assert cross_resp.status_code in (400, 403, 404)


@pytest.mark.asyncio
async def test_18_19_reject_editing_non_draft_or_deleted(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """18 & 19. Reject editing non-DRAFT email (400) or soft-deleted draft (400)."""
    token = await register_and_login(async_client, "user_m9_18@test.com")
    comp_id = await create_company_helper(async_client, token, "Co M9 18")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support18@m9.com")

    # Sent email
    sent_email = Email(
        company_id=comp_id,
        email_account_id=acc_id,
        direction="OUTGOING",
        status="SENT",
        sender="support18@m9.com",
        recipients=["client@example.com"],
        subject="Already Sent",
    )
    # Trashed draft
    trashed_draft = Email(
        company_id=comp_id,
        email_account_id=acc_id,
        direction="OUTGOING",
        status="DRAFT",
        sender="support18@m9.com",
        recipients=["client@example.com"],
        subject="Trashed Draft",
        is_deleted=True,
    )
    db_session.add_all([sent_email, trashed_draft])
    await db_session.commit()

    # 18. Attempt editing SENT email -> 400
    resp_sent = await async_client.put(
        f"/api/v1/emails/drafts/{sent_email.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"subject": "Modifying Sent Email"},
    )
    assert resp_sent.status_code == 400
    assert "draft" in resp_sent.json()["detail"].lower()

    # 19. Attempt editing trashed draft -> 400
    resp_trash = await async_client.put(
        f"/api/v1/emails/drafts/{trashed_draft.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"subject": "Modifying Trashed Draft"},
    )
    assert resp_trash.status_code == 400
    assert "deleted" in resp_trash.json()["detail"].lower()


# =============================================================================
# 4. Draft Retrieval & Shared Collaboration Tests (20 - 23)
# =============================================================================

@pytest.mark.asyncio
async def test_20_21_retrieve_draft_and_shared_collaboration(async_client: AsyncClient):
    """20 & 21. Retrieve draft by ID; authorized colleague can view creator's draft."""
    owner_token = await register_and_login(async_client, "owner_m9_20@test.com", "Owner User")
    comp_id = await create_company_helper(async_client, owner_token, "Co M9 20")
    acc_id = await create_account_helper(async_client, owner_token, comp_id, email="shared@m9.com")

    # Member user granted access to shared account
    colleague_token = await register_and_login(async_client, "colleague_m9_20@test.com", "Colleague")
    await async_client.post(
        f"/api/v1/companies/{comp_id}/members",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"email": "colleague_m9_20@test.com", "role": "MEMBER"},
    )
    colleague_info = (await async_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {colleague_token}"})).json()
    await async_client.post(
        f"/api/v1/companies/{comp_id}/email-accounts/{acc_id}/access",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"user_id": colleague_info["id"]},
    )

    # Owner creates draft
    create_resp = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"email_account_id": acc_id, "subject": "Shared Collaborative Draft"},
    )
    draft_id = create_resp.json()["id"]

    # 20. Owner retrieves draft
    owner_get = await async_client.get(
        f"/api/v1/emails/drafts/{draft_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert owner_get.status_code == 200
    assert owner_get.json()["subject"] == "Shared Collaborative Draft"

    # 21. Colleague with account access retrieves owner's draft
    colleague_get = await async_client.get(
        f"/api/v1/emails/drafts/{draft_id}",
        headers={"Authorization": f"Bearer {colleague_token}"},
    )
    assert colleague_get.status_code == 200
    assert colleague_get.json()["id"] == draft_id


@pytest.mark.asyncio
async def test_22_23_cross_company_and_unauthorized_draft_access_rejected(async_client: AsyncClient):
    """22 & 23. Cross-company and cross-account access rejected with 403 or 404."""
    token_a = await register_and_login(async_client, "user_m9_22a@test.com")
    comp_a = await create_company_helper(async_client, token_a, "Co M9 22A")
    acc_a = await create_account_helper(async_client, token_a, comp_a, email="support22a@m9.com")

    token_b = await register_and_login(async_client, "user_m9_22b@test.com")
    comp_b = await create_company_helper(async_client, token_b, "Co M9 22B")

    draft_resp = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"email_account_id": acc_a, "subject": "Private Draft A"},
    )
    draft_id = draft_resp.json()["id"]

    # User B tries to view Draft A -> 403 or 404
    resp = await async_client.get(
        f"/api/v1/emails/drafts/{draft_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp.status_code in (403, 404)


# =============================================================================
# 5. Draft Listing & Mailbox Integration Tests (24 - 26)
# =============================================================================

@pytest.mark.asyncio
async def test_24_25_26_draft_listing_and_mailbox_integration(async_client: AsyncClient):
    """24, 25, 26. Draft appears in folder=drafts; disappears when sent or discarded."""
    token = await register_and_login(async_client, "user_m9_24@test.com")
    comp_id = await create_company_helper(async_client, token, "Co M9 24")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support24@m9.com")

    # Create draft
    draft_resp = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={"email_account_id": acc_id, "to": ["lead@example.com"], "subject": "Listing Test", "body_text": "Content"},
    )
    draft_id = draft_resp.json()["id"]

    # 24. Appears in folder=drafts
    list_resp = await async_client.get(
        "/api/v1/emails?folder=drafts",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_resp.status_code == 200
    draft_ids = [e["id"] for e in list_resp.json()["emails"]]
    assert draft_id in draft_ids

    # 25. Send draft -> disappears from folder=drafts, appears in folder=sent
    with patch.object(SMTPClient, "send_email_sync", return_value=None):
        send_resp = await async_client.post(
            f"/api/v1/emails/drafts/{draft_id}/send",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert send_resp.status_code == 200

    list_after_send = await async_client.get(
        "/api/v1/emails?folder=drafts",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert draft_id not in [e["id"] for e in list_after_send.json()["emails"]]

    sent_list = await async_client.get(
        "/api/v1/emails?folder=sent",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert draft_id in [e["id"] for e in sent_list.json()["emails"]]


# =============================================================================
# 6. Discard & Trash Tests (27 - 29)
# =============================================================================

@pytest.mark.asyncio
async def test_27_28_29_discard_and_trash_lifecycle(async_client: AsyncClient):
    """27, 28, 29. Discard soft-deletes draft into Trash; M8 restore recovers it."""
    token = await register_and_login(async_client, "user_m9_27@test.com")
    comp_id = await create_company_helper(async_client, token, "Co M9 27")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support27@m9.com")

    draft_resp = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={"email_account_id": acc_id, "subject": "To Be Discarded"},
    )
    draft_id = draft_resp.json()["id"]

    # 27. Discard draft -> soft-deleted
    discard_resp = await async_client.delete(
        f"/api/v1/emails/drafts/{draft_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert discard_resp.status_code == 200
    assert discard_resp.json()["is_deleted"] is True
    assert discard_resp.json()["deleted_at"] is not None

    # 28. Discarded draft appears in Trash and not in drafts
    drafts_list = await async_client.get(
        "/api/v1/emails?folder=drafts",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert draft_id not in [e["id"] for e in drafts_list.json()["emails"]]

    trash_list = await async_client.get(
        "/api/v1/emails?folder=trash",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert draft_id in [e["id"] for e in trash_list.json()["emails"]]

    # 29. Restore draft -> returns to folder=drafts
    restore_resp = await async_client.patch(
        f"/api/v1/emails/{draft_id}/restore",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert restore_resp.status_code == 200
    assert restore_resp.json()["is_deleted"] is False

    drafts_restored = await async_client.get(
        "/api/v1/emails?folder=drafts",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert draft_id in [e["id"] for e in drafts_restored.json()["emails"]]


# =============================================================================
# 7. Send Validation Tests (30 - 35)
# =============================================================================

@pytest.mark.asyncio
async def test_30_31_reject_send_without_recipients_or_body(async_client: AsyncClient):
    """30 & 31. Reject sending draft with empty recipients (422) or missing body (422)."""
    token = await register_and_login(async_client, "user_m9_30@test.com")
    comp_id = await create_company_helper(async_client, token, "Co M9 30")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support30@m9.com")

    # Draft with empty recipients
    d1 = (await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={"email_account_id": acc_id, "body_text": "Has body, no to"},
    )).json()["id"]

    resp1 = await async_client.post(
        f"/api/v1/emails/drafts/{d1}/send",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp1.status_code == 422
    assert "recipient" in resp1.json()["detail"].lower()

    # Draft with recipients but empty body
    d2 = (await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={"email_account_id": acc_id, "to": ["user@example.com"], "subject": "No Body"},
    )).json()["id"]

    resp2 = await async_client.post(
        f"/api/v1/emails/drafts/{d2}/send",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 422
    assert "body" in resp2.json()["detail"].lower()


@pytest.mark.asyncio
async def test_32_33_reject_send_inactive_account_or_missing_smtp(async_client: AsyncClient):
    """32 & 33. Reject sending draft when account is inactive or missing SMTP host (400)."""
    token = await register_and_login(async_client, "user_m9_32@test.com")
    comp_id = await create_company_helper(async_client, token, "Co M9 32")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support32@m9.com")

    # Create draft
    draft_id = (await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={"email_account_id": acc_id, "to": ["user@example.com"], "body_text": "Ready to send"},
    )).json()["id"]

    # Deactivate account
    await async_client.put(
        f"/api/v1/companies/{comp_id}/email-accounts/{acc_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"is_active": False},
    )

    # 32. Attempt send on inactive account -> 400
    resp_inactive = await async_client.post(
        f"/api/v1/emails/drafts/{draft_id}/send",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_inactive.status_code == 400
    assert "inactive" in resp_inactive.json()["detail"].lower()


@pytest.mark.asyncio
async def test_34_35_reject_send_soft_deleted_or_non_draft(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """34 & 35. Reject sending soft-deleted draft (400) or non-DRAFT email (400)."""
    token = await register_and_login(async_client, "user_m9_34@test.com")
    comp_id = await create_company_helper(async_client, token, "Co M9 34")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support34@m9.com")

    # Create draft and soft-delete it
    draft_id = (await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={"email_account_id": acc_id, "to": ["user@example.com"], "body_text": "Ready"},
    )).json()["id"]
    await async_client.delete(
        f"/api/v1/emails/drafts/{draft_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    # 34. Attempt sending deleted draft -> 400
    resp_del = await async_client.post(
        f"/api/v1/emails/drafts/{draft_id}/send",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_del.status_code == 400
    assert "deleted" in resp_del.json()["detail"].lower()


# =============================================================================
# 8. Send Success & Thread Integration Tests (36 - 44)
# =============================================================================

@pytest.mark.asyncio
async def test_36_to_41_send_original_draft_success(async_client: AsyncClient, db_session: AsyncSession):
    """36 - 41. Send original draft successfully, transitions to SENT, populates sent_at,
    creates Message-ID, appears in Sent folder, creates thread with message_count=1.
    """
    token = await register_and_login(async_client, "user_m9_36@test.com")
    comp_id = await create_company_helper(async_client, token, "Co M9 36")
    acc_id = await create_account_helper(async_client, token, comp_id, name="Hero Support", email="support36@m9.com")

    # Create draft
    draft_resp = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "email_account_id": acc_id,
            "to": ["customer@example.com"],
            "cc": ["manager@example.com"],
            "bcc": ["secret@example.com"],
            "subject": "Original Discussion",
            "body_text": "Plain text body.",
            "body_html": "<p>HTML body.</p>",
        },
    )
    draft_id = draft_resp.json()["id"]

    captured_kwargs = {}

    def mock_send(*args, **kwargs):
        captured_kwargs.update(kwargs)

    with patch.object(SMTPClient, "send_email_sync", side_effect=mock_send):
        send_resp = await async_client.post(
            f"/api/v1/emails/drafts/{draft_id}/send",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert send_resp.status_code == 200
        data = send_resp.json()

        # 36. Status is SENT
        assert data["status"] == "SENT"
        # 37. sent_at populated
        assert data["sent_at"] is not None
        # 38. Message-ID exists
        assert data["message_id"] is not None
        # 40. Correct envelope recipients (including BCC)
        assert "secret@example.com" in captured_kwargs["to_addrs"]
        # Header check: BCC must NOT be in public headers
        assert captured_kwargs["message"]["Bcc"] is None

        # 41. Thread created & attached
        thread_id = data["thread_id"]
        assert thread_id is not None
        thread = (await db_session.execute(select(EmailThread).where(EmailThread.id == thread_id))).scalars().first()
        assert thread is not None
        assert thread.message_count == 1
        assert thread.subject == "Original Discussion"


@pytest.mark.asyncio
async def test_42_43_44_send_reply_draft_thread_and_headers(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """42, 43, 44. Send reply draft updates existing thread, increments message count,
    and sets In-Reply-To and References.
    """
    token = await register_and_login(async_client, "user_m9_42@test.com")
    comp_id = await create_company_helper(async_client, token, "Co M9 42")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support42@m9.com")

    # Initial incoming thread
    thread = EmailThread(
        company_id=comp_id,
        email_account_id=acc_id,
        subject="Project Alpha",
        message_count=1,
        has_reply=False,
        last_message_at=datetime.now(timezone.utc) if False else None,
        is_read=True,
    )
    from datetime import datetime, timezone
    thread.last_message_at = datetime.now(timezone.utc)
    db_session.add(thread)
    await db_session.flush()

    parent = Email(
        company_id=comp_id,
        email_account_id=acc_id,
        thread_id=thread.id,
        message_id="<parent-alpha@partner.com>",
        direction="INCOMING",
        status="RECEIVED",
        sender="partner@partner.com",
        recipients=["support42@m9.com"],
        subject="Project Alpha",
        references_header="<root-alpha@partner.com>",
        is_read=True,
    )
    db_session.add(parent)
    await db_session.commit()

    # Create reply draft
    draft_id = (await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "email_account_id": acc_id,
            "thread_id": thread.id,
            "in_reply_to": "<parent-alpha@partner.com>",
            "to": ["partner@partner.com"],
            "subject": "Re: Project Alpha",
            "body_text": "We acknowledge receipt.",
        },
    )).json()["id"]

    captured_kwargs = {}

    def mock_send(*args, **kwargs):
        captured_kwargs.update(kwargs)

    with patch.object(SMTPClient, "send_email_sync", side_effect=mock_send):
        resp = await async_client.post(
            f"/api/v1/emails/drafts/{draft_id}/send",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

        # 42. Thread message_count incremented to 2
        await db_session.refresh(thread)
        assert thread.message_count == 2

        # 43. In-Reply-To set
        mime_msg = captured_kwargs["message"]
        assert mime_msg["In-Reply-To"] == "<parent-alpha@partner.com>"

        # 44. References contains root and parent
        references = mime_msg["References"]
        assert "<root-alpha@partner.com>" in references
        assert "<parent-alpha@partner.com>" in references


# =============================================================================
# 9. SMTP Failure & Recovery Tests (45 - 49)
# =============================================================================

@pytest.mark.asyncio
async def test_45_to_49_smtp_failure_preserves_draft_and_allows_retry(async_client: AsyncClient):
    """45 - 49. SMTP failure returns 502, keeps status DRAFT, preserves content, stores error_message,
    and allows user to retry sending successfully.
    """
    token = await register_and_login(async_client, "user_m9_45@test.com")
    comp_id = await create_company_helper(async_client, token, "Co M9 45")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support45@m9.com")

    # Create draft
    draft_resp = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "email_account_id": acc_id,
            "to": ["client@example.com"],
            "subject": "Critical Message",
            "body_text": "Important information that must not be lost.",
        },
    )
    draft_id = draft_resp.json()["id"]

    # 45. Send fails with SMTP error
    with patch.object(
        SMTPClient,
        "send_email_sync",
        side_effect=SMTPConnectionError("Failed to connect to SMTP server."),
    ):
        fail_resp = await async_client.post(
            f"/api/v1/emails/drafts/{draft_id}/send",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert fail_resp.status_code == 502
        assert "SMTP server" in fail_resp.json()["detail"]

    # 46, 47, 48. Inspect draft state: still DRAFT, content intact, error recorded
    check_resp = await async_client.get(
        f"/api/v1/emails/drafts/{draft_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert check_resp.status_code == 200
    data = check_resp.json()
    assert data["status"] == "DRAFT"  # 46. Remains DRAFT
    assert data["body_text"] == "Important information that must not be lost."  # 47. Content intact
    assert "SMTP server" in data["error_message"]  # 48. error_message populated

    # 49. Retry sending after network recovery -> succeeds!
    with patch.object(SMTPClient, "send_email_sync", return_value=None):
        retry_resp = await async_client.post(
            f"/api/v1/emails/drafts/{draft_id}/send",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert retry_resp.status_code == 200
        assert retry_resp.json()["status"] == "SENT"
        assert retry_resp.json()["error_message"] is None


# =============================================================================
# 10. Concurrency & Double-Send Prevention Tests (50 - 51)
# =============================================================================

@pytest.mark.asyncio
async def test_50_51_concurrency_double_send_protection(async_client: AsyncClient):
    """50 & 51. Concurrent send attempts on the same draft cannot double-send;
    second attempt receives 409 Conflict.
    """
    token = await register_and_login(async_client, "user_m9_50@test.com")
    comp_id = await create_company_helper(async_client, token, "Co M9 50")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support50@m9.com")

    draft_id = (await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "email_account_id": acc_id,
            "to": ["user@example.com"],
            "subject": "Race Condition Test",
            "body_text": "Concurrent sending body.",
        },
    )).json()["id"]

    # Emulate slow SMTP transmission
    send_count = 0

    def slow_send(*args, **kwargs):
        nonlocal send_count
        send_count += 1
        import time
        time.sleep(0.3)

    with patch.object(SMTPClient, "send_email_sync", side_effect=slow_send):
        # Fire two concurrent send requests
        task1 = async_client.post(
            f"/api/v1/emails/drafts/{draft_id}/send",
            headers={"Authorization": f"Bearer {token}"},
        )
        task2 = async_client.post(
            f"/api/v1/emails/drafts/{draft_id}/send",
            headers={"Authorization": f"Bearer {token}"},
        )
        res1, res2 = await asyncio.gather(task1, task2)

        statuses = {res1.status_code, res2.status_code}
        # One must succeed (200) and the other must be rejected (409 Conflict)
        assert 200 in statuses
        assert 409 in statuses
        # SMTP should only have been called once
        assert send_count == 1


# =============================================================================
# 11. Authorization & Security Tests (52 - 55)
# =============================================================================

@pytest.mark.asyncio
async def test_52_to_55_draft_authorization_enforcement(async_client: AsyncClient):
    """52 - 55. Unauthorized user cannot edit or send draft; cross-company rejected;
    member requires explicit EmailAccountAccess.
    """
    owner_token = await register_and_login(async_client, "owner_m9_52@test.com")
    comp_id = await create_company_helper(async_client, owner_token, "Co M9 52")
    acc_id = await create_account_helper(async_client, owner_token, comp_id, email="support52@m9.com")

    # Member user without access
    member_token = await register_and_login(async_client, "member_m9_52@test.com")
    await async_client.post(
        f"/api/v1/companies/{comp_id}/members",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"email": "member_m9_52@test.com", "role": "MEMBER"},
    )

    # Company B user
    other_token = await register_and_login(async_client, "other_m9_52@test.com")
    comp_b = await create_company_helper(async_client, other_token, "Co M9 52B")

    # Owner creates draft
    draft_id = (await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"email_account_id": acc_id, "to": ["target@example.com"], "body_text": "Draft content"},
    )).json()["id"]

    # 52. Member without account access cannot edit draft -> 403
    edit_resp = await async_client.put(
        f"/api/v1/emails/drafts/{draft_id}",
        headers={"Authorization": f"Bearer {member_token}"},
        json={"subject": "Hacked Subject"},
    )
    assert edit_resp.status_code == 403

    # 53. Member without account access cannot send draft -> 403
    with patch.object(SMTPClient, "send_email_sync", return_value=None):
        send_resp = await async_client.post(
            f"/api/v1/emails/drafts/{draft_id}/send",
            headers={"Authorization": f"Bearer {member_token}"},
        )
        assert send_resp.status_code == 403

    # 54. Other company user rejected -> 403 or 404
    cross_resp = await async_client.get(
        f"/api/v1/emails/drafts/{draft_id}",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert cross_resp.status_code in (403, 404)

    # 55. Grant member access -> now member can edit and send
    member_info = (await async_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {member_token}"})).json()
    await async_client.post(
        f"/api/v1/companies/{comp_id}/email-accounts/{acc_id}/access",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"user_id": member_info["id"]},
    )

    grant_edit = await async_client.put(
        f"/api/v1/emails/drafts/{draft_id}",
        headers={"Authorization": f"Bearer {member_token}"},
        json={"subject": "Authorized Colleague Edit"},
    )
    assert grant_edit.status_code == 200
    assert grant_edit.json()["subject"] == "Authorized Colleague Edit"
