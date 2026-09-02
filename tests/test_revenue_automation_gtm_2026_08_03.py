"""World-class revenue automation — refill, pay-truth, inquiry Hot Queue bridge."""

from __future__ import annotations

import json
import types
from datetime import datetime, timedelta, timezone

import pytest


@pytest.fixture()
def sap_dir(tmp_path, monkeypatch):
    from app.platform.sales_autopilot import store

    d = tmp_path / "sales_autopilot"
    d.mkdir()
    monkeypatch.setattr(store, "_DIR", str(d))
    monkeypatch.setattr(store, "_PROSPECTS_FILE", str(d / "prospects.json"))
    monkeypatch.setattr(store, "_ATTEMPTS_FILE", str(d / "attempts.jsonl"))
    return d


def test_refill_disabled_by_default(sap_dir, monkeypatch):
    from app.platform.sales_autopilot import refill

    monkeypatch.delenv("SALES_AUTOPILOT_REFILL", raising=False)
    out = refill.refill_from_prospector()
    assert out["enabled"] is False
    assert out.get("skip_reason") == "refill_disabled"
    assert out["upserted"] == 0


def test_refill_upserts_and_dedupes(sap_dir, monkeypatch):
    from app.platform.sales_autopilot import refill, store

    monkeypatch.setenv("SALES_AUTOPILOT_REFILL", "1")
    monkeypatch.setenv("SALES_AUTOPILOT_REFILL_CAP", "5")
    monkeypatch.setenv("SALES_AUTOPILOT_REFILL_MIN_SCORE", "40")

    rows = [
        {
            "id": "p-hot-1",
            "business_name": "Hot Salon",
            "phone": "+919811112222",
            "email": "hot@example.com",
            "city": "Pune",
            "niche": "beauty_makeover",
            "status": "ready",
            "lead_score": 80,
            "is_hot_lead": True,
            "found_at": "2026-08-03T10:00:00Z",
        },
        {
            "id": "p-low",
            "business_name": "Low Score",
            "phone": "+919833334444",
            "email": "low@example.com",
            "status": "ready",
            "lead_score": 10,
            "found_at": "2026-08-03T10:01:00Z",
        },
        {
            "id": "p-dup-phone",
            "business_name": "Dup Phone",
            "phone": "9811112222",
            "email": "other@example.com",
            "status": "ready",
            "lead_score": 90,
            "found_at": "2026-08-03T10:02:00Z",
        },
    ]

    def _list(status=None, limit=100):
        out = list(rows)
        if status:
            out = [r for r in out if r.get("status") == status]
        return out[:limit]

    monkeypatch.setattr("app.platform.prospector.list_prospects", _list)

    first = refill.refill_from_prospector()
    assert first["upserted"] == 1
    assert store.get_prospect("p-hot-1")["status"] == store.STATUS_NEW
    assert store.get_prospect("p-hot-1")["source"] == "prospector_refill"

    second = refill.refill_from_prospector()
    assert second["upserted"] == 0
    assert second["skipped_dup"] >= 1


def test_refill_force_bypasses_flag(sap_dir, monkeypatch):
    from app.platform.sales_autopilot import refill

    monkeypatch.delenv("SALES_AUTOPILOT_REFILL", raising=False)
    monkeypatch.setattr("app.platform.prospector.list_prospects", lambda status=None, limit=100: [])
    out = refill.refill_from_prospector(force=True)
    assert out.get("skip_reason") != "refill_disabled"
    assert out["forced"] is True


