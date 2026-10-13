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
        await conn.execute(text("TRUNCATE TABLE users, companies, company_users, company_invitations, domains, email_accounts, email_account_access, emails, email_templates, email_signatures, email_attachments, campaigns, campaign_recipients, campaign_deliveries, suppression_list, campaign_attachments RESTART IDENTITY CASCADE;"))
    yield
    async with test_async_engine.begin() as conn:
        await conn.execute(text("TRUNCATE TABLE users, companies, company_users, company_invitations, domains, email_accounts, email_account_access, emails, email_templates, email_signatures, email_attachments, campaigns, campaign_recipients, campaign_deliveries, suppression_list, campaign_attachments RESTART IDENTITY CASCADE;"))
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
