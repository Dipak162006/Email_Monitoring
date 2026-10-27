import io
from email.message import EmailMessage
from unittest.mock import patch
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage import attachment_storage_service
from app.modules.email_accounts.models import EmailAccount
from app.modules.emails.models import Email, EmailAttachment, EmailStatus, EmailDirection
from app.services.smtp.client import SMTPClient


# =============================================================================
# Helpers
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
) -> int:
    """Create an email account with SMTP settings and return its ID."""
    resp = await client.post(
        f"/api/v1/companies/{company_id}/email-accounts",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": name,
            "email_address": email,
            "provider": "CUSTOM",
            "smtp_host": "smtp.acme.com",
            "smtp_port": 587,
            "smtp_security": "STARTTLS",
            "smtp_username": email,
            "smtp_password": "SecretPassword123!",
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


# =============================================================================
# Mailbox Reply All & Forward Attachments Tests
# =============================================================================

@pytest.mark.asyncio
async def test_copy_attachments_same_account(async_client: AsyncClient, db_session: AsyncSession):
    """Copy attachments within the same account reuses storage path and prevents duplicates."""
    token = await register_and_login(async_client, "replyfwd_user01@test.com")
    comp_id = await create_company_helper(async_client, token, "Co ReplyFwd 01")
    acc_id = await create_account_helper(async_client, token, comp_id, email="acc01@replyfwd.com")

    # 1. Create source draft and upload an attachment
    src_draft = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={"email_account_id": acc_id, "subject": "Source Email with Attachment"},
    )
    src_id = src_draft.json()["id"]

    file_bytes = b"Sample document content for forward test"
    upload_resp = await async_client.post(
        f"/api/v1/emails/drafts/{src_id}/attachments",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("report.pdf", io.BytesIO(file_bytes), "application/pdf")},
    )
    assert upload_resp.status_code == 201
    orig_att = upload_resp.json()

    # 2. Create destination forward draft on the same account
    dst_draft = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={"email_account_id": acc_id, "subject": "Fwd: Source Email with Attachment"},
    )
    dst_id = dst_draft.json()["id"]

    # 3. Copy attachments from source to destination
    copy_resp = await async_client.post(
        f"/api/v1/emails/drafts/{dst_id}/attachments/copy-from/{src_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert copy_resp.status_code in (200, 201)
    copy_data = copy_resp.json()
    assert copy_data["total"] == 1
    cloned_att = copy_data["attachments"][0]
    assert cloned_att["id"] != orig_att["id"]
    assert cloned_att["file_name"] == "report.pdf"
    assert cloned_att["file_size"] == len(file_bytes)
    assert cloned_att["content_type"] == "application/pdf"
    assert cloned_att["email_id"] == dst_id

    # Verify same account reuses storage path in database
    src_record = (await db_session.execute(select(EmailAttachment).where(EmailAttachment.id == orig_att["id"]))).scalar_one()
    dst_record = (await db_session.execute(select(EmailAttachment).where(EmailAttachment.id == cloned_att["id"]))).scalar_one()
    assert src_record.storage_path == dst_record.storage_path

    # 4. Duplicate copy protection: calling copy again does not create duplicate attachments
    dup_resp = await async_client.post(
        f"/api/v1/emails/drafts/{dst_id}/attachments/copy-from/{src_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert dup_resp.status_code in (200, 201)
    assert dup_resp.json()["total"] == 1

    # Cleanup disk file
    attachment_storage_service.delete_file_sync(src_record.storage_path)


@pytest.mark.asyncio
async def test_copy_attachments_cross_account_same_company(async_client: AsyncClient, db_session: AsyncSession):
    """Copying attachments across different accounts within the same company creates a physical file copy."""
    token = await register_and_login(async_client, "replyfwd_user02@test.com")
    comp_id = await create_company_helper(async_client, token, "Co ReplyFwd 02")
    acc_a_id = await create_account_helper(async_client, token, comp_id, name="Account A", email="acca@replyfwd.com")
    acc_b_id = await create_account_helper(async_client, token, comp_id, name="Account B", email="accb@replyfwd.com")

    # Source draft on Account A
    src_draft = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={"email_account_id": acc_a_id, "subject": "Source Email from Account A"},
    )
    src_id = src_draft.json()["id"]

    file_bytes = b"Contract details for account migration"
    upload_resp = await async_client.post(
        f"/api/v1/emails/drafts/{src_id}/attachments",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("contract.pdf", io.BytesIO(file_bytes), "application/pdf")},
    )
    assert upload_resp.status_code == 201
    src_att = upload_resp.json()

    # Destination draft on Account B
    dst_draft = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={"email_account_id": acc_b_id, "subject": "Fwd: Contract to Account B"},
    )
    dst_id = dst_draft.json()["id"]

    # Copy attachments from Account A source to Account B draft
    copy_resp = await async_client.post(
        f"/api/v1/emails/drafts/{dst_id}/attachments/copy-from/{src_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert copy_resp.status_code in (200, 201)
    copied_att = copy_resp.json()["attachments"][0]

    # Verify storage isolation
    src_rec = (await db_session.execute(select(EmailAttachment).where(EmailAttachment.id == src_att["id"]))).scalar_one()
    dst_rec = (await db_session.execute(select(EmailAttachment).where(EmailAttachment.id == copied_att["id"]))).scalar_one()

    assert src_rec.email_account_id == acc_a_id
    assert dst_rec.email_account_id == acc_b_id
    assert src_rec.storage_path != dst_rec.storage_path
    assert f"account_{acc_a_id}" in src_rec.storage_path
    assert f"account_{acc_b_id}" in dst_rec.storage_path

    # Verify both physical files exist on disk
    src_path = attachment_storage_service.resolve_storage_path(src_rec.storage_path)
    dst_path = attachment_storage_service.resolve_storage_path(dst_rec.storage_path)
    assert src_path.exists()
    assert dst_path.exists()
    assert src_path.read_bytes() == file_bytes
    assert dst_path.read_bytes() == file_bytes

    # Cleanup disk files
    attachment_storage_service.delete_file_sync(src_rec.storage_path)
    attachment_storage_service.delete_file_sync(dst_rec.storage_path)


@pytest.mark.asyncio
async def test_reject_unauthorized_and_cross_company_copy(async_client: AsyncClient):
    """Reject cross-company attachment copy with 404 or 403."""
    # User 1 / Company 1
    token1 = await register_and_login(async_client, "replyfwd_user03_c1@test.com")
    comp1_id = await create_company_helper(async_client, token1, "Co ReplyFwd C1")
    acc1_id = await create_account_helper(async_client, token1, comp1_id, email="c1@replyfwd.com")

    # User 2 / Company 2
    token2 = await register_and_login(async_client, "replyfwd_user03_c2@test.com")
    comp2_id = await create_company_helper(async_client, token2, "Co ReplyFwd C2")
    acc2_id = await create_account_helper(async_client, token2, comp2_id, email="c2@replyfwd.com")

    # Email in Company 1
    c1_draft = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token1}"},
        json={"email_account_id": acc1_id, "subject": "Company 1 Secret"},
    )
    c1_email_id = c1_draft.json()["id"]

    await async_client.post(
        f"/api/v1/emails/drafts/{c1_email_id}/attachments",
        headers={"Authorization": f"Bearer {token1}"},
        files={"file": ("secret.txt", io.BytesIO(b"top secret"), "text/plain")},
    )

    # Draft in Company 2
    c2_draft = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token2}"},
        json={"email_account_id": acc2_id, "subject": "Company 2 Draft"},
    )
    c2_email_id = c2_draft.json()["id"]

    # User 2 attempts to copy from Company 1 email into Company 2 draft
    cross_copy_resp = await async_client.post(
        f"/api/v1/emails/drafts/{c2_email_id}/attachments/copy-from/{c1_email_id}",
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert cross_copy_resp.status_code in (403, 404)

    # User 1 attempts to copy into Company 2 draft
    cross_target_resp = await async_client.post(
        f"/api/v1/emails/drafts/{c2_email_id}/attachments/copy-from/{c1_email_id}",
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert cross_target_resp.status_code in (403, 404)


@pytest.mark.asyncio
async def test_delete_cloned_draft_attachment_preserves_original(async_client: AsyncClient, db_session: AsyncSession):
    """Deleting a cloned draft attachment does not delete or damage the original attachment or disk file."""
    token = await register_and_login(async_client, "replyfwd_user04@test.com")
    comp_id = await create_company_helper(async_client, token, "Co ReplyFwd 04")
    acc_id = await create_account_helper(async_client, token, comp_id, email="acc04@replyfwd.com")

    # Source draft with attachment
    src_draft = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={"email_account_id": acc_id, "subject": "Original Message"},
    )
    src_id = src_draft.json()["id"]

    file_bytes = b"Permanent attachment bytes to verify reference counting"
    upload_resp = await async_client.post(
        f"/api/v1/emails/drafts/{src_id}/attachments",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("shared.pdf", io.BytesIO(file_bytes), "application/pdf")},
    )
    orig_att_id = upload_resp.json()["id"]

    # Clone into destination draft
    dst_draft = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={"email_account_id": acc_id, "subject": "Cloned Draft"},
    )
    dst_id = dst_draft.json()["id"]

    copy_resp = await async_client.post(
        f"/api/v1/emails/drafts/{dst_id}/attachments/copy-from/{src_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    cloned_att_id = copy_resp.json()["attachments"][0]["id"]

    # Delete cloned attachment from destination draft
    del_resp = await async_client.delete(
        f"/api/v1/emails/drafts/{dst_id}/attachments/{cloned_att_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_resp.status_code == 204

    # Verify cloned attachment is gone from DB
    cloned_rec = (await db_session.execute(select(EmailAttachment).where(EmailAttachment.id == cloned_att_id))).scalar_one_or_none()
    assert cloned_rec is None

    # Verify original attachment still exists in DB
    orig_rec = (await db_session.execute(select(EmailAttachment).where(EmailAttachment.id == orig_att_id))).scalar_one_or_none()
    assert orig_rec is not None

    # Verify physical file still exists on disk
    disk_path = attachment_storage_service.resolve_storage_path(orig_rec.storage_path)
    assert disk_path.exists()
    assert disk_path.read_bytes() == file_bytes

    # Cleanup disk file
    attachment_storage_service.delete_file_sync(orig_rec.storage_path)


@pytest.mark.asyncio
async def test_send_forward_draft_with_attachments_mime_verification(async_client: AsyncClient):
    """Sending a forward draft with copied attachments produces valid multipart MIME attachments."""
    token = await register_and_login(async_client, "replyfwd_user05@test.com")
    comp_id = await create_company_helper(async_client, token, "Co ReplyFwd 05")
    acc_id = await create_account_helper(async_client, token, comp_id, email="acc05@replyfwd.com")

    # Source email with attachment
    src_draft = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={"email_account_id": acc_id, "subject": "Source Project Update"},
    )
    src_id = src_draft.json()["id"]

    pdf_bytes = b"%PDF-1.4 proposal document data"
    await async_client.post(
        f"/api/v1/emails/drafts/{src_id}/attachments",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("proposal.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )

    # Destination forward draft
    dst_draft = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "email_account_id": acc_id,
            "to": ["partner@external.com"],
            "subject": "Fwd: Source Project Update",
            "body_text": "Please see forwarded proposal.",
        },
    )
    dst_id = dst_draft.json()["id"]

    # Copy attachments to forward draft
    await async_client.post(
        f"/api/v1/emails/drafts/{dst_id}/attachments/copy-from/{src_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    captured_kwargs = {}

    def mock_send(*args, **kwargs):
        captured_kwargs.update(kwargs)

    with patch.object(SMTPClient, "send_email_sync", side_effect=mock_send):
        send_resp = await async_client.post(
            f"/api/v1/emails/drafts/{dst_id}/send",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert send_resp.status_code == 200
        assert send_resp.json()["status"] == "SENT"

        # Verify MIME content
        mime_msg = captured_kwargs["message"]
        assert mime_msg.is_multipart()
        attachments = list(mime_msg.iter_attachments())
        assert len(attachments) == 1
        att = attachments[0]
        assert att.get_filename() == "proposal.pdf"
        assert att.get_content_type() == "application/pdf"
        assert att.get_content() == pdf_bytes


@pytest.mark.asyncio
async def test_reply_threading_headers_in_reply_to_and_references(async_client: AsyncClient, db_session: AsyncSession):
    """Replies correctly set In-Reply-To and References threading headers upon sending."""
    token = await register_and_login(async_client, "replyfwd_user06@test.com")
    comp_id = await create_company_helper(async_client, token, "Co ReplyFwd 06")
    acc_id = await create_account_helper(async_client, token, comp_id, email="acc06@replyfwd.com")

    orig_msg_id = "<msg-original-789@external.com>"

    # 1. Insert parent incoming email in the account
    parent_email = Email(
        company_id=comp_id,
        email_account_id=acc_id,
        direction=EmailDirection.INCOMING,
        status=EmailStatus.RECEIVED,
        sender="sender@external.com",
        recipients=["acc06@replyfwd.com"],
        subject="Discussion",
        body_text="Initial proposal from client",
        message_id=orig_msg_id,
    )
    db_session.add(parent_email)
    await db_session.commit()
    await db_session.refresh(parent_email)

    # 2. Create reply draft specifying in_reply_to
    reply_draft = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "email_account_id": acc_id,
            "to": ["sender@external.com"],
            "subject": "Re: Discussion",
            "body_text": "Thank you for the update.",
            "in_reply_to": orig_msg_id,
        },
    )
    assert reply_draft.status_code == 201
    draft_id = reply_draft.json()["id"]

    captured_kwargs = {}

    def mock_send(*args, **kwargs):
        captured_kwargs.update(kwargs)

    with patch.object(SMTPClient, "send_email_sync", side_effect=mock_send):
        send_resp = await async_client.post(
            f"/api/v1/emails/drafts/{draft_id}/send",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert send_resp.status_code == 200

        mime_msg = captured_kwargs["message"]
        assert mime_msg["In-Reply-To"] == orig_msg_id
        assert orig_msg_id in mime_msg["References"]


@pytest.mark.asyncio
async def test_draft_account_change_safely_migrates_attachments(async_client: AsyncClient, db_session: AsyncSession):
    """Switching a draft's sending account migrates attachment physical files and DB metadata."""
    token = await register_and_login(async_client, "replyfwd_user07@test.com")
    comp_id = await create_company_helper(async_client, token, "Co ReplyFwd 07")
    acc_a_id = await create_account_helper(async_client, token, comp_id, name="Acc A", email="acca@test07.com")
    acc_b_id = await create_account_helper(async_client, token, comp_id, name="Acc B", email="accb@test07.com")

    # Create draft on Account A with an attachment
    draft_resp = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={"email_account_id": acc_a_id, "subject": "Draft with attachment to switch"},
    )
    draft_id = draft_resp.json()["id"]

    file_bytes = b"Data file to migrate on account switch"
    att_resp = await async_client.post(
        f"/api/v1/emails/drafts/{draft_id}/attachments",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("dataset.csv", io.BytesIO(file_bytes), "text/csv")},
    )
    att_id = att_resp.json()["id"]

    # Verify initial storage on Account A
    att_a = (await db_session.execute(select(EmailAttachment).where(EmailAttachment.id == att_id))).scalar_one()
    assert att_a.email_account_id == acc_a_id
    old_storage_path = str(att_a.storage_path)
    old_path = attachment_storage_service.resolve_storage_path(old_storage_path)
    assert old_path.exists()

    # Switch draft's sending account to Account B
    update_resp = await async_client.put(
        f"/api/v1/emails/drafts/{draft_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"email_account_id": acc_b_id},
    )
    assert update_resp.status_code == 200

    # Query DB to verify attachment was migrated to Account B
    db_session.expire_all()
    att_b = (await db_session.execute(select(EmailAttachment).where(EmailAttachment.id == att_id))).scalar_one()
    assert att_b.email_account_id == acc_b_id
    assert att_b.storage_path != old_storage_path
    assert f"account_{acc_b_id}" in att_b.storage_path

    new_path = attachment_storage_service.resolve_storage_path(att_b.storage_path)
    assert new_path.exists()
    assert new_path.read_bytes() == file_bytes

    # Cleanup disk file
    attachment_storage_service.delete_file_sync(att_b.storage_path)


