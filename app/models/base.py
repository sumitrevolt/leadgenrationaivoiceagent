"""
Database Base Configuration
Production-ready with async support
"""
from contextlib import contextmanager, asynccontextmanager
from typing import AsyncGenerator, Generator, Optional

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
            sync_url = settings.database_url.replace("+asyncpg", "").replace("postgresql://", "postgresql+psycopg2://")
            
            _engine = create_engine(
                sync_url,
                pool_size=10,
                max_overflow=20,
                pool_pre_ping=True,
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
            from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

            # Normalize DATABASE_URL to an ASYNC driver URL.
            url = settings.database_url
            if url.startswith("sqlite") and "+aiosqlite" not in url:
                url = url.replace("sqlite+pysqlite://", "sqlite://").replace("sqlite://", "sqlite+aiosqlite://")
            elif url.startswith("postgresql") and "+asyncpg" not in url:
                url = url.replace("postgresql+psycopg2://", "postgresql://").replace("postgresql://", "postgresql+asyncpg://")

            kwargs = dict(pool_pre_ping=True, echo=settings.debug)
            # SQLite does not support pool_size/max_overflow.
            if not url.startswith("sqlite"):
                kwargs.update(pool_size=20, max_overflow=30)

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


async def init_async_db():
    """Initialize database tables (async)"""
    engine = _get_async_engine()
    if engine:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("? Database tables created (async)")


async def close_async_db():
    """Close async database connections"""
    global _async_engine
    if _async_engine:
        await _async_engine.dispose()
        _async_engine = None
        logger.info("? Async database connection closed")
