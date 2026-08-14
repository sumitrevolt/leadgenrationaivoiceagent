"""Guest UPI bind workflow — resolves the ``approved_but_unbound`` stall (#304).

A guest "maine pay kiya" submission carries no client_id and lands with
``needs_client_bind=True``. Approving it fails closed (no activation, order
still closed) with ``activation_blocked="empty_client_id"``. This suite proves
the operator queue action that recovers it: ``bind_client`` attaches the
verified marketing client (fail-closed: unknown client / cross-tenant re-point
refused / already-activated refused), and the owner's Approve — the single
activation gate — then activates.

Pure python + hermetic: stores (upi, offers), ``clients_store.resolve_client``
and the activation side-effect hooks (usage.activate_plan, onboarding,
deal-won, gst invoice) are monkeypatched — no network/DB/Celery, no real
``data/`` writes.
"""

from __future__ import annotations

import asyncio

import pytest


@pytest.fixture
def up(tmp_path, monkeypatch):
    """upi_payments module with its store + offers store pointed at tmp files."""
    from app.marketing import clients_store, offers
    from app.platform import upi_payments as mod

    monkeypatch.setattr(mod, "_STORE", lambda: str(tmp_path / "upi_payments.json"))
    monkeypatch.setattr(mod, "_notify_admin", lambda *a, **k: None)
    monkeypatch.setattr(offers, "_store", lambda: str(tmp_path / "offers.jsonl"))
    monkeypatch.delenv("UPI_AUTO_ACTIVATE", raising=False)
    monkeypatch.delenv("UPI_AUTO_ACTIVATE_CLIENTS", raising=False)

    def fake_resolve(cid):
        # "cli_real" is the canonical marketing id; "billing-alias" resolves to it.
        if cid in ("cli_real", "billing-alias"):
            return {"id": "cli_real", "name": "Real Client"}
        return None

    monkeypatch.setattr(clients_store, "resolve_client", fake_resolve)
    return mod


@pytest.fixture
def act(up, monkeypatch):
    """Stub the activation + post-activation side effects (no Celery/DB/network)."""
    from app.billing import usage
    from app.platform import upi_payments as upi

    calls: list[tuple] = []

    def fake_activate(cid, plan, **kw):
        calls.append((cid, plan))
        return True

    monkeypatch.setattr(usage, "activate_plan", fake_activate)
    monkeypatch.setattr(usage, "reset_usage_period", lambda cid, **kw: True)
    monkeypatch.setattr(upi, "_trigger_onboarding", lambda cid="": None)
    monkeypatch.setattr(upi, "_mark_deal_won", lambda phone: None)
    monkeypatch.setattr(upi, "_fire_gst_invoice", lambda *a, **k: None)
    return calls


def _guest_submit(up, ref="TXN-GUEST-1", plan="starter", contact="+919000000001"):
    return up.submit_payment("", plan, ref, amount=1999, payer_name="Guest", payer_contact=contact)


def test_guest_submit_lands_unbound(up):
    """Guest submission: pending, needs_client_bind, no client_id, no activation."""
    rec = _guest_submit(up)
    assert rec.get("ok") is True
    assert rec.get("status") == "pending"
    assert rec.get("needs_client_bind") is True
    assert not (rec.get("client_id") or "").strip()
    assert rec.get("auto_activated") is False


def test_approve_unbound_fails_closed_and_bind_then_reapprove_activates(up, act):
    """Owner approve on unbound = fail-closed warning; bind + re-approve activates."""
    sub = _guest_submit(up)

    # 1. Owner approves the guest payment (bank credit confirmed) — must NOT
    #    activate (no identity) and must surface a recoverable state.
    decided = up.decide(sub["id"], True, decided_by="admin")
    assert decided.get("status") == "approved"
    assert decided.get("activation_blocked") == "empty_client_id"
    assert decided.get("needs_client_bind") is True
    assert not decided.get("activated")
    assert "approved_but_unbound" in (decided.get("warning") or "")
    assert act == []
    assert [row["id"] for row in up.list_actionable()] == [sub["id"]]

    # 2. Operator binds the verified client.
    bound = up.bind_client(sub["id"], "cli_real", decided_by="admin")
    assert bound.get("ok") is True
    assert bound.get("client_id") == "cli_real"
    assert bound.get("needs_client_bind") is False
    assert "activation_blocked" not in bound
    assert bound.get("bound_by") == "admin"
    assert bound.get("bound_at")
    assert act == []  # bind itself NEVER activates
    assert [row["id"] for row in up.list_actionable()] == [sub["id"]]

    # 3. Re-approve (owner gate) → activates exactly once.
    final = up.decide(sub["id"], True, decided_by="admin")
    assert final.get("activated") is True
    assert act == [("cli_real", "starter")]
    assert up.list_actionable() == []


def test_actionable_queue_includes_pending_and_approved_unactivated(up, act):
    pending = _guest_submit(up, ref="TXN-ACTION-PENDING")
    approved_unbound = _guest_submit(up, ref="TXN-ACTION-UNBOUND")
    activated = _guest_submit(up, ref="TXN-ACTION-DONE")

    up.decide(approved_unbound["id"], True)
    up.bind_client(activated["id"], "cli_real")
    up.decide(activated["id"], True)

    actionable_ids = [row["id"] for row in up.list_actionable()]
    assert actionable_ids == [pending["id"], approved_unbound["id"]]


