"""W3.5 — activate_plan emits the customer webhooks it documented but never fired.

`customer_webhooks` supports `payment.received` / `subscription.activated` and even
ships a sync `fire_emit` wrapper "for billing/sync paths" — but no billing code called
it, so a customer's registered webhook never heard about a payment. Fix: when
`activate_plan` provisions a plan (after pay/renew), fire both events (gated by
CUSTOMER_WEBHOOKS inside emit, never-raises).
"""

from __future__ import annotations

from app.billing import usage
from app.marketing import clients_store
from app.platform import customer_webhooks


def test_activate_plan_fires_subscription_and_payment_webhooks(monkeypatch):
    monkeypatch.setattr(clients_store, "get_client", lambda cid: {"id": cid})
    monkeypatch.setattr(clients_store, "update_client", lambda *a, **k: True)

    emitted = []
    monkeypatch.setattr(
        customer_webhooks, "fire_emit", lambda cid, ev, payload: emitted.append((cid, ev, payload))
    )

    ok = usage.activate_plan("client9", "combo", subscription_id="sub_1")
    assert ok is True
    events = [ev for _, ev, _ in emitted]
    assert "subscription.activated" in events, "plan activation must emit subscription.activated"
    assert "payment.received" in events, "plan activation must emit payment.received"
    # payload carries the client + plan for the subscriber
    for cid, _ev, payload in emitted:
        assert cid == "client9"
        assert payload.get("plan") == "combo"


def test_activate_plan_no_emit_when_not_applied(monkeypatch):
    monkeypatch.setattr(
        clients_store, "get_client", lambda cid: None
    )  # unknown client → not applied

    emitted = []
    monkeypatch.setattr(customer_webhooks, "fire_emit", lambda *a, **k: emitted.append(1))

    ok = usage.activate_plan("ghost", "combo")
    assert ok is False
    assert emitted == [], "no webhook when the plan was not applied"
