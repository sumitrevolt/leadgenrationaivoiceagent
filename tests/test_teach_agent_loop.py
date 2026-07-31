"""Tests — teach-agent-loop 2026-07-31: teen naye self-improve actions.

  dialer_sprint_prep : untapped prospect phones → human-dialer prep briefs
  hot_wa_draft       : Hot Queue warm leads → WhatsApp reply drafts (draft-only)
  job_heal_sweep     : stale scheduled-job heartbeats → bounded re-dispatch

Hermetic: engine modules monkeypatch, koi network/DB nahi. Sync + asyncio.run
pattern (repo convention). Har action pe 5 scenarios: happy / empty / LLM-down /
engine-timeout / concurrent-idempotent.
"""

from __future__ import annotations

import asyncio

import pytest


# =====================================================================
# dialer_sprint_prep
# =====================================================================
def _patch_prep_engines(monkeypatch, prospects, brief=None, prep_error=None):
    from app.platform import call_prep, prospect_lists

    async def fake_prep(phone=None, client_id=None):
        if prep_error:
            raise prep_error
        return brief or {
            "ok": True,
            "phone": phone,
            "provider": "fallback",
            "brief": {"kaun_hai": f"{phone}", "next_action": "call karo"},
        }

    monkeypatch.setattr(prospect_lists, "search", lambda **kw: prospects)
    monkeypatch.setattr(call_prep, "prep_brief", fake_prep)
    from app.platform import dialer_log

    monkeypatch.setattr(dialer_log, "_read_logs", lambda: [])


def test_dialer_sprint_prep_happy_path(tmp_path, monkeypatch):
    from app.agents.sprint_actions import dialer_sprint_prep

    _patch_prep_engines(
        monkeypatch,
        [
            {
                "phone": "9876543210",
                "business_name": "SolarWala",
                "niche": "solar",
                "city": "Pune",
                "score": 80,
            },
            {
                "phone": "+919812345678",
                "business_name": "GymFit",
                "niche": "gym",
                "city": "Mumbai",
                "score": 60,
            },
            {
                "phone": "no-phone",
                "business_name": "NoPhoneCo",
                "niche": "gym",
                "city": "Delhi",
                "score": 90,
            },
        ],
    )
    out = asyncio.run(dialer_sprint_prep(limit=5))
    assert out["ok"] is True
    assert out["prepped"] == 2  # no-phone skip + 2 valid phones
    assert out["briefs"][0]["phone"] == "9876543210"
    assert out["briefs"][1]["phone"] == "9812345678"


def test_dialer_sprint_prep_empty_no_prospects(tmp_path, monkeypatch):
    from app.agents.sprint_actions import dialer_sprint_prep

    _patch_prep_engines(monkeypatch, [])
    out = asyncio.run(dialer_sprint_prep(limit=3))
    assert out["ok"] is False
    assert out["prepped"] == 0


def test_dialer_sprint_prep_llm_down_fallback(tmp_path, monkeypatch):
    from app.agents.sprint_actions import dialer_sprint_prep

    # prep_brief khud fallback deta hai (static brief) — yahan simulate:
    # LLM-down = prep_brief ok=True provider="fallback"
    _patch_prep_engines(
        monkeypatch,
        [
            {
                "phone": "9876543210",
                "business_name": "SolarWala",
                "niche": "solar",
                "city": "Pune",
                "score": 80,
            },
        ],
        brief={
            "ok": True,
            "phone": "9876543210",
            "provider": "fallback",
            "brief": {"kaun_hai": "static"},
        },
    )
    out = asyncio.run(dialer_sprint_prep(limit=3))
    assert out["ok"] is True
    assert out["briefs"][0]["provider"] == "fallback"
    assert out["briefs"][0]["brief"]["kaun_hai"] == "static"


def test_dialer_sprint_prep_engine_error_graceful(tmp_path, monkeypatch):
    from app.agents.sprint_actions import dialer_sprint_prep

    _patch_prep_engines(
        monkeypatch,
        [
            {
                "phone": "9876543210",
                "business_name": "X",
                "niche": "solar",
                "city": "Pune",
                "score": 70,
            }
        ],
        prep_error=asyncio.TimeoutError("prep 25s cap hit"),
    )
    out = asyncio.run(dialer_sprint_prep(limit=3))
    # prep error → brief appended with ok=False; action never raises
    assert out["briefs"][0]["ok"] is False
    assert "prep 25s cap hit" in str(out["briefs"][0].get("error"))


