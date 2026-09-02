"""Loop 3B (2026-07-10): admin GTM visibility for successful signups.

Every successful signup MUST emit a `signup_completed` AutomationLog row so the
admin Delivery Command Center's Automation Runs panel can count new customers
per day/week (job_type filter). This is the happy-path mirror of Loop 2's
`signup_auto_login_failed` row.

RED-first: fails before the log_event call in Loop 3B, passes after.
"""

from __future__ import annotations

import pytest


def _stub_signup_side_effects(monkeypatch, cid: str = "c_c1"):
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


def test_signup_success_emits_signup_completed_row(client, monkeypatch):
    """Paid signup MUST emit exactly one signup_completed AutomationLog row
    with the ADR-064 canonical fields for admin count/filter."""
    _stub_signup_side_effects(monkeypatch, cid="c_gtm_paid")

    import app.platform.automation_log_service as als

    captured: list[dict] = []
    monkeypatch.setattr(als, "log_event", lambda **kw: (captured.append(kw), "id")[1])

    r = client.post(
        "/api/public/signup",
        json={
            "business_name": "GTM Paid Biz",
            "email": "gtmpaid@example.com",
            "password": "secret123",  # pragma: allowlist secret
            "plan": "advanced",
        },
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("auto_login") is True

    rows = [c for c in captured if c.get("job_type") == "signup_completed"]
    assert len(rows) == 1, f"expected exactly 1 signup_completed row, got {len(rows)}: {captured}"
    row = rows[0]
    assert row.get("client_id") == "c_gtm_paid"
    assert row.get("status") == "success"
    assert row.get("triggered_by") == "signup"
    summary = row.get("output_summary") or ""
    assert "GTM Paid Biz" in summary, (
        f"business name must be in summary for admin scan: {summary!r}"
    )
    assert "advanced" in summary
    assert "[trial]" not in summary
    meta = row.get("meta_json") or {}
    assert meta.get("email") == "gtmpaid@example.com"
    assert meta.get("plan") == "advanced"
    assert meta.get("trial") is False
    assert meta.get("auto_login") is True
    assert meta.get("plan_provisioned") is True


def test_signup_success_trial_flagged_in_summary_and_meta(client, monkeypatch):
    """Trial signup MUST tag `[trial]` in the summary and `trial: True` in meta
    so admins can split trial vs paid counts at a glance."""
    _stub_signup_side_effects(monkeypatch, cid="c_gtm_trial")

    import app.platform.automation_log_service as als

    captured: list[dict] = []
    monkeypatch.setattr(als, "log_event", lambda **kw: (captured.append(kw), "id")[1])

    r = client.post(
        "/api/public/signup",
        json={
            "business_name": "GTM Trial Biz",
            "email": "gtmtrial@example.com",
            "password": "secret123",  # pragma: allowlist secret
            "plan": "trial",
        },
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("trial") is True

    rows = [c for c in captured if c.get("job_type") == "signup_completed"]
    assert len(rows) == 1
    row = rows[0]
    assert "[trial]" in (row.get("output_summary") or ""), "admin scan needs trial tag"
    meta = row.get("meta_json") or {}
    assert meta.get("trial") is True
    # Trial signups skip paid provisioning by design (Loop 1B contract).
    assert meta.get("plan_provisioned") is False


def test_signup_completed_log_failure_does_not_break_signup(client, monkeypatch):
    """Defensive: if automation_log_service.log_event blows up on the happy
    path, signup MUST still return 200 with a healthy `auto_login: True` — the
    admin visibility feature is non-blocking."""
    _stub_signup_side_effects(monkeypatch, cid="c_gtm_defensive")

    import app.platform.automation_log_service as als

    monkeypatch.setattr(
        als, "log_event", lambda **kw: (_ for _ in ()).throw(RuntimeError("db down"))
    )

    r = client.post(
        "/api/public/signup",
        json={
            "business_name": "GTM Defensive Biz",
            "email": "gtmdef@example.com",
            "password": "secret123",  # pragma: allowlist secret
            "plan": "starter",
        },
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("ok") is True
    assert d.get("auto_login") is True, "auto_login independent of admin logging"
