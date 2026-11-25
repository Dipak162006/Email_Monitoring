from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.campaigns.models import (
    Campaign,
    CampaignDelivery,
    CampaignRecipient,
    CampaignStatus,
    CampaignDeliveryStatus,
    CampaignRecipientStatus,
)
from app.modules.email_accounts.models import EmailAccount
from app.modules.emails.models import (
    Email,
    EmailDirection,
    EmailStatus,
    EmailTrackingEvent,
    EmailTrackingToken,
    TrackingEventType,
    TrackingTokenType,
)
from app.modules.emails.open_tracking_service import (
    BODY_CLOSE_PATTERN,
    EXISTING_PIXEL_PATTERN,
    OpenTrackingService,
)
from app.modules.emails.service import EmailService
from app.modules.emails.tracking_client import TrackingServiceClient
from app.modules.emails.tracking_routes import TRANSPARENT_PIXEL_GIF
from app.modules.emails.tracking_schemas import TrackingTokenIssueResponse
from app.modules.emails.tracking_service import EmailTrackingService


@pytest.mark.asyncio
async def test_open_token_issuance_and_idempotency(async_client: AsyncClient, db_session: AsyncSession):
    """Verify OPEN token creation, SHA-256 persistence, and deterministic idempotency."""
    test_secret = "test-open-tracking-internal-secret"

    with patch.object(settings, "TRACKING_INTERNAL_SECRET", test_secret):
        payload = {
            "company_id": 10,
            "email_id": 20,
            "token_type": "OPEN",
            "campaign_id": 30,
            "recipient_id": 40,
            "delivery_id": 50,
            "idempotency_key": "c30_d50_open",
            "expires_in_seconds": 86400,
        }

        # 1. Issue token
        res1 = await async_client.post(
            "/api/v1/internal/tracking/tokens",
            json=payload,
            headers={"X-Tracking-Internal-Secret": test_secret},
        )
        assert res1.status_code == 201
        data1 = res1.json()

        assert "token_id" in data1
        assert "raw_token" in data1
        assert data1["token_type"] == "OPEN"
        assert data1["destination_url"] is None
        assert f"/t/o/{data1['raw_token']}" in data1["tracking_url"]

        # Verify only SHA-256 hash is persisted in database
        stmt = select(EmailTrackingToken).where(EmailTrackingToken.id == data1["token_id"])
        token_row = (await db_session.execute(stmt)).scalar_one()
        assert token_row.token_hash == EmailTrackingService.hash_token(data1["raw_token"])
        assert token_row.token_type == "OPEN"
        assert token_row.destination_url is None
        assert token_row.idempotency_key == "c30_d50_open"

        # 2. Idempotent re-issuance returns identical raw_token and tracking_url
        res2 = await async_client.post(
            "/api/v1/internal/tracking/tokens",
            json=payload,
            headers={"X-Tracking-Internal-Secret": test_secret},
        )
        assert res2.status_code == 201
        data2 = res2.json()
        assert data2["token_id"] == data1["token_id"]
        assert data2["raw_token"] == data1["raw_token"]
        assert data2["tracking_url"] == data1["tracking_url"]


@pytest.mark.asyncio
async def test_open_pixel_valid_token_and_event_persistence(async_client: AsyncClient, db_session: AsyncSession):
    """Verify GET /t/o/{token} returns 1x1 GIF, no-cache headers, and logs an unclassified OPEN event."""
    token_record, raw_token = await EmailTrackingService.create_tracking_token(
        db=db_session,
        company_id=1,
        email_id=5,
        token_type=TrackingTokenType.OPEN,
        campaign_id=12,
        recipient_id=34,
        delivery_id=56,
    )
    await db_session.commit()

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "X-Forwarded-For": "198.51.100.25, 10.0.0.1",
    }

    resp = await async_client.get(f"/t/o/{raw_token}", headers=headers)
    assert resp.status_code == 200
    assert resp.headers["Content-Type"] == "image/gif"
    assert resp.headers["Cache-Control"] == "no-store, no-cache, must-revalidate, max-age=0"
    assert resp.headers["Pragma"] == "no-cache"
    assert resp.headers["Expires"] == "0"
    assert resp.content == TRANSPARENT_PIXEL_GIF
    assert len(resp.content) == 43
    assert resp.content[:6] == b"GIF89a"

    # Verify event record in database
    stmt = select(EmailTrackingEvent).where(EmailTrackingEvent.token_id == token_record.id)
    event_row = (await db_session.execute(stmt)).scalar_one()

    assert event_row.event_type == "OPEN"
    assert event_row.company_id == 1
    assert event_row.email_id == 5
    assert event_row.campaign_id == 12
    assert event_row.recipient_id == 34
    assert event_row.delivery_id == 56
    assert event_row.is_bot is False  # Standard interactive browser open classified as non-bot
    assert event_row.ip_address == "198.51.100.25"
    assert "Mozilla/5.0" in event_row.user_agent


