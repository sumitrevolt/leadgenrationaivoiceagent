"""
Test Configuration
Production-ready test fixtures with proper async handling
"""

import asyncio
import os

# TESTS ME AUTOMATION HAMESHA OFF (app.main import se PEHLE set karna zaroori):
# TestClient(app) startup pe in-process team_scheduler chal jaata tha aur fresh
# checkout (CI) pe growth-pulse job REAL OSM/Places scraping karne lagta —
# urllib timeout=25 ke loops me poora pytest hang (CI runs #1-#9 lesson, 2026-06-11).
os.environ.setdefault("RUN_IN_PROCESS_SCHEDULER", "0")
os.environ.setdefault("TEAM_AUTOMATION", "0")
# TestClient startup (lifespan) KB embedder pre-warm trigger karta — tests me heavy
# fastembed load (8s+) background task = slow/interfere. Tests me OFF.
os.environ.setdefault("KB_PREWARM", "0")
# FULL-SUITE HANG FIX: prod "redis://redis:6379" hostname test-env me DNS-resolve
# NAHI hota -> get_redis_client connect DNS pe HANG (test_agent_stack rate-limit dep
# pe atak jata tha). Redis ko localhost-REFUSE pe point karo: instant ConnectionRefused
# (no DNS, no hang) -> in-memory fallback. Qdrant off -> embedder load skip (keyword KB).
# Dono ka graceful fallback hai = zero test-behaviour change, sirf hang khatam.
os.environ["REDIS_URL"] = "redis://127.0.0.1:6399/0"
os.environ.setdefault("QDRANT_URL", "")

# SAFETY NET: koi bhi test agar galti se asli network (LLM/Exotel/Maps/Redis) hit
# kare to wo HANG na ho — har raw socket op max 10s me fail ho jaye. pytest-timeout
# ka thread-method blocking socket ko interrupt nahi kar pata (Windows pe signal-
# method bhi nahi hai), isliye poora suite kabhi-kabhi infinite hang ho jata tha.
# TestClient ASGI in-process hai (socket nahi) → isse unaffected; sirf real network
# bounded hota hai. (test_growth_engine self-heal auto_content branch lesson, 2026-06-13.)
import socket as _socket

_socket.setdefaulttimeout(10)

# NETWORK GUARD (OPT-IN, default OFF): blocks external sockets so a COLD single
# test/file doesn't hang on embedder/LLM downloads. Allows localhost/127.0.0.1/::1
# (SQLite, in-process TestClient).
# ⚠️ DEFAULT OFF kyun: aggressive raise se kuch code (fastembed/httpx) infinite-RETRY
# loop me chala jaata hai → poora full-suite 9% pe HANG ho gaya (2026-06-13 lesson).
# Bina guard ke full suite `socket.setdefaulttimeout(10)` se slow-but-COMPLETE hota hai.
# Cold single-file run ke liye chahiye to: set PYTEST_NETGUARD=1.
if os.environ.get("PYTEST_NETGUARD", "0").strip().lower() in ("1", "true", "yes"):
    try:
        from tests._netguard import enable as _netguard_enable

        _netguard_enable()
    except Exception as _ng_exc:
        import warnings as _warnings

        _warnings.warn(
            f"[conftest] netguard could not be enabled: {_ng_exc!r}.",
            RuntimeWarning,
        )

# Use SQLite for tests (fast, no external dependencies)
# DB lives in the OS temp dir — avoids polluting the repo and works on
# network/mounted filesystems where SQLite locking can fail with disk I/O errors.
import tempfile
from collections.abc import AsyncGenerator, Generator
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.api.auth_deps import (
    get_current_user,
    require_admin,
    require_agent,
    require_manager,
    require_super_admin,
)
from app.main import app

# =============================================================================
# LLM STUB (tests) — free_ai.chat/transcribe REAL httpx calls karte the jo offline/
# slow free-providers (groq TPD, gemini quota, openrouter 404) pe HANG karte the
# (test_multilang/carousel/meme/2026 etc. — full-suite ~9-13% pe atak jata). Yahan
# global module-attr stub: saare callers (free_ai.chat) instant canned reply paate.
# Real LLM kabhi test me NAHI chahiye — content fns ka template/structure phir bhi
# banta. Ek jagah fix = saari LLM-content tests fast + zero network hang.
# =============================================================================
try:
    from app.voice_agent import free_ai as _free_ai_mod

    async def _stub_llm_chat(system, messages, max_tokens=90, temperature=0.6):
        return ("Theek hai sir, samajh gayi — aap boliye.", "stub")

    async def _stub_transcribe(*_a, **_k):
        return ""

    _free_ai_mod.chat = _stub_llm_chat
    _free_ai_mod.transcribe_audio = _stub_transcribe
except Exception:
    pass
from app.models.base import Base, get_async_db, get_db
from app.models.user import User, UserRole, UserStatus

# =============================================================================
# TEST DATABASE CONFIGURATION
# =============================================================================


_TEST_DB_PATH = os.path.join(tempfile.gettempdir(), "leadgen_test.db")
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", f"sqlite:///{_TEST_DB_PATH}")
TEST_ASYNC_DATABASE_URL = TEST_DATABASE_URL.replace("sqlite:///", "sqlite+aiosqlite:///")

# Sync engine for test setup
engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Async engine for async tests
async_engine = create_async_engine(
    TEST_ASYNC_DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)
AsyncTestingSessionLocal = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


# =============================================================================
# DEPENDENCY OVERRIDES
# =============================================================================


def override_get_db():
    """Override database dependency for testing"""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


