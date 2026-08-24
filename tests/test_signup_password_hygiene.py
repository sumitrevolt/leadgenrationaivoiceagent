"""Loop 13B (2026-07-10): reject the most obvious credential-stuffing passwords.

Blocking these at signup prevents an account whose first login attempt would
tripwire our Loop 8 `login_failed` monitoring — the credential-stuffing detection
signal-to-noise ratio improves. Real customers with `password` / `qwerty` are
indistinguishable from bot signups and are steered toward a stronger choice.
"""

from __future__ import annotations

import pytest

from tests._api_helpers import api_error_message


def _stub(monkeypatch, cid="c_pw"):
    import app.api.customer_auth as ca
    import app.billing.usage as usage
    import app.marketing.clients_store as cs

    monkeypatch.setattr(
        cs, "add_client", lambda **k: {"id": cid, "business_name": k.get("business_name")}
    )
    monkeypatch.setattr(ca, "login_exists", lambda e: False)
    monkeypatch.setattr(ca, "client_has_login", lambda c: False)
    monkeypatch.setattr(ca, "register_login", lambda *a, **k: {})
    monkeypatch.setattr(usage, "activate_plan", lambda c, p, **k: True)
    monkeypatch.setattr(usage, "reset_usage_period", lambda c: True)


@pytest.mark.parametrize(
    ("bad_pw", "expected_hint"),
    [
        ("password", "common"),
        ("Password", "common"),
        ("PASSWORD", "common"),
        ("123456", "common"),
        ("12345678", "common"),
        ("qwerty", "common"),
        ("admin", "6 characters"),  # Pydantic min-length validation runs first.
        ("welcome", "common"),
        ("letmein", "common"),
        ("iloveyou", "common"),
        ("  password  ", "common"),  # trailing whitespace defeat
    ],
)
def test_signup_rejects_common_breached_passwords(client, monkeypatch, bad_pw, expected_hint):
    """Top-N breached password list → 422 with a helpful hint, not silent
    account creation that immediately gets brute-forced."""
    _stub(monkeypatch)
    r = client.post(
        "/api/public/signup",
        json={
            "business_name": "Weak Biz",
            "email": f"weak{hash(bad_pw) % 1000}@example.com",
            "password": bad_pw,
            "plan": "starter",
        },
    )
    assert r.status_code == 422, f"pw={bad_pw!r} should be rejected, got {r.status_code}"
    body = r.json()
    message = api_error_message(body)
    if message == "Request validation failed":
        message = " ".join(error["message"] for error in body["error"]["details"]["errors"])
    message = message.lower()
    assert expected_hint.lower() in message, (
        f"reject message should hint at strength, got: {message!r}"
    )


def test_signup_accepts_reasonable_password(client, monkeypatch):
    """Ordinary 8-char password not in the block-list still passes."""
    _stub(monkeypatch, cid="c_ok_pw")
    r = client.post(
        "/api/public/signup",
        json={
            "business_name": "Ok Biz",
            "email": "okpw@example.com",
            "password": "mySafe#42Word",  # pragma: allowlist secret
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
    body = r.json()
    assert api_error_message(body) == "Request validation failed"
    assert "6 characters" in " ".join(
        error["message"] for error in body["error"]["details"]["errors"]
    )
