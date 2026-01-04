"""
Test Configuration
Production-ready test fixtures with proper async handling
"""
import pytest
import asyncio
import os
from typing import Generator, AsyncGenerator
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.main import app
from app.models.base import Base, get_db, get_async_db
from app.models.user import User, UserRole, UserStatus
from app.api.auth_deps import get_current_user, require_agent, require_manager, require_admin, require_super_admin


# =============================================================================
# TEST DATABASE CONFIGURATION
# =============================================================================

# Use SQLite for tests (fast, no external dependencies)
TEST_DATABASE_URL = "sqlite:///./test.db"
TEST_ASYNC_DATABASE_URL = "sqlite+aiosqlite:///./test.db"

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
    from httpx import AsyncClient, ASGITransport
    
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
def mock_twilio(mocker):
    """Mock Twilio client for tests"""
    mock = mocker.patch("app.telephony.twilio_handler.TwilioHandler")
    return mock


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
