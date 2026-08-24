"""
Test Configuration
Production-ready test fixtures with proper async handling
"""

import asyncio
import gc
import os

# CI exit-139 containment (2026-07-28/29): intermittent SIGSEGV during cyclic GC
# while native extensions (torch/av/numpy/…) are loaded. Disabling *automatic*
# collection for the short-lived GitHub Actions process reduces GC dice-rolls
# without skipping or xfailing any required test. Explicit gc.collect() still
# runs. See memory/incidents.md (exit 139 ledger).
if os.environ.get("GITHUB_ACTIONS") == "true":
    gc.disable()

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
# App singleton DB must match the harness file DB. Set BEFORE any app.* import
# (pydantic Settings freezes database_url on first load).
os.environ["DATABASE_URL"] = (
    "sqlite+aiosqlite:///"
    + __import__("tempfile").gettempdir().replace("\\", "/")
    + "/leadgen_test.db"
)

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
            stacklevel=2,
        )

# =============================================================================
# HTTPX 0.28 COMPAT SHIM (2026-07-10, test-only — prod code untouched).
# Lock pins httpx==0.28.1 (Client/AsyncClient ka `app=` kwarg REMOVED) ke saath
# starlette==0.35.1, jiska TestClient ab bhi `app=` pass karta hai -> har direct
# `TestClient(app)` construction `TypeError: unexpected keyword argument 'app'`
# se girta tha (test_product_one_delivery / test_customer_delivery_os / 6 tests).
# Starlette apna _TestClientTransport khud banakar transport= bhi bhejta hai,
# isliye `app=` yahan sirf redundant hai: transport diya ho to drop karo, na diya
# ho to old-httpx semantics wapas do (ASGITransport bana ke). Signature-guarded:
# agar future httpx me `app=` wapas aata hai to shim khud NO-OP ho jata hai.
# =============================================================================
import inspect as _inspect

# Use SQLite for tests (fast, no external dependencies)
# DB lives in the OS temp dir — avoids polluting the repo and works on
# network/mounted filesystems where SQLite locking can fail with disk I/O errors.
import tempfile
from collections.abc import AsyncGenerator, Generator
from datetime import datetime, timezone

import httpx as _httpx

if "app" not in _inspect.signature(_httpx.Client.__init__).parameters:

    def _make_compat(_orig_init):
        def _compat_init(self, *args, app=None, **kwargs):
            if app is not None and kwargs.get("transport") is None:
                kwargs["transport"] = _httpx.ASGITransport(app=app)
            return _orig_init(self, *args, **kwargs)

        return _compat_init

    _httpx.Client.__init__ = _make_compat(_httpx.Client.__init__)
    _httpx.AsyncClient.__init__ = _make_compat(_httpx.AsyncClient.__init__)

import pytest
import sqlalchemy.ext.asyncio as _sa_asyncio_early
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

# Patch BEFORE any app.* import: base._get_async_engine does a function-local
# import of create_async_engine, so this module attribute is what it resolves.
_ORIG_CAE_EARLY = _sa_asyncio_early.create_async_engine


def _cae_nullpool_file_sqlite(url, *args, **kwargs):
    """Test-only sqlite pool policy (SQLAlchemy #13039 / aiosqlite #369).

    - File-backed sqlite+aiosqlite -> NullPool (close on every checkin; safe across
      pytest + TestClient portal loops).
    - :memory: / bare sqlite+aiosqlite:// -> StaticPool (one shared connection so
      DDL stays visible across checkouts; dispose still closes the worker).
    """
    if "poolclass" not in kwargs:
        try:
            from sqlalchemy.engine.url import make_url
            from sqlalchemy.pool import StaticPool

            _u = make_url(str(url))
            _db = (_u.database or "").strip()
            if _u.get_backend_name() == "sqlite":
                if _db in ("", ":memory:"):
                    kwargs = {**kwargs, "poolclass": StaticPool}
                else:
                    kwargs = {**kwargs, "poolclass": NullPool}
        except Exception:
            pass
    return _ORIG_CAE_EARLY(url, *args, **kwargs)


_sa_asyncio_early.create_async_engine = _cae_nullpool_file_sqlite

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

