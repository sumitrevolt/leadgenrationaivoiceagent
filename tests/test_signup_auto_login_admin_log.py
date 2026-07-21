"""Loop 2 (2026-07-10): admin observability for signup auto-login failure.

When `create_access_token` raises during signup, the account is still created
(idempotent password login intact) but the customer must recover via manual
login. The admin Delivery Command Center's Automation Runs panel is already
wired to `/api/admin/automation-logs` (ADR-064) — this loop plugs a
`signup_auto_login_failed` row so ops sees the count without grepping logs.

RED-first: fails before the log_event emission, passes after.
"""

from __future__ import annotations

import pytest


def _stub_signup_side_effects(monkeypatch, cid: str = "c_al2"):
    import app.api.customer_auth as ca
    import app.billing.usage as usage
    import app.marketing.clients_store as cs

    monkeypatch.setattr(
        cs,
        "add_client",
        lambda **k: {"id": cid, "business_name": k.get("business_name")},
    )
    monkeypatch.setattr(ca, "login_exists", lambda e: False)
    monkeypatch.setattr(ca, "client_has_login", lambda c: False)
    monkeypatch.setattr(ca, "register_login", lambda *a, **k: {"ok": True})
    monkeypatch.setattr(usage, "activate_plan", lambda c, p, **k: True)
    monkeypatch.setattr(usage, "reset_usage_period", lambda c: True)


def test_signup_auto_login_failure_emits_automation_log(client, monkeypatch):
    """Server MUST emit a `signup_auto_login_failed` AutomationLog row so the admin
    Delivery Command Center's Automation Runs panel can surface the failure count
    (job_type filter + customer filter + evidence trail) without ops greppping logs."""
    _stub_signup_side_effects(monkeypatch, cid="c_admin_log")

    import app.api.admin as admin_mod
    import app.platform.automation_log_service as als

    def _broken_mint(*a, **k):
        raise RuntimeError("JWT_SECRET missing")

    monkeypatch.setattr(admin_mod, "create_access_token", _broken_mint)

    captured: list[dict] = []

    def _fake_log_event(**kw):
        captured.append(kw)
        return "log_id_fake"

    monkeypatch.setattr(als, "log_event", _fake_log_event)

    r = client.post(
        "/api/public/signup",
        json={
            "business_name": "Admin Log Biz",
            "email": "adminlog@example.com",
            "password": "secret123",  # pragma: allowlist secret
            "plan": "starter",
        },
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("auto_login") is False

    # Exactly one signup_auto_login_failed row must have been emitted with the
    # ADR-064 canonical field set (client_id + job_type + status + attribution).
    rows = [c for c in captured if c.get("job_type") == "signup_auto_login_failed"]
    assert len(rows) == 1, f"expected exactly 1 admin log row, got {len(rows)}: {captured}"
    row = rows[0]
    assert row.get("client_id") == "c_admin_log", "client attribution required for admin filter"
    assert row.get("status") == "failed"
    assert row.get("triggered_by") == "signup"
    err = row.get("error_message") or ""
    assert "RuntimeError" in err and "JWT_SECRET" in err, f"error class + reason needed: {err!r}"
    meta = row.get("meta_json") or {}
    assert meta.get("email") == "adminlog@example.com"
    assert meta.get("plan") == "starter"


def test_signup_normal_path_emits_no_failure_log(client, monkeypatch):
    """GREEN: happy-path signup MUST NOT emit a failure row (no false positives in
    the admin panel — panel filter would otherwise show noise on every signup)."""
    _stub_signup_side_effects(monkeypatch, cid="c_admin_ok")

    import app.platform.automation_log_service as als

    captured: list[dict] = []
    monkeypatch.setattr(als, "log_event", lambda **kw: (captured.append(kw), "id")[1])

    r = client.post(
        "/api/public/signup",
        json={
            "business_name": "Admin Log Ok",
            "email": "adminlog2@example.com",
            "password": "secret123",  # pragma: allowlist secret
            "plan": "starter",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json().get("auto_login") is True

    failure_rows = [c for c in captured if c.get("job_type") == "signup_auto_login_failed"]
    assert failure_rows == [], f"no failure rows expected on happy path: {failure_rows}"


def test_signup_log_emit_failure_does_not_break_signup(client, monkeypatch):
    """Defensive: even if automation_log_service.log_event itself explodes, signup
    MUST still return 200 with the auto_login=false signal so the customer is not
    dead-ended by a downstream logging bug."""
    _stub_signup_side_effects(monkeypatch, cid="c_admin_log_err")

    import app.api.admin as admin_mod
    import app.platform.automation_log_service as als

    monkeypatch.setattr(
        admin_mod,
        "create_access_token",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("nope")),
    )
    monkeypatch.setattr(
        als, "log_event", lambda **kw: (_ for _ in ()).throw(RuntimeError("db down"))
    )

    r = client.post(
        "/api/public/signup",
        json={
            "business_name": "Admin Log Defensive",
            "email": "adminlog3@example.com",
            "password": "secret123",  # pragma: allowlist secret
            "plan": "starter",
        },
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("ok") is True
    assert d.get("auto_login") is False
    assert d.get("next", {}).get("url") == "/app/login"
