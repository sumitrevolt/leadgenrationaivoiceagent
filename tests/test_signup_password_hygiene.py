"""Loop 13B (2026-07-10): reject the most obvious credential-stuffing passwords.

Blocking these at signup prevents an account whose first login attempt would
tripwire our Loop 8 `login_failed` monitoring — the credential-stuffing detection
signal-to-noise ratio improves. Real customers with `password` / `qwerty` are
indistinguishable from bot signups and are steered toward a stronger choice.
"""

from __future__ import annotations

import pytest


def _stub(monkeypatch, cid="c_pw"):
    import app.api.customer_auth as ca
    import app.marketing.clients_store as cs
    import app.billing.usage as usage

    monkeypatch.setattr(cs, "add_client", lambda **k: {"id": cid, "business_name": k.get("business_name")})
    monkeypatch.setattr(ca, "login_exists", lambda e: False)
    monkeypatch.setattr(ca, "client_has_login", lambda c: False)
    monkeypatch.setattr(ca, "register_login", lambda *a, **k: None)
    monkeypatch.setattr(usage, "activate_plan", lambda c, p, **k: True)
    monkeypatch.setattr(usage, "reset_usage_period", lambda c: True)


@pytest.mark.parametrize("bad_pw", [
    "password", "Password", "PASSWORD",  # case-insensitive
    "123456", "12345678", "qwerty",
    "admin", "welcome", "letmein", "iloveyou",
    "  password  ",  # trailing whitespace defeat
])
def test_signup_rejects_common_breached_passwords(client, monkeypatch, bad_pw):
    """Top-N breached password list → 422 with a helpful hint, not silent
    account creation that immediately gets brute-forced."""
    _stub(monkeypatch)
    r = client.post(
        "/api/public/signup",
        json={
            "business_name": "Weak Biz",
            "email": f"weak{hash(bad_pw)%1000}@example.com",
            "password": bad_pw,
            "plan": "starter",
        },
    )
    assert r.status_code == 422, f"pw={bad_pw!r} should be rejected, got {r.status_code}"
    detail = (r.json().get("detail") or "").lower()
    assert "common" in detail or "alag" in detail or "safer" in detail, (
        f"reject message should hint at strength, got: {detail!r}"
    )


def test_signup_accepts_reasonable_password(client, monkeypatch):
    """Ordinary 8-char password not in the block-list still passes."""
    _stub(monkeypatch, cid="c_ok_pw")
    r = client.post(
        "/api/public/signup",
        json={
            "business_name": "Ok Biz",
            "email": "okpw@example.com",
            "password": "mySafe#42Word",
            "plan": "starter",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json().get("ok") is True


def test_signup_still_rejects_too_short(client, monkeypatch):
    """Pre-existing < 6-char check must survive Loop 13B — order of validation
    keeps it before the block-list."""
    _stub(monkeypatch)
    r = client.post(
        "/api/public/signup",
        json={
            "business_name": "Short",
            "email": "short@example.com",
            "password": "abc",
            "plan": "starter",
        },
    )
    assert r.status_code == 422
    assert "6 characters" in (r.json().get("detail") or "")
