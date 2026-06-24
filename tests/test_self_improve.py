"""Tests — self-improve continuous loop + skill_library auto-learn + naye social channels.
Sync + asyncio.run pattern, tmp stores monkeypatch. No network/DB needed (hermetic).
"""

from __future__ import annotations

import asyncio
import random


# ----------------------------- skill library ----------------------------- #
def test_skill_library_learn_and_pick(tmp_path, monkeypatch):
    from app.platform import skill_library as sl

    monkeypatch.setattr(sl, "_USES", str(tmp_path / "uses.jsonl"))
    monkeypatch.setattr(sl, "_LESSONS", str(tmp_path / "lessons.jsonl"))

    # fresh = empty stats, pick neutral
    assert sl.stats() == {}
    assert sl.pick_action(["a", "b"]) in ("a", "b")

    # winner vs loser learn
    for _ in range(4):
        sl.record_use("scrape_leads", True, "ok")
    sl.record_use("seo_pages", False, "fail")
    st = sl.stats()
    assert st["scrape_leads"]["rate"] > st["seo_pages"]["rate"]
    assert sl.best(1)[0]["skill"] == "scrape_leads"

    class ExploitRng(random.Random):
        def random(self):
            return 0.99  # > epsilon -> exploit best

    assert sl.pick_action(["seo_pages", "scrape_leads"], rng=ExploitRng()) == "scrape_leads"

    # lessons
    r = sl.record_lesson("outreach", "Subject line chhota rakho, reply rate badta hai")
    assert r["ok"] is True
    assert sl.lessons("outreach")[0]["topic"] == "outreach"
    assert "Subject" in sl.lessons_snippet("outreach reply")
    assert sl.record_lesson("x", "")["ok"] is False
    assert sl.summary()["skills_tracked"] == 2


# ----------------------------- self-improve loop ----------------------------- #
def _patch_stores(monkeypatch, tmp_path):
    from app.agents import self_improve as si
    from app.platform import skill_library as sl

    monkeypatch.setattr(si, "_STATE", str(tmp_path / "state.json"))
    monkeypatch.setattr(si, "_QUEUE", str(tmp_path / "queue.jsonl"))
    monkeypatch.setattr(si, "_RUNS", str(tmp_path / "runs.jsonl"))
    monkeypatch.setattr(sl, "_USES", str(tmp_path / "uses.jsonl"))
    monkeypatch.setattr(sl, "_LESSONS", str(tmp_path / "lessons.jsonl"))
    return si


def test_selfimprove_gated_off(tmp_path, monkeypatch):
    si = _patch_stores(monkeypatch, tmp_path)
    monkeypatch.delenv("SELF_IMPROVE_LOOP", raising=False)
    assert si.enabled() is False
    assert asyncio.run(si.run_once()) == {"enabled": False}
    assert si.ensure_alive() == {"enabled": False}


def test_selfimprove_queue_and_pick(tmp_path, monkeypatch):
    si = _patch_stores(monkeypatch, tmp_path)
    assert si.add_task("")["ok"] is False
    r = si.add_task("Pune solar 10 leads lao", action="scrape_leads")
    assert r["ok"] is True

    picked = asyncio.run(si._pick_next())
    assert picked["source"] == "queue"
    assert picked["action"] == "scrape_leads"
    assert picked["queued_id"] == r["task"]["id"]

    si._mark_done(r["task"]["id"], "done")
    assert si._next_queued() is None


def test_selfimprove_run_once_learns_and_chains(tmp_path, monkeypatch):
    si = _patch_stores(monkeypatch, tmp_path)
    from app.platform import skill_library as sl

    monkeypatch.setenv("SELF_IMPROVE_LOOP", "1")

    async def fake_pick():
        return {"task": "[auto] test", "action": "scrape_leads", "source": "auto"}

    async def fake_exec(action, task):
        return {"ok": True, "detail": f"executed {action}"}

    monkeypatch.setattr(si, "_pick_next", fake_pick)
    monkeypatch.setattr(si, "_execute", fake_exec)

    out = asyncio.run(si.run_once())
    assert out["enabled"] is True and out["ok"] is True
    assert out["action"] == "scrape_leads"
    # learn hua: skill_library me use record
    assert sl.stats()["scrape_leads"]["uses"] == 1
    # heartbeat + runs_today
    st = si.status()
    assert st["state"]["runs_today"] == 1
    assert st["recent_runs"][0]["action"] == "scrape_leads"

    # daily cap guard
    monkeypatch.setenv("SELF_IMPROVE_MAX_PER_DAY", "1")
    out2 = asyncio.run(si.run_once())
    assert out2.get("skipped") == "daily_cap"


