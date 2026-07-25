"""Sales Autopilot — eligibility decisions (fail-closed)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.platform.sales_autopilot import eligibility as elig
from app.platform.sales_autopilot import policy as policy_mod
from app.platform.sales_autopilot import store as store

_IST = timezone(timedelta(hours=5, minutes=30))
_MIDDAY = datetime(2026, 7, 24, 12, 0, tzinfo=_IST)  # inside 9–19 window


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    # Redirect store + policy to a temp dir.
    monkeypatch.setattr(store, "_DIR", str(tmp_path))
    monkeypatch.setattr(store, "_PROSPECTS_FILE", str(tmp_path / "prospects.json"))
    monkeypatch.setattr(store, "_ATTEMPTS_FILE", str(tmp_path / "attempts.jsonl"))
    monkeypatch.setattr(policy_mod, "_POLICY_DIR", str(tmp_path))
    monkeypatch.setattr(policy_mod, "_POLICY_FILE", str(tmp_path / "policy.json"))
    # Enable engine via env; keep dry-run.
    monkeypatch.setenv("SALES_AUTOPILOT_ENABLED", "1")
    monkeypatch.delenv("SALES_AUTOPILOT_DRY_RUN", raising=False)
    # Neutralize external gates deterministically.
    monkeypatch.setattr(elig, "_owner_kill", lambda name: False)
    monkeypatch.setattr(elig, "_is_suppressed", lambda phone: False)
    yield


def _prospect(**over):
    base = {
        "id": "p-1",
        "name": "Test Salon",
        "phone": "+919812345678",
        "email": "hi@testsalon.in",
        "city": "Pune",
        "niche": "beauty_makeover",
        "source": "inquiry_form",
        "consent_basis": "inquiry_form_submitted",
        "status": store.STATUS_NEW,
    }
    base.update(over)
    return base


def test_eligible_happy_path():
    r = elig.evaluate(_prospect(), channel="whatsapp", step=elig.STEP_INITIAL, now_ist=_MIDDAY)
    assert r["decision"] == elig.ELIGIBLE


def test_engine_disabled(monkeypatch):
    monkeypatch.delenv("SALES_AUTOPILOT_ENABLED", raising=False)
    r = elig.evaluate(_prospect(), channel="whatsapp", now_ist=_MIDDAY)
    assert r["decision"] == elig.INELIGIBLE
    assert "engine_disabled" in r["reason_codes"]


def test_no_consent_ineligible():
    r = elig.evaluate(_prospect(consent_basis=None), channel="whatsapp", now_ist=_MIDDAY)
    assert r["decision"] == elig.INELIGIBLE
    assert "no_consent_basis" in r["reason_codes"]


def test_opted_out_ineligible():
    r = elig.evaluate(_prospect(status=store.STATUS_OPTED_OUT), channel="whatsapp", now_ist=_MIDDAY)
    assert r["decision"] == elig.INELIGIBLE
    assert "opted_out" in r["reason_codes"]


def test_suppressed_fail_closed(monkeypatch):
    monkeypatch.setattr(elig, "_is_suppressed", lambda phone: True)
    r = elig.evaluate(_prospect(), channel="whatsapp", now_ist=_MIDDAY)
    assert r["decision"] == elig.INELIGIBLE
    assert "suppressed" in r["reason_codes"]


def test_owner_kill_fail_closed(monkeypatch):
    monkeypatch.setattr(elig, "_owner_kill", lambda name: name == "owner_whatsapp_outbound")
    r = elig.evaluate(_prospect(), channel="whatsapp", now_ist=_MIDDAY)
    assert r["decision"] == elig.INELIGIBLE
    assert "owner_whatsapp_killed" in r["reason_codes"]


def test_outside_hours_deferred():
    night = datetime(2026, 7, 24, 23, 0, tzinfo=_IST)
    r = elig.evaluate(_prospect(), channel="whatsapp", now_ist=night)
    assert r["decision"] == elig.DEFERRED
    assert "outside_business_hours" in r["reason_codes"]


def test_icp_mismatch():
    policy_mod.save_policy({"icp": {"niches": ["restaurant"], "cities": []}})
    r = elig.evaluate(_prospect(niche="beauty_makeover"), channel="whatsapp", now_ist=_MIDDAY)
    assert r["decision"] == elig.INELIGIBLE
    assert "icp_mismatch" in r["reason_codes"]


def test_no_channel_contact():
    r = elig.evaluate(_prospect(email=None), channel="email", now_ist=_MIDDAY)
    assert r["decision"] == elig.INELIGIBLE
    assert "no_channel_contact" in r["reason_codes"]


def test_step_already_done_idempotent():
    store.upsert_prospect(_prospect(steps_done=["initial_whatsapp"]))
    r = elig.evaluate(_prospect(), channel="whatsapp", step=elig.STEP_INITIAL, now_ist=_MIDDAY)
    assert r["decision"] == elig.INELIGIBLE
    assert "step_already_done" in r["reason_codes"]


def test_error_fail_closed(monkeypatch):
    # Force an internal error path → INELIGIBLE, never a silent ELIGIBLE.
    monkeypatch.setattr(elig._policy_mod, "get_policy", lambda: (_ for _ in ()).throw(ValueError()))
    r = elig.evaluate(_prospect(), channel="whatsapp", now_ist=_MIDDAY)
    assert r["decision"] == elig.INELIGIBLE
    assert "eligibility_error" in r["reason_codes"]