def test_dialer_sprint_prep_dedupes_dialed_phones(tmp_path, monkeypatch):
    from app.agents.sprint_actions import dialer_sprint_prep
    from app.platform import dialer_log

    _patch_prep_engines(
        monkeypatch,
        [
            {
                "phone": "9876543210",
                "business_name": "SolarWala",
                "niche": "solar",
                "city": "Pune",
                "score": 80,
            },
            {
                "phone": "9812345678",
                "business_name": "GymFit",
                "niche": "gym",
                "city": "Mumbai",
                "score": 60,
            },
        ],
    )
    # 9876543210 already dialed → skip
    monkeypatch.setattr(dialer_log, "_read_logs", lambda: [{"phone": "9876543210"}])
    out = asyncio.run(dialer_sprint_prep(limit=5))
    assert out["prepped"] == 1
    assert out["briefs"][0]["phone"] == "9812345678"


def test_dialer_sprint_prep_concurrent_safe(tmp_path, monkeypatch):
    from app.agents.sprint_actions import dialer_sprint_prep

    _patch_prep_engines(
        monkeypatch,
        [
            {
                "phone": "9876543210",
                "business_name": "SolarWala",
                "niche": "solar",
                "city": "Pune",
                "score": 80,
            }
        ],
    )

    async def _two():
        a, b = await asyncio.gather(dialer_sprint_prep(3), dialer_sprint_prep(3))
        return a, b

    a, b = asyncio.run(_two())
    assert a["ok"] is True and b["ok"] is True
    assert a["prepped"] == b["prepped"] == 1


# =====================================================================
# hot_wa_draft
# =====================================================================
def _patch_wa_engines(monkeypatch, hot_rows, save_ok=True, chat_error=None, existing_wa=()):
    from app.platform import reply_agent
    from app.voice_agent import free_ai

    monkeypatch.setattr(reply_agent, "hot_queue", lambda **kw: hot_rows)
    monkeypatch.setattr(reply_agent, "list_drafts", lambda limit=50: list(existing_wa))
    saves: list[dict] = []
    monkeypatch.setattr(reply_agent, "_save_draft", lambda rec: saves.append(rec) or save_ok)
    monkeypatch.setattr("app.agents.sprint_actions._has_wa_draft", lambda ra, ph: False)

    async def fake_chat(system, messages, **kw):
        if chat_error:
            raise chat_error
        return "Namaste! Free Google audit + demo: https://leadsgenai.in/demo", "mock"

    monkeypatch.setattr(free_ai, "chat", fake_chat)
    return saves


def test_hot_wa_draft_happy_path(tmp_path, monkeypatch):
    from app.agents.sprint_actions import hot_wa_draft

    saves = _patch_wa_engines(
        monkeypatch,
        [
            {
                "from": "9876543210",
                "phone": "9876543210",
                "business_name": "SolarWala",
                "niche": "solar",
                "intent": "interested",
            },
        ],
    )
    out = asyncio.run(hot_wa_draft(limit=5))
    assert out["ok"] is True
    assert out["drafted"] == 1
    assert len(saves) == 1
    assert saves[0]["channel"] == "whatsapp"
    assert saves[0]["from"] == "9876543210"
    assert "leadsgenai.in" in saves[0]["draft"]


def test_hot_wa_draft_empty_queue(tmp_path, monkeypatch):
    from app.agents.sprint_actions import hot_wa_draft

    _patch_wa_engines(monkeypatch, [])
    out = asyncio.run(hot_wa_draft(limit=5))
    assert out["ok"] is False
    assert out["drafted"] == 0


def test_hot_wa_draft_skips_already_drafted(tmp_path, monkeypatch):
    from app.agents.sprint_actions import hot_wa_draft

    _patch_wa_engines(
        monkeypatch,
        [
            {
                "from": "9876543210",
                "phone": "9876543210",
                "business_name": "SolarWala",
                "niche": "solar",
                "intent": "interested",
                "draft": "already there",
            },
        ],
    )
    out = asyncio.run(hot_wa_draft(limit=5))
    assert out["ok"] is False
    assert out["drafted"] == 0
    assert out["skipped"] == 1


