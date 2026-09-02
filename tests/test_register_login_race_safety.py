"""Loop 23 (2026-07-10): register_login race-safe guard against cross-tenant overwrite.

Signup path checks `login_exists(email)` at line ~550 then registers ~70 lines
later. Under load, two concurrent submits with the same email can both pass the
initial check → both call register_login → last-writer wins, leaving one orphan
`clients_store` row (client_id whose credential was overwritten by the winner).

Fix: register_login(allow_reassign=False) refuses to overwrite a row whose
existing client_id differs from the incoming one. Signup path handles the
`email_claimed` return by raising the same 409 the initial dedupe uses.

Admin `set-password` (support/reset scenarios) keeps the default
`allow_reassign=True` so operators can retarget an email to a new client_id.
"""

from __future__ import annotations

import pytest


def test_register_login_refuses_cross_tenant_overwrite(monkeypatch):
    """Simulated race: row for email X exists with client_id A; a second submit
    tries to bind X to client_id B → refused with `email_claimed`."""
    import app.api.customer_auth as ca

    seed = [
        {
            "email": "race@example.com",
            "client_id": "cid_A",
            "password_hash": ca._hash("passA"),
            "created_at": "2026-07-10T00:00:00Z",
        }
    ]
    monkeypatch.setattr(ca, "_read", lambda: list(seed))

    written: list[list[dict]] = []
    monkeypatch.setattr(ca, "_write_all", lambda rows: written.append(list(rows)))

    r = ca.register_login("race@example.com", "passB", "cid_B", allow_reassign=False)
    assert r.get("ok") is False
    assert r.get("error") == "email_claimed"
    assert r.get("client_id") == "cid_A"  # existing owner surfaced for logging
    assert written == [], "MUST NOT rewrite the store — orphan-row prevention"


def test_register_login_same_client_id_is_idempotent(monkeypatch):
    """Same client_id → idempotent overwrite (real password rotation)."""
    import app.api.customer_auth as ca

    seed = [
        {
            "email": "race@example.com",
            "client_id": "cid_A",
            "password_hash": ca._hash("passOld"),
            "created_at": "2026-07-10T00:00:00Z",
        }
    ]
    monkeypatch.setattr(ca, "_read", lambda: list(seed))
    written: list[list[dict]] = []
    monkeypatch.setattr(ca, "_write_all", lambda rows: written.append(list(rows)))

    r = ca.register_login("race@example.com", "passNew", "cid_A", allow_reassign=False)
    assert r.get("ok") is True
    assert len(written) == 1
    assert len(written[0]) == 1
    assert written[0][0]["client_id"] == "cid_A"


def test_register_login_admin_reassign_default_allowed(monkeypatch):
    """Default `allow_reassign=True` (admin set-password) preserves current
    overwrite semantics — support-driven re-targeting stays possible."""
    import app.api.customer_auth as ca

    seed = [
        {
            "email": "race@example.com",
            "client_id": "cid_A",
            "password_hash": ca._hash("passA"),
            "created_at": "2026-07-10T00:00:00Z",
        }
    ]
    monkeypatch.setattr(ca, "_read", lambda: list(seed))
    written: list[list[dict]] = []
    monkeypatch.setattr(ca, "_write_all", lambda rows: written.append(list(rows)))

    r = ca.register_login("race@example.com", "passB", "cid_B")  # default allow_reassign=True
    assert r.get("ok") is True
    assert r.get("client_id") == "cid_B"
    assert len(written) == 1
    assert written[0][0]["client_id"] == "cid_B", "admin path re-targets the credential"


def test_signup_returns_409_on_race_claimed_email(client, monkeypatch):
    """Integration: public_signup path handles the `email_claimed` return by
    raising the same 409 the initial dedupe check uses — no silent hijack."""
    import app.api.customer_auth as ca
    import app.marketing.clients_store as cs
    import app.billing.usage as usage

    # Initial login_exists check passes (row seeded AFTER, simulating race).
    monkeypatch.setattr(ca, "login_exists", lambda e: False)
    monkeypatch.setattr(
        cs, "add_client", lambda **k: {"id": "cid_race", "business_name": k.get("business_name")}
    )
    monkeypatch.setattr(ca, "client_has_login", lambda c: False)
    monkeypatch.setattr(usage, "activate_plan", lambda c, p, **k: True)
    monkeypatch.setattr(usage, "reset_usage_period", lambda c: True)

    # Simulate register_login returning email_claimed (race-lost case).
    monkeypatch.setattr(
        ca,
        "register_login",
        lambda email, pw, cid, allow_reassign=True: {
            "ok": False,
            "error": "email_claimed",
            "email": email,
            "client_id": "cid_other",
        },
    )

    r = client.post(
        "/api/public/signup",
        json={
            "business_name": "Race Loser",
            "email": "race@example.com",
            "password": "secret123",
            "plan": "starter",
        },
    )
    assert r.status_code == 409
    body = r.json()
    message = body.get("detail") or (body.get("error") or {}).get("message") or ""
    assert "already registered" in message.lower()