def test_approved_activation_failure_stays_actionable_until_retry(up, act, monkeypatch):
    sub = up.submit_payment("cli_real", "starter", "TXN-ACTION-FAILED", amount=1999)
    monkeypatch.setattr(up, "_try_activate", lambda *args, **kwargs: False)

    failed = up.decide(sub["id"], True)

    assert failed.get("activation_blocked") == "activation_failed"
    assert [row["id"] for row in up.list_actionable()] == [sub["id"]]

    monkeypatch.setattr(up, "_try_activate", lambda *args, **kwargs: True)
    recovered = up.decide(sub["id"], True)

    assert recovered.get("activated") is True
    assert "activation_blocked" not in recovered
    assert up.list_actionable() == []


def test_admin_pending_api_returns_full_actionable_queue(up, monkeypatch):
    from app.api import upi_payments as api

    rows = [{"id": "pending"}, {"id": "approved-unactivated"}]
    monkeypatch.setattr(up, "list_actionable", lambda: rows)

    out = asyncio.run(api.upi_pending_list(_user={"role": "admin"}))

    assert out == {"ok": True, "pending": rows}


def test_bind_before_approve_single_owner_gate(up, act):
    """Bind first, then one Approve activates — Approve remains the only gate."""
    sub = _guest_submit(up)
    bound = up.bind_client(sub["id"], "cli_real")
    assert bound.get("ok") is True
    assert act == []

    final = up.decide(sub["id"], True, decided_by="admin")
    assert final.get("activated") is True
    assert act == [("cli_real", "starter")]


def test_duplicate_reapprove_does_not_double_activate(up, act):
    """Re-approving an already-activated submission is a no-op (#240/#241)."""
    sub = _guest_submit(up)
    up.bind_client(sub["id"], "cli_real")
    up.decide(sub["id"], True)
    assert act == [("cli_real", "starter")]

    # Second + third approve: idempotent — no extra activation calls.
    up.decide(sub["id"], True)
    up.decide(sub["id"], True)
    assert act == [("cli_real", "starter")]


def test_bind_resolves_billing_alias_to_canonical_client(up):
    """Binding accepts a billing alias and stores the canonical marketing id."""
    sub = _guest_submit(up)
    bound = up.bind_client(sub["id"], "billing-alias")
    assert bound.get("ok") is True
    assert bound.get("client_id") == "cli_real"


def test_bind_same_client_idempotent(up):
    """Binding the same client twice is a no-op success, not an error."""
    sub = _guest_submit(up)
    first = up.bind_client(sub["id"], "cli_real")
    assert first.get("ok") is True
    second = up.bind_client(sub["id"], "cli_real")
    assert second.get("ok") is True
    assert second.get("client_id") == "cli_real"
    rows = up.list_payments()
    assert len(rows) == 1  # no duplicate record


def test_bind_wrong_client_refused(up):
    """Cross-tenant guard: re-pointing a bound submission to another client is refused."""
    sub = _guest_submit(up)
    up.bind_client(sub["id"], "cli_real")
    out = up.bind_client(sub["id"], "some_other_client")
    assert out.get("ok") is False
    assert out.get("error") == "already_bound_to_other"
    # Original binding untouched.
    rec = up.list_payments()[0]
    assert rec.get("client_id") == "cli_real"


def test_bind_unknown_client_refused(up):
    """Fail-closed: binding to a client that does not exist in the store is refused."""
    sub = _guest_submit(up)
    out = up.bind_client(sub["id"], "ghost-client")
    assert out.get("ok") is False
    assert out.get("error") == "unknown_client"
    rec = up.list_payments()[0]
    assert rec.get("needs_client_bind") is True
    assert not (rec.get("client_id") or "").strip()


def test_bind_missing_client_id_refused(up):
    sub = _guest_submit(up)
    assert up.bind_client(sub["id"], "")["error"] == "client_id_required"
    assert up.bind_client(sub["id"], "   ")["error"] == "client_id_required"


def test_bind_not_found(up):
    assert up.bind_client("nope", "cli_real")["error"] == "not_found"


def test_bind_already_activated_refused(up, act):
    """Binding cannot resurrect a settled (activated) payment."""
    sub = _guest_submit(up)
    up.bind_client(sub["id"], "cli_real")
    up.decide(sub["id"], True)
    assert up.list_payments()[0].get("activated") is True

    out = up.bind_client(sub["id"], "cli_real")
    assert out.get("ok") is True  # same-client idempotent no-op on activated record
    out2 = up.bind_client(sub["id"], "other_client")
    assert out2.get("ok") is False
    assert out2.get("error") == "already_activated"


def test_guest_submit_malformed_order_ref_refused(up):
    """Guest submissions with a bad order reference are refused fail-closed."""
    out = up.submit_payment("", "starter", "TXN-BAD-REF", amount=1999, order_ref="LG-doesnotexist")
    assert out.get("ok") is False
    assert "not payable" in (out.get("error") or "")


def test_guest_submit_with_valid_order_ref_binds_deal(up):
    """Guest submit with a valid offer keeps the order/deal anchor through bind."""
    from app.marketing import offers

    o = offers.issue_offer("deal-guest", "starter")
    out = up.submit_payment("", "starter", "TXN-WITH-REF", amount=1999, order_ref=o["order_ref"])
    assert out.get("ok") is True
    rec = up.list_payments()[-1]
    assert rec.get("order_ref") == o["order_ref"]
    assert rec.get("deal_id") == "deal-guest"
    assert rec.get("needs_client_bind") is True

    bound = up.bind_client(rec["id"], "cli_real")
    assert bound.get("ok") is True
    assert bound.get("deal_id") == "deal-guest"
