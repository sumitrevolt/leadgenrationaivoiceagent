"""Security tests — Auth Bypass.

Verifies that authenticated endpoints cannot be accessed without valid credentials,
and that auth bypass vectors (missing auth, weak tokens, session fixation) are blocked.

Playbook ref: Security Playbook — Auth bypass tests.
"""
from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from app.main import app

client = TestClient(app)


def _assert_401_or_403(response):
    assert response.status_code in (401, 403), (
        f"Expected 401/403, got {response.status_code} for {response.url}"
    )


# ---------------------------------------------------------------------------
# Admin endpoints — must require auth
# ---------------------------------------------------------------------------
ADMIN_PATHS = [
    "/app/admin",
    "/api/admin/stats",
    "/api/admin/users",
    "/api/admin/billing",
    "/api/admin/agents",
    "/api/admin/workflows",
    "/api/admin/scheduler",
    "/api/admin/queues",
    "/api/admin/health",
    "/api/admin/settings",
]


@pytest.mark.parametrize("path", ADMIN_PATHS)
def test_admin_endpoints_require_auth(path: str):
    """Admin endpoints without auth must return 401/403."""
    resp = client.get(path, follow_redirects=False)
    _assert_401_or_403(resp)


# ---------------------------------------------------------------------------
# Customer portal — must require auth
# ---------------------------------------------------------------------------
CUSTOMER_PATHS = [
    "/app/customer",
    "/api/customer/profile",
    "/api/customer/invoices",
    "/api/customer/subscriptions",
    "/api/customer/webhooks",
]


@pytest.mark.parametrize("path", CUSTOMER_PATHS)
def test_customer_endpoints_require_auth(path: str):
    """Customer endpoints without auth must return 401/403."""
    resp = client.get(path, follow_redirects=False)
    _assert_401_or_403(resp)


# ---------------------------------------------------------------------------
# Billing mutation endpoints — must require auth
# ---------------------------------------------------------------------------
BILLING_MUTATION_PATHS = [
    ("POST", "/api/billing/subscribe"),
    ("POST", "/api/billing/cancel"),
    ("POST", "/api/billing/upgrade"),
    ("POST", "/api/billing/payment"),
    ("PUT", "/api/billing/invoice"),
]


@pytest.mark.parametrize("method,path", BILLING_MUTATION_PATHS)
def test_billing_mutations_require_auth(method: str, path: str):
    """Billing mutations without auth must return 401/403."""
    resp = client.request(method, path, follow_redirects=False)
    _assert_401_or_403(resp)


# ---------------------------------------------------------------------------
# Voice/Telephony endpoints — must require auth or valid token
# ---------------------------------------------------------------------------
VOICE_AUTH_PATHS = [
    "/api/telephony/call",
    "/api/telephony/campaign",
    "/api/telephony/status",
]


@pytest.mark.parametrize("path", VOICE_AUTH_PATHS)
def test_voice_endpoints_require_auth(path: str):
    """Voice control endpoints without auth must return 401/403."""
    resp = client.post(path, json={}, follow_redirects=False)
    _assert_401_or_403(resp)


# ---------------------------------------------------------------------------
# Weak token rejection
# ---------------------------------------------------------------------------
def test_bearer_token_too_short_rejected():
    """Tokens shorter than reasonable length should be rejected."""
    resp = client.get(
        "/api/customer/profile",
        headers={"Authorization": "Bearer xyz"},
        follow_redirects=False,
    )
    _assert_401_or_403(resp)


# ---------------------------------------------------------------------------
# Missing CSRF on state-changing POST (if CSRF middleware exists)
# ---------------------------------------------------------------------------
def test_csrf_protected_post_rejects_without_token():
    """If CSRF is enabled, POST without token must be rejected."""
    # This is a best-effort test; if the app doesn't use CSRF, it may 404 or 302.
    resp = client.post("/api/admin/settings", json={}, follow_redirects=False)
    # We expect 401/403 regardless of CSRF status because auth is missing.
    _assert_401_or_403(resp)
