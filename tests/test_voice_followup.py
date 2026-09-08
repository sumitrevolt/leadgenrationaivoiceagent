"""Tests — voice follow-up scheduler (trial day8/9, interested follow-up, compliance)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest


@pytest.fixture
def vf_store(tmp_path, monkeypatch):
    store = tmp_path / "voice_scheduled_callbacks.jsonl"
    runs = tmp_path / "voice_followup_runs.jsonl"
    monkeypatch.setattr("app.telephony.voice_followup._STORE", str(store))
    monkeypatch.setattr("app.telephony.voice_followup._RUNS", str(runs))
    monkeypatch.setenv("VOICE_FOLLOWUP", "1")
    return store


def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("VOICE_FOLLOWUP", raising=False)
    from app.telephony import voice_followup as vf

    r = vf.schedule_trial_callbacks(phone="9876543210")
    assert r.get("skipped") == "disabled"


def test_schedule_trial_day8_day9(vf_store):
    from app.telephony import voice_followup as vf

    started = datetime(2026, 7, 1, 6, 0, tzinfo=timezone.utc)
    r = vf.schedule_trial_callbacks(
        phone="9876543210",
        client_id="c1",
        business_name="Test Biz",
        trial_started_at=started,
    )
    assert r["ok"] is True
    assert len(r["scheduled"]) == 2

    rows = vf._read(str(vf_store))
    purposes = {x["purpose"] for x in rows}
    assert purposes == {vf.PURPOSE_TRIAL_DAY8, vf.PURPOSE_TRIAL_DAY9}
    assert all(x["status"] == "pending" for x in rows)

    r2 = vf.schedule_trial_callbacks(phone="9876543210", trial_started_at=started)
    assert r2["ok"] is True
    assert r2["scheduled"] == []


def test_interested_followup_dedupe(vf_store):
    from app.telephony import voice_followup as vf

    r1 = vf.schedule_interested_followup(
        phone="919876543210",
        call_id="call-abc",
        business_name="Lead",
    )
    assert r1["ok"] is True
    assert r1["purpose"] == vf.PURPOSE_INTERESTED_1

    r_dup = vf.schedule_interested_followup(phone="919876543210", call_id="call-abc")
    assert r_dup.get("skipped") == "duplicate_call"

    r2 = vf.schedule_interested_followup(phone="919876543210", call_id="call-def")
    assert r2["ok"] is True
    assert r2["purpose"] == vf.PURPOSE_INTERESTED_2

    r3 = vf.schedule_interested_followup(phone="919876543210", call_id="call-ghi")
    assert r3.get("skipped") == "max_followups"


def test_opt_out_blocks_schedule(vf_store, monkeypatch):
    from app.telephony import voice_followup as vf

    monkeypatch.setattr(
        "app.telephony.consent_ledger.is_suppressed",
        lambda _p: True,
    )
    r = vf.schedule_interested_followup(phone="9876543210", call_id="x1")
    assert r.get("skipped") == "opt_out"


def test_cancel_on_not_interested(vf_store):
    from app.telephony import voice_followup as vf

    vf.schedule_interested_followup(phone="9876543210", call_id="c1")
    n = vf.cancel_for_phone("9876543210", reason="not_interested")
    assert n == 1
    rows = vf._read(str(vf_store))
    assert rows[0]["status"] == "cancelled"


@pytest.mark.asyncio
async def test_post_call_workflow_idempotent(vf_store, monkeypatch):
    from app.telephony import voice_followup as vf

    seen = {"n": 0}

    async def _fake_seen(key, ttl_s=None):
        seen["n"] += 1
        return seen["n"] > 1

    monkeypatch.setattr("app.billing.idempotency.seen_before", _fake_seen)

    async def _not_paid(_c):
        return False

    monkeypatch.setattr(vf, "_client_has_paid", _not_paid)

    q = {"qualified": True}
    r1 = await vf.run_post_call_workflows(
        call_id="sid-1",
        phone="9876543210",
        q=q,
    )
    assert r1["ok"] is True
    r2 = await vf.run_post_call_workflows(
        call_id="sid-1",
        phone="9876543210",
        q=q,
    )
    assert r2.get("skipped") == "duplicate"


@pytest.mark.asyncio
async def test_run_due_respects_trai_window(vf_store, monkeypatch):
    from app.telephony import voice_followup as vf

    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    vf._write_all(
        str(vf_store),
        [
            {
                "id": "rec1",
                "phone": "919876543210",
                "purpose": vf.PURPOSE_INTERESTED_1,
                "scheduled_at": past,
                "status": "pending",
                "niche": "ai_marketing",
                "attempts": 0,
            }
        ],
    )
    monkeypatch.setattr(
        "app.telephony.campaign_compliance.trai_window_ok",
        lambda _t: (False, "closed"),
    )
    out = await vf.run_due()
    assert out.get("skipped") == "trai_window"
    rows = vf._read(str(vf_store))
    assert rows[0]["status"] == "pending"


@pytest.mark.asyncio
async def test_run_due_places_transactional_call(vf_store, monkeypatch):
    from app.telephony import voice_followup as vf

    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    vf._write_all(
        str(vf_store),
        [
            {
                "id": "rec2",
                "phone": "919876543210",
                "client_id": "",
                "purpose": vf.PURPOSE_TRIAL_DAY8,
                "scheduled_at": past,
                "status": "pending",
                "niche": "ai_marketing",
                "attempts": 0,
            }
        ],
    )
    monkeypatch.setattr(
        "app.telephony.campaign_compliance.trai_window_ok",
        lambda _t: (True, ""),
    )
    monkeypatch.setattr("app.telephony.consent_ledger.is_suppressed", lambda _p: False)
    monkeypatch.setattr("app.telephony.consent_ledger.reconsent_blocked", lambda _p: False)

    async def _fake_start(**kwargs):
        assert kwargs.get("call_type") == "transactional"
        return {"placed": True}

    monkeypatch.setattr("app.api.telephony_vobiz.start_stream_call", _fake_start)

    out = await vf.run_due()
    assert out["placed"] == 1
    rows = vf._read(str(vf_store))
    assert rows[0]["status"] == "placed"


@pytest.mark.asyncio
async def test_run_due_passes_wizard_opening_for_aware_lead(vf_store, monkeypatch):
    """Business-type-aware followup (wizard niche + name) → start_stream_call ko
    wizard opening_line milta hai; generic lead pe "" (fallback intact)."""
    from app.telephony import voice_followup as vf

    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    vf._write_all(
        str(vf_store),
        [
            {
                "id": "rec3",
                "phone": "919876543210",
                "client_id": "",
                "business_name": "Sharma Salon",
                "purpose": vf.PURPOSE_INTERESTED_1,
                "scheduled_at": past,
                "status": "pending",
                "niche": "salon_spa",
                "attempts": 0,
            },
            {
                "id": "rec4",
                "phone": "919876543211",
                "client_id": "",
                "business_name": "Generic Co",
                "purpose": vf.PURPOSE_INTERESTED_1,
                "scheduled_at": past,
                "status": "pending",
                "niche": "ai_marketing",
                "attempts": 0,
            },
        ],
    )
    monkeypatch.setattr(
        "app.telephony.campaign_compliance.trai_window_ok",
        lambda _t: (True, ""),
    )
    monkeypatch.setattr("app.telephony.consent_ledger.is_suppressed", lambda _p: False)
    monkeypatch.setattr("app.telephony.consent_ledger.reconsent_blocked", lambda _p: False)

    calls: list[dict] = []

    async def _fake_start(**kwargs):
        calls.append(kwargs)
        return {"placed": True}

    monkeypatch.setattr("app.api.telephony_vobiz.start_stream_call", _fake_start)

    out = await vf.run_due()
    assert out["placed"] == 2
    by_phone = {c["to"]: c.get("opening_line") or "" for c in calls}
    # wizard niche + name → personalized opening
    assert "Sharma Salon" in by_phone["919876543210"]
    # non-wizard niche → "" (niche-script chain)
    assert by_phone["919876543211"] == ""
