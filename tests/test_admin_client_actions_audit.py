"""ADR-104 (2026-07-15, Priority 4): password-reset / onboard-scrape endpoint
audit + safety verification.

Both endpoints in app/api/admin_ops.py are admin-only (require_admin),
synthetic-client-only in these tests. Covers:
  - password-reset: 8-char minimum now matches the admin_dashboard.html modal
    (previously only 4 server-side); 404 on missing client; 400 on missing
    email; success writes a delivery_ledger audit event (actor=admin) and
    never logs the password itself.
  - onboard/scrape: 404 on missing client; queues onboarding.auto_onboard as
    a background task (force=True); success writes a delivery_ledger audit
    event (actor=admin).

Pure-python: clients_store / delivery_ledger / customer_auth are all
monkeypatched -- no network, no real DB, no real customer touched.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import BackgroundTasks, HTTPException


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# --------------------------------------------------------------------------- #
# password-reset
# --------------------------------------------------------------------------- #
def test_password_reset_rejects_short_password():
    from app.api import admin_ops

    with pytest.raises(HTTPException) as exc:
        _run(
            admin_ops.client_password_reset(
                "client-1",
                {"password": "short"},  # pragma: allowlist secret
            )
        )
    assert exc.value.status_code == 400
    assert "8" in exc.value.detail


def test_password_reset_rejects_missing_client(monkeypatch):
    from app.api import admin_ops
    from app.marketing import clients_store

    monkeypatch.setattr(clients_store, "get_client", lambda cid: None)

    with pytest.raises(HTTPException) as exc:
        _run(
            admin_ops.client_password_reset(
                "no-such-client",
                {"password": "longenoughpw"},  # pragma: allowlist secret
            )
        )
    assert exc.value.status_code == 404


def test_password_reset_rejects_missing_email(monkeypatch):
    from app.api import admin_ops
    from app.marketing import clients_store

    monkeypatch.setattr(
        clients_store, "get_client", lambda cid: {"id": cid, "business_name": "No Email Biz"}
    )

    with pytest.raises(HTTPException) as exc:
        _run(
            admin_ops.client_password_reset(
                "client-noemail",
                {"password": "longenoughpw"},  # pragma: allowlist secret
            )
        )
    assert exc.value.status_code == 400
    assert "email" in exc.value.detail.lower()


def test_password_reset_success_registers_login_and_logs_audit(tmp_path, monkeypatch):
    from app.api import admin_ops, customer_auth
    from app.marketing import clients_store, delivery_ledger

    monkeypatch.setattr(
        clients_store,
        "get_client",
        lambda cid: {
            "id": cid,
            "business_name": "Sharma Solar",
            "email": "owner@sharmasolar.example",
        },
    )
    monkeypatch.setattr(delivery_ledger, "_LEDGER_DIR", lambda: str(tmp_path / "ledger"))

    calls = []
    monkeypatch.setattr(
        customer_auth,
        "register_login",
        lambda email, password, client_id, **kw: (
            calls.append((email, password, client_id)) or {"ok": True}
        ),
    )

    result = _run(
        admin_ops.client_password_reset(
            "client-42",
            {"password": "NewPassw0rd!"},  # pragma: allowlist secret
        )
    )
    assert result == {"ok": True}
    assert calls == [("owner@sharmasolar.example", "NewPassw0rd!", "client-42")]

    events = delivery_ledger.timeline("client-42")
    assert len(events) == 1
    assert events[0]["event"] == "admin_manual_action"
    assert events[0].get("actor") == "admin"
    assert events[0].get("detail") == "password_reset"
    # The password itself must never end up in the audit trail.
    assert "NewPassw0rd!" not in str(events[0])


def test_password_reset_ledger_failure_is_fail_open(tmp_path, monkeypatch):
    """If the ledger write itself throws, the reset must still succeed --
    audit logging is best-effort and must never block the actual action."""
    from app.api import admin_ops, customer_auth
    from app.marketing import clients_store, delivery_ledger

    monkeypatch.setattr(
        clients_store,
        "get_client",
        lambda cid: {"id": cid, "business_name": "X", "email": "x@example.com"},
    )
    monkeypatch.setattr(customer_auth, "register_login", lambda *a, **kw: {"ok": True})

    def _boom(*a, **kw):
        raise RuntimeError("ledger down")

    monkeypatch.setattr(delivery_ledger, "log_event", _boom)

    result = _run(
        admin_ops.client_password_reset(
            "client-x",
            {"password": "LongEnoughPw1"},  # pragma: allowlist secret
        )
    )
    assert result == {"ok": True}


# --------------------------------------------------------------------------- #
# onboard/scrape
# --------------------------------------------------------------------------- #
def test_onboard_scrape_rejects_missing_client(monkeypatch):
    from app.api import admin_ops
    from app.marketing import clients_store

    monkeypatch.setattr(clients_store, "get_client", lambda cid: None)

    with pytest.raises(HTTPException) as exc:
        _run(admin_ops.client_onboard_scrape("no-such-client", BackgroundTasks()))
    assert exc.value.status_code == 404


def test_onboard_scrape_queues_task_and_logs_audit(tmp_path, monkeypatch):
    from app.api import admin_ops
    from app.marketing import clients_store, delivery_ledger, onboarding

    monkeypatch.setattr(
        clients_store, "get_client", lambda cid: {"id": cid, "business_name": "Verma Gym"}
    )
    monkeypatch.setattr(delivery_ledger, "_LEDGER_DIR", lambda: str(tmp_path / "ledger2"))

    bg = BackgroundTasks()
    result = _run(admin_ops.client_onboard_scrape("client-77", bg))
    assert result == {"ok": True}

    # Background task queued with the right target + force=True, not executed here.
    assert len(bg.tasks) == 1
    task = bg.tasks[0]
    assert task.func is onboarding.auto_onboard
    assert task.args[0] == "client-77"
    assert task.kwargs.get("force") is True
    assert task.kwargs.get("send_welcome") is False

    events = delivery_ledger.timeline("client-77")
    assert len(events) == 1
    assert events[0]["event"] == "admin_manual_action"
    assert events[0].get("actor") == "admin"
    assert events[0].get("detail") == "onboard_rescrape_triggered"