def test_hot_wa_draft_llm_down_fallback(tmp_path, monkeypatch):
    from app.agents.sprint_actions import hot_wa_draft

    saves = _patch_wa_engines(
        monkeypatch,
        [
            {
                "from": "9876543210",
                "phone": "9876543210",
                "business_name": "SolarWala",
                "niche": "solar",
                "intent": "interested",
            },
        ],
        chat_error=RuntimeError("no providers"),
    )
    out = asyncio.run(hot_wa_draft(limit=5))
    assert out["ok"] is True
    assert out["drafted"] == 1
    assert "leadsgenai.in/demo" in saves[0]["draft"]  # deterministic fallback


def test_hot_wa_draft_engine_timeout_graceful(tmp_path, monkeypatch):
    from app.agents.sprint_actions import hot_wa_draft

    _patch_wa_engines(
        monkeypatch,
        [
            {
                "from": "9876543210",
                "phone": "9876543210",
                "business_name": "SolarWala",
                "niche": "solar",
                "intent": "interested",
            },
        ],
        chat_error=asyncio.TimeoutError("free_ai 20s cap"),
    )
    out = asyncio.run(hot_wa_draft(limit=5))
    assert out["ok"] is True  # fallback drafted even on timeout
    assert out["drafted"] == 1


def test_hot_wa_draft_save_failure_graceful(tmp_path, monkeypatch):
    from app.agents.sprint_actions import hot_wa_draft
    from app.platform import reply_agent
    from app.voice_agent import free_ai

    monkeypatch.setattr(
        reply_agent,
        "hot_queue",
        lambda **kw: [
            {
                "from": "9876543210",
                "phone": "9876543210",
                "business_name": "SolarWala",
                "niche": "solar",
                "intent": "interested",
            }
        ],
    )
    monkeypatch.setattr(reply_agent, "list_drafts", lambda limit=50: [])
    monkeypatch.setattr(reply_agent, "_save_draft", lambda rec: False)
    monkeypatch.setattr("app.agents.sprint_actions._has_wa_draft", lambda ra, ph: False)

    async def fake_chat(system, messages, **kw):
        return "hi from mock", "mock"

    monkeypatch.setattr(free_ai, "chat", fake_chat)

    out = asyncio.run(hot_wa_draft(limit=5))
    assert out["ok"] is False
    assert out["skipped"] == 1


# =====================================================================
# job_heal_sweep
# =====================================================================
def _patch_heal_engines(monkeypatch, health=None, recover=None, recover_error=None):
    from app.platform import automation_health, team_scheduler

    monkeypatch.setattr(
        automation_health, "health", lambda: health or {"overdue": [], "never_ran": []}
    )

    def fake_recover():
        if recover_error:
            raise recover_error
        return recover or {"ok": True, "due": [], "started": {}, "skipped_excluded": []}

    monkeypatch.setattr(team_scheduler, "_recover_due_jobs", fake_recover)


def test_job_heal_sweep_happy_path(tmp_path, monkeypatch):
    from app.agents.sprint_actions import job_heal_sweep

    _patch_heal_engines(
        monkeypatch,
        health={"overdue": ["content"], "never_ran": ["digest"]},
        recover={
            "ok": True,
            "due": ["content"],
            "started": {"content": "queued"},
            "skipped_excluded": ["email_outreach"],
        },
    )
    out = asyncio.run(job_heal_sweep(max_jobs=3))
    assert out["ok"] is True
    assert out["started"]["content"] == "queued"
    assert "overdue=1 never_ran=1 started=1" in out["detail"]


def test_job_heal_sweep_no_due_jobs(tmp_path, monkeypatch):
    from app.agents.sprint_actions import job_heal_sweep

    _patch_heal_engines(monkeypatch)
    out = asyncio.run(job_heal_sweep(max_jobs=3))
    assert out["ok"] is True
    assert out["overdue"] == [] and out["never_ran"] == []


def test_job_heal_sweep_excluded_honored(tmp_path, monkeypatch):
    from app.agents.sprint_actions import job_heal_sweep

    _patch_heal_engines(
        monkeypatch,
        health={"overdue": ["platform_dial", "content"], "never_ran": []},
        recover={
            "ok": True,
            "due": ["content"],
            "started": {"content": "queued"},
            "skipped_excluded": ["platform_dial", "email_outreach"],
        },
    )
    out = asyncio.run(job_heal_sweep(max_jobs=3))
    assert out["skipped_excluded"] == ["platform_dial", "email_outreach"]
    assert "excluded=2" in out["detail"]


