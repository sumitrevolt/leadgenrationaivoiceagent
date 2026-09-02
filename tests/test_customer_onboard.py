"""S.1 admin customer-onboard endpoint — profile + login in one call.

This is the operator's primary "add new customer" action; tests pin the
contract so a future refactor can't silently break it:
- Returns client_id always
- When email passed: password is returned ONCE in plaintext
- When password not passed: server generates strong random 14-char
- Plan validation rejects garbage
- Profile-only mode (no email) is allowed
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _iso(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Redirect both clients_store + customer_auth to isolated tmp files so
    each test starts clean."""
    from app.api import customer_auth
    from app.marketing import clients_store

    monkeypatch.setattr(clients_store, "_FILE", tmp_path / "clients.jsonl", raising=False)
    monkeypatch.setattr(customer_auth, "_FILE", tmp_path / "customer_logins.jsonl", raising=False)
    # Bypass admin auth in tests — onboard is admin-only, but the dep is the
    # same one already covered by test_billing_auth_idor.py.
    from app.api import customer_onboard

    async def _noop_admin(*a: Any, **kw: Any) -> Any:
        return None

    monkeypatch.setattr(customer_onboard, "require_admin", _noop_admin, raising=False)

    # Clear MAGIC_LINK so the hint is empty (deterministic)
    monkeypatch.delenv("MAGIC_LINK", raising=False)


def _client() -> TestClient:
    # Build the app fresh per-test to pick up the monkeypatched module-level deps.
    from app.main import app

    return TestClient(app)


# --------------------------------------------------------------------------- #
# Schema validation
# --------------------------------------------------------------------------- #
def test_missing_business_name_is_422() -> None:
    r = _client().post(
        "/api/admin/customers/onboard",
        json={"phone": "9876543210"},
    )
    assert r.status_code == 422


def test_short_business_name_is_422() -> None:
    r = _client().post(
        "/api/admin/customers/onboard",
        json={"business_name": "X", "phone": "9876543210"},
    )
    assert r.status_code == 422


def test_invalid_plan_is_422() -> None:
    r = _client().post(
        "/api/admin/customers/onboard",
        json={"business_name": "Sharma Solar", "phone": "9876543210", "plan": "diamond"},
    )
    assert r.status_code == 422


def test_invalid_email_is_422() -> None:
    r = _client().post(
        "/api/admin/customers/onboard",
        json={"business_name": "Sharma Solar", "phone": "9876543210", "email": "not-an-email"},
    )
    assert r.status_code == 422


# --------------------------------------------------------------------------- #
# Happy paths
# --------------------------------------------------------------------------- #
def test_profile_only_no_email_returns_dashboard_url() -> None:
    r = _client().post(
        "/api/admin/customers/onboard",
        json={
            "business_name": "Sharma Solar",
            "niche": "solar",
            "city": "Pune",
            "phone": "9876543210",
            "plan": "trial",
        },
    )
    assert r.status_code == 200
    d = r.json()
    assert d["client_id"]
    assert d["login_email"] == ""
    assert d["password"] == ""
    assert d["customer_dashboard"].endswith(d["client_id"])
    assert d["plan"] == "trial"


def test_with_email_returns_generated_password() -> None:
    r = _client().post(
        "/api/admin/customers/onboard",
        json={
            "business_name": "Sharma Solar",
            "phone": "9876543210",
            "email": "owner@sharmasolar.in",
        },
    )
    assert r.status_code == 200
    d = r.json()
    assert d["login_email"] == "owner@sharmasolar.in"
    assert d["password"]
    assert d["password_generated"] is True
    # Generated password is 14 chars (per _gen_password contract)
    assert len(d["password"]) == 14


def test_with_email_and_custom_password_returns_custom() -> None:
    r = _client().post(
        "/api/admin/customers/onboard",
        json={
            "business_name": "Sharma Solar",
            "phone": "9876543210",
            "email": "owner@sharmasolar.in",
            "password": "my-chosen-password-1",
        },
    )
    assert r.status_code == 200
    d = r.json()
    assert d["password"] == "my-chosen-password-1"
    assert d["password_generated"] is False


def test_login_actually_works_after_onboard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The credentials returned MUST authenticate against /api/customer/login.
    This is the end-to-end property — without it, the form is broken UX."""
    from app.api import customer_auth

    monkeypatch.setattr(customer_auth, "_FILE", tmp_path / "logins.jsonl", raising=False)
    client = _client()
    r = client.post(
        "/api/admin/customers/onboard",
        json={
            "business_name": "Sharma Solar",
            "phone": "9876543211",
            "email": "auth-check@sharmasolar.in",
        },
    )
    d = r.json()
    assert r.status_code == 200
    # Login with the returned credentials (router mounted at /api/customer/auth)
    r2 = client.post(
        "/api/customer/auth/login",
        json={"email": "auth-check@sharmasolar.in", "password": d["password"]},
    )
    assert r2.status_code == 200, r2.text
    payload = r2.json()
    # Either gets a JWT directly (no 2FA) or a needs_2fa marker
    assert "access_token" in payload or payload.get("needs_2fa") is True


# --------------------------------------------------------------------------- #
# Idempotency / re-onboard
# --------------------------------------------------------------------------- #
def test_repeat_onboard_returns_existing_client_id() -> None:
    """Re-onboarding the same phone+business should not create a duplicate
    profile (clients_store dedupes); returns the existing client_id but
    issues a fresh password — operator can use it as a manual password reset."""
    c = _client()
    r1 = c.post(
        "/api/admin/customers/onboard",
        json={"business_name": "Sharma Solar", "phone": "9876543299", "email": "owner@x.com"},
    )
    r2 = c.post(
        "/api/admin/customers/onboard",
        json={"business_name": "Sharma Solar", "phone": "9876543299", "email": "owner@x.com"},
    )
    assert r1.status_code == r2.status_code == 200
    assert r1.json()["client_id"] == r2.json()["client_id"]
    # Fresh password issued
    assert r1.json()["password"] != r2.json()["password"]