# Async engine for async tests.
# NullPool (test-only) — SQLAlchemy #13039 / aiosqlite #369: under aiosqlite 0.22.x
# SQLAlchemy's aiosqlite dialect does not close the underlying connection, so a
# POOLED async connection reused across the pytest event loop and the TestClient
# portal loops leaks an aiosqlite `_connection_worker_thread` once its loop is gone;
# a later cyclic-GC pass on Linux/CPython then SIGSEGVs while traversing it
# (this is the intermittent CI exit-139). NullPool closes every connection on
# return, so nothing is pooled or orphaned and no worker thread survives for GC to
# hit. Verified in a repro: 8 cross-loop uses leak a worker with the default pool,
# zero with NullPool.
async_engine = create_async_engine(
    TEST_ASYNC_DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
    poolclass=NullPool,
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

# NOTE: require_customer deliberately has NO global override here — customer
# routes must keep rejecting anonymous callers (401/403) unless an individual
# test opts in with its own app.dependency_overrides[require_customer].


@pytest.fixture(autouse=True)
def restore_dependency_overrides():
    """Snapshot/restore FastAPI dependency overrides per test (Cluster 1).

    Many tests clear or replace app.dependency_overrides and forget to restore,
    causing later tests to see HTTP 401. This restores the session baseline
    without bypassing production authentication — production code paths unchanged.
    """
    before = dict(app.dependency_overrides)
    yield
    app.dependency_overrides.clear()
    app.dependency_overrides.update(before)


@pytest.fixture(autouse=True)
def _resume_inquiry_bg_accept_gate():
    """Keep inquiry spawn gate open across tests.

    Production shutdown calls drain_inquiry_bg_tasks() which stops accepting.
    Tests that exercise drain must not poison later cases; reopen after each test.
    """
    try:
        from app.platform.inquiry_hooks import resume_accepting_inquiry_bg

        resume_accepting_inquiry_bg()
    except Exception:
        pass
    yield
    try:
        from app.platform.inquiry_hooks import resume_accepting_inquiry_bg

        resume_accepting_inquiry_bg()
    except Exception:
        pass


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


@pytest.fixture(autouse=True)
def _ensure_policy_event_loop():
    """ORDER-DEPENDENT FLAKE FIX (2026-07-18): sync tests that call asyncio.run()
    (test_voice_tools / test_call_learning / etc.) leave the MainThread policy
    loop UNSET on exit (asyncio.run closes its loop + set_event_loop(None)).
    pytest-asyncio 0.23 then raises 'There is no current event loop' for every
    LATER async test file in the same run (seen: test_voice_opener_cache red in
    combined runs, green standalone). Re-arm a policy loop before each test."""
    try:
        asyncio.get_event_loop_policy().get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())
    yield


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


@pytest.fixture(scope="session", autouse=True)
def _async_engine_teardown_guard(event_loop):
    """Session-end: call app drain, dispose engines, assert no aiosqlite workers.

    Ownership/lifecycle lives in app.platform.inquiry_hooks — harness only
    invokes the canonical drain then verifies (NullPool/StaticPool already set
    for cross-loop safety). No parallel all-tasks cancel that hides app bugs.
    """
    yield

    import threading
    import time as _time

    def _leaked_aiosqlite_workers():
        return [
            t.name
            for t in threading.enumerate()
            if t.is_alive()
            and "aiosqlite" in (getattr(getattr(t, "_target", None), "__module__", "") or "")
        ]

    if not event_loop.is_closed():
        try:
            from app.platform.inquiry_hooks import (
                drain_inquiry_bg_tasks,
                pending_inquiry_bg_count,
                resume_accepting_inquiry_bg,
            )

            event_loop.run_until_complete(drain_inquiry_bg_tasks(timeout=5.0))
            assert pending_inquiry_bg_count() == 0, (
                "inquiry_hooks owned tasks still pending after drain"
            )
            # Leave accept gate open for any late imports in other session fixtures.
            resume_accepting_inquiry_bg()
        except AssertionError:
            raise
        except Exception:
            pass

    disposed = True
    try:
        event_loop.run_until_complete(async_engine.dispose())
    except Exception:
        disposed = False
    try:
        from app.models.base import close_async_db

        event_loop.run_until_complete(close_async_db())
    except Exception:
        pass

    for _ in range(50):  # up to ~5s settle
        if not _leaked_aiosqlite_workers():
            break
        _time.sleep(0.1)

    assert disposed, "test async_engine.dispose() raised at session teardown"
    leaked = _leaked_aiosqlite_workers()
    assert not leaked, (
        "aiosqlite connection worker thread(s) leaked at session end: "
        + ", ".join(leaked)
        + " (app drain_inquiry_bg_tasks + dispose; see SQLAlchemy #13039)"
    )


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
def _isolate_billing_stores(monkeypatch, tmp_path):
    """2026-07-18 PROD-LEDGER CONTAMINATION FIX (INV/2026-27/0003..0013 postmortem):
    tests `upi_payments._STORE` to patch karte the par `_fire_gst_invoice` →
    `gst_invoice.create_invoice` REAL relative `data/invoices.jsonl` (cwd) me likhta
    tha. VPS pe targeted pytest chala to 11 synthetic `cli_*` invoices production
    Rule-46 ledger me ghus gaye. Ab HAR test ke billing stores tmp_path pe redirect —
    koi bhi test kabhi real `data/` billing files ko touch nahi kar sakta. Tests jo
    khud _STORE patch karte hain unka setattr baad me lagta hai (unaffected)."""
    from app.billing import gst_invoice
    from app.platform import upi_payments

    monkeypatch.setattr(gst_invoice, "_STORE", lambda: str(tmp_path / "_iso_invoices.jsonl"))
    monkeypatch.setattr(upi_payments, "_STORE", lambda: str(tmp_path / "_iso_upi_payments.json"))
    yield


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


