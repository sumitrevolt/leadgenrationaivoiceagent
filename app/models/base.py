"""
Database Base Configuration
Production-ready with async support
"""

from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager

from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session

from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# =============================================================================
# BASE CLASS (Always available)
# =============================================================================

Base = declarative_base()

# =============================================================================
# LAZY ENGINE INITIALIZATION
# =============================================================================

_engine = None
_async_engine = None
_SessionLocal = None
_async_session = None


def _get_sync_engine():
    """Lazy initialization of sync engine"""
    global _engine, _SessionLocal

    if _engine is None:
        try:
            from sqlalchemy import create_engine
            from sqlalchemy.orm import sessionmaker

            # Convert async URL to sync for migrations
            sync_url = settings.database_url.replace("+asyncpg", "").replace(
                "postgresql://", "postgresql+psycopg2://"
            )
            # For SQLite, convert async driver to sync driver
            if sync_url.startswith("sqlite+aiosqlite://"):
                sync_url = sync_url.replace("sqlite+aiosqlite://", "sqlite://")
            elif sync_url.startswith("sqlite+pysqlite://"):
                sync_url = sync_url.replace("sqlite+pysqlite://", "sqlite://")
            # Ensure relative paths are resolved to absolute
            if sync_url.startswith("sqlite:///"):
                import os
                rel_path = sync_url[len("sqlite:///"):]
                if rel_path.startswith("/"):
                    rel_path = rel_path[1:]
                abs_path = os.path.abspath(rel_path)
                sync_url = f"sqlite:///{abs_path}"

            # Sync engine = migrations + occasional background sync only (rarely
            # concurrent) → small pool. Shares the same PgBouncer/PG budget as the
            # async engine (audit P1-2).
            _engine = create_engine(
                sync_url,
                pool_size=3,
                max_overflow=2,
                pool_pre_ping=True,
                pool_recycle=1800,
                pool_timeout=10,
                echo=settings.debug,
            )
            _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
            logger.info("? Sync database engine initialized")
        except Exception as e:
            logger.warning(f"Could not initialize sync engine: {e}")
            return None

    return _engine


def _get_async_engine():
    """Lazy initialization of async engine"""
    global _async_engine, _async_session

    if _async_engine is None:
        try:
            from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

            # Normalize DATABASE_URL to an ASYNC driver URL.
            url = settings.database_url
            if url.startswith("sqlite") and "+aiosqlite" not in url:
                url = url.replace("sqlite+pysqlite://", "sqlite://").replace(
                    "sqlite://", "sqlite+aiosqlite://"
                )
            elif url.startswith("postgresql") and "+asyncpg" not in url:
                url = url.replace("postgresql+psycopg2://", "postgresql://").replace(
                    "postgresql://", "postgresql+asyncpg://"
                )

            kwargs = {"pool_pre_ping": True, "echo": settings.debug}
            # SQLite does not support pool_size/max_overflow.
            if not url.startswith("sqlite"):
                # Right-sized for PgBouncer session-mode (DEFAULT_POOL_SIZE=25) +
                # Postgres max_connections=100 across ALL processes: 2 web + worker +
                # worker-heavy ≈ 4 engines × pool_size 5 = 20 baseline ≤ 25. Session
                # mode me held client-conn ≈ server-conn, isliye bada pool ulta
                # contention/queueing deta tha (audit P1-2). recycle = PgBouncer/PG
                # idle-close se aayi stale conn pre-empt; timeout = exhaust pe 30s
                # hang ki jagah 10s me fail-fast (request stall na ho).
                kwargs.update(pool_size=5, max_overflow=5, pool_recycle=1800, pool_timeout=10)

            _async_engine = create_async_engine(url, **kwargs)
            _async_session = async_sessionmaker(
                _async_engine,
                class_=AsyncSession,
                expire_on_commit=False,
                autoflush=False,
            )
            logger.info(f"✅ Async database engine initialized ({url.split('://')[0]})")
        except Exception as e:
            logger.warning(f"Could not initialize async engine: {e}")
            return None

    return _async_engine


# Properties for backward compatibility
@property
def engine():
    return _get_sync_engine()


@property
def async_engine():
    return _get_async_engine()


def async_session():
    """Get async session factory"""
    _get_async_engine()
    return _async_session


# =============================================================================
# SYNC DATABASE DEPENDENCIES
# =============================================================================


