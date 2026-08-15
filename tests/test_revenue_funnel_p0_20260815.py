"""P0 revenue-funnel remediations 2026-08-15 — no fake paid, no outbound send."""

from __future__ import annotations

import asyncio
import inspect

from app.api.automation_flags import AUTOMATION_FLAGS
from app.billing import dunning
from app.platform import reply_agent as ra
from app.platform.automation_flag_manifest import FlagGovernance, describe_flag
from app.platform.team_scheduler import _last_ran


def test_renewal_skips_when_dunning_engine_already_covers(monkeypatch):
    monkeypatch.setenv("DUNNING_ENGINE", "1")
    monkeypatch.setenv("RENEWAL_REMINDER_ENABLED", "1")
    out = asyncio.run(dunning.send_renewal_reminders())
    assert out["skipped"] == "covered_by_dunning_run_due"


def test_renewal_respects_own_flag_when_dunning_off(monkeypatch):
    monkeypatch.setenv("DUNNING_ENGINE", "0")
    monkeypatch.setenv("RENEWAL_REMINDER_ENABLED", "0")
    out = asyncio.run(dunning.send_renewal_reminders())
    assert out["skipped"] == "RENEWAL_REMINDER_ENABLED=0"


def test_in_process_renewal_is_day_keyed_not_every_tick():
    ts = __import__(
        "app.platform.team_scheduler", fromlist=["scheduler_loop", "_renewal_reminders_day"]
    )
    src = inspect.getsource(ts.scheduler_loop)
    assert "if _renewal_reminders_day != day_key" in src
    assert '_last_ran.get("renewal_reminders")' not in src
    # Private marker stays outside _last_ran so STAFF_JOBS / Aaj parity stays clean.
    assert "renewal_reminders" not in _last_ran
    assert hasattr(ts, "_renewal_reminders_day")
    assert (
        "renewal_reminders"
        not in __import__("app.tasks.staff_jobs", fromlist=["STAFF_JOBS"]).STAFF_JOBS
    )


def test_renewal_reminder_flag_is_registered():
    assert "RENEWAL_REMINDER_ENABLED" in AUTOMATION_FLAGS
    meta = describe_flag("RENEWAL_REMINDER_ENABLED")
    assert meta.governance == FlagGovernance.OWNER_APPROVAL_REQUIRED
    assert meta.kind.value == "boolean"


def test_calling_flagged_surfaces_in_hot_queue(tmp_path, monkeypatch):
    from app.platform import auto_outreach as ao

    drafts = tmp_path / "reply_drafts.jsonl"
    drafts.write_text("", encoding="utf-8")
    monkeypatch.setattr(ra, "_DRAFTS_FILE", str(drafts))
    monkeypatch.setattr(ra, "_full_prospect_map", lambda: {})
    monkeypatch.setattr(
        "app.platform.sales_autopilot.pay_truth.unpaid_chase_cards",
        lambda limit=50: [],
    )
    monkeypatch.setattr(
        ao,
        "hot_queue_candidates",
        lambda limit=20: [
            {
                "id": "p_flag_1",
                "business_name": "Flagged Salon",
                "phone": "9876543210",
                "email": "salon@test.in",
                "niche": "beauty",
                "city": "Pune",
                "status": "ready",
                "lead_score": 80,
                "reason": "calling_flagged",
                "wa_followup_link": "https://wa.me/919876543210?text=hi",
            }
        ],
    )
    q = ra.hot_queue(limit=20)
    hit = next(r for r in q if r.get("hq_id") == "callflag:p_flag_1")
    assert hit["channel"] == "calling_flagged"
    assert hit["wa_link"].startswith("https://wa.me/919876543210")
    assert hit["owner_action"] == "call_or_wa_draft_then_done"


def test_callflag_done_hides_card(tmp_path, monkeypatch):
    from app.platform import auto_outreach as ao

    drafts = tmp_path / "reply_drafts.jsonl"
    drafts.write_text("", encoding="utf-8")
    monkeypatch.setattr(ra, "_DRAFTS_FILE", str(drafts))
    monkeypatch.setattr(ra, "_full_prospect_map", lambda: {})
    monkeypatch.setattr(
        "app.platform.sales_autopilot.pay_truth.unpaid_chase_cards",
        lambda limit=50: [],
    )
    rows = [
        {
            "id": "p_flag_2",
            "business_name": "Done Salon",
            "phone": "9123456780",
            "email": "done@test.in",
            "status": "ready",
            "lead_score": 90,
            "reason": "calling_flagged",
            "calling_flagged": True,
        }
    ]
    state = {"hq_done": False}

    def _cands(limit=20):
        return [] if state["hq_done"] else rows

    def _mark(pid, *, done=False, parked=False):
        if pid == "p_flag_2" and done:
            state["hq_done"] = True
            return True
        return False

    monkeypatch.setattr(ao, "hot_queue_candidates", _cands)
    monkeypatch.setattr(ao, "mark_hot_queue_candidate", _mark)
    assert any(r.get("hq_id") == "callflag:p_flag_2" for r in ra.hot_queue(limit=20))
    assert ra.mark_handled("callflag:p_flag_2") is True
    assert not any(r.get("hq_id") == "callflag:p_flag_2" for r in ra.hot_queue(limit=20))


def test_hard_off_defaults_on_when_unset(monkeypatch):
    monkeypatch.setenv("REPLY_AUTO_SEND", "1")
    monkeypatch.delenv("REPLY_AUTO_SEND_HARD_OFF", raising=False)

    async def _check_blocked():
        return await ra._reply_auto_send_enabled()

    async def _check_armed():
        monkeypatch.setenv("REPLY_AUTO_SEND_HARD_OFF", "0")
        return await ra._reply_auto_send_enabled()

    assert asyncio.run(_check_blocked()) is False
    assert asyncio.run(_check_armed()) is True