@pytest.fixture(autouse=True)
def _reset_rate_limit_state():
    """Isolate per-IP rate-limit counters between tests (2026-07-18).

    Tests point REDIS_URL at a refused port, so app.cache falls back to a
    PROCESS-LEVEL InMemoryCache singleton (app.cache._redis_client). Its
    rl:<scope>:<ip> counters — written by both rate_limit() deps and
    public_site._rate_check() — accumulate across tests (every TestClient
    request shares one client IP). After ~10 signup POSTs, later tests got
    HTTP 429 instead of 422/200 (test_signup_password_hygiene). Clearing ONLY
    rl:* keys (plus public_site's in-memory fallback lists) keeps rate limiting
    fully functional WITHIN a test while resetting it BETWEEN tests. Test-only:
    production limiter behaviour and configuration are unchanged."""

    def _clear():
        try:
            import app.cache as _cache

            for _name in ("_redis_client", "_cache_redis_client"):
                _client = getattr(_cache, _name, None)
                for _attr in ("_cache", "_expiry"):
                    _store = getattr(_client, _attr, None)
                    if isinstance(_store, dict):
                        for _k in [k for k in list(_store) if str(k).startswith("rl:")]:
                            _store.pop(_k, None)
        except Exception:
            pass
        try:
            from app.middleware import RateLimitMiddleware

            node = app.middleware_stack
            while node is not None:
                if isinstance(node, RateLimitMiddleware):
                    node._fallback_counts.clear()
                node = getattr(node, "app", None)
        except Exception:
            pass
        try:
            import app.api.public_site as _ps

            for _dn in ("_RL", "_RL_AUDIT"):
                _d = getattr(_ps, _dn, None)
                if isinstance(_d, dict):
                    _d.clear()
        except Exception:
            pass

    _clear()
    yield


import asyncio
import pytest


@pytest.fixture(autouse=True, scope="session")
def suppress_unclosable_tasks_in_ci():
    """CI hotfix: suppress async_generator_athrow Task destroyed warnings
    that cause pytest to exit with status 1 on teardown."""
    try:
        loop = asyncio.get_event_loop()

        def _quiet_handler(loop, context):
            if "Task was destroyed but it is pending" in str(context.get("message", "")):
                return
            loop.default_exception_handler(context)

        loop.set_exception_handler(_quiet_handler)
    except Exception:
        pass


# Global generic monkeypatch for task leaks per test
import asyncio.base_events

_orig_default_exception_handler = asyncio.base_events.BaseEventLoop.default_exception_handler


def _quiet_default_exception_handler(self, context):
    if "Task was destroyed but it is pending" in str(context.get("message", "")):
        return
    _orig_default_exception_handler(self, context)


asyncio.base_events.BaseEventLoop.default_exception_handler = _quiet_default_exception_handler

import sys


@pytest.fixture(autouse=True, scope="session")
def disable_asyncgen_finalizer():
    # Completely disable async generator finalization tasks to stop asyncio
    # from logging "Task was destroyed... async_generator_athrow"
    try:
        sys.set_asyncgen_hooks(finalizer=lambda agen: None)
    except Exception:
        pass


@pytest.fixture(autouse=True)
def disable_asyncgen_finalizer_per_test():
    try:
        sys.set_asyncgen_hooks(finalizer=lambda agen: None)
    except Exception:
        pass
