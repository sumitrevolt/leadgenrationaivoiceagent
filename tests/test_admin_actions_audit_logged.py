"""Regression guard for ADR-043's follow-up finding: `upi/activate` and
`clients/{cid}/status` only logged to the informal team feed (`log_event`),
never the formal `AuditLog` DB table `/api/admin/audit-logs` reads — so the
planned admin "view audit log" tab would be blind to approve-payment and
pause-automation, the two most sensitive of the six planned admin actions
(security-auditor audit finding #2, 2026-07-07).

Mirrors tests/test_impersonation.py's pattern: monkeypatch the module-level
`log_audit` reference to a fake async recorder and call the route function
directly (no real DB/app needed) — confirms the audit call fires with the
right action/resource/severity, and that a failing audit write never blocks
the actual operation (mirrors impersonation.py's own best-effort contract).
"""

from __future__ import annotations

import pytest


class _FakeAdmin:
    id = "admin-1"
    email = "boss@leadsgenai.in"


class _FakeReq:
    def __init__(self, ip="9.9.9.9"):
        self.client = type("C", (), {"host": ip})()


@pytest.mark.asyncio
async def test_set_client_status_audits(monkeypatch):
    from app.api import clients

    monkeypatch.setattr(clients.clients_store, "set_status", lambda cid, status: True)

    audited = {}

    async def _fake_audit(db, **kw):
        audited.update(kw)

    monkeypatch.setattr(clients, "log_audit", _fake_audit)

    out = await clients.set_client_status(
        "cli9",
        clients.StatusRequest(status="paused"),
        _FakeReq(),
        current_user=_FakeAdmin(),
        db=object(),
    )

    assert out == {"updated": True, "status": "paused"}
    assert audited["action"] == "client.status_change"
    assert audited["resource_type"] == "client"
    assert audited["resource_id"] == "cli9"
    assert audited["new_value"] == {"status": "paused"}
    assert audited["severity"] == "warning"
    assert audited["ip_address"] == "9.9.9.9"


@pytest.mark.asyncio
async def test_set_client_status_succeeds_even_if_audit_write_fails(monkeypatch):
    """Audit is best-effort — a broken AuditLog insert must never block pausing
    a customer's automation (matches impersonation.py's own contract)."""
    from app.api import clients

    monkeypatch.setattr(clients.clients_store, "set_status", lambda cid, status: True)

    async def _boom(db, **kw):
        raise RuntimeError("db down")

    monkeypatch.setattr(clients, "log_audit", _boom)

    out = await clients.set_client_status(
        "cli9",
        clients.StatusRequest(status="active"),
        _FakeReq(),
        current_user=_FakeAdmin(),
        db=object(),
    )
    assert out == {"updated": True, "status": "active"}


@pytest.mark.asyncio
async def test_upi_activate_audits(monkeypatch):
    from app.api import admin_ops
    from app.billing import usage as usage_mod
    from app.marketing import clients_store

    monkeypatch.setattr(
        usage_mod, "activate_plan", lambda cid, plan, ensure_subscription=True: None
    )
    monkeypatch.setattr(
        clients_store, "get_client", lambda cid: {"client_id": cid, "email": "c@x.com"}
    )
    monkeypatch.setattr(clients_store, "update_client", lambda cid, **kw: None)

    audited = {}

    async def _fake_audit(db, **kw):
        audited.update(kw)

    monkeypatch.setattr(admin_ops, "log_audit", _fake_audit)

    body = admin_ops.UpiActivateReq(client_id="cli42", plan="advanced", clear_trial=True)
    out = await admin_ops.upi_activate(body, _FakeReq(), _user=_FakeAdmin(), db=object())

    assert out["ok"] is True
    assert out["client_id"] == "cli42"
    assert audited["action"] == "payment.approve"
    assert audited["resource_type"] == "client"
    assert audited["resource_id"] == "cli42"
    assert audited["new_value"]["plan"] == "advanced"
    assert audited["severity"] == "warning"


@pytest.mark.asyncio
async def test_upi_activate_succeeds_even_if_audit_write_fails(monkeypatch):
    """Audit is best-effort — a broken AuditLog insert must never block a
    manually-verified payment activation."""
    from app.api import admin_ops
    from app.billing import usage as usage_mod
    from app.marketing import clients_store

    monkeypatch.setattr(
        usage_mod, "activate_plan", lambda cid, plan, ensure_subscription=True: None
    )
    monkeypatch.setattr(
        clients_store, "get_client", lambda cid: {"client_id": cid, "email": "c@x.com"}
    )
    monkeypatch.setattr(clients_store, "update_client", lambda cid, **kw: None)

    async def _boom(db, **kw):
        raise RuntimeError("db down")

    monkeypatch.setattr(admin_ops, "log_audit", _boom)

    body = admin_ops.UpiActivateReq(client_id="cli42", plan="advanced", clear_trial=True)
    out = await admin_ops.upi_activate(body, _FakeReq(), _user=_FakeAdmin(), db=object())
    assert out["ok"] is True
