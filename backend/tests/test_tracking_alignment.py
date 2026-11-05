from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
import httpx
import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, settings
from app.main import app
from app.modules.emails.models import (
    EmailTrackingEvent,
    EmailTrackingToken,
    TrackingEventType,
    TrackingTokenType,
)
from app.modules.emails.tracking_client import TrackingServiceClient
from app.modules.emails.tracking_routes import verify_tracking_internal_secret
from app.modules.emails.tracking_schemas import (
    TrackingTokenIssueRequest,
    TrackingTokenIssueResponse,
)
from app.modules.emails.tracking_service import EmailTrackingService


@pytest.mark.asyncio
async def test_tracking_records_created_without_local_parent_records(db_session: AsyncSession):
    """Verify that tracking records can be persisted with arbitrary company_id and email_id
    without requiring existing parent rows in companies or emails tables (cross-backend independence)."""
    non_existent_company_id = 999999
    non_existent_email_id = 888888

    token_rec, raw_token = await EmailTrackingService.create_tracking_token(
        db=db_session,
        company_id=non_existent_company_id,
        email_id=non_existent_email_id,
        token_type=TrackingTokenType.CLICK,
        destination_url="https://pulsemail.io/decoupled-test",
    )
    await db_session.flush()

    assert token_rec.id is not None
    assert token_rec.company_id == non_existent_company_id
    assert token_rec.email_id == non_existent_email_id

    # Create event linked to this token without parent companies/emails rows
    event = await EmailTrackingService.record_tracking_event(
        db=db_session,
        token=token_rec,
        event_type=TrackingEventType.CLICK,
        ip_address="198.51.100.25",
        user_agent="TestAgent/1.0",
    )
    await db_session.flush()

    assert event.id is not None
    assert event.company_id == non_existent_company_id
    assert event.email_id == non_existent_email_id
    assert event.token_id == token_rec.id


@pytest.mark.asyncio
async def test_tracking_token_event_internal_relationship(db_session: AsyncSession):
    """Verify that the internal parent-child relationship between EmailTrackingToken and
    EmailTrackingEvent remains properly constrained and cascades on delete."""
    token_rec, raw_token = await EmailTrackingService.create_tracking_token(
        db=db_session,
        company_id=101,
        email_id=202,
        token_type=TrackingTokenType.OPEN,
    )
    await db_session.flush()

    event1 = await EmailTrackingService.record_tracking_event(
        db=db_session,
        token=token_rec,
        event_type=TrackingEventType.OPEN,
    )
    event2 = await EmailTrackingService.record_tracking_event(
        db=db_session,
        token=token_rec,
        event_type=TrackingEventType.OPEN,
    )
    await db_session.flush()

    # Verify relationship
    events_count = (await db_session.execute(
        select(func.count(EmailTrackingEvent.id)).where(EmailTrackingEvent.token_id == token_rec.id)
    )).scalar_one()
    assert events_count == 2

    # Deleting token should cascade delete linked events
    await db_session.delete(token_rec)
    await db_session.flush()

    remaining_events = (await db_session.execute(
        select(func.count(EmailTrackingEvent.id)).where(EmailTrackingEvent.token_id == token_rec.id)
    )).scalar_one()
    assert remaining_events == 0


@pytest.mark.asyncio
async def test_internal_endpoint_rejects_missing_or_invalid_auth(async_client: AsyncClient):
    """Verify that POST /api/v1/internal/tracking/tokens strictly rejects calls without valid secret."""
    payload = {
        "company_id": 1,
        "email_id": 10,
        "token_type": "CLICK",
        "destination_url": "https://pulsemail.io",
    }

    # 1. Missing auth header
    res_no_auth = await async_client.post("/api/v1/internal/tracking/tokens", json=payload)
    assert res_no_auth.status_code == 401

    # 2. Invalid secret in X-Tracking-Internal-Secret header
    res_bad_secret = await async_client.post(
        "/api/v1/internal/tracking/tokens",
        json=payload,
        headers={"X-Tracking-Internal-Secret": "wrong-secret-value"},
    )
    assert res_bad_secret.status_code == 401

    # 3. Invalid secret in Bearer Authorization header
    res_bad_bearer = await async_client.post(
        "/api/v1/internal/tracking/tokens",
        json=payload,
        headers={"Authorization": "Bearer wrong-secret-value"},
    )
    assert res_bad_bearer.status_code == 401


