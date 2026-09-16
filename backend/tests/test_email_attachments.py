import io
import os
from pathlib import Path
from unittest.mock import patch
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.storage import attachment_storage_service
from app.modules.email_accounts.models import EmailAccount, EmailAccountAccess
from app.modules.emails.models import Email, EmailAttachment, EmailStatus
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
):
    """Grant a user access to an email account."""
    resp = await client.post(
        f"/api/v1/companies/{company_id}/email-accounts/{account_id}/access",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"user_id": user_id},
    )
    assert resp.status_code in (200, 201)


# =============================================================================
# 1. Storage & Upload Validation Tests
# =============================================================================

@pytest.mark.asyncio
async def test_01_upload_attachment_metadata_and_storage(async_client: AsyncClient, db_session: AsyncSession):
    """1. Upload valid attachment: stores metadata and disk file correctly."""
    token = await register_and_login(async_client, "m12_user01@test.com")
    comp_id = await create_company_helper(async_client, token, "Co M12 01")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support01@m12.com")

    # Create draft
    draft_resp = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={"email_account_id": acc_id, "subject": "Draft with Attachment"},
    )
    draft_id = draft_resp.json()["id"]

    # Upload file
    file_content = b"PDF dummy content for testing attachments"
    files = {
        "file": ("invoice.pdf", io.BytesIO(file_content), "application/pdf")
    }

    upload_resp = await async_client.post(
        f"/api/v1/emails/drafts/{draft_id}/attachments",
        headers={"Authorization": f"Bearer {token}"},
        files=files,
    )
    assert upload_resp.status_code == 201
    data = upload_resp.json()
    assert data["id"] is not None
    assert data["file_name"] == "invoice.pdf"
    assert data["content_type"] == "application/pdf"
    assert data["file_size"] == len(file_content)
    assert data["email_id"] == draft_id
    assert "storage_path" not in data  # Server storage path never exposed in response

    # Verify disk storage
    att_id = data["id"]
    att_record = (await db_session.execute(select(EmailAttachment).where(EmailAttachment.id == att_id))).scalars().first()
    assert att_record is not None
    assert att_record.file_name == "invoice.pdf"
    assert att_record.company_id == comp_id
    assert att_record.email_account_id == acc_id
    disk_path = attachment_storage_service.resolve_storage_path(att_record.storage_path)
    assert disk_path.exists()
    assert disk_path.read_bytes() == file_content

    # Cleanup disk file
    attachment_storage_service.delete_file_sync(att_record.storage_path)


