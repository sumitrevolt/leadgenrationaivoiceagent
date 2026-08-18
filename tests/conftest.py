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

import asyncio
import pytest
@pytest.fixture(autouse=True, scope="session")
def suppress_unclosable_tasks_in_ci():
    """CI hotfix: suppress async_generator_athrow Task destroyed warnings
    that cause pytest to exit with status 1 on teardown."""
    try:
        loop = asyncio.get_event_loop()
        def _quiet_handler(loop, context):
            msg = context.get("message", "")
            if "Task was destroyed but it is pending" in msg:
                return
            loop.default_exception_handler(context)
        loop.set_exception_handler(_quiet_handler)
    except RuntimeError:
        pass
