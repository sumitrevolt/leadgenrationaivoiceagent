"""B1 - revenue time-series snapshot store + /revenue-trend endpoint."""

import pytest
from fastapi.testclient import TestClient

from app.api.auth_deps import require_admin
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _admin_auth():
    """Bypass admin auth for endpoint tests (real auth stays enforced in prod)."""
    app.dependency_overrides[require_admin] = lambda: {"id": "admin", "role": "super_admin"}
    yield
    app.dependency_overrides.pop(require_admin, None)


def test_snapshot_roundtrip(tmp_path, monkeypatch):
    from datetime import date, timedelta

    from app.platform import revenue_snapshots as rs

    f = tmp_path / "revenue_snapshots.jsonl"
    monkeypatch.setattr(rs, "_SNAP_FILE", str(f))
    # Dates must fall inside read_trend(days=30) cutoff relative to "today".
    d0 = (date.today() - timedelta(days=2)).strftime("%Y-%m-%d")
    d1 = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    rs._append_row({"date": d0, "mrr": 1000, "active": 2, "churn_pct": 0.0, "ltv": 6000})
    rs._append_row({"date": d1, "mrr": 1200, "active": 3, "churn_pct": 5.0, "ltv": 4800})
    pts = rs.read_trend(days=30, clients=[])
    real = [p for p in pts if not p.get("estimated")]
    assert [p["date"] for p in real] == [d0, d1]
    assert real[-1]["mrr"] == 1200
    assert real[-1]["estimated"] is False


def test_estimate_curve_from_clients(tmp_path, monkeypatch):
    from app.platform import revenue_snapshots as rs

    monkeypatch.setattr(rs, "_SNAP_FILE", str(tmp_path / "none.jsonl"))
    clients = [
        {"created_at": "2026-06-01", "plan_price_inr": 2999, "status": "active"},
        {"created_at": "2026-06-10", "plan_price_inr": 1199, "status": "active"},
    ]
    pts = rs.read_trend(days=30, clients=clients)
    assert len(pts) >= 1
    assert all(p["estimated"] for p in pts)
    assert pts[-1]["mrr"] >= 2999  # both clients counted by today


def test_revenue_trend_endpoint_flag_off(monkeypatch):
    monkeypatch.delenv("REVENUE_TRENDS", raising=False)
    r = client.get("/api/admin/revenue-trend?days=30")
    assert r.status_code == 200
    assert r.json()["enabled"] is False
