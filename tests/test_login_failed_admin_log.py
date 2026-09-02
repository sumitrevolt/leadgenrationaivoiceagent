"""Loop 8 (2026-07-10): admin observability for auth failures / brute-force.

Every failed login emits a `login_failed` AutomationLog row so the admin
Delivery Command Center's Automation Runs panel surfaces credential-stuffing
spikes early (job_type filter shows the RATE, not just a single failure).

Security-critical: MUST NOT leak which factor failed (bad_email vs bad_pw) in
the caller-facing message — user enumeration hole. Log meta records
`known_email` for admin triage but the 401 detail stays uniform.
"""

from __future__ import annotations

import pytest

from tests._api_helpers import api_error_message


def test_login_bad_email_emits_login_failed_row(client, monkeypatch):
    """Unknown email → 401 uniform message + one login_failed log row with
    known_email=False for admin triage."""
    import app.api.customer_auth as ca
    import app.platform.automation_log_service as als

    monkeypatch.setattr(ca, "_find", lambda e: None)

    captured: list[dict] = []
    monkeypatch.setattr(als, "log_event", lambda **kw: (captured.append(kw), "id")[1])

    r = client.post(
        "/api/customer/auth/login",
        json={
            "email": "nonexistent@example.com",
            "password": "whatever",  # pragma: allowlist secret
        },
    )
    assert r.status_code == 401
    # Uniform message MUST NOT reveal which factor failed.
    assert "Invalid email or password" in api_error_message(r)

    rows = [c for c in captured if c.get("job_type") == "login_failed"]
    assert len(rows) == 1, f"expected exactly 1 login_failed row, got {len(rows)}"
    row = rows[0]
    assert row.get("status") == "failed"
    assert row.get("triggered_by") == "customer_login"
    assert row.get("error_message") == "invalid_creds", "no factor leak in log either"
    meta = row.get("meta_json") or {}
    assert meta.get("email") == "nonexistent@example.com"
    assert meta.get("known_email") is False, "admin triage: unknown email vs bad password"


def test_login_bad_password_emits_login_failed_row(client, monkeypatch):
    """Known email + wrong password → same uniform 401 + log row with
    known_email=True so admin can spot credential stuffing on real accounts."""
    import app.api.customer_auth as ca
    import app.platform.automation_log_service as als

    monkeypatch.setattr(
        ca,
        "_find",
        lambda e: {
            "email": e,
            "client_id": "c_known",
            "password_hash": "pbkdf2$120000$deadbeef$abcd",  # pragma: allowlist secret
        },
    )
    monkeypatch.setattr(ca, "_verify", lambda pw, stored: False)

    captured: list[dict] = []
    monkeypatch.setattr(als, "log_event", lambda **kw: (captured.append(kw), "id")[1])

    r = client.post(
        "/api/customer/auth/login",
        json={"email": "known@example.com", "password": "wrong"},  # pragma: allowlist secret
    )
    assert r.status_code == 401
    assert "Invalid email or password" in api_error_message(r)

    rows = [c for c in captured if c.get("job_type") == "login_failed"]
    assert len(rows) == 1
    meta = rows[0].get("meta_json") or {}
    assert meta.get("known_email") is True, "admin needs to distinguish stuffing vs random probes"


def test_login_success_emits_no_failure_log(client, monkeypatch):
    """Successful login MUST NOT emit a failure row (no false positives in the
    admin panel). Also verifies the success path is untouched by Loop 8."""
    import app.api.customer_auth as ca
    import app.platform.automation_log_service as als
    import app.platform.customer_totp as totp

    monkeypatch.setattr(
        ca,
        "_find",
        lambda e: {
            "email": e,
            "client_id": "c_ok",
            "password_hash": "stored",  # pragma: allowlist secret
        },
    )
    monkeypatch.setattr(ca, "_verify", lambda pw, stored: True)
    monkeypatch.setattr(totp, "is_enabled", lambda cid: False)

    captured: list[dict] = []
    monkeypatch.setattr(als, "log_event", lambda **kw: (captured.append(kw), "id")[1])

    r = client.post(
        "/api/customer/auth/login",
        json={"email": "ok@example.com", "password": "right"},  # pragma: allowlist secret
    )
    assert r.status_code == 200
    assert r.json().get("access_token"), "success path unchanged"

    failure_rows = [c for c in captured if c.get("job_type") == "login_failed"]
    assert failure_rows == [], f"no failure rows on success: {failure_rows}"
