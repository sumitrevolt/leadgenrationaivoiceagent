"""Sales Autopilot — scheduler runtime-wiring acceptance.

Proves the canary tick is REGISTERED in the canonical beat/staff runtime and is safe:
INERT when disabled, dry-run never touches a provider, canary batch = 1 (no catch-up
flood), single-flight distributed lock (no overlap, released on success/failure), kill
switches block claims, the WhatsApp-only selection never picks the email stub, and the
summary API reports the runtime truth. Calling stays HARD OFF.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.platform.sales_autopilot import eligibility as elig
from app.platform.sales_autopilot import policy as policy_mod
from app.platform.sales_autopilot import scheduler as sched
from app.platform.sales_autopilot import send as send_mod
from app.platform.sales_autopilot import store as store

_IST = timezone(timedelta(hours=5, minutes=30))
_MIDDAY = datetime(2026, 7, 24, 12, 0, tzinfo=_IST)  # inside 9–19 window


class _FakeRedis:
    """Minimal SET NX / GET / DELETE to exercise the single-flight lock deterministically."""

    def __init__(self) -> None:
        self.kv: dict[str, str] = {}

    def set(self, key, val, nx=False, ex=None):
        if nx and key in self.kv:
            return None
        self.kv[key] = val
        return True

    def get(self, key):
        return self.kv.get(key)

    def delete(self, key):
        self.kv.pop(key, None)


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "_DIR", str(tmp_path))
    monkeypatch.setattr(store, "_PROSPECTS_FILE", str(tmp_path / "prospects.json"))
    monkeypatch.setattr(store, "_ATTEMPTS_FILE", str(tmp_path / "attempts.jsonl"))
    monkeypatch.setattr(policy_mod, "_POLICY_DIR", str(tmp_path))
    monkeypatch.setattr(policy_mod, "_POLICY_FILE", str(tmp_path / "policy.json"))
    # Deterministic external gates so eligibility can pass when we want it to.
    monkeypatch.setattr(elig, "_owner_kill", lambda name: False)
    monkeypatch.setattr(elig, "_is_suppressed", lambda phone: False)
    monkeypatch.setattr(elig, "_now_ist", lambda: _MIDDAY)
    # Ensure a clean flag env each test.
    for k in (
        "SALES_AUTOPILOT_ENABLED",
        "SALES_AUTOPILOT_WHATSAPP_ENABLED",
        "SALES_AUTOPILOT_EMAIL_ENABLED",
        "SALES_AUTOPILOT_DRY_RUN",
        "SALES_AUTOPILOT_NEW_OUTREACH_KILL",
    ):
        monkeypatch.delenv(k, raising=False)
    yield


def _seed_new(n: int) -> None:
    for i in range(n):
        store.upsert_prospect(
            {
                "id": f"p-{i}",
                "name": f"Salon {i}",
                "phone": f"+91981234{i:04d}",
                "city": "Pune",
                "niche": "beauty_makeover",
                "consent_basis": "inquiry_form",
                "status": store.STATUS_NEW,
            }
        )


def _provider_spy(monkeypatch):
    calls = {"n": 0}

    async def _boom(phone, message):
        calls["n"] += 1
        return {"sent": True, "mode": "cloud_api"}

    from app.marketing import whatsapp_campaign

    monkeypatch.setattr(whatsapp_campaign, "send_one", _boom)
    return calls


# 1. Registration exists in the canonical runtime (beat + staff + meta + no-catch-up). ---- #
def test_scheduler_registration_exists():
    from app.platform import scheduler_config, team_scheduler
    from app.tasks.staff_jobs import STAFF_JOBS

    assert "sales_autopilot" in STAFF_JOBS
    assert "sales_autopilot" in scheduler_config.JOB_META
    assert "sales_autopilot" in scheduler_config.RUN_DUE_EXCLUDE  # no catch-up recovery
    assert "sales_autopilot" in team_scheduler._last_ran


def test_beat_schedule_has_hourly_task():
    from app.worker import celery_app

    beat = celery_app.conf.beat_schedule
    assert "staff-sales-autopilot-hourly" in beat
    entry = beat["staff-sales-autopilot-hourly"]
    assert entry["args"] == ("sales_autopilot",)


# 2. Disabled → INERT (no lock, no provider). ------------------------------------------- #
def test_disabled_is_inert(monkeypatch):
    _seed_new(3)
    calls = _provider_spy(monkeypatch)
    res = asyncio.run(sched.run_tick())
    assert res == {"enabled": False, "processed": 0}
    assert calls["n"] == 0


# 3. Dry-run → provider invocation count 0. --------------------------------------------- #
def test_dry_run_never_calls_provider(monkeypatch):
    monkeypatch.setenv("SALES_AUTOPILOT_ENABLED", "1")  # dry_run stays True (default)
    _seed_new(3)
    calls = _provider_spy(monkeypatch)
    res = asyncio.run(sched.run_tick())
    assert res["enabled"] is True
    assert res["dry_run"] is True
    assert calls["n"] == 0
    # Everything processed was SIMULATED, nothing SENT.
    assert res["outcomes"].get(send_mod.SENT, 0) == 0


# 4. Canary batch = 1 + 6. No catch-up flood (backlog processed one small batch). ------- #
def test_canary_batch_one_no_catch_up(monkeypatch):
    monkeypatch.setenv("SALES_AUTOPILOT_ENABLED", "1")
    _seed_new(5)  # backlog of 5 eligible NEW prospects
    calls = _provider_spy(monkeypatch)
    res = asyncio.run(sched.run_tick())
    assert res["processed"] == 1  # exactly the canary batch, not the whole backlog
    assert len(res["items"]) == 1
    assert calls["n"] == 0


# 5. Distributed lock: single-flight primitive + overlap skip + release on success. ------ #
def test_lock_primitive_single_flight(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(sched, "_redis", lambda: fake)
    t1 = sched._acquire_lock()
    assert t1 and not t1.startswith("local:")
    assert sched._acquire_lock() is None  # second claimant blocked while held
    sched._release_lock(t1)
    t3 = sched._acquire_lock()  # released → acquirable again
    assert t3 and not t3.startswith("local:")


def test_run_tick_skips_when_lock_held(monkeypatch):
    fake = _FakeRedis()
    fake.kv[sched._LOCK_KEY] = "someone-else"  # lock already held
    monkeypatch.setattr(sched, "_redis", lambda: fake)
    monkeypatch.setenv("SALES_AUTOPILOT_ENABLED", "1")
    _seed_new(2)
    calls = _provider_spy(monkeypatch)
    res = asyncio.run(sched.run_tick())
    assert res == {"enabled": True, "skipped": "lock_held", "processed": 0}
    assert calls["n"] == 0
    assert fake.kv[sched._LOCK_KEY] == "someone-else"  # did not steal/overwrite


def test_lock_released_after_successful_tick(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(sched, "_redis", lambda: fake)
    monkeypatch.setenv("SALES_AUTOPILOT_ENABLED", "1")
    _seed_new(1)
    asyncio.run(sched.run_tick())
    assert sched._LOCK_KEY not in fake.kv  # released in finally


# 7. Kill switch blocks claims (no work, no provider). ---------------------------------- #
def test_new_outreach_kill_blocks(monkeypatch):
    monkeypatch.setenv("SALES_AUTOPILOT_ENABLED", "1")
    monkeypatch.setenv("SALES_AUTOPILOT_NEW_OUTREACH_KILL", "1")
    _seed_new(3)
    calls = _provider_spy(monkeypatch)
    res = asyncio.run(sched.run_tick())
    assert res["processed"] == 0  # new-outreach targets skipped at selection
    assert calls["n"] == 0


# 8. Outside sending window defers (nothing SENT/SIMULATED live). ----------------------- #
def test_outside_window_defers(monkeypatch):
    monkeypatch.setenv("SALES_AUTOPILOT_ENABLED", "1")
    monkeypatch.setattr(elig, "_now_ist", lambda: datetime(2026, 7, 24, 23, 0, tzinfo=_IST))
    _seed_new(2)
    calls = _provider_spy(monkeypatch)
    res = asyncio.run(sched.run_tick())
    # The one selected target is DEFERRED (outside hours), never sent.
    assert res["outcomes"].get(send_mod.SENT, 0) == 0
    assert calls["n"] == 0


# 10. Test/demo prospects excluded (no lawful consent basis ⇒ ineligible). --------------- #
def test_demo_prospect_excluded(monkeypatch):
    monkeypatch.setenv("SALES_AUTOPILOT_ENABLED", "1")
    # A demo/test row carries no consent_basis → eligibility fail-closed blocks it.
    store.upsert_prospect(
        {
            "id": "demo-1",
            "phone": "+919800000000",
            "niche": "beauty_makeover",
            "source": "demo_seed",
            "status": store.STATUS_NEW,
        }
    )
    r = elig.evaluate(
        store.get_prospect("demo-1"), channel="whatsapp", step=elig.STEP_INITIAL, now_ist=_MIDDAY
    )
    assert r["decision"] == elig.INELIGIBLE
    assert "no_consent_basis" in r["reason_codes"]


# 11. Scheduler tick stays WhatsApp-preferring; email live path is fail-closed. -------- #
def test_scheduler_selects_whatsapp_only(monkeypatch):
    monkeypatch.setenv("SALES_AUTOPILOT_ENABLED", "1")
    _seed_new(3)
    res = asyncio.run(sched.run_tick())
    for item in res["items"]:
        assert item["channel"] == "whatsapp"


def test_scheduler_selects_email_when_whatsapp_off_email_on(monkeypatch):
    monkeypatch.setenv("SALES_AUTOPILOT_ENABLED", "1")
    monkeypatch.setenv("SALES_AUTOPILOT_WHATSAPP_ENABLED", "0")
    monkeypatch.setenv("SALES_AUTOPILOT_EMAIL_ENABLED", "1")
    _seed_new(3)
    res = asyncio.run(sched.run_tick())
    assert res["enabled"] is True
    assert len(res["items"]) >= 1
    for item in res["items"]:
        # Email-channel selection routes to the email template (no WhatsApp provider).
        assert item["channel"] == "email"
        assert item["step"] == elig.STEP_INITIAL
    # No live WhatsApp/email provider call in this fixture (dry-run default).
    assert res["outcomes"].get(send_mod.SENT, 0) == 0


def test_scheduler_primary_channel_prefers_whatsapp_when_both_on(monkeypatch):
    monkeypatch.setenv("SALES_AUTOPILOT_ENABLED", "1")
    monkeypatch.setenv("SALES_AUTOPILOT_WHATSAPP_ENABLED", "1")
    monkeypatch.setenv("SALES_AUTOPILOT_EMAIL_ENABLED", "1")
    pol = policy_mod.get_policy()
    assert sched._primary_channel(pol) == "whatsapp"
    monkeypatch.setenv("SALES_AUTOPILOT_WHATSAPP_ENABLED", "0")
    monkeypatch.setenv("SALES_AUTOPILOT_EMAIL_ENABLED", "1")
    assert sched._primary_channel(policy_mod.get_policy()) == "email"


def test_email_channel_fail_closed_without_smtp(monkeypatch):
    # Fully armed email + no SMTP/API creds ⇒ FAILED (fail-closed), never WhatsApp.
    #
    # HERMETIC PRECONDITION (do not remove): "no creds" must be ENFORCED, not assumed.
    # EmailSender/api_available read app.config.settings, which is populated from .env at
    # import time. On a machine with real SMTP configured this test used to skip straight
    # past the smtp_not_configured branch and attempt a LIVE Hostinger send, returning
    # SKIPPED instead of FAILED — so the fail-closed invariant was only ever asserted by
    # accident on credential-less CI. Blanking the settings here makes the assertion mean
    # the same thing on every machine and keeps the suite from touching a real provider.
    from app.config import settings as _settings

    monkeypatch.setattr(_settings, "smtp_user", "", raising=False)
    monkeypatch.setattr(_settings, "smtp_password", "", raising=False)
    monkeypatch.setattr(_settings, "resend_api_key", "", raising=False)
    monkeypatch.setattr(_settings, "brevo_api_key", "", raising=False)

    monkeypatch.setenv("SALES_AUTOPILOT_ENABLED", "1")
    monkeypatch.setenv("SALES_AUTOPILOT_EMAIL_ENABLED", "1")
    monkeypatch.setenv("SALES_AUTOPILOT_DRY_RUN", "0")
    policy_mod.save_policy({"dry_run": False, "email_enabled": True})
    store.upsert_prospect(
        {
            "id": "e-1",
            "email": "owner@salon.in",
            "niche": "beauty_makeover",
            "consent_basis": "inquiry_form",
            "status": store.STATUS_NEW,
        }
    )
    calls = _provider_spy(monkeypatch)  # WhatsApp provider spy — must stay 0
    res = asyncio.run(send_mod.send("e-1", channel="email", step=elig.STEP_INITIAL))
    assert res["outcome"] == send_mod.FAILED
    assert res["reason"] == "smtp_not_configured"
    assert (res.get("provider") or {}).get("provider_called") is False
    assert calls["n"] == 0


# 12. Summary reports runtime scheduler truth. ------------------------------------------ #
def test_summary_reports_scheduler_truth(monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    # Record one tick so last_tick is populated (engine off → INERT record).
    asyncio.run(sched.run_tick())
    client = TestClient(app)
    r = client.get("/api/sales-autopilot/summary")
    assert r.status_code == 200
    s = r.json()["scheduler"]
    assert s["scheduler_registered"] is True
    assert s["no_catch_up"] is True
    assert s["cadence"] and ":25" in s["cadence"]
    assert s["last_tick"] is not None
    assert s["last_tick"]["enabled"] is False


# 13. Calling stays untouched (no dial/call symbol; scheduler is send-only). ------------- #
def test_calling_untouched():
    assert not hasattr(sched, "dial")
    assert not hasattr(sched, "call")


# 14. Empty queue is a NORMAL idle, not silent success — explicit idle_reason. ----------- #
def test_empty_queue_records_idle_reason(monkeypatch):
    monkeypatch.setenv("SALES_AUTOPILOT_ENABLED", "1")
    res = asyncio.run(sched.run_tick())
    assert res["enabled"] is True
    assert res["processed"] == 0
    assert res["idle_reason"] == "no_eligible_prospects"
    assert isinstance(res["prospect_status_counts"], dict)
    # Persisted to last_tick so Mission Control reads the same truth.
    lt = store.get_last_tick()
    assert lt is not None
    assert lt["idle_reason"] == "no_eligible_prospects"


def test_idle_reason_absent_when_work_happens(monkeypatch):
    monkeypatch.setenv("SALES_AUTOPILOT_ENABLED", "1")
    _seed_new(1)
    res = asyncio.run(sched.run_tick())
    assert res["processed"] == 1
    assert "idle_reason" not in res
