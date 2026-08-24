"""2FA fail-open hole (onboarding-audit finding, enterprise hardening).

customer_login ka poora TOTP block ek try/except-pass me tha — account 2FA-ENABLED
hone par bhi `create_challenge` ka koi bhi error silently FULL JWT de deta tha
(password-only bypass of 2FA = security hole). Fix:
- account 2FA-enabled + challenge error → fail-CLOSED (503, no bypass)
- is_enabled STATE-check error (2FA status unknown) → documented fail-open
  (no-2FA majority ko infra-error pe lockout nahi) — par ab LOUD log, silent nahi.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

import app.api.customer_auth as ca
from app.platform import customer_totp


@pytest.fixture()
def user(tmp_path, monkeypatch):
    monkeypatch.setattr(ca, "_STORE", str(tmp_path / "auth.jsonl"))
    ca.register_login("c@x.in", "secret123", "cid-1")
    return ca.LoginIn(email="c@x.in", password="secret123")


def test_2fa_enabled_challenge_error_fails_closed(user, monkeypatch):
    """2FA-enabled account par challenge-creation error = 503, NOT a plain JWT."""
    monkeypatch.setattr(customer_totp, "is_enabled", lambda cid: True)

    def _boom(cid):
        raise RuntimeError("totp store down")

    monkeypatch.setattr(customer_totp, "create_challenge", _boom)
    with pytest.raises(HTTPException) as ei:
        asyncio.run(ca.customer_login(user))
    assert ei.value.status_code == 503


def test_2fa_state_error_fails_open_no_lockout(user, monkeypatch):
    """is_enabled hi error de (2FA state unknown) → login proceeds (documented)."""

    def _boom(cid):
        raise RuntimeError("state unreadable")

    monkeypatch.setattr(customer_totp, "is_enabled", _boom)
    res = asyncio.run(ca.customer_login(user))
    assert res.get("access_token")


def test_2fa_enabled_happy_returns_challenge(user, monkeypatch):
    monkeypatch.setattr(customer_totp, "is_enabled", lambda cid: True)
    monkeypatch.setattr(customer_totp, "create_challenge", lambda cid: "chal-tok")
    res = asyncio.run(ca.customer_login(user))
    assert res.get("needs_2fa") is True
    assert res.get("challenge_token") == "chal-tok"
    assert "access_token" not in res
