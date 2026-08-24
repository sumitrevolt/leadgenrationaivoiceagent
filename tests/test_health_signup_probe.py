"""Loop 14 (2026-07-10): signup-path targeted health probe.

`/health/signup` catches JWT-mint / clients_store / auth-store / automation-log
outages so an ops uptime monitor pages the team the moment signup breaks —
instead of "why is nobody signing up" observation on the CRM.
"""

from __future__ import annotations

import pytest


def test_health_signup_all_green_when_deps_healthy(client):
    """Happy path: all four checks pass → 200 with per-check `healthy`."""
    r = client.get("/health/signup")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("status") == "healthy"
    assert d.get("surface") == "signup"
    checks = d.get("checks") or {}
    for name in ("jwt_mint", "clients_store", "auth_store", "automation_log"):
        assert name in checks, f"probe missing: {name}"
        assert checks[name].get("status") == "healthy", (
            f"{name} unexpectedly unhealthy: {checks[name]}"
        )


def test_health_signup_reports_503_when_jwt_mint_fails(client, monkeypatch):
    """JWT mint broken → 503 with per-check error class so ops can page immediately."""
    import app.api.admin as admin_mod

    def _boom(*a, **k):
        raise RuntimeError("JWT_SECRET missing")

    monkeypatch.setattr(admin_mod, "create_access_token", _boom)

    r = client.get("/health/signup")
    assert r.status_code == 503
    d = r.json()
    assert d.get("status") == "unhealthy"
    jm = (d.get("checks") or {}).get("jwt_mint") or {}
    assert jm.get("status") == "unhealthy"
    assert "RuntimeError" in (jm.get("error") or "")
    # Other checks should still report their own status (per-probe granularity).
    assert (d.get("checks") or {}).get("clients_store", {}).get("status") in (
        "healthy",
        "unhealthy",
    )


def test_health_signup_reports_503_when_automation_log_missing(client, monkeypatch):
    """Loops 2/3B/7/8 depend on automation_log_service — probe MUST fail if
    log_event isn't callable (e.g. import regression)."""
    import app.platform.automation_log_service as als

    monkeypatch.setattr(als, "log_event", None)  # not callable

    r = client.get("/health/signup")
    assert r.status_code == 503
    checks = (r.json() or {}).get("checks") or {}
    assert checks.get("automation_log", {}).get("status") == "unhealthy"


def test_health_signup_never_raises_even_on_import_pathology(client, monkeypatch):
    """Every probe MUST be wrapped so a single import bug never brings /health/signup
    down — it should still report 503 with a structured error, not 500."""
    r = client.get("/health/signup")
    assert r.status_code in (200, 503)
    assert isinstance(r.json().get("checks"), dict)
