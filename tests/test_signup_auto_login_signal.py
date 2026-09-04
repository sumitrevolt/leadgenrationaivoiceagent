"""Enterprise-grade signup auto-login signalling (2026-07-10 onboarding audit).

GAP: `public_signup` swallowed `create_access_token` failures at DEBUG level and
returned `{ok: True, access_token: null}` — a silent data-consistency violation.
Frontend (`pricing.html:377`) then sent empty Bearer on the PAID checkout path,
producing a bare 401 with no user-facing recovery guidance.

FIX: response now carries an explicit `auto_login: bool` and, when False, a
`next` block guiding the customer to `/app/login` with their email prefilled.
Log level escalated to WARNING so ops sees the JWT-config regression instantly.

These tests are RED-first: they FAIL against the pre-fix code and PASS after.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _clear_signup_bucket(monkeypatch):
    from app.api import public_site as ps

    async def _allow_signup(_ip, _bucket="signup"):
        return None

    monkeypatch.setattr(ps, "_rate_check", _allow_signup)
    ps._RL.clear()
    yield
    ps._RL.clear()


def _stub_signup_side_effects(monkeypatch, cid: str = "c_al"):
    """Mirror pattern from test_p1_audit_fixes_2026_06_27._stub_signup_side_effects."""
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
    # Default: neuter plan provisioning (return True = success, isolated from auto_login).
    monkeypatch.setattr(usage, "activate_plan", lambda c, p, **k: True)
    monkeypatch.setattr(usage, "reset_usage_period", lambda c: True)


def test_signup_normal_path_reports_auto_login_true(client, monkeypatch):
    """GREEN case: token mint succeeds → response has auto_login=True and no `next`."""
    _stub_signup_side_effects(monkeypatch, cid="c_ok")

    r = client.post(
        "/api/public/signup",
        json={
            "business_name": "Auto Login Ok",
            "email": "ok@example.com",
            "password": "secret123",
            "plan": "starter",
        },
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("ok") is True
    assert d.get("auto_login") is True, "auto_login must be explicit True on normal path"
    assert d.get("access_token"), "token must be present on normal path"
    assert d.get("plan_provisioned") is True, "paid plan must report provisioned=True on success"
    assert "next" not in d, "no fallback guidance needed on success"


def test_signup_token_mint_failure_signals_auto_login_false(client, monkeypatch):
    """RED-first: create_access_token raises → response MUST NOT silently succeed.

    Contract:
      - 200 OK with account still created (idempotent password login is intact).
      - `auto_login: False` so FE can branch instead of guessing on null token.
      - `access_token: None` (unchanged truth; caller reads `auto_login` flag).
      - `next: {url: "/app/login", email: <body.email>, reason: "auto_login_unavailable"}`.
    """
    _stub_signup_side_effects(monkeypatch, cid="c_bad")

    import app.api.admin as admin_mod

    def _broken_mint(*a, **k):
        raise RuntimeError("JWT_SECRET missing")

    monkeypatch.setattr(admin_mod, "create_access_token", _broken_mint)

    r = client.post(
        "/api/public/signup",
        json={
            "business_name": "Auto Login Fail",
            "email": "fail@example.com",
            "password": "secret123",
            "plan": "starter",
        },
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("ok") is True, "account creation still succeeds — auth failure is degrade-only"
    assert d.get("access_token") is None, "token honestly null; do not fake a value"
    assert d.get("auto_login") is False, "MUST signal fallback so FE stops the paid flow"
    nxt = d.get("next") or {}
    assert nxt.get("url") == "/app/login", "guide user to login page"
    assert nxt.get("email") == "fail@example.com", "prefill email so re-login is one field"
    assert nxt.get("reason") == "auto_login_unavailable"


def test_signup_token_mint_failure_logs_at_warning_level(client, monkeypatch):
    """Ops signal: token mint failure MUST log at >= WARNING (was DEBUG silent)."""
    _stub_signup_side_effects(monkeypatch, cid="c_warn")

    import app.api.admin as admin_mod

    def _broken_mint(*a, **k):
        raise RuntimeError("kid unavailable")

    monkeypatch.setattr(admin_mod, "create_access_token", _broken_mint)

    from app.api import public_site as ps

    warnings: list[str] = []
    monkeypatch.setattr(
        ps.logger,
        "warning",
        lambda message, *args: warnings.append(str(message) % args if args else str(message)),
    )
    r = client.post(
        "/api/public/signup",
        json={
            "business_name": "Auto Login Warn",
            "email": "warn@example.com",
            "password": "secret123",
            "plan": "starter",
        },
    )
    assert r.status_code == 200, r.text
    # At least one warning-or-higher record from public_site mentioning the failure.
    assert warnings, "expected a WARNING log when auto-login token cannot be minted"
    joined = " ".join(warnings).lower()
    assert "auto-login" in joined or "auto_login" in joined or "token" in joined


# ── Plan provisioning signal tests (2026-07-10 blocker #1 fix) ──


def test_signup_plan_provisioning_failure_signals_false(client, monkeypatch):
    """RED-first: activate_plan returns False → response has plan_provisioned=False,
    log at WARNING, but signup still succeeds (account created)."""
    import app.api.customer_auth as ca
    import app.billing.usage as usage
    from app.marketing import clients_store as cs

    monkeypatch.setattr(
        cs, "add_client", lambda **k: {"id": "c_pp", "business_name": k.get("business_name")}
    )
    monkeypatch.setattr(ca, "login_exists", lambda e: False)
    monkeypatch.setattr(ca, "client_has_login", lambda c: False)
    monkeypatch.setattr(ca, "register_login", lambda *a, **k: {"ok": True})
    monkeypatch.setattr(usage, "activate_plan", lambda c, p, **k: False)  # plan NOT applied
    monkeypatch.setattr(usage, "reset_usage_period", lambda c: False)

    r = client.post(
        "/api/public/signup",
        json={
            "business_name": "Plan Fail",
            "email": "planfail@example.com",
            "password": "secret123",
            "plan": "starter",
        },
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("ok") is True
    assert d.get("plan_provisioned") is False, "MUST signal provisioning failure so ops can fix"


def test_signup_plan_provisioning_raises_signals_false(client, monkeypatch):
    """When activate_plan raises → response has plan_provisioned=False + WARNING log."""
    import app.api.customer_auth as ca
    import app.billing.usage as usage

    monkeypatch.setattr(
        cs, "add_client", lambda **k: {"id": "c_ppr", "business_name": k.get("business_name")}
    )
    monkeypatch.setattr(ca, "login_exists", lambda e: False)
    monkeypatch.setattr(ca, "client_has_login", lambda c: False)
    monkeypatch.setattr(ca, "register_login", lambda *a, **k: {"ok": True})
    monkeypatch.setattr(
        usage, "activate_plan", lambda c, p, **k: (_ for _ in ()).throw(RuntimeError("DB down"))
    )

    from app.api import public_site as ps

    warnings: list[str] = []
    monkeypatch.setattr(
        ps.logger,
        "warning",
        lambda message, *args: warnings.append(str(message) % args if args else str(message)),
    )
    r = client.post(
        "/api/public/signup",
        json={
            "business_name": "Plan Raise",
            "email": "planraise@example.com",
            "password": "secret123",
            "plan": "starter",
        },
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("ok") is True
    assert d.get("plan_provisioned") is False
    assert any("provisioning" in message.lower() for message in warnings), (
        "expected WARNING log when plan provisioning raises"
    )


def test_signup_trial_skips_plan_provisioning(client, monkeypatch):
    """Trial signup MUST NOT call plan provisioning — returns plan_provisioned=False."""
    import app.api.customer_auth as ca
    import app.billing.usage as usage
    from app.marketing import clients_store as cs

    monkeypatch.setattr(
        cs, "add_client", lambda **k: {"id": "c_tr", "business_name": k.get("business_name")}
    )
    monkeypatch.setattr(ca, "login_exists", lambda e: False)
    monkeypatch.setattr(ca, "client_has_login", lambda c: False)
    monkeypatch.setattr(ca, "register_login", lambda *a, **k: {"ok": True})
    # Should never be called for trial — if it is, raise to catch.
    monkeypatch.setattr(
        usage,
        "activate_plan",
        lambda c, p, **k: (_ for _ in ()).throw(AssertionError("trial must not provision")),
    )
    monkeypatch.setattr(
        usage,
        "reset_usage_period",
        lambda c: (_ for _ in ()).throw(AssertionError("trial must not watermark")),
    )

    r = client.post(
        "/api/public/signup",
        json={
            "business_name": "Trial User",
            "email": "trial@example.com",
            "password": "secret123",
            "plan": "trial",
        },
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("ok") is True
    assert d.get("trial") is True
    assert d.get("plan_provisioned") is False, "trial path must skip plan provisioning"