@pytest.mark.asyncio
async def test_02_reject_empty_file(async_client: AsyncClient):
    """2. Reject 0-byte file with 400 Bad Request."""
    token = await register_and_login(async_client, "m12_user02@test.com")
    comp_id = await create_company_helper(async_client, token, "Co M12 02")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support02@m12.com")

    draft_resp = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={"email_account_id": acc_id},
    )
    draft_id = draft_resp.json()["id"]

    files = {
        "file": ("empty.txt", io.BytesIO(b""), "text/plain")
    }
    resp = await async_client.post(
        f"/api/v1/emails/drafts/{draft_id}/attachments",
        headers={"Authorization": f"Bearer {token}"},
        files=files,
    )
    assert resp.status_code == 400
    assert "empty" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_03_reject_oversized_file(async_client: AsyncClient):
    """3. Reject file exceeding max configured size (413 Payload Too Large)."""
    token = await register_and_login(async_client, "m12_user03@test.com")
    comp_id = await create_company_helper(async_client, token, "Co M12 03")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support03@m12.com")

    draft_resp = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={"email_account_id": acc_id},
    )
    draft_id = draft_resp.json()["id"]

    # Temporarily set MAX_ATTACHMENT_SIZE_BYTES to 1 KB for test
    with patch.object(settings, "MAX_ATTACHMENT_SIZE_BYTES", 1024):
        files = {
            "file": ("large.dat", io.BytesIO(b"x" * 2048), "application/octet-stream")
        }
        resp = await async_client.post(
            f"/api/v1/emails/drafts/{draft_id}/attachments",
            headers={"Authorization": f"Bearer {token}"},
            files=files,
        )
        assert resp.status_code == 413
        assert "exceeds" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_04_reject_dangerous_executable_extensions(async_client: AsyncClient):
    """4. Reject dangerous executable files (.exe, .bat, .sh, .cmd, .ps1) with 400 Bad Request."""
    token = await register_and_login(async_client, "m12_user04@test.com")
    comp_id = await create_company_helper(async_client, token, "Co M12 04")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support04@m12.com")

    draft_resp = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={"email_account_id": acc_id},
    )
    draft_id = draft_resp.json()["id"]

    for dangerous_name in ["malware.exe", "script.bat", "run.sh", "payload.cmd", "exploit.ps1"]:
        files = {
            "file": (dangerous_name, io.BytesIO(b"malicious content"), "application/octet-stream")
        }
        resp = await async_client.post(
            f"/api/v1/emails/drafts/{draft_id}/attachments",
            headers={"Authorization": f"Bearer {token}"},
            files=files,
        )
        assert resp.status_code == 400
        assert "not allowed" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_05_path_traversal_filename_normalized(async_client: AsyncClient, db_session: AsyncSession):
    """5. Path traversal filename like '../../secret.pdf' is safely normalized to 'secret.pdf'."""
    token = await register_and_login(async_client, "m12_user05@test.com")
    comp_id = await create_company_helper(async_client, token, "Co M12 05")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support05@m12.com")

    draft_resp = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={"email_account_id": acc_id},
    )
    draft_id = draft_resp.json()["id"]

    files = {
        "file": ("../../../../etc/passwd_report.pdf", io.BytesIO(b"%PDF-report-data"), "application/pdf")
    }
    resp = await async_client.post(
        f"/api/v1/emails/drafts/{draft_id}/attachments",
        headers={"Authorization": f"Bearer {token}"},
        files=files,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["file_name"] == "passwd_report.pdf"
    assert "/" not in data["file_name"]
    assert "\\" not in data["file_name"]
    assert ".." not in data["file_name"]

    # Verify on disk that storage path does not escape base directory
    att_id = data["id"]
    att_record = (await db_session.execute(select(EmailAttachment).where(EmailAttachment.id == att_id))).scalars().first()
    assert att_record is not None
    resolved = attachment_storage_service.resolve_storage_path(att_record.storage_path)
    assert str(resolved).startswith(str(attachment_storage_service.get_base_upload_dir()))

    # Clean up
    attachment_storage_service.delete_file_sync(att_record.storage_path)


# =============================================================================
# 2. Authorization Tests
# =============================================================================

@pytest.mark.asyncio
async def test_06_unauthorized_account_member_rejected(async_client: AsyncClient):
    """6. Company member without EmailAccountAccess cannot upload, view, or delete attachments (403)."""
    owner_token = await register_and_login(async_client, "m12_owner06@test.com")
    comp_id = await create_company_helper(async_client, owner_token, "Co M12 06")
    acc_id = await create_account_helper(async_client, owner_token, comp_id, email="support06@m12.com")

    # Colleague registered & added as company member, but NOT given EmailAccountAccess
    colleague_token = await register_and_login(async_client, "m12_colleague06@test.com")
    await add_company_member_helper(async_client, owner_token, comp_id, "m12_colleague06@test.com", role="MEMBER")

    # Owner creates draft and uploads attachment
    draft_resp = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"email_account_id": acc_id},
    )
    draft_id = draft_resp.json()["id"]

    upload_resp = await async_client.post(
        f"/api/v1/emails/drafts/{draft_id}/attachments",
        headers={"Authorization": f"Bearer {owner_token}"},
        files={"file": ("notes.txt", io.BytesIO(b"important notes"), "text/plain")},
    )
    assert upload_resp.status_code == 201
    att_id = upload_resp.json()["id"]

    # Colleague tries to upload to draft -> 403
    resp_upload = await async_client.post(
        f"/api/v1/emails/drafts/{draft_id}/attachments",
        headers={"Authorization": f"Bearer {colleague_token}"},
        files={"file": ("colleague.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    assert resp_upload.status_code == 403

    # Colleague tries to list draft attachments -> 403
    resp_list = await async_client.get(
        f"/api/v1/emails/drafts/{draft_id}/attachments",
        headers={"Authorization": f"Bearer {colleague_token}"},
    )
    assert resp_list.status_code == 403

    # Colleague tries to download attachment -> 403
    resp_down = await async_client.get(
        f"/api/v1/emails/{draft_id}/attachments/{att_id}/download",
        headers={"Authorization": f"Bearer {colleague_token}"},
    )
    assert resp_down.status_code == 403

    # Colleague tries to delete attachment -> 403
    resp_del = await async_client.delete(
        f"/api/v1/emails/drafts/{draft_id}/attachments/{att_id}",
        headers={"Authorization": f"Bearer {colleague_token}"},
    )
    assert resp_del.status_code == 403


@pytest.mark.asyncio
async def test_07_cross_company_access_rejected(async_client: AsyncClient):
    """7. User from another company cannot upload or download attachments (403/404)."""
    token_a = await register_and_login(async_client, "m12_user07a@test.com")
    comp_a = await create_company_helper(async_client, token_a, "Co M12 07A")
    acc_a = await create_account_helper(async_client, token_a, comp_a, email="support07a@m12.com")

    token_b = await register_and_login(async_client, "m12_user07b@test.com")
    comp_b = await create_company_helper(async_client, token_b, "Co M12 07B")

    draft_resp = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"email_account_id": acc_a},
    )
    draft_id = draft_resp.json()["id"]

    upload_resp = await async_client.post(
        f"/api/v1/emails/drafts/{draft_id}/attachments",
        headers={"Authorization": f"Bearer {token_a}"},
        files={"file": ("secret_a.pdf", io.BytesIO(b"%PDF confidential"), "application/pdf")},
    )
    att_id = upload_resp.json()["id"]

    # User B tries to download attachment -> 403/404
    resp = await async_client.get(
        f"/api/v1/emails/{draft_id}/attachments/{att_id}/download",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp.status_code in (403, 404)

    # User B tries to upload attachment to Draft A -> 403/404
    resp_up = await async_client.post(
        f"/api/v1/emails/drafts/{draft_id}/attachments",
        headers={"Authorization": f"Bearer {token_b}"},
        files={"file": ("injected.pdf", io.BytesIO(b"%PDF"), "application/pdf")},
    )
    assert resp_up.status_code in (403, 404)


@pytest.mark.asyncio
async def test_08_authorized_account_member_can_access(async_client: AsyncClient):
    """8. Authorized team member with EmailAccountAccess can upload, view, and download draft attachments."""
    owner_token = await register_and_login(async_client, "m12_owner08@test.com")
    comp_id = await create_company_helper(async_client, owner_token, "Co M12 08")
    acc_id = await create_account_helper(async_client, owner_token, comp_id, email="support08@m12.com")

    colleague_token = await register_and_login(async_client, "m12_colleague08@test.com")
    colleague_id = await add_company_member_helper(async_client, owner_token, comp_id, "m12_colleague08@test.com", role="MEMBER")
    await grant_account_access_helper(async_client, owner_token, comp_id, acc_id, colleague_id)

    # Owner creates draft
    draft_resp = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"email_account_id": acc_id},
    )
    draft_id = draft_resp.json()["id"]

    # Colleague uploads attachment
    colleague_file = b"Colleague uploaded spec document"
    upload_resp = await async_client.post(
        f"/api/v1/emails/drafts/{draft_id}/attachments",
        headers={"Authorization": f"Bearer {colleague_token}"},
        files={"file": ("spec.txt", io.BytesIO(colleague_file), "text/plain")},
    )
    assert upload_resp.status_code == 201
    att_id = upload_resp.json()["id"]

    # Owner downloads colleague's attachment
    down_resp = await async_client.get(
        f"/api/v1/emails/{draft_id}/attachments/{att_id}/download",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert down_resp.status_code == 200
    assert down_resp.content == colleague_file


# =============================================================================
# 3. Draft Attachment Lifecycle Tests
# =============================================================================

@pytest.mark.asyncio
async def test_09_multiple_attachments_and_listing(async_client: AsyncClient):
    """9. Upload multiple attachments and list them for draft."""
    token = await register_and_login(async_client, "m12_user09@test.com")
    comp_id = await create_company_helper(async_client, token, "Co M12 09")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support09@m12.com")

    draft_resp = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={"email_account_id": acc_id, "subject": "Multiple Attachments"},
    )
    draft_id = draft_resp.json()["id"]

    # Upload 1
    r1 = await async_client.post(
        f"/api/v1/emails/drafts/{draft_id}/attachments",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("doc1.pdf", io.BytesIO(b"PDF doc 1"), "application/pdf")},
    )
    assert r1.status_code == 201

    # Upload 2
    r2 = await async_client.post(
        f"/api/v1/emails/drafts/{draft_id}/attachments",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("image.png", io.BytesIO(b"\x89PNG\r\n\x1a\n..."), "image/png")},
    )
    assert r2.status_code == 201

    # List attachments
    list_resp = await async_client.get(
        f"/api/v1/emails/drafts/{draft_id}/attachments",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_resp.status_code == 200
    items = list_resp.json()["attachments"]
    assert len(items) == 2
    filenames = {i["file_name"] for i in items}
    assert filenames == {"doc1.pdf", "image.png"}


@pytest.mark.asyncio
async def test_10_delete_attachment_from_draft(async_client: AsyncClient, db_session: AsyncSession):
    """10. Delete attachment removes database record and stored file."""
    token = await register_and_login(async_client, "m12_user10@test.com")
    comp_id = await create_company_helper(async_client, token, "Co M12 10")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support10@m12.com")

    draft_resp = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={"email_account_id": acc_id},
    )
    draft_id = draft_resp.json()["id"]

    up = await async_client.post(
        f"/api/v1/emails/drafts/{draft_id}/attachments",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("to_remove.txt", io.BytesIO(b"will be deleted"), "text/plain")},
    )
    att_id = up.json()["id"]

    # Fetch storage path
    att_record = (await db_session.execute(select(EmailAttachment).where(EmailAttachment.id == att_id))).scalars().first()
    storage_path = att_record.storage_path
    disk_path = attachment_storage_service.resolve_storage_path(storage_path)
    assert disk_path.exists()

    # Delete attachment
    del_resp = await async_client.delete(
        f"/api/v1/emails/drafts/{draft_id}/attachments/{att_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_resp.status_code == 204

    # Verify DB record gone
    att_check = (await db_session.execute(select(EmailAttachment).where(EmailAttachment.id == att_id))).scalars().first()
    assert att_check is None

    # Verify disk file deleted
    assert not disk_path.exists()


@pytest.mark.asyncio
async def test_11_draft_update_preserves_attachments(async_client: AsyncClient):
    """11. Updating draft subject/body does not affect uploaded attachments."""
    token = await register_and_login(async_client, "m12_user11@test.com")
    comp_id = await create_company_helper(async_client, token, "Co M12 11")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support11@m12.com")

    draft_resp = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={"email_account_id": acc_id, "subject": "Original Subject"},
    )
    draft_id = draft_resp.json()["id"]

    await async_client.post(
        f"/api/v1/emails/drafts/{draft_id}/attachments",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("kept.pdf", io.BytesIO(b"%PDF kept"), "application/pdf")},
    )

    # Update draft body and subject
    patch_resp = await async_client.put(
        f"/api/v1/emails/drafts/{draft_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"subject": "Updated Subject", "body_text": "Updated body text"},
    )
    assert patch_resp.status_code == 200

    # Attachments still present
    list_resp = await async_client.get(
        f"/api/v1/emails/drafts/{draft_id}/attachments",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_resp.status_code == 200
    assert len(list_resp.json()["attachments"]) == 1
    assert list_resp.json()["attachments"][0]["file_name"] == "kept.pdf"


@pytest.mark.asyncio
async def test_12_cannot_upload_or_delete_on_deleted_draft(async_client: AsyncClient):
    """12. Cannot upload or delete attachments on soft-deleted draft (400)."""
    token = await register_and_login(async_client, "m12_user12@test.com")
    comp_id = await create_company_helper(async_client, token, "Co M12 12")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support12@m12.com")

    draft_resp = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={"email_account_id": acc_id},
    )
    draft_id = draft_resp.json()["id"]

    # Upload attachment first
    up = await async_client.post(
        f"/api/v1/emails/drafts/{draft_id}/attachments",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("test.txt", io.BytesIO(b"data"), "text/plain")},
    )
    att_id = up.json()["id"]

    # Discard draft (soft-delete to Trash)
    await async_client.delete(
        f"/api/v1/emails/drafts/{draft_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    # Attempt upload on discarded draft -> 400
    resp_up = await async_client.post(
        f"/api/v1/emails/drafts/{draft_id}/attachments",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("another.txt", io.BytesIO(b"data2"), "text/plain")},
    )
    assert resp_up.status_code == 400

    # Attempt delete on discarded draft -> 400
    resp_del = await async_client.delete(
        f"/api/v1/emails/drafts/{draft_id}/attachments/{att_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_del.status_code == 400


# =============================================================================
# 4. Sending Integration & MIME Construction Tests
# =============================================================================

@pytest.mark.asyncio
async def test_13_send_draft_with_attachments_mime_and_binary(async_client: AsyncClient):
    """13. Send draft with attachments: MIME message contains multipart attachments,
    correct filename, content-type, binary integrity, and headers.
    """
    token = await register_and_login(async_client, "m12_user13@test.com")
    comp_id = await create_company_helper(async_client, token, "Co M12 13")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support13@m12.com")

    # Create draft
    draft_resp = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "email_account_id": acc_id,
            "to": ["partner@example.com"],
            "subject": "Proposal with Contract",
            "body_text": "Please see attached contract and diagram.",
            "body_html": "<p>Please see attached contract and diagram.</p>",
        },
    )
    draft_id = draft_resp.json()["id"]

    pdf_bytes = b"%PDF-1.4 binary data \x00\x01\x02\xff"
    png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"

    # Add 2 attachments
    await async_client.post(
        f"/api/v1/emails/drafts/{draft_id}/attachments",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("contract.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    await async_client.post(
        f"/api/v1/emails/drafts/{draft_id}/attachments",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("architecture.png", io.BytesIO(png_bytes), "image/png")},
    )

    captured_kwargs = {}

    def mock_send(*args, **kwargs):
        captured_kwargs.update(kwargs)

    with patch.object(SMTPClient, "send_email_sync", side_effect=mock_send):
        send_resp = await async_client.post(
            f"/api/v1/emails/drafts/{draft_id}/send",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert send_resp.status_code == 200
        assert send_resp.json()["status"] == "SENT"

        # Verify MIME construction
        mime_msg = captured_kwargs["message"]
        assert mime_msg.is_multipart()

        attachments = list(mime_msg.iter_attachments())
        assert len(attachments) == 2

        filenames = [att.get_filename() for att in attachments]
        assert "contract.pdf" in filenames
        assert "architecture.png" in filenames

        for att in attachments:
            fname = att.get_filename()
            payload = att.get_content()
            if fname == "contract.pdf":
                assert att.get_content_type() == "application/pdf"
                assert payload == pdf_bytes
            elif fname == "architecture.png":
                assert att.get_content_type() == "image/png"
                assert payload == png_bytes


@pytest.mark.asyncio
async def test_14_smtp_failure_preserves_draft_and_attachments(async_client: AsyncClient):
    """14. SMTP failure keeps draft in DRAFT status and preserves attachments for retry."""
    token = await register_and_login(async_client, "m12_user14@test.com")
    comp_id = await create_company_helper(async_client, token, "Co M12 14")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support14@m12.com")

    draft_resp = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "email_account_id": acc_id,
            "to": ["client@example.com"],
            "subject": "Failing send test",
            "body_text": "Content",
        },
    )
    draft_id = draft_resp.json()["id"]

    # Upload attachment
    await async_client.post(
        f"/api/v1/emails/drafts/{draft_id}/attachments",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("statement.pdf", io.BytesIO(b"%PDF stmt"), "application/pdf")},
    )

    # Mock SMTP to raise exception
    with patch.object(SMTPClient, "send_email_sync", side_effect=RuntimeError("SMTP Connection Refused")):
        send_resp = await async_client.post(
            f"/api/v1/emails/drafts/{draft_id}/send",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert send_resp.status_code == 502

    # Check draft is still DRAFT
    get_draft = await async_client.get(
        f"/api/v1/emails/drafts/{draft_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_draft.status_code == 200
    assert get_draft.json()["status"] == "DRAFT"

    # Attachments still exist
    list_resp = await async_client.get(
        f"/api/v1/emails/drafts/{draft_id}/attachments",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_resp.status_code == 200
    assert len(list_resp.json()["attachments"]) == 1
    assert list_resp.json()["attachments"][0]["file_name"] == "statement.pdf"


# =============================================================================
# 5. Sent-Email Attachment Lifecycle Tests
# =============================================================================

@pytest.mark.asyncio
async def test_15_sent_email_attachments_accessible(async_client: AsyncClient):
    """15. After successful send, attachments remain associated with sent email and are downloadable."""
    token = await register_and_login(async_client, "m12_user15@test.com")
    comp_id = await create_company_helper(async_client, token, "Co M12 15")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support15@m12.com")

    draft_resp = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "email_account_id": acc_id,
            "to": ["recipient@example.com"],
            "subject": "Sent Attachment Check",
            "body_text": "Here is the document.",
        },
    )
    email_id = draft_resp.json()["id"]

    file_bytes = b"Final Report 2026 Content"
    up_resp = await async_client.post(
        f"/api/v1/emails/drafts/{email_id}/attachments",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("report_2026.pdf", io.BytesIO(file_bytes), "application/pdf")},
    )
    att_id = up_resp.json()["id"]

    # Send email
    with patch.object(SMTPClient, "send_email_sync"):
        send_resp = await async_client.post(
            f"/api/v1/emails/drafts/{email_id}/send",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert send_resp.status_code == 200

    # Retrieve sent email's attachments via /emails/{email_id}/attachments
    list_resp = await async_client.get(
        f"/api/v1/emails/{email_id}/attachments",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_resp.status_code == 200
    items = list_resp.json()["attachments"]
    assert len(items) == 1
    assert items[0]["file_name"] == "report_2026.pdf"

    # Download attachment from sent email
    down_resp = await async_client.get(
        f"/api/v1/emails/{email_id}/attachments/{att_id}/download",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert down_resp.status_code == 200
    assert down_resp.content == file_bytes
    assert 'attachment; filename="report_2026.pdf"' in down_resp.headers.get("content-disposition", "")

    # Cannot delete attachment from sent email (only drafts allow attachment deletion)
    del_resp = await async_client.delete(
        f"/api/v1/emails/drafts/{email_id}/attachments/{att_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_resp.status_code == 400


@pytest.mark.asyncio
async def test_16_permanent_deletion_cleans_attachment_files(async_client: AsyncClient, db_session: AsyncSession):
    """16. Permanent deletion of an email purges its attachment records and disk files."""
    token = await register_and_login(async_client, "m12_user16@test.com")
    comp_id = await create_company_helper(async_client, token, "Co M12 16")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support16@m12.com")

    draft_resp = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={"email_account_id": acc_id, "subject": "To Be Purged"},
    )
    email_id = draft_resp.json()["id"]

    up_resp = await async_client.post(
        f"/api/v1/emails/drafts/{email_id}/attachments",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("to_purge.pdf", io.BytesIO(b"%PDF will be purged"), "application/pdf")},
    )
    att_id = up_resp.json()["id"]

    att_record = (await db_session.execute(select(EmailAttachment).where(EmailAttachment.id == att_id))).scalars().first()
    disk_path = attachment_storage_service.resolve_storage_path(att_record.storage_path)
    assert disk_path.exists()

    # Soft delete (move to Trash)
    del1 = await async_client.delete(
        f"/api/v1/emails/{email_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del1.status_code == 200
    # While in trash, file still exists
    assert disk_path.exists()

    # Permanent delete from Trash
    del2 = await async_client.delete(
        f"/api/v1/emails/{email_id}/permanent",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del2.status_code == 200

    # Attachment record and disk file must be purged
    assert not disk_path.exists()
    att_check = (await db_session.execute(select(EmailAttachment).where(EmailAttachment.id == att_id))).scalars().first()
    assert att_check is None


# =============================================================================
# 6. Direct Email Sending with Attachments Tests (17 - 25)
# =============================================================================

@pytest.mark.asyncio
async def test_17_direct_send_without_attachments_still_works(async_client: AsyncClient):
    """17. Direct send via POST /api/v1/emails/send without attachments still works normally."""
    token = await register_and_login(async_client, "m12_user17@test.com")
    comp_id = await create_company_helper(async_client, token, "Co M12 17")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support17@m12.com")

    with patch.object(SMTPClient, "send_email_sync"):
        resp = await async_client.post(
            "/api/v1/emails/send",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email_account_id": acc_id,
                "to": ["user@example.com"],
                "subject": "Direct send without attachments",
                "body_text": "Plain text message",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "SENT"
        assert data["subject"] == "Direct send without attachments"


@pytest.mark.asyncio
async def test_18_direct_send_with_one_attachment(async_client: AsyncClient, db_session: AsyncSession):
    """18. Direct send with one attachment: MIME includes attachment and DB associates attachment with sent email."""
    token = await register_and_login(async_client, "m12_user18@test.com")
    comp_id = await create_company_helper(async_client, token, "Co M12 18")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support18@m12.com")

    # Upload attachment to a temporary draft
    draft_resp = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={"email_account_id": acc_id},
    )
    draft_id = draft_resp.json()["id"]

    pdf_content = b"%PDF-1.4 direct send document content"
    up_resp = await async_client.post(
        f"/api/v1/emails/drafts/{draft_id}/attachments",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("manual.pdf", io.BytesIO(pdf_content), "application/pdf")},
    )
    assert up_resp.status_code == 201
    att_id = up_resp.json()["id"]

    captured_kwargs = {}

    def mock_send(*args, **kwargs):
        captured_kwargs.update(kwargs)

    with patch.object(SMTPClient, "send_email_sync", side_effect=mock_send):
        send_resp = await async_client.post(
            "/api/v1/emails/send",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email_account_id": acc_id,
                "to": ["client@example.com"],
                "subject": "Direct Send with Attachment",
                "body_text": "Here is the user manual.",
                "attachment_ids": [att_id],
            },
        )
        assert send_resp.status_code == 201
        sent_data = send_resp.json()
        sent_email_id = sent_data["id"]

        # Verify MIME message
        mime_msg = captured_kwargs["message"]
        attachments = list(mime_msg.iter_attachments())
        assert len(attachments) == 1
        assert attachments[0].get_filename() == "manual.pdf"
        assert attachments[0].get_content_type() == "application/pdf"
        assert attachments[0].get_content() == pdf_content

        # Verify database association: attachment is now associated with sent_email_id
        att_rec = (await db_session.execute(select(EmailAttachment).where(EmailAttachment.id == att_id))).scalars().first()
        assert att_rec is not None
        assert att_rec.email_id == sent_email_id


@pytest.mark.asyncio
async def test_19_direct_send_with_multiple_attachments_and_binary_integrity(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """19. Direct send with multiple attachments preserves binary content, filenames, and content-types."""
    token = await register_and_login(async_client, "m12_user19@test.com")
    comp_id = await create_company_helper(async_client, token, "Co M12 19")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support19@m12.com")

    draft_resp = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={"email_account_id": acc_id},
    )
    draft_id = draft_resp.json()["id"]

    pdf_bytes = b"%PDF-1.4 binary \x00\x01\x02\xfe\xff"
    png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00"

    att1_id = (await async_client.post(
        f"/api/v1/emails/drafts/{draft_id}/attachments",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("contract.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )).json()["id"]

    att2_id = (await async_client.post(
        f"/api/v1/emails/drafts/{draft_id}/attachments",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("diagram.png", io.BytesIO(png_bytes), "image/png")},
    )).json()["id"]

    captured_kwargs = {}

    def mock_send(*args, **kwargs):
        captured_kwargs.update(kwargs)

    with patch.object(SMTPClient, "send_email_sync", side_effect=mock_send):
        send_resp = await async_client.post(
            "/api/v1/emails/send",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email_account_id": acc_id,
                "to": ["partner@example.com"],
                "subject": "Multiple Attachments Direct Send",
                "body_text": "Please check both attached files.",
                "attachment_ids": [att1_id, att2_id],
            },
        )
        assert send_resp.status_code == 201
        email_id = send_resp.json()["id"]

        # Verify MIME parts
        mime_msg = captured_kwargs["message"]
        attachments = list(mime_msg.iter_attachments())
        assert len(attachments) == 2
        names = {att.get_filename() for att in attachments}
        assert names == {"contract.pdf", "diagram.png"}

        for att in attachments:
            if att.get_filename() == "contract.pdf":
                assert att.get_content_type() == "application/pdf"
                assert att.get_content() == pdf_bytes
            elif att.get_filename() == "diagram.png":
                assert att.get_content_type() == "image/png"
                assert att.get_content() == png_bytes

        # Verify both attachments re-linked to sent email
        att_list = (await db_session.execute(
            select(EmailAttachment).where(EmailAttachment.email_id == email_id)
        )).scalars().all()
        assert len(att_list) == 2


@pytest.mark.asyncio
async def test_20_direct_send_invalid_attachment_id_rejected_before_smtp(async_client: AsyncClient):
    """20. Nonexistent attachment ID in direct send is rejected with 404 before SMTP."""
    token = await register_and_login(async_client, "m12_user20@test.com")
    comp_id = await create_company_helper(async_client, token, "Co M12 20")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support20@m12.com")

    with patch.object(SMTPClient, "send_email_sync") as mock_smtp:
        resp = await async_client.post(
            "/api/v1/emails/send",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email_account_id": acc_id,
                "to": ["client@example.com"],
                "subject": "Invalid attachment ID test",
                "body_text": "Content",
                "attachment_ids": [99999],
            },
        )
        assert resp.status_code == 404
        assert not mock_smtp.called


@pytest.mark.asyncio
async def test_21_direct_send_cross_account_attachment_rejected(async_client: AsyncClient):
    """21. Attachment from another EmailAccount is rejected with 400 before SMTP."""
    token = await register_and_login(async_client, "m12_user21@test.com")
    comp_id = await create_company_helper(async_client, token, "Co M12 21")
    acc_1 = await create_account_helper(async_client, token, comp_id, email="account1@m12.com")
    acc_2 = await create_account_helper(async_client, token, comp_id, email="account2@m12.com")

    # Create draft and attachment in Account 1
    draft_1 = (await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={"email_account_id": acc_1},
    )).json()["id"]

    att_id = (await async_client.post(
        f"/api/v1/emails/drafts/{draft_1}/attachments",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("file1.pdf", io.BytesIO(b"%PDF data"), "application/pdf")},
    )).json()["id"]

    # Try to send from Account 2 referencing Account 1's attachment
    with patch.object(SMTPClient, "send_email_sync") as mock_smtp:
        resp = await async_client.post(
            "/api/v1/emails/send",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email_account_id": acc_2,
                "to": ["client@example.com"],
                "subject": "Cross Account Attachment Test",
                "body_text": "Content",
                "attachment_ids": [att_id],
            },
        )
        assert resp.status_code == 400
        assert not mock_smtp.called


