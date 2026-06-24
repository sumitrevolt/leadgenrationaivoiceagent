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
        return max(1, int(os.environ.get("SELF_IMPROVE_MAX_PER_DAY", "120")))
    except Exception:
        return 120


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
    "code_scan": (False, "observability signals se code-upgrade proposals (Vikram, gated)"),
    "voice_eval": (False, "voice agent persona eval smoke (Swara/Arjun, gated VOICE_EVAL_AUTO)"),
    "rescore_pipeline": (False, "DB leads rescore + hot-lead surface (Neha/Rohan, revenue)"),
    "cadence_sweep": (False, "omnichannel cadence due-steps advance (gated CADENCE_ENGINE)"),
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
    ],
    "inbound": ["seo_pages", "channel_experiments", "social_drafts"],
    "conversion": [
        "sales_deepdive",
        "revenue_sweep",
        "content_pack",
        "voice_eval",
        "rescore_pipeline",
    ],
    "retention": ["revenue_sweep", "content_pack"],
    "scale": ["optimizer", "campaign_optimize", "channel_experiments", "harvest_leads", "study_skills"],
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

        res = await lead_harvester.run_harvest()
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


async def _study_skills(task: str) -> dict[str, Any]:
    """Skill pack se relevant (ya least-studied) skill padho → EK lesson skill_library me.
    Yahi 'LLM seekhta rahe' loop hai: skills → lessons → future prompts condition karte."""
    try:
        from app.platform import skill_pack
    except Exception as e:
        return {"ok": False, "detail": f"skill_pack import: {e}"}
    if not skill_pack.enabled():
        return {"ok": True, "detail": "SKILL_PACK off (skip)"}

    hits = skill_pack.find(task or "marketing leads growth", k=1)
    name = hits[0]["name"] if hits else ""
    if not name:
        all_sk = skill_pack.list_skills()
        if not all_sk:
            return {"ok": False, "detail": "no skills found"}
        import random as _r

        name = _r.choice(all_sk)["name"]
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
    return {"ok": True, "detail": f"studied '{s['name']}': {lesson[:100]}"}


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


def _acquire_revive_lock() -> bool:
    """Single-chain guard: Redis NX lock taaki concurrent revivers (watchdog hourly +
    self_improve_revive */20min) ek hi stale-window me DO chains na bana dein → queue
    flood (2501 self_improve_tick lesson). TTL ~gap*2: chain sach me mari ho to expire
    hoke agla revive reseed kar lega. Fail-open — Redis na ho to True (purana behaviour)."""
    try:
        import redis as _redis

        from app.config import settings

        r = _redis.Redis.from_url(str(settings.redis_url), socket_timeout=2)
        ttl = max(300, gap_seconds() * 2)
        return bool(r.set("self_improve:revive_lock", str(int(time.time())), nx=True, ex=ttl))
    except Exception:
        return True  # fail-open: Redis down → pehle jaisa behave karo


def ensure_alive() -> dict[str, Any]:
    """Watchdog hook (light, sync): flag ON + heartbeat stale → Celery tick enqueue.
    Web process me kabhi inline run nahi (prod-down lesson). Single-chain locked —
    concurrent/repeat revivals chain multiply nahi karte."""
    if not enabled():
        return {"enabled": False}
    try:
        st = _load_state()
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
        "recent_runs": _read_jsonl(_RUNS)[-10:][::-1],
    }
    try:
        out["queue_pending"] = 1 if _next_queued() else 0
        rows = _read_jsonl(_QUEUE)
        done = {r.get("id") for r in rows if r.get("status") == "done"}
        out["queue_pending"] = sum(
            1 for r in rows if r.get("status") == "pending" and r.get("id") not in done
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


class CostTracker:
    """Daily cost cap + per-task tracking (Phase 6 safety gates)."""

    def __init__(self, daily_cap: float = 50.0):
        self.daily_cap = daily_cap
        self.today_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.today_cost = 0.0
        self.tasks_today: list[dict[str, Any]] = []

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
        }

    def _reset_if_new_day(self) -> None:
        new_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if new_date != self.today_date:
            self.today_date = new_date
            self.today_cost = 0.0
            self.tasks_today = []


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
    """Human approval gates for high-risk self-improve actions (Phase 6)."""

    def __init__(self, approval_required: bool = False):
        self.approval_required = approval_required
        self.pending: list[dict[str, Any]] = []
        self.approved: list[dict[str, Any]] = []
        self._approval_file = os.path.join("data", "self_improve_approvals.jsonl")

    def queue_task(self, task_name: str, reason: str, cost_estimate: float) -> bool:
        """Queue task for approval. Return True if auto-approved, False if waiting."""
        if not self.approval_required:
            return True

        # Risk-scored auto-approve (gated RISK_AUTO_APPROVE): clearly low-risk + cheap
        # actions skip the human gate by policy; risky/ban-sensitive ones still queue.
        # Additive, never-raise, default OFF = unchanged behaviour.
        try:
            from app.agents import risk_approve

            if risk_approve.enabled() and risk_approve.should_auto_approve(
                task_name, cost_estimate, reason
            ):
                return True
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
        self.pending.append(rec)
        _append(self._approval_file, rec)
        return False

    def get_pending(self) -> list[dict[str, Any]]:
        """Return list of pending approvals."""
        return self.pending.copy()

    def approve(self, task_id: str) -> bool:
        """Admin approves a pending task. Return True if found."""
        for task in self.pending:
            if task.get("id") == task_id:
                task["status"] = "approved"
                task["approved_at"] = _now().isoformat()
                self.approved.append(task)
                _append(self._approval_file, task)
                self.pending.remove(task)
                return True
        return False

    def reject(self, task_id: str, reason: str = "") -> bool:
        """Admin rejects a pending task. Return True if found."""
        for task in self.pending:
            if task.get("id") == task_id:
                task["status"] = "rejected"
                task["rejection_reason"] = reason[:200]
                task["rejected_at"] = _now().isoformat()
                _append(self._approval_file, task)
                self.pending.remove(task)
                return True
        return False

    def is_approved(self, task_id: str) -> bool:
        """Check if a specific task is approved."""
        return any(t.get("id") == task_id and t.get("status") == "approved" for t in self.approved)


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

    # Learn — har run skill_library me (with outcome value)
    try:
        from app.platform import skill_library

        skill_library.record_use(
            action, bool(result.get("ok")), result.get("detail", ""), ms, agent="boss"
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
        from app.platform import obsidian_sync as _obs
        import datetime as _dt
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
    "OUTCOME_WEIGHTS",
    "DETERMINISTIC_GATES",
]