@pytest.mark.asyncio
async def test_internal_endpoint_valid_issuance(async_client: AsyncClient, db_session: AsyncSession):
    """Verify successful server-to-server token issuance."""
    test_secret = "test-high-entropy-internal-secret-32ch"

    with patch.object(settings, "TRACKING_INTERNAL_SECRET", test_secret):
        payload = {
            "company_id": 42,
            "email_id": 99,
            "token_type": "CLICK",
            "destination_url": "https://pulsemail.io/demo",
            "expires_in_seconds": 86400,
        }

        res = await async_client.post(
            "/api/v1/internal/tracking/tokens",
            json=payload,
            headers={"X-Tracking-Internal-Secret": test_secret},
        )

        assert res.status_code == 201
        data = res.json()

        assert "token_id" in data
        assert "raw_token" in data
        assert "tracking_url" in data
        assert data["token_type"] == "CLICK"
        assert data["destination_url"] == "https://pulsemail.io/demo"
        assert f"/t/c/{data['raw_token']}" in data["tracking_url"]

        # Verify database record: only SHA-256 hash is persisted
        token_row = (await db_session.execute(
            select(EmailTrackingToken).where(EmailTrackingToken.id == data["token_id"])
        )).scalar_one()

        assert token_row.token_hash == EmailTrackingService.hash_token(data["raw_token"])
        assert token_row.destination_url == "https://pulsemail.io/demo"


@pytest.mark.asyncio
async def test_internal_endpoint_idempotency(async_client: AsyncClient, db_session: AsyncSession):
    """Verify that retrying token issuance with the same idempotency key yields the exact same
    raw token and tracking URL without creating duplicate database records."""
    test_secret = "test-idempotent-secret-key-32chars!"
    idempotency_key = "idemp_msg_42_link_0"

    with patch.object(settings, "TRACKING_INTERNAL_SECRET", test_secret):
        payload = {
            "company_id": 50,
            "email_id": 77,
            "token_type": "CLICK",
            "destination_url": "https://pulsemail.io/pricing",
            "idempotency_key": idempotency_key,
        }

        # First request
        res1 = await async_client.post(
            "/api/v1/internal/tracking/tokens",
            json=payload,
            headers={"X-Tracking-Internal-Secret": test_secret},
        )
        assert res1.status_code == 201
        data1 = res1.json()

        # Second request (retry)
        res2 = await async_client.post(
            "/api/v1/internal/tracking/tokens",
            json=payload,
            headers={"X-Tracking-Internal-Secret": test_secret},
        )
        assert res2.status_code == 201
        data2 = res2.json()

        # Both responses must be identical
        assert data1["token_id"] == data2["token_id"]
        assert data1["raw_token"] == data2["raw_token"]
        assert data1["tracking_url"] == data2["tracking_url"]

        # Exactly 1 row must exist in the database with this idempotency key
        count = (await db_session.execute(
            select(func.count(EmailTrackingToken.id)).where(
                EmailTrackingToken.idempotency_key == idempotency_key
            )
        )).scalar_one()
        assert count == 1


@pytest.mark.asyncio
async def test_internal_endpoint_validation_failures(async_client: AsyncClient):
    """Verify input validation for token purpose, missing destination URL, and malformed URLs."""
    test_secret = "test-validation-secret-key-32chars"

    with patch.object(settings, "TRACKING_INTERNAL_SECRET", test_secret):
        headers = {"X-Tracking-Internal-Secret": test_secret}

        # 1. Invalid token type
        res_invalid_type = await async_client.post(
            "/api/v1/internal/tracking/tokens",
            json={"company_id": 1, "email_id": 1, "token_type": "FORBIDDEN_TYPE"},
            headers=headers,
        )
        assert res_invalid_type.status_code == 422

        # 2. CLICK token without destination_url
        res_missing_url = await async_client.post(
            "/api/v1/internal/tracking/tokens",
            json={"company_id": 1, "email_id": 1, "token_type": "CLICK"},
            headers=headers,
        )
        assert res_missing_url.status_code == 422

        # 3. Non-http/https destination URL (e.g. javascript:)
        res_js_url = await async_client.post(
            "/api/v1/internal/tracking/tokens",
            json={
                "company_id": 1,
                "email_id": 1,
                "token_type": "CLICK",
                "destination_url": "javascript:alert('xss')",
            },
            headers=headers,
        )
        assert res_js_url.status_code == 422