def test_pay_truth_demotes_converted_without_ledger(sap_dir, monkeypatch):
    from app.platform.sales_autopilot import pay_truth, store

    store.upsert_prospect(
        {
            "id": "estique-like",
            "name": "Fake Converted",
            "phone": "+919700000001",
            "status": store.STATUS_CONVERTED,
            "converted_client_id": "deadbeef0001",
            "consent_basis": "manual",
        }
    )
    monkeypatch.setattr(
        pay_truth,
        "has_payment_proof",
        lambda cid: {"paid": False, "client_id": cid, "via": None},
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "app.integrations.ntfy",
        types.SimpleNamespace(push_bg=lambda *a, **k: None),
    )

    res = pay_truth.reconcile_pay_truth(chase=False)
    assert res["demoted"] == 1
    assert store.get_prospect("estique-like")["status"] == store.STATUS_AWAITING_PAYMENT


def test_pay_truth_restores_when_ledger_exists(sap_dir, monkeypatch):
    from app.platform.sales_autopilot import pay_truth, store

    store.upsert_prospect(
        {
            "id": "paid-one",
            "name": "Paid Biz",
            "status": store.STATUS_AWAITING_PAYMENT,
            "converted_client_id": "paidcid001",
            "consent_basis": "manual",
        }
    )
    monkeypatch.setattr(
        pay_truth,
        "has_payment_proof",
        lambda cid: {"paid": True, "client_id": cid, "via": "invoice"},
    )
    res = pay_truth.reconcile_pay_truth(chase=False)
    assert res["restored"] == 1
    rec = store.get_prospect("paid-one")
    assert rec["status"] == store.STATUS_CONVERTED
    assert rec.get("payment_verified") is True


def test_enrich_prospect_revenue_status(sap_dir, monkeypatch):
    from app.platform.sales_autopilot import pay_truth, store

    rec = store.upsert_prospect(
        {
            "id": "x1",
            "status": store.STATUS_CONVERTED,
            "converted_client_id": "c1",
        }
    )
    monkeypatch.setattr(
        pay_truth,
        "has_payment_proof",
        lambda cid: {"paid": False, "client_id": cid},
    )
    en = pay_truth.enrich_prospect(rec)
    assert en["revenue_status"] == "awaiting_payment"
    assert en["payment_verified"] is False


def test_inquiry_bridge_platform_only(tmp_path, monkeypatch):
    from app.platform import inquiry_hq_bridge as br
    from app.platform import reply_agent as ra

    drafts = tmp_path / "reply_drafts.jsonl"
    monkeypatch.setattr(ra, "_DRAFTS_FILE", str(drafts))

    skip = br.bridge_inquiry_to_hot_queue(
        {"client_id": "cust1", "phone": "9876543210", "business_name": "X"}
    )
    assert skip.get("skipped") == "customer_owned"

    ok = br.bridge_inquiry_to_hot_queue(
        {
            "phone": "+919876543210",
            "business_name": "Platform Lead",
            "message": "Demo chahiye",
            "at": "2026-08-03T12:00:00+00:00",
        }
    )
    assert ok.get("ok") is True
    lines = drafts.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    card = json.loads(lines[0])
    assert card["channel"] == "inquiry"
    assert card["intent"] == "interested"
    assert "leadsgenai.in/pricing" in card["draft"]

    again = br.bridge_inquiry_to_hot_queue(
        {
            "phone": "+919876543210",
            "business_name": "Platform Lead",
            "at": "2026-08-03T12:05:00+00:00",
        }
    )
    assert again.get("skipped") == "already_queued"


def test_hot_queue_includes_inquiry_channel(tmp_path, monkeypatch):
    from app.platform import reply_agent as ra

    drafts = tmp_path / "reply_drafts.jsonl"
    monkeypatch.setattr(ra, "_DRAFTS_FILE", str(drafts))
    monkeypatch.setattr(ra, "_full_prospect_map", lambda: {})
    ra.enqueue_action_card(
        {
            "channel": "inquiry",
            "from": "9876543210",
            "phone": "9876543210",
            "intent": "interested",
            "draft": "hello",
            "text": "want demo",
            "business_name": "Test",
            "at": "2026-08-03T12:00:00+00:00",
        }
    )
    monkeypatch.setattr(
        "app.platform.sales_autopilot.pay_truth.unpaid_chase_cards",
        lambda limit=50: [],
    )
    q = ra.hot_queue(limit=10)
    assert any(r.get("channel") == "inquiry" for r in q)


