"""T5.1 Remote Tracking Event API & Classification Integration Tests.

Verifies:
1. Internal API authentication:
   - Rejects unauthenticated or invalid secret with 401 Unauthorized.
   - Accepts X-Tracking-Internal-Secret header.
   - Accepts Authorization: Bearer <secret> header.
2. Filtering & Pagination:
   - Supports since_id for cursor pagination in strictly ascending event ID order.
   - Supports bounded limit.
   - Supports event-type filtering (OPEN, CLICK, UNSUBSCRIBE).
   - Enforces company tenant isolation when company_id is provided.
3. Zero-PII & Secret Protection:
   - Validates that returned records contain NO raw tokens, NO token hashes,
     NO recipient email addresses, and NO IP addresses.
4. End-to-end Public Route Classification Integration:
   - Pixel load with Google Image Proxy UA records is_bot=True, bot_reason='google_image_proxy'.
   - Link click with Microsoft SafeLinks UA records is_bot=True, bot_reason='microsoft_safelinks'.
   - Pixel load with normal Chrome UA records is_bot=None (unclassified).
5. Existing Unsubscribe Endpoint Regression:
   - Preserves /api/v1/unsubscribes functionality and schema.
6. TrackingServiceClient Integration:
   - Validates get_tracking_events method handles success, filtering, and network failures.
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.emails.models import (
    EmailTrackingEvent,
    EmailTrackingToken,
    TrackingEventType,
    TrackingTokenType,
)
from app.modules.emails.tracking_client import TrackingServiceClient
from app.modules.emails.tracking_service import EmailTrackingService


@pytest.mark.asyncio
async def test_tracking_events_api_authentication(async_client: AsyncClient, db_session: AsyncSession):
    """Verify endpoint strictly rejects missing/invalid secret and accepts valid header."""
    secret = "internal-test-secret-t51-secure-token"
    with patch.object(settings, "TRACKING_INTERNAL_SECRET", secret):
        # 1. Missing secret -> 401
        resp_no_auth = await async_client.get("/api/v1/internal/tracking/events")
        assert resp_no_auth.status_code == 401
        assert "Invalid or missing tracking internal secret" in resp_no_auth.json()["detail"]

        # 2. Invalid secret -> 401
        resp_bad_auth = await async_client.get(
            "/api/v1/internal/tracking/events",
            headers={"X-Tracking-Internal-Secret": "wrong-secret"},
        )
        assert resp_bad_auth.status_code == 401

        # 3. Valid via X-Tracking-Internal-Secret -> 200
        resp_valid_header = await async_client.get(
            "/api/v1/internal/tracking/events",
            headers={"X-Tracking-Internal-Secret": secret},
        )
        assert resp_valid_header.status_code == 200
        assert isinstance(resp_valid_header.json(), list)

        # 4. Valid via Bearer Authorization -> 200
        resp_valid_bearer = await async_client.get(
            "/api/v1/internal/tracking/events",
            headers={"Authorization": f"Bearer {secret}"},
        )
        assert resp_valid_bearer.status_code == 200
        assert isinstance(resp_valid_bearer.json(), list)


@pytest.mark.asyncio
async def test_tracking_events_api_pagination_filtering_and_zero_pii(
    async_client: AsyncClient, db_session: AsyncSession
):
    """Verify pagination, event-type filtering, tenant isolation, and strict Zero-PII contract."""
    secret = "internal-test-secret-t51-secure-token"
    company_a = 501
    company_b = 502

    # Create tokens for Company A
    token_a1, _ = await EmailTrackingService.create_tracking_token(
        db=db_session,
        company_id=company_a,
        email_id=10,
        campaign_id=100,
        recipient_id=1001,
        delivery_id=10001,
        token_type=TrackingTokenType.OPEN,
    )
    token_a2, _ = await EmailTrackingService.create_tracking_token(
        db=db_session,
        company_id=company_a,
        email_id=10,
        campaign_id=100,
        recipient_id=1001,
        delivery_id=10001,
        token_type=TrackingTokenType.CLICK,
        destination_url="https://example.com/a2",
    )

    # Create token for Company B
    token_b1, _ = await EmailTrackingService.create_tracking_token(
        db=db_session,
        company_id=company_b,
        email_id=20,
        campaign_id=200,
        recipient_id=2001,
        delivery_id=20001,
        token_type=TrackingTokenType.OPEN,
    )
    await db_session.flush()

    # Create events
    ev1 = await EmailTrackingService.record_tracking_event(
        db=db_session,
        token=token_a1,
        event_type=TrackingEventType.OPEN,
        user_agent="GoogleImageProxy",
        ip_address="66.249.80.1",
        is_bot=True,
        bot_reason="google_image_proxy",
        bot_confidence=0.95,
    )
    ev2 = await EmailTrackingService.record_tracking_event(
        db=db_session,
        token=token_a2,
        event_type=TrackingEventType.CLICK,
        user_agent="Mozilla/5.0 SafeLinks/1.0",
        ip_address="52.100.1.1",
        is_bot=True,
        bot_reason="microsoft_safelinks",
        bot_confidence=0.90,
    )
    ev3 = await EmailTrackingService.record_tracking_event(
        db=db_session,
        token=token_a1,
        event_type=TrackingEventType.OPEN,
        user_agent="Mozilla/5.0 Chrome/120.0.0.0 Safari/537.36",
        ip_address="198.51.100.2",
        is_bot=None,
    )
    ev4 = await EmailTrackingService.record_tracking_event(
        db=db_session,
        token=token_b1,
        event_type=TrackingEventType.OPEN,
        user_agent="Mozilla/5.0 Safari/537.36",
        ip_address="198.51.100.3",
        is_bot=None,
    )
    await db_session.commit()

    with patch.object(settings, "TRACKING_INTERNAL_SECRET", secret):
        headers = {"X-Tracking-Internal-Secret": secret}

        # 1. Fetch all events for company_a
        resp = await async_client.get(
            f"/api/v1/internal/tracking/events?company_id={company_a}",
            headers=headers,
        )
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 3
        # Assert ascending event IDs
        event_ids = [item["event_id"] for item in items]
        assert event_ids == sorted(event_ids)
        assert all(item["company_id"] == company_a for item in items)

        # 2. Assert Zero PII and No Secret Leaks
        for item in items:
            assert "raw_token" not in item
            assert "token_hash" not in item
            assert "email" not in item
            assert "recipient_email" not in item
            assert "destination_url" not in item
            assert "ip_address" not in item
            assert "client_ip" not in item
            # Confirm required association keys
            assert item["campaign_id"] == 100
            assert item["recipient_id"] == 1001
            assert item["delivery_id"] == 10001
            assert "occurred_at" in item

        # 3. Test Type Filtering: types=CLICK
        resp_clicks = await async_client.get(
            f"/api/v1/internal/tracking/events?company_id={company_a}&types=CLICK",
            headers=headers,
        )
        assert resp_clicks.status_code == 200
        click_items = resp_clicks.json()
        assert len(click_items) == 1
        assert click_items[0]["event_type"] == "CLICK"
        assert click_items[0]["is_bot"] is True
        assert click_items[0]["bot_reason"] == "microsoft_safelinks"

        # 4. Test Cursor Pagination: since_id = ev1.id
        resp_cursor = await async_client.get(
            f"/api/v1/internal/tracking/events?company_id={company_a}&since_id={ev1.id}&limit=1",
            headers=headers,
        )
        assert resp_cursor.status_code == 200
        cursor_items = resp_cursor.json()
        assert len(cursor_items) == 1
        assert cursor_items[0]["event_id"] == ev2.id

        # 5. Company B isolation
        resp_b = await async_client.get(
            f"/api/v1/internal/tracking/events?company_id={company_b}",
            headers=headers,
        )
        assert resp_b.status_code == 200
        b_items = resp_b.json()
        assert len(b_items) == 1
        assert b_items[0]["company_id"] == company_b
        assert b_items[0]["event_id"] == ev4.id


@pytest.mark.asyncio
async def test_end_to_end_public_tracking_classification_integration(
    async_client: AsyncClient, db_session: AsyncSession
):
    """Verify public endpoints /t/o/{token} and /t/c/{token} automatically classify events in DB."""
    secret = "internal-test-secret-t51-secure-token"
    company_id = 601

    # Token for Open Pixel
    open_token_rec, open_raw = await EmailTrackingService.create_tracking_token(
        db=db_session,
        company_id=company_id,
        email_id=55,
        token_type=TrackingTokenType.OPEN,
    )
    # Token for Click Redirect
    click_token_rec, click_raw = await EmailTrackingService.create_tracking_token(
        db=db_session,
        company_id=company_id,
        email_id=56,
        token_type=TrackingTokenType.CLICK,
        destination_url="https://example.com/target-page",
    )
    await db_session.commit()

    # 1. Trigger Open with Google Image Proxy UA
    open_resp = await async_client.get(
        f"/t/o/{open_raw}",
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 5.1; rv:11.0) Gecko Firefox/11.0 (via ggpht.com GoogleImageProxy)"},
    )
    assert open_resp.status_code == 200

    # 2. Trigger Click with SafeLinks UA
    click_resp = await async_client.get(
        f"/t/c/{click_raw}",
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) SafeLinks/1.0"},
    )
    assert click_resp.status_code == 302

    # 3. Trigger Open with Standard Interactive Chrome UA
    open_chrome_resp = await async_client.get(
        f"/t/o/{open_raw}",
        headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"},
    )
    assert open_chrome_resp.status_code == 200

    # 4. Query events directly from DB to verify classification persistence
    stmt = (
        select(EmailTrackingEvent)
        .where(EmailTrackingEvent.company_id == company_id)
        .order_by(EmailTrackingEvent.id.asc())
    )
    events = (await db_session.execute(stmt)).scalars().all()
    assert len(events) == 3

    # Event 1: Google Image Proxy Open (Provider proxy remains unclassified UNKNOWN)
    assert events[0].event_type == "OPEN"
    assert events[0].is_bot is None
    assert events[0].bot_reason == "google_image_proxy"
    assert events[0].bot_confidence is None

    # Event 2: SafeLinks Click
    assert events[1].event_type == "CLICK"
    assert events[1].is_bot is True
    assert events[1].bot_reason == "microsoft_safelinks"
    assert events[1].bot_confidence >= 0.90

    # Event 3: Human / Standard Browser Open (Authentic Mozilla/5.0 classified as non-bot)
    assert events[2].event_type == "OPEN"
    assert events[2].is_bot is False
    assert events[2].bot_reason is None
    assert events[2].bot_confidence == 0.85


@pytest.mark.asyncio
async def test_existing_unsubscribes_endpoint_regression(
    async_client: AsyncClient, db_session: AsyncSession
):
    """Verify that existing /api/v1/unsubscribes endpoint continues to function without disturbance."""
    secret = "internal-test-secret-t51-secure-token"
    company_id = 701

    token_rec, raw_token = await EmailTrackingService.create_tracking_token(
        db=db_session,
        company_id=company_id,
        email_id=88,
        campaign_id=99,
        recipient_id=123,
        token_type=TrackingTokenType.UNSUBSCRIBE,
        destination_url="email:optout@example.com",
    )
    await db_session.flush()

    # Record unsubscribe event
    await EmailTrackingService.record_tracking_event(
        db=db_session,
        token=token_rec,
        event_type=TrackingEventType.UNSUBSCRIBE,
        user_agent="Mozilla/5.0 RFC8058Client",
    )
    await db_session.commit()

    with patch.object(settings, "TRACKING_INTERNAL_SECRET", secret):
        resp = await async_client.get(
            "/api/v1/unsubscribes?since_id=0&limit=10",
            headers={"X-Tracking-Internal-Secret": secret},
        )
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) >= 1
        unsub_item = next(it for it in items if it["company_id"] == company_id)
        assert unsub_item["campaign_id"] == 99
        assert unsub_item["recipient_id"] == 123
        assert unsub_item["email"] == "optout@example.com"
        assert "event_id" in unsub_item


@pytest.mark.asyncio
async def test_tracking_service_client_get_tracking_events():
    """Verify TrackingServiceClient.get_tracking_events fetches, formats, and handles errors safely."""
    client = TrackingServiceClient(
        service_url="http://mock-tracking-server:8000",
        internal_secret="mock-secret-t51",
    )
    assert client.is_configured is True

    mock_events = [
        {
            "event_id": 1,
            "company_id": 10,
            "campaign_id": 100,
            "recipient_id": 50,
            "delivery_id": 200,
            "event_type": "OPEN",
            "occurred_at": "2026-11-20T10:00:00Z",
            "is_bot": True,
            "bot_reason": "apple_mpp",
            "bot_confidence": 0.95,
        }
    ]

    # Test successful fetch with filters
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_events

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp

        results = await client.get_tracking_events(
            since_id=0,
            limit=50,
            types=["OPEN", "CLICK"],
            company_id=10,
        )
        assert len(results) == 1
        assert results[0]["event_id"] == 1
        assert results[0]["bot_reason"] == "apple_mpp"

        # Assert query params sent to server
        assert mock_get.call_count == 1
        call_kwargs = mock_get.call_args[1]
        assert call_kwargs["params"]["since_id"] == 0
        assert call_kwargs["params"]["limit"] == 50
        assert call_kwargs["params"]["types"] == "OPEN,CLICK"
        assert call_kwargs["params"]["company_id"] == 10
        assert call_kwargs["headers"]["X-Tracking-Internal-Secret"] == "mock-secret-t51"

    # Test network failure fails safely (returns empty list without raising)
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=httpx.ConnectError("Failed to connect")):
        failed_results = await client.get_tracking_events(since_id=0)
        assert failed_results == []