def test_selfimprove_execute_error_never_raises(tmp_path, monkeypatch):
    si = _patch_stores(monkeypatch, tmp_path)
    monkeypatch.setenv("SELF_IMPROVE_LOOP", "1")

    async def fake_pick():
        return {"task": "t", "action": "optimizer", "source": "auto"}

    async def boom(action, task):
        raise RuntimeError("engine down")

    monkeypatch.setattr(si, "_pick_next", fake_pick)
    monkeypatch.setattr(si, "_execute", boom)
    out = asyncio.run(si.run_once())
    assert out["enabled"] is True and out["ok"] is False
    assert "engine down" in out["detail"]


def test_reflect_grounds_on_prior_lessons_and_winning_traces(tmp_path, monkeypatch):
    """_reflect() ab (a) loop ke apne purane self_improve lessons aur (b) best trajectory
    replay-hints ko reflection digest me feed karta — dono pehle dormant loops the
    (replay_hint 0-caller; self_improve lessons write-only). free_ai.chat mock se digest
    capture karke verify + flag OFF pe replay inert."""
    si = _patch_stores(monkeypatch, tmp_path)
    from app.agents import trajectory as traj
    from app.platform import skill_library as sl
    from app.voice_agent import free_ai

    # recent runs (outcome_value ke saath taaki replay top-reward action pe ground ho)
    si._append(si._RUNS, {"action": "seo_pages", "ok": True, "detail": "2 pages", "outcome_value": 0.9})
    si._append(si._RUNS, {"action": "scrape_leads", "ok": True, "detail": "covered", "outcome_value": 0.5})

    # WIRE B: loop ka apna prior lesson (reflexion memory)
    sl.record_lesson("self_improve", "MARKER_PRIOR_LESSON seo_pages best perform kar raha")

    # WIRE A: trajectory enable + ek winning trace seed
    monkeypatch.setenv("TRAJECTORY_LEARN", "1")
    monkeypatch.setattr(traj, "_STORE", str(tmp_path / "traj.jsonl"))
    traj.record_trajectory("seo_pages", [{"step": "MARKER_TRACE_STEP"}], "ok", reward=0.9)

    captured: dict[str, str] = {}

    async def fake_chat(system, messages, **kw):
        captured["digest"] = str(messages[-1].get("content", ""))
        return ("Lesson: seo_pages pe focus rakho.", "mock")

    monkeypatch.setattr(free_ai, "chat", fake_chat)

    out = asyncio.run(si._reflect())
    assert out["ok"] is True
    digest = captured["digest"]
    assert "MARKER_PRIOR_LESSON" in digest  # WIRE B: prior lessons consumed
    assert "MARKER_TRACE_STEP" in digest  # WIRE A: winning trace grounded

    # flag OFF → replay grounding inert (zero behaviour change default)
    monkeypatch.delenv("TRAJECTORY_LEARN", raising=False)
    captured.clear()
    out2 = asyncio.run(si._reflect())
    assert out2["ok"] is True
    assert "MARKER_TRACE_STEP" not in captured["digest"]


# ----------------------------- social channels ----------------------------- #
def test_social_channels_fallback_drafts(monkeypatch):
    from app.marketing import social_channels as sc
    from app.voice_agent import free_ai

    async def no_llm(*a, **k):
        raise RuntimeError("no providers")

    monkeypatch.setattr(free_ai, "chat", no_llm)

    out = asyncio.run(sc.draft("youtube_shorts", "solar", "Pune"))
    assert out["ok"] is True and "HOOK" in out["draft"]
    assert asyncio.run(sc.draft("not_a_channel"))["ok"] is False

    batch = asyncio.run(sc.draft_batch("gym", "Mumbai", limit=3))
    assert batch["ok"] is True and batch["count"] == 3
    assert len(sc.list_channels()) == 8


def test_bandit_includes_new_channels():
    from app.marketing import channel_experiments as ce

    for ch in (
        "instagram_comment",
        "youtube_shorts",
        "gbp_qna",
        "whatsapp_status",
        "micro_influencer",
        "local_pr",
        "event_outreach",
        "listing_optimizer",
    ):
        assert ch in ce.CHANNELS
        assert ch in ce._SOCIAL_V2
    # stats sab channels cover karta
    assert set(ce.stats().keys()) == set(ce.CHANNELS)
