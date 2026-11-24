import sys
from pathlib import Path
from typing import AsyncGenerator
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

# Ensure backend root is on sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from alembic.config import Config
from sqlalchemy.engine import make_url
import urllib.parse
from app.core import redis as core_redis

from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app

PROTECTED_DATABASE_NAMES = {
    "email_monitoring",
    "production",
    "prod",
    "postgres",
    "default",
}

PROTECTED_REDIS_DBS = {0}
TEST_REDIS_DB = 15


def derive_safe_test_redis_url(base_url: str, target_db: int = TEST_REDIS_DB) -> str:
    """Derive and validate an isolated test Redis URL from a base URL.
    
    Guarantees fail-closed safety by rejecting DB 0 and protected databases.
    """
    if not base_url:
        raise RuntimeError("FATAL SAFETY INTERLOCK: Base Redis URL is empty.")

    if target_db in PROTECTED_REDIS_DBS or target_db == 0:
        raise RuntimeError(
            f"FATAL SAFETY INTERLOCK: Target test Redis DB cannot be in protected DBs {PROTECTED_REDIS_DBS}!"
        )

    parsed = urllib.parse.urlparse(base_url)
    new_url = urllib.parse.urlunparse(parsed._replace(path=f"/{target_db}"))
    return new_url


def validate_test_redis_url(redis_url: str) -> int:
    """Validate that a Redis URL points strictly to an isolated test database (not DB 0)."""
    parsed = urllib.parse.urlparse(redis_url)
    db_str = parsed.path.lstrip("/")
    db_num = int(db_str) if db_str.isdigit() else 0
    if db_num in PROTECTED_REDIS_DBS or db_num == 0:
        raise RuntimeError(
            f"FATAL SAFETY INTERLOCK: Test Redis URL '{redis_url}' points to protected Redis DB {db_num}! "
            "Tests must strictly run against isolated Redis DB 15."
        )
    if db_num != TEST_REDIS_DB:
        raise RuntimeError(
            f"FATAL SAFETY INTERLOCK: Test Redis URL must use DB {TEST_REDIS_DB}, got DB {db_num}."
        )
    return db_num


# Derive and enforce test Redis configuration at pytest initialization
TEST_REDIS_URL = derive_safe_test_redis_url(settings.REDIS_URL, target_db=TEST_REDIS_DB)
validate_test_redis_url(TEST_REDIS_URL)

settings.REDIS_URL = TEST_REDIS_URL
settings.REDIS_DB = TEST_REDIS_DB
settings.CELERY_BROKER_URL = TEST_REDIS_URL
settings.CELERY_RESULT_BACKEND = TEST_REDIS_URL

# Reset global redis_client so any future get_redis_client() uses TEST_REDIS_URL
if core_redis.redis_client is not None:
    core_redis.redis_client = None



def derive_safe_test_db_url(base_url: str) -> str:
    """Derive and validate an isolated test database URL from a base URL.
    
    Guarantees fail-closed safety by rejecting any protected or non-test database.
    """
    if not base_url:
        raise RuntimeError("FATAL SAFETY INTERLOCK: Base database URL is empty.")

    parsed = make_url(base_url)
    db_name = (parsed.database or "").lower()

    if not db_name:
        raise RuntimeError("FATAL SAFETY INTERLOCK: Base database URL does not specify a database name.")

    # Derive test database name if not already ending in _test
    if not db_name.endswith("_test") and "test" not in db_name:
        test_db_name = f"{db_name}_test"
        parsed = parsed.set(database=test_db_name)
    else:
        test_db_name = db_name

    # Validate target database name
    if test_db_name in PROTECTED_DATABASE_NAMES:
        raise RuntimeError(
            f"FATAL SAFETY INTERLOCK: Derived test database '{test_db_name}' is in the protected database list!"
        )
    if not test_db_name.endswith("_test") and "test" not in test_db_name:
        raise RuntimeError(
            f"FATAL SAFETY INTERLOCK: Test database '{test_db_name}' must end with '_test' or contain 'test'!"
        )

    return parsed.render_as_string(hide_password=False)


# Dedicated, validated test database URLs (async and sync)
TEST_DATABASE_URL = derive_safe_test_db_url(settings.DATABASE_URL)
TEST_DATABASE_SYNC_URL = derive_safe_test_db_url(settings.DATABASE_SYNC_URL)

test_async_engine = create_async_engine(
    TEST_DATABASE_URL,
    echo=False,
    future=True,
    poolclass=NullPool,
)

