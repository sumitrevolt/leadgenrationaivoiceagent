"""Tests for the Control Center L1 aggregator (/api/control-center/overview).

The top-level tests/conftest.py already overrides require_admin with a mock
super-admin user, so a plain TestClient(app) is authenticated. We also set an
explicit override (test_flow_api.py style) so this file is self-contained.
"""

from fastapi.testclient import TestClient


def _client():
    from app.api import auth_deps
    from app.main import app

    app.dependency_overrides[auth_deps.require_admin] = lambda: type("U", (), {"email": "t@t"})()
    return TestClient(app)


def test_overview_returns_full_contract():
    """200 + every contract key present; cost.available must be False (no telemetry)."""
    c = _client()
    r = c.get("/api/control-center/overview")
    assert r.status_code == 200
    body = r.json()
    for key in (
        "ok",
        "metrics",
        "staff",
        "jobs",
        "problems",
        "activation",
        "eval_gate",
        "cost",
    ):
        assert key in body, f"missing top-level key: {key}"
    assert body["ok"] is True
    # cost is ALWAYS unavailable — the project has no cost telemetry, never fabricate.
    assert body["cost"]["available"] is False
    # metrics sub-shape the frontend depends on
    m = body["metrics"]
    for sub in ("staff", "jobs", "runs", "queue", "heartbeat", "llm"):
        assert sub in m, f"missing metrics.{sub}"
    assert "ok_rate" in m["llm"] and "primary" in m["llm"]
    assert isinstance(body["providers"], list) and body["providers"]


def test_never_raises_when_today_overview_breaks(monkeypatch):
    """If a downstream fan-in module raises, the endpoint still returns 200/ok=true
    with the contract shape intact (partial degradation, never a 500)."""
    import app.platform.today_overview as today_overview

    def _boom():
        raise RuntimeError("today_overview exploded")

    monkeypatch.setattr(today_overview, "build", _boom)

    c = _client()
    r = c.get("/api/control-center/overview")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    # degraded-but-shaped: today_overview-sourced keys fall back to safe defaults
    assert body["headline"] == ""
    assert body["staff"] == []
    assert body["problems"] == []
    # unaffected blocks + envelope still present
    assert "metrics" in body and "cost" in body
    assert body["cost"]["available"] is False
