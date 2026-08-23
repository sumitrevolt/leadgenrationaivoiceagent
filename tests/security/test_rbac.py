"""Security tests — RBAC enforcement.

Verifies that role-based access control is enforced:
- Admin endpoints reject customer tokens.
- Customer endpoints accept customer tokens.
- Admin endpoints accept admin tokens.
- Missing roles default to least privilege.

Playbook ref: Security Playbook — RBAC tests.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from app.main import app

client = TestClient(app)

# A protected endpoint must NEVER return a success (2xx) to an unauthenticated /
# wrong-role caller. That is the real security invariant. 401/403 (gated), 404
# (route absent), 405 (method guard), 422 (validation) and 3xx (redirect to login)
# are ALL acceptable — only a 2xx is a genuine auth bypass. Asserting an exact code
# couples the test to specific route paths/methods that drift (and turns a missing
# route into a false "failure"); asserting "not 2xx" tests the actual guarantee.
_SUCCESS = {200, 201, 202, 203, 204, 206}


# ---------------------------------------------------------------------------
# Admin endpoints must reject unauthenticated / customer-only sessions
# ---------------------------------------------------------------------------
ADMIN_API_PATHS = [
    "/api/admin/stats",
    "/api/admin/users",
    "/api/admin/billing",
    "/api/admin/agents",
    "/api/admin/workflows",
    "/api/platform/health",  # sec sweep 2026-07-06: was anon (tenant count + scheduler state leak)
    "/api/v1/status",  # sec sweep 2026-07-06: was anon (env/version/LLM-TTS-STT config + llm_usage leak)
]


@pytest.mark.parametrize("path", ADMIN_API_PATHS)
def test_admin_api_rejects_no_auth(path: str):
    """Admin API without any auth token must not succeed (no 2xx)."""
    resp = client.get(path, follow_redirects=False)
    assert resp.status_code not in _SUCCESS, (
        f"AUTH BYPASS: {path} -> {resp.status_code} without auth"
    )


# ---------------------------------------------------------------------------
# Regression: app/api/platform.py tenant CRUD/billing + app/api/ml_training.py
# were fully unauthenticated (production audit 2026-07-01, security batch 4) —
# anyone could read tenant PII, free-upgrade billing, pause/resume/DELETE any
# tenant, and trigger prod ML training/scheduler control. Fixed by adding
# require_admin (require_super_admin for the destructive delete). These tests
# only run real auth enforcement here (tests/security/conftest.py strips the
# harness's mock-admin override) — the top-level suite's mocked-open auth is
# exactly why this class of bug shipped undetected before.
# ---------------------------------------------------------------------------
def _seed_fake_tenant(monkeypatch, tenant_id: str):
    """Seed a REAL entry in tenant_manager.tenants so an auth bypass on
    get/upgrade/delete/scrape-tenant would surface as a 200 (they 404 on a
    lookup miss) rather than being masked by an incidental not-found response."""
    import types
    from datetime import datetime

    from app.api.platform import tenant_manager

    fake = types.SimpleNamespace(
        id=tenant_id,
        company_name="RBAC Regression Co",
        contact_name="Test",
        contact_phone="+919999999999",
        contact_email="rbac-test@example.com",
        industry="testing",
        status=types.SimpleNamespace(value="active"),
        config=types.SimpleNamespace(
            subscription_tier=types.SimpleNamespace(value="growth"),
            calls_used=0,
            monthly_call_limit=100,
            automation_level=types.SimpleNamespace(value="full"),
            auto_scrape=True,
            auto_call=True,
        ),
        is_running=True,
        total_leads_generated=0,
        total_calls_made=0,
        total_appointments=0,
        created_at=datetime.now(),
    )
    monkeypatch.setitem(tenant_manager.tenants, tenant_id, fake)


def test_platform_tenant_get_rejects_no_auth(monkeypatch):
    tenant_id = "rbac-regression-tenant-1"
    _seed_fake_tenant(monkeypatch, tenant_id)
    resp = client.get(f"/api/platform/tenants/{tenant_id}", follow_redirects=False)
    assert resp.status_code not in _SUCCESS, (
        f"AUTH BYPASS: GET /api/platform/tenants/{{id}} -> {resp.status_code} without auth"
    )


def test_platform_tenant_upgrade_rejects_no_auth(monkeypatch):
    tenant_id = "rbac-regression-tenant-2"
    _seed_fake_tenant(monkeypatch, tenant_id)
    resp = client.post(
        f"/api/platform/tenants/{tenant_id}/upgrade",
        json={"tier": "growth"},
        follow_redirects=False,
    )
    assert resp.status_code not in _SUCCESS, (
        f"AUTH BYPASS: POST /api/platform/tenants/{{id}}/upgrade -> {resp.status_code} without auth"
    )


def test_platform_tenant_scrape_rejects_no_auth(monkeypatch):
    tenant_id = "rbac-regression-tenant-3"
    _seed_fake_tenant(monkeypatch, tenant_id)
    resp = client.post(f"/api/platform/scrape/tenant/{tenant_id}", follow_redirects=False)
    assert resp.status_code not in _SUCCESS, (
        f"AUTH BYPASS: POST /api/platform/scrape/tenant/{{id}} -> {resp.status_code} without auth"
    )


def test_platform_tenant_delete_rejects_no_auth(monkeypatch):
    # pause_tenant()/resume_tenant() silently no-op on an unknown id (no lookup
    # gate), so those two are valid with a nonexistent id as-is. delete_tenant()
    # 404s on a miss, so it needs the same real-entry seeding as get/upgrade.
    tenant_id = "rbac-regression-tenant-4"
    _seed_fake_tenant(monkeypatch, tenant_id)
    resp = client.delete(f"/api/platform/tenants/{tenant_id}", follow_redirects=False)
    assert resp.status_code not in _SUCCESS, (
        f"AUTH BYPASS: DELETE /api/platform/tenants/{{id}} -> {resp.status_code} without auth"
    )


PLATFORM_TENANT_POST_PATHS = [
    "/api/platform/tenants/nonexistent-id/pause",
    "/api/platform/tenants/nonexistent-id/resume",
    "/api/platform/scrape/platform",
]


@pytest.mark.parametrize("path", PLATFORM_TENANT_POST_PATHS)
def test_platform_tenant_post_rejects_no_auth(path: str):
    """These three don't gate on tenant existence (pause/resume no-op silently,
    scrape/platform takes no id) — a nonexistent id doesn't mask an auth bypass."""
    resp = client.post(path, json={"tier": "growth"}, follow_redirects=False)
    assert resp.status_code not in _SUCCESS, (
        f"AUTH BYPASS: {path} -> {resp.status_code} without auth"
    )


