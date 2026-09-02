"""Sales Autopilot — Estique protection regression.

Owner already manually contacted Estique. The engine must NEVER auto-send the initial
touch again: eligibility returns OWNER_EXCEPTION_REQUIRED and send BLOCKS it.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.platform.sales_autopilot import eligibility as elig
from app.platform.sales_autopilot import policy as policy_mod
from app.platform.sales_autopilot import send as send_mod
from app.platform.sales_autopilot import store as store

_MIDDAY = datetime(2026, 7, 24, 12, tzinfo=timezone(timedelta(hours=5, minutes=30)))


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "_DIR", str(tmp_path))
    monkeypatch.setattr(store, "_PROSPECTS_FILE", str(tmp_path / "prospects.json"))
    monkeypatch.setattr(store, "_ATTEMPTS_FILE", str(tmp_path / "attempts.jsonl"))
    monkeypatch.setattr(policy_mod, "_POLICY_DIR", str(tmp_path))
    monkeypatch.setattr(policy_mod, "_POLICY_FILE", str(tmp_path / "policy.json"))
    monkeypatch.setenv("SALES_AUTOPILOT_ENABLED", "1")
    monkeypatch.setattr(elig, "_owner_kill", lambda name: False)
    monkeypatch.setattr(elig, "_is_suppressed", lambda phone: False)
    yield


def _estique_prospect():
    return {
        "id": store.ESTIQUE_ID,
        "name": "Estique Salon & Spa",
        "phone": store.ESTIQUE_PHONE,
        "email": store.ESTIQUE_EMAIL,
        "city": "Thane",
        "niche": "beauty_makeover",
        "consent_basis": "manual_owner_confirmed",
    }


def test_estique_initial_blocked_by_id():
    r = elig.evaluate(
        _estique_prospect(), channel="whatsapp", step=elig.STEP_INITIAL, now_ist=_MIDDAY
    )
    assert r["decision"] == elig.OWNER_EXCEPTION_REQUIRED
    assert "manual_owner_confirmed_initial_blocked" in r["reason_codes"]


def test_estique_blocked_by_phone_even_with_different_id():
    p = _estique_prospect()
    p["id"] = "some-other-id"
    r = elig.evaluate(p, channel="whatsapp", step=elig.STEP_INITIAL, now_ist=_MIDDAY)
    assert r["decision"] == elig.OWNER_EXCEPTION_REQUIRED


def test_estique_send_blocks_no_provider(monkeypatch):
    called = {"n": 0}

    async def _boom(phone, message):
        called["n"] += 1
        return {"sent": True}

    from app.marketing import whatsapp_campaign

    monkeypatch.setattr(whatsapp_campaign, "send_one", _boom)
    # Even fully armed, Estique initial must not send.
    monkeypatch.setenv("SALES_AUTOPILOT_WHATSAPP_ENABLED", "1")
    policy_mod.save_policy({"dry_run": False, "whatsapp_enabled": True})
    monkeypatch.setenv("SALES_AUTOPILOT_DRY_RUN", "0")
    store.upsert_prospect(_estique_prospect())

    res = asyncio.run(send_mod.send(store.ESTIQUE_ID, channel="whatsapp", step=elig.STEP_INITIAL))
    assert res["outcome"] == send_mod.BLOCKED
    assert res["reason"] == elig.OWNER_EXCEPTION_REQUIRED
    assert called["n"] == 0


def test_ensure_estique_seed_records_manual_confirmed():
    rec = store.ensure_estique_seed()
    assert rec["status"] == store.STATUS_MANUAL_OWNER_CONFIRMED
    assert rec.get("manual_owner_confirmed") is True
    assert store.is_owner_confirmed(store.ESTIQUE_ID) is True