TestAsyncSessionLocal = async_sessionmaker(
    bind=test_async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
async def clean_database():
    """Ensure clean database state before each test on isolated test database only."""
    # Fail-closed guard: ensure engine points strictly to a test database
    engine_db = (test_async_engine.url.database or "").lower()
    if not engine_db.endswith("_test") and "test" not in engine_db:
        raise RuntimeError(
            f"FATAL SAFETY INTERLOCK: clean_database refusing to run on non-test database '{engine_db}'!"
        )
    if engine_db in PROTECTED_DATABASE_NAMES:
        raise RuntimeError(
            f"FATAL SAFETY INTERLOCK: clean_database refusing to run on protected database '{engine_db}'!"
        )

    async with test_async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE email_accounts ADD COLUMN IF NOT EXISTS incoming_protocol VARCHAR(10) DEFAULT 'IMAP' NOT NULL;"))
        await conn.execute(text("ALTER TABLE email_attachments ADD COLUMN IF NOT EXISTS disposition VARCHAR(50) DEFAULT 'attachment' NOT NULL;"))
        await conn.execute(text("ALTER TABLE email_attachments ADD COLUMN IF NOT EXISTS content_id VARCHAR(255);"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_email_attachments_content_id ON email_attachments (content_id);"))
        await conn.execute(text("ALTER TABLE email_tracking_tokens ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR(64);"))
        await conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_email_tracking_tokens_idempotency_key ON email_tracking_tokens (idempotency_key);"))
        await conn.execute(text("ALTER TABLE email_tracking_events ALTER COLUMN is_bot DROP NOT NULL, ALTER COLUMN is_bot DROP DEFAULT;"))
        await conn.execute(text("ALTER TABLE email_tracking_events ADD COLUMN IF NOT EXISTS remote_event_id BIGINT;"))
        await conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_email_tracking_events_remote_event_id ON email_tracking_events (remote_event_id);"))
        await conn.execute(text("ALTER TABLE email_tracking_events ALTER COLUMN token_id DROP NOT NULL;"))
        await conn.execute(text("ALTER TABLE email_tracking_events ALTER COLUMN email_id DROP NOT NULL;"))
        for fk in [
            "email_tracking_tokens_company_id_fkey",
            "email_tracking_tokens_email_id_fkey",
            "email_tracking_tokens_campaign_id_fkey",
            "email_tracking_tokens_recipient_id_fkey",
            "email_tracking_tokens_delivery_id_fkey",
            "email_tracking_events_company_id_fkey",
            "email_tracking_events_email_id_fkey",
            "email_tracking_events_campaign_id_fkey",
            "email_tracking_events_recipient_id_fkey",
            "email_tracking_events_delivery_id_fkey",
        ]:
            await conn.execute(text(f"ALTER TABLE email_tracking_tokens DROP CONSTRAINT IF EXISTS {fk};"))
            await conn.execute(text(f"ALTER TABLE email_tracking_events DROP CONSTRAINT IF EXISTS {fk};"))
        await conn.execute(text("TRUNCATE TABLE users, companies, company_users, company_invitations, domains, email_accounts, email_account_access, emails, email_templates, email_signatures, email_attachments, campaigns, campaign_steps, campaign_recipients, campaign_deliveries, suppression_list, campaign_attachments, email_tracking_tokens, email_tracking_events, tracking_event_quarantine RESTART IDENTITY CASCADE;"))
    yield
    async with test_async_engine.begin() as conn:
        await conn.execute(text("TRUNCATE TABLE users, companies, company_users, company_invitations, domains, email_accounts, email_account_access, emails, email_templates, email_signatures, email_attachments, campaigns, campaign_steps, campaign_recipients, campaign_deliveries, suppression_list, campaign_attachments, email_tracking_tokens, email_tracking_events, tracking_event_quarantine RESTART IDENTITY CASCADE;"))
    await test_async_engine.dispose()


@pytest.fixture
def test_alembic_config() -> Config:
    """Provide an Alembic Config strictly and verifiably bound to the isolated test database."""
    alembic_ini_path = backend_dir / "alembic.ini"
    cfg = Config(str(alembic_ini_path))
    
    # Validate target URL immediately before configuring
    parsed = make_url(TEST_DATABASE_SYNC_URL)
    db_name = (parsed.database or "").lower()
    if db_name in PROTECTED_DATABASE_NAMES or (not db_name.endswith("_test") and "test" not in db_name):
        raise RuntimeError(
            f"FATAL SAFETY INTERLOCK: Refusing to create Alembic test config for unsafe database '{db_name}'."
        )

    cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_SYNC_URL)
    cfg.set_main_option("is_test_migration", "true")
    return cfg


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an active test database session."""
    async with TestAsyncSessionLocal() as session:
        yield session


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Test client configured with test database dependency overrides."""
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with TestAsyncSessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
async def clean_redis():
    """Ensure clean Redis state on isolated test database (DB 15) only.
    
    Guarantees fail-closed safety by verifying exclusive test ownership before cleanup.
    """
    validate_test_redis_url(settings.REDIS_URL)
    client = core_redis.get_redis_client()
    conn_db = client.connection_pool.connection_kwargs.get("db", 0)
    if conn_db != TEST_REDIS_DB or conn_db in PROTECTED_REDIS_DBS:
        raise RuntimeError(
            f"FATAL SAFETY INTERLOCK: Redis client connection is bound to DB {conn_db}, expected {TEST_REDIS_DB}!"
        )

    try:
        await client.flushdb()
    except Exception:
        pass

    yield client

    try:
        if client.connection_pool.connection_kwargs.get("db", 0) == TEST_REDIS_DB:
            await client.flushdb()
    except Exception:
        pass
    try:
        await client.aclose()
    except Exception:
        pass
    core_redis.redis_client = None


@pytest.fixture
def test_redis_client(clean_redis):
    """Provide the verified test Redis client bound strictly to DB 15."""
    return clean_redis