def test_job_heal_sweep_engine_error_graceful(tmp_path, monkeypatch):
    from app.agents.sprint_actions import job_heal_sweep

    _patch_heal_engines(monkeypatch, recover_error=RuntimeError("watchdog lock"))
    out = asyncio.run(job_heal_sweep(max_jobs=3))
    assert out["ok"] is False
    assert "watchdog lock" in out["detail"]


def test_job_heal_sweep_concurrent_safe(tmp_path, monkeypatch):
    from app.agents.sprint_actions import job_heal_sweep

    _patch_heal_engines(
        monkeypatch,
        health={"overdue": ["content"], "never_ran": []},
        recover={
            "ok": True,
            "due": ["content"],
            "started": {"content": "queued"},
            "skipped_excluded": [],
        },
    )

    async def _two():
        a, b = await asyncio.gather(job_heal_sweep(3), job_heal_sweep(3))
        return a, b

    a, b = asyncio.run(_two())
    assert a["ok"] is True and b["ok"] is True
    assert a["started"] == b["started"] == {"content": "queued"}


# =====================================================================
# self_improve registration (dispatch + ACTIONS + stage bias)
# =====================================================================
def test_actions_registered_and_dispatchable(tmp_path, monkeypatch):
    from app.agents import self_improve as si

    for name in ("dialer_sprint_prep", "hot_wa_draft", "job_heal_sweep"):
        assert name in si.ACTIONS, f"{name} missing from ACTIONS"
        assert si.ACTIONS[name][0] is False, f"{name} should be light-cost (LLM-heavy=False)"

    # stage bias coverage
    assert "dialer_sprint_prep" in si._STAGE_ACTIONS["outreach_quality"]
    assert "hot_wa_draft" in si._STAGE_ACTIONS["conversion"]
    assert "job_heal_sweep" in si._STAGE_ACTIONS["scale"]

    # dispatch wiring: _execute routes to sprint_actions (mock engine modules)
    from app.platform import prospect_lists
    from app.voice_agent import free_ai

    monkeypatch.setattr(prospect_lists, "search", lambda **kw: [])

    async def _fake_prep(limit=3):
        return {"ok": False, "prepped": 0, "detail": "empty"}

    monkeypatch.setattr("app.agents.sprint_actions.dialer_sprint_prep", _fake_prep)
    res = asyncio.run(si._execute("dialer_sprint_prep", "test"))
    assert res["ok"] is False and res["detail"] == "dialer_prep=0 (untapped phones)"

    # hot_wa_draft dispatch → empty queue → ok False
    from app.platform import reply_agent

    monkeypatch.setattr(reply_agent, "hot_queue", lambda **kw: [])

    async def _fake_wa(limit=5):
        return {"ok": False, "drafted": 0, "skipped": 0, "detail": "empty"}

    monkeypatch.setattr("app.agents.sprint_actions.hot_wa_draft", _fake_wa)
    res = asyncio.run(si._execute("hot_wa_draft", "test"))
    assert res["ok"] is False and res["detail"] == "wa_drafts=0 skipped=0"

    # job_heal_sweep dispatch
    from app.platform import automation_health, team_scheduler

    monkeypatch.setattr(automation_health, "health", lambda: {"overdue": [], "never_ran": []})
    monkeypatch.setattr(
        team_scheduler,
        "_recover_due_jobs",
        lambda: {"ok": True, "due": [], "started": {}, "skipped_excluded": []},
    )
    res = asyncio.run(si._execute("job_heal_sweep", "test"))
    assert res["ok"] is True and res["detail"] == "overdue=0 started=0"

    # unknown action still falls through
    res = asyncio.run(si._execute("nope", "x"))
    assert res["ok"] is False and "unknown action" in res["detail"]


def test_actions_llm_heavy_flag_means_cheap_cost(tmp_path, monkeypatch):
    from app.agents import self_improve as si

    for name in ("dialer_sprint_prep", "hot_wa_draft", "job_heal_sweep"):
        # light action → estimated cost 0.5 (not 2.5)
        assert si.ACTIONS[name][0] is False