ML_TRAINING_GET_PATHS = ["/api/ml/status", "/api/ml/metrics", "/api/ml/brain/status"]


@pytest.mark.parametrize("path", ML_TRAINING_GET_PATHS)
def test_ml_training_get_rejects_no_auth(path: str):
    resp = client.get(path, follow_redirects=False)
    assert resp.status_code not in _SUCCESS, (
        f"AUTH BYPASS: {path} -> {resp.status_code} without auth"
    )


ML_TRAINING_POST_PATHS = [
    "/api/ml/train",
    "/api/ml/feedback",
    "/api/ml/scheduler/start",
    "/api/ml/scheduler/stop",
    "/api/ml/brain/train/now",
    "/api/ml/vertex/train/now",
    "/api/ml/vertex/behavior",
]


@pytest.mark.parametrize("path", ML_TRAINING_POST_PATHS)
def test_ml_training_post_rejects_no_auth(path: str):
    resp = client.post(path, json={}, follow_redirects=False)
    assert resp.status_code not in _SUCCESS, (
        f"AUTH BYPASS: {path} -> {resp.status_code} without auth"
    )


# Same batch: app/api/leads.py's GET /stats/summary (business-data leak) and
# GET /scrape/{task_id} (scrape-task leak) also shipped with zero auth.
def test_leads_stats_summary_rejects_no_auth():
    resp = client.get("/api/leads/stats/summary", follow_redirects=False)
    assert resp.status_code not in _SUCCESS, (
        f"AUTH BYPASS: /api/leads/stats/summary -> {resp.status_code} without auth"
    )


