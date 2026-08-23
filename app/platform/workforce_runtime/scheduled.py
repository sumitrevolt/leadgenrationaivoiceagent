"""Evidence-gated scheduler bridge into the canonical workforce dispatch."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.platform.workforce_runtime.dispatch import dispatch, runtime_status
from app.platform.workforce_runtime.types import WorkforceRequest, WorkforceResult

# Only non-customer, non-Voice scheduled work enters DSH during migration.
# Everything else remains on the direct scheduler path until its authority wave.
SAFE_SCHEDULED_JOBS: dict[str, str] = {
    "ops": "none",
    "engineer_sre": "none",
    "engineer_finops": "none",
    "engineer_security": "none",
    "engineer_dbre": "none",
    "engineer_dataquality": "none",
    "engineer_deps": "none",
    "mcp_engineer": "none",
    "readiness_digest": "none",
    "gsc_rank": "internal",
    "revenue_snapshot": "internal",
    "meter_watch": "none",
    "task_lease_reap": "internal",
}

NEVER_DSH_SCHEDULED_JOBS = frozenset(
    {
        "platform_dial",
        "call_kpi_digest",
        "qa",
        "trainer",
        "email_outreach",
        "email_followup",
        "reply_triage",
        "approval_email_sweep",
        "sales_autopilot",
        "social_drain",
        "product_one_health",
        "hq_auto_chase",
        "reply_auto_send",
        "content_approval_sweep",
        "trial_nudge",  # customer-contact lane (trial UPI email) — direct path only
    }
)


def action_for_job(job: str) -> str:
    return f"scheduled__{str(job or '').strip().lower()}"


def _configured_for(agent_id: str) -> bool:
    status = runtime_status()
    allowlist = set(status.get("dsh_agent_allowlist") or [])
    return bool(
        agent_id in allowlist
        and (status.get("dsh_runtime_enabled") or status.get("dsh_shadow_enabled"))
    )


def _register(agent_id: str, job: str, side_effect: str) -> str:
    from app.platform.agent_runtime import (
        AgentCapability,
        AgentExecutionContext,
        register_capability,
    )

    action = action_for_job(job)

    async def _run(ctx: AgentExecutionContext) -> dict[str, Any]:
        from app.platform import team_scheduler

        ok = await team_scheduler._run_job_direct(
            job,
            retry_count=int(ctx.task.payload.get("retry_count") or 0),
        )
        if not ok:
            raise RuntimeError("scheduled_job_reported_failure")
        return {"ok": True, "job": job, "source": "workforce_dispatch"}

    _run.__name__ = f"dsh_scheduled_{job}"
    register_capability(
        AgentCapability(
            agent_id=agent_id,
            action=action,
            fn=_run,
            side_effect=side_effect,
            tenant_scoped=False,
            requires_approval=False,
            description=f"Evidence-gated scheduler bridge for {job}",
        )
    )
    return action


async def maybe_dispatch(
    job: str,
    *,
    retry_count: int = 0,
    idempotency_key: str = "",
) -> WorkforceResult | None:
    """Return None when this job must remain on the deterministic direct path."""
    job = str(job or "").strip().lower()
    if job in NEVER_DSH_SCHEDULED_JOBS or job not in SAFE_SCHEDULED_JOBS:
        return None

    from app.platform import agent_runtime
    from app.platform.agent_runtime_workforce import ensure_workforce_registered
    from app.platform.owner_agent_execution import agent_for_job

    agent_id = str(agent_for_job(job) or "").strip().lower()
    if not agent_id or agent_id not in agent_runtime.PILOT_AGENTS or not _configured_for(agent_id):
        return None

    ensure_workforce_registered()
    action = _register(agent_id, job, SAFE_SCHEDULED_JOBS[job])
    slot = datetime.now(timezone.utc).strftime("%Y%m%d%H")
    return await dispatch(
        WorkforceRequest(
            agent_id=agent_id,
            action=action,
            payload={"job": job, "retry_count": int(retry_count or 0)},
            idempotency_key=idempotency_key or f"scheduler_{job}_{slot}",
            trigger="scheduler",
        )
    )


__all__ = [
    "NEVER_DSH_SCHEDULED_JOBS",
    "SAFE_SCHEDULED_JOBS",
    "action_for_job",
    "maybe_dispatch",
]