async def override_get_async_db() -> AsyncGenerator:
    """Override async database dependency for testing"""
    async with AsyncTestingSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def create_mock_user(
    user_id: str = "test-user-id",
    email: str = "test@example.com",
    role: UserRole = UserRole.SUPER_ADMIN,
) -> User:
    """Create a mock user with specified attributes"""
    user = User(
        id=user_id,
        email=email,
        first_name="Test",
        last_name="User",
        role=role,
        status=UserStatus.ACTIVE,
        password_hash="$2b$12$mockhash",  # bcrypt format
        password_salt="",
        is_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    return user


def get_mock_user():
    """Return a mock authenticated user for tests (sync)"""
    return create_mock_user()


async def get_mock_user_async():
    """Return a mock authenticated user for tests (async)"""
    return create_mock_user()


# Apply dependency overrides
app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[get_async_db] = override_get_async_db
app.dependency_overrides[get_current_user] = get_mock_user
app.dependency_overrides[require_agent] = get_mock_user
app.dependency_overrides[require_manager] = get_mock_user
app.dependency_overrides[require_admin] = get_mock_user
app.dependency_overrides[require_super_admin] = get_mock_user


# =============================================================================
# EVENT LOOP CONFIGURATION
# =============================================================================


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests (session-scoped for performance)"""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# =============================================================================
# DATABASE FIXTURES
# =============================================================================


@pytest.fixture(scope="function")
def db():
    """Create test database tables (function-scoped for isolation)"""
    # Create all tables
    Base.metadata.create_all(bind=engine)
    yield
    # Drop all tables after test
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
async def async_db():
    """Create test database tables for async tests"""
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture(scope="function")
def db_session(db) -> Generator:
    """Get a database session for direct database operations"""
    session = TestingSessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@pytest.fixture(scope="function")
async def async_db_session(async_db) -> AsyncGenerator:
    """Get an async database session"""
    async with AsyncTestingSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# =============================================================================
# CLIENT FIXTURES
# =============================================================================


@pytest.fixture(scope="function")
def client(db) -> Generator:
    """Create test client (sync)"""
    from httpx import ASGITransport
    from starlette.testclient import TestClient as StarletteTestClient

    # Use ASGITransport for newer httpx versions
    try:
        with TestClient(app) as c:
            yield c
    except TypeError:
        # Fallback for httpx >= 0.28
        transport = ASGITransport(app=app)
        with StarletteTestClient(app, transport=transport) as c:
            yield c


@pytest.fixture(scope="function")
async def async_client(async_db):
    """Create async test client"""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# =============================================================================
# SAMPLE DATA FIXTURES
# =============================================================================


@pytest.fixture
def sample_lead() -> dict:
    """Sample lead data"""
    return {
        "company_name": "Test Company Pvt Ltd",
        "contact_name": "Rahul Sharma",
        "phone": "+919876543210",
        "email": "rahul@testcompany.com",
        "city": "Mumbai",
        "category": "Real Estate",
        "source": "manual",
        "notes": "Test lead for unit testing",
    }


@pytest.fixture
def sample_campaign() -> dict:
    """Sample campaign data"""
    return {
        "name": "Test Campaign Q1",
        "niche": "real_estate",
        "client_name": "Test Client Corp",
        "client_service": "Property Sales",
        "target_cities": ["Mumbai", "Delhi", "Bangalore"],
        "target_lead_count": 100,
        "daily_call_limit": 50,
        "working_hours_start": "09:00",
        "working_hours_end": "18:00",
    }


@pytest.fixture
def sample_user() -> dict:
    """Sample user data for registration tests"""
    return {
        "email": "newuser@example.com",
        "password": "SecurePass123!",
        "first_name": "New",
        "last_name": "User",
    }


@pytest.fixture
def auth_headers() -> dict:
    """Sample authentication headers"""
    return {
        "Authorization": "Bearer test-token",
        "Content-Type": "application/json",
    }


# =============================================================================
# MOCK FIXTURES
# =============================================================================


@pytest.fixture
def mock_redis(mocker):
    """Mock Redis client for tests"""
    mock = mocker.patch("app.cache.get_redis_client")
    mock_client = mocker.AsyncMock()
    mock.return_value = mock_client
    return mock_client


@pytest.fixture
def mock_llm(mocker):
    """Mock LLM Brain for tests"""
    mock = mocker.patch("app.voice_agent.llm_brain.LLMBrain")
    mock_instance = mocker.AsyncMock()
    mock.return_value = mock_instance
    mock_instance.generate_opening.return_value = "Hello! How can I help you today?"
    mock_instance.generate_response.return_value = "Thank you for your interest."
    return mock_instance


# =============================================================================
# CLEANUP
# =============================================================================


@pytest.fixture(autouse=True)
def cleanup_test_files():
    """Clean up test files after each test"""
    yield
    # Clean up test database file if it exists
    test_db_path = "./test.db"
    if os.path.exists(test_db_path):
        try:
            os.remove(test_db_path)
        except PermissionError:
            pass  # File might still be in use


@pytest.fixture(scope="session", autouse=True)
def netguard_session():
    """
    Session-scoped fixture that ensures the network guard stays active for
    the whole test run.  The guard is also installed at import time above,
    but this fixture re-enables it after any potential disable() call and
    provides a clean disable on teardown (useful when running a single test
    interactively where you want real network after the session).
    """
    try:
        from tests._netguard import disable as _ng_disable
        from tests._netguard import enable as _ng_enable

        _ng_enable()  # idempotent if already active
        yield
        _ng_disable()  # restore originals so pytest's own cleanup can work
    except Exception:
        yield  # never block pytest teardown