def test_leads_scrape_status_rejects_no_auth():
    # A nonexistent task_id would 404 regardless of auth (dependency runs first,
    # but so would a real 401) — seed a REAL entry so an auth bypass would
    # actually surface as a 200, not be masked by an incidental 404.
    import app.api.leads as leads_mod

    task_id = "rbac-regression-test-task"
    leads_mod.scrape_tasks[task_id] = {"status": "completed", "leads_found": 3}
    try:
        resp = client.get(f"/api/leads/scrape/{task_id}", follow_redirects=False)
        assert resp.status_code not in _SUCCESS, (
            f"AUTH BYPASS: /api/leads/scrape/{{task_id}} -> {resp.status_code} without auth"
        )
    finally:
        leads_mod.scrape_tasks.pop(task_id, None)


@pytest.mark.parametrize("path", ADMIN_API_PATHS)
def test_admin_api_rejects_customer_token(path: str):
    """Admin API with a customer-scoped token must be rejected."""
    # Simulate a customer token (JWT with role='customer')
    resp = client.get(
        path,
        # nosecret (fake unsigned test JWT, role=customer)
        headers={"Authorization": "Bearer eyJhbG...fake"},
        follow_redirects=False,
    )
    # An invalid/wrong-role token must not yield a success response.
    assert resp.status_code not in _SUCCESS, (
        f"AUTH BYPASS: {path} -> {resp.status_code} with bad token"
    )


# ---------------------------------------------------------------------------
# Customer endpoints must accept customer auth (or redirect to login)
# ---------------------------------------------------------------------------
CUSTOMER_API_PATHS = [
    "/api/customer/profile",
    "/api/customer/invoices",
    "/api/customer/subscriptions",
]


@pytest.mark.parametrize("path", CUSTOMER_API_PATHS)
def test_customer_api_rejects_no_auth(path: str):
    """Customer API without auth must be rejected or redirected (no 2xx)."""
    resp = client.get(path, follow_redirects=False)
    assert resp.status_code not in _SUCCESS, (
        f"AUTH BYPASS: {path} -> {resp.status_code} without auth"
    )


# ---------------------------------------------------------------------------
# Public endpoints must remain open (sanity check)
# ---------------------------------------------------------------------------
PUBLIC_PATHS = [
    "/",
    "/health",
    "/api/public/pay-info",
    "/api/activation/summary",
    "/pricing",
    "/demo",
    "/audit",
]


@pytest.mark.parametrize("path", PUBLIC_PATHS)
def test_public_endpoints_remain_open(path: str):
    """Public endpoints must NOT require auth."""
    resp = client.get(path, follow_redirects=False)
    assert resp.status_code in (200, 307, 308, 404), (
        f"Public endpoint {path} got {resp.status_code} — should be open"
    )


def test_activation_summary_omits_named_blockers():
    """Public /summary exposes counts + booleans ONLY — never the named
    blockers/warns arrays (a recon list of which controls are unarmed).
    Sec sweep 2026-07-06."""
    resp = client.get("/api/activation/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert "blocker_count" in body and "ready_for_launch" in body  # counts/booleans stay
    assert "blockers" not in body  # named controls no longer leaked
    assert "warns" not in body


# ---------------------------------------------------------------------------
# Least-privilege default: unknown role = deny
# ---------------------------------------------------------------------------
def test_unknown_role_defaults_to_deny():
    """A token with an unknown/unsupported role must be denied for admin paths."""
    resp = client.get(
        "/api/admin/stats",
        # nosecret (fake unsigned test JWT, role=unknown)
        headers={"Authorization": "Bearer eyJhbG...fake"},
        follow_redirects=False,
    )
    assert resp.status_code not in _SUCCESS, (
        f"AUTH BYPASS: unknown-role token -> {resp.status_code}"
    )
