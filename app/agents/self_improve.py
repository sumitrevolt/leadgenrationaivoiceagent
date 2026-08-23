"""Self-Improve CONTINUOUS loop — task complete → agla task, koi fixed timing nahi.

DESIGN (2026 self-improving agent pattern, free-stack):
  pick task (queue ya auto-generate from weakest funnel stage + skill_library)
  → execute (SAB existing engines reuse — rebuild nahi)
  → learn (skill_library.record_use; har N runs pe LLM reflection → lesson)
  → agla task turant queue (Celery self-requeue, countdown=gap) → repeat forever.

SAFETY (prod-down + Groq-TPD lessons baked-in):
  - GATED `SELF_IMPROVE_LOOP=1` (default OFF = sab no-op). Web process me KABHI
    heavy run nahi — sirf Celery worker me (tick task), API sirf enqueue/status.
  - Guards: SELF_IMPROVE_GAP_S (default 180s min gap, token safety),
    SELF_IMPROVE_MAX_PER_DAY (default 60), per-iteration hard timeout 240s,
    LLM-heavy actions skip jab providers degraded (llm_metrics ok-rate).
  - Loop kabhi marta nahi: exception pe bhi requeue; watchdog `ensure_alive()`
    stale heartbeat pe revive karta (dead-man safe).

Ban-safe: koi auto-send/post nahi — sirf wahi engines jo khud gated/draft-only.
Stores: data/self_improve_state.json · self_improve_queue.jsonl · self_improve_runs.jsonl.
Import-safe, kabhi raise nahi.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_STATE = os.path.join("data", "self_improve_state.json")
_QUEUE = os.path.join("data", "self_improve_queue.jsonl")
_RUNS = os.path.join("data", "self_improve_runs.jsonl")
_VOICE_LEARN_STATE = os.path.join("data", "voice_learn_state.json")

_ITER_TIMEOUT_S = 240  # ek iteration ka hard cap (event-loop/token safety)
_REFLECT_EVERY = 8  # har N runs pe LLM reflection → lesson


def _now() -> datetime:
    return datetime.now(timezone.utc)


def enabled() -> bool:
    return os.environ.get("SELF_IMPROVE_LOOP", "0").strip().lower() in ("1", "true", "yes")


def gap_seconds() -> int:
    """Task-complete → agla task ka min gap (koi cron timing nahi, bas token-safety pause)."""
    try:
        return max(30, int(os.environ.get("SELF_IMPROVE_GAP_S", "180")))
    except Exception:
        return 180


def max_per_day() -> int:
    try:
        return max(1, int(os.environ.get("SELF_IMPROVE_MAX_PER_DAY", "120")))
    except Exception:
        return 120


_TICK_RUNNING_KEY = "self_improve:tick_running"
_TICK_NEXT_ALLOWED_KEY = "self_improve:tick_next_allowed"
_TICK_ETA_SKEW_S = 2.0  # Celery ETA vs Redis timestamp sub-second drift allowance


def _redis_client():
    try:
        import redis as _redis

        from app.config import settings

        return _redis.Redis.from_url(str(settings.redis_url), socket_timeout=2)
    except Exception:
        return None


def _redis_value(val: Any) -> str:
    if isinstance(val, bytes):
        try:
            return val.decode("utf-8")
        except Exception:
            return ""
    return str(val or "")


def acquire_tick_slot() -> str:
    """Distributed guard: duplicate self-requeue chains ek hi window me run na karein."""
    token = uuid.uuid4().hex
    r = _redis_client()
    if r is None:
        # W1.5: FAIL-CLOSED — Redis client unavailable = koi slot NAHI (guard ke bina
        # duplicate self-requeue chains ban jate the). Caller "" ko clean-skip karta.
        logger.debug("[self-improve] tick-slot: Redis client unavailable — fail-closed skip")
        return ""
    try:
        next_allowed = float(_redis_value(r.get(_TICK_NEXT_ALLOWED_KEY)) or 0)
        # `note_tick_requeue()` broker enqueue ke just baad timestamp likhta hai,
        # isliye ETA task kuch milliseconds pehle land kar sakta hai. Far-future
        # ticks ab bhi block; near-boundary tick ko NX running-lock safely dedupe karega.
        if next_allowed and time.time() < (next_allowed - _TICK_ETA_SKEW_S):
            return ""
        ttl = max(300, _ITER_TIMEOUT_S + 120)
        if not r.set(_TICK_RUNNING_KEY, token, nx=True, ex=ttl):
            return ""
        return token
    except Exception as e:
        # W1.5: FAIL-CLOSED — Redis error (down) pe slot mat do; ek missed tick
        # duplicate chains se behtar. No per-tick stack-trace (debug-log only).
        logger.debug("[self-improve] tick-slot: Redis error — fail-closed skip: %s", e)
        return ""


def release_tick_slot(token: str) -> None:
    """Running slot release karo aur default gap tak next duplicate tick block karo."""
    if not token:
        return
    r = _redis_client()
    if r is None:
        return
    try:
        if _redis_value(r.get(_TICK_RUNNING_KEY)) == token:
            r.delete(_TICK_RUNNING_KEY)
        next_allowed = time.time() + gap_seconds()
        r.set(_TICK_NEXT_ALLOWED_KEY, str(next_allowed), ex=max(300, gap_seconds() + 300))
    except Exception:
        pass


def note_tick_requeue(countdown: int | float) -> None:
    """Successful requeue ka actual future slot mark karo (daily-cap pe 3600s)."""
    r = _redis_client()
    if r is None:
        return
    try:
        delay = max(0, float(countdown))
        r.set(_TICK_NEXT_ALLOWED_KEY, str(time.time() + delay), ex=max(300, int(delay) + 300))
    except Exception:
        pass


# ---------------------------------------------------------------- stores


def _read_jsonl(path: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            rows.append(json.loads(line))
                        except Exception:
                            pass
    except Exception:
        pass
    return rows


def _append(path: str, rec: dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


def _load_state() -> dict[str, Any]:
    try:
        if os.path.exists(_STATE):
            with open(_STATE, encoding="utf-8") as f:
                return json.load(f) or {}
    except Exception:
        pass
    return {}


def _save_state(st: dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(_STATE) or ".", exist_ok=True)
        with open(_STATE, "w", encoding="utf-8") as f:
            json.dump(st, f, ensure_ascii=False, default=str)
    except Exception:
        pass


def _heartbeat(extra: dict[str, Any] | None = None) -> None:
    st = _load_state()
    day = _now().strftime("%Y-%m-%d")
    if st.get("day") != day:
        st["day"] = day
        st["runs_today"] = 0
    st["last_tick"] = time.time()
    st["last_tick_at"] = _now().isoformat()
    if extra:
        st.update(extra)
    _save_state(st)
    try:
        from app.platform import automation_health

        status = str(st.get("status") or "tick")
        last_action = str(st.get("last_action") or "")
        note = last_action if status == "ok" and last_action else status
        # ENTERPRISE FIX (2026-07-10): pehle hamesha ok=True send hota tha —
        # automation_health pe self_improve ka card kabhi red nahi hota chahe
        # daily_cap / gate_skip / budget_cap / approval_pending ho. Ab sirf
        # "ok" status hi ok=True — baaki sab WARNING ya ERROR (not OK).
        is_ok = status == "ok"
        automation_health.record_run("self_improve", ok=is_ok, seconds=0.0, note=note)
    except Exception:
        pass


# ---------------------------------------------------------------- task queue


def add_task(task: str, action: str = "", source: str = "manual") -> dict[str, Any]:
    """Manual/agent task queue me daalo — loop ise pehle uthayega."""
    try:
        t = (task or "").strip()
        if not t:
            return {"ok": False, "error": "empty task"}
        rec = {
            "id": uuid.uuid4().hex[:12],
            "task": t[:300],
            "action": (action or "").strip().lower()[:40],
            "source": source[:20],
            "status": "pending",
            "at": _now().isoformat(),
        }
        _append(_QUEUE, rec)
        return {"ok": True, "task": rec}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def queue_ttl_days() -> float:
    """Pending work older than this is skipped, never deleted or auto-run.

    Seven days keeps stale lead/revenue tasks from executing after a long pause while
    allowing operators to extend the window explicitly for a planned backlog.
    """
    try:
        return min(365.0, max(1.0, float(os.getenv("SELF_IMPROVE_QUEUE_TTL_DAYS", "7"))))
    except Exception:
        return 7.0


def _is_stale_queue_row(row: dict[str, Any], now: datetime | None = None) -> bool:
    if row.get("status") != "pending":
        return False
    try:
        queued_at = datetime.fromisoformat(str(row.get("at", "")))
        if queued_at.tzinfo is None:
            queued_at = queued_at.replace(tzinfo=timezone.utc)
        return (now or _now()) - queued_at > timedelta(days=queue_ttl_days())
    except Exception:
        # Malformed timestamps remain visible and are preserved for operator review.
        return False


def _next_queued() -> dict[str, Any] | None:
    """Pehla fresh pending task; stale work is preserved but never auto-run."""
    rows = _read_jsonl(_QUEUE)
    done = {r.get("id") for r in rows if r.get("status") == "done"}
    for r in rows:
        if r.get("status") == "pending" and r.get("id") not in done and not _is_stale_queue_row(r):
            return r
    return None


def _mark_done(task_id: str, result: str = "") -> None:
    _append(
        _QUEUE, {"id": task_id, "status": "done", "result": result[:200], "at": _now().isoformat()}
    )


# ---------------------------------------------------------------- actions (SAB reuse)

# action → (LLM-heavy?, description). Side-effect engines khud gated hain.
ACTIONS: dict[str, tuple[bool, str]] = {
    "scrape_leads": (False, "naye prospects scrape (42-niche rotation, Places/OSM)"),
    "harvest_leads": (False, "multi-source harvest (websearch/opendata/enrich, legal-only)"),
    "channel_experiments": (True, "2 channel experiments (bandit) — drafts/SEO pages"),
    "content_pack": (True, "best-niche content pack (posts+hashtags+offer)"),
    "seo_pages": (True, "2 niche×city SEO landing pages (organic inbound)"),
    "sales_deepdive": (True, "top hot-leads pe 5-agent sales deep-dive (drafts)"),
    "social_drafts": (True, "naye social channels ke drafts (insta/shorts/status...)"),
    "revenue_sweep": (False, "dunning + lifecycle nurture due-runs"),
    "optimizer": (True, "growth optimizer full pass (weakest stage + corrective)"),
    "campaign_optimize": (True, "Kiran campaign optimization (proposals + bandit + voice eval)"),
    "reflection": (True, "recent runs pe LLM reflection → lesson save"),
    "study_skills": (True, "project skill padh ke lesson nikalo (skill_pack → skill_library)"),
    "skill_sweep": (True, "project skills ko stable round-robin me one-by-one study karo"),
    "code_scan": (False, "observability signals se code-upgrade proposals (Vikram, gated)"),
    "voice_eval": (False, "voice agent persona eval smoke (Swara/Arjun, gated VOICE_EVAL_AUTO)"),
    "voice_learn": (True, "real call transcripts analyze → voice lesson (brain consume, compound)"),
    "rescore_pipeline": (False, "DB leads rescore + hot-lead surface (Neha/Rohan, revenue)"),
    "cadence_sweep": (False, "omnichannel cadence due-steps advance (gated CADENCE_ENGINE)"),
    "dialer_sprint_prep": (
        False,
        "untapped prospect phones ke human-dialer prep briefs (read-only)",
    ),
    "hot_wa_draft": (False, "Hot Queue warm leads ke WhatsApp reply drafts (draft-only, ban-safe)"),
    "job_heal_sweep": (
        False,
        "stale scheduled-job heartbeats detect + bounded re-dispatch (reliability)",
    ),
}

# funnel weakest-stage → preferred actions (deterministic bias)
# 2026-06-13 REBALANCE: agents 90%+ INTERNAL busywork (study_skills/reflection/
# social_drafts) kar rahe the, real outbound/revenue kam. Har stage ko ab OUTBOUND/
# revenue actions (harvest_leads, sales_deepdive, revenue_sweep, channel_experiments,
# seo_pages) ki taraf bias kiya. Pure-meta hatai: reflection waise bhi har
# _REFLECT_EVERY(8) runs pe ALAG se chalti hai; study_skills sirf 'scale' me rakha
# (periodic learning). Outbound velocity ↑, self-monitoring noise ↓.
_STAGE_ACTIONS = {
    "lead_supply": ["harvest_leads", "scrape_leads", "seo_pages", "channel_experiments"],
    "outreach_quality": [
        "sales_deepdive",
        "harvest_leads",
        "channel_experiments",
        "social_drafts",
        "cadence_sweep",
        "dialer_sprint_prep",
    ],
    "inbound": ["seo_pages", "channel_experiments", "social_drafts"],
    "conversion": [
        "sales_deepdive",
        "revenue_sweep",
        "content_pack",
        "voice_eval",
        "voice_learn",
        "rescore_pipeline",
        "hot_wa_draft",
        "dialer_sprint_prep",
    ],
    "retention": ["revenue_sweep", "content_pack"],
    "scale": [
        "optimizer",
        "campaign_optimize",
        "channel_experiments",
        "harvest_leads",
        "skill_sweep",
        "job_heal_sweep",
    ],
}


def _llm_healthy() -> bool:
    """Providers degraded ho to LLM-heavy actions skip (Groq TPD lesson)."""
    try:
        from app.platform import llm_metrics

        st = llm_metrics.stats(window=200) or {}
        provs = st.get("providers") or {}
        if not provs:
            return True
        ok_any = any(
            (p.get("ok_rate") or p.get("ok", 0)) for p in provs.values() if isinstance(p, dict)
        )
        return bool(ok_any)
    except Exception:
        return True  # fail-open: metrics na ho to normal


async def _pick_next() -> dict[str, Any]:
    """Agla task chuno: (1) manual queue, (2) weakest-stage bias + skill_library
    epsilon-greedy. LLM sirf task-text refine ke liye (fallback static)."""
    q = _next_queued()
    if q:
        return {
            "task": q["task"],
            "action": q.get("action") or "",
            "queued_id": q["id"],
            "source": "queue",
        }

    stage = "lead_supply"
    try:
        from app.agents import growth_optimizer

        snap = await asyncio.wait_for(growth_optimizer.funnel_snapshot(), timeout=30)
        stage = (growth_optimizer.weakest_stage(snap) or {}).get("stage") or "lead_supply"
    except Exception:
        pass

    candidates = _STAGE_ACTIONS.get(stage, list(ACTIONS.keys()))
    if not _llm_healthy():
        light = [a for a in candidates if not ACTIONS.get(a, (True, ""))[0]]
        candidates = light or ["scrape_leads", "revenue_sweep"]

    # DIVERSITY GUARD v2 (2026-06-12): sales_deepdive ek action monopoly le raha tha.
    # 2-tier approach: (1) last 6 runs dedup, (2) 20-min per-action cooldown.
    try:
        recent_runs = _read_jsonl(_RUNS)[-6:]
        recent_acts = [r.get("action") for r in recent_runs if r.get("action")]
        deduped = [a for a in candidates if a not in recent_acts]
        if deduped:
            candidates = deduped
        # agar sab recently used = candidates unchanged (fallback safe)
    except Exception:
        pass
    # Cooldown: agar koi action 20 min pehle chala to deprioritize (hata do, fallback nahi)
    try:
        from datetime import datetime, timedelta
        from datetime import timezone as _tz

        cutoff = datetime.now(_tz.utc) - timedelta(minutes=20)
        recent_runs_all = _read_jsonl(_RUNS)[-20:]
        hot = set()
        for r in recent_runs_all:
            try:
                ran_at = datetime.fromisoformat(str(r.get("at", "")))
                if ran_at.tzinfo is None:
                    ran_at = ran_at.replace(tzinfo=_tz.utc)
                if ran_at > cutoff:
                    hot.add(r.get("action"))
            except Exception:
                pass
        cooled = [a for a in candidates if a not in hot]
        if cooled:
            candidates = cooled
    except Exception:
        pass

    try:
        from app.platform import skill_library

        action = skill_library.pick_action(candidates) or candidates[0]
    except Exception:
        action = candidates[0]

    return {
        "task": f"[auto] weakest stage '{stage}' improve karo via {action}",
        "action": action,
        "stage": stage,
        "source": "auto",
    }


async def _execute(action: str, task: str) -> dict[str, Any]:
    """Action dispatch — sab existing engines, lazy import, bounded."""
    if action == "scrape_leads":
        from app.platform import niche_prospector

        res = await niche_prospector.run(batch=4, limit_per_query=4)
        return {"ok": bool(res.get("ok", True)), "detail": f"covered={res.get('covered', [])}"}
    if action == "harvest_leads":
        from app.platform import lead_harvester

        # `scrape_leads` already owns niche_prospector. Nesting that same
        # multi-city workflow here repeatedly exhausted this iteration's 240s
        # budget during Places cooldown. Keep harvest complementary and bounded.
        res = await lead_harvester.run_harvest(
            limit=4,
            sources=["osm", "websearch", "opendata"],
        )
        return {
            "ok": bool(res.get("ok")),
            "detail": f"+{res.get('new_leads', 0)} leads (dedup {res.get('deduped', 0)}, enrich {((res.get('enrich') or {}).get('found', 0))})",
        }
    if action == "channel_experiments":
        from app.marketing import channel_experiments

        res = await channel_experiments.run_daily(2)
        n = len(res.get("launched") or [])
        return {"ok": res.get("enabled", False) and n > 0, "detail": f"{n} experiments"}
    if action == "content_pack":
        from app.marketing import niche_pack
        from app.marketing.channel_experiments import _pick_niche_city

        niche, _ = _pick_niche_city()
        res = await niche_pack.build_pack(niche)
        return {"ok": bool(res.get("posts") or res.get("ok", True)), "detail": f"pack: {niche}"}
    if action == "seo_pages":
        from app.marketing import seo_pages

        res = await seo_pages.generate_batch(limit=2)
        return {
            "ok": bool(res.get("pages") or res.get("count")),
            "detail": f"{res.get('count', 0)} pages",
        }
    if action == "sales_deepdive":
        from app.agents import sales_team

        res = await sales_team.run_auto(2)
        return {
            "ok": bool(res.get("ok", True)),
            "detail": f"analyzed={res.get('analyzed', res.get('count', 0))}",
        }
    if action == "social_drafts":
        from app.marketing import social_channels
        from app.marketing.channel_experiments import _pick_niche_city

        niche, city = _pick_niche_city()
        res = await social_channels.draft_batch(niche=niche, city=city, channels=None, limit=3)
        return {
            "ok": bool(res.get("count")),
            "detail": f"{res.get('count', 0)} social drafts ({niche}/{city})",
        }
    if action == "revenue_sweep":
        out = []
        try:
            from app.billing import dunning

            r = await dunning.run_due()
            out.append(f"dunning={r.get('processed', r.get('count', 0))}")
        except Exception:
            pass
        try:
            from app.marketing import lifecycle_nurture

            r = await lifecycle_nurture.run_due()
            out.append(f"nurture={r.get('processed', r.get('count', 0))}")
        except Exception:
            pass
        return {"ok": True, "detail": ", ".join(out) or "sweep done"}
    if action == "optimizer":
        from app.agents import growth_optimizer

        res = await growth_optimizer.optimize()
        return {
            "ok": bool(res.get("enabled", True)),
            "detail": f"stage={res.get('weakest', {}).get('stage', '?')}",
        }
    if action == "campaign_optimize":
        from app.agents import campaign_optimizer

        res = await campaign_optimizer.optimize(force=True)
        return {
            "ok": bool(res.get("ok", True)),
            "detail": f"proposals={res.get('proposals_count', 0)} run={res.get('run_id', '?')}",
        }
    if action == "reflection":
        return await _reflect()
    if action == "study_skills":
        return await _study_skills(task)
    if action == "skill_sweep":
        return await _study_skills("skill sweep all skills one by one")
    if action == "code_scan":
        from app.agents import code_upgrader

        res = await code_upgrader.run_if_enabled()
        if not res.get("enabled", True):
            return {"ok": True, "detail": "CODE_UPGRADER off (skip)"}
        return {
            "ok": bool(res.get("ok")),
            "detail": f"signals={res.get('signals', 0)} proposed={res.get('proposed', 0)}",
        }
    if action == "voice_eval":
        return await _voice_eval()
    if action == "voice_learn":
        return await _voice_learn()
    if action == "rescore_pipeline":
        from app.platform import pipeline_ops

        res = await pipeline_ops.run_daily()
        _rc = (res.get("rescore") or {}) if isinstance(res, dict) else {}
        _ht = (res.get("hot") or {}) if isinstance(res, dict) else {}
        return {
            "ok": bool(res.get("ok", True)),
            "detail": f"rescored={_rc.get('updated', 0)} hot={_ht.get('hot_count', 0)}",
        }
    if action == "cadence_sweep":
        from app.marketing import cadence

        res = await cadence.run_due()
        if not res.get("ok"):
            return {"ok": True, "detail": f"cadence: {res.get('reason', 'skip')}"}
        return {
            "ok": True,
            "detail": f"cadence advanced={res.get('advanced', res.get('processed', res.get('count', 0)))}",
        }
    if action == "dialer_sprint_prep":
        from app.agents import sprint_actions

        res = await sprint_actions.dialer_sprint_prep(limit=3)
        return {
            "ok": bool(res.get("ok")),
            "detail": f"dialer_prep={res.get('prepped', 0)} (untapped phones)",
        }
    if action == "hot_wa_draft":
        from app.agents import sprint_actions

        res = await sprint_actions.hot_wa_draft(limit=5)
        return {
            "ok": bool(res.get("ok")),
            "detail": f"wa_drafts={res.get('drafted', 0)} skipped={res.get('skipped', 0)}",
        }
    if action == "job_heal_sweep":
        from app.agents import sprint_actions

        res = await sprint_actions.job_heal_sweep(max_jobs=3)
        return {
            "ok": bool(res.get("ok")),
            "detail": f"overdue={len(res.get('overdue') or [])} started={len(res.get('started') or {})}",
        }
    return {"ok": False, "detail": f"unknown action '{action}'"}


async def _voice_eval() -> dict[str, Any]:
    """Voice agent persona eval smoke (dormant eval_suite wire). Gated VOICE_EVAL_AUTO.
    brain=None = LLM-free rule-based run → cheap regression catch (double/repeat/pushy)."""
    if os.environ.get("VOICE_EVAL_AUTO", "0").strip().lower() not in ("1", "true", "yes"):
        return {"ok": True, "detail": "VOICE_EVAL_AUTO off (skip)"}
    try:
        from app.voice_agent.eval_suite import PERSONAS, run_suite
        from app.voice_agent.natural_dialog import NaturalDialogManager

        try:
            from app.marketing.channel_experiments import _pick_niche_city

            niche, _ = _pick_niche_city()
        except Exception:
            niche = "solar"

        def _factory():
            return NaturalDialogManager(niche=niche, brain=None)

        report = await asyncio.wait_for(run_suite(_factory, personas=PERSONAS[:3]), timeout=120)
        total = report.passed + report.failed
        try:
            from app.platform import team

            team.log_event(
                "swara",
                "voice_eval",
                f"🎙️ persona smoke {report.passed}/{total} pass ({report.pass_rate:.0%}) niche={niche}",
                status="ok" if report.pass_rate >= 0.7 else "warn",
            )
        except Exception:
            pass
        return {
            "ok": report.pass_rate >= 0.5,
            "detail": f"voice eval {report.passed}/{total} ({report.pass_rate:.0%}) {niche}",
        }
    except Exception as e:
        return {"ok": False, "detail": f"voice_eval: {str(e)[:100]}"}


def _load_voice_learn_state() -> dict[str, Any]:
    try:
        if os.path.exists(_VOICE_LEARN_STATE):
            with open(_VOICE_LEARN_STATE, encoding="utf-8") as f:
                return json.load(f) or {}
    except Exception:
        pass
    return {}


def _save_voice_learn_state(st: dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(_VOICE_LEARN_STATE) or ".", exist_ok=True)
        with open(_VOICE_LEARN_STATE, "w", encoding="utf-8") as f:
            json.dump(st, f, ensure_ascii=False, default=str)
    except Exception:
        pass


async def _voice_learn() -> dict[str, Any]:
    """REAL recent call transcripts (data/call_transcripts) ko analyze karke EK voice
    lesson nikaalo jo `telecaller_brain` khud consume karta hai (skill_library
    lessons_snippet `voice_{niche}` / `voice_general`) — yeh loop ka voice-agent
    COMPOUNDING step: real call → weakness → lesson → agli live call behtar.

    Reuse-only (rebuild nahi): live_eval.eval_recent_calls (deterministic scorer,
    off-loop thread) + 1 bounded free-LLM lesson. Side-effect KOI nahi (sirf lesson
    record, draft). Never-raise. Dedupe: same weakest call dobara learn nahi hota
    (lesson-spam guard). No calls yet = graceful skip."""
    try:
        from app.agents import live_eval

        rep = await asyncio.wait_for(asyncio.to_thread(live_eval.eval_recent_calls, 8), timeout=60)
    except Exception as e:
        return {"ok": False, "detail": f"voice_learn eval: {str(e)[:90]}"}

    n = int(rep.get("n") or 0)
    if n == 0:
        return {"ok": True, "detail": "no recent calls (skip)"}
    mean = rep.get("mean_score")
    per = rep.get("per_call") or []
    # weakest call jisme QA findings hain ya score < 0.7
    weak = sorted(
        [
            c
            for c in per
            if (c.get("qa_finding_count") or 0) > 0 or float(c.get("score") or 1.0) < 0.7
        ],
        key=lambda c: float(c.get("score") or 1.0),
    )
    if not weak:
        try:
            from app.platform import skill_library

            skill_library.record_use(
                "voice_learn", False, f"mean={mean} n={n} clean", agent="arjun"
            )
        except Exception:
            pass
        return {"ok": True, "detail": f"voice clean: mean={mean} n={n} (no lesson)"}

    target = weak[0]
    call_id = str(target.get("call_id") or "")
    vst = _load_voice_learn_state()
    if call_id and vst.get("last_call_id") == call_id:
        return {"ok": True, "detail": f"voice_learn: already learned {call_id[:10]}"}

    niche = str(target.get("niche") or "general")
    findings = target.get("qa_findings") or []
    lesson = ""
    if _llm_healthy():
        try:
            from app.voice_agent import free_ai

            digest = (
                f"niche={niche} call_score={target.get('score')} qa_findings={str(findings)[:600]}"
            )
            text, _ = await asyncio.wait_for(
                free_ai.chat(
                    "Tu Swara (AI voice agent) ka QA coach hai. In real call-findings se EK concrete "
                    "Hinglish lesson de jo agli live call me Swara turant apply kar sake (kya galat hua "
                    "+ EXACT kya behtar bolna). Max 2 sentences, sirf lesson.",
                    [{"role": "user", "content": digest}],
                    max_tokens=120,
                    temperature=0.3,
                ),
                timeout=45,
            )
            lesson = (text or "").strip()
        except Exception:
            pass
    if not lesson:
        lesson = (
            f"Call score {target.get('score')} ({niche}) weak — findings: {str(findings)[:160]}. "
            "Inhe agli call me sudhaar (ACP: short, ek sawaal, KB-grounded)."
        )

    topic = f"voice_{niche}"
    try:
        from app.platform import skill_library

        skill_library.record_lesson(topic, lesson, source="voice_learn", agent="meera")
        skill_library.record_use(
            "voice_learn", True, f"weak {call_id[:10]} score={target.get('score')}", agent="arjun"
        )
    except Exception:
        pass
    _save_voice_learn_state({"last_call_id": call_id, "topic": topic, "at": _now().isoformat()})
    try:
        from app.platform import team

        team.log_event(
            "meera",
            "voice_learn",
            f"🎙️ {niche} weak-call lesson (score {target.get('score')}): {lesson[:80]}",
            status="warn",
        )
    except Exception:
        pass
    return {"ok": True, "detail": f"voice lesson [{topic}]: {lesson[:90]}"}


async def _study_skills(task: str) -> dict[str, Any]:
    """Skill pack se relevant (ya least-studied) skill padho → EK lesson skill_library me.
    Yahi 'LLM seekhta rahe' loop hai: skills → lessons → future prompts condition karte."""
    try:
        from app.platform import skill_pack
    except Exception as e:
        return {"ok": False, "detail": f"skill_pack import: {e}"}
    if not skill_pack.enabled():
        return {"ok": True, "detail": "SKILL_PACK off (skip)"}

    sweep_progress: dict[str, Any] = {}
    name = ""
    if _is_skill_sweep_task(task):
        all_sk = skill_pack.list_skills()
        if not all_sk:
            return {"ok": False, "detail": "no skills found"}
        name, sweep_progress = _next_skill_sweep_name(all_sk)
    else:
        hits = skill_pack.find(task or "marketing leads growth", k=1)
        name = hits[0]["name"] if hits else ""
        if not name:
            all_sk = skill_pack.list_skills()
            if not all_sk:
                return {"ok": False, "detail": "no skills found"}
            name, sweep_progress = _next_skill_sweep_name(all_sk)
    s = skill_pack.load(name)
    if not s:
        return {"ok": False, "detail": f"skill '{name}' load fail"}

    lesson = ""
    try:
        from app.voice_agent import free_ai

        text, _ = await asyncio.wait_for(
            free_ai.chat(
                "Tu ek growth-team coach hai. Diye gaye internal playbook (skill) se EK concrete, "
                "actionable Hinglish lesson nikaal jo AI-staff aaj apply kar sakein. Max 2 sentences, sirf lesson.",
                [{"role": "user", "content": f"Skill '{s['name']}':\n{s['text'][:3500]}"}],
                max_tokens=120,
                temperature=0.4,
            ),
            timeout=45,
        )
        lesson = (text or "").strip()
    except Exception:
        pass
    if not lesson:
        lesson = f"Skill '{s['name']}' follow karo: {s['description'][:140]}"
    try:
        from app.platform import skill_library

        skill_library.record_lesson(f"skill:{s['name']}", lesson, source="study", agent="guru")
    except Exception:
        pass
    try:
        from app.platform import team

        team.log_event("guru", "skill_study", f"📚 {s['name']}: {lesson[:90]}")
    except Exception:
        pass
    prefix = ""
    if sweep_progress:
        prefix = f"skill-sweep {sweep_progress.get('position')}/{sweep_progress.get('total')} "
    return {"ok": True, "detail": f"{prefix}studied '{s['name']}': {lesson[:100]}"}


def _is_skill_sweep_task(task: str) -> bool:
    """Manual task says to cover all skills one-by-one, not just top keyword hit."""
    t = (task or "").lower()
    return (
        "all skills" in t
        or "every skill" in t
        or "one by one" in t
        or "round robin" in t
        or "skill sweep" in t
    )


def _next_skill_sweep_name(skills: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    """Stable round-robin over skill_pack.list_skills(); cursor persists in loop state."""
    names = sorted({str(s.get("name") or "").strip().lower() for s in skills if s.get("name")})
    if not names:
        return "", {}
    signature = hashlib.sha1(
        "|".join(names).encode("utf-8", errors="ignore"), usedforsecurity=False
    ).hexdigest()
    st = _load_state()
    sweep = st.get("skill_sweep") if isinstance(st.get("skill_sweep"), dict) else {}
    if sweep.get("signature") != signature:
        index = 0
        cycles = 0
    else:
        try:
            index = int(sweep.get("index", 0) or 0)
        except Exception:
            index = 0
        try:
            cycles = int(sweep.get("completed_cycles", 0) or 0)
        except Exception:
            cycles = 0
    index = max(0, index) % len(names)
    name = names[index]
    next_index = (index + 1) % len(names)
    if next_index == 0:
        cycles += 1
    st["skill_sweep"] = {
        "signature": signature,
        "index": next_index,
        "total": len(names),
        "last": name,
        "completed_cycles": cycles,
        "last_at": _now().isoformat(),
    }
    _save_state(st)
    return name, {"position": index + 1, "total": len(names), "completed_cycles": cycles}


async def _reflect() -> dict[str, Any]:
    """Recent runs pe free-LLM reflection → lesson skill_library me. Fallback static."""
    runs = _read_jsonl(_RUNS)[-12:]
    if not runs:
        return {"ok": True, "detail": "no runs yet"}
    lesson = ""
    try:
        from app.voice_agent import free_ai

        digest = "\n".join(
            f"- {r.get('action')}: ok={r.get('ok')} {str(r.get('detail', ''))[:80]}" for r in runs
        )
        try:
            # SKILL_PACK on ho to relevant project-skill ka excerpt context me (LLM seekhe)
            from app.platform import skill_pack

            if skill_pack.enabled():
                fails = [str(r.get("action")) for r in runs if not r.get("ok")]
                sn = skill_pack.snippet_for(" ".join(fails) or "growth automation", max_chars=700)
                if sn:
                    digest += f"\n\nRelevant internal playbook:\n{sn}"
        except Exception:
            pass
        # Reflexion memory — loop ke apne purane self_improve lessons recall karo taaki
        # gyaan compound ho (har N-run reflection amnesiac na rahe). lessons_snippet(
        # "self_improve") ab tak write-only tha (sirf voice topics consume hote the) —
        # yahan loop apne lessons ko khud consume karta hai.
        try:
            from app.platform import skill_library as _sl

            prior = _sl.lessons_snippet("self_improve", k=3)
            if prior:
                digest += f"\n\nPehle ke apne lessons (inpe build karo, repeat mat karo):\n{prior}"
        except Exception:
            pass
        # SONA replay — best winning traces ka grounding (TRAJECTORY_LEARN gated).
        # record_trajectory ne wins likhe the; replay_hint() ab tak 0-caller dormant tha
        # (replay-into-loop deliberate follow-up). _execute ko risky maan ke nahi chhua —
        # reflection (safe meta-step) me wire kiya: top-reward actions ke winning traces
        # se lesson ground hota hai. Flag OFF = zero behaviour change.
        try:
            from app.agents import trajectory as _traj

            if _traj.enabled():
                _seen: set[str] = set()
                _hints: list[str] = []
                for r in sorted(
                    runs, key=lambda x: float(x.get("outcome_value") or 0.0), reverse=True
                ):
                    act = str(r.get("action") or "")
                    if not act or act in _seen:
                        continue
                    _seen.add(act)
                    h = _traj.replay_hint(act, max_chars=400)
                    if h:
                        _hints.append(h)
                    if len(_hints) >= 2:
                        break
                if _hints:
                    digest += "\n\nPast winning runs (inse seekho kya chala):\n" + "\n".join(_hints)
        except Exception:
            pass
        # Obsidian second brain: past improvement patterns
        _obs_ctx = ""
        try:
            from app.platform import obsidian_sync as _obs

            _obs_ctx = _obs.brain_context("self improve reflection agent", k=3)
        except Exception:
            pass
        if _obs_ctx:
            digest += f"\n\nObsidian brain (past self-improve context):\n{_obs_ctx}"
        text, _ = await asyncio.wait_for(
            free_ai.chat(
                "Tu ek growth-ops coach hai. Recent automation runs dekh ke EK concrete Hinglish lesson de "
                "(kya kaam kar raha, kya badalna chahiye). Sirf lesson, max 2 sentences.",
                [{"role": "user", "content": digest}],
                max_tokens=120,
                temperature=0.4,
            ),
            timeout=45,
        )
        lesson = (text or "").strip()
    except Exception:
        pass
    if not lesson:
        fails = [r.get("action") for r in runs if not r.get("ok")]
        lesson = (
            f"Actions failing zyada: {', '.join(sorted({str(f) for f in fails}))} — inke flags/creds check karo."
            if fails
            else "Sab actions theek chal rahe — explore naya channel via channel_experiments."
        )
    try:
        from app.platform import skill_library

        skill_library.record_lesson("self_improve", lesson, source="reflection", agent="meera")
    except Exception:
        pass
    # Hivemind: reflection lessons → KB skills namespace (cross-agent sharing)
    if (
        lesson
        and len(lesson) > 20
        and os.environ.get("KB_SKILL_LEARN", "").strip() in ("1", "true", "yes", "on")
    ):
        try:
            from app.voice_agent.knowledge_base import get_knowledge_base

            _kb = get_knowledge_base()
            await asyncio.wait_for(
                asyncio.to_thread(
                    lambda: _kb.add_documents(
                        [{"text": lesson, "source": "self_improve_reflect"}], namespace="skills"
                    )
                ),
                timeout=4.0,
            )
        except Exception:
            pass
    # Write reflection lesson to obsidian brain
    try:
        from datetime import datetime

        from app.platform import obsidian_sync as _obs

        _obs.append_note(
            "Sessions", datetime.utcnow().strftime("%Y-%m-%d"), lesson[:500], member="self_improve"
        )
    except Exception:
        pass
    return {"ok": True, "detail": f"lesson: {lesson[:120]}"}


def _acquire_revive_lock() -> bool:
    """Single-chain guard: Redis NX lock taaki concurrent revivers (watchdog hourly +
    self_improve_revive */20min) ek hi stale-window me DO chains na bana dein → queue
    flood (2501 self_improve_tick lesson). TTL ~gap*2: chain sach me mari ho to expire
    hoke agla revive reseed kar lega. Redis unavailable/error par fail-closed
    rakho: watchdog ko duplicate chain seed karne ki permission nahi milni chahiye
    jab distributed lock verify nahi ho sakta."""
    try:
        r = _redis_client()
        if r is None:
            return False
        ttl = max(300, gap_seconds() * 2)
        return bool(r.set("self_improve:revive_lock", str(int(time.time())), nx=True, ex=ttl))
    except Exception as e:
        logger.debug("[self-improve] revive-lock unavailable — fail-closed: %s", e)
        return False


def ensure_alive() -> dict[str, Any]:
    """Watchdog hook (light, sync): flag ON + heartbeat stale → Celery tick enqueue.
    Web process me kabhi inline run nahi (prod-down lesson). Single-chain locked —
    concurrent/repeat revivals chain multiply nahi karte.

    Cap-aware (2026-07-28 prod OOM correlation): after ``daily_cap``/``budget_cap``
    the owner chain deliberately requeues with a ~3600s countdown. Heartbeat is
    fresh at the skip, then goes quiet for up to an hour — the old
    ``max(900, gap*4)`` stale window treated that intentional sleep as death and
    seeded a parallel chain every ~15 minutes. Those revives mostly hit
    ``tick_slot`` (owner still holds ``next_allowed``) or re-hit the cap, but
    every receive still costs worker RSS and correlated with cgroup OOM. Do not
    revive while the same calendar day is still cap-paused, or while Redis says
    a future tick is already scheduled.
    """
    if not enabled():
        return {"enabled": False}
    try:
        st = _load_state()
        status = str(st.get("status") or "")
        day = _now().strftime("%Y-%m-%d")
        if status in ("daily_cap", "budget_cap") and str(st.get("day") or "") == day:
            return {"enabled": True, "alive": True, "paused": status}

        r = _redis_client()
        if r is not None:
            try:
                next_allowed = float(_redis_value(r.get(_TICK_NEXT_ALLOWED_KEY)) or 0)
                if next_allowed and time.time() < (next_allowed - _TICK_ETA_SKEW_S):
                    return {"enabled": True, "alive": True, "scheduled": True}
            except Exception:
                pass

        last = float(st.get("last_tick", 0) or 0)
        stale = (time.time() - last) > max(900, gap_seconds() * 4)
        if not stale:
            return {"enabled": True, "alive": True}
        # stale → revive, PAR sirf agar koi dusra reviver abhi-abhi na chala ho (NX lock)
        if not _acquire_revive_lock():
            return {"enabled": True, "alive": False, "revive_skipped": "lock"}
        from app.tasks.staff_jobs import self_improve_tick

        self_improve_tick.delay()
        logger.info("[self-improve] stale heartbeat — tick re-enqueued (lock acquired)")
        return {"enabled": True, "alive": False, "revived": True}
    except Exception as e:
        return {"enabled": True, "error": str(e)[:120]}


def status() -> dict[str, Any]:
    """Loop ka live status + recent runs + skill summary (admin UI/API)."""
    st = _load_state()
    out: dict[str, Any] = {
        "enabled": enabled(),
        "gap_seconds": gap_seconds(),
        "max_per_day": max_per_day(),
        "state": {
            k: st.get(k) for k in ("day", "runs_today", "last_tick_at", "last_action", "status")
        },
        "queue_pending": 0,
        "queue_stale": 0,
        "queue_ttl_days": queue_ttl_days(),
        "recent_runs": _read_jsonl(_RUNS)[-10:][::-1],
    }
    try:
        out["queue_pending"] = 1 if _next_queued() else 0
        rows = _read_jsonl(_QUEUE)
        done = {r.get("id") for r in rows if r.get("status") == "done"}
        out["queue_pending"] = sum(
            1
            for r in rows
            if r.get("status") == "pending"
            and r.get("id") not in done
            and not _is_stale_queue_row(r)
        )
        out["queue_stale"] = sum(
            1
            for r in rows
            if r.get("status") == "pending" and r.get("id") not in done and _is_stale_queue_row(r)
        )
    except Exception:
        pass
    try:
        from app.platform import skill_library

        out["skills"] = skill_library.summary()
    except Exception:
        pass
    return out


# ================================================================ PHASE 7 + 6
# Deterministic Feedback Loops + Cost-Aware Bandit Optimization
# ================================================================

# Phase 7: Outcome weighting for deterministic feedback gates
OUTCOME_WEIGHTS = {
    "lead_quality": 0.40,  # hot-lead score (0-1)
    "revenue": 0.40,  # MRR impact ($)
    "cost": -0.20,  # penalize expensive ($/outcome)
}

DETERMINISTIC_GATES = {
    "budget": True,  # Skip if over daily budget
    "expensive_risky": True,  # Skip if cost>$5 AND success<60%
    "low_roi": True,  # Skip if neutral outcome AND cost>$3
}


def compute_outcome_value(outcome_dict: dict[str, Any]) -> float:
    """
    Phase 7: Combines multiple metrics into single value score (0-1).

    outcome_dict = {
        "lead_count": 18,
        "avg_lead_score": 0.64,
        "revenue_impact": 150,  # $ of deals expected
        "cost": 2.31,
        "success": True
    }

    Returns: 0-1 score (weighted blend of lead quality + revenue - cost).
    """
    try:
        lead_quality = float(outcome_dict.get("avg_lead_score", 0))  # 0-1
        lead_quality = max(0, min(1, lead_quality))

        revenue = float(outcome_dict.get("revenue_impact", 0))  # $ of deals
        revenue_score = revenue / 1000.0  # normalize to 0-1 (capped at $1000)
        revenue_score = max(0, min(1, revenue_score))

        cost = float(outcome_dict.get("cost", 0))  # $ spent
        cost_score = cost / 10.0  # normalize to 0-1 (capped at $10)
        cost_score = max(0, min(1, cost_score))

        # Weighted sum (cost is negative = penalizes expensive)
        score = (
            OUTCOME_WEIGHTS["lead_quality"] * lead_quality
            + OUTCOME_WEIGHTS["revenue"] * revenue_score
            + OUTCOME_WEIGHTS["cost"] * cost_score
        )

        return max(0, min(1, score))  # clamp to 0-1
    except Exception:
        return 0.5  # fail-open: neutral score


# ---------------------------------------------------------------- cost tracking + approval gates


_COST_FILE = os.path.join("data", "self_improve_cost.json")


class CostTracker:
    """Daily cost cap + per-task tracking (Phase 6 safety gates).

    Spent counter persists to `data/self_improve_cost.json` so worker restart
    mid-day does not reset the advisory budget. max_per_day() run-count remains
    the hard durable gate; this tracker is estimated $/task (not measured tokens).
    """

    def __init__(self, daily_cap: float = 50.0):
        self.daily_cap = daily_cap
        self.today_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.today_cost = 0.0
        self.tasks_today: list[dict[str, Any]] = []
        self._load()

    def can_afford(self, task_name: str, estimated_cost: float) -> bool:
        """Check if task fits under daily budget."""
        self._reset_if_new_day()
        return (self.today_cost + estimated_cost) <= self.daily_cap

    def record_cost(self, task_name: str, actual_cost: float) -> None:
        """Log cost for task."""
        self._reset_if_new_day()
        self.today_cost += actual_cost
        self.tasks_today.append(
            {
                "task": task_name,
                "cost": round(actual_cost, 2),
                "time": _now().isoformat(),
            }
        )
        self._persist()

    def get_daily_status(self) -> dict[str, Any]:
        """Return today's budget status."""
        self._reset_if_new_day()
        return {
            "date": self.today_date,
            "cap": self.daily_cap,
            "spent": round(self.today_cost, 2),
            "remaining": round(self.daily_cap - self.today_cost, 2),
            "pct_used": (
                round(100 * self.today_cost / self.daily_cap, 1) if self.daily_cap > 0 else 0
            ),
            "tasks": self.tasks_today,
            # Honesty: cost constants ($2.5/$0.5) are estimates, not measured tokens.
            # Counter is file-durable across worker restarts (same UTC day).
            # Hard durable guard remains max_per_day() run-count (file-state).
            "note": "estimated_durable_file",
        }

    def _reset_if_new_day(self) -> None:
        new_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if new_date != self.today_date:
            self.today_date = new_date
            self.today_cost = 0.0
            self.tasks_today = []
            self._persist()

    def _load(self) -> None:
        try:
            if os.path.exists(_COST_FILE):
                with open(_COST_FILE, encoding="utf-8") as f:
                    d = json.load(f) or {}
                if str(d.get("date") or "") == self.today_date:
                    self.today_cost = float(d.get("spent") or 0.0)
                    tasks = d.get("tasks") or []
                    self.tasks_today = list(tasks)[-50:] if isinstance(tasks, list) else []
        except Exception:
            pass

    def _persist(self) -> None:
        try:
            os.makedirs(os.path.dirname(_COST_FILE) or ".", exist_ok=True)
            with open(_COST_FILE, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "date": self.today_date,
                        "spent": round(self.today_cost, 2),
                        "tasks": self.tasks_today[-50:],
                    },
                    f,
                    ensure_ascii=False,
                )
        except Exception:
            pass


