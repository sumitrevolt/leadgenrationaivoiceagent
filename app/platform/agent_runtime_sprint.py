"""Agent Runtime — GTM sprint capabilities (kavya host, 2026-07-31).

================================================================================

Teeno already-deployed sprint actions (``app.agents.sprint_actions``) ko Agent
Runtime ke under ek governed one-shot surface pe laata hai. Host = **kavya**
(existing Wave-A GREEN L0 read-only pilot) — naya persona/agent nahi banta, isliye
31-agent canonical invariant intact. Runtime gate = ``OPS_HEALTH_AGENT`` (kavya ka
``primary_flag``, already in automation-flags registry); scheduler ka gate alag
(``OPS_WATCHDOG``) — ye flag sirf RUNTIME dispatch unlock karta hai, koi scheduled
work auto-start nahi hota.

Risk honesty: teeno actions ``side_effect="none"`` — draft / brief / internal
re-dispatch only, koi customer contact send nahi. ``WHATSAPP_AUTO_SEND``,
``REPLY_AUTO_SEND``, ``AUTO_EMAIL_OUTREACH``, ``PLATFORM_DIAL_DAILY`` untouched.

Kavya's contract ``prohibited=("mutate_infra", "customer_contact")`` — teeno
actions inhe violate nahi karte (draft save / brief generate / job heartbeat
re-dispatch = internal, bounded). ``counts_contact=False`` — koi customer touch
nahi.

Import-safe; ``ensure_sprint_registered()`` idempotent.
"""

from __future__ import annotations

from typing import Any

from app.platform.agent_runtime import AgentCapability, AgentExecutionContext, register_capability
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Host pilot: kavya (Wave-A GREEN L0). Runtime primary_flag = OPS_HEALTH_AGENT.
_HOST_AGENT = "kavya"


# --------------------------------------------------------------------------- #
# Adapters — sprint_actions functions ko AgentExecutionContext-shaped caps
# --------------------------------------------------------------------------- #
async def kavya_dialer_sprint_prep(ctx: AgentExecutionContext) -> dict[str, Any]:
    """Dialer sprint prep briefs (read-only) — untapped phones ka prep."""
    from app.agents import sprint_actions

    limit = int(ctx.task.payload.get("limit") or 3)
    out = await sprint_actions.dialer_sprint_prep(limit=limit)
    if out.get("ok"):
        ctx.add_usage(api_calls=int(out.get("prepped") or 0))
    return out


async def kavya_hot_wa_draft(ctx: AgentExecutionContext) -> dict[str, Any]:
    """Hot Queue warm leads ke WhatsApp reply DRAFTS (draft-only, ban-safe)."""
    from app.agents import sprint_actions

    limit = int(ctx.task.payload.get("limit") or 5)
    out = await sprint_actions.hot_wa_draft(limit=limit)
    if out.get("ok"):
        ctx.add_usage(api_calls=int(out.get("drafted") or 0))
    return out


async def kavya_job_heal_sweep(ctx: AgentExecutionContext) -> dict[str, Any]:
    """Stale scheduled-job heartbeats detect + bounded re-dispatch (internal)."""
    from app.agents import sprint_actions

    max_jobs = int(ctx.task.payload.get("max_jobs") or 3)
    return await sprint_actions.job_heal_sweep(max_jobs=max_jobs)


# --------------------------------------------------------------------------- #
# Registration (idempotent)
# --------------------------------------------------------------------------- #
def ensure_sprint_registered() -> None:
    """Idempotent — register_capability is a plain keyed overwrite."""
    register_capability(
        AgentCapability(
            agent_id=_HOST_AGENT,
            action="dialer_sprint_prep",
            fn=kavya_dialer_sprint_prep,
            side_effect="none",
            tenant_scoped=False,
            requires_approval=False,
            counts_contact=False,
            description=(
                "Dialer sprint prep briefs for untapped prospect phones — "
                "read-only, no call/message (GREEN L0)"
            ),
        )
    )
    register_capability(
        AgentCapability(
            agent_id=_HOST_AGENT,
            action="hot_wa_draft",
            fn=kavya_hot_wa_draft,
            side_effect="none",
            tenant_scoped=False,
            requires_approval=False,
            counts_contact=False,
            description=(
                "Hot Queue warm-lead WhatsApp reply drafts — draft-only, "
                "human 1-click send, no auto-send (GREEN L0)"
            ),
        )
    )
    register_capability(
        AgentCapability(
            agent_id=_HOST_AGENT,
            action="job_heal_sweep",
            fn=kavya_job_heal_sweep,
            side_effect="none",
            tenant_scoped=False,
            requires_approval=False,
            counts_contact=False,
            description=(
                "Stale scheduled-job heartbeats detect + bounded re-dispatch "
                "(RUN_DUE_EXCLUDE honored) (GREEN L0)"
            ),
        )
    )


__all__ = [
    "ensure_sprint_registered",
    "kavya_dialer_sprint_prep",
    "kavya_hot_wa_draft",
    "kavya_job_heal_sweep",
]
