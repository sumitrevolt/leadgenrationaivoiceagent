"""ADR-106 — customer billing API must resolve legacy billing-id aliases.

Context (2026-07-16 browser acceptance): jiya-makeover (the only real paying
customer, Starter ₹1,999, invoice INV/2026-27/0001) logged in and saw
"NO PLAN — Free / Trial" + a fresh UPI QR, because her Subscription/Invoice
rows are owned by legacy billing id `d79d690f61b3` while her JWT carries
`jiya-makeover`. ADR-095 fixed this identity split for the alert path via
`billing_client_ids`; `_billing_client_ids()` mirrors it for the billing API.

2026-07-19 hardening: helper now uses `resolve_client` so a billing-alias JWT
(`d79d690f61b3`) also loads the marketing record and returns both ids.

Offline contract tests — no DB, no network.
"""

from __future__ import annotations

from app.api import billing as billing_api

# Known public fixture id (Jiya billing alias) — not a credential.
_BILL_ID = "d79d690f61b3"  # pragma: allowlist secret
_MKT_ID = "jiya-makeover"

_JIYA_REC = {
    "id": _MKT_ID,
    "billing_client_ids": [_BILL_ID],
}


def test_alias_merged_from_clients_store(monkeypatch):
    monkeypatch.setattr(
        "app.marketing.clients_store.resolve_client",
        lambda cid: _JIYA_REC if cid == _MKT_ID else None,
    )
    assert billing_api._billing_client_ids(_MKT_ID) == [_MKT_ID, _BILL_ID]


def test_billing_alias_jwt_also_resolves_both_ids(monkeypatch):
    """Billing-id login must still see marketing + billing ids in the IN-set."""
    monkeypatch.setattr(
        "app.marketing.clients_store.resolve_client",
        lambda cid: _JIYA_REC if cid in (_MKT_ID, _BILL_ID) else None,
    )
    assert billing_api._billing_client_ids(_BILL_ID) == [_BILL_ID, _MKT_ID]


def test_no_aliases_returns_canonical_only(monkeypatch):
    monkeypatch.setattr(
        "app.marketing.clients_store.resolve_client",
        lambda cid: {"id": cid},
    )
    assert billing_api._billing_client_ids("fresh-client") == ["fresh-client"]


def test_unknown_client_returns_canonical(monkeypatch):
    monkeypatch.setattr("app.marketing.clients_store.resolve_client", lambda cid: None)
    assert billing_api._billing_client_ids("ghost") == ["ghost"]


def test_store_failure_fails_open_to_canonical(monkeypatch):
    def boom(cid):
        raise RuntimeError("store unreadable")

    monkeypatch.setattr("app.marketing.clients_store.resolve_client", boom)
    assert billing_api._billing_client_ids(_MKT_ID) == [_MKT_ID]


def test_dedup_and_garbage_aliases(monkeypatch):
    monkeypatch.setattr(
        "app.marketing.clients_store.resolve_client",
        lambda cid: {
            "id": _MKT_ID,
            "billing_client_ids": [cid, "", None, _BILL_ID, _BILL_ID],
        },
    )
    assert billing_api._billing_client_ids(_MKT_ID) == [_MKT_ID, _BILL_ID]


def test_ev_enum_or_str_never_raises():
    """ADR-106 addendum: prod DB had payment_gateway='upi' as a PLAIN STRING
    (manual UPI activation), so `.value` 500'd the first-ever real subscription
    response. `_ev()` must handle enum, str, and None."""
    import enum

    class S(enum.Enum):
        ACTIVE = "active"

    assert billing_api._ev(S.ACTIVE) == "active"
    assert billing_api._ev("upi") == "upi"
    assert billing_api._ev(None) is None


def test_no_direct_dot_value_on_subscription_fields():
    import inspect

    src = inspect.getsource(billing_api)
    for bad in (
        "subscription.status.value",
        "subscription.billing_cycle.value",
        "subscription.payment_gateway.value",
        "sub.status.value",
        "inv.status.value",
    ):
        assert bad not in src, f"{bad} regressed — use _ev() (str-safe)"


def test_every_where_clause_uses_alias_resolution():
    """Regression guard: no customer-facing billing WHERE clause may compare
    client_id by direct equality again (that is the exact bug shipped)."""
    import inspect

    src = inspect.getsource(billing_api)
    for model in ("Subscription", "Invoice", "PaymentMethod", "UsageRecord"):
        assert f"{model}.client_id == client_id" not in src, (
            f"{model} query regressed to direct equality — use "
            "_billing_client_ids(client_id) with .in_()"
        )
    assert src.count("_billing_client_ids(") >= 10


def test_get_invoices_jsonl_uses_alias_set():
    """JSONL GST ledger may store legacy billing id — filter must use aliases."""
    import inspect

    src = inspect.getsource(billing_api.get_invoices)
    assert "alias" in src.lower()
    assert "gst_invoice" in src
    assert 'str(r.get("client_id")) == client_id' not in src
