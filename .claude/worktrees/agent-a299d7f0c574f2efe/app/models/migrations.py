"""Graceful, best-effort DB migration runner for application startup.

Live prod builds its schema with ``create_all()`` (see app.models.base). This module
keeps the Alembic version history CONSISTENT on boot WITHOUT ever breaking that:

  - Fresh / create_all-built DB with no ``alembic_version``  -> STAMP head (mark the
    current schema as up-to-date; do NOT try to re-create existing tables).
  - DB already under Alembic control                         -> UPGRADE head (apply any
    new migrations; migration 005 is idempotent so it's safe either way).
  - Truly empty DB                                           -> UPGRADE from base.

NEVER raises — a migration hiccup must not stop the app from booting. Disable entirely
with ``SKIP_DB_MIGRATIONS=1``.
"""

from __future__ import annotations

import os

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def _flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _sync_url() -> str:
    """SYNC SQLAlchemy URL (settings -> env -> sqlite default), async drivers normalised."""
    url = ""
    try:
        from app.config import settings

        url = (getattr(settings, "database_url", "") or "").strip()
    except Exception:
        url = ""
    url = url or os.environ.get("DATABASE_URL", "").strip() or "sqlite:///./leadgen.db"
    url = url.replace("+aiosqlite", "").replace("+asyncpg", "").replace("+aiomysql", "")
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


def _alembic_cfg():
    """Build an Alembic Config pointed at the repo's alembic.ini + versions dir."""
    from alembic.config import Config

    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ini = os.path.join(repo_root, "alembic.ini")
    script_dir = os.path.join(repo_root, "alembic")
    cfg = Config(ini if os.path.exists(ini) else None)
    cfg.set_main_option("script_location", script_dir)
    cfg.set_main_option("sqlalchemy.url", _sync_url())
    return cfg


def run_startup_migrations() -> dict:
    """Best-effort: keep the Alembic version consistent on boot. NEVER raises."""
    if _flag("SKIP_DB_MIGRATIONS"):
        return {"skipped": "SKIP_DB_MIGRATIONS"}
    try:
        from alembic.runtime.migration import MigrationContext
        from sqlalchemy import create_engine, inspect

        from alembic import command

        engine = create_engine(_sync_url())
        try:
            with engine.connect() as conn:
                current = MigrationContext.configure(conn).get_current_revision()
                has_tables = bool(inspect(conn).get_table_names())
        finally:
            engine.dispose()

        cfg = _alembic_cfg()
        if current is None:
            if has_tables:
                # Schema already built by create_all() -> just record where we are.
                command.stamp(cfg, "head")
                return {"action": "stamped_head"}
            # Empty DB -> build the whole schema via migrations.
            command.upgrade(cfg, "head")
            return {"action": "upgraded_from_empty"}
        # Already version-controlled -> apply anything new (idempotent migrations).
        command.upgrade(cfg, "head")
        return {"action": "upgraded", "from": current}
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"startup migrations skipped (non-fatal): {e}")
        return {"error": str(e)}


__all__ = ["run_startup_migrations"]
