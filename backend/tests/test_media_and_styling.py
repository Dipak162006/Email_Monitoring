import pytest
from httpx import AsyncClient
from app.core.css_inliner import inline_css
from app.core.sanitizer import sanitize_html
from app.core.storage import AttachmentStorageService
from app.modules.emails.service import process_inline_media_images


def test_css_inliner_and_sanitizer_preserves_styles_and_table_attrs():
    """Verify that <style> blocks get inlined onto HTML elements before being sanitized,

    and email layout attributes (role, bgcolor, border, cellpadding, cellspacing) are preserved.
    """
    pasted_template = """
    <html>
      <head>
        <style>
          .banner { background-color: #6366f1; color: #ffffff; padding: 20px; }
          .headline { font-size: 24px; font-weight: bold; }
          .cta-btn { background-color: #10b981; color: #ffffff; text-decoration: none; padding: 12px 24px; }
        </style>
      </head>
      <body>
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#f8fafc">
          <tr>
            <td align="center" valign="top">
              <div class="banner">
                <h1 class="headline" style="margin: 0;">Welcome!</h1>
                <a href="https://example.com" class="cta-btn">Get Started</a>
                <img src="cid:logo@pulsemail" alt="Logo" width="200" height="50" border="0" data-media-id="123" />
              </div>
            </td>
          </tr>
        </table>
      </body>
    </html>
    """

    sanitized = sanitize_html(pasted_template)

    # 1. Class declarations should have been inlined onto matching elements
    assert "background-color: #6366f1" in sanitized or "background-color:#6366f1" in sanitized
    assert "color: #ffffff" in sanitized or "color:#ffffff" in sanitized
    assert "font-size: 24px" in sanitized or "font-size:24px" in sanitized
    assert "background-color: #10b981" in sanitized or "background-color:#10b981" in sanitized

    # 2. Existing inline styles preserved
    assert "margin: 0" in sanitized or "margin:0" in sanitized

    # 3. Table presentation and email attributes preserved
    assert 'role="presentation"' in sanitized
    assert 'cellpadding="0"' in sanitized
    assert 'cellspacing="0"' in sanitized
    assert 'bgcolor="#f8fafc"' in sanitized
    assert 'align="center"' in sanitized
    assert 'valign="top"' in sanitized

    # 4. CID URL scheme and img attributes preserved
    assert 'src="cid:logo@pulsemail"' in sanitized
    assert 'width="200"' in sanitized
    assert 'height="50"' in sanitized
    assert 'data-media-id="123"' in sanitized


def test_process_inline_media_images(tmp_path, monkeypatch):
    """Verify that local media URLs in HTML are detected, replaced with CID references,
    and image bytes are collected for inline MIME embedding.
    """
    company_id = 42
    filename = "0123456789abcdef0123456789abcdef.png"
    
    # Mock media storage directory
    media_dir = tmp_path / f"media/company_{company_id}"
    media_dir.mkdir(parents=True, exist_ok=True)
    image_file = media_dir / filename
    fake_png_data = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRfakeimagebytes"
    image_file.write_bytes(fake_png_data)

    monkeypatch.setattr(
        AttachmentStorageService,
        "resolve_media_path",
        classmethod(lambda cls, cid, fn: image_file if cid == company_id and fn == filename else None),
    )

    html_content = f"""
    <div>
      <p>Hello world</p>
      <img src="/api/v1/media/{company_id}/{filename}" alt="Uploaded Banner" />
      <img src="https://external.com/pic.jpg" alt="External" />
    </div>
    """

    processed_html, inline_images = process_inline_media_images(html_content, company_id)

    # Local URL should be replaced with CID
    expected_cid = f"media_{filename}@pulsemail"
    assert f'src="cid:{expected_cid}"' in processed_html
    assert f"/api/v1/media/{company_id}/{filename}" not in processed_html

    # External URL unchanged
    assert 'src="https://external.com/pic.jpg"' in processed_html

    # Inline image payload prepared
    assert len(inline_images) == 1
    assert inline_images[0]["cid"] == expected_cid
    assert inline_images[0]["bytes"] == fake_png_data
    assert inline_images[0]["subtype"] == "png"


@pytest.mark.asyncio
async def test_media_upload_and_serving_endpoints(async_client: AsyncClient):
    """Test POST /api/v1/companies/{company_id}/media and GET /api/v1/media/{company_id}/{filename}."""
    client = async_client
    # Register & Login
    reg_resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "media_owner@test.com", "password": "Password123!", "full_name": "Media Tester"},
    )
    assert reg_resp.status_code == 201

    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "media_owner@test.com", "password": "Password123!"},
    )
    token = login_resp.json()["access_token"]
    auth_header = {"Authorization": f"Bearer {token}"}

    # Create company
    comp_resp = await client.post("/api/v1/companies/", headers=auth_header, json={"name": "Media Corp"})
    assert comp_resp.status_code == 201
    company_id = comp_resp.json()["id"]

    # 1. Upload valid PNG image
    tiny_png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
        b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    upload_resp = await client.post(
        f"/api/v1/companies/{company_id}/media",
        headers=auth_header,
        files={"file": ("logo.png", tiny_png, "image/png")},
    )
    assert upload_resp.status_code == 201, upload_resp.text
    media_data = upload_resp.json()
    assert "url" in media_data
    assert "media_id" in media_data
    media_url = media_data["url"]
    filename = media_data["media_id"].split("/")[-1]

    # 2. Publicly access the image via GET /api/v1/media/{company_id}/{filename} (no auth header needed)
    get_resp = await client.get(media_url)
    assert get_resp.status_code == 200
    assert get_resp.headers["content-type"] == "image/png"
    assert "public" in get_resp.headers["cache-control"]
    assert get_resp.content == tiny_png

    # 3. Path traversal attack blocked
    traversal_resp = await client.get(f"/api/v1/media/{company_id}/../../etc/passwd")
    assert traversal_resp.status_code in (400, 404)

    # 4. Invalid filename format blocked
    invalid_resp = await client.get(f"/api/v1/media/{company_id}/invalid-filename.png")
    assert invalid_resp.status_code in (400, 404)

    # 5. Invalid file type rejected on upload
    bad_upload = await client.post(
        f"/api/v1/companies/{company_id}/media",
        headers=auth_header,
        files={"file": ("malicious.exe", b"executable bytes", "application/x-msdownload")},
    )
    assert bad_upload.status_code == 400
