import base64
from email.message import EmailMessage
import io
from pathlib import Path
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage import AttachmentStorageService
from app.modules.email_accounts.models import EmailAccount
from app.modules.emails.attachment_service import AttachmentService
from app.modules.emails.mailbox_service import EmailMailboxService
from app.modules.emails.models import Email, EmailAttachment, EmailDirection, EmailStatus
from app.services.imap.parser import EmailParser, ParsedAttachment


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
) -> int:
    """Create a configured EmailAccount."""
    resp = await client.post(
        f"/api/v1/companies/{company_id}/email-accounts",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": name,
            "email_address": email,
            "provider": "CUSTOM",
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "smtp_security": "STARTTLS",
            "smtp_username": email,
            "smtp_password": "secret_smtp_password",
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


# =============================================================================
# Unit Tests: MIME Parser Body & Inline Attachment Detection
# =============================================================================

def test_parse_zoho_html_with_name_parameter():
    """Zoho often sends text/html with name='message.html' without Content-Disposition: attachment.
    Verify this is parsed as body_html and NOT classified as an attachment.
    """
    raw_email = (
        b"From: sender@zoho.com\r\n"
        b"To: recipient@example.com\r\n"
        b"Subject: Zoho HTML Test\r\n"
        b"MIME-Version: 1.0\r\n"
        b"Content-Type: multipart/alternative; boundary=\"BOUNDARY123\"\r\n"
        b"\r\n"
        b"--BOUNDARY123\r\n"
        b"Content-Type: text/plain; charset=\"UTF-8\"\r\n"
        b"\r\n"
        b"Plain text fallback body\r\n"
        b"--BOUNDARY123\r\n"
        b"Content-Type: text/html; charset=\"UTF-8\"; name=\"message.html\"\r\n"
        b"\r\n"
        b"<html><body><h1>Hello from Zoho</h1><p>Main content</p></body></html>\r\n"
        b"--BOUNDARY123--\r\n"
    )

    parsed = EmailParser.parse_raw_email(raw_email)
    assert parsed.body_text == "Plain text fallback body"
    assert parsed.body_html is not None
    assert "<h1>Hello from Zoho</h1>" in parsed.body_html
    # Crucial assertion: message.html must NOT be in attachments!
    assert len(parsed.attachments) == 0


def test_parse_text_only_email():
    """Verify text-only email extracts body_text and has body_html as None."""
    raw_email = (
        b"From: sender@example.com\r\n"
        b"To: recipient@example.com\r\n"
        b"Subject: Plain Text Only\r\n"
        b"Content-Type: text/plain; charset=\"UTF-8\"\r\n"
        b"\r\n"
        b"This is a pure plain-text message without HTML.\r\n"
    )

    parsed = EmailParser.parse_raw_email(raw_email)
    assert parsed.body_text is not None
    assert parsed.body_text.strip() == "This is a pure plain-text message without HTML."
    assert parsed.body_html is None
    assert len(parsed.attachments) == 0


def test_parse_html_only_email():
    """Verify HTML-only email extracts body_html and has body_text as None."""
    raw_email = (
        b"From: sender@example.com\r\n"
        b"To: recipient@example.com\r\n"
        b"Subject: HTML Only\r\n"
        b"Content-Type: text/html; charset=\"UTF-8\"\r\n"
        b"\r\n"
        b"<html><body><p>Only HTML</p></body></html>\r\n"
    )

    parsed = EmailParser.parse_raw_email(raw_email)
    assert parsed.body_html is not None
    assert parsed.body_html.strip() == "<html><body><p>Only HTML</p></body></html>"
    assert parsed.body_text is None
    assert len(parsed.attachments) == 0


def test_parse_multipart_related_with_inline_cid_and_regular_attachment():
    """Verify multipart/related with inline CID logo, tracking pixel, and regular attachment."""
    pixel_gif = b"GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
    logo_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + b"X" * 150
    pdf_bytes = b"%PDF-1.4 sample pdf content for contract"

    raw_email = (
        b"From: sender@example.com\r\n"
        b"To: recipient@example.com\r\n"
        b"Subject: Mixed Related and Attachment\r\n"
        b"MIME-Version: 1.0\r\n"
        b"Content-Type: multipart/mixed; boundary=\"MIXED_BOUND\"\r\n"
        b"\r\n"
        b"--MIXED_BOUND\r\n"
        b"Content-Type: multipart/related; boundary=\"RELATED_BOUND\"\r\n"
        b"\r\n"
        b"--RELATED_BOUND\r\n"
        b"Content-Type: text/html; charset=\"UTF-8\"\r\n"
        b"\r\n"
        b"<div><p>Company Newsletter</p><img src=\"cid:logo_12345\"><img src=\"cid:track_pixel\"></div>\r\n"
        b"--RELATED_BOUND\r\n"
        b"Content-Type: image/png; name=\"logo.png\"\r\n"
        b"Content-ID: <logo_12345>\r\n"
        b"Content-Disposition: inline; filename=\"logo.png\"\r\n"
        b"Content-Transfer-Encoding: base64\r\n"
        b"\r\n"
        + base64.b64encode(logo_png) + b"\r\n"
        b"--RELATED_BOUND\r\n"
        b"Content-Type: image/gif; name=\"spacer.gif\"\r\n"
        b"Content-ID: <track_pixel>\r\n"
        b"Content-Transfer-Encoding: base64\r\n"
        b"\r\n"
        + base64.b64encode(pixel_gif) + b"\r\n"
        b"--RELATED_BOUND--\r\n"
        b"--MIXED_BOUND\r\n"
        b"Content-Type: application/pdf; name=\"contract.pdf\"\r\n"
        b"Content-Disposition: attachment; filename=\"contract.pdf\"\r\n"
        b"Content-Transfer-Encoding: base64\r\n"
        b"\r\n"
        + base64.b64encode(pdf_bytes) + b"\r\n"
        b"--MIXED_BOUND--\r\n"
    )

    parsed = EmailParser.parse_raw_email(raw_email)
    assert parsed.body_html is not None
    assert "cid:logo_12345" in parsed.body_html

    # Total attachments in parsed message
    assert len(parsed.attachments) == 3

    # Check inline classification
    logo_att = next(a for a in parsed.attachments if a.filename == "logo.png")
    assert logo_att.is_inline is True
    assert logo_att.content_id == "logo_12345"

    spacer_att = next(a for a in parsed.attachments if a.filename == "spacer.gif")
    assert spacer_att.is_inline is True

    pdf_att = next(a for a in parsed.attachments if a.filename == "contract.pdf")
    assert pdf_att.is_inline is False
    assert pdf_att.content_id is None


# =============================================================================
# Integration Tests: DB Persistence, Filtering & CID Resolution
# =============================================================================

@pytest.mark.anyio
async def test_attachment_service_inline_separation_and_cid_resolution(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Test full workflow:
    1. Create an incoming email with inline CID image and regular PDF attachment.
    2. Verify list_email_attachments(include_inline=False) hides the inline image.
    3. Verify resolve_cids_in_html embeds base64 data URIs.
    4. Verify raw DB body_html retains original cid: reference.
    5. Verify mailbox attachment_count only counts downloadable attachment.
    """
    token = await register_and_login(async_client, "zoho_tester@example.com")
    company_id = await create_company_helper(async_client, token, "Zoho Workspace")
    account_id = await create_account_helper(async_client, token, company_id, "Zoho Mail", "zoho_user@example.com")

    # 1. Insert Email record with CID in body_html
    raw_html = (
        "<html><body>"
        "<h2>Welcome to Our Company</h2>"
        "<p><img src=\"cid:header_logo_001\" alt=\"Logo\"></p>"
        "<p>Please review the attached contract.</p>"
        "</body></html>"
    )
    email_record = Email(
        company_id=company_id,
        email_account_id=account_id,
        message_id="<zoho-msg-999@zoho.com>",
        direction=EmailDirection.INCOMING.value,
        status=EmailStatus.RECEIVED.value,
        sender="billing@zoho.com",
        recipients=["zoho_user@example.com"],
        subject="Invoice & Welcome",
        body_text="Welcome to Our Company. Please review the attached contract.",
        body_html=raw_html,
        is_read=False,
        is_starred=False,
    )
    db_session.add(email_record)
    await db_session.flush()
    email_id = email_record.id

    # 2. Add inline logo attachment
    logo_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + b"\x00" * 80
    inline_att = await AttachmentService.create_incoming_attachment(
        db=db_session,
        company_id=company_id,
        email_account_id=account_id,
        email_id=email_id,
        file_name="logo.png",
        content_type="image/png",
        content_bytes=logo_bytes,
        disposition="inline",
        content_id="header_logo_001",
    )
    assert inline_att is not None
    assert inline_att.disposition == "inline"
    assert inline_att.content_id == "header_logo_001"

    # 3. Add regular downloadable PDF attachment
    pdf_bytes = b"%PDF-1.4 dummy invoice content"
    pdf_att = await AttachmentService.create_incoming_attachment(
        db=db_session,
        company_id=company_id,
        email_account_id=account_id,
        email_id=email_id,
        file_name="invoice.pdf",
        content_type="application/pdf",
        content_bytes=pdf_bytes,
        disposition="attachment",
        content_id=None,
    )
    assert pdf_att is not None
    assert pdf_att.disposition == "attachment"

    await db_session.commit()

    # 4. Query email details via API endpoint GET /emails/{id}
    resp = await async_client.get(
        f"/api/v1/emails/{email_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()

    # Verify attachment_count only counts non-inline attachments (1, not 2)
    assert data["attachment_count"] == 1

    # Verify CID in body_html was resolved to a base64 data URI for browser rendering
    resolved_html = data["body_html"]
    assert "cid:header_logo_001" not in resolved_html
    assert "data:image/png;base64," in resolved_html

    # 5. Query raw DB record: verify original cid: reference is preserved in DB
    db_email = await db_session.get(Email, email_id)
    assert db_email is not None
    assert "cid:header_logo_001" in db_email.body_html
    assert "data:image/png;base64," not in db_email.body_html

    # 6. Query attachments list via API endpoint GET /emails/{id}/attachments
    att_resp = await async_client.get(
        f"/api/v1/emails/{email_id}/attachments",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert att_resp.status_code == 200
    att_data = att_resp.json()
    # By default, inline attachments are excluded from downloadable attachments list!
    assert att_data["total"] == 1
    assert len(att_data["attachments"]) == 1
    assert att_data["attachments"][0]["file_name"] == "invoice.pdf"

    # 7. Query with include_inline=True: should return both
    att_all_resp = await async_client.get(
        f"/api/v1/emails/{email_id}/attachments?include_inline=true",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert att_all_resp.status_code == 200
    att_all_data = att_all_resp.json()
    assert att_all_data["total"] == 2
    filenames = [a["file_name"] for a in att_all_data["attachments"]]
    assert "logo.png" in filenames
    assert "invoice.pdf" in filenames


@pytest.mark.anyio
async def test_attachment_service_idempotency_on_repeated_sync(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Test that repeated sync calls for the same email do not create duplicate attachments."""
    token = await register_and_login(async_client, "idemp_user@example.com")
    company_id = await create_company_helper(async_client, token, "Idemp Corp")
    account_id = await create_account_helper(async_client, token, company_id, "Desk", "desk@idemp.com")

    email_record = Email(
        company_id=company_id,
        email_account_id=account_id,
        message_id="<idemp-123@idemp.com>",
        direction=EmailDirection.INCOMING.value,
        status=EmailStatus.RECEIVED.value,
        sender="sender@example.com",
        recipients=["desk@idemp.com"],
        subject="Idempotency Test",
        body_text="Test",
        is_read=False,
    )
    db_session.add(email_record)
    await db_session.flush()
    email_id = email_record.id

    logo_bytes = b"sample_logo_bytes_123"

    # First sync call
    att1 = await AttachmentService.create_incoming_attachment(
        db=db_session,
        company_id=company_id,
        email_account_id=account_id,
        email_id=email_id,
        file_name="brand_logo.png",
        content_type="image/png",
        content_bytes=logo_bytes,
        disposition="inline",
        content_id="brand_logo_cid",
    )
    await db_session.commit()

    # Second sync call with exact same attachment
    att2 = await AttachmentService.create_incoming_attachment(
        db=db_session,
        company_id=company_id,
        email_account_id=account_id,
        email_id=email_id,
        file_name="brand_logo.png",
        content_type="image/png",
        content_bytes=logo_bytes,
        disposition="inline",
        content_id="brand_logo_cid",
    )
    assert att1.id == att2.id

    # Verify only 1 record exists in DB
    stmt = select(EmailAttachment).where(EmailAttachment.email_id == email_id)
    res = await db_session.execute(stmt)
    all_atts = list(res.scalars().all())
    assert len(all_atts) == 1