def should_skip_task(
    task_name: str, cost_remaining: float, last_outcome: dict[str, Any] | None = None
) -> tuple[bool, str]:
    """
    Phase 7: Deterministic gates that skip expensive low-ROI tasks.

    Rules:
    1. If cost_remaining < estimated_cost, skip (budget)
    2. If success_rate < 60% AND cost > $5, skip (expensive + risky)
    3. If last outcome was "neutral" (value_score<0.5) AND cost > $3, skip (no ROI)

    Returns: (skip: bool, reason: str)
    """
    try:
        from app.platform import skill_library

        task_stats = skill_library.stats().get(task_name, {})
        success_rate = task_stats.get("rate", 0.5)  # default neutral
        cost_avg = 2.5 if ACTIONS.get(task_name, (True, ""))[0] else 0.5

        # Gate 1: Budget (skip if exceeds remaining)
        if not DETERMINISTIC_GATES.get("budget", True):
            return False, ""
        if cost_avg > cost_remaining:
            return True, f"budget_exceeded (${cost_remaining:.2f} left, task costs ${cost_avg:.2f})"

        # Gate 2: High-cost + low-success (skip risky expensive)
        if not DETERMINISTIC_GATES.get("expensive_risky", True):
            return False, ""
        if success_rate < 0.6 and cost_avg > 5:
            return True, f"expensive_risky (success={success_rate:.0%}, cost=${cost_avg:.2f})"

        # Gate 3: Neutral outcome + expensive (skip low-ROI)
        if not DETERMINISTIC_GATES.get("low_roi", True):
            return False, ""
        if last_outcome:
            value_score = last_outcome.get("value_score", 0.5)
            if value_score < 0.5 and cost_avg > 3:
                return True, f"low_roi (outcome_value={value_score:.2f}, cost=${cost_avg:.2f})"

        return False, ""
    except Exception:
        return False, ""


