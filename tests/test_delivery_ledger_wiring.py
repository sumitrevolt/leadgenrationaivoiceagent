"""Each of these tests monkeypatches app.platform.delivery_ledger.log_event at
the call site and asserts it fires with the right event_type/client_id — the
same style already used in tests/test_call_event_client_id.py for
app.platform.team.log_event."""

import pytest


def test_add_client_logs_customer_created(monkeypatch, tmp_path):
    from app.marketing import clients_store

    monkeypatch.setattr(clients_store, "_CLIENTS_FILE", str(tmp_path / "clients.jsonl"))
    events = []
    monkeypatch.setattr(
        "app.platform.delivery_ledger.log_event",
        lambda client_id, event_type, **kw: events.append((client_id, event_type)),
    )
    rec = clients_store.add_client(business_name="Test Biz", niche="solar", phone="9812345678")
    assert rec.get("id")
    assert (rec["id"], "customer_created") in events
