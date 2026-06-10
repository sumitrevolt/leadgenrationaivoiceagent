"""Process Library — deterministic business workflows (babysitter process-as-code).

Har process = ordered steps IN CODE. Step kinds:
  - task: {id, action, args?, gate?, max_retries?} — EXECUTORS registry se chalti
    (sab EXISTING engines reuse — rebuild nahi). Gate = pure code check.
  - breakpoint: {id, kind: "breakpoint", question} — enforced human approval
    (ban-risky cheez se pehle: outreach/publish).

Naya process add karne ka pattern: PROCESSES me entry + (zaroorat ho to)
EXECUTORS me action. Side-effect actions (send/call/post) YAHAN BHI nahi —
sirf gated/draft-only engines. Import-safe, kabhi raise nahi.
"""

from __future__ import annotations

from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


# ---------------------------------------------------------------- executors (sab reuse)


async def _exec_scrape(inputs: dict) -> dict:
    from app.platform import niche_prospector

    res = await niche_prospector.run(batch=int(inputs.get("batch", 3)), limit_per_query=4)
    n = 0
    try:
        n = int(res.get("found", res.get("count", 0)) or 0)
    except Exception:
        pass
    return {"ok": bool(res.get("ok", True)), "count": n, "detail": f"covered={res.get('covered', [])} found={n}"}


async def _exec_rescore(inputs: dict) -> dict:
    from app.platform import lead_scoring

    res = await lead_scoring.rescore_db()
    n = int(res.get("scored", res.get("count", 0)) or 0) if isinstance(res, dict) else 0
    return {"ok": True, "count": n, "detail": f"rescored={n}"}


async def _exec_sales_analysis(inputs: dict) -> dict:
    from app.agents import sales_team

    res = await sales_team.run_auto(int(inputs.get("limit", 2)))
    n = int(res.get("analyzed", res.get("count", 0)) or 0) if isinstance(res, dict) else 0
    return {"ok": True, "count": n, "detail": f"deep-dives={n}"}


async def _exec_content_pack(inputs: dict) -> dict:
    from app.marketing import niche_pack

    niche = str(inputs.get("niche") or "general")
    res = await niche_pack.build_pack(niche, business_name=inputs.get("business_name"), city=str(inputs.get("city", "")))
    posts = res.get("posts") or []
    return {"ok": bool(posts or res.get("ok", True)), "count": len(posts), "detail": f"pack {niche}: {len(posts)} posts"}


async def _exec_social_drafts(inputs: dict) -> dict:
    from app.marketing import social_channels

    res = await social_channels.draft_batch(
        niche=str(inputs.get("niche", "general")), city=str(inputs.get("city", "")),
        business_name=str(inputs.get("business_name", "")), limit=int(inputs.get("limit", 3)),
    )
    return {"ok": bool(res.get("ok")), "count": int(res.get("count", 0) or 0), "detail": f"{res.get('count', 0)} social drafts"}


async def _exec_cadence_run(inputs: dict) -> dict:
    from app.marketing import cadence

    res = await cadence.run_due()
    n = int(res.get("processed", res.get("count", 0)) or 0) if isinstance(res, dict) else 0
    return {"ok": True, "count": n, "detail": f"cadence touches={n} (gated CADENCE_ENGINE)"}


async def _exec_optimizer(inputs: dict) -> dict:
    from app.agents import growth_optimizer

    res = await growth_optimizer.optimize()
    return {"ok": True, "count": 1, "detail": f"weakest={((res or {}).get('weakest') or {}).get('stage', '?')}"}


async def _exec_revenue_sweep(inputs: dict) -> dict:
    parts = []
    try:
        from app.billing import dunning

        r = await dunning.run_due()
        parts.append(f"dunning={r.get('processed', 0)}")
    except Exception:
        pass
    try:
        from app.marketing import lifecycle_nurture

        r = await lifecycle_nurture.run_due()
        parts.append(f"nurture={r.get('processed', 0)}")
    except Exception:
        pass
    return {"ok": True, "count": 1, "detail": ", ".join(parts) or "sweep done"}


