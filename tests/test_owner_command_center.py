"""Tests for the Owner Command Center (OCC) aggregator API and routes."""
from __future__ import annotations

import json

from fastapi.testclient import TestClient


def _override_admin(app):
    from app.api.auth_deps import require_admin
    app.dependency_overrides[require_admin] = lambda: {"username": "test"}


# ---------------------------------------------------------------------------
# 1. OCC aggregator returns valid JSON structure
# ---------------------------------------------------------------------------

def test_occ_overview_returns_200_and_valid_json(client: TestClient):
    """GET /api/occ/overview must return 200 + well-formed JSON payload."""
    _override_admin(client.app)
    resp = client.get("/api/occ/overview")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, dict)
    assert body["ok"] is True
    assert "at" in body
    assert "elapsed_ms" in body
    # All expected blocks present
    for key in (
        "today_overview",
        "automation_health",
        "activation",
        "workforce",
        "combos",
        "task_ledger",
        "admin_kpis",
        "system",
        "wiring_gaps",
    ):
        assert key in body, f"missing key: {key}"
    client.app.dependency_overrides.clear()


def test_occ_overview_task_ledger_shape(client: TestClient):
    """task_ledger block must have total/by_status/by_owner keys."""
    _override_admin(client.app)
    resp = client.get("/api/occ/overview")
    assert resp.status_code == 200
    tl = resp.json()["task_ledger"]
    assert "total" in tl
    assert "by_status" in tl
    assert "by_owner" in tl
    assert isinstance(tl["total"], int)
    assert isinstance(tl["by_status"], dict)
    assert isinstance(tl["by_owner"], dict)
    client.app.dependency_overrides.clear()


def test_occ_overview_system_block_has_disk_and_ports(client: TestClient):
    """system block must include disk_* and port_* keys."""
    _override_admin(client.app)
    resp = client.get("/api/occ/overview")
    assert resp.status_code == 200
    system = resp.json()["system"]
    # At least one disk key
    assert any(k.startswith("disk_") for k in system), "no disk_ keys in system block"
    # At least one port key
    assert any(k.startswith("port_") for k in system), "no port_ keys in system block"
    client.app.dependency_overrides.clear()


def test_occ_overview_requires_admin():
    """Without admin override, /api/occ/overview must return 401/403."""
    from app.main import app
    app.dependency_overrides.clear()
    with TestClient(app) as c:
        resp = c.get("/api/occ/overview")
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# 2. /app/command-center redirect works
# ---------------------------------------------------------------------------

def test_command_center_redirect(client: TestClient):
    """GET /app/command-center must 307-redirect to /app/owner-command-center."""
    resp = client.get("/app/command-center", follow_redirects=False)
    assert resp.status_code == 307
    assert resp.headers["location"] == "/app/owner-command-center"


def test_owner_command_center_page_returns_200(client: TestClient):
    """GET /app/owner-command-center must return 200 with HTML."""
    resp = client.get("/app/owner-command-center")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")


# ---------------------------------------------------------------------------
# 3. No regressions on existing routes
# ---------------------------------------------------------------------------

def test_health_endpoint_still_works(client: TestClient):
    """GET /health must still return 200."""
    resp = client.get("/health")
    assert resp.status_code == 200


def test_api_status_still_works(client: TestClient):
    """GET /api/status must still return 200."""
    resp = client.get("/api/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"


def test_pricing_page_still_works(client: TestClient):
    """GET /pricing must still return 200."""
    resp = client.get("/pricing")
    assert resp.status_code == 200


def test_admin_page_still_works(client: TestClient):
    """GET /app/admin must still return 200."""
    resp = client.get("/app/admin")
    assert resp.status_code == 200
