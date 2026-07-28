"""Tests — self-improve continuous loop + skill_library auto-learn + naye social channels.
Sync + asyncio.run pattern, tmp stores monkeypatch. No network/DB needed (hermetic).
"""

from __future__ import annotations

import asyncio
import json
import random
import time
from datetime import datetime, timedelta, timezone


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
    from app.platform import automation_health as ah
    from app.platform import skill_library as sl

    monkeypatch.setattr(si, "_STATE", str(tmp_path / "state.json"))
    monkeypatch.setattr(si, "_QUEUE", str(tmp_path / "queue.jsonl"))
    monkeypatch.setattr(si, "_RUNS", str(tmp_path / "runs.jsonl"))
    monkeypatch.setattr(ah, "_RUNS", lambda: str(tmp_path / "job_runs.jsonl"))
    monkeypatch.setattr(ah, "_BEATS", lambda: str(tmp_path / "job_heartbeats.json"))
    monkeypatch.setattr(sl, "_USES", str(tmp_path / "uses.jsonl"))
    monkeypatch.setattr(sl, "_LESSONS", str(tmp_path / "lessons.jsonl"))
    return si


def test_selfimprove_gated_off(tmp_path, monkeypatch):
    si = _patch_stores(monkeypatch, tmp_path)
    monkeypatch.delenv("SELF_IMPROVE_LOOP", raising=False)
    assert si.enabled() is False
    assert asyncio.run(si.run_once()) == {"enabled": False}
    assert si.ensure_alive() == {"enabled": False}


def test_cost_tracker_persists_across_instances(tmp_path, monkeypatch):
    """F-3: CostTracker spent survives 'worker restart' (new instance, same file)."""
    from app.agents import self_improve as si

    cost_file = tmp_path / "self_improve_cost.json"
    monkeypatch.setattr(si, "_COST_FILE", str(cost_file))
    si._cost_tracker = None

    ct1 = si.CostTracker(daily_cap=50.0)
    ct1.record_cost("scrape_leads", 2.5)
    assert ct1.get_daily_status()["spent"] == 2.5
    assert ct1.get_daily_status()["note"] == "estimated_durable_file"
    assert cost_file.exists()

    ct2 = si.CostTracker(daily_cap=50.0)
    assert ct2.today_cost == 2.5
    assert ct2.can_afford("x", 47.5) is True  # 2.5 + 47.5 = 50
    assert ct2.can_afford("x", 48.0) is False


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


def test_selfimprove_stale_queue_is_visible_but_not_auto_run(tmp_path, monkeypatch):
    si = _patch_stores(monkeypatch, tmp_path)
    monkeypatch.setenv("SELF_IMPROVE_QUEUE_TTL_DAYS", "7")
    stale = {
        "id": "stale-1",
        "task": "old lead follow-up",
        "status": "pending",
        "at": (datetime.now(timezone.utc) - timedelta(days=8)).isoformat(),
    }
    si._append(si._QUEUE, stale)

    assert si._next_queued() is None
    status = si.status()
    assert status["queue_pending"] == 0
    assert status["queue_stale"] == 1
    assert status["queue_ttl_days"] == 7.0


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
    from app.platform import automation_health as ah

    with open(ah._BEATS(), encoding="utf-8") as f:
        beats = json.load(f)
    assert beats["self_improve"]["ok"] is True
    assert "scrape_leads" in beats["self_improve"]["note"]

    # daily cap guard
    monkeypatch.setenv("SELF_IMPROVE_MAX_PER_DAY", "1")
    out2 = asyncio.run(si.run_once())
    assert out2.get("skipped") == "daily_cap"
    with open(ah._BEATS(), encoding="utf-8") as f:
        beats = json.load(f)
    assert beats["self_improve"]["note"] == "daily_cap"