def get_db() -> Generator[Session, None, None]:
    """
    Sync database session dependency
    Use as dependency in FastAPI routes for sync operations
    """
    _get_sync_engine()
    if _SessionLocal is None:
        raise RuntimeError("Database not configured")

    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """
    Context manager for sync database sessions
    Use in background tasks
    """
    _get_sync_engine()
    if _SessionLocal is None:
        raise RuntimeError("Database not configured")

    db = _SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# =============================================================================
# ASYNC DATABASE DEPENDENCIES
# =============================================================================


async def get_async_db() -> AsyncGenerator:
    """
    Async database session dependency
    Use as dependency in FastAPI routes
    """
    session_factory = async_session()
    if session_factory is None:
        raise RuntimeError("Async database not configured")

    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_async_session() -> AsyncGenerator:
    """
    Async context manager for database sessions
    Use in background async tasks
    """
    session_factory = async_session()
    if session_factory is None:
        raise RuntimeError("Async database not configured")

    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# =============================================================================
# INITIALIZATION
# =============================================================================


def init_db():
    """Initialize database tables (sync)"""
    engine = _get_sync_engine()
    if engine:
        Base.metadata.create_all(bind=engine)
        logger.info("? Database tables created (sync)")


def _apply_schema_upgrades(sync_conn) -> None:
    """
    Lightweight, idempotent in-place migrations for columns added after the
    first release. create_all() only creates NEW tables — existing tables
    need explicit ALTERs. Safe on SQLite and Postgres.
    """
    from sqlalchemy import inspect, text

    # All three components (table, column, DDL) are hardcoded literals —
    # none come from user input or runtime variables, so there is no
    # injection surface. The allowlist check below is an additional guard
    # against any future code path that might add dynamic entries (CWE-89).
    _UPGRADES: dict[str, list[tuple[str, str]]] = {
        "agents": [("role", "VARCHAR(20) DEFAULT 'leads'")],
        "automation_logs": [("evidence_url", "VARCHAR(500)")],
    }
    _SAFE_TABLES: frozenset[str] = frozenset(_UPGRADES.keys())
    _SAFE_COLS: frozenset[str] = frozenset(col for cols in _UPGRADES.values() for col, _ in cols)
    # DDL type strings are also allowlisted — only these exact strings may
    # appear in an ALTER TABLE statement; no user-controlled data ever reaches here.
    _SAFE_DDL: frozenset[str] = frozenset(ddl for cols in _UPGRADES.values() for _, ddl in cols)

    inspector = inspect(sync_conn)
    for table, cols in _UPGRADES.items():
        if table not in _SAFE_TABLES:
            logger.warning("Schema upgrade: unknown table %r skipped", table)
            continue
        try:
            if table not in inspector.get_table_names():
                continue
            existing = {c["name"] for c in inspector.get_columns(table)}
            for col, ddl in cols:
                if col not in _SAFE_COLS:
                    logger.warning("Schema upgrade: unknown column %r skipped", col)
                    continue
                if ddl not in _SAFE_DDL:
                    logger.warning("Schema upgrade: unknown DDL %r skipped", ddl)
                    continue
                if col not in existing:
                    # table, col, and ddl are all validated against hardcoded
                    # frozensets above — no user-controlled data can reach here.
                    # Identifiers are also double-quoted for defence-in-depth.
                    stmt = text(f'ALTER TABLE "{table}" ADD COLUMN "{col}" {ddl}')
                    sync_conn.execute(stmt)
                    logger.info("Schema upgrade: %s.%s added", table, col)
        except Exception as e:
            logger.warning("Schema upgrade check failed for %s: %s", table, e)


async def init_async_db():
    """Initialize database tables (async).

    DB_CREATE_ALL (default "1" = aaj jaisa behaviour) — boot pe create_all +
    idempotent column-ALTERs. Alembic-only cutover ke liye (audit P2): pehle
    migrations live DB ke against verify karo (`alembic upgrade head` clean), FIR
    `DB_CREATE_ALL=0` set karo — tab schema purely Alembic-managed. Default ON
    rakha kyunki blind flip = missing-table/column risk (isliye opt-in, deliberate).
    """
    import os as _os

    if _os.environ.get("DB_CREATE_ALL", "1").strip().lower() not in ("1", "true", "yes"):
        logger.info("DB_CREATE_ALL=0 — create_all skipped (Alembic-only schema mode)")
        return
    engine = _get_async_engine()
    if engine:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(_apply_schema_upgrades)
        logger.info("? Database tables created (async)")


async def close_async_db():
    """Close async database connections"""
    global _async_engine
    if _async_engine:
        await _async_engine.dispose()
        _async_engine = None
        logger.info("? Async database connection closed")
