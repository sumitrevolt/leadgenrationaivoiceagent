"""Hands-Free Automations — proof that every advertised auto is backed by a real,
importable engine with its run-entry, and that customer_autopilot is inert-by-default.

Guards the 'surface not fabricate' rule: each of the 20 'Hands-Free Automations'
pricing items maps to a wired engine; the 4 new-wire jobs are flag-gated DEFAULT-OFF,
draft-only, and never raise.
"""

import asyncio
import importlib

import pytest

from app.api.automation_flags import AUTOMATION_FLAGS
from app.marketing.packages import _STARTER_FEATURE_GROUPS, _STARTER_FEATURES
from app.platform import customer_autopilot

_AUTOPILOT_FLAGS = ["EVERGREEN_RECYCLE", "NPS_AUTO", "STALE_INQUIRY_NUDGE", "OWNER_BRIEF_DAILY"]

# (module_path, attr) for each backing engine behind a 'Hands-Free Automations' item.
_BACKING_ENGINES = [
    ("app.platform.booking_reminders", "run_due"),
    ("app.platform.service_reminders", "run_due_if_enabled"),
    ("app.marketing.review_monitor", "run_check"),
    ("app.platform.brand_pulse", "run_weekly_if_enabled"),
    ("app.platform.rank_tracker", "run_if_enabled"),
    ("app.marketing.customer_crm", "run_wishes_if_enabled"),
    ("app.marketing.newsletter", "run_due_if_enabled"),
    ("app.platform.winback", "run_due_if_enabled"),
    ("app.marketing.cadence", "run_due"),
    ("app.marketing.journeys", "emit_event"),
    ("app.platform.lead_alerts", "notify_new_lead_bg"),
    ("app.marketing.sales_pipeline", "run_pipeline"),
    ("app.marketing.lifecycle_nurture", "run_due"),
    ("app.telephony.voice_followup", "run_due"),
    ("app.platform.deliverability_monitor", "run_check"),
    ("app.platform.team_report", "run_weekly_if_enabled"),
    # the 4 customer_autopilot-wired engines:
    ("app.marketing.evergreen", "recycle_for_client"),
    ("app.platform.nps", "request_drafts"),
    ("app.platform.speed_to_lead", "per_inquiry_for_client"),
    ("app.marketing.clients_store", "list_clients"),
]


def _hands_free_group():
    return next(
        (g for g in _STARTER_FEATURE_GROUPS if g.get("title") == "Hands-Free Automations"),
        None,
    )


def test_hands_free_group_present_with_20_items():
    g = _hands_free_group()
    assert g is not None, "Hands-Free Automations group missing from _STARTER_FEATURE_GROUPS"
    assert len(g["items"]) == 20, f"expected 20 hands-free items, got {len(g['items'])}"
    # no blank/dup items
    items = [i.strip() for i in g["items"]]
    assert all(items), "blank hands-free item"
    assert len(set(items)) == 20, "duplicate hands-free item"


def test_flat_features_include_hands_free():
    g = _hands_free_group()
    for it in g["items"]:
        assert it in _STARTER_FEATURES, f"flat list missing: {it}"
    # group-derived flat list stays consistent
    assert _STARTER_FEATURES.count(g["items"][0]) == 1


def test_new_autopilot_flags_registered():
    for f in _AUTOPILOT_FLAGS:
        assert f in AUTOMATION_FLAGS, f"flag {f} not in AUTOMATION_FLAGS registry"


@pytest.mark.parametrize("module_path,attr", _BACKING_ENGINES)
def test_backing_engine_importable_with_run_entry(module_path, attr):
    mod = importlib.import_module(module_path)
    fn = getattr(mod, attr, None)
    assert callable(fn), f"{module_path}.{attr} missing/not callable (advertised but not backed)"


def test_run_all_inert_when_flags_off(monkeypatch):
    """All autopilot flags OFF -> run_all never raises, every sub-job reports skipped."""
    for f in _AUTOPILOT_FLAGS:
        monkeypatch.delenv(f, raising=False)
    out = asyncio.run(customer_autopilot.run_all())
    assert out["ok"] is True
    for k in ("evergreen", "nps", "stale_inquiry", "owner_brief"):
        assert out[k].get("skipped") == "flag_off", f"{k} not inert when flag off"


def test_nps_autopilot_writes_draft_when_enabled(monkeypatch, tmp_path):
    """Flag ON -> draft-only write to jsonl, idempotent (2nd run = no dup)."""
    monkeypatch.setenv("NPS_AUTO", "1")
    monkeypatch.setattr(customer_autopilot, "_DATA_DIR", str(tmp_path))

    fake_drafts = [
        {"client": "Sharma Dental", "slug": "sharma-dental", "message": "rate us", "wa_link": None}
    ]
    import app.platform.nps as nps_mod

    monkeypatch.setattr(nps_mod, "request_drafts", lambda limit=50: fake_drafts)

    r1 = customer_autopilot.nps_survey_drafts()
    assert r1["ok"] is True and r1["drafts"] == 1
    # idempotent: same day re-run writes 0 new
    r2 = customer_autopilot.nps_survey_drafts()
    assert r2["drafts"] == 0


def test_stale_inquiry_inert_without_clients(monkeypatch, tmp_path):
    """Flag ON but no clients -> no raise, zero nudges."""
    monkeypatch.setenv("STALE_INQUIRY_NUDGE", "1")
    monkeypatch.setattr(customer_autopilot, "_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(customer_autopilot, "_clients", lambda: [])
    r = customer_autopilot.stale_inquiry_nudges()
    assert r["ok"] is True and r["nudges"] == 0
