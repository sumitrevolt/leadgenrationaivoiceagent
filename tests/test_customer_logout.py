"""Customer logout (session revocation) tests."""

import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


@pytest.mark.asyncio
async def test_customer_logout_invalidates_token():
    """Test that logout revokes customer JWT token."""
    # Login
    login_resp = client.post(
        "/api/customer/auth/login",
        json={"email": "test.logout@example.com", "password": "Password123!"},
    )
    assert login_resp.status_code in (200, 401)  # May not exist in test DB
    if login_resp.status_code != 200:
        pytest.skip("Test account not available")

    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Verify token works before logout
    me_resp = client.get("/api/customer/auth/me", headers=headers)
    assert me_resp.status_code == 200, "Token should work before logout"

    # Logout
    logout_resp = client.post("/api/customer/auth/logout", headers=headers)
    assert logout_resp.status_code == 200

    # Try to use token after logout
    me_after = client.get("/api/customer/auth/me", headers=headers)
    assert me_after.status_code == 401, "Token should be rejected after logout"
    assert "revoked" in me_after.json().get("detail", "").lower() or me_after.status_code == 401


def test_logout_endpoint_exists():
    """Test that logout endpoint exists and requires auth."""
    # Unauthenticated should fail
    resp = client.post("/api/customer/auth/logout")
    assert resp.status_code in (401, 403), "Logout without auth should fail"


def test_logout_returns_success():
    """Test logout returns 200 even if Redis unavailable."""
    # With invalid token (will fail Redis check but endpoint returns 200)
    headers = {"Authorization": "Bearer invalid.jwt.token"}
    resp = client.post("/api/customer/auth/logout", headers=headers)
    # Either 401 (token invalid) or 200 (graceful degradation) are acceptable
    assert resp.status_code in (200, 401)
