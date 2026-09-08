"""Loop 19 (2026-07-10): customer self-serve password change.

Contract:
- `require_customer` gates the endpoint (JWT sub=client_id is authoritative).
- Old password verified against JSONL store via constant-time _verify.
- New password rejected if in Loop 13B breached-password block-list.
- New password rejected if identical to old (hint at mistake).
- On success: JSONL row updated + `password_changed` AutomationLog emitted.
- On failure: `password_change_failed` AutomationLog emitted for brute-force
  monitoring (same pattern as Loop 8's login_failed).
"""

from __future__ import annotations

import pytest

from tests._api_helpers import api_error_message


@pytest.fixture(autouse=True)
def _override_customer_auth(monkeypatch):
    """Force `require_customer` to return a known client_id for these tests."""
    from app.api.customer_auth import require_customer
    from app.main import app

    app.dependency_overrides[require_customer] = lambda: "c_pwtest"
    yield
    app.dependency_overrides.pop(require_customer, None)


def _stub_store_row(monkeypatch, email: str = "u@example.com"):
    """Seed the store with one customer row."""
    import app.api.customer_auth as ca

    row = {
        "email": email,
        "client_id": "c_pwtest",
        "password_hash": ca._hash("oldPass123!"),
    }
    monkeypatch.setattr(ca, "_read", lambda: [row])
    captured: dict = {}

    def _mock_reg(e, p, c, **kw):
        captured.update(email=e, password=p, client_id=c)
        return {"ok": True}

    monkeypatch.setattr(ca, "register_login", _mock_reg)
    return captured


def test_change_password_happy_path_updates_store_and_logs(client, monkeypatch):
    captured = _stub_store_row(monkeypatch)

    import app.platform.automation_log_service as als

    log_rows: list[dict] = []
    monkeypatch.setattr(als, "log_event", lambda **kw: (log_rows.append(kw), "id")[1])

    r = client.post(
        "/api/customer/auth/change-password",
        json={
            "old_password": "oldPass123!",  # pragma: allowlist secret
            "new_password": "newerPass456$",  # pragma: allowlist secret
        },
    )
    assert r.status_code == 200, r.text
    assert r.json().get("ok") is True

    assert captured.get("password") == "newerPass456$", "store MUST be updated with new pw"
    assert captured.get("email") == "u@example.com"

    success_rows = [x for x in log_rows if x.get("job_type") == "password_changed"]
    assert len(success_rows) == 1
    assert success_rows[0].get("client_id") == "c_pwtest"


def test_change_password_rejects_wrong_old_password_with_admin_log(client, monkeypatch):
    _stub_store_row(monkeypatch)

    import app.platform.automation_log_service as als

    log_rows: list[dict] = []
    monkeypatch.setattr(als, "log_event", lambda **kw: (log_rows.append(kw), "id")[1])

    r = client.post(
        "/api/customer/auth/change-password",
        json={"old_password": "WRONG", "new_password": "newerPass456$"},  # pragma: allowlist secret
    )
    assert r.status_code == 401
    fail_rows = [x for x in log_rows if x.get("job_type") == "password_change_failed"]
    assert len(fail_rows) == 1, "brute-force monitor row must be emitted"
    assert fail_rows[0].get("error_message") == "invalid_old_password"


def test_change_password_rejects_breached_new_password(client, monkeypatch):
    _stub_store_row(monkeypatch)

    r = client.post(
        "/api/customer/auth/change-password",
        json={
            "old_password": "oldPass123!",  # pragma: allowlist secret
            "new_password": "password",  # pragma: allowlist secret
        },
    )
    assert r.status_code == 422
    assert "common" in api_error_message(r).lower()


def test_change_password_rejects_reuse_of_old_password(client, monkeypatch):
    _stub_store_row(monkeypatch)

    r = client.post(
        "/api/customer/auth/change-password",
        json={
            "old_password": "oldPass123!",  # pragma: allowlist secret
            "new_password": "oldPass123!",  # pragma: allowlist secret
        },
    )
    assert r.status_code == 422
    assert "alag" in api_error_message(r).lower()


def test_change_password_returns_409_when_no_credential_row(client, monkeypatch):
    """Edge: legitimate JWT but no matching credential row (legacy account or
    store corruption). MUST NOT 500 — hint the customer toward support."""
    import app.api.customer_auth as ca

    monkeypatch.setattr(ca, "_read", lambda: [])  # empty store

    r = client.post(
        "/api/customer/auth/change-password",
        json={"old_password": "any", "new_password": "newerPass456$"},  # pragma: allowlist secret
    )
    assert r.status_code == 409
    assert "support" in api_error_message(r).lower()