@pytest.mark.asyncio
async def test_tracking_service_client_success():
    """Verify TrackingServiceClient successful token issuance parsing."""
    client = TrackingServiceClient(
        service_url="https://email-monitoring.onrender.com",
        internal_secret="client-test-secret",
        timeout_seconds=2.0,
    )
    assert client.is_configured is True

    mock_response = {
        "token_id": 123,
        "raw_token": "mocked_raw_token_xyz123",
        "token_type": "CLICK",
        "tracking_url": "https://email-monitoring.onrender.com/t/c/mocked_raw_token_xyz123",
        "destination_url": "https://pulsemail.io/success",
        "expires_at": None,
        "created_at": "2026-11-05T17:00:00Z",
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = httpx.Response(201, json=mock_response)

        result = await client.issue_token(
            company_id=1,
            email_id=5,
            token_type=TrackingTokenType.CLICK,
            destination_url="https://pulsemail.io/success",
        )

        assert result is not None
        assert result.token_id == 123
        assert result.raw_token == "mocked_raw_token_xyz123"
        assert result.tracking_url == "https://email-monitoring.onrender.com/t/c/mocked_raw_token_xyz123"


@pytest.mark.asyncio
async def test_tracking_service_client_resilience_and_fail_open():
    """Verify that TrackingServiceClient fails open (returns None) on timeouts, connection errors,
    or non-201 HTTP responses so email sending is NEVER halted."""
    client = TrackingServiceClient(
        service_url="https://email-monitoring.onrender.com",
        internal_secret="client-test-secret",
        timeout_seconds=0.5,
    )

    # 1. Timeout failure -> returns None
    with patch("httpx.AsyncClient.post", side_effect=httpx.TimeoutException("Simulated timeout")):
        res_timeout = await client.issue_token(
            company_id=1,
            email_id=2,
            token_type=TrackingTokenType.CLICK,
            destination_url="https://pulsemail.io",
        )
        assert res_timeout is None

    # 2. Connection failure -> returns None
    with patch("httpx.AsyncClient.post", side_effect=httpx.ConnectError("Simulated connection refused")):
        res_conn = await client.issue_token(
            company_id=1,
            email_id=2,
            token_type=TrackingTokenType.CLICK,
            destination_url="https://pulsemail.io",
        )
        assert res_conn is None

    # 3. Non-201 HTTP status -> returns None
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = httpx.Response(500, text="Internal Server Error")
        res_500 = await client.issue_token(
            company_id=1,
            email_id=2,
            token_type=TrackingTokenType.CLICK,
            destination_url="https://pulsemail.io",
        )
        assert res_500 is None

    # 4. Unconfigured client -> returns None immediately without network call
    unconfigured_client = TrackingServiceClient(service_url="", internal_secret="")
    assert unconfigured_client.is_configured is False
    res_unconfigured = await unconfigured_client.issue_token(
        company_id=1,
        email_id=2,
        token_type=TrackingTokenType.CLICK,
        destination_url="https://pulsemail.io",
    )
    assert res_unconfigured is None


@pytest.mark.asyncio
async def test_alembic_025_migration_cycle(test_alembic_config: Config):
    """Verify that Alembic can downgrade 025 to 024 and upgrade cleanly to head."""
    from tests.conftest import test_async_engine

    await test_async_engine.dispose()
    command.stamp(test_alembic_config, "head")

    # Downgrade 025 -> 024 (re-adds foreign keys, drops idempotency_key)
    command.downgrade(test_alembic_config, "024_email_tracking_tables")

    # Upgrade 024 -> 025 (drops foreign keys, re-adds idempotency_key)
    command.upgrade(test_alembic_config, "025_decouple_tracking_fkeys")

    await test_async_engine.dispose()

