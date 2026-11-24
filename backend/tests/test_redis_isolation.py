"""Targeted tests for permanent Pytest Redis isolation and safety interlocks (T5.6.8).

Verifies:
1. Test Redis resolves strictly to DB 15.
2. DB 0 is rejected by the safety interlocks (fail-closed).
3. Test cursor writes do not alter development Redis DB 0 values.
4. Test cleanup flushes only DB 15 and does not affect DB 0.
"""
import urllib.parse
import pytest
import redis.asyncio as aioredis

from app.core.config import settings
from app.core.redis import get_redis_client
from app.core import redis as core_redis
from app.modules.campaigns.tracking_sync_service import TrackingEventSyncService
from app.modules.campaigns.unsubscribe_service import UnsubscribeService
from tests.conftest import (
    TEST_REDIS_DB,
    derive_safe_test_redis_url,
    validate_test_redis_url,
)


@pytest.mark.asyncio
async def test_redis_resolves_to_db_15(test_redis_client):
    """1. Verify that pytest Redis settings and clients strictly resolve to DB 15."""
    assert settings.REDIS_DB == 15
    parsed = urllib.parse.urlparse(settings.REDIS_URL)
    assert parsed.path == "/15"

    client = get_redis_client()
    assert client.connection_pool.connection_kwargs.get("db") == TEST_REDIS_DB


def test_db_0_rejected_by_safety_interlock():
    """2. Verify that safety interlocks immediately raise RuntimeError when DB 0 is encountered."""
    # Validator checks
    with pytest.raises(RuntimeError, match="FATAL SAFETY INTERLOCK"):
        validate_test_redis_url("redis://localhost:6379/0")

    with pytest.raises(RuntimeError, match="FATAL SAFETY INTERLOCK"):
        validate_test_redis_url("redis://redis:6379")

    with pytest.raises(RuntimeError, match="FATAL SAFETY INTERLOCK"):
        derive_safe_test_redis_url("redis://localhost:6379/0", target_db=0)

    # Core client interlock check
    original_url = settings.REDIS_URL
    original_client = core_redis.redis_client
    try:
        core_redis.redis_client = None
        settings.REDIS_URL = "redis://localhost:6379/0"
        with pytest.raises(RuntimeError, match="FATAL SAFETY INTERLOCK.*protected DB 0"):
            get_redis_client()
    finally:
        settings.REDIS_URL = original_url
        core_redis.redis_client = original_client


@pytest.mark.asyncio
async def test_cursor_writes_do_not_alter_dev_cursor(test_redis_client):
    """3. Verify test cursor writes in DB 15 do not alter development DB 0 cursors."""
    # Capture DB 0 baseline before test writes
    parsed = urllib.parse.urlparse(settings.REDIS_URL)
    dev_url = urllib.parse.urlunparse(parsed._replace(path="/0"))
    dev_client = aioredis.from_url(dev_url, encoding="utf-8", decode_responses=True)
    try:
        baseline_int = await dev_client.get(TrackingEventSyncService.CURSOR_REDIS_KEY)
        baseline_unsub = await dev_client.get(UnsubscribeService.CURSOR_REDIS_KEY)

        # Write mock test cursors via standard application services into DB 15
        await TrackingEventSyncService.set_sync_cursor(999999)
        await UnsubscribeService.set_sync_cursor(888888)

        # Verify they were written to DB 15
        assert await TrackingEventSyncService.get_sync_cursor() == 999999
        assert await UnsubscribeService.get_sync_cursor() == 888888

        # Directly read DB 0 using the separate client to verify DB 0 is completely unchanged
        current_int = await dev_client.get(TrackingEventSyncService.CURSOR_REDIS_KEY)
        current_unsub = await dev_client.get(UnsubscribeService.CURSOR_REDIS_KEY)

        assert current_int == baseline_int, f"DB 0 interaction cursor was modified! Before: {baseline_int}, After: {current_int}"
        assert current_unsub == baseline_unsub, f"DB 0 unsubscribe cursor was modified! Before: {baseline_unsub}, After: {current_unsub}"
        assert current_int != "999999"
        assert current_unsub != "888888"
    finally:
        await dev_client.aclose()


@pytest.mark.asyncio
async def test_cleanup_does_not_affect_db_0(test_redis_client):
    """4. Verify test cleanup / flushdb on DB 15 does not affect DB 0."""
    parsed = urllib.parse.urlparse(settings.REDIS_URL)
    dev_url = urllib.parse.urlunparse(parsed._replace(path="/0"))
    dev_client = aioredis.from_url(dev_url, encoding="utf-8", decode_responses=True)
    try:
        baseline_int = await dev_client.get(TrackingEventSyncService.CURSOR_REDIS_KEY)
        baseline_unsub = await dev_client.get(UnsubscribeService.CURSOR_REDIS_KEY)

        # Write temporary keys into DB 15
        await test_redis_client.set("temp_test_key", "test_value")
        assert await test_redis_client.get("temp_test_key") == "test_value"

        # Flush DB 15
        await test_redis_client.flushdb()
        assert await test_redis_client.get("temp_test_key") is None

        # Verify DB 0 remains untouched
        current_int = await dev_client.get(TrackingEventSyncService.CURSOR_REDIS_KEY)
        current_unsub = await dev_client.get(UnsubscribeService.CURSOR_REDIS_KEY)

        assert current_int == baseline_int
        assert current_unsub == baseline_unsub
    finally:
        await dev_client.aclose()