async def _exec_harvest(inputs: dict) -> dict:
    from app.platform import lead_harvester

    res = await lead_harvester.run_harvest(
        niche=str(inputs.get("niche", "")), city=str(inputs.get("city", "")), limit=int(inputs.get("limit", 10))
    )
    n = int(res.get("new_leads", 0) or 0)
    return {"ok": bool(res.get("ok")), "count": n, "detail": f"harvest +{n} (dedup {res.get('deduped', 0)})"}


EXECUTORS = {
    "scrape": _exec_scrape,
    "harvest": _exec_harvest,
    "rescore": _exec_rescore,
    "sales_analysis": _exec_sales_analysis,
    "content_pack": _exec_content_pack,
    "social_drafts": _exec_social_drafts,
    "cadence_run": _exec_cadence_run,
    "optimizer": _exec_optimizer,
    "revenue_sweep": _exec_revenue_sweep,
}


async def execute_step(step: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    """Step ka action EXECUTORS se chalao. Unknown action = fail (deterministic)."""
    fn = EXECUTORS.get(str(step.get("action", "")))
    if not fn:
        return {"ok": False, "detail": f"unknown action '{step.get('action')}'"}
    return await fn(inputs or {})


def check_gate(step: dict[str, Any], result: dict[str, Any]) -> tuple[bool, str]:
    """Deterministic CODE gate (babysitter: gates = logic, not opinion).
    Supported: {"gate": {"min_count": N}} ya default ok-check. Kabhi raise nahi."""
    try:
        if not result.get("ok"):
            return False, str(result.get("detail", "step not ok"))[:150]
        g = step.get("gate") or {}
        mc = g.get("min_count")
        if mc is not None and int(result.get("count", 0) or 0) < int(mc):
            return False, f"count {result.get('count', 0)} < min {mc}"
        return True, ""
    except Exception as e:
        return False, f"gate error: {e}"


# ---------------------------------------------------------------- process definitions


PROCESSES: dict[str, dict[str, Any]] = {
    # Lead campaign: scrape → score → deep-dive → HUMAN APPROVE → cadence
    "lead_campaign": {
        "name": "Lead campaign (scrape→score→analyze→approve→cadence)",
        "steps": [
            {"id": "scrape", "action": "scrape", "max_retries": 1},
            {"id": "rescore", "action": "rescore"},
            {"id": "deep_dive", "action": "sales_analysis"},
            {"kind": "breakpoint", "id": "approve_outreach",
             "question": "Deep-dive reports + drafts ready (data/prospect_analyses/). Outreach/cadence aage badhau?"},
            {"id": "cadence", "action": "cadence_run"},
        ],
    },
    # Client content onboarding: pack → drafts → HUMAN REVIEW
    "client_content": {
        "name": "Client content pack (pack→social drafts→review)",
        "steps": [
            {"id": "pack", "action": "content_pack", "gate": {"min_count": 1}, "max_retries": 1},
            {"id": "social", "action": "social_drafts", "gate": {"min_count": 1}},
            {"kind": "breakpoint", "id": "review_pack",
             "question": "Content pack + social drafts ready. Client ko bhejne ke liye approve?"},
        ],
    },
    # Growth audit: optimizer pass + revenue sweep (no breakpoint — read/draft only)
    "growth_audit": {
        "name": "Growth audit (optimizer→revenue sweep)",
        "steps": [
            {"id": "optimize", "action": "optimizer"},
            {"id": "revenue", "action": "revenue_sweep"},
        ],
    },
}


def get_process(key: str) -> dict[str, Any] | None:
    return PROCESSES.get((key or "").strip().lower())


def list_keys() -> list[str]:
    return list(PROCESSES.keys())


def list_processes() -> list[dict[str, Any]]:
    out = []
    for k, p in PROCESSES.items():
        out.append({
            "key": k,
            "name": p["name"],
            "steps": [
                {"id": s.get("id"), "kind": s.get("kind", "task"), "action": s.get("action", ""),
                 "gate": s.get("gate"), "question": s.get("question", "")}
                for s in p["steps"]
            ],
        })
    return out


__all__ = ["PROCESSES", "EXECUTORS", "get_process", "list_keys", "list_processes", "execute_step", "check_gate"]
