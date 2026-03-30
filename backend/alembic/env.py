"""Alembic migration environment for TidePool.

Imports all ORM models so that autogenerate can detect schema changes,
and configures the sync database URL derived from the async app config.
"""

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# ---------------------------------------------------------------------------
# Ensure the backend package is importable when running alembic from the
# backend/ directory (e.g. ``alembic upgrade head``).
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# ---------------------------------------------------------------------------
# Import all models so Base.metadata contains every table.
# ---------------------------------------------------------------------------
from app.database import Base  # noqa: E402

# Core models (triggers relationship resolution across all modules)
from app.models import (  # noqa: E402, F401
    User,
    ApiKey,
    Campaign,
    AddressBook,
    Contact,
    Group,
    GroupMember,
    EmailTemplate,
    LandingPage,
    SmtpProfile,
    CampaignRecipient,
    TrackingEvent,
    AuditLog,
    ReportSnapshot,
)
from app.training.models import TrainingRedirect  # noqa: E402, F401
from app.models.api_key import ApiKey  # noqa: E402, F401

# ---------------------------------------------------------------------------
# Alembic Config object -- provides access to values in alembic.ini.
# ---------------------------------------------------------------------------
config = context.config

# Set up Python logging from the ini file.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata for 'autogenerate' support.
target_metadata = Base.metadata

# ---------------------------------------------------------------------------
# Build a synchronous database URL from the async app config.
# Alembic runs migrations synchronously, so we swap asyncpg -> psycopg2.
# ---------------------------------------------------------------------------
from app.config import settings  # noqa: E402

sync_url = settings.DATABASE_URL.replace("+asyncpg", "+psycopg2")
config.set_main_option("sqlalchemy.url", sync_url)


# ---------------------------------------------------------------------------
# Offline and online migration runners.
# ---------------------------------------------------------------------------

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Generates SQL scripts without connecting to the database. Useful for
    producing migration SQL to apply manually in controlled environments.
    """
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
    """Run migrations in 'online' mode.

    Creates a synchronous engine and runs migrations inside a transaction.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