class ApprovalQueue:
    """Human approval gates for high-risk self-improve actions (Phase 6).

    Cross-process by design: self-improve ticks run in the Celery worker
    container (RUN_IN_PROCESS_SCHEDULER=0 in prod) while the approve/reject
    API + Office HQ UI run in the app container — an in-memory list is
    invisible across that boundary (a task queued by the worker would never
    be visible to, or approvable from, the app process). `data/self_improve_
    approvals.jsonl` (bind-mounted, shared by both containers) is the single
    source of truth; state is folded to the latest record per task id, same
    reconciliation pattern already used by app/marketing/content_approval.py.
    """

    def __init__(self, approval_required: bool = False):
        self.approval_required = approval_required
        self._approval_file = os.path.join("data", "self_improve_approvals.jsonl")

    def _latest(self) -> dict[str, dict[str, Any]]:
        latest: dict[str, dict[str, Any]] = {}
        for rec in _read_jsonl(self._approval_file):
            tid = rec.get("id")
            if tid:
                latest[tid] = rec
        return latest

    def _log(self, action: str, detail: str, meta: dict[str, Any]) -> None:
        try:
            from app.platform.team import log_event

            log_event("system", action, detail, meta=meta)
        except Exception:
            pass

    def queue_task(self, task_name: str, reason: str, cost_estimate: float) -> str:
        """Queue task for approval (or consume an already-approved one).

        Returns a truthy value (an id) if the caller should execute the
        action NOW — either auto-approved, or a previously-approved request
        for this same action is being consumed — else "" if it's still
        waiting/newly queued. `is_approved()` used to be dead code (nothing
        ever re-ran an approved task); consuming here is what makes approval
        actually resume execution.
        """
        if not self.approval_required:
            return "auto"

        existing = [r for r in self._latest().values() if r.get("task") == task_name]
        for rec in existing:
            if rec.get("status") == "approved":
                self._append_decision(rec, "consumed")
                self._log(
                    "selfimprove_approval_consumed",
                    f"{task_name} approved earlier — running now",
                    {"id": rec.get("id"), "task": task_name},
                )
                return str(rec.get("id") or "auto")
            if rec.get("status") == "waiting":
                return ""  # already queued for this action — don't duplicate

        # Risk-scored auto-approve (gated RISK_AUTO_APPROVE): clearly low-risk + cheap
        # actions skip the human gate by policy; risky/ban-sensitive ones still queue.
        # Additive, never-raise, default OFF = unchanged behaviour.
        try:
            from app.agents import risk_approve

            if risk_approve.enabled() and risk_approve.should_auto_approve(
                task_name, cost_estimate, reason
            ):
                return "auto"
        except Exception:
            pass

        rec = {
            "id": uuid.uuid4().hex[:12],
            "task": task_name,
            "reason": reason[:300],
            "cost": round(cost_estimate, 2),
            "timestamp": _now().isoformat(),
            "status": "waiting",
        }
        _append(self._approval_file, rec)
        self._log(
            "selfimprove_approval_queued",
            f"{task_name} needs approval — {reason[:160]}",
            {"id": rec["id"], "task": task_name, "cost": rec["cost"]},
        )
        return ""

    def _append_decision(self, rec: dict[str, Any], status: str, **extra: Any) -> None:
        _append(self._approval_file, {**rec, "status": status, **extra})

    def get_pending(self) -> list[dict[str, Any]]:
        """Return list of pending approvals."""
        if not self.approval_required:
            return []
        return [r for r in self._latest().values() if r.get("status") == "waiting"]

    def approve(self, task_id: str) -> bool:
        """Admin approves a pending task. Return True if found."""
        rec = self._latest().get(task_id)
        if not rec or rec.get("status") != "waiting":
            return False
        self._append_decision(rec, "approved", approved_at=_now().isoformat())
        return True

    def reject(self, task_id: str, reason: str = "") -> bool:
        """Admin rejects a pending task. Return True if found."""
        rec = self._latest().get(task_id)
        if not rec or rec.get("status") != "waiting":
            return False
        self._append_decision(
            rec, "rejected", rejection_reason=reason[:200], rejected_at=_now().isoformat()
        )
        return True

    def is_approved(self, task_id: str) -> bool:
        """Check if a specific task is approved."""
        rec = self._latest().get(task_id)
        return bool(rec and rec.get("status") == "approved")

    @property
    def approved(self) -> list[dict[str, Any]]:
        return [r for r in self._latest().values() if r.get("status") in ("approved", "consumed")]


