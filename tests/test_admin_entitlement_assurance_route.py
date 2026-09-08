"""Admin API route for the billing/entitlement-assurance scan.

Verifies the previously-dormant ``entitlement_assurance`` detector is now
reachable at ``GET /api/admin/entitlement-assurance`` (mirrors the wired sibling
``/api/admin/delivery-assurance``): correct contract passthrough, ``limit``
plumbing, and the never-500 degrade contract on internal failure.

NOTE: tests/conftest.py globally mocks require_admin — anon-reject is asserted in
tests/security/. This suite asserts the route exists + shape only.
"""

# ruff: noqa: I001
from __future__ import annotations

from fastapi.testclient import TestClient

from app.billing import entitlement_assurance
from app.main import app

client = TestClient(app)

_ROUTE = "/api/admin/entitlement-assurance"


def _fake_scan(limit: int = 200):
    return {
        "run_id": "test-run",
        "agent_id": "entitlement_assurance",
        "domain": "billing",
        "lane": "GREEN",
        "status": "success",
        "started_at": "2026-07-24T00:00:00+00:00",
        "completed_at": "2026-07-24T00:00:01+00:00",
        "latency_ms": 5,
        "checked": 3,
        "issues": [
            {
                "type": "paid_no_invoice",
                "count": 1,
                "sample": [{"id": "leak-biz", "severity": "critical"}],
            }
        ],
        "counts": {"checked": 3, "flagged": 1, "paid_no_invoice": 1},
        "error": None,
        "_limit_seen": limit,
    }


def test_route_mounted_and_passes_scan_through(monkeypatch):
    monkeypatch.setattr(entitlement_assurance, "scan_entitlements", _fake_scan)
    r = client.get(_ROUTE)
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["agent_id"] == "entitlement_assurance"
    assert data["domain"] == "billing"
    assert data["counts"]["paid_no_invoice"] == 1
    assert data["issues"][0]["type"] == "paid_no_invoice"


def test_limit_query_is_plumbed(monkeypatch):
    monkeypatch.setattr(entitlement_assurance, "scan_entitlements", _fake_scan)
    r = client.get(_ROUTE, params={"limit": 7})
    assert r.status_code == 200
    assert r.json()["_limit_seen"] == 7


def test_limit_bounds_validated():
    # ge=1 / le=500 — out-of-range must be a 422 validation, not a 500
    assert client.get(_ROUTE, params={"limit": 0}).status_code == 422
    assert client.get(_ROUTE, params={"limit": 9999}).status_code == 422


def test_never_500_on_internal_failure(monkeypatch):
    def _boom(limit: int = 200):
        raise RuntimeError("scan exploded")

    monkeypatch.setattr(entitlement_assurance, "scan_entitlements", _boom)
    r = client.get(_ROUTE)
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is False
    assert data["status"] == "error"
    assert data["agent_id"] == "entitlement_assurance"
    assert data["error"]


def test_real_scan_smoke_never_raises():
    # Real invocation against whatever local stores exist — must degrade, not 500.
    r = client.get(_ROUTE)
    assert r.status_code == 200
    data = r.json()
    assert data["agent_id"] == "entitlement_assurance"
    assert "counts" in data and "issues" in data
