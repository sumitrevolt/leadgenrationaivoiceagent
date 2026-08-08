"""An approved/auto-activated UPI payment closes its bound offer (#240).

`submit_payment`'s order gate refuses a reference that is not payable right now,
and its comment relies on the offer leaving `issued` "once the owner approves".
Nothing ever performed that transition, so an order stayed payable forever:

    submit(order_ref=X, upi_ref=TXN1) -> approve -> activate   # legitimate
    submit(order_ref=X, upi_ref=TXN2)                          # different ref,
                                                               # duplicate guard
                                                               # keys on upi_ref
    -> approve -> _try_activate AGAIN -> usage period re-zeroed
                                      -> second GST invoice

These tests pin the terminal transition and the fail-closed replay refusal that
depends on it. Reject must NOT close the order — the money never arrived, so a
prospect who really does pay still needs a payable reference.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def env(tmp_path, monkeypatch):
    from app.marketing import offers
    from app.platform import upi_payments

    monkeypatch.setattr(upi_payments, "_STORE", lambda: str(tmp_path / "upi.json"))
    monkeypatch.setattr(offers, "_store", lambda: str(tmp_path / "offers.jsonl"))
    monkeypatch.delenv("UPI_AUTO_ACTIVATE", raising=False)
    monkeypatch.delenv("UPI_AUTO_ACTIVATE_CLIENTS", raising=False)
    # Activation/onboarding/invoice side effects are out of scope here.
    monkeypatch.setattr(upi_payments, "_try_activate", lambda *a, **k: True)
    monkeypatch.setattr(upi_payments, "_trigger_onboarding", lambda *a, **k: None)
    monkeypatch.setattr(upi_payments, "_fire_gst_invoice", lambda *a, **k: None)
    monkeypatch.setattr(upi_payments, "_mark_deal_won", lambda *a, **k: None)
    monkeypatch.setattr(upi_payments, "_notify_admin", lambda *a, **k: None)
    return upi_payments, offers


def test_approve_marks_the_bound_offer_paid(env):
    upi, offers = env
    o = offers.issue_offer("deal1", "starter")

    sub = upi.submit_payment("cli1", "starter", "TXN1", amount=1999, order_ref=o["order_ref"])
    upi.decide(sub["id"], approve=True, decided_by="owner")

    assert offers.get_offer(o["order_ref"])["status"] == offers.STATUS_PAID


def test_paid_order_cannot_be_submitted_again(env):
    """The replay hole: a second upi_ref under the same order must be refused."""
    upi, offers = env
    o = offers.issue_offer("deal1", "starter")

    first = upi.submit_payment("cli1", "starter", "TXN1", amount=1999, order_ref=o["order_ref"])
    upi.decide(first["id"], approve=True, decided_by="owner")

    replay = upi.submit_payment("cli1", "starter", "TXN2", amount=1999, order_ref=o["order_ref"])

    assert replay["ok"] is False
    assert "already_paid" in replay["error"]
    # Exactly one payment row for this order — no second activation candidate.
    bound = [r for r in upi.list_payments() if r.get("order_ref") == o["order_ref"]]
    assert len(bound) == 1


def test_reject_leaves_the_order_payable(env):
    """Rejected claim = money never arrived; the real payer still needs the ref."""
    upi, offers = env
    o = offers.issue_offer("deal1", "starter")

    sub = upi.submit_payment("cli1", "starter", "TXN1", amount=1999, order_ref=o["order_ref"])
    upi.decide(sub["id"], approve=False, decided_by="owner")

    assert offers.get_offer(o["order_ref"])["status"] == offers.STATUS_ISSUED
    payable, reason = offers.resolve_payable(o["order_ref"])
    assert payable is not None and reason == "ok"


def test_approve_closes_order_even_when_client_is_unbound(env):
    """Guest submission: activation is deferred, but the credit still landed."""
    upi, offers = env
    o = offers.issue_offer("deal1", "starter")

    sub = upi.submit_payment("", "starter", "TXN1", amount=1999, order_ref=o["order_ref"])
    out = upi.decide(sub["id"], approve=True, decided_by="owner")

    assert out.get("activation_blocked") == "empty_client_id"
    assert offers.get_offer(o["order_ref"])["status"] == offers.STATUS_PAID


def test_auto_activation_closes_the_order(env, monkeypatch):
    upi, offers = env
    monkeypatch.setenv("UPI_AUTO_ACTIVATE", "1")
    monkeypatch.setenv("UPI_AUTO_ACTIVATE_CLIENTS", "cli1")
    o = offers.issue_offer("deal1", "starter")

    sub = upi.submit_payment("cli1", "starter", "TXN1", amount=1999, order_ref=o["order_ref"])

    assert sub["status"] == "auto_activated"
    assert offers.get_offer(o["order_ref"])["status"] == offers.STATUS_PAID


def test_re_approve_is_idempotent(env):
    upi, offers = env
    o = offers.issue_offer("deal1", "starter")

    sub = upi.submit_payment("cli1", "starter", "TXN1", amount=1999, order_ref=o["order_ref"])
    upi.decide(sub["id"], approve=True, decided_by="owner")
    upi.decide(sub["id"], approve=True, decided_by="owner")

    assert offers.get_offer(o["order_ref"])["status"] == offers.STATUS_PAID


def test_payment_without_order_ref_is_unaffected(env):
    """Pre-#240 behaviour: no reference, no offer store touched, no crash."""
    upi, offers = env

    sub = upi.submit_payment("cli1", "starter", "TXN1", amount=1999)
    out = upi.decide(sub["id"], approve=True, decided_by="owner")

    assert out["status"] == "approved"
    assert "order_ref" not in out
    assert offers.list_offers() == []


def test_offer_store_failure_never_breaks_the_approval(env, monkeypatch):
    upi, offers = env
    o = offers.issue_offer("deal1", "starter")
    sub = upi.submit_payment("cli1", "starter", "TXN1", amount=1999, order_ref=o["order_ref"])

    def boom(*a, **k):
        raise RuntimeError("offer store unavailable")

    monkeypatch.setattr(offers, "mark_status", boom)
    out = upi.decide(sub["id"], approve=True, decided_by="owner")

    assert out["status"] == "approved"
    assert out.get("activated") is True