@pytest.mark.asyncio
async def test_22_direct_send_cross_company_attachment_rejected(async_client: AsyncClient):
    """22. Attachment from another company is rejected with 403/404 before SMTP."""
    token_a = await register_and_login(async_client, "m12_user22a@test.com")
    comp_a = await create_company_helper(async_client, token_a, "Co M12 22A")
    acc_a = await create_account_helper(async_client, token_a, comp_a, email="support22a@m12.com")

    token_b = await register_and_login(async_client, "m12_user22b@test.com")
    comp_b = await create_company_helper(async_client, token_b, "Co M12 22B")
    acc_b = await create_account_helper(async_client, token_b, comp_b, email="support22b@m12.com")

    draft_a = (await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"email_account_id": acc_a},
    )).json()["id"]

    att_a_id = (await async_client.post(
        f"/api/v1/emails/drafts/{draft_a}/attachments",
        headers={"Authorization": f"Bearer {token_a}"},
        files={"file": ("secret_a.pdf", io.BytesIO(b"%PDF confidential"), "application/pdf")},
    )).json()["id"]

    # User B tries to send email referencing Company A's attachment
    with patch.object(SMTPClient, "send_email_sync") as mock_smtp:
        resp = await async_client.post(
            "/api/v1/emails/send",
            headers={"Authorization": f"Bearer {token_b}"},
            json={
                "email_account_id": acc_b,
                "to": ["external@example.com"],
                "subject": "Injected Attachment Test",
                "body_text": "Trying to steal file",
                "attachment_ids": [att_a_id],
            },
        )
        assert resp.status_code in (403, 404)
        assert not mock_smtp.called


