"""Campaign Optimization Agent (Kiran) — enterprise flywheel learning loop.

Orchestrates existing engines (growth_optimizer, channel_experiments,
content_feedback, live_eval) into one optimization cycle. Produces PROPOSALS
only — never auto-deploys scripts globally without statistical + eval_gate gates.

GATED `CAMPAIGN_OPTIMIZER=1` (default OFF). Store: data/campaign_optimization/
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

_DIR = os.path.join("data", "campaign_optimization")
_RUNS = os.path.join(_DIR, "runs.jsonl")
_COUNTER = os.path.join(_DIR, "interaction_counter.json")
_PROPOSALS = os.path.join(_DIR, "proposals.jsonl")
_DECISIONS = os.path.join(_DIR, "proposal_decisions.jsonl")


def _call_transcripts() -> str:
    """Call transcripts dir — resolved per call, never frozen at import."""
    from app.platform.runtime_recording_paths import call_transcripts_dir

    return str(call_transcripts_dir())


_TYPE_SCRIPT_MAP: dict[str, tuple[str, str]] = {
    "email_variant": ("cold_email", "email"),
    "call_opening": ("voice_opening", "voice"),
    "objection_card": ("objection_card", "email"),
    "ab_test": ("cold_email", "email"),
}

INTERACTION_THRESHOLD = 100
MIN_ARM_INTERACTIONS = 100
MIN_RELATIVE_IMPROVEMENT = 0.15  # 15% relative meeting-rate lift


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _enabled() -> bool:
    return os.environ.get("CAMPAIGN_OPTIMIZER", "0").strip().lower() in ("1", "true", "yes")


def _append(path: str, rec: dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


def _read_jsonl(path: str, limit: int = 5000) -> list[dict[str, Any]]:
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
    return rows[-limit:]


def _load_counter() -> dict[str, Any]:
    try:
        if os.path.exists(_COUNTER):
            with open(_COUNTER, encoding="utf-8") as f:
                return json.load(f) or {}
    except Exception:
        pass
    return {"total": 0, "last_run_at": "", "last_run_total": 0}


def _save_counter(st: dict[str, Any]) -> None:
    try:
        os.makedirs(_DIR, exist_ok=True)
        with open(_COUNTER, "w", encoding="utf-8") as f:
            json.dump(st, f, ensure_ascii=False, default=str)
    except Exception:
        pass


def count_interactions() -> int:
    """Approximate interaction count from existing jsonl stores (read-only)."""
    total = 0
    paths = [
        os.path.join("data", "channel_outcomes.jsonl"),
        os.path.join("data", "reply_drafts.jsonl"),
        os.path.join("data", "cadence_runs.jsonl"),
        os.path.join("data", "content_feedback.jsonl"),
    ]
    for p in paths:
        total += len(_read_jsonl(p, 10000))
    try:
        tdir = str(_call_transcripts())
        if os.path.isdir(tdir):
            for fn in os.listdir(tdir):
                if fn.endswith(".jsonl"):
                    total += len(_read_jsonl(os.path.join(tdir, fn), 500))
    except Exception:
        pass
    return total


def should_run(*, force: bool = False) -> tuple[bool, str]:
    if force:
        return True, "forced"
    if not _enabled():
        return False, "CAMPAIGN_OPTIMIZER off"
    st = _load_counter()
    last_total = int(st.get("last_run_total", 0) or 0)
    current = count_interactions()
    delta = current - last_total
    if delta >= INTERACTION_THRESHOLD:
        return True, f"threshold met (+{delta} since last run)"
    # Weekly fallback: 7 days since last run
    last_at = str(st.get("last_run_at") or "")
    if last_at:
        try:
            prev = datetime.fromisoformat(last_at.replace("Z", "+00:00"))
            if (datetime.now(timezone.utc) - prev).days >= 7:
                return True, "weekly cycle"
        except Exception:
            pass
    return False, f"waiting ({delta}/{INTERACTION_THRESHOLD} new interactions)"


async def _gather_inputs() -> dict[str, Any]:
    """Read-only snapshot of all optimization inputs."""
    snap: dict[str, Any] = {"at": _now(), "interaction_count": count_interactions()}
    try:
        from app.agents import growth_optimizer

        funnel = await growth_optimizer.funnel_snapshot()
        snap["funnel"] = funnel
        snap["weakest"] = growth_optimizer.weakest_stage(funnel)
    except Exception as e:
        snap["funnel_error"] = str(e)[:120]
    try:
        from app.marketing import channel_experiments

        snap["channels"] = channel_experiments.stats()
        snap["channel_recent"] = channel_experiments.recent(20)
    except Exception:
        pass
    try:
        from app.marketing import content_feedback

        snap["themes"] = content_feedback.theme_stats()
        snap["best_themes"] = content_feedback.best_themes(5)
    except Exception:
        pass
    try:
        from app.agents import live_eval

        snap["voice_eval"] = live_eval.eval_recent_calls(
            10
        )  # sync fn — await here raised TypeError (swallowed), input always dropped
    except Exception:
        pass
    try:
        from app.platform import lead_scoring

        snap["hot_leads"] = await lead_scoring.top_hot_leads(10)
    except Exception:
        pass
    return snap


async def _generate_proposals(inputs: dict[str, Any]) -> list[dict[str, Any]]:
    """LLM proposals — drafts only, eval_gate checked before any promotion."""
    proposals: list[dict[str, Any]] = []
    weakest = (inputs.get("weakest") or {}).get("stage", "outreach_quality")
    themes = inputs.get("best_themes") or []
    theme_hint = ", ".join(str(t.get("theme", "")) for t in themes[:3] if t)
    sys_prompt = (
        "You are Kiran, Campaign Optimization Agent for LeadGen AI (Indian SMB marketing).\n"
        "GOAL: maximize booked meetings and qualified opportunities.\n"
        "OUTPUT: JSON array of 2-4 proposal objects ONLY. Each object keys:\n"
        "  type (email_variant|call_opening|objection_card|ab_test),\n"
        "  niche (or 'general'),\n"
        "  title (short),\n"
        "  body (actionable draft text, Hinglish OK),\n"
        "  rationale (1 line why).\n"
        "Never suggest auto-send or bulk blast. Proposals only."
    )
    user = (
        f"Weakest funnel stage: {weakest}\n"
        f"Best content themes: {theme_hint or 'unknown'}\n"
        f"Channel stats summary: {str(inputs.get('channels', {}))[:800]}\n"
        f"Voice eval mean: {(inputs.get('voice_eval') or {}).get('mean_score', 'n/a')}\n"
        "Generate improvement proposals."
    )
    try:
        from app.voice_agent import free_ai

        reply, _ = await free_ai.chat(
            sys_prompt,
            [{"role": "user", "content": user}],
            max_tokens=900,
            temperature=0.4,
        )
        raw = (reply or "").strip()
        start = raw.find("[")
        end = raw.rfind("]") + 1
        if start >= 0 and end > start:
            parsed = json.loads(raw[start:end])
            if isinstance(parsed, list):
                for p in parsed[:4]:
                    if isinstance(p, dict) and p.get("title"):
                        proposals.append(
                            {
                                "id": uuid.uuid4().hex[:12],
                                "status": "proposal",
                                "created_at": _now(),
                                **p,
                            }
                        )
    except Exception as e:
        logger.debug("[campaign_opt] LLM proposals skip: %s", e)
    if not proposals:
        proposals.append(
            {
                "id": uuid.uuid4().hex[:12],
                "type": "ab_test",
                "niche": "general",
                "title": f"Address weakest stage: {weakest}",
                "body": (inputs.get("weakest") or {}).get("action", "Run channel experiments"),
                "rationale": "Rule-based fallback when LLM unavailable",
                "status": "proposal",
                "created_at": _now(),
            }
        )
    return proposals


def check_promotion_gate(
    champion_rate: float,
    challenger_rate: float,
    champion_n: int,
    challenger_n: int,
) -> dict[str, Any]:
    """Statistical gate before global script promotion (plan safety rules)."""
    ok_n = champion_n >= MIN_ARM_INTERACTIONS and challenger_n >= MIN_ARM_INTERACTIONS
    if champion_rate <= 0:
        rel_improve = 1.0 if challenger_rate > 0 else 0.0
    else:
        rel_improve = (challenger_rate - champion_rate) / champion_rate
    promote = ok_n and rel_improve >= MIN_RELATIVE_IMPROVEMENT
    eval_ok = True
    try:
        from app.agents import eval_gate

        verdict = eval_gate.score_and_gate(
            "campaign_optimizer",
            "promotion",
            challenger_rate,
            agent="kiran",
        )
        eval_ok = verdict.get("decision") != "reject" or not eval_gate.hard_mode()
        if verdict.get("decision") == "reject" and eval_gate.hard_mode():
            promote = False
    except Exception:
        pass
    return {
        "promote": promote,
        "champion_n": champion_n,
        "challenger_n": challenger_n,
        "champion_rate": round(champion_rate, 4),
        "challenger_rate": round(challenger_rate, 4),
        "relative_improvement": round(rel_improve, 4),
        "eval_gate_pass": eval_ok,
        "min_interactions": MIN_ARM_INTERACTIONS,
        "min_relative_improvement": MIN_RELATIVE_IMPROVEMENT,
    }


async def optimize(*, force: bool = False) -> dict[str, Any]:
    """Main optimization cycle — orchestrates sub-engines, returns run summary."""
    run_id = uuid.uuid4().hex[:12]
    ok_run, reason = should_run(force=force)
    if not ok_run:
        return {"ok": True, "enabled": _enabled(), "skipped": reason, "run_id": run_id}

    inputs = await _gather_inputs()
    sub_results: dict[str, Any] = {}

    try:
        from app.agents import growth_optimizer

        sub_results["optimizer"] = await growth_optimizer.optimize()
    except Exception as e:
        sub_results["optimizer"] = {"error": str(e)[:120]}

    try:
        from app.marketing import channel_experiments

        sub_results["experiments"] = await channel_experiments.run_daily(2)
    except Exception as e:
        sub_results["experiments"] = {"error": str(e)[:120]}

    proposals = await _generate_proposals(inputs)
    for p in proposals:
        _append(_PROPOSALS, p)

    rec = {
        "run_id": run_id,
        "at": _now(),
        "reason": reason,
        "interaction_count": inputs.get("interaction_count"),
        "weakest_stage": (inputs.get("weakest") or {}).get("stage"),
        "proposals_count": len(proposals),
        "proposals": proposals,
        "sub_results": {k: _brief(v) for k, v in sub_results.items()},
    }
    _append(_RUNS, rec)

    st = _load_counter()
    st["total"] = int(inputs.get("interaction_count") or 0)
    st["last_run_at"] = _now()
    st["last_run_total"] = st["total"]
    _save_counter(st)

    try:
        from app.platform.team import log_event

        log_event(
            "kiran",
            "campaign_optimize",
            f"Run {run_id}: {len(proposals)} proposals · weakest="
            f"{(inputs.get('weakest') or {}).get('stage', '?')}",
            meta={"run_id": run_id, "proposals": len(proposals)},
            status="ok",
        )
    except Exception:
        pass

    try:
        from app.platform import skill_library

        for p in proposals[:2]:
            skill_library.record_lesson(
                f"campaign_{p.get('type', 'proposal')}",
                f"{p.get('title', '')}: {p.get('body', '')[:300]}",
                source="kiran",
                agent="kiran",
            )
    except Exception:
        pass

    try:
        from app.platform import campaign_variants

        promo = await campaign_variants.auto_promote_all()
        rec["auto_promote"] = promo
        for sid, pr in (promo.get("results") or {}).items():
            if pr.get("promoted"):
                log_event(
                    "kiran",
                    "variant_promoted",
                    f"{sid}: challenger promoted → {pr.get('new_champion', '?')}",
                    meta=pr,
                    status="ok",
                )
    except Exception:
        pass

    return {"ok": True, "enabled": True, "run_id": run_id, **rec}


def _brief(v: Any) -> Any:
    if isinstance(v, dict):
        return {k: v[k] for k in list(v.keys())[:8]}
    return v


def recent_runs(limit: int = 20) -> list[dict[str, Any]]:
    return list(reversed(_read_jsonl(_RUNS, limit)))[:limit]


def recent_proposals(limit: int = 30) -> list[dict[str, Any]]:
    return _proposals_with_status(limit)


def _proposal_status(proposal_id: str) -> str:
    for d in reversed(_read_jsonl(_DECISIONS, 5000)):
        if d.get("proposal_id") == proposal_id:
            return str(d.get("action") or "proposal")
    return "proposal"


def _proposals_with_status(limit: int = 30) -> list[dict[str, Any]]:
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    for p in reversed(_read_jsonl(_PROPOSALS, 5000)):
        pid = str(p.get("id") or "")
        if not pid or pid in seen:
            continue
        seen.add(pid)
        row = dict(p)
        row["status"] = _proposal_status(pid)
        rows.append(row)
        if len(rows) >= limit:
            break
    return rows


async def approve_proposal(proposal_id: str) -> dict[str, Any]:
    """Human approve → register challenger variant (never auto-deploy globally)."""
    prop = next(
        (p for p in reversed(_read_jsonl(_PROPOSALS, 5000)) if p.get("id") == proposal_id),
        None,
    )
    if not prop:
        return {"ok": False, "error": "proposal not found"}
    if _proposal_status(proposal_id) == "approve":
        return {"ok": True, "already": True, "proposal_id": proposal_id, "proposal": prop}

    ptype = str(prop.get("type") or "email_variant")
    script_id, channel = _TYPE_SCRIPT_MAP.get(ptype, ("cold_email", "email"))
    niche = str(prop.get("niche") or "general")
    content = f"{prop.get('title', '')}\n\n{prop.get('body', '')}".strip()

    from app.platform import campaign_variants

    existing = await campaign_variants.list_variants(script_id)
    if not any(v.get("status") == "champion" for v in existing):
        await campaign_variants.register_variant(
            script_id=script_id,
            variant_key="champion",
            content="Baseline outreach script (pre-Kiran champion)",
            niche=niche,
            channel=channel,
        )
    reg = await campaign_variants.register_variant(
        script_id=script_id,
        variant_key=f"ch_{proposal_id[:8]}",
        content=content[:8000],
        niche=niche,
        channel=channel,
    )
    _append(
        _DECISIONS,
        {
            "proposal_id": proposal_id,
            "action": "approve",
            "at": _now(),
            "script_id": script_id,
            "variant": reg,
        },
    )
    try:
        from app.platform.team import log_event

        log_event(
            "kiran",
            "proposal_approved",
            f"Approved {proposal_id[:8]} → {script_id} challenger",
            meta={"proposal_id": proposal_id, "variant_id": (reg or {}).get("id")},
            status="ok",
        )
    except Exception:
        pass
    return {
        "ok": True,
        "proposal_id": proposal_id,
        "script_id": script_id,
        "variant": reg,
        "proposal": prop,
    }


def status() -> dict[str, Any]:
    st = _load_counter()
    ok_run, reason = should_run()
    return {
        "enabled": _enabled(),
        "interaction_count": count_interactions(),
        "threshold": INTERACTION_THRESHOLD,
        "should_run": ok_run,
        "should_run_reason": reason,
        "last_run_at": st.get("last_run_at"),
        "last_run_total": st.get("last_run_total"),
        "promotion_gate": {
            "min_interactions_per_arm": MIN_ARM_INTERACTIONS,
            "min_relative_improvement": MIN_RELATIVE_IMPROVEMENT,
        },
    }


__all__ = [
    "optimize",
    "should_run",
    "count_interactions",
    "check_promotion_gate",
    "recent_runs",
    "recent_proposals",
    "approve_proposal",
    "status",
    "INTERACTION_THRESHOLD",
]