def test_selfimprove_tick_slot_blocks_duplicate_chains(tmp_path, monkeypatch):
    si = _patch_stores(monkeypatch, tmp_path)
    monkeypatch.setenv("SELF_IMPROVE_LOOP", "1")
    monkeypatch.setenv("SELF_IMPROVE_GAP_S", "180")

    class FakeRedis:
        def __init__(self):
            self.store = {}

        def get(self, key):
            val = self.store.get(key)
            return val.encode("utf-8") if isinstance(val, str) else val

        def set(self, key, val, nx=False, ex=None):
            if nx and key in self.store:
                return False
            self.store[key] = str(val)
            return True

        def delete(self, key):
            self.store.pop(key, None)

    fake = FakeRedis()
    monkeypatch.setattr(si, "_redis_client", lambda: fake)

    token = si.acquire_tick_slot()
    assert token
    assert si.acquire_tick_slot() == ""

    si.release_tick_slot(token)
    assert si.acquire_tick_slot() == ""

    si.note_tick_requeue(3600)
    assert float(fake.store["self_improve:tick_next_allowed"]) > time.time() + 3500


def test_selfimprove_tick_slot_accepts_small_eta_clock_skew(tmp_path, monkeypatch):
    """Celery ETA thoda early arrive ho sakta hai; NX running-lock still dedupes it."""
    si = _patch_stores(monkeypatch, tmp_path)

    class FakeRedis:
        def __init__(self):
            self.store = {
                "self_improve:tick_next_allowed": str(time.time() + 0.5),
            }

        def get(self, key):
            val = self.store.get(key)
            return val.encode("utf-8") if isinstance(val, str) else val

        def set(self, key, val, nx=False, ex=None):
            if nx and key in self.store:
                return False
            self.store[key] = str(val)
            return True

    fake = FakeRedis()
    monkeypatch.setattr(si, "_redis_client", lambda: fake)

    token = si.acquire_tick_slot()
    assert token, "sub-second Celery ETA skew must not kill the only requeue chain"
    assert si.acquire_tick_slot() == "", "running-lock must still reject a duplicate"


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


def test_study_skills_sweep_round_robins_all_skills(tmp_path, monkeypatch):
    si = _patch_stores(monkeypatch, tmp_path)
    from app.platform import skill_library as sl
    from app.platform import skill_pack
    from app.voice_agent import free_ai

    skills = [
        {"name": "alpha", "description": "Alpha discipline", "source": "project", "chars": 10},
        {"name": "beta", "description": "Beta discipline", "source": "project", "chars": 10},
    ]

    monkeypatch.setattr(skill_pack, "enabled", lambda: True)
    monkeypatch.setattr(skill_pack, "list_skills", lambda: skills)
    monkeypatch.setattr(skill_pack, "find", lambda *a, **k: [{"name": "alpha"}])
    monkeypatch.setattr(
        skill_pack,
        "load",
        lambda name: {
            "name": name,
            "description": f"{name} discipline",
            "text": f"# {name}\nUse {name} safely.",
        },
    )

    async def fake_chat(system, messages, **kw):
        return ("Apply the selected skill in a bounded, verified way.", "mock")

    monkeypatch.setattr(free_ai, "chat", fake_chat)

    first = asyncio.run(si._study_skills("use all skills one by one in loop"))
    second = asyncio.run(si._study_skills("use all skills one by one in loop"))

    assert first["ok"] is True and "alpha" in first["detail"]
    assert second["ok"] is True and "beta" in second["detail"]
    topics = [r["topic"] for r in sl.lessons(limit=5)]
    assert "skill:alpha" in topics
    assert "skill:beta" in topics


