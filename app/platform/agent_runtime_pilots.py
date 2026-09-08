"""
Agent Runtime — Phase-B pilot capabilities (kavya / isha / zara).
=================================================================

3 pilot agents, 3 alag risk-profiles, sab EXISTING engines reuse karte hain
(koi naya executor/queue nahi):

  1. kavya  — GREEN L0, deterministic: read-only operational health check
              (automation_health.health() — zero side effects, zero LLM).
  2. isha   — GREEN L1, genuine reasoning agent: DRAFT/PROPOSAL output only.
              LLM sirf tab jab AGENT_RUNTIME_LLM=1 (free stack, graceful
              deterministic fallback) — kabhi publish nahi karta.
  3. zara   — AMBER L2, approval-controlled: sirf ALREADY-APPROVED content ko
              existing social_engine queue me hand-off karta hai. Approval gate
              runtime enforce karta hai (requires_approval=True); engine flag
              off ho to honest SkipTask — fake publish kabhi nahi.

Voice-specific code yahan NAHI hai (STT/TTS/streaming/barge-in/DND-window =
sirf voice agents ke module). RED agents (swara/ananya) yahan register hi
nahi hote — runtime unhe lane-level pe block karta hai.

Import-safe; ensure_pilots_registered() idempotent.
"""

from __future__ import annotations

import os
from typing import Any

from app.platform.agent_runtime import (
    AgentCapability,
    AgentExecutionContext,
    SkipTask,
    register_capability,
)
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


# --------------------------------------------------------------------------- #
# 1. Kavya — GREEN, L0_OBSERVE, deterministic read-only ops check
# --------------------------------------------------------------------------- #
async def kavya_ops_health_check(ctx: AgentExecutionContext) -> dict[str, Any]:
    """Read-only: automation_health rollup + queue depth. Mutates NOTHING."""
    from app.platform import automation_health

    h = automation_health.health()
    ctx.add_usage(api_calls=1)
    return {
        "check": "ops_health_check",
        "read_only": True,
        "status": h.get("status"),
        "ok": h.get("ok"),
        "overdue": h.get("overdue") or [],
        "never_ran": h.get("never_ran") or [],
        "queue": h.get("queue") or {},
        "dead_tasks_present": bool(h.get("dead_tasks_present")),
    }


# --------------------------------------------------------------------------- #
# 2. Isha — GREEN, L1_RECOMMEND, reasoning: draft/proposal ONLY (no publish)
# --------------------------------------------------------------------------- #
async def isha_draft_content_brief(ctx: AgentExecutionContext) -> dict[str, Any]:
    """Content brief PROPOSAL — human review required, koi side effect nahi.

    LLM path sirf AGENT_RUNTIME_LLM=1 pe (free providers via free_ai), warna
    deterministic template. Dono case me output = draft, publish kabhi nahi.
    """
    topic = str(ctx.task.payload.get("topic") or "local business marketing").strip()[:200]
    business = str(ctx.task.payload.get("business_name") or ctx.tenant_id or "client").strip()[:100]

    draft_text = ""
    generator = "deterministic_template"
    if (os.getenv("AGENT_RUNTIME_LLM") or "").strip().lower() in ("1", "true", "yes"):
        try:
            from app.voice_agent.free_ai import chat as _chat

            draft_text = await _chat(
                "You draft short Hinglish marketing briefs. Draft/proposal only — never publish.",
                [
                    {
                        "role": "user",
                        "content": (
                            f"Draft a short Hinglish social-post brief for '{business}' "
                            f"about: {topic}. 3 bullet hooks + 1 CTA. Draft only."
                        ),
                    }
                ],
                max_tokens=220,
            )
            if draft_text:
                generator = "llm_free_stack"
                ctx.add_usage(cost_inr=0.5, api_calls=1)
        except Exception as e:
            logger.debug("[agent_runtime_pilots] isha LLM fallback: %s", e)
            draft_text = ""
    if not draft_text:
        draft_text = (
            f"BRIEF (draft): {business} — {topic}\n"
            f"- Hook 1: local problem → aapka solution\n"
            f"- Hook 2: social proof / before-after\n"
            f"- Hook 3: limited-time offer\n"
            f"- CTA: WhatsApp par message karo"
        )
    return {
        "proposal": {
            "kind": "content_brief",
            "business": business,
            "topic": topic,
            "draft": draft_text[:2000],
            "generator": generator,
        },
        "requires_human_review": True,
        "published": False,
        "customer_contacted": False,
    }


# --------------------------------------------------------------------------- #
# 3. Zara — AMBER, L2, approval-controlled publish HAND-OFF (existing engine)
# --------------------------------------------------------------------------- #
async def zara_publish_approved_content(ctx: AgentExecutionContext) -> dict[str, Any]:
    """Sirf ALREADY-APPROVED content_approval record ko existing social_engine
    queue me daalta hai. Approval verification runtime gate pe ho chuki hoti
    hai (requires_approval=True → approval_ref approved). Engine off = honest
    skip; executor = existing social_drain (koi duplicate publisher nahi)."""
    from app.marketing import content_approval

    approval_id = str(ctx.task.approval_ref or "").strip()
    rec = content_approval._by_id_for_client(ctx.tenant_id, approval_id)
    if not rec or str(rec.get("status") or "") != "approved":
        # Defense-in-depth: runtime gate ke baad record badla ho to fail-closed.
        raise PermissionError(f"approval '{approval_id}' not approved for tenant")

    try:
        from app.social_engine import engine as social_engine

        engine_on = bool(social_engine.enabled())
    except Exception:
        engine_on = False
    if not engine_on:
        raise SkipTask("social_engine_disabled")

    job_ids = social_engine.enqueue_publish(
        ctx.tenant_id,
        caption=str(rec.get("caption") or "")[:2200],
        media_url=str(rec.get("media_url") or ""),
        media_type=str(rec.get("media_type") or "image"),
    )
    ctx.add_usage(api_calls=1)
    return {
        "handed_off": bool(job_ids),
        "queue_job_ids": job_ids,
        "approval_id": approval_id,
        "executor": "social_engine.social_drain (existing)",
        "published_directly": False,
    }


# --------------------------------------------------------------------------- #
# Registration (idempotent)
# --------------------------------------------------------------------------- #
def ensure_pilots_registered() -> None:
    """Idempotent — register_capability is a plain keyed overwrite, so calling
    this repeatedly is cheap and always leaves the 3 pilots wired."""
    register_capability(
        AgentCapability(
            agent_id="kavya",
            action="ops_health_check",
            fn=kavya_ops_health_check,
            side_effect="none",
            tenant_scoped=False,
            description="Read-only automation/dead-man health rollup (GREEN L0)",
        )
    )
    register_capability(
        AgentCapability(
            agent_id="isha",
            action="draft_content_brief",
            fn=isha_draft_content_brief,
            side_effect="none",
            tenant_scoped=True,
            description="Content brief draft/proposal — human review required (GREEN L1, reasoning)",
        )
    )
    register_capability(
        AgentCapability(
            agent_id="zara",
            action="publish_approved_content",
            fn=zara_publish_approved_content,
            side_effect="customer",
            tenant_scoped=True,
            requires_approval=True,
            description="Approved content → existing social_engine queue hand-off (AMBER, approval-gated)",
        )
    )


__all__ = [
    "ensure_pilots_registered",
    "kavya_ops_health_check",
    "isha_draft_content_brief",
    "zara_publish_approved_content",
]
