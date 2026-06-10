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
import json
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_STATE = os.path.join("data", "self_improve_state.json")
_QUEUE = os.path.join("data", "self_improve_queue.jsonl")
_RUNS = os.path.join("data", "self_improve_runs.jsonl")

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
        return max(1, int(os.environ.get("SELF_IMPROVE_MAX_PER_DAY", "60")))
    except Exception:
        return 60


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


def _next_queued() -> dict[str, Any] | None:
    """Pehla pending queued task (done-markers ke against resolve)."""
    rows = _read_jsonl(_QUEUE)
    done = {r.get("id") for r in rows if r.get("status") == "done"}
    for r in rows:
        if r.get("status") == "pending" and r.get("id") not in done:
            return r
    return None


def _mark_done(task_id: str, result: str = "") -> None:
    _append(_QUEUE, {"id": task_id, "status": "done", "result": result[:200], "at": _now().isoformat()})


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
    "reflection": (True, "recent runs pe LLM reflection → lesson save"),
}

# funnel weakest-stage → preferred actions (deterministic bias)
_STAGE_ACTIONS = {
    "lead_supply": ["scrape_leads", "harvest_leads", "seo_pages", "channel_experiments"],
    "outreach_quality": ["sales_deepdive", "social_drafts", "reflection"],
    "inbound": ["seo_pages", "channel_experiments", "social_drafts"],
    "conversion": ["sales_deepdive", "content_pack", "revenue_sweep"],
    "retention": ["revenue_sweep", "content_pack", "reflection"],
    "scale": ["optimizer", "channel_experiments", "social_drafts"],
}


def _llm_healthy() -> bool:
    """Providers degraded ho to LLM-heavy actions skip (Groq TPD lesson)."""
    try:
        from app.platform import llm_metrics

        st = llm_metrics.stats(window=200) or {}
        provs = st.get("providers") or {}
        if not provs:
            return True
        ok_any = any((p.get("ok_rate") or p.get("ok", 0)) for p in provs.values() if isinstance(p, dict))
        return bool(ok_any)
    except Exception:
        return True  # fail-open: metrics na ho to normal


async def _pick_next() -> dict[str, Any]:
    """Agla task chuno: (1) manual queue, (2) weakest-stage bias + skill_library
    epsilon-greedy. LLM sirf task-text refine ke liye (fallback static)."""
    q = _next_queued()
    if q:
        return {"task": q["task"], "action": q.get("action") or "", "queued_id": q["id"], "source": "queue"}

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

        res = await lead_harvester.run_harvest()
        return {"ok": bool(res.get("ok")), "detail": f"+{res.get('new_leads', 0)} leads (dedup {res.get('deduped', 0)}, enrich {((res.get('enrich') or {}).get('found', 0))})"}
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
        return {"ok": bool(res.get("pages") or res.get("count")), "detail": f"{res.get('count', 0)} pages"}
    if action == "sales_deepdive":
        from app.agents import sales_team

        res = await sales_team.run_auto(2)
        return {"ok": bool(res.get("ok", True)), "detail": f"analyzed={res.get('analyzed', res.get('count', 0))}"}
    if action == "social_drafts":
        from app.marketing import social_channels
        from app.marketing.channel_experiments import _pick_niche_city

        niche, city = _pick_niche_city()
        res = await social_channels.draft_batch(niche=niche, city=city, channels=None, limit=3)
        return {"ok": bool(res.get("count")), "detail": f"{res.get('count', 0)} social drafts ({niche}/{city})"}
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
        return {"ok": bool(res.get("enabled", True)), "detail": f"stage={res.get('weakest', {}).get('stage', '?')}"}
    if action == "reflection":
        return await _reflect()
    return {"ok": False, "detail": f"unknown action '{action}'"}


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
            f"Actions failing zyada: {', '.join(sorted(set(str(f) for f in fails)))} — inke flags/creds check karo."
            if fails
            else "Sab actions theek chal rahe — explore naya channel via channel_experiments."
        )
    try:
        from app.platform import skill_library

        skill_library.record_lesson("self_improve", lesson, source="reflection", agent="meera")
    except Exception:
        pass
    return {"ok": True, "detail": f"lesson: {lesson[:120]}"}


# ---------------------------------------------------------------- main loop tick


async def run_once() -> dict[str, Any]:
    """EK iteration: pick → execute → learn. Loop continuation Celery requeue se
    (tasks/staff_jobs.self_improve_tick). Kabhi raise nahi."""
    if not enabled():
        return {"enabled": False}

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

    t0 = time.monotonic()
    try:
        result = await asyncio.wait_for(_execute(action, picked.get("task", "")), timeout=_ITER_TIMEOUT_S)
    except asyncio.TimeoutError:
        result = {"ok": False, "detail": f"timeout {_ITER_TIMEOUT_S}s"}
    except Exception as e:
        result = {"ok": False, "detail": str(e)[:200]}
    ms = (time.monotonic() - t0) * 1000

    # learn — har run skill_library me
    try:
        from app.platform import skill_library

        skill_library.record_use(action, bool(result.get("ok")), result.get("detail", ""), ms, agent="boss")
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
        "at": _now().isoformat(),
    }
    _append(_RUNS, rec)
    _heartbeat({"runs_today": runs_today + 1, "last_action": action, "status": "ok"})

    # periodic reflection (auto-learn never stops)
    total = runs_today + 1
    if action != "reflection" and total % _REFLECT_EVERY == 0:
        try:
            await asyncio.wait_for(_reflect(), timeout=60)
        except Exception:
            pass

    try:
        from app.platform import team

        team.log_event("manager", "self_improve", f"{action}: {'OK' if rec['ok'] else 'FAIL'} — {rec['detail'][:80]}")
        team.team_pulse(max_members=2)  # har tick 2 under-active staff ko bhi heartbeat
    except Exception:
        pass

    return {"enabled": True, **rec}


def ensure_alive() -> dict[str, Any]:
    """Watchdog hook (light, sync): flag ON + heartbeat stale → Celery tick enqueue.
    Web process me kabhi inline run nahi (prod-down lesson)."""
    if not enabled():
        return {"enabled": False}
    try:
        st = _load_state()
        last = float(st.get("last_tick", 0) or 0)
        stale = (time.time() - last) > max(900, gap_seconds() * 4)
        if not stale:
            return {"enabled": True, "alive": True}
        from app.tasks.staff_jobs import self_improve_tick

        self_improve_tick.delay()
        logger.info("[self-improve] stale heartbeat — tick re-enqueued")
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
        "state": {k: st.get(k) for k in ("day", "runs_today", "last_tick_at", "last_action", "status")},
        "queue_pending": 0,
        "recent_runs": _read_jsonl(_RUNS)[-10:][::-1],
    }
    try:
        out["queue_pending"] = 1 if _next_queued() else 0
        rows = _read_jsonl(_QUEUE)
        done = {r.get("id") for r in rows if r.get("status") == "done"}
        out["queue_pending"] = sum(1 for r in rows if r.get("status") == "pending" and r.get("id") not in done)
    except Exception:
        pass
    try:
        from app.platform import skill_library

        out["skills"] = skill_library.summary()
    except Exception:
        pass
    return out


__all__ = ["enabled", "gap_seconds", "run_once", "ensure_alive", "status", "add_task", "ACTIONS"]
