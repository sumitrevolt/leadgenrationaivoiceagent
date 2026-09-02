"""
Alembic Migrations Environment
LeadGen AI Voice Agent

Migrations run on a SYNCHRONOUS engine (works for BOTH SQLite — the default app DB —
and Postgres). The async pool in app.models.base is for the running app; one-shot
migrations don't need it and a sync engine avoids the aiosqlite/asyncpg driver dance.

`target_metadata` is the FULL app model set: importing the `app.models` package
registers EVERY table on `Base.metadata` (leads, clients, campaigns, users, payments,
billing_records, agents, agent_events, data_credits, ...) — single source of truth, no
hand-maintained per-model import list to drift out of sync.
"""

from logging.config import fileConfig

from sqlalchemy import create_engine, pool

# Importing the package registers every model on Base.metadata.
import app.models  # noqa: F401  (side-effect import — registers all tables)
from alembic import context
from app.models.base import Base

# Alembic Config object (values from alembic.ini).
config = context.config

# Python logging from the ini (best-effort — never block migrations on a logging hiccup).
# disable_existing_loggers=False is REQUIRED: env.py is imported in-process by
# run_startup_migrations() during the app lifespan, and fileConfig defaults to
# disable_existing_loggers=True (the default) - which sets logger.disabled=True on EVERY app
# logger that already exists (e.g. app.integrations.email_sender), silencing them
# process-wide for the rest of that process. That is an application-lifecycle bug
# (startup migrations silently killed app logging) and the direct cause of the
# order-dependent email/log test failures. Alembic only needs to configure its
# own loggers here, not clobber the application's.
if config.config_file_name is not None:
    try:
        fileConfig(config.config_file_name, disable_existing_loggers=False)
    except Exception:
        pass

target_metadata = Base.metadata


def _sync_url() -> str:
    """Resolve a SYNC SQLAlchemy URL for migrations (settings -> env -> sqlite default)."""
    import os

    url = ""
    try:
        from app.config import settings

        url = (getattr(settings, "database_url", "") or "").strip()
    except Exception:
        url = ""
    url = url or os.environ.get("DATABASE_URL", "").strip() or "sqlite:///./leadgen.db"
    # Normalise async drivers to their sync counterparts for the migration engine.
    url = url.replace("+aiosqlite", "").replace("+asyncpg", "").replace("+aiomysql", "")
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL, no DBAPI needed)."""
    context.configure(
        url=_sync_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode against a sync engine (batch mode on SQLite)."""
    connectable = create_engine(_sync_url(), poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            # SQLite can't ALTER most things in place — batch mode rewrites tables.
            render_as_batch=connection.dialect.name == "sqlite",
        )
        with context.begin_transaction():
            context.run_migrations()
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