@pytest.mark.asyncio
async def test_23_direct_send_smtp_failure_preserves_attachment_state(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """23. SMTP failure during direct send persists FAILED email record and associates attachment for auditability."""
    token = await register_and_login(async_client, "m12_user23@test.com")
    comp_id = await create_company_helper(async_client, token, "Co M12 23")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support23@m12.com")

    draft_id = (await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={"email_account_id": acc_id},
    )).json()["id"]

    att_id = (await async_client.post(
        f"/api/v1/emails/drafts/{draft_id}/attachments",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("audit.pdf", io.BytesIO(b"%PDF audit data"), "application/pdf")},
    )).json()["id"]

    # Mock SMTP to fail
    with patch.object(SMTPClient, "send_email_sync", side_effect=RuntimeError("SMTP Connection Down")):
        resp = await async_client.post(
            "/api/v1/emails/send",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email_account_id": acc_id,
                "to": ["dest@example.com"],
                "subject": "Failing Direct Send",
                "body_text": "Audit document",
                "attachment_ids": [att_id],
            },
        )
        assert resp.status_code == 502

    # Verify attachment is still in DB and attached to the FAILED email record
    att_rec = (await db_session.execute(select(EmailAttachment).where(EmailAttachment.id == att_id))).scalars().first()
    assert att_rec is not None
    failed_email = (await db_session.execute(select(Email).where(Email.id == att_rec.email_id))).scalars().first()
    assert failed_email is not None
    assert failed_email.status == EmailStatus.FAILED.value


