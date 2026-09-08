"""Sales Autopilot — follow-up selection + inbound reply classification/handling."""

from __future__ import annotations

import pytest

from app.platform.sales_autopilot import followups as followups
from app.platform.sales_autopilot import inbound as inbound
from app.platform.sales_autopilot import policy as policy_mod
from app.platform.sales_autopilot import store as store


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "_DIR", str(tmp_path))
    monkeypatch.setattr(store, "_PROSPECTS_FILE", str(tmp_path / "prospects.json"))
    monkeypatch.setattr(store, "_ATTEMPTS_FILE", str(tmp_path / "attempts.jsonl"))
    monkeypatch.setattr(policy_mod, "_POLICY_DIR", str(tmp_path))
    monkeypatch.setattr(policy_mod, "_POLICY_FILE", str(tmp_path / "policy.json"))
    monkeypatch.setenv("SALES_AUTOPILOT_ENABLED", "1")
    yield


# ---- follow-ups -------------------------------------------------- #
def test_followup_due_after_gap(monkeypatch):
    store.upsert_prospect(
        {"id": "f1", "phone": "+91981", "status": store.STATUS_CONTACTED, "followup_count": 0}
    )
    # Age the record beyond the 48h gap.
    monkeypatch.setattr(followups, "_hours_since", lambda ts: 100.0)
    due = followups.due_followups(channel="whatsapp")
    assert any(d["prospect"]["id"] == "f1" and d["step"] == "followup_1" for d in due)


def test_followup_stops_after_reply(monkeypatch):
    store.upsert_prospect(
        {
            "id": "f2",
            "phone": "+91982",
            "status": store.STATUS_REPLIED,
            "followup_count": 0,
            "reply_count": 1,
        }
    )
    monkeypatch.setattr(followups, "_hours_since", lambda ts: 100.0)
    due = followups.due_followups(channel="whatsapp")
    assert all(d["prospect"]["id"] != "f2" for d in due)


def test_followup_cap_two(monkeypatch):
    store.upsert_prospect(
        {"id": "f3", "phone": "+91983", "status": store.STATUS_FOLLOWUP, "followup_count": 2}
    )
    monkeypatch.setattr(followups, "_hours_since", lambda ts: 1000.0)
    due = followups.due_followups(channel="whatsapp")
    assert all(d["prospect"]["id"] != "f3" for d in due)


# ---- inbound classify -------------------------------------------- #
def test_classify_optout():
    assert inbound.classify_reply("STOP")["category"] == inbound.OPT_OUT
    assert inbound.classify_reply("please unsubscribe")["category"] == inbound.OPT_OUT


def test_classify_demo_and_pricing():
    assert inbound.classify_reply("send me a demo")["category"] == inbound.DEMO_REQUEST
    assert inbound.classify_reply("what is the price?")["category"] == inbound.PRICING_QUESTION


def test_optout_suppresses_fail_closed(monkeypatch):
    store.upsert_prospect({"id": "r1", "phone": "+919812345678", "status": store.STATUS_CONTACTED})
    suppressed = {"n": 0}

    from app.marketing import wa_campaign_runner

    monkeypatch.setattr(
        wa_campaign_runner, "suppress", lambda phone, reason="": suppressed.__setitem__("n", 1)
    )
    res = inbound.handle_inbound("r1", "STOP please")
    assert res["category"] == inbound.OPT_OUT
    assert res["action"] == "suppressed"
    assert suppressed["n"] == 1
    assert store.get_prospect("r1")["status"] == store.STATUS_OPTED_OUT


def test_reply_escalates_unknown_when_dry_run():
    store.upsert_prospect({"id": "r2", "phone": "+91981", "status": store.STATUS_CONTACTED})
    res = inbound.handle_inbound("r2", "who are you exactly")
    # dry-run default ⇒ no auto-reply; escalate to owner.
    assert res["action"] == "escalate_owner"
    assert store.get_prospect("r2")["status"] == store.STATUS_REPLIED


def test_payment_done_hands_off():
    store.upsert_prospect({"id": "r3", "phone": "+91981", "status": store.STATUS_CONTACTED})
    res = inbound.handle_inbound("r3", "payment done, UTR 123456")
    assert res["action"] == "handoff_payment"
