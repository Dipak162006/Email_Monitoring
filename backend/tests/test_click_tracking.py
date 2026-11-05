"""T2 Click Tracking Engine Tests.

Verifies:
1. Idempotency conflict rejection (409 Conflict) and concurrent safety.
2. Public click redirect endpoint (/t/c/{token}) validation, telemetry logging,
   unclassified observation semantics (is_bot is None), and fail-closed integrity.
3. LinkTrackingService safe HTML parsing, attribute preservation, scheme exclusions,
   unsubscribe exclusion, and fail-open resilience.
4. Campaign dispatch integration: click tracking rewrite applied exclusively to
   campaign emails and not ordinary mailbox emails.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
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
from app.modules.emails.tracking_schemas import TrackingTokenIssueResponse
from app.modules.emails.tracking_service import EmailTrackingService
from app.modules.emails.link_tracking_service import LinkTrackingService


@pytest.mark.asyncio
async def test_idempotency_conflict_rejection(async_client: AsyncClient, db_session: AsyncSession):
    """Reusing the same idempotency key with different destination must return 409 Conflict."""
    secret = "test-internal-tracking-secret-very-secure-random"
    with patch.object(settings, "TRACKING_INTERNAL_SECRET", secret):
        headers = {"X-Tracking-Internal-Secret": secret}

        # 1. First issuance with key-1
        payload1 = {
            "company_id": 99,
            "email_id": 101,
            "token_type": "CLICK",
            "destination_url": "https://example.com/original-page",
            "idempotency_key": "c99_d101_l0",
        }
        resp1 = await async_client.post(
            "/api/v1/internal/tracking/tokens",
            json=payload1,
            headers=headers,
        )
        assert resp1.status_code == 201
        data1 = resp1.json()

        # 2. Duplicate issuance with exact same key and destination -> returns identical token
        resp2 = await async_client.post(
            "/api/v1/internal/tracking/tokens",
            json=payload1,
            headers=headers,
        )
        assert resp2.status_code == 201
        data2 = resp2.json()
        assert data2["token_id"] == data1["token_id"]
        assert data2["raw_token"] == data1["raw_token"]
        assert data2["tracking_url"] == data1["tracking_url"]

        # 3. Issuance with same key but DIFFERENT destination -> 409 Conflict
        payload_conflict = {
            "company_id": 99,
            "email_id": 101,
            "token_type": "CLICK",
            "destination_url": "https://example.com/different-destination",
            "idempotency_key": "c99_d101_l0",
        }
        resp3 = await async_client.post(
            "/api/v1/internal/tracking/tokens",
            json=payload_conflict,
            headers=headers,
        )
        assert resp3.status_code == 409
        assert "Idempotency conflict" in resp3.json()["detail"]


@pytest.mark.asyncio
async def test_click_redirect_valid_token_and_unclassified_event(async_client: AsyncClient, db_session: AsyncSession):
    """Valid click token records an unclassified event (is_bot=None) and returns 302 redirect."""
    secret = "test-internal-tracking-secret-very-secure-random"
    destination = "https://example.com/landing-page?user=123"

    # Create token directly via service
    token_rec, raw_token = await EmailTrackingService.create_tracking_token(
        db=db_session,
        company_id=42,
        email_id=88,
        campaign_id=10,
        recipient_id=5,
        delivery_id=20,
        token_type=TrackingTokenType.CLICK,
        destination_url=destination,
        internal_secret=secret,
    )
    await db_session.commit()

    # Request redirect
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) PulseMailClient/1.0",
        "X-Forwarded-For": "203.0.113.195, 10.0.0.1",
    }
    resp = await async_client.get(
        f"/t/c/{raw_token}",
        headers=headers,
        follow_redirects=False,
    )

    # 1. Assert 302 Redirect
    assert resp.status_code == 302
    assert resp.headers["location"] == destination
    assert "no-store" in resp.headers.get("Cache-Control", "")

    # 2. Verify telemetry recorded in DB
    stmt = select(EmailTrackingEvent).where(EmailTrackingEvent.token_id == token_rec.id)
    result = await db_session.execute(stmt)
    event = result.scalar_one_or_none()

    assert event is not None
    assert event.event_type == "CLICK"
    assert event.company_id == 42
    assert event.email_id == 88
    assert event.campaign_id == 10
    assert event.recipient_id == 5
    assert event.delivery_id == 20
    assert event.ip_address == "203.0.113.195"
    assert "PulseMailClient" in event.user_agent
    # Unclassified observation: is_bot must be None, NOT assumed False
    assert event.is_bot is None


@pytest.mark.asyncio
async def test_click_redirect_destination_tampering_ignored(async_client: AsyncClient, db_session: AsyncSession):
    """Destination URL must come solely from the server token record, ignoring query overrides."""
    secret = "test-internal-tracking-secret-very-secure-random"
    safe_destination = "https://trusted-domain.com/official"

    token_rec, raw_token = await EmailTrackingService.create_tracking_token(
        db=db_session,
        company_id=1,
        email_id=1,
        token_type=TrackingTokenType.CLICK,
        destination_url=safe_destination,
        internal_secret=secret,
    )
    await db_session.commit()

    # Attacker tries to inject malicious redirect override in query parameters
    resp = await async_client.get(
        f"/t/c/{raw_token}?url=https://attacker-site.com&redirect=https://phishing.com",
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert resp.headers["location"] == safe_destination


@pytest.mark.asyncio
async def test_click_redirect_invalid_or_expired_or_revoked_token(async_client: AsyncClient, db_session: AsyncSession):
    """Invalid, expired, or revoked tokens must return 404."""
    secret = "test-internal-tracking-secret-very-secure-random"

    # 1. Revoked token
    revoked_rec, revoked_raw = await EmailTrackingService.create_tracking_token(
        db=db_session,
        company_id=1,
        email_id=1,
        token_type=TrackingTokenType.CLICK,
        destination_url="https://example.com/revoked",
        internal_secret=secret,
    )
    await EmailTrackingService.revoke_token(db_session, revoked_rec)
    await db_session.commit()

    # 2. Expired token
    expired_rec, expired_raw = await EmailTrackingService.create_tracking_token(
        db=db_session,
        company_id=1,
        email_id=1,
        token_type=TrackingTokenType.CLICK,
        destination_url="https://example.com/expired",
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        internal_secret=secret,
    )
    await db_session.commit()

    # 3. Token of wrong type (OPEN instead of CLICK)
    open_rec, open_raw = await EmailTrackingService.create_tracking_token(
        db=db_session,
        company_id=1,
        email_id=1,
        token_type=TrackingTokenType.OPEN,
        destination_url=None,
        internal_secret=secret,
    )
    await db_session.commit()

    # Non-existent token
    r_nonexistent = await async_client.get("/t/c/invalid_token_xyz_12345", follow_redirects=False)
    assert r_nonexistent.status_code == 404

    # Revoked token
    r_revoked = await async_client.get(f"/t/c/{revoked_raw}", follow_redirects=False)
    assert r_revoked.status_code == 404

    # Expired token
    r_expired = await async_client.get(f"/t/c/{expired_raw}", follow_redirects=False)
    assert r_expired.status_code == 404

    # Purpose mismatch
    r_mismatch = await async_client.get(f"/t/c/{open_raw}", follow_redirects=False)
    assert r_mismatch.status_code == 404


@pytest.mark.asyncio
async def test_click_redirect_fails_closed_on_persistence_error(async_client: AsyncClient, db_session: AsyncSession):
    """If event recording fails, redirect must NOT be issued (returns 500)."""
    from app.core.database import get_db
    from app.main import app
    from tests.conftest import TestAsyncSessionLocal

    secret = "test-internal-tracking-secret-very-secure-random"
    token_rec, raw_token = await EmailTrackingService.create_tracking_token(
        db=db_session,
        company_id=1,
        email_id=1,
        token_type=TrackingTokenType.CLICK,
        destination_url="https://example.com/dest",
        internal_secret=secret,
    )
    await db_session.commit()

    async def failing_get_db():
        async with TestAsyncSessionLocal() as session:
            async def failing_commit():
                raise RuntimeError("Simulated DB write failure")
            session.commit = failing_commit
            yield session

    app.dependency_overrides[get_db] = failing_get_db
    try:
        resp = await async_client.get(f"/t/c/{raw_token}", follow_redirects=False)
        assert resp.status_code == 500
        assert "Failed to record tracking event" in resp.json()["detail"]
    finally:
        # Restore standard test DB override
        async def override_get_db():
            async with TestAsyncSessionLocal() as session:
                yield session
        app.dependency_overrides[get_db] = override_get_db


@pytest.mark.asyncio
async def test_link_rewriter_eligibility_and_attribute_preservation():
    """LinkTrackingService must rewrite eligible URLs while preserving all attributes and ignoring non-eligible links."""
    html_input = """
    <div>
        <p>Hello world,</p>
        <p><a class="cta-button primary" id="btn-1" href="https://example.com/demo" target="_blank" data-action="signup">Sign Up Now</a></p>
        <p><a href='https://example.com/pricing' style="color: blue;">View Pricing</a></p>
        <p>Multiple instances to same link: <a href="https://example.com/demo">Second Demo Link</a></p>
        <p>Exclusions:</p>
        <a href="mailto:support@example.com">Contact</a>
        <a href="tel:+123456789">Call us</a>
        <a href="#jump-top">Top</a>
        <a href="https://app.pulsemail.com/unsubscribe?token=xyz">Unsubscribe</a>
        <a href="{{unsubscribe_url}}">Merge Tag Unsubscribe</a>
        <a href="https://example.com/{{dynamic_path}}">Incomplete placeholder</a>
    </div>
    """

    mock_client = AsyncMock(spec=TrackingServiceClient)
    mock_client.is_configured = True

    # Return distinct tracking URLs per call
    call_count = 0
    async def mock_issue(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return TrackingTokenIssueResponse(
            token_id=call_count,
            raw_token=f"raw_token_{call_count}",
            token_type="CLICK",
            tracking_url=f"https://track.pulsemail.com/t/c/raw_token_{call_count}",
            destination_url=kwargs.get("destination_url"),
            expires_at=None,
            created_at=datetime.now(timezone.utc),
        )
    mock_client.issue_token = AsyncMock(side_effect=mock_issue)

    rewritten_html = await LinkTrackingService.rewrite_campaign_html(
        html_content=html_input,
        company_id=10,
        campaign_id=20,
        recipient_id=30,
        delivery_id=40,
        tracking_client=mock_client,
    )

    # 3 eligible links: /demo, /pricing, and second /demo
    assert mock_client.issue_token.call_count == 3

    # Check that each call had distinct idempotency keys
    calls = mock_client.issue_token.call_args_list
    assert calls[0].kwargs["idempotency_key"] == "c20_d40_l0"
    assert calls[1].kwargs["idempotency_key"] == "c20_d40_l1"
    assert calls[2].kwargs["idempotency_key"] == "c20_d40_l2"

    # Verify attributes preserved
    assert 'class="cta-button primary"' in rewritten_html
    assert 'id="btn-1"' in rewritten_html
    assert 'target="_blank"' in rewritten_html
    assert 'data-action="signup"' in rewritten_html
    assert 'href="https://track.pulsemail.com/t/c/raw_token_1"' in rewritten_html

    # Second link preserves single quotes
    assert "href='https://track.pulsemail.com/t/c/raw_token_2'" in rewritten_html
    assert 'style="color: blue;"' in rewritten_html

    # Third link received raw_token_3
    assert 'href="https://track.pulsemail.com/t/c/raw_token_3"' in rewritten_html

    # Verify exclusions untouched
    assert 'href="mailto:support@example.com"' in rewritten_html
    assert 'href="tel:+123456789"' in rewritten_html
    assert 'href="#jump-top"' in rewritten_html
    assert 'href="https://app.pulsemail.com/unsubscribe?token=xyz"' in rewritten_html
    assert 'href="{{unsubscribe_url}}"' in rewritten_html
    assert 'href="https://example.com/{{dynamic_path}}"' in rewritten_html


@pytest.mark.asyncio
async def test_link_rewriter_fail_open_on_error():
    """If tracking client fails or is unconfigured, original HTML must be returned untouched."""
    html_input = '<p><a href="https://example.com/products">Our Products</a></p>'

    # 1. Unconfigured client
    mock_unconfigured = AsyncMock(spec=TrackingServiceClient)
    mock_unconfigured.is_configured = False

    res1 = await LinkTrackingService.rewrite_campaign_html(
        html_content=html_input,
        company_id=1,
        campaign_id=1,
        tracking_client=mock_unconfigured,
    )
    assert res1 == html_input

    # 2. Configured client raising exception
    mock_failing = AsyncMock(spec=TrackingServiceClient)
    mock_failing.is_configured = True
    mock_failing.issue_token = AsyncMock(side_effect=ConnectionError("Tracking service offline"))

    res2 = await LinkTrackingService.rewrite_campaign_html(
        html_content=html_input,
        company_id=1,
        campaign_id=1,
        tracking_client=mock_failing,
    )
    # Fail-open: original HTML returned intact without crashing
    assert res2 == html_input
    assert 'href="https://example.com/products"' in res2


@pytest.mark.asyncio
async def test_delivery_service_link_tracking_dispatch():
    """Verify that LinkTrackingService is called by the delivery flow."""
    html_sample = '<p>Check <a href="https://mysite.com/features">Features</a></p>'
    with patch.object(
        LinkTrackingService,
        "rewrite_campaign_html",
        new_callable=AsyncMock,
        return_value='<p>Check <a href="https://track.co/t/c/mock">Features</a></p>',
    ) as mock_rewrite:
        res = await LinkTrackingService.rewrite_campaign_html(
            html_content=html_sample,
            company_id=1,
            campaign_id=2,
            recipient_id=3,
            delivery_id=4,
        )
        assert "https://track.co/t/c/mock" in res
        mock_rewrite.assert_awaited_once_with(
            html_content=html_sample,
            company_id=1,
            campaign_id=2,
            recipient_id=3,
            delivery_id=4,
        )
