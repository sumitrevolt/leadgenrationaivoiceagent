"""Contract: a customer's billing/login id must canonicalize to the marketing
client id for all MARKETING-content reads, so a UPI-activated customer (login
id == billing id, e.g. Jiya `d79d690f61b3`) sees the content bank generated
under her marketing id (`jiya-makeover`), not an orphaned partial view.

Split-brain root cause fixed 2026-07-19: marketing pipeline keys on the
marketing id; DB/billing/login keys on `d79d690f61b3` (carried in the marketing
record's `billing_client_ids`). Billing/invoice reads must stay on the raw id.
"""

import json
import os

from app.marketing import clients_store

MKT_ID = "jiya-makeover"
BILL_ID = "d79d690f61b3"


def _seed_marketing_client(monkeypatch, tmp_path):
    monkeypatch.setattr(clients_store, "_CLIENTS_FILE", str(tmp_path / "marketing_clients.jsonl"))
    rec = {
        "id": MKT_ID,
        "business_name": "Jiya Makeover Studio",
        "slug": MKT_ID,
        "niche": "beauty_makeover",
        "plan": "starter",
        "status": "active",
        "billing_client_ids": [BILL_ID],
    }
    path = clients_store._CLIENTS_FILE
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


def test_canonical_client_id_resolves_billing_alias(monkeypatch, tmp_path):
    _seed_marketing_client(monkeypatch, tmp_path)
    # Billing/login alias -> marketing id
    assert clients_store.canonical_client_id(BILL_ID) == MKT_ID
    assert (clients_store.resolve_client(BILL_ID) or {}).get("id") == MKT_ID
    # Idempotent for the marketing id itself
    assert clients_store.canonical_client_id(MKT_ID) == MKT_ID
    # Unknown id (seed/demo client keyed by its own id) falls back unchanged
    assert clients_store.canonical_client_id("unknown-xyz") == "unknown-xyz"


def test_portal_marketing_cid_helper(monkeypatch, tmp_path):
    _seed_marketing_client(monkeypatch, tmp_path)
    from app.api import customer_auth

    assert customer_auth._marketing_cid(BILL_ID) == MKT_ID
    assert customer_auth._marketing_cid(MKT_ID) == MKT_ID
    assert customer_auth._marketing_cid("unknown-xyz") == "unknown-xyz"


def test_delivery_status_reads_canonical_identity(monkeypatch, tmp_path):
    """customer_delivery_status(billing_id) must read content under the
    marketing id, not the raw billing id."""
    _seed_marketing_client(monkeypatch, tmp_path)
    from app.marketing import product_one_delivery as pod

    seen: dict[str, str] = {}

    def _rec_content(cid):
        seen["content_cid"] = cid
        return []

    monkeypatch.setattr(pod, "_content_items", _rec_content)
    monkeypatch.setattr(pod, "_approvals", lambda cid: [])
    monkeypatch.setattr(pod, "_ledger_summary", lambda cid: {})
    monkeypatch.setattr(pod, "_ledger_events", lambda cid: [])
    monkeypatch.setattr(pod, "manual_events", lambda cid, limit=200: [])
    monkeypatch.setattr(pod, "_ledger_recent_failures", lambda cid: 0)
    monkeypatch.setattr(pod, "_monthly_report_on_disk", lambda cid, client=None: False)
    monkeypatch.setattr(pod, "_gbp_scored_audit", lambda cid: None)

    state = pod.customer_delivery_status(BILL_ID)
    assert state.get("ok") is True
    assert seen.get("content_cid") == MKT_ID
