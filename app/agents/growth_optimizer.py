"""Growth Optimizer — multi-agent SELF-HEALING PROFIT loop (marketing-first).

growth_engine (15-min pulse) pipeline ki QUANTITY heal karta hai (blog/content/
prospect top-up). YEH optimizer us se ek level UPAR — roz pura REVENUE funnel
dekhta hai aur strategy-level self-heal karta:

  funnel snapshot (leads → outreach → replies → inbound → signups → MRR → retention)
   → weakest-stage detect (rule-based, deterministic)
   → DIRECT corrective actions (existing engines: scrape/SEO/experiments/nurture/dunning)
   → multi-agent STRATEGY pass (coordinator.coordinate_advanced: Reflexion+critic+memory)
   → naye free/legal channel ideas (free-LLM brainstorm → data/growth_ideas.jsonl)

Sab free-stack + ban-safe (drafts/own-site only; auto-send apne channel-gates pe).
GATED `GROWTH_OPTIMIZER=1` (default OFF = optimize() no-op). Voice secondary —
saare actions marketing-first. Store: data/growth_optimizer_runs.jsonl.
Import-safe, kabhi raise nahi.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_RUNS = os.path.join("data", "growth_optimizer_runs.jsonl")
_IDEAS = os.path.join("data", "growth_ideas.jsonl")

# Funnel-stage priority (pehla matching = weakest; supply se shuru — bina leads
# ke baaki sab bekaar).
STAGES = ["lead_supply", "outreach_quality", "inbound", "conversion", "retention", "scale"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _enabled() -> bool:
    return os.environ.get("GROWTH_OPTIMIZER", "0").strip().lower() in ("1", "true", "yes")


def _append(path: str, rec: dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


async def funnel_snapshot() -> dict[str, Any]:
    """Poora revenue funnel ek dict me (har source defensive)."""
    snap: dict[str, Any] = {"at": _now().isoformat()}
    try:
        from app.platform import growth_engine

        pulse = growth_engine.latest_pulse() or {}
        snap["prospects"] = pulse.get("prospects") or {}
        snap["inquiries"] = pulse.get("inquiries") or {}
        snap["emails"] = pulse.get("emails") or {}
        snap["best_niche"] = pulse.get("best_niche")
        snap["clients_active"] = int(pulse.get("marketing_clients_active", 0) or 0)
        snap["blog_articles"] = int(pulse.get("blog_articles", 0) or 0)
    except Exception:
        pass
    try:
        from app.marketing import channel_experiments

        snap["channels"] = channel_experiments.stats()
    except Exception:
        pass
    try:
        from app.billing import dunning

        d = dunning.stats()
        snap["dunning_open"] = int(d.get("open", 0) or 0)
    except Exception:
        snap["dunning_open"] = 0
    try:
        from app.marketing import lifecycle_nurture

        snap["nurture"] = lifecycle_nurture.stats()
    except Exception:
        pass
    try:
        from app.marketing import seo_pages

        snap["seo_pages"] = len(seo_pages.list_pages(limit=500))
    except Exception:
        snap["seo_pages"] = 0
    return snap


def weakest_stage(snap: dict[str, Any]) -> dict[str, Any]:
    """Rule-based weakest funnel stage (pure function — testable, deterministic)."""
    p = snap.get("prospects") or {}
    e = snap.get("emails") or {}
    inq = snap.get("inquiries") or {}
    ready = int(p.get("ready", 0) or 0)
    replied = int(p.get("replied", 0) or 0)
    emailed = int(e.get("emailed", 0) or 0)
    inquiries_total = int(inq.get("total", 0) or 0)
    nurture = snap.get("nurture") or {}
    if ready < 20:
        return {
            "stage": "lead_supply",
            "reason": f"sirf {ready} ready prospects — pipeline patli",
            "action": "all-niche scrape batch + city rotation expand",
        }
    if emailed >= 30 and replied / max(emailed, 1) < 0.02:
        return {
            "stage": "outreach_quality",
            "reason": f"{emailed} emails pe sirf {replied} replies (<2%)",
            "action": "naye channels/angles experiment (bandit explore badhao)",
        }
    if inquiries_total < 5 or int(snap.get("seo_pages", 0) or 0) < 10:
        return {
            "stage": "inbound",
            "reason": f"{inquiries_total} inquiries, {snap.get('seo_pages', 0)} SEO pages — organic inbound kamzor",
            "action": "SEO niche×city pages batch + community experiments",
        }
    if int(snap.get("clients_active", 0) or 0) == 0 or (
        int(nurture.get("finished", 0) or 0) > int(nurture.get("converted", 0) or 0) + 2
    ):
        return {
            "stage": "conversion",
            "reason": "signups convert nahi ho rahe (nurture finished > converted)",
            "action": "lifecycle nurture + sales pipeline push + proposals",
        }
    if int(snap.get("dunning_open", 0) or 0) > 0:
        return {
            "stage": "retention",
            "reason": f"{snap.get('dunning_open')} dunning cases open — MRR risk",
            "action": "dunning sweep + client health save-actions",
        }
    return {
        "stage": "scale",
        "reason": "koi bottleneck nahi — winners ko scale karo",
        "action": "best channel double-down + naye niches/cities",
    }


async def _direct_actions(stage: str) -> list[str]:
    """Stage-specific DIRECT corrective actions (LLM nahi — real engines). Har
    action apne try/except me; jo chala uska naam list me."""
    done: list[str] = []
    try:
        if stage == "lead_supply":
            from app.platform import niche_prospector

            res = await niche_prospector.run(batch=6, limit_per_query=4)
            done.append(f"scrape batch ({len(res.get('covered') or [])} niches)")
        elif stage == "outreach_quality":
            # Channel experiments (gated, may no-op) + always: SEO pages + social drafts
            try:
                from app.marketing import channel_experiments

                res = await channel_experiments.run_daily(3)
                done.append(f"channel experiments x{len(res.get('launched') or [])}")
            except Exception:
                pass
            try:
                from app.marketing import seo_pages

                res2 = await seo_pages.generate_batch(limit=3)
                done.append(f"seo pages +{res2.get('count', len(res2.get('pages') or []))}")
            except Exception:
                pass
            try:
                from app.marketing import social_channels
                from app.marketing.channel_experiments import _pick_niche_city

                niche, city = _pick_niche_city()
                res3 = await social_channels.draft_batch(niche=niche, city=city, limit=2)
                done.append(f"social drafts +{res3.get('count', 0)}")
            except Exception:
                pass
        elif stage == "inbound":
            from app.marketing import seo_pages

            res = await seo_pages.generate_batch(limit=8)
            done.append(
                f"seo pages +{res.get('count', len(res.get('pages') or res.get('generated') or []))}"
            )
            try:
                from app.marketing import channel_experiments

                res2 = await channel_experiments.run_daily(2)
                done.append(f"experiments x{len(res2.get('launched') or [])}")
            except Exception:
                pass
        elif stage == "conversion":
            from app.marketing import lifecycle_nurture, sales_pipeline

            await lifecycle_nurture.run_due()
            await sales_pipeline.run_pipeline()
            done.append("nurture + sales pipeline sweep")
        elif stage == "retention":
            from app.billing import dunning
            from app.platform import client_health

            await dunning.run_due()
            await client_health.run_check()
            done.append("dunning + health sweep")
        else:  # scale
            from app.marketing import channel_experiments

            res = await channel_experiments.run_daily(3)
            done.append(f"scale experiments x{len(res.get('launched') or [])}")
    except Exception as e:
        logger.debug(f"[optimizer] direct action skip: {e}")
    return done


async def suggest_new_ways(niche: str = "general") -> list[str]:
    """free-LLM brainstorm: naye FREE+LEGAL customer-approach ideas (drafts me
    convert karne layak). Fallback static list. Ideas log hote (Boss review)."""
    ideas: list[str] = []
    try:
        from app.voice_agent.free_ai import chat

        raw, _prov = await chat(
            (
                "Tu ek Indian local-business growth hacker hai. SIRF free aur legal "
                "tarike de (koi paid ads, koi scraping-ToS-violation, koi WhatsApp bulk). "
                'JSON list de: ["idea1", ...] — 5 ideas, har ek <15 words, Hinglish.'
            ),
            [
                {
                    "role": "user",
                    "content": f"Niche: {niche}. leadsgenai.in ke liye naye customer-approach channels?",
                }
            ],
            max_tokens=220,
        )
        txt = raw if isinstance(raw, str) else str(raw)
        start, end = txt.find("["), txt.rfind("]")
        if start >= 0 and end > start:
            parsed = json.loads(txt[start : end + 1])
            ideas = [str(x)[:120] for x in parsed if str(x).strip()][:5]
    except Exception as e:
        logger.debug(f"[optimizer] idea brainstorm fallback: {e}")
    if not ideas:
        ideas = [
            "Google Business Profile Q&A me niche-expert answers (free visibility)",
            "Local business WhatsApp groups me hafte ka free marketing tip",
            "Justdial/Sulekha pe apna FREE listing + audit-link",
            "YouTube Shorts script: '2-min me missed call ka nuksan' calculator demo",
            "Niche association/chamber newsletters me free audit offer",
        ]
    for idea in ideas:
        _append(_IDEAS, {"idea": idea, "niche": niche, "at": _now().isoformat()})
    return ideas


async def optimize() -> dict[str, Any]:
    """Daily self-healing profit loop. GATED GROWTH_OPTIMIZER=1 — off = no-op.

    snapshot → weakest stage → direct actions → multi-agent strategy pass
    (Reflexion+critic+memory) → new-channel ideas → persist + log."""
    if not _enabled():
        return {"enabled": False}
    try:
        snap = await funnel_snapshot()
        weak = weakest_stage(snap)
        actions = await _direct_actions(weak["stage"])

        # Multi-agent strategy pass (coordinator: planner+handoff+critic+memory).
        strategy: dict[str, Any] = {}
        try:
            from app.agents import coordinator

            goal = (
                f"Funnel ka weakest stage: {weak['stage']} ({weak['reason']}). "
                f"Best niche: {snap.get('best_niche') or 'unknown'}. "
                f"Marketing-first plan banao is stage ko fix karne ka (voice secondary), "
                f"free+legal channels only."
            )
            strategy = await coordinator.coordinate_advanced(goal, max_iterations=1, execute=False)
        except Exception as e:
            logger.debug(f"[optimizer] strategy pass skip: {e}")

        ideas = await suggest_new_ways(str(snap.get("best_niche") or "general"))

        # Self-improve queue: top idea → skill_library me lesson record karo taaki
        # self_improve loop isko utha ke execute kare (study/content/outreach actions).
        try:
            if ideas and os.environ.get("SELF_IMPROVE_LOOP", "").strip() in ("1", "true", "yes"):
                from app.platform import skill_library as _sl

                _sl.record_lesson(
                    topic=f"growth_optimizer:{weak['stage']}",
                    lesson=ideas[0],
                    source="growth_optimizer",
                    agent="boss",
                )
        except Exception:
            pass

        rec = {
            "id": uuid.uuid4().hex[:12],
            "stage": weak["stage"],
            "reason": weak["reason"],
            "direct_actions": actions,
            "ideas": ideas,
            "strategy_score": (strategy or {}).get(
                "final_score"
            ),  # coordinate_advanced returns final_score, not score
            "at": _now().isoformat(),
        }
        _append(_RUNS, rec)
        try:
            from app.platform import team

            # "boss" is not a STAFF key ("manager" is) -- was silently invisible in
            # team_status(). This IS genuinely manager-level work (whole-funnel
            # strategy, calls coordinator.coordinate_advanced), so the owner stays
            # Boss -- just the key needed fixing. Fixed 2026-07-01.
            team.log_event(
                "manager",
                "growth_optimizer",
                f"weakest={weak['stage']} | actions: {', '.join(actions) or 'none'} | {len(ideas)} new ideas",
                meta={"reason": weak["reason"]},
            )
        except Exception:
            pass
        return {
            "enabled": True,
            "weakest": weak,
            "direct_actions": actions,
            "ideas": ideas,
            "snapshot": snap,
        }
    except Exception as e:
        logger.warning(f"[optimizer] optimize failed: {e}")
        return {"enabled": True, "error": str(e)}


def recent_runs(limit: int = 20) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        if os.path.exists(_RUNS):
            with open(_RUNS, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            rows.append(json.loads(line))
                        except Exception:
                            pass
    except Exception:
        pass
    return rows[-limit:][::-1]