@pytest.mark.asyncio
async def test_24_direct_send_with_signature_and_attachment(async_client: AsyncClient):
    """24. Direct send with both signature and attachment integrates correctly in MIME message."""
    token = await register_and_login(async_client, "m12_user24@test.com")
    comp_id = await create_company_helper(async_client, token, "Co M12 24")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support24@m12.com")

    # Create signature
    sig_resp = await async_client.post(
        f"/api/v1/companies/{comp_id}/email-accounts/{acc_id}/signatures",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Default Sig",
            "body_text": "--\nBest regards,\nSupport Team",
            "is_default": True,
        },
    )
    assert sig_resp.status_code == 201

    # Create attachment
    draft_id = (await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={"email_account_id": acc_id},
    )).json()["id"]

    att_id = (await async_client.post(
        f"/api/v1/emails/drafts/{draft_id}/attachments",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("welcome.txt", io.BytesIO(b"Welcome guide"), "text/plain")},
    )).json()["id"]

    captured_kwargs = {}

    def mock_send(*args, **kwargs):
        captured_kwargs.update(kwargs)

    with patch.object(SMTPClient, "send_email_sync", side_effect=mock_send):
        resp = await async_client.post(
            "/api/v1/emails/send",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email_account_id": acc_id,
                "to": ["newuser@example.com"],
                "subject": "Welcome with Attachment",
                "body_text": "Hello, please find your guide attached.",
                "attachment_ids": [att_id],
            },
        )
        assert resp.status_code == 201

        mime_msg = captured_kwargs["message"]
        # Body contains signature
        body_content = mime_msg.get_body(preferencelist=("plain",)).get_content()
        assert "Best regards" in body_content
        # Attachment present
        attachments = list(mime_msg.iter_attachments())
        assert len(attachments) == 1
        assert attachments[0].get_filename() == "welcome.txt"