# Global instances (persist across run_once calls)
_cost_tracker: CostTracker | None = None
_approval_queue: ApprovalQueue | None = None


def _get_cost_tracker() -> CostTracker:
    global _cost_tracker
    if _cost_tracker is None:
        try:
            cap = float(os.environ.get("SELFIMPROVE_COST_CAP", "50.0"))
        except Exception:
            cap = 50.0
        _cost_tracker = CostTracker(daily_cap=cap)
    return _cost_tracker


def _get_approval_queue() -> ApprovalQueue:
    global _approval_queue
    if _approval_queue is None:
        approval_mode = os.environ.get("SELF_IMPROVE_APPROVAL", "0").strip().lower() in (
            "1",
            "true",
            "yes",
        )
        _approval_queue = ApprovalQueue(approval_required=approval_mode)
    return _approval_queue


# ================================================================ MAIN LOOP (Phase 7 integrated)
# ================================================================


async def run_once() -> dict[str, Any]:
    """
    EK iteration: pick → deterministic-gates → execute → learn.
    Loop continuation Celery requeue se (tasks/staff_jobs.self_improve_tick).
    Kabhi raise nahi.

    Phase 7 additions:
    - Deterministic gates (budget, expensive_risky, low_roi)
    - Outcome value computation (lead_quality + revenue - cost)
    - Cost-aware task picking
    """
    if not enabled():
        return {"enabled": False}

    ct = _get_cost_tracker()
    aq = _get_approval_queue()

    st = _load_state()
    day = _now().strftime("%Y-%m-%d")
    runs_today = int(st.get("runs_today", 0) or 0) if st.get("day") == day else 0
    if runs_today >= max_per_day():
        _heartbeat({"status": "daily_cap"})
        return {"enabled": True, "skipped": "daily_cap", "runs_today": runs_today}

    picked = await _pick_next()
    action = picked.get("action") or "channel_experiments"
    if action not in ACTIONS:
        action = "channel_experiments"

    # Estimate cost
    estimated_cost = 2.5 if ACTIONS.get(action, (False, ""))[0] else 0.5

    # ========== PHASE 7: DETERMINISTIC GATES ==========
    cost_remaining = ct.daily_cap - ct.today_cost
    last_outcome = None
    try:
        from app.platform import skill_library

        task_stats = skill_library.stats().get(action, {})
        # Infer last outcome if possible (for low_roi gate)
        runs = _read_jsonl(_RUNS)
        last_run = next((r for r in reversed(runs) if r.get("action") == action), None)
        if last_run:
            last_outcome = {
                "value_score": last_run.get("outcome_value", 0.5),
                "cost": last_run.get("cost", estimated_cost),
            }
    except Exception:
        pass

    skip, skip_reason = should_skip_task(action, cost_remaining, last_outcome)
    if skip:
        _heartbeat({"status": "gate_skip"})
        logger.info(f"[self-improve] deterministic gate: {action} — {skip_reason}")
        return {
            "enabled": True,
            "skipped": "gate_skip",
            "gate_reason": skip_reason,
            "cost_status": ct.get_daily_status(),
        }

    # ========== PHASE 6: COST + APPROVAL GATES ==========
    if not ct.can_afford(action, estimated_cost):
        _heartbeat({"status": "budget_cap"})
        logger.info(
            f"[self-improve] budget cap: spent ${ct.today_cost:.2f}, need ${estimated_cost:.2f}"
        )
        return {
            "enabled": True,
            "skipped": "budget_cap",
            "cost_status": ct.get_daily_status(),
        }

    if aq.approval_required and ACTIONS.get(action, (False, ""))[0]:
        task_id = aq.queue_task(
            action,
            reason=f"{picked.get('task', '')[:100]} — LLM-heavy action",
            cost_estimate=estimated_cost,
        )
        if not task_id:
            _heartbeat({"status": "approval_pending"})
            logger.info(f"[self-improve] approval_pending: {action}")
            return {
                "enabled": True,
                "skipped": "approval_pending",
                "action": action,
                "pending_approvals": len(aq.get_pending()),
            }

    # ========== EXECUTE ==========
    t0 = time.monotonic()
    try:
        result = await asyncio.wait_for(
            _execute(action, picked.get("task", "")), timeout=_ITER_TIMEOUT_S
        )
    except asyncio.TimeoutError:
        result = {"ok": False, "detail": f"timeout {_ITER_TIMEOUT_S}s"}
    except Exception as e:
        result = {"ok": False, "detail": str(e)[:200]}
    ms = (time.monotonic() - t0) * 1000

    # Record cost
    ct.record_cost(action, estimated_cost)

    # ========== PHASE 7: COMPUTE OUTCOME VALUE ==========
    outcome_value = 0.5  # default neutral
    if result.get("ok"):
        # Try to extract outcome metrics from result detail
        outcome_dict = {
            "lead_count": result.get("lead_count", 0),
            "avg_lead_score": result.get("avg_lead_score", 0.5),
            "revenue_impact": result.get("revenue_impact", 0),
            "cost": estimated_cost,
            "success": result.get("ok", False),
        }
        outcome_value = compute_outcome_value(outcome_dict)

    # ===== D1: eval_gate reward signal (baseline-relative regression detect) =====
    # Deterministic outcome_value slow-drift miss karta (0.85->0.62 har baar 0.6 pass).
    # eval_gate median-baseline se regression pakadta. INERT unless EVAL_GATE=1 (tab
    # bhi sirf logging) — EVAL_GATE_HARD=1 pe 'reject' action ko SOFT de-prioritize
    # (outcome_value gira do → credit/skill_library kam, KOI destructive rollback nahi).
    # Best-effort, kabhi raise nahi.
    try:
        from app.agents import eval_gate

        if eval_gate.enabled():
            _verdict = eval_gate.score_and_gate(
                suite="self_improve",
                metric="outcome_value",
                current_score=float(outcome_value),
                agent="boss",
                artifact=str(action),
            )
            if _verdict.get("decision") == "reject" and eval_gate.hard_mode():
                outcome_value = min(float(outcome_value), 0.2)
                logger.info(
                    f"[self-improve] eval_gate REJECT {action} ratio={_verdict.get('ratio')}"
                    " — outcome de-prioritized (hard mode)"
                )
    except Exception as _eg_exc:
        logger.debug(f"[self-improve] eval_gate hook skip: {_eg_exc}")

    # Learn — har run skill_library me (with outcome value)
    try:
        from app.platform import skill_library

        skill_library.record_use(
            action, bool(result.get("ok")), result.get("detail", ""), ms, agent="boss"
        )
    except Exception:
        pass
    # Hivemind: HIGH-VALUE runs (outcome >= 0.7) → KB skills namespace (Activeloop pattern)
    if (
        result.get("ok")
        and outcome_value >= 0.7
        and os.environ.get("KB_SKILL_LEARN", "").strip() in ("1", "true", "yes", "on")
    ):
        try:
            from app.voice_agent.knowledge_base import get_knowledge_base

            _kb = get_knowledge_base()
            _skill_text = f"Action: {action}\nTask: {str(picked.get('task', ''))[:200]}\nResult: {str(result.get('detail', ''))[:200]}"
            await asyncio.wait_for(
                asyncio.to_thread(
                    lambda: _kb.add_documents(
                        [{"text": _skill_text, "source": f"self_improve:{action}"}],
                        namespace="skills",
                    )
                ),
                timeout=4.0,
            )
        except Exception:
            pass

    if picked.get("queued_id"):
        _mark_done(picked["queued_id"], result.get("detail", ""))

    rec = {
        "id": uuid.uuid4().hex[:10],
        "task": picked.get("task", ""),
        "action": action,
        "source": picked.get("source", "auto"),
        "ok": bool(result.get("ok")),
        "detail": str(result.get("detail", ""))[:300],
        "ms": round(ms, 1),
        "cost": round(estimated_cost, 2),
        "outcome_value": round(outcome_value, 2),  # NEW: Phase 7
        "at": _now().isoformat(),
    }
    _append(_RUNS, rec)
    # RL reward spine (Phase 0) — mirror outcome_value into the unified reward log.
    try:
        from app.agents.rl import reward as _rl_reward

        _rl_reward.record_reward(
            "funnel",
            action,
            float(rec["outcome_value"]),
            ref=rec["id"],
            context={"source": rec["source"]},
        )
    except Exception:
        pass
    # Trajectory record (Ruflo SONA / training-export #13) — gated TRAJECTORY_LEARN,
    # never-raise, low-volume (~max_per_day lines). Feeds trajectory.best_trajectories
    # + export_dataset with REAL run data. Replay-into-loop NOW WIRED via _reflect()
    # (best winning traces ground the reflection lesson) — the safe path. Direct replay
    # into _execute action dispatch stays deferred (would touch sub-engine prompts = risky).
    try:
        from app.agents import trajectory

        if trajectory.enabled():
            trajectory.record_trajectory(
                action=action,
                steps=[{"task": str(picked.get("task", ""))[:200], "detail": rec["detail"]}],
                outcome="ok" if rec["ok"] else "fail",
                reward=float(rec["outcome_value"]),
                meta={"source": rec["source"], "ms": rec["ms"], "cost": rec["cost"]},
            )
    except Exception:
        pass
    _heartbeat({"runs_today": runs_today + 1, "last_action": action, "status": "ok"})
    # Obsidian — append self-improve run to Sessions/ (INERT if OBSIDIAN_SYNC unset).
    try:
        import datetime as _dt

        from app.platform import obsidian_sync as _obs

        _obs.append_note(
            "Sessions",
            _dt.datetime.utcnow().strftime("%Y-%m-%d"),
            f"self_improve [{action}] {'OK' if rec['ok'] else 'FAIL'} — {rec['detail'][:80]}",
            member="self_improve",
            tags=["self-improve"],
        )
    except Exception:
        pass

    # periodic reflection (auto-learn never stops)
    total = runs_today + 1
    if action != "reflection" and total % _REFLECT_EVERY == 0:
        try:
            await asyncio.wait_for(_reflect(), timeout=60)
        except Exception:
            pass

    try:
        from app.platform import team

        gate_info = f" [GATE: {skip_reason}]" if skip else ""
        team.log_event(
            "manager",
            "self_improve",
            f"{action}: {'OK' if rec['ok'] else 'FAIL'} — ${rec['cost']:.2f} (value={rec['outcome_value']:.2f}) — {rec['detail'][:70]}{gate_info}",
        )
        team.team_pulse(max_members=2)  # har tick 2 under-active staff ko bhi heartbeat
    except Exception:
        pass

    return {"enabled": True, **rec, "cost_status": ct.get_daily_status()}


def cost_status() -> dict[str, Any]:
    """Return current daily cost tracking status."""
    ct = _get_cost_tracker()
    return ct.get_daily_status()


def approval_status() -> dict[str, Any]:
    """Return current approval queue status."""
    aq = _get_approval_queue()
    return {
        "approval_required": aq.approval_required,
        "pending_count": len(aq.get_pending()),
        "pending": aq.get_pending(),
        "approved_count": len(aq.approved),
    }


__all__ = [
    "enabled",
    "gap_seconds",
    "run_once",
    "ensure_alive",
    "status",
    "add_task",
    "ACTIONS",
    "cost_status",
    "approval_status",
    "CostTracker",
    "ApprovalQueue",
    "compute_outcome_value",
    "should_skip_task",
    "acquire_tick_slot",
    "release_tick_slot",
    "note_tick_requeue",
    "OUTCOME_WEIGHTS",
    "DETERMINISTIC_GATES",
]