def test_skill_sweep_action_executes_round_robin(tmp_path, monkeypatch):
    si = _patch_stores(monkeypatch, tmp_path)
    from app.platform import skill_pack

    skills = [
        {"name": "alpha", "description": "Alpha discipline", "source": "project", "chars": 10},
        {"name": "beta", "description": "Beta discipline", "source": "project", "chars": 10},
    ]

    monkeypatch.setattr(skill_pack, "enabled", lambda: True)
    monkeypatch.setattr(skill_pack, "list_skills", lambda: skills)
    monkeypatch.setattr(
        skill_pack,
        "load",
        lambda name: {
            "name": name,
            "description": f"{name} discipline",
            "text": f"# {name}\nUse {name} safely.",
        },
    )

    assert "skill_sweep" in si.ACTIONS
    first = asyncio.run(si._execute("skill_sweep", "ignored"))
    second = asyncio.run(si._execute("skill_sweep", "ignored"))

    assert first["ok"] is True and "alpha" in first["detail"]
    assert second["ok"] is True and "beta" in second["detail"]


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
    si._append(
        si._RUNS, {"action": "seo_pages", "ok": True, "detail": "2 pages", "outcome_value": 0.9}
    )
    si._append(
        si._RUNS, {"action": "scrape_leads", "ok": True, "detail": "covered", "outcome_value": 0.5}
    )

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


# ----------------------------- voice_learn (voice-agent self-improve) ----------------------------- #
def _patch_voice_stores(monkeypatch, tmp_path):
    from app.agents import self_improve as si
    from app.platform import skill_library as sl
    from app.platform import team

    monkeypatch.setattr(si, "_VOICE_LEARN_STATE", str(tmp_path / "voice_learn_state.json"))
    monkeypatch.setattr(sl, "_USES", str(tmp_path / "uses.jsonl"))
    monkeypatch.setattr(sl, "_LESSONS", str(tmp_path / "lessons.jsonl"))
    monkeypatch.setattr(team, "log_event", lambda *a, **k: None)
    return si


def test_voice_learn_records_brain_lesson_and_dedupes(tmp_path, monkeypatch):
    """Weak REAL call → voice_{niche} lesson record karta (telecaller_brain ise
    lessons_snippet('voice_solar') se consume karta = compound). Dedupe: same
    weakest call dobara learn nahi hota. Reuse-only: live_eval mock se driven."""
    si = _patch_voice_stores(monkeypatch, tmp_path)
    from app.agents import live_eval
    from app.platform import skill_library as sl
    from app.voice_agent import free_ai

    report = {
        "n": 3,
        "mean_score": 0.55,
        "total_qa_findings": 2,
        "per_call": [
            {
                "call_id": "call-weak-1",
                "niche": "solar",
                "score": 0.4,
                "qa_finding_count": 2,
                "qa_findings": ["repeat", "off-topic"],
            },
            {
                "call_id": "call-ok-1",
                "niche": "solar",
                "score": 0.9,
                "qa_finding_count": 0,
                "qa_findings": [],
            },
        ],
    }
    monkeypatch.setattr(live_eval, "eval_recent_calls", lambda n, **k: report)

    async def fake_chat(system, messages, **kw):
        return (
            "Customer ka exact sawaal sun ke ek-line KB-grounded jawab de, repeat mat kar.",
            "mock",
        )

    monkeypatch.setattr(free_ai, "chat", fake_chat)

    out = asyncio.run(si._voice_learn())
    assert out["ok"] is True
    # lesson voice_solar topic me — yahi brain consume karta hai
    assert "voice_solar" in [lsn["topic"] for lsn in sl.lessons("voice_solar")]
    assert "KB-grounded" in sl.lessons_snippet("voice_solar")

    # dedupe: same weakest call dobara → naya lesson nahi
    out2 = asyncio.run(si._voice_learn())
    assert "already learned" in out2["detail"]


def test_voice_learn_no_calls_graceful_skip(tmp_path, monkeypatch):
    si = _patch_voice_stores(monkeypatch, tmp_path)
    from app.agents import live_eval

    monkeypatch.setattr(live_eval, "eval_recent_calls", lambda n, **k: {"n": 0, "per_call": []})
    out = asyncio.run(si._voice_learn())
    assert out["ok"] is True and "no recent calls" in out["detail"]


