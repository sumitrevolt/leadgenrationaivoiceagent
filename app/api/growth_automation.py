"""Agent automation-ops endpoints — self-improve loop, skill library/pack, code
upgrader, social drafts, lead harvester, approval cockpit, self-improve gates.

Extracted from app/api/growth.py (2026-06-20 refactor) to shrink the god-router.
Mounted via growth.router.include_router(); paths unchanged (/api/growth/...).
Also (transitively) mounts the /process/* sub-router.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.auth_deps import require_admin, require_super_admin

router = APIRouter(tags=["Growth"])


# ------------- Self-improve continuous loop + skill library + naye channels ------------- #
@router.get("/selfimprove/status")
async def selfimprove_status(_user=Depends(require_admin)):
    """Continuous loop ka live status: heartbeat, runs, queue, skill summary."""
    from app.agents import self_improve

    return self_improve.status()


@router.post("/selfimprove/run")
async def selfimprove_run(_user=Depends(require_admin)):
    """Loop tick ABHI enqueue karo (Celery worker me chalega — web process block
    nahi hota). Flag OFF ho to bhi one-shot enqueue ho jata (tick khud gate check
    karta, requeue sirf flag ON pe). Celery down ho to in-process fallback."""
    try:
        from app.tasks.staff_jobs import self_improve_tick

        r = self_improve_tick.delay()
        return {"ok": True, "queued": True, "task_id": str(getattr(r, "id", ""))}
    except Exception:
        try:
            from app.agents import self_improve

            res = await self_improve.run_once()
            return {"ok": True, "queued": False, "fallback": "in_process", "result": res}
        except Exception as e2:
            return {
                "ok": False,
                "queued": False,
                "error": str(e2)[:200],
                "hint": "celery worker chal raha hai?",
            }


class SelfImproveTaskIn(BaseModel):
    task: str
    action: str = ""


@router.post("/selfimprove/task")
async def selfimprove_add_task(body: SelfImproveTaskIn, _user=Depends(require_admin)):
    """Manual task queue me daalo — loop agle tick pe ise pehle uthayega.
    Valid actions: self_improve.ACTIONS keys (khali = auto-pick)."""
    from app.agents import self_improve

    return self_improve.add_task(body.task, body.action, source="manual")


@router.get("/selfimprove/actions")
async def selfimprove_actions(_user=Depends(require_admin)):
    """Available loop actions + descriptions."""
    from app.agents import self_improve

    return {
        "actions": [
            {"key": k, "llm_heavy": v[0], "desc": v[1]} for k, v in self_improve.ACTIONS.items()
        ]
    }


@router.get("/skills/library")
async def skills_library(_user=Depends(require_admin)):
    """Auto-learn skill library: per-tactic success-rates + recent lessons."""
    from app.platform import skill_library

    return skill_library.summary()


class LessonIn(BaseModel):
    topic: str = "general"
    lesson: str


@router.post("/skills/lesson")
async def skills_add_lesson(body: LessonIn, _user=Depends(require_admin)):
    """Manual lesson add (human coaching → agents agle runs me use karte)."""
    from app.platform import skill_library

    return skill_library.record_lesson(body.topic, body.lesson, source="manual", agent="sumit")


# ------------- Skill pack (Claude project skills → VPS agents) + code upgrader ------------- #
@router.get("/skills/pack")
async def skills_pack_list(q: str = "", _user=Depends(require_admin)):
    """35+ project skills (+agent-authored extras) — list ya keyword search."""
    from app.platform import skill_pack

    if q:
        return {"query": q, "matches": skill_pack.find(q, k=5)}
    return {"enabled": skill_pack.enabled(), "skills": skill_pack.list_skills()}


@router.get("/skills/pack/{name}")
async def skills_pack_get(name: str, _user=Depends(require_admin)):
    from app.platform import skill_pack

    s = skill_pack.load(name)
    if not s:
        raise HTTPException(status_code=404, detail="skill not found")
    return s


@router.post("/skills/pack/ingest")
async def skills_pack_ingest(_user=Depends(require_admin)):
    """Saari skills KB namespace 'skills' me (Qdrant semantic recall)."""
    from app.platform import skill_pack

    return skill_pack.ingest_to_kb()


class SkillAuthorIn(BaseModel):
    name: str
    text: str


@router.post("/skills/pack/author")
async def skills_pack_author(body: SkillAuthorIn, _user=Depends(require_admin)):
    """Tier-1 SAFE write — naya/updated skill data/skills_extra/ me (runtime-live)."""
    from app.platform import skill_pack

    return skill_pack.author(body.name, body.text)


@router.post("/upgrader/scan")
async def upgrader_scan(_user=Depends(require_admin)):
    """Vikram: observability signals → code-upgrade proposals (flag-independent manual run)."""
    from app.agents import code_upgrader

    return await code_upgrader.scan_and_propose()


@router.get("/upgrader/patches")
async def upgrader_patches(
    status: str | None = None, limit: int = 50, _user=Depends(require_admin)
):
    from app.agents import code_upgrader

    return {"patches": code_upgrader.list_patches(status, limit)}


class PatchStatusIn(BaseModel):
    status: str  # approved | rejected | applied
    note: str = ""


@router.post("/upgrader/patches/{patch_id}/status")
async def upgrader_patch_status(
    patch_id: str, body: PatchStatusIn, _user=Depends(require_super_admin)
):
    """Hybrid gate: core-code patch approve/reject — SUPER_ADMIN only (RBAC design)."""
    from app.agents import code_upgrader

    return code_upgrader.set_status(patch_id, body.status, body.note)


@router.get("/upgrader/code-search")
async def upgrader_code_search(q: str, k: int = 6, _user=Depends(require_admin)):
    """Semantic codebase search (Kilo-Code "codebase_search" parity) — engineering
    agents (Vikram) isi se relevant code dhoondte hain. Index daily training job se
    banta; khaali / deps missing → []. Read-only, flag-independent (admin-gated)."""
    from app.agents import code_search

    hits = await code_search.search(q, k=k)
    return {
        "ok": True,
        "query": q,
        "grounding_enabled": code_search.enabled(),
        "count": len(hits),
        "hits": hits,
    }


class CodeDiagnosticsIn(BaseModel):
    code: str
    paths: list[str] = []  # optional: cited file paths to existence-check
    lint: bool = True


@router.post("/upgrader/diagnostics")
async def upgrader_diagnostics(body: CodeDiagnosticsIn, _user=Depends(require_admin)):
    """Static code diagnostics (OpenCode LSP-diagnostics parity) — admin patch-code
    ko approve karne se PEHLE validate kare: ast syntax (+ ruff lint if available) +
    referenced-path existence. Read-only, never-raise."""
    from app.agents import code_diagnostics

    diags = code_diagnostics.check_code(body.code, run_lint=body.lint)
    if body.paths:
        diags = list(diags) + code_diagnostics.check_references(body.paths)
    return {
        "ok": not any(d.get("level") == "error" for d in diags),
        "count": len(diags),
        "summary": code_diagnostics.summary(diags),
        "diagnostics": diags,
    }


@router.get("/social/channels")
async def social_channels_list(_user=Depends(require_admin)):
    """Naye customer-approach channels (sab ban-safe drafts)."""
    from app.marketing import social_channels

    return {"channels": social_channels.list_channels()}


class SocialDraftIn(BaseModel):
    channel: str
    niche: str = "general"
    city: str = ""
    business_name: str = ""


@router.post("/social/draft")
async def social_draft(body: SocialDraftIn, _user=Depends(require_admin)):
    """Ek naye channel ka ready-to-post Hinglish draft (manual 1-click post)."""
    from app.marketing import social_channels

    return await social_channels.draft(body.channel, body.niche, body.city, body.business_name)


class SocialBatchIn(BaseModel):
    niche: str = "general"
    city: str = ""
    business_name: str = ""
    channels: list[str] | None = None
    limit: int = 4


@router.post("/social/batch")
async def social_batch(body: SocialBatchIn, _user=Depends(require_admin)):
    """Multiple naye channels ka draft pack."""
    from app.marketing import social_channels

    return await social_channels.draft_batch(
        body.niche, body.city, body.business_name, body.channels, body.limit
    )


# ------------- Lead harvester (multi-source, legal-only, automated loop) ------------- #
class HarvestIn(BaseModel):
    niche: str = ""
    city: str = ""
    limit: int = 10
    sources: list[str] | None = None


@router.post("/harvest/run")
async def harvest_run(body: HarvestIn, _user=Depends(require_admin)):
    """Multi-source lead harvest abhi chalao (manual = flag-independent).
    Sources: prospector (Places/OSM), websearch (BRAVE_API_KEY), opendata
    (DATA_GOV_IN_API_KEY) + email-enrich. Directory/social scraping NAHI (ToS)."""
    from app.platform import lead_harvester

    return await lead_harvester.run_harvest(body.niche, body.city, body.limit, body.sources)


@router.get("/harvest/runs")
async def harvest_runs(limit: int = 15, _user=Depends(require_admin)):
    """Recent harvest runs (per-source stats)."""
    from app.platform import lead_harvester

    return {"runs": lead_harvester.recent_runs(limit)}


@router.get("/harvest/sources")
async def harvest_sources(_user=Depends(require_admin)):
    """Source readiness (kaunse keys armed) + blocked-domains policy."""
    from app.platform import lead_harvester

    return lead_harvester.source_status()


@router.post("/harvest/enrich")
async def harvest_enrich(limit: int = 10, _user=Depends(require_admin)):
    """Email-less prospects pe enrich waterfall abhi chalao."""
    from app.platform import lead_harvester

    return await lead_harvester.enrich_missing_emails(limit)


@router.get("/harvest/gtm-coverage")
async def harvest_gtm_coverage(_user=Depends(require_admin)):
    """GTM City x Niche coverage matrix status — total/covered pairs, %, leads harvested,
    top uncovered (next up). Gated GTM_TARGETING (else enabled:false)."""
    from app.platform import gtm_targeting

    return gtm_targeting.coverage_summary()


@router.post("/harvest/udyam-run")
async def harvest_udyam_run(
    city: str = "", niche: str = "general", limit: int = 20, _user=Depends(require_admin)
):
    """Run the Udyam-PRIMARY pipeline now: data.gov.in Udyam seeds -> Google-Maps +
    website enrich -> dedup -> persist. Gated UDYAM_PIPELINE (+ DATA_GOV_IN_API_KEY)."""
    from app.platform import udyam_pipeline

    return await udyam_pipeline.run(limit=max(1, min(int(limit or 20), 50)), city=city, niche=niche)


@router.post("/harvest/indiamart-run")
async def harvest_indiamart_run(days: int = 1, niche: str = "general", _user=Depends(require_admin)):
    """Pull the seller's own IndiaMART buyer-leads (official Lead Manager API) + persist.
    Gated INDIAMART_CRM_KEY (seller account). Legal — NOT directory scraping."""
    from app.integrations import indiamart_leads

    return await indiamart_leads.fetch_and_persist(days=max(1, min(int(days or 1), 7)), niche=niche)


@router.get("/enrich/opencorporates")
async def enrich_opencorporates(name: str, _user=Depends(require_admin)):
    """Company-registry lookup (CIN/status/incorporation) for a business name.
    Gated OPENCORPORATES_API_TOKEN (else empty)."""
    from app.integrations import opencorporates

    return await opencorporates.enrich(name)


# Process-engine endpoints extracted to app/api/growth_process.py (2026-06-20);
# included below so /api/growth/process/* paths stay unchanged.
from app.api.growth_process import router as _process_router  # noqa: E402

router.include_router(_process_router)


# --------------------- Agentic-Output Approval Cockpit (sub-project D V1) ----- #
@router.get("/approvals/drafts")
async def approvals_drafts(include_decided: bool = False, _user=Depends(require_admin)):
    """Unified agentic-draft queue (sales/coordinator/fde) — risk-tiered cockpit.

    Bridge-first V1: surfaces the orphan agentic outputs that otherwise rot in
    data/*.jsonl. code_upgrader/process-breakpoint/self_improve keep their own
    endpoints. Read-only; inert if no drafts exist."""
    from app.platform import approvals_bridge

    return approvals_bridge.list_drafts(include_decided=include_decided)


class DraftDecideIn(BaseModel):
    decision: str  # approve | reject


@router.post("/approvals/drafts/{source}/{item_id}/decide")
async def approvals_draft_decide(
    source: str, item_id: str, body: DraftDecideIn, _user=Depends(require_admin)
):
    """Smart 1-click: stamp status + fire the BOUNDED SAFE next-action per source
    (sales=mark-reviewed · coordinator=self_improve task · fde=enable disabled drip).
    Risky real-send stays draft-only by design. Idempotent."""
    from app.platform import approvals_bridge

    return approvals_bridge.decide(
        source, item_id, body.decision, by=getattr(_user, "email", "admin") or "admin"
    )


# ----------------------------- Self-Improve Approval Gates (Phase 6) -------- #


@router.get("/selfimprove/cost-status")
async def selfimprove_cost(current_user=Depends(require_admin)):
    """Daily cost tracking status (budget cap, spent, remaining)."""
    from app.agents import self_improve

    return self_improve.cost_status()


@router.get("/selfimprove/approvals-pending")
async def selfimprove_approvals(current_user=Depends(require_admin)):
    """List all pending approval tasks (Phase 6 gate)."""
    from app.agents import self_improve

    status = self_improve.approval_status()
    return status


class ApprovalActionIn(BaseModel):
    reason: str = ""


@router.patch("/selfimprove/approval/{task_id}/approve")
async def approve_selfimprove_task(
    task_id: str,
    body: ApprovalActionIn | None = None,
    current_user=Depends(require_admin),
):
    """Admin approves a pending self-improve task."""
    from app.agents import self_improve

    aq = self_improve._get_approval_queue()
    success = aq.approve(task_id)
    if success:
        try:
            from app.platform import team

            team.log_event(
                "admin",
                "selfimprove_approved",
                f"Task {task_id} approved by {getattr(current_user, 'email', 'admin')}",
            )
        except Exception:
            pass
        return {"status": "approved", "task_id": task_id}
    return {"status": "error", "detail": f"task {task_id} not found"}


@router.patch("/selfimprove/approval/{task_id}/reject")
async def reject_selfimprove_task(
    task_id: str,
    body: ApprovalActionIn,
    current_user=Depends(require_admin),
):
    """Admin rejects a pending self-improve task."""
    from app.agents import self_improve

    aq = self_improve._get_approval_queue()
    success = aq.reject(task_id, reason=body.reason or "")
    if success:
        try:
            from app.platform import team

            team.log_event(
                "admin",
                "selfimprove_rejected",
                f"Task {task_id} rejected: {body.reason or 'no reason'} by {getattr(current_user, 'email', 'admin')}",
            )
        except Exception:
            pass
        return {"status": "rejected", "task_id": task_id, "reason": body.reason}
    return {"status": "error", "detail": f"task {task_id} not found"}