def test_speed_to_lead_summary_has_5min_fields(monkeypatch):
    from app.platform import speed_to_lead as stl

    rows = [
        {"phone": "9876543210", "at": "2026-08-01T10:00:00+00:00"},
        {"phone": "9876543211", "at": "2026-08-01T11:00:00+00:00"},
    ]
    monkeypatch.setattr(
        stl,
        "_read_jsonl",
        lambda path: rows if "inquir" in str(path).replace("\\", "/") else [],
    )

    def _evidence():
        t0 = datetime.fromisoformat("2026-08-01T10:00:00+00:00").timestamp()
        t1 = datetime.fromisoformat("2026-08-01T11:00:00+00:00").timestamp()
        return {
            "9876543210": [(t0 + 90, "alert")],
            "9876543211": [(t1 + 400, "dialer_call")],
        }

    monkeypatch.setattr(stl, "_evidence_epochs", _evidence)
    s = stl.summary(30)
    assert s["ok"] is True
    assert "under_5min_pct" in s
    assert "sla_5min_ok" in s
    assert s["world_class_target_seconds"] == 300
    assert s["under_5min_pct"] == 50.0


def test_eligibility_blocks_awaiting_payment(sap_dir, monkeypatch):
    from app.platform.sales_autopilot import eligibility as elig
    from app.platform.sales_autopilot import policy as policy_mod
    from app.platform.sales_autopilot import store

    monkeypatch.setattr(policy_mod, "_POLICY_DIR", str(sap_dir))
    monkeypatch.setattr(policy_mod, "_POLICY_FILE", str(sap_dir / "policy.json"))
    monkeypatch.setenv("SALES_AUTOPILOT_ENABLED", "1")
    monkeypatch.setenv("SALES_AUTOPILOT_EMAIL_ENABLED", "1")
    monkeypatch.setenv("SALES_AUTOPILOT_DRY_RUN", "1")
    monkeypatch.setattr(elig, "_owner_kill", lambda name: False)
    monkeypatch.setattr(elig, "_canonical_suppressed", lambda *a, **k: False)
    monkeypatch.setattr(elig, "_is_suppressed", lambda p: False)
    monkeypatch.setattr(
        elig,
        "_now_ist",
        lambda: datetime(2026, 7, 24, 12, tzinfo=timezone(timedelta(hours=5, minutes=30))),
    )
    store.upsert_prospect(
        {
            "id": "await1",
            "email": "a@b.com",
            "status": store.STATUS_AWAITING_PAYMENT,
            "consent_basis": "manual",
        }
    )
    res = elig.evaluate(
        store.get_prospect("await1"),
        channel="email",
        step=elig.STEP_FOLLOWUP_1,
    )
    assert res["decision"] == elig.INELIGIBLE
    assert "already_converted" in res["reason_codes"]


def test_upi_approve_empty_client_refuses_activate(tmp_path, monkeypatch):
    from app.platform import upi_payments as upi

    store_path = tmp_path / "upi_payments.json"
    store_path.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(upi, "_STORE", lambda: str(store_path))
    monkeypatch.setattr(upi, "_notify_admin", lambda *a, **k: None)

    rec = upi.submit_payment("", "starter", "UTRTEST123", amount=1999)
    assert rec.get("ok") is True
    assert rec.get("needs_client_bind") is True
    decided = upi.decide(rec["id"], True, decided_by="test")
    assert decided.get("activation_blocked") == "empty_client_id"
    assert not decided.get("activated")


def test_refill_flag_in_registry():
    from app.api.automation_flags import AUTOMATION_FLAGS

    assert "SALES_AUTOPILOT_REFILL" in AUTOMATION_FLAGS
