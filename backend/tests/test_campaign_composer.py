import io
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.storage import AttachmentStorageService
from app.modules.campaigns.models import Campaign, CampaignAttachment, CampaignStatus
from app.modules.campaigns.schemas import CampaignStatus
from app.modules.emails.models import Email, EmailAttachment, EmailStatus
from unittest.mock import patch
from app.services.transport.models import EmailTransportResult
from app.workers import tasks
from tests.conftest import TestAsyncSessionLocal
from tests.test_campaign_delivery import (
    register_and_login,
    create_company_helper,
    create_email_account_helper,
    setup_delivery_campaign,
    add_recipient_helper,
    queue_campaign_helper,
)
from app.modules.campaigns.delivery_service import CampaignDeliveryService


@pytest.fixture(autouse=True)
def configure_worker_db():
    """Ensure delivery engine worker tasks use the test database."""
    orig_session_maker = tasks.WorkerAsyncSessionLocal
    tasks.WorkerAsyncSessionLocal = TestAsyncSessionLocal
    yield
    tasks.WorkerAsyncSessionLocal = orig_session_maker


@pytest.mark.asyncio
async def test_campaign_attachment_upload_list_delete(async_client: AsyncClient, db_session: AsyncSession):
    """Test uploading, listing, downloading, and deleting attachments on a DRAFT campaign."""
    owner_token = await register_and_login(async_client, "owner_comp1@test.com", "Owner Comp1")
    company_id = await create_company_helper(async_client, owner_token, "Comp Org 1")
    account_id = await create_email_account_helper(async_client, owner_token, company_id, "outreach1@company.com")

    # 1. Create a draft campaign
    camp_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "name": "Q4 Outreach",
            "email_account_id": account_id,
            "subject": "Exclusive offer for {{first_name}}",
            "body_html": "<p>Hello {{first_name}}</p>",
            "body_text": "Hello {{first_name}}",
        },
    )
    assert camp_resp.status_code == 201
    campaign_id = camp_resp.json()["id"]

    # 2. Upload an attachment
    file_content = b"PDF marketing flyer payload"
    files = {"file": ("flyer.pdf", io.BytesIO(file_content), "application/pdf")}
    upload_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/attachments",
        headers={"Authorization": f"Bearer {owner_token}"},
        files=files,
    )
    assert upload_resp.status_code == 201
    att_data = upload_resp.json()
    assert att_data["file_name"] == "flyer.pdf"
    assert att_data["file_size"] == len(file_content)
    assert att_data["content_type"] == "application/pdf"
    attachment_id = att_data["id"]

    # 3. List attachments
    list_resp = await async_client.get(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/attachments",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert list_data["total"] == 1
    assert list_data["attachments"][0]["id"] == attachment_id

    # 4. Campaign detail includes attachments
    detail_resp = await async_client.get(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert detail_resp.status_code == 200
    assert len(detail_resp.json()["attachments"]) == 1

    # 5. Download attachment
    download_resp = await async_client.get(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/attachments/{attachment_id}/download",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert download_resp.status_code == 200
    assert download_resp.content == file_content

    # 6. Delete attachment
    del_resp = await async_client.delete(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/attachments/{attachment_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert del_resp.status_code == 204

    # 7. Verify listing is now empty
    list_resp2 = await async_client.get(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/attachments",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert list_resp2.status_code == 200
    assert list_resp2.json()["total"] == 0


@pytest.mark.asyncio
async def test_campaign_attachment_validation_and_tenant_isolation(async_client: AsyncClient, db_session: AsyncSession):
    """Test validation rules (disallowed extension, non-draft status) and cross-company tenant isolation."""
    owner_token = await register_and_login(async_client, "owner_comp2@test.com", "Owner Comp2")
    company_id = await create_company_helper(async_client, owner_token, "Comp Org 2")
    account_id = await create_email_account_helper(async_client, owner_token, company_id, "outreach2@company.com")

    # Second organization
    other_token = await register_and_login(async_client, "other_comp2@test.com", "Other Comp2")
    other_company_id = await create_company_helper(async_client, other_token, "Other Org 2")

    camp_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "name": "Validation Campaign",
            "email_account_id": account_id,
            "subject": "Subject",
        },
    )
    campaign_id = camp_resp.json()["id"]

    # 1. Reject disallowed extension (e.g. .exe)
    exe_file = {"file": ("malware.exe", io.BytesIO(b"binary"), "application/octet-stream")}
    bad_upload = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/attachments",
        headers={"Authorization": f"Bearer {owner_token}"},
        files=exe_file,
    )
    assert bad_upload.status_code == 400
    assert "not allowed" in bad_upload.json()["detail"].lower()

    # 2. Reject cross-company access (other company user cannot upload or list)
    valid_file = {"file": ("doc.txt", io.BytesIO(b"text content"), "text/plain")}
    cross_upload = await async_client.post(
        f"/api/v1/companies/{other_company_id}/campaigns/{campaign_id}/attachments",
        headers={"Authorization": f"Bearer {other_token}"},
        files=valid_file,
    )
    assert cross_upload.status_code == 404

    # 3. Reject upload when campaign is not in DRAFT status
    # Manually update campaign status to RUNNING in database
    db_camp = await db_session.get(Campaign, campaign_id)
    db_camp.status = CampaignStatus.RUNNING.value
    await db_session.commit()

    upload_non_draft = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/attachments",
        headers={"Authorization": f"Bearer {owner_token}"},
        files={"file": ("doc.txt", io.BytesIO(b"text content"), "text/plain")},
    )
    assert upload_non_draft.status_code == 400
    assert "only draft" in upload_non_draft.json()["detail"].lower()


@pytest.mark.asyncio
async def test_import_existing_draft_into_campaign(async_client: AsyncClient, db_session: AsyncSession):
    """Test importing an existing draft email into a campaign with content and attachments."""
    owner_token = await register_and_login(async_client, "owner_comp3@test.com", "Owner Comp3")
    company_id = await create_company_helper(async_client, owner_token, "Comp Org 3")
    account_id = await create_email_account_helper(async_client, owner_token, company_id, "outreach3@company.com")

    # 1. Create a draft email in drafts folder
    draft_create_resp = await async_client.post(
        "/api/v1/emails/drafts",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "email_account_id": account_id,
            "to": ["draft_target@test.com"],
            "subject": "Draft Subject with {{first_name}}",
            "body_html": "<p>Hello {{first_name}},</p><p>Check this update</p><script>alert('xss')</script>",
            "body_text": "Hello {{first_name}}, Check this update",
        },
    )
    assert draft_create_resp.status_code == 201
    draft_id = draft_create_resp.json()["id"]

    # 2. Upload an attachment to the draft
    att_bytes = b"Sample draft attachment"
    draft_att_resp = await async_client.post(
        f"/api/v1/emails/drafts/{draft_id}/attachments",
        headers={"Authorization": f"Bearer {owner_token}"},
        files={"file": ("pricing.pdf", io.BytesIO(att_bytes), "application/pdf")},
    )
    assert draft_att_resp.status_code == 201

    # 3. Create a draft campaign
    camp_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "name": "Campaign to Import Into",
            "email_account_id": account_id,
            "subject": "Initial Subject",
            "body_html": "<p>Initial body</p>",
        },
    )
    campaign_id = camp_resp.json()["id"]

    # 4. Import the draft into the campaign
    import_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{campaign_id}/import-draft",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"draft_id": draft_id},
    )
    assert import_resp.status_code == 200
    camp_data = import_resp.json()
    assert camp_data["subject"] == "Draft Subject with {{first_name}}"
    assert "alert('xss')" not in camp_data["body_html"]  # Sanitized!
    assert "Hello {{first_name}}" in camp_data["body_html"]
    assert len(camp_data["attachments"]) == 1
    assert camp_data["attachments"][0]["file_name"] == "pricing.pdf"

    # 5. Verify the original draft is not modified or deleted
    draft_check = await async_client.get(
        f"/api/v1/emails/drafts/{draft_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert draft_check.status_code == 200
    assert draft_check.json()["status"] == "DRAFT"


@pytest.mark.asyncio
async def test_campaign_delivery_with_attachments(async_client: AsyncClient, db_session: AsyncSession):
    """Verify that campaign delivery includes campaign attachments in outgoing messages,
    persists per-recipient EmailAttachment records, and does not send to suppressed recipients.
    """
    owner_token = await register_and_login(async_client, "owner_comp4@test.com", "Owner Comp4")
    company_id = await create_company_helper(async_client, owner_token, "Comp Org 4")
    camp_id, account_id = await setup_delivery_campaign(async_client, db_session, owner_token, company_id)

    # 1. Attach a file to the campaign
    att_bytes = b"Campaign report document"
    files = {"file": ("report.pdf", io.BytesIO(att_bytes), "application/pdf")}
    att_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/campaigns/{camp_id}/attachments",
        headers={"Authorization": f"Bearer {owner_token}"},
        files=files,
    )
    assert att_resp.status_code == 201

    # 2. Add recipients (one normal, one to be suppressed)
    r1 = await add_recipient_helper(async_client, owner_token, company_id, camp_id, "eligible@delivery-test.com", first_name="Alice")
    r2 = await add_recipient_helper(async_client, owner_token, company_id, camp_id, "suppressed@delivery-test.com", first_name="Bob")

    # 3. Suppress Bob
    await async_client.post(
        f"/api/v1/companies/{company_id}/suppressions",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"email": "suppressed@delivery-test.com", "reason": "UNSUBSCRIBE"},
    )

    # 4. Queue campaign directly in DB
    await queue_campaign_helper(db_session, camp_id)

    # 5. Execute campaign delivery with mock transport
    with patch("app.services.smtp.client.SMTPClient.send_email_sync") as mock_smtp:
        exec_result = await CampaignDeliveryService.execute_campaign(
            campaign_id=camp_id,
            company_id=company_id,
        )

        assert exec_result["sent_count"] == 1
        assert exec_result["skipped_count"] == 1  # suppressed recipient skipped

        # 6. Verify outgoing message sent to SMTP has the attachment
        assert mock_smtp.call_count == 1
        sent_msg = mock_smtp.call_args.kwargs.get("message") or mock_smtp.call_args[0][7]
        attachments_in_msg = list(sent_msg.iter_attachments())
        assert len(attachments_in_msg) == 1
        assert attachments_in_msg[0].get_filename() == "report.pdf"

    # 7. Verify per-recipient EmailAttachment record was created in DB
    sent_att_res = await db_session.execute(
        select(EmailAttachment).where(
            EmailAttachment.company_id == company_id,
            EmailAttachment.file_name == "report.pdf",
        )
    )
    sent_att = sent_att_res.scalar_one_or_none()
    assert sent_att is not None
    assert sent_att.file_name == "report.pdf"
