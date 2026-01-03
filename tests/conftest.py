"""
Test Configuration
"""
import pytest
import asyncio
from typing import Generator
from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.models.base import Base, get_db
from app.models.user import User
from app.api.auth_deps import get_current_user, require_agent, require_manager, require_admin, require_super_admin


# Test database
TEST_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    """Override database dependency for testing"""
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


# Create a mock authenticated user for testing
def get_mock_user():
    """Return a mock authenticated user for tests"""
    user = User(
        id="test-user-id",
        email="test@example.com",
        first_name="Test",
        last_name="User",
        role="super_admin",  # Give full access for tests
        status="active",
        password_hash="mock_hash",
        password_salt="mock_salt",
        is_verified=True,
        created_at=datetime.utcnow()
    )
    return user


app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[get_current_user] = get_mock_user
app.dependency_overrides[require_agent] = get_mock_user
app.dependency_overrides[require_manager] = get_mock_user
app.dependency_overrides[require_admin] = get_mock_user
app.dependency_overrides[require_super_admin] = get_mock_user


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="function")
def db():
    """Create test database tables"""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db) -> Generator:
    """Create test client"""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def sample_lead():
    """Sample lead data"""
    return {
        "company_name": "Test Company",
        "contact_name": "Test Contact",
        "phone": "+919876543210",
        "email": "test@example.com",
        "city": "Mumbai",
        "category": "Real Estate"
    }


@pytest.fixture
def sample_campaign():
    """Sample campaign data"""
    return {
        "name": "Test Campaign",
        "niche": "real_estate",
        "client_name": "Test Client",
        "client_service": "Property Sales",
        "target_cities": ["Mumbai", "Delhi"],
        "target_lead_count": 100,
        "daily_call_limit": 50
    }
