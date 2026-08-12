"""Operating HQ API — thin admin-gated router over app.platform.office_hq.

Mounted at /api/platform/office/*  (sibling of the existing /api/platform/team
router). Snapshot/pipeline-drilldown are read-only. Approvals decide + agent
manual-run reuse the EXISTING endpoints (/api/growth/approvals/drafts/*,
/api/platform/team/run/*) — deliberately not duplicated here. The mutation
endpoints below (pause/resume/assign/next-action/resolve-stuck/move) are REAL
actions with a narrow, honestly-documented scope — see app.platform.agent_controls
and app.platform.admin_pipeline_overrides docstrings for exactly what each one
does and does not affect.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from app.api.auth_deps import require_admin
from app.api.ratelimit import rate_limit

router = APIRouter(prefix="/platform/office", tags=["Operating HQ"])


@router.get("/snapshot")
async def office_snapshot(current_user=Depends(require_admin)):
    """Full HQ snapshot — rooms, agents, metrics, 12-stage pipeline, approvals,
    system health, next-best-actions. Never raises (degrades to safe defaults
    per-section — see app.platform.office_hq)."""
    from app.platform import office_hq

    try:
        return await office_hq.build_snapshot()
    except Exception as e:  # pragma: no cover — belt-and-suspenders, builder never raises
        from app.platform.office_schema import UNITY_OFFICE_SCHEMA_VERSION

        return {
            "ok": False,
            "schema_version": UNITY_OFFICE_SCHEMA_VERSION,
            "error": str(e),
            "rooms": [],
            "agents": [],
            "metrics": {},
            "pipeline": [],
            "approvals": {"drafts": [], "counts": {}},
            "system_health": {},
            "next_best_actions": [],
        }


@router.post("/boss-review")
async def office_boss_review(current_user=Depends(require_admin)):
    """Boss Finalizer (manager agent) — FREE-LLM verdict + reason per pending
    approval item (cap 10, per-item timeout, never raises). RECOMMEND-ONLY:
    stores nothing, approves nothing — the human still clicks Approve/Reject
    on the existing decide endpoints. Code patches stay never-auto-applied."""
    from app.platform import office_hq

    try:
        return await office_hq.boss_review()
    except Exception as e:  # pragma: no cover — builder never raises
        return {"ok": False, "error": str(e), "verdicts": [], "reviewed": 0}


@router.get("/pipeline/{stage_id}")
async def office_pipeline_stage(stage_id: str, current_user=Depends(require_admin)):
    """Drill-down for one pipeline stage (full item list, not just top-3)."""
    from app.platform import office_hq

    try:
        return await office_hq.pipeline_stage_detail(stage_id)
    except Exception as e:  # pragma: no cover
        return {"id": stage_id, "count": 0, "items": [], "source": "mock", "error": str(e)}


# --------------------------------------------------------------------------- #
# Agent pause/resume — REAL, but narrowly scoped to the manual "Run now"
# button only (see app.platform.agent_controls docstring). Restricted to
# RUNNABLE_MEMBERS at the router edge so a pause flag can never be set on an
# agent it has zero effect on (that would be exactly the "lies to admin"
# failure mode the UI spec forbids).
# --------------------------------------------------------------------------- #
@router.post("/agents/{member}/pause")
async def office_pause_agent(member: str, current_user=Depends(require_admin)):
    from app.platform import agent_controls, office_hq

    if member not in office_hq.RUNNABLE_MEMBERS:
        return {
            "ok": False,
            "error": f"pause has no real effect on '{member}' (no manual-run wiring) — refused",
        }
    result = agent_controls.pause(member, by=getattr(current_user, "email", "admin") or "admin")
    await office_hq.invalidate_snapshot_cache()
    return result


@router.post("/agents/{member}/resume")
async def office_resume_agent(member: str, current_user=Depends(require_admin)):
    from app.platform import agent_controls, office_hq

    result = agent_controls.resume(member, by=getattr(current_user, "email", "admin") or "admin")
    await office_hq.invalidate_snapshot_cache()
    return result


# --------------------------------------------------------------------------- #
# F3 "Kaam Do" — map se ek Hinglish goal dispatch. scope="solo" (sirf yeh agent,
# coordinator.fan_out single-agent) ya "team" (coordinator.coordinate). BOTH
# DRAFT-SAFE (execute=False) + BOUNDED (asyncio.wait_for inside office_hq) so a
# 90s blocking call can never hang the HTTP worker; rate-limited exactly like
# the POST /api/agents/council precedent (WEB_CONCURRENCY=2 — a double-click
# spam of a heavy LLM run would otherwise be an outage). Never raises.
# --------------------------------------------------------------------------- #
class AgentTaskIn(BaseModel):
    goal: str = Field(..., min_length=1, max_length=500)
    scope: str = "solo"  # "solo" | "team"


# --------------------------------------------------------------------------- #
# HQ Ask — 🤖 copilot ka main entry: question -> grounded Boss answer; task ->
# auto-route to the right staff member via the SAME draft-safe Kaam-Do path.
# Rate-limited like council/kaam-do (LLM-heavy). Never raises.
# --------------------------------------------------------------------------- #
class AskIn(BaseModel):
    q: str = Field(..., min_length=1, max_length=500)


@router.post("/ask", dependencies=[Depends(rate_limit("hqask", 10, 60))])
async def office_ask(body: AskIn, current_user=Depends(require_admin)):
    """One box for everything: {ok, kind:"question"|"task", text, member?, run_id?}."""
    from app.platform import office_hq

    try:
        return await office_hq.hq_ask(body.q)
    except Exception as e:  # pragma: no cover — helper never raises
        return {"ok": False, "kind": "question", "text": "", "error": str(e)[:300]}


@router.post("/agents/{member}/task", dependencies=[Depends(rate_limit("agents", 5, 60))])
async def office_agent_task(member: str, body: AgentTaskIn, current_user=Depends(require_admin)):
    """Draft-safe bounded task dispatch to one agent (solo) or the coordinator
    team. Returns {ok, summary, run_id?}; failures/timeouts degrade to an honest
    {ok:False|status:"timeout"} (never raises)."""
    from app.platform import office_hq

    try:
        return await office_hq.run_agent_task(member, body.goal, body.scope)
    except Exception as e:  # pragma: no cover — helper never raises
        return {"ok": False, "error": str(e), "member": member, "scope": body.scope}


# --------------------------------------------------------------------------- #
# Pipeline item mutations
# --------------------------------------------------------------------------- #
class AssignOwnerIn(BaseModel):
    agent_key: str


class NextActionIn(BaseModel):
    note: str


class MoveItemIn(BaseModel):
    item_type: str  # "lead" | "deal"
    next_stage: str


@router.post("/pipeline/item/{item_id}/assign")
async def office_assign_owner(
    item_id: str, body: AssignOwnerIn, current_user=Depends(require_admin)
):
    from app.platform import office_hq

    result = office_hq.assign_item_owner(
        item_id, body.agent_key, by=getattr(current_user, "email", "admin") or "admin"
    )
    await office_hq.invalidate_snapshot_cache()
    return result


@router.post("/pipeline/item/{item_id}/next-action")
async def office_set_next_action(
    item_id: str, body: NextActionIn, current_user=Depends(require_admin)
):
    from app.platform import office_hq

    result = office_hq.set_item_next_action(
        item_id, body.note, by=getattr(current_user, "email", "admin") or "admin"
    )
    await office_hq.invalidate_snapshot_cache()
    return result


@router.post("/pipeline/item/{item_id}/resolve-stuck")
async def office_resolve_stuck(item_id: str, current_user=Depends(require_admin)):
    from app.platform import office_hq

    result = office_hq.resolve_item_stuck(
        item_id, by=getattr(current_user, "email", "admin") or "admin"
    )
    await office_hq.invalidate_snapshot_cache()
    return result


@router.post("/pipeline/item/{item_id}/move")
async def office_move_item(item_id: str, body: MoveItemIn, current_user=Depends(require_admin)):
    from app.platform import office_hq

    result = office_hq.move_item(
        item_id,
        body.item_type,
        body.next_stage,
        by=getattr(current_user, "email", "admin") or "admin",
    )
    await office_hq.invalidate_snapshot_cache()
    return result


# --------------------------------------------------------------------------- #
# F4 — "Subah ki Briefing": daily Hinglish HQ bulletin (text + Swara audio).
# JSON endpoint composes/caches (one LLM+TTS per IST-day; ?force=1 regens); the
# audio endpoint serves ONLY the cached mp3 (never generates) — the frontend
# calls /briefing first, then fetches /briefing/audio as a blob with hdrs()
# because an <audio> tag cannot send the Authorization header. Both never-raise.
# --------------------------------------------------------------------------- #
class ImprovementCouncilIn(BaseModel):
    topic: str = Field("", max_length=400)
    team_size: int = Field(4, ge=2, le=4)
    max_rounds: int = Field(1, ge=1, le=2)


# --------------------------------------------------------------------------- #
# F6 "Team Improvement Council" — snapshot-grounded AgentVerse discussion on
# what to improve next (dynamic expert recruit -> contribute -> synthesize ->
# critic score). Always draft-only. Distinct rate bucket from /ask (heavier,
# multi-round LLM run) so the two features don't share one IP budget.
# --------------------------------------------------------------------------- #
@router.post("/improve", dependencies=[Depends(rate_limit("hqcouncil", 4, 120))])
async def office_improvement_council(
    body: ImprovementCouncilIn, current_user=Depends(require_admin)
):
    """Team Improvement Council: {ok, topic, experts, contributions, solution,
    summary, score}. Never raises (degrades to ok:False / status:timeout)."""
    from app.platform import office_hq

    try:
        return await office_hq.improvement_council(body.topic, body.team_size, body.max_rounds)
    except Exception as e:  # pragma: no cover — helper never raises
        return {"ok": False, "error": str(e)[:300], "topic": body.topic}


@router.get("/briefing")
async def office_briefing(force: int = 0, current_user=Depends(require_admin)):
    """Today's HQ radio-bulletin: {ok, date, text, has_audio}. Cached once per
    IST-day; force=1 regenerates. Never raises (degrades to text-only / ok:False)."""
    from app.platform import office_briefing as ob

    try:
        return await ob.build_briefing(force=bool(force))
    except Exception as e:  # pragma: no cover — builder never raises
        return {"ok": False, "error": str(e), "date": "", "text": "", "has_audio": False}


@router.get("/briefing/audio")
async def office_briefing_audio(current_user=Depends(require_admin)):
    """Serve today's cached bulletin mp3 (Swara's voice). 404-safe JSON when the
    audio was never generated / TTS failed — never raises."""
    from app.platform import office_briefing as ob

    try:
        path = ob.audio_path_for_today()
        if not path:
            return JSONResponse(
                status_code=404, content={"ok": False, "error": "audio not available"}
            )
        return FileResponse(path, media_type="audio/mpeg", filename="briefing.mp3")
    except Exception as e:  # pragma: no cover
        return JSONResponse(status_code=404, content={"ok": False, "error": str(e)})


@router.get("/agent-os-status")
async def office_agent_os_status(current_user=Depends(require_admin)):
    """Read-only Agent OS + OmniRoute operator status (ADR-109).

    Never returns API keys, raw prompts, or customer PII. OmniRoute remains
    INERT unless both flags + key are set; this endpoint only reports truth.
    """
    import os

    try:
        from app.platform.agent_os_routing import agent_route_table
        from app.platform.omniroute_client import (
            _TASK_ROUTES,
            agents_enabled,
            omniroute_available,
            omniroute_enabled,
        )
        from app.platform.team import STAFF
    except Exception as e:  # pragma: no cover
        return {"ok": False, "error": type(e).__name__, "agents": [], "omniroute": {}}

    try:
        table = agent_route_table()
        agents = []
        eligible = 0
        forbidden = 0
        for key, meta in STAFF.items():
            row = table.get(key) or {}
            omni_ok = bool(row.get("omniroute_eligible"))
            if omni_ok:
                eligible += 1
            else:
                forbidden += 1
            agents.append(
                {
                    "key": key,
                    "name": meta.get("name"),
                    "title": meta.get("title"),
                    "product": meta.get("product"),
                    "category": row.get("category"),
                    "omniroute_task": row.get("omniroute_task"),
                    "privacy_class": row.get("privacy_class"),
                    "omniroute_eligible": omni_ok,
                    "may_contact_customers": row.get("may_contact_customers"),
                    "requires_human_approval_before_publish": row.get(
                        "requires_human_approval_before_publish"
                    ),
                    "auto_run_allowed": row.get("auto_run_allowed"),
                    "queue": row.get("queue"),
                }
            )
        base = os.getenv("OMNIROUTE_BASE_URL", "http://127.0.0.1:20128/v1")
        key_set = bool(os.getenv("OMNIROUTE_API_KEY"))
        omni = {
            "enabled_flag": omniroute_enabled(),
            "agents_flag": os.getenv("OMNIROUTE_AGENTS", "0").strip().lower()
            in ("1", "true", "yes"),
            "api_key_present": key_set,
            "available": omniroute_available(),
            "agents_hook_armed": agents_enabled(),
            "base_url": base,
            "task_routes": sorted(_TASK_ROUTES.keys()),
            "prod_note": (
                "VPS pe gateway nahi hai — flags OFF rakho jab tak "
                "OMNIROUTE_BASE_URL + loopback/tunnel na ho."
            ),
        }
        return {
            "ok": True,
            "staff_count": len(STAFF),
            "eligible_for_omniroute": eligible,
            "forbidden_omniroute": forbidden,
            "agents": agents,
            "omniroute": omni,
            "runbook": "/docs path: docs/AGENT_OS_OMNIROUTE_ADMIN_RUNBOOK.md",
        }
    except Exception as e:  # pragma: no cover
        return {"ok": False, "error": type(e).__name__, "agents": [], "omniroute": {}}
