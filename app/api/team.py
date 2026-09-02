"""
Team API — AI staff roster, live activity feed, manual job runs.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.auth_deps import require_admin
from app.models.user import User
from app.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter(prefix="/platform/team", tags=["Team"])


@router.get("")
async def get_team_status(product: str | None = None, current_user: User = Depends(require_admin)):
    """?product=marketing|voice => sirf us product ke agents + shared platform staff (ADR-009)."""
    try:
        from app.platform import team

        status = team.team_status()
        p = (product or "").strip().lower()
        if p in ("marketing", "voice") and isinstance(status.get("members"), list):
            keep = set(team.staff_for_product(p))
            status["members"] = [m for m in status["members"] if m.get("key") in keep]
            status["product"] = p
        return status
    except Exception as e:
        logger.warning(f"[team-api] status failed: {e}")
        return {"error": str(e), "members": [], "totals": {}}


@router.get("/events")
async def get_team_events(
    limit: int = 60, member: str | None = None, current_user: User = Depends(require_admin)
):
    try:
        from app.platform import team

        return {"events": team.recent_events(limit=limit, member=member)}
    except Exception as e:
        logger.warning(f"[team-api] events failed: {e}")
        return {"events": [], "error": str(e)}


@router.get("/stats")
async def get_team_stats(
    days: int = 7, member: str | None = None, current_user: User = Depends(require_admin)
):
    """Per-agent success-rate + last-run rollup (degrade-detection KPI). Feed =
    /events; yeh = aggregate. Never raises — empty on failure."""
    try:
        from app.platform import team

        return team.stats(member=member, days=days)
    except Exception as e:
        logger.warning(f"[team-api] stats failed: {e}")
        return {"agents": [], "overall": {}, "error": str(e)}


@router.post("/run/{member}")
async def run_team_member(member: str, current_user: User = Depends(require_admin)):
    try:
        import uuid

        from app.platform import agent_controls, agent_runtime, team
        from app.platform.agent_runtime_workforce import (
            ACTION_DELIVERY_SCAN,
            ACTION_OWNED,
            ensure_workforce_registered,
        )

        agent_id = agent_controls.ALIAS_TO_MEMBER.get(
            member.strip().lower(), member.strip().lower()
        )
        ensure_workforce_registered()
        capabilities = agent_runtime.capabilities_for(agent_id)
        if not capabilities:
            return {"error": f"unknown member/job: {member}"}
        action = (
            ACTION_DELIVERY_SCAN
            if ACTION_DELIVERY_SCAN in capabilities
            else ACTION_OWNED
            if ACTION_OWNED in capabilities
            else capabilities[0]
        )
        team.log_event("manager", "task_assigned", f"manual run: {agent_id}")
        result = await agent_runtime.submit(
            agent_id,
            action,
            {"source": "team_api_manual"},
            idempotency_key=f"manual_{uuid.uuid4().hex}",
            trigger="manual_api",
        )
        return result.to_dict()
    except Exception as e:
        logger.warning(f"[team-api] run {member} failed: {e}")
        return {"error": str(e)}


class ProspectStatusIn(BaseModel):
    status: str = Field(..., max_length=20, description="ready|sent|replied|client|dead")


class OutreachReviewDecisionIn(BaseModel):
    email: str = Field(..., min_length=3, max_length=160)
    decision: str = Field(..., min_length=3, max_length=40)
    note: str = Field("", max_length=300)
    bucket: str = Field("", max_length=60)


@router.get("/prospects")
async def get_prospects(
    status: str | None = None, limit: int = 100, current_user: User = Depends(require_admin)
):
    try:
        from app.platform import prospector

        return {"prospects": prospector.list_prospects(status=status, limit=limit)}
    except Exception as e:
        logger.warning(f"[team-api] prospects list failed: {e}")
        return {"prospects": [], "error": str(e)}


@router.post("/prospects/run")
async def run_prospecting_now(current_user: User = Depends(require_admin)):
    try:
        from app.platform import prospector, team

        team.log_event("manager", "task_assigned", "manual run: prospecting (rohan)")
        return await prospector.run_prospecting()
    except Exception as e:
        logger.warning(f"[team-api] prospects run failed: {e}")
        return {"ok": False, "error": str(e)}


@router.post("/prospects/{pid}/status")
async def set_prospect_status(
    pid: str, body: ProspectStatusIn, current_user: User = Depends(require_admin)
):
    try:
        from app.platform import prospector

        ok = prospector.mark_prospect(pid, body.status)
        return {"ok": ok, "id": pid, "status": body.status if ok else None}
    except Exception as e:
        logger.warning(f"[team-api] prospect status failed: {e}")
        return {"ok": False, "error": str(e)}


@router.post("/email-outreach/run")
async def run_email_outreach_now(current_user: User = Depends(require_admin)):
    try:
        from app.platform import auto_outreach, team

        team.log_event("manager", "task_assigned", "manual run: email outreach (rohan)")
        return await auto_outreach.run_email_outreach()
    except Exception as e:
        logger.warning(f"[team-api] email-outreach run failed: {e}")
        return {"error": str(e)}


@router.get("/email-outreach/stats")
async def get_email_outreach_stats(current_user: User = Depends(require_admin)):
    try:
        from app.platform import auto_outreach

        return auto_outreach.outreach_stats()
    except Exception as e:
        logger.warning(f"[team-api] email-outreach stats failed: {e}")
        return {"error": str(e)}


@router.get("/email-outreach/runs")
async def get_email_outreach_runs(limit: int = 5, current_user: User = Depends(require_admin)):
    """Last email-outreach / follow-up run outcomes (Schedule tab line ke liye).
    Har run ka result AgentEvent meta me hota hai — yahan sirf filtered read."""
    try:
        from app.platform import auto_outreach

        runs = auto_outreach.last_run_summaries(limit=limit)
        return {"runs": runs, "total_returned": len(runs)}
    except Exception as e:
        logger.warning(f"[team-api] email-outreach runs failed: {e}")
        return {"runs": [], "total_returned": 0, "error": str(e)}


@router.get("/outreach-activity")
async def get_outreach_activity(limit: int = 20, current_user: User = Depends(require_admin)):
    """Admin-friendly: kisko email bheja, kitne, kya reply aaya (ek nazar me)."""
    try:
        from app.platform import auto_outreach

        return auto_outreach.outreach_activity(limit=max(1, min(int(limit or 20), 100)))
    except Exception as e:
        logger.warning(f"[team-api] outreach-activity failed: {e}")
        return {"error": str(e), "summary": {}, "recent_sent": [], "recent_replies": []}


@router.get("/outreach-pending-review")
async def get_outreach_pending_review(
    bucket: str = "", limit: int = 100, current_user: User = Depends(require_admin)
):
    """Admin export helper: deduped pending recipients by review bucket."""
    try:
        from app.platform import auto_outreach

        return auto_outreach.pending_review_candidates(
            bucket=str(bucket or ""), limit=max(1, min(int(limit or 100), 500))
        )
    except Exception as e:
        logger.warning(f"[team-api] outreach-pending-review failed: {e}")
        return {"error": str(e), "bucket": bucket or "", "count": 0, "candidates": []}


@router.post("/outreach-review-decision")
async def post_outreach_review_decision(
    payload: OutreachReviewDecisionIn, current_user: User = Depends(require_admin)
):
    """Operator bookmark: admin records a review decision for a pending recipient
    (reviewed_sent / reviewed_skip / reviewed_schedule / reviewed_suppress / reviewed_unsuppress).
    Append-only jsonl; never auto-sends, never touches warmup state."""
    try:
        from app.platform import auto_outreach

        return auto_outreach.record_review_decision(
            email=payload.email,
            decision=payload.decision,
            note=payload.note or "",
            bucket=payload.bucket or "",
            reviewer=(current_user.email if getattr(current_user, "email", None) else ""),
        )
    except Exception as e:
        logger.warning(f"[team-api] outreach-review-decision failed: {e}")
        return {"ok": False, "error": str(e)}


@router.get("/outreach-review-decisions")
async def get_outreach_review_decisions(
    bucket: str = "", limit: int = 100, current_user: User = Depends(require_admin)
):
    """Latest decision per recipient (optionally filtered by bucket)."""
    try:
        from app.platform import auto_outreach

        return {
            "counts": auto_outreach.review_decision_counts(),
            **auto_outreach.list_review_decisions(
                bucket=str(bucket or ""), limit=max(1, min(int(limit or 100), 1000))
            ),
        }
    except Exception as e:
        logger.warning(f"[team-api] outreach-review-decisions failed: {e}")
        return {"error": str(e), "bucket": bucket or "", "count": 0, "decisions": []}


@router.get("/outreach-review-decision-counts")
async def get_outreach_review_decision_counts(current_user: User = Depends(require_admin)):
    """Counts by decision-kind (dashboard tile)."""
    try:
        from app.platform import auto_outreach

        return auto_outreach.review_decision_counts()
    except Exception as e:
        logger.warning(f"[team-api] outreach-review-decision-counts failed: {e}")
        return {"error": str(e), "unique_recipients": 0}


@router.post("/email-followups/run")
async def run_email_followups_now(current_user: User = Depends(require_admin)):
    try:
        from app.platform import auto_outreach, team

        team.log_event("manager", "task_assigned", "manual run: email follow-ups (rohan)")
        return await auto_outreach.run_email_followups()
    except Exception as e:
        logger.warning(f"[team-api] email-followups run failed: {e}")
        return {"error": str(e)}


@router.post("/reply-triage/run")
async def run_reply_triage_now(current_user: User = Depends(require_admin)):
    try:
        from app.platform import reply_agent, team

        team.log_event("manager", "task_assigned", "manual run: reply triage")
        return await reply_agent.run_reply_triage()
    except Exception as e:
        logger.warning(f"[team-api] reply-triage run failed: {e}")
        return {"error": str(e)}


@router.get("/growth")
async def get_growth(current_user: User = Depends(require_admin)):
    try:
        from app.platform import growth_engine

        return {"pulse": growth_engine.latest_pulse(), "history": growth_engine.history(30)}
    except Exception as e:
        logger.warning(f"[team-api] growth get failed: {e}")
        return {"pulse": {}, "history": [], "error": str(e)}


@router.post("/growth/run")
async def run_growth_now(current_user: User = Depends(require_admin)):
    try:
        from app.platform import growth_engine, team

        team.log_event("manager", "task_assigned", "manual run: growth pulse")
        return await growth_engine.pulse()
    except Exception as e:
        logger.warning(f"[team-api] growth run failed: {e}")
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Agent Scheduler (scheduler_config) — admin toggle + per-job run-now + run-due.
# run-due = external recovery tick (Bearer LEADGEN_SCHEDULER_SECRET, admin JWT
# NAHI chahiye — host cron/systemd timer hit kar sake). Secret unset => 503
# fail-CLOSED (webhook-signature pattern).
# ---------------------------------------------------------------------------


class SchedulerToggleIn(BaseModel):
    enabled: bool
    note: str = Field("", max_length=120)


@router.post("/scheduler/run-due")
async def scheduler_run_due(request: Request, max_jobs: int = 3):
    """Overdue/never-ran jobs ko re-dispatch karo (bounded, idempotent-ish).
    Backup dead-man ticker: Celery beat + in-process loop dono mar jayein to
    external cron isse hit karke agents revive kar sakta hai."""
    import hmac as _hmac
    import os as _os

    secret = _os.environ.get("LEADGEN_SCHEDULER_SECRET", "").strip()
    if not secret:
        raise HTTPException(status_code=503, detail="scheduler secret not configured")
    auth = request.headers.get("authorization", "")
    if not _hmac.compare_digest(auth, f"Bearer {secret}"):
        raise HTTPException(status_code=401, detail="invalid scheduler token")
    try:
        from app.platform import scheduler_config

        return scheduler_config.run_due(max_jobs=max_jobs)
    except Exception as e:
        logger.warning(f"[team-api] scheduler run-due failed: {e}")
        return {"ok": False, "error": str(e)[:150]}


@router.get("/scheduler")
async def get_scheduler_jobs(current_user: User = Depends(require_admin)):
    """Saare scheduled agent-jobs: label/cadence/owner + enabled + heartbeat health."""
    try:
        from app.platform import scheduler_config

        return scheduler_config.list_jobs()
    except Exception as e:
        logger.warning(f"[team-api] scheduler list failed: {e}")
        return {"jobs": [], "error": str(e)}


@router.get("/scheduler/runs")
async def get_scheduler_runs(
    job: str = "",
    status: str = "",
    limit: int = 100,
    failures_first: bool = True,
    current_user: User = Depends(require_admin),
):
    """Per-run history (data/job_runs.jsonl) — kaunsa job kab chala, pass/fail +
    fail hone ki wajah (error_class/message). Pehle yeh jsonl write-only tha (koi
    padhta hi nahi) — ab admin run-history + failure-reason dekh sakta.
    Default failures_first=true (jo toota wo pehle). Never raises."""
    try:
        from app.platform import automation_health

        runs = automation_health.run_history(
            job=job, status=status, limit=limit, failures_first=failures_first
        )
        return {"runs": runs, "total_returned": len(runs)}
    except Exception as e:
        logger.warning(f"[team-api] scheduler runs failed: {e}")
        return {"runs": [], "total_returned": 0, "error": str(e)}


@router.post("/scheduler/{job}/toggle")
async def toggle_scheduler_job(
    job: str, body: SchedulerToggleIn, current_user: User = Depends(require_admin)
):
    """Job ON/PAUSE karo — runtime, no-restart (data/scheduler_overrides.json)."""
    try:
        from app.platform import scheduler_config

        by = getattr(current_user, "email", None) or getattr(current_user, "username", "admin")
        return scheduler_config.set_enabled(job, body.enabled, by=str(by), note=body.note)
    except Exception as e:
        logger.warning(f"[team-api] scheduler toggle {job} failed: {e}")
        return {"ok": False, "error": str(e)[:150]}


@router.post("/scheduler/{job}/run")
async def run_scheduler_job_now(job: str, current_user: User = Depends(require_admin)):
    """Job ABHI chalao — background dispatch (Celery prefer; HTTP block nahi)."""
    try:
        from app.platform import scheduler_config

        by = getattr(current_user, "email", None) or getattr(current_user, "username", "admin")
        return scheduler_config.run_now(job, by=str(by))
    except Exception as e:
        logger.warning(f"[team-api] scheduler run {job} failed: {e}")
        return {"ok": False, "error": str(e)[:150]}


__all__ = ["router"]