@pytest.mark.asyncio
async def test_draft_update_failure_preserves_original_attachment_and_file(async_client: AsyncClient, db_session: AsyncSession):
    """When draft update fails, original attachment and storage file are preserved, and new copies are cleaned up."""
    token = await register_and_login(async_client, "replyfwd_user08@test.com")
    comp_id = await create_company_helper(async_client, token, "Co ReplyFwd 08")
    acc_a_id = await create_account_helper(async_client, token, comp_id, name="Acc A8", email="acca8@test08.com")
    acc_b_id = await create_account_helper(async_client, token, comp_id, name="Acc B8", email="accb8@test08.com")

    # Create draft on Account A with an attachment
    draft_resp = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={"email_account_id": acc_a_id, "subject": "Draft before failed update"},
    )
    draft_id = draft_resp.json()["id"]

    file_bytes = b"Crucial data file that must not be deleted on failure"
    att_resp = await async_client.post(
        f"/api/v1/emails/drafts/{draft_id}/attachments",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("important.pdf", io.BytesIO(file_bytes), "application/pdf")},
    )
    assert att_resp.status_code == 201
    att_id = att_resp.json()["id"]

    att_a = (await db_session.execute(select(EmailAttachment).where(EmailAttachment.id == att_id))).scalar_one()
    orig_storage_path = str(att_a.storage_path)
    orig_file = attachment_storage_service.resolve_storage_path(orig_storage_path)
    assert orig_file.exists()

    # Attempt to update draft to Account B while referencing a non-existent thread
    update_resp = await async_client.put(
        f"/api/v1/emails/drafts/{draft_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "email_account_id": acc_b_id,
            "thread_id": 999999,  # Non-existent thread forces validation failure
        },
    )
    assert update_resp.status_code in (400, 404, 422)

    # Verify DB transaction was rolled back: attachment still belongs to Account A
    db_session.expire_all()
    att_check = (await db_session.execute(select(EmailAttachment).where(EmailAttachment.id == att_id))).scalar_one()
    assert att_check.email_account_id == acc_a_id
    assert att_check.storage_path == orig_storage_path

    # Verify original physical file is intact
    assert orig_file.exists()
    assert orig_file.read_bytes() == file_bytes

    # Cleanup disk file
    attachment_storage_service.delete_file_sync(orig_storage_path)


