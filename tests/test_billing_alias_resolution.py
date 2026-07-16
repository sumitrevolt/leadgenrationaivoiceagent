"""ADR-106 — customer billing API must resolve legacy billing-id aliases.

Context (2026-07-16 browser acceptance): jiya-makeover (the only real paying
customer, Starter ₹1,999, invoice INV/2026-27/0001) logged in and saw
"NO PLAN — Free / Trial" + a fresh UPI QR, because her Subscription/Invoice
rows are owned by legacy billing id `d79d690f61b3` while her JWT carries
`jiya-makeover`. ADR-095 fixed this identity split for the alert path via
`billing_client_ids`; `_billing_client_ids()` mirrors it for the billing API.

Offline contract tests — no DB, no network.
"""

from __future__ import annotations

import pytest

from app.api import billing as billing_api


def test_alias_merged_from_clients_store(monkeypatch):
    monkeypatch.setattr(
        "app.marketing.clients_store.get_client",
        lambda cid: {"id": cid, "billing_client_ids": ["d79d690f61b3"]},
    )
    assert billing_api._billing_client_ids("jiya-makeover") == [
        "jiya-makeover",
        "d79d690f61b3",
    ]


def test_no_aliases_returns_canonical_only(monkeypatch):
    monkeypatch.setattr(
        "app.marketing.clients_store.get_client",
        lambda cid: {"id": cid},
    )
    assert billing_api._billing_client_ids("fresh-client") == ["fresh-client"]


def test_unknown_client_returns_canonical(monkeypatch):
    monkeypatch.setattr("app.marketing.clients_store.get_client", lambda cid: None)
    assert billing_api._billing_client_ids("ghost") == ["ghost"]


def test_store_failure_fails_open_to_canonical(monkeypatch):
    def boom(cid):
        raise RuntimeError("store unreadable")

    monkeypatch.setattr("app.marketing.clients_store.get_client", boom)
    assert billing_api._billing_client_ids("jiya-makeover") == ["jiya-makeover"]


def test_dedup_and_garbage_aliases(monkeypatch):
    monkeypatch.setattr(
        "app.marketing.clients_store.get_client",
        lambda cid: {"billing_client_ids": [cid, "", None, "d79d690f61b3", "d79d690f61b3"]},
    )
    assert billing_api._billing_client_ids("jiya-makeover") == [
        "jiya-makeover",
        "d79d690f61b3",
    ]


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
    assert src.count("_billing_client_ids(client_id)") >= 10
