"""Contract: a customer's billing/login id must canonicalize to the marketing
client id for all MARKETING-content reads/writes, so a UPI-activated customer
(login id == billing id, e.g. Jiya `d79d690f61b3`) sees AND can act on the
content bank generated under her marketing id (`jiya-makeover`), not an
orphaned partial view.

Split-brain root cause fixed 2026-07-19: marketing pipeline keys on the
marketing id; DB/billing/login keys on `d79d690f61b3` (carried in the marketing
record's `billing_client_ids`). Billing/invoice reads must stay on the raw id.

Extended 2026-07-19 (same day): dashboard keystone `_client_record`, approval
banner, and decide-path ownership now also canonicalize — without those, a
billing-alias login could SEE content via portal/content but still could not
approve it (decide_for_client ownership check failed).
"""

import json
import os

from app.marketing import clients_store

MKT_ID = "jiya-makeover"
BILL_ID = "d79d690f61b3"


def _seed_marketing_client(monkeypatch, tmp_path):
    monkeypatch.setattr(
        clients_store, "_CLIENTS_FILE", lambda: str(tmp_path / "marketing_clients.jsonl")
    )
    rec = {
        "id": MKT_ID,
        "business_name": "Jiya Makeover Studio",
        "slug": MKT_ID,
        "niche": "beauty_makeover",
        "plan": "starter",
        "status": "active",
        "billing_client_ids": [BILL_ID],
    }
    path = clients_store._CLIENTS_FILE()
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


def test_client_record_resolves_billing_alias(monkeypatch, tmp_path):
    """Dashboard keystone: _client_record(billing_id) must return the marketing
    record, otherwise content count / plan / onboarding all orphan."""
    _seed_marketing_client(monkeypatch, tmp_path)
    from app.api.customer_dashboard_builders import _client_record

    rec = _client_record(BILL_ID)
    assert rec is not None
    assert rec.get("id") == MKT_ID
    assert rec.get("plan") == "starter"
    # Idempotent for marketing id
    assert (_client_record(MKT_ID) or {}).get("id") == MKT_ID
    # Unknown stays None (no phantom record)
    assert _client_record("unknown-xyz") is None


def test_approval_banner_uses_marketing_id(monkeypatch, tmp_path):
    """Approval banner must count pending under marketing id, not billing id."""
    _seed_marketing_client(monkeypatch, tmp_path)
    from app.api import customer_dashboard_builders as builders
    from app.marketing import content_approval

    monkeypatch.setattr(content_approval, "_FILE", lambda: str(tmp_path / "approvals.jsonl"))
    submitted = content_approval.submit(MKT_ID, {"title": "Bridal look", "caption": "test"})
    assert submitted.get("ok") is True
    assert (submitted.get("approval") or {}).get("id")

    banner = builders._approval_banner(BILL_ID)
    assert banner.show is True
    assert banner.count == 1


def test_customer_can_decide_approval_via_billing_alias(monkeypatch, tmp_path):
    """P1 mutation: customer logged in with billing id MUST be able to approve
    a content item that was submitted under their marketing id. Without
    canonicalization, decide_for_client returns 'approval nahi mila'."""
    _seed_marketing_client(monkeypatch, tmp_path)
    from app.marketing import content_approval

    monkeypatch.setattr(content_approval, "_FILE", lambda: str(tmp_path / "approvals.jsonl"))
    submitted = content_approval.submit(MKT_ID, {"title": "Festive offer", "caption": "sale"})
    assert submitted.get("ok") is True
    approval_id = (submitted.get("approval") or {}).get("id")
    assert approval_id

    # Raw billing id MUST fail ownership (proves the gate exists)
    raw = content_approval.decide_for_client(BILL_ID, approval_id, "approve")
    assert raw.get("ok") is False

    # After canonicalization (what the API endpoint now does) it succeeds
    mcid = clients_store.canonical_client_id(BILL_ID)
    assert mcid == MKT_ID
    decided = content_approval.decide_for_client(mcid, approval_id, "approve")
    assert decided.get("ok") is True


def test_pending_endpoint_sees_marketing_approvals(monkeypatch, tmp_path):
    """customer_pending_approvals must surface marketing-keyed pending rows
    when called with the billing/login alias (mirrors the API canonicalization)."""
    _seed_marketing_client(monkeypatch, tmp_path)
    from app.marketing import content_approval

    monkeypatch.setattr(content_approval, "_FILE", lambda: str(tmp_path / "approvals.jsonl"))
    content_approval.submit(MKT_ID, {"title": "Reel idea", "caption": "before/after"})

    # Billing alias alone finds nothing (proves keying)
    assert content_approval.pending(BILL_ID) == []
    # Canonical path (what the endpoint now uses) finds it
    rows = content_approval.pending(clients_store.canonical_client_id(BILL_ID))
    assert len(rows) == 1
    assert rows[0].get("client_id") == MKT_ID