@pytest.mark.asyncio
async def test_account_switch_removes_old_file_only_when_no_longer_referenced(async_client: AsyncClient, db_session: AsyncSession):
    """Account switch removes the old file only when no other records reference it."""
    token = await register_and_login(async_client, "replyfwd_user09@test.com")
    comp_id = await create_company_helper(async_client, token, "Co ReplyFwd 09")
    acc_a_id = await create_account_helper(async_client, token, comp_id, name="Acc A9", email="acca9@test09.com")
    acc_b_id = await create_account_helper(async_client, token, comp_id, name="Acc B9", email="accb9@test09.com")

    # 1. Create Draft 1 on Account A with an attachment
    draft1_resp = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={"email_account_id": acc_a_id, "subject": "Draft 1"},
    )
    draft1_id = draft1_resp.json()["id"]

    file_bytes = b"Shared attachment between two drafts"
    att1_resp = await async_client.post(
        f"/api/v1/emails/drafts/{draft1_id}/attachments",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("shared.pdf", io.BytesIO(file_bytes), "application/pdf")},
    )
    assert att1_resp.status_code == 201
    att1_id = att1_resp.json()["id"]

    # 2. Create Draft 2 on Account A and copy attachment from Draft 1 (same account reuses storage path)
    draft2_resp = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={"email_account_id": acc_a_id, "subject": "Draft 2"},
    )
    draft2_id = draft2_resp.json()["id"]

    copy_resp = await async_client.post(
        f"/api/v1/emails/drafts/{draft2_id}/attachments/copy-from/{draft1_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert copy_resp.status_code in (200, 201)
    att2_id = copy_resp.json()["attachments"][0]["id"]

    db_session.expire_all()
    record1 = (await db_session.execute(select(EmailAttachment).where(EmailAttachment.id == att1_id))).scalar_one()
    record2 = (await db_session.execute(select(EmailAttachment).where(EmailAttachment.id == att2_id))).scalar_one()
    assert record1.storage_path == record2.storage_path
    shared_path = record1.storage_path
    disk_file = attachment_storage_service.resolve_storage_path(shared_path)
    assert disk_file.exists()

    # 3. Switch Draft 2 to Account B.
    # Draft 1 still references shared_path, so shared_path MUST NOT be deleted!
    update2_resp = await async_client.put(
        f"/api/v1/emails/drafts/{draft2_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"email_account_id": acc_b_id},
    )
    assert update2_resp.status_code == 200

    # Old shared file must still exist because Draft 1 still references it
    assert disk_file.exists()

    # 4. Now switch Draft 1 to Account B.
    # Now ZERO records reference shared_path, so shared_path should be safely removed.
    update1_resp = await async_client.put(
        f"/api/v1/emails/drafts/{draft1_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"email_account_id": acc_b_id},
    )
    assert update1_resp.status_code == 200

    # Verify old file is now deleted
    assert not disk_file.exists()

    # Cleanup new files on Account B
    db_session.expire_all()
    new_record1 = (await db_session.execute(select(EmailAttachment).where(EmailAttachment.id == att1_id))).scalar_one()
    new_record2 = (await db_session.execute(select(EmailAttachment).where(EmailAttachment.id == att2_id))).scalar_one()
    attachment_storage_service.delete_file_sync(new_record1.storage_path)
    attachment_storage_service.delete_file_sync(new_record2.storage_path)


@pytest.mark.asyncio
async def test_copy_attachments_preserves_distinct_files_with_same_name_and_size(async_client: AsyncClient, db_session: AsyncSession):
    """Source email with distinct files of identical name and size copies both files and remains idempotent."""
    token = await register_and_login(async_client, "replyfwd_user10@test.com")
    comp_id = await create_company_helper(async_client, token, "Co ReplyFwd 10")
    acc_id = await create_account_helper(async_client, token, comp_id, email="acc10@replyfwd.com")

    # 1. Create source draft and upload TWO distinct files with identical filename and size
    src_draft = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={"email_account_id": acc_id, "subject": "Source with identical metadata files"},
    )
    src_id = src_draft.json()["id"]

    # File 1: 30 bytes of 'A'
    file_bytes_1 = b"A" * 30
    att1_resp = await async_client.post(
        f"/api/v1/emails/drafts/{src_id}/attachments",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("payload.bin", io.BytesIO(file_bytes_1), "application/octet-stream")},
    )
    assert att1_resp.status_code == 201
    src_att1_id = att1_resp.json()["id"]

    # File 2: 30 bytes of 'B' (same file_name and file_size)
    file_bytes_2 = b"B" * 30
    att2_resp = await async_client.post(
        f"/api/v1/emails/drafts/{src_id}/attachments",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("payload.bin", io.BytesIO(file_bytes_2), "application/octet-stream")},
    )
    assert att2_resp.status_code == 201
    src_att2_id = att2_resp.json()["id"]

    # 2. Create target draft
    target_draft = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={"email_account_id": acc_id, "subject": "Target Draft"},
    )
    target_id = target_draft.json()["id"]

    # 3. Copy attachments to target draft
    copy1 = await async_client.post(
        f"/api/v1/emails/drafts/{target_id}/attachments/copy-from/{src_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert copy1.status_code in (200, 201)
    copy1_data = copy1.json()
    assert copy1_data["total"] == 2
    copied_source_ids = {att["source_attachment_id"] for att in copy1_data["attachments"]}
    assert copied_source_ids == {src_att1_id, src_att2_id}

    # 4. Repeat copy request: must be idempotent and not create duplicate copies
    copy2 = await async_client.post(
        f"/api/v1/emails/drafts/{target_id}/attachments/copy-from/{src_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert copy2.status_code in (200, 201)
    copy2_data = copy2.json()
    assert copy2_data["total"] == 2
    assert len(copy2_data["attachments"]) == 2

    # Cleanup disk files
    rec1 = (await db_session.execute(select(EmailAttachment).where(EmailAttachment.id == src_att1_id))).scalar_one()
    rec2 = (await db_session.execute(select(EmailAttachment).where(EmailAttachment.id == src_att2_id))).scalar_one()
    attachment_storage_service.delete_file_sync(rec1.storage_path)
    attachment_storage_service.delete_file_sync(rec2.storage_path)


@pytest.mark.asyncio
async def test_delete_attachment_locked_serializes_with_copy_safely(async_client: AsyncClient, db_session: AsyncSession):
    """Deleting an attachment acquired with for_update preserves physical file if clone exists."""
    token = await register_and_login(async_client, "replyfwd_user11@test.com")
    comp_id = await create_company_helper(async_client, token, "Co ReplyFwd 11")
    acc_id = await create_account_helper(async_client, token, comp_id, email="acc11@replyfwd.com")

    # 1. Draft 1 with an attachment
    d1 = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={"email_account_id": acc_id, "subject": "Draft 1 Lock Test"},
    )
    d1_id = d1.json()["id"]

    file_bytes = b"Protected binary content with row-level locking"
    att1_resp = await async_client.post(
        f"/api/v1/emails/drafts/{d1_id}/attachments",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("locked.bin", io.BytesIO(file_bytes), "application/octet-stream")},
    )
    assert att1_resp.status_code == 201
    att1_id = att1_resp.json()["id"]

    # 2. Draft 2 copies attachment from Draft 1
    d2 = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {token}"},
        json={"email_account_id": acc_id, "subject": "Draft 2 Lock Test"},
    )
    d2_id = d2.json()["id"]

    copy_resp = await async_client.post(
        f"/api/v1/emails/drafts/{d2_id}/attachments/copy-from/{d1_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert copy_resp.status_code in (200, 201)
    att2_id = copy_resp.json()["attachments"][0]["id"]

    db_session.expire_all()
    rec1 = (await db_session.execute(select(EmailAttachment).where(EmailAttachment.id == att1_id))).scalar_one()
    storage_path = rec1.storage_path
    disk_file = attachment_storage_service.resolve_storage_path(storage_path)
    assert disk_file.exists()

    # 3. Delete Draft 1's attachment using row-locked delete_draft_attachment
    del1_resp = await async_client.delete(
        f"/api/v1/emails/drafts/{d1_id}/attachments/{att1_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del1_resp.status_code == 204

    # File must still exist because Draft 2 still references it
    assert disk_file.exists()
    assert disk_file.read_bytes() == file_bytes

    # 4. Delete Draft 2's attachment
    del2_resp = await async_client.delete(
        f"/api/v1/emails/drafts/{d2_id}/attachments/{att2_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del2_resp.status_code == 204

    # Now with 0 references, file must be cleanly deleted from disk
    assert not disk_file.exists()