@pytest.mark.asyncio
async def test_25_direct_send_with_threading_and_attachment(async_client: AsyncClient, db_session: AsyncSession):
    """25. Direct send replying with threading and attachment preserves headers and MIME attachment."""
    token = await register_and_login(async_client, "m12_user25@test.com")
    comp_id = await create_company_helper(async_client, token, "Co M12 25")
    acc_id = await create_account_helper(async_client, token, comp_id, email="support25@m12.com")

    # Initial email sent
    with patch.object(SMTPClient, "send_email_sync"):
        resp1 = await async_client.post(
            "/api/v1/emails/send",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email_account_id": acc_id,
                "to": ["client@example.com"],
                "subject": "Initial Discussion",
                "body_text": "Starting topic",
            },
        )
        msg1_id = resp1.json()["message_id"]
        thread_id = resp1.json()["thread_id"]

    # Create attachment
    draft_id = (await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={"email_account_id": acc_id},
    )).json()["id"]

    att_id = (await async_client.post(
        f"/api/v1/emails/drafts/{draft_id}/attachments",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("followup.pdf", io.BytesIO(b"%PDF followup"), "application/pdf")},
    )).json()["id"]

    captured_kwargs = {}

    def mock_send(*args, **kwargs):
        captured_kwargs.update(kwargs)

    with patch.object(SMTPClient, "send_email_sync", side_effect=mock_send):
        resp2 = await async_client.post(
            "/api/v1/emails/send",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email_account_id": acc_id,
                "to": ["client@example.com"],
                "subject": "Re: Initial Discussion",
                "body_text": "Replying with followup attachment",
                "in_reply_to": msg1_id,
                "thread_id": thread_id,
                "attachment_ids": [att_id],
            },
        )
        assert resp2.status_code == 201

        mime_msg = captured_kwargs["message"]
        assert mime_msg["In-Reply-To"] == msg1_id
        attachments = list(mime_msg.iter_attachments())
        assert len(attachments) == 1
        assert attachments[0].get_filename() == "followup.pdf"

