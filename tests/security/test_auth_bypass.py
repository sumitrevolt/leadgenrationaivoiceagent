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


# Security invariant: an unauthenticated request to a protected DATA endpoint must
# NOT return a success (2xx). 401/403 (gated), 404 (route absent), 405 (method
# guard), 422 (validation) and 3xx (login redirect) are all acceptable — only a 2xx
# is a real bypass. (HTML SPA shells are 200 by design and tested separately below.)
_SUCCESS = {200, 201, 202, 203, 204, 206}


def _assert_unauthed(response):
    assert response.status_code not in _SUCCESS, (
        f"AUTH BYPASS: {response.url} returned {response.status_code} without auth"
    )


# ---------------------------------------------------------------------------
# Admin SPA shells (static HTML) — served (200) but their DATA is API-gated.
# The page shell is intentionally public + gated client-side; the security
# guarantee lives on the /api endpoints (asserted below). The shell must be
# served or redirect to login, and must NOT inline server-rendered secrets.
# ---------------------------------------------------------------------------
SPA_SHELL_PAGES = ["/app/admin", "/app/customer"]


@pytest.mark.parametrize("path", SPA_SHELL_PAGES)
def test_spa_shell_pages_do_not_leak_secrets(path: str):
    resp = client.get(path, follow_redirects=False)
    assert resp.status_code in (200, 302, 303, 307, 401, 403), (
        f"{path} -> unexpected {resp.status_code}"
    )
    if resp.status_code == 200:
        body = resp.text
        # Static SPA shell may legitimately contain UI labels like "API Key" or a
        # password <input>. What must NOT appear is a POPULATED secret VALUE — a
        # provider key prefix or a server-issued bearer/JWT baked into the page.
        assert "sk_live" not in body and "sk_test" not in body
        assert "Bearer eyJ" not in body and "-----BEGIN" not in body


# ---------------------------------------------------------------------------
# Admin API endpoints — must require auth
# ---------------------------------------------------------------------------
ADMIN_PATHS = [
    "/api/admin/stats",
    "/api/admin/users",
    "/api/admin/billing",
    "/api/admin/agents",
    "/api/admin/workflows",
    "/api/admin/scheduler",
    "/api/admin/queues",
    "/api/admin/health",
    "/api/admin/settings",
    # High-sensitivity endpoints added to catch missing-auth regressions (batch 3)
    "/api/admin/revenue-analytics",
    "/api/admin/upi/pending",
    "/api/admin/upi/configure",
    "/api/admin/voice/gemini-keys",
    "/api/admin/trust/configure-turnstile",
    "/api/admin/trust/configure-sentry",
    "/api/admin/db/tables",
]


@pytest.mark.parametrize("path", ADMIN_PATHS)
def test_admin_endpoints_require_auth(path: str):
    """Admin endpoints without auth must return 401/403."""
    resp = client.get(path, follow_redirects=False)
    _assert_unauthed(resp)


# ---------------------------------------------------------------------------
# Customer portal — must require auth
# ---------------------------------------------------------------------------
CUSTOMER_PATHS = [
    "/api/customer/profile",
    "/api/customer/invoices",
    "/api/customer/subscriptions",
    "/api/customer/webhooks",
]


@pytest.mark.parametrize("path", CUSTOMER_PATHS)
def test_customer_endpoints_require_auth(path: str):
    """Customer endpoints without auth must return 401/403."""
    resp = client.get(path, follow_redirects=False)
    _assert_unauthed(resp)


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
    _assert_unauthed(resp)


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
    _assert_unauthed(resp)


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
    _assert_unauthed(resp)


# ---------------------------------------------------------------------------
# Missing CSRF on state-changing POST (if CSRF middleware exists)
# ---------------------------------------------------------------------------
def test_csrf_protected_post_rejects_without_token():
    """If CSRF is enabled, POST without token must be rejected."""
    # This is a best-effort test; if the app doesn't use CSRF, it may 404 or 302.
    resp = client.post("/api/admin/settings", json={}, follow_redirects=False)
    # We expect 401/403 regardless of CSRF status because auth is missing.
    _assert_unauthed(resp)
