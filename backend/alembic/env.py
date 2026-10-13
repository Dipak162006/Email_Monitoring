import os
import sys
from logging.config import fileConfig
from pathlib import Path
from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import make_url

# Ensure backend root is on sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.core.config import settings
from app.core.database import Base
import app.modules.auth.models  # noqa: F401 - ensure models are registered
import app.modules.companies.models  # noqa: F401 - ensure models are registered
import app.modules.email_accounts.models  # noqa: F401 - ensure models are registered
import app.modules.emails.models  # noqa: F401 - ensure models are registered
import app.modules.domains.models  # noqa: F401 - ensure models are registered
import app.modules.campaigns.models  # noqa: F401 - ensure models are registered

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

PROTECTED_DATABASE_NAMES = {
    "email_monitoring",
    "production",
    "prod",
    "postgres",
    "default",
}


def validate_migration_safety(url_str: str) -> None:
    """Fail-closed safety check that rejects migration operations on protected or non-test databases during test runs."""
    is_pytest = bool(os.environ.get("PYTEST_CURRENT_TEST"))
    is_test_migration = (config.get_main_option("is_test_migration") or "").lower() == "true"

    if is_pytest or is_test_migration:
        if not url_str:
            raise RuntimeError(
                "FATAL SAFETY INTERLOCK: Refusing to run migrations during test execution because no target database URL was provided."
            )

        parsed = make_url(url_str)
        db_name = (parsed.database or "").lower()

        if not db_name:
            raise RuntimeError(
                "FATAL SAFETY INTERLOCK: Migration target URL has no database specified during test execution."
            )

        if db_name in PROTECTED_DATABASE_NAMES:
            raise RuntimeError(
                f"FATAL SAFETY INTERLOCK: Migration target '{db_name}' is a protected development/production database! "
                f"Refusing to execute migrations during test execution."
            )

        if not db_name.endswith("_test") and "test" not in db_name:
            raise RuntimeError(
                f"FATAL SAFETY INTERLOCK: Refusing to run migrations during test execution on non-test database '{db_name}'. "
                f"Migrations executed during tests must target a dedicated test database ending with '_test'."
            )


# Preserve explicit test URL if set (e.g. by isolated test runner); otherwise default to settings.DATABASE_SYNC_URL
explicit_url = config.get_main_option("sqlalchemy.url")
if explicit_url is None:
    target_url = settings.DATABASE_SYNC_URL
    config.set_main_option("sqlalchemy.url", target_url)
else:
    target_url = explicit_url

# Validate target database before executing any migration operations
validate_migration_safety(target_url)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    try:
        with connectable.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
            )

            with context.begin_transaction():
                context.run_migrations()
    finally:
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
