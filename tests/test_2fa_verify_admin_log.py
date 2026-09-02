"""Loop 21 (2026-07-10): 2FA verify path emits login_failed for admin visibility.

Loop 8 covered password-only login failures. The 2FA verify step has two failure
modes (invalid challenge, bad TOTP code) that each carry their own attack signal:
- invalid challenge → replay / CSRF probe
- bad TOTP code → targeted 2FA guessing on a known account

Both now emit `login_failed` AutomationLog rows with the failure-mode encoded in
`error_message` + `meta.stage` so admins can distinguish them.
"""

from __future__ import annotations

import pytest


def test_2fa_verify_invalid_challenge_emits_admin_log(client, monkeypatch):
    """Invalid or expired challenge → login_failed with stage=challenge_consume."""
    import app.api.customer_totp as ctt
    import app.platform.customer_totp as ct_mod

    monkeypatch.setattr(ct_mod, "consume_challenge", lambda t: None)

    import app.platform.automation_log_service as als

    captured: list[dict] = []
    monkeypatch.setattr(als, "log_event", lambda **kw: (captured.append(kw), "id")[1])

    r = client.post(
        "/api/customer/2fa/verify",
        json={"challenge_token": "expired-or-fake-token-x1x2x3", "code": "123456"},
    )
    assert r.status_code == 400
    rows = [c for c in captured if c.get("job_type") == "login_failed"]
    assert len(rows) == 1
    row = rows[0]
    assert row.get("error_message") == "invalid_or_expired_2fa_challenge"
    assert row.get("triggered_by") == "customer_2fa_verify"
    assert (row.get("meta_json") or {}).get("stage") == "challenge_consume"


def test_2fa_verify_bad_code_emits_admin_log_with_client_id(client, monkeypatch):
    """Bad TOTP code → login_failed with client_id attribution (targeted-2FA-guess signal)."""
    import app.platform.customer_totp as ct_mod

    monkeypatch.setattr(ct_mod, "consume_challenge", lambda t: "c_targeted")
    monkeypatch.setattr(ct_mod, "verify", lambda cid, code: False)

    import app.platform.automation_log_service as als

    captured: list[dict] = []
    monkeypatch.setattr(als, "log_event", lambda **kw: (captured.append(kw), "id")[1])

    r = client.post(
        "/api/customer/2fa/verify",
        json={"challenge_token": "good-challenge-token-abcdef", "code": "999999"},
    )
    assert r.status_code == 401
    rows = [c for c in captured if c.get("job_type") == "login_failed"]
    assert len(rows) == 1
    row = rows[0]
    assert row.get("client_id") == "c_targeted", (
        "client_id attribution needed for targeted-attack signal"
    )
    assert row.get("error_message") == "bad_2fa_code"
    assert (row.get("meta_json") or {}).get("stage") == "totp_verify"


def test_2fa_verify_success_emits_no_failure_row(client, monkeypatch):
    """Success path MUST NOT emit a failure row."""
    import app.platform.customer_totp as ct_mod

    monkeypatch.setattr(ct_mod, "consume_challenge", lambda t: "c_ok_2fa")
    monkeypatch.setattr(ct_mod, "verify", lambda cid, code: True)

    # Stub the auth-store row lookup + token creation so success returns 200.
    import app.api.customer_auth as ca

    monkeypatch.setattr(
        ca,
        "_read",
        lambda: [{"email": "ok@example.com", "client_id": "c_ok_2fa", "password_hash": "x"}],
    )

    import app.platform.automation_log_service as als

    captured: list[dict] = []
    monkeypatch.setattr(als, "log_event", lambda **kw: (captured.append(kw), "id")[1])

    r = client.post(
        "/api/customer/2fa/verify",
        json={"challenge_token": "good-verify-token-abcdefg1234", "code": "123456"},
    )
    assert r.status_code == 200
    assert r.json().get("access_token")
    failure_rows = [c for c in captured if c.get("job_type") == "login_failed"]
    assert failure_rows == [], f"no failure rows on success: {failure_rows}"