@pytest.mark.asyncio
async def test_open_pixel_invalid_expired_revoked_token(async_client: AsyncClient, db_session: AsyncSession):
    """Verify that invalid, expired, or revoked tokens return 404 without image or event logging."""
    # 1. Non-existent token
    fake_token = "0" * 32
    res_nonexistent = await async_client.get(f"/t/o/{fake_token}")
    assert res_nonexistent.status_code == 404
    assert "invalid, expired, or has been disabled" in res_nonexistent.json()["detail"]

    # 2. Revoked token
    tok_revoked, raw_revoked = await EmailTrackingService.create_tracking_token(
        db=db_session,
        company_id=1,
        email_id=5,
        token_type=TrackingTokenType.OPEN,
    )
    await EmailTrackingService.revoke_token(db=db_session, token=tok_revoked)
    await db_session.commit()

    res_revoked = await async_client.get(f"/t/o/{raw_revoked}")
    assert res_revoked.status_code == 404

    # 3. Expired token
    tok_expired, raw_expired = await EmailTrackingService.create_tracking_token(
        db=db_session,
        company_id=1,
        email_id=5,
        token_type=TrackingTokenType.OPEN,
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    await db_session.commit()

    res_expired = await async_client.get(f"/t/o/{raw_expired}")
    assert res_expired.status_code == 404


@pytest.mark.asyncio
async def test_open_pixel_wrong_purpose(async_client: AsyncClient, db_session: AsyncSession):
    """Verify that tokens requested at the wrong tracking endpoint return 404."""
    # Create CLICK token
    click_tok, click_raw = await EmailTrackingService.create_tracking_token(
        db=db_session,
        company_id=1,
        email_id=5,
        token_type=TrackingTokenType.CLICK,
        destination_url="https://example.com/target",
    )
    # Create OPEN token
    open_tok, open_raw = await EmailTrackingService.create_tracking_token(
        db=db_session,
        company_id=1,
        email_id=5,
        token_type=TrackingTokenType.OPEN,
    )
    await db_session.commit()

    # Requesting CLICK token at /t/o/{token} must return 404
    res_click_at_open = await async_client.get(f"/t/o/{click_raw}")
    assert res_click_at_open.status_code == 404

    # Requesting OPEN token at /t/c/{token} must return 404
    res_open_at_click = await async_client.get(f"/t/c/{open_raw}")
    assert res_open_at_click.status_code == 404


@pytest.mark.asyncio
async def test_open_pixel_fails_closed_on_persistence_error(async_client: AsyncClient, db_session: AsyncSession):
    """Verify that failure to record/commit the event returns 500 without returning image."""
    _, raw_token = await EmailTrackingService.create_tracking_token(
        db=db_session,
        company_id=1,
        email_id=5,
        token_type=TrackingTokenType.OPEN,
    )
    await db_session.commit()

    with patch.object(EmailTrackingService, "record_tracking_event", side_effect=RuntimeError("Database lock")):
        res = await async_client.get(f"/t/o/{raw_token}")
        assert res.status_code == 500
        assert res.json()["detail"] == "Failed to record tracking event"


@pytest.mark.asyncio
async def test_open_tracking_service_injection_and_duplicate_prevention():
    """Verify OpenTrackingService HTML injection, closing body placement, and duplicate prevention."""
    mock_client = AsyncMock(spec=TrackingServiceClient)
    mock_client.is_configured = True
    mock_client.issue_token.return_value = TrackingTokenIssueResponse(
        token_id=99,
        raw_token="mock_open_token_123",
        token_type="OPEN",
        tracking_url="https://track.pulsemail.io/t/o/mock_open_token_123",
        destination_url=None,
        expires_at=None,
        created_at=datetime.now(timezone.utc),
    )

    # 1. HTML with </body>: pixel placed before </body>
    html_with_body = "<html><body><h1>Hello</h1><p>Welcome</p></body></html>"
    res1 = await OpenTrackingService.inject_campaign_open_pixel(
        html_content=html_with_body,
        company_id=1,
        campaign_id=10,
        recipient_id=20,
        delivery_id=30,
        tracking_client=mock_client,
    )
    assert '<img src="https://track.pulsemail.io/t/o/mock_open_token_123"' in res1
    assert 'data-pulsemail-open-pixel="true"' in res1
    assert res1.endswith("</body></html>")
    assert res1.index("data-pulsemail-open-pixel") < res1.index("</body>")

    # 2. HTML without </body>: pixel appended to end
    html_no_body = "<div><p>Simple content</p></div>"
    res2 = await OpenTrackingService.inject_campaign_open_pixel(
        html_content=html_no_body,
        company_id=1,
        campaign_id=10,
        recipient_id=20,
        delivery_id=30,
        tracking_client=mock_client,
    )
    assert res2.startswith("<div><p>Simple content</p></div><img src=")
    assert 'data-pulsemail-open-pixel="true"' in res2

    # 3. Duplicate prevention: HTML that already contains open pixel is NOT modified
    mock_client.reset_mock()
    res3 = await OpenTrackingService.inject_campaign_open_pixel(
        html_content=res1,  # Already has pixel
        company_id=1,
        campaign_id=10,
        recipient_id=20,
        delivery_id=30,
        tracking_client=mock_client,
    )
    assert res3 == res1
    mock_client.issue_token.assert_not_called()

    # 4. Safe handling of empty/None HTML
    assert await OpenTrackingService.inject_campaign_open_pixel(None, company_id=1, tracking_client=mock_client) is None
    assert await OpenTrackingService.inject_campaign_open_pixel("", company_id=1, tracking_client=mock_client) == ""


@pytest.mark.asyncio
async def test_open_tracking_service_fail_open_on_error():
    """Verify that OpenTrackingService returns original HTML untouched on any error or timeout."""
    # 1. Unconfigured client
    unconf_client = TrackingServiceClient(service_url="", internal_secret="")
    original_html = "<p>Original email content</p>"
    res_unconf = await OpenTrackingService.inject_campaign_open_pixel(
        html_content=original_html,
        company_id=1,
        tracking_client=unconf_client,
    )
    assert res_unconf == original_html

    # 2. Client exception
    err_client = AsyncMock(spec=TrackingServiceClient)
    err_client.is_configured = True
    err_client.issue_token.side_effect = RuntimeError("Render timeout")
    res_err = await OpenTrackingService.inject_campaign_open_pixel(
        html_content=original_html,
        company_id=1,
        tracking_client=err_client,
    )
    assert res_err == original_html


@pytest.mark.asyncio
async def test_campaign_delivery_service_open_tracking_integration():
    """Verify that OpenTrackingService is integrated into the campaign delivery flow alongside click tracking."""
    with patch.object(OpenTrackingService, "inject_campaign_open_pixel", new_callable=AsyncMock) as mock_open:
        mock_open.return_value = "<html><body>Tracked</body></html>"

        res = await OpenTrackingService.inject_campaign_open_pixel(
            html_content="<html><body>Test</body></html>",
            company_id=1,
            campaign_id=2,
            recipient_id=3,
            delivery_id=4,
        )
        assert mock_open.called
        assert res == "<html><body>Tracked</body></html>"


@pytest.mark.asyncio
async def test_untrusted_proxy_headers_cannot_spoof_ip(async_client: AsyncClient, db_session: AsyncSession):
    """Verify that forged X-Forwarded-For headers cannot control stored IP when proxy is untrusted."""
    # 1. Create OPEN token
    open_tok, open_raw = await EmailTrackingService.create_tracking_token(
        db=db_session,
        company_id=1,
        email_id=5,
        token_type=TrackingTokenType.OPEN,
    )
    # 2. Create CLICK token
    click_tok, click_raw = await EmailTrackingService.create_tracking_token(
        db=db_session,
        company_id=1,
        email_id=6,
        token_type=TrackingTokenType.CLICK,
        destination_url="https://example.com/dest",
    )
    await db_session.commit()

    # Explicitly set TRUSTED_PROXIES to empty string (untrusted proxy boundary)
    with patch.object(settings, "TRUSTED_PROXIES", ""):
        forged_headers = {
            "User-Agent": "AttackerBrowser/1.0",
            "X-Forwarded-For": "198.51.100.99, 10.0.0.1",
        }

        # Probe OPEN endpoint with forged header
        resp_open = await async_client.get(f"/t/o/{open_raw}", headers=forged_headers)
        assert resp_open.status_code == 200

        stmt_open = select(EmailTrackingEvent).where(EmailTrackingEvent.token_id == open_tok.id)
        open_evt = (await db_session.execute(stmt_open)).scalar_one()
        assert open_evt.ip_address is None  # Must store NULL, NOT forged IP

        # Probe CLICK endpoint with forged header
        resp_click = await async_client.get(f"/t/c/{click_raw}", headers=forged_headers, follow_redirects=False)
        assert resp_click.status_code == 302

        stmt_click = select(EmailTrackingEvent).where(EmailTrackingEvent.token_id == click_tok.id)
        click_evt = (await db_session.execute(stmt_click)).scalar_one()
        assert click_evt.ip_address is None  # Must store NULL, NOT forged IP


@pytest.mark.asyncio
async def test_cf_connecting_ip_security_boundary(async_client: AsyncClient, db_session: AsyncSession):
    """Verify CF-Connecting-IP is ignored when untrusted, and accepted only when proxy is trusted."""
    open_tok, open_raw = await EmailTrackingService.create_tracking_token(
        db=db_session,
        company_id=1,
        email_id=7,
        token_type=TrackingTokenType.OPEN,
    )
    click_tok, click_raw = await EmailTrackingService.create_tracking_token(
        db=db_session,
        company_id=1,
        email_id=8,
        token_type=TrackingTokenType.CLICK,
        destination_url="https://example.com/dest2",
    )
    await db_session.commit()

    cf_headers = {
        "User-Agent": "TestClient/1.0",
        "CF-Connecting-IP": "203.0.113.88",
    }

    # Case A: Untrusted proxy boundary -> CF header must be rejected and store NULL
    with patch.object(settings, "TRUSTED_PROXIES", ""):
        res1 = await async_client.get(f"/t/o/{open_raw}", headers=cf_headers)
        assert res1.status_code == 200
        stmt1 = select(EmailTrackingEvent).where(EmailTrackingEvent.token_id == open_tok.id)
        evt1 = (await db_session.execute(stmt1)).scalar_one()
        assert evt1.ip_address is None

    # Case B: Trusted proxy boundary (127.0.0.1 from test client) -> CF header is accepted
    with patch.object(settings, "TRUSTED_PROXIES", "127.0.0.1"):
        res2 = await async_client.get(f"/t/c/{click_raw}", headers=cf_headers, follow_redirects=False)
        assert res2.status_code == 302
        stmt2 = select(EmailTrackingEvent).where(EmailTrackingEvent.token_id == click_tok.id)
        evt2 = (await db_session.execute(stmt2)).scalar_one()
        assert evt2.ip_address == "203.0.113.88"


@pytest.mark.asyncio
async def test_missing_forwarding_headers_handled_safely(async_client: AsyncClient, db_session: AsyncSession):
    """Verify that requests without any forwarding headers succeed and store NULL IP."""
    open_tok, open_raw = await EmailTrackingService.create_tracking_token(
        db=db_session,
        company_id=1,
        email_id=9,
        token_type=TrackingTokenType.OPEN,
    )
    click_tok, click_raw = await EmailTrackingService.create_tracking_token(
        db=db_session,
        company_id=1,
        email_id=10,
        token_type=TrackingTokenType.CLICK,
        destination_url="https://example.com/dest3",
    )
    await db_session.commit()

    # Empty headers (no X-Forwarded-For or CF-Connecting-IP)
    empty_headers = {"User-Agent": "DirectBrowser/1.0"}

    res_open = await async_client.get(f"/t/o/{open_raw}", headers=empty_headers)
    assert res_open.status_code == 200

    stmt_open = select(EmailTrackingEvent).where(EmailTrackingEvent.token_id == open_tok.id)
    evt_open = (await db_session.execute(stmt_open)).scalar_one()
    assert evt_open.ip_address is None
    assert evt_open.user_agent == "DirectBrowser/1.0"
    assert evt_open.is_bot is None

    res_click = await async_client.get(f"/t/c/{click_raw}", headers=empty_headers, follow_redirects=False)
    assert res_click.status_code == 302

    stmt_click = select(EmailTrackingEvent).where(EmailTrackingEvent.token_id == click_tok.id)
    evt_click = (await db_session.execute(stmt_click)).scalar_one()
    assert evt_click.ip_address is None
    assert evt_click.user_agent == "DirectBrowser/1.0"
    assert evt_click.is_bot is None