def test_voice_learn_clean_calls_no_lesson_spam(tmp_path, monkeypatch):
    si = _patch_voice_stores(monkeypatch, tmp_path)
    from app.agents import live_eval
    from app.platform import skill_library as sl

    report = {
        "n": 2,
        "mean_score": 0.95,
        "per_call": [
            {
                "call_id": "c1",
                "niche": "gym",
                "score": 0.95,
                "qa_finding_count": 0,
                "qa_findings": [],
            },
            {
                "call_id": "c2",
                "niche": "gym",
                "score": 0.9,
                "qa_finding_count": 0,
                "qa_findings": [],
            },
        ],
    }
    monkeypatch.setattr(live_eval, "eval_recent_calls", lambda n, **k: report)
    out = asyncio.run(si._voice_learn())
    assert out["ok"] is True and "clean" in out["detail"]
    assert sl.lessons("voice_gym") == []  # healthy calls = koi lesson spam nahi


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


# ------------------------- ApprovalQueue (cross-process) ------------------------- #
def test_approval_queue_visible_across_separate_instances(tmp_path):
    """Prod runs ticks in the Celery worker container and serves the approve/
    reject API + Office HQ UI from the app container — two different
    processes. An in-memory queue is invisible across that boundary; state
    must flow through the shared approvals file instead. Simulate that split
    with two independent ApprovalQueue instances pointed at the same file."""
    from app.agents.self_improve import ApprovalQueue

    shared_file = str(tmp_path / "approvals.jsonl")
    worker_side = ApprovalQueue(approval_required=True)
    worker_side._approval_file = shared_file
    app_side = ApprovalQueue(approval_required=True)
    app_side._approval_file = shared_file

    assert worker_side.queue_task("social_drafts", "test reason", 2.5) == ""

    pending = app_side.get_pending()
    assert len(pending) == 1
    task_id = pending[0]["id"]

    assert app_side.approve(task_id) is True
    assert worker_side.get_pending() == []
    assert app_side.get_pending() == []


def test_approval_queue_consumes_approval_to_actually_run(tmp_path):
    """is_approved() used to be dead code -- nothing ever re-ran an approved
    task, so approving one had zero effect. queue_task() must now consume a
    previously-approved request for the same action and signal the caller
    to execute it, without re-queuing or duplicating."""
    from app.agents.self_improve import ApprovalQueue

    aq = ApprovalQueue(approval_required=True)
    aq._approval_file = str(tmp_path / "approvals.jsonl")

    assert aq.queue_task("seo_pages", "reason", 1.0) == ""
    task_id = aq.get_pending()[0]["id"]

    # Same action ticked again while still waiting -- must not duplicate.
    assert aq.queue_task("seo_pages", "reason", 1.0) == ""
    assert len(aq.get_pending()) == 1

    assert aq.approve(task_id) is True
    assert aq.get_pending() == []

    # Next tick for the same action: consumed -> truthy id, caller runs it now.
    assert aq.queue_task("seo_pages", "reason", 1.0) == task_id
    assert aq.is_approved(task_id) is False  # consumed, not still "approved"

    # A further tick must queue a fresh request, not resurrect the consumed one.
    assert aq.queue_task("seo_pages", "reason", 1.0) == ""


def test_approval_queue_reject_does_not_resurrect_as_approved(tmp_path):
    from app.agents.self_improve import ApprovalQueue

    aq = ApprovalQueue(approval_required=True)
    aq._approval_file = str(tmp_path / "approvals.jsonl")

    aq.queue_task("content_pack", "reason", 1.0)
    task_id = aq.get_pending()[0]["id"]
    assert aq.reject(task_id, reason="not now") is True
    assert aq.get_pending() == []
    assert aq.is_approved(task_id) is False

    # Rejected action queues a brand-new request on the next tick.
    assert aq.queue_task("content_pack", "reason", 1.0) == ""
    assert len(aq.get_pending()) == 1
