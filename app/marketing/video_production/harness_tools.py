"""Register Video Production Cell capabilities in the canonical harness registry.

Shadow-friendly: definitions only; enforcement gated by VIDEO_HARNESS_ENFORCE.
Agents map to existing STAFF (isha / zara / arnav) — no 32nd persona.
"""

from __future__ import annotations

from app.agents.harness.registry import (
    REGISTRY,
    AuthorityClass,
    RiskLane,
    SideEffectClass,
    ToolDefinition,
)

_OWNERS_GREEN = frozenset({"isha", "manager", "nikhil"})
_OWNERS_PUBLISH = frozenset({"zara", "manager"})
_OWNERS_COMPLIANCE = frozenset({"arnav", "isha", "manager"})
_TENANTS = frozenset({"*", "__system__"})


def _reg(**kwargs) -> None:
    try:
        REGISTRY.register(ToolDefinition(**kwargs))
    except Exception:
        pass


def register_video_tools() -> None:
    """Idempotent registration of video.* tools."""
    _reg(
        name="video.brief.create",
        version="1.0.0",
        description="Create daily video brief from tenant brand profile (no fabrication).",
        input_schema={
            "type": "object",
            "properties": {
                "client_id": {"type": "string", "maxLength": 60},
                "content_date": {"type": "string", "maxLength": 32},
            },
            "required": ["client_id"],
            "additionalProperties": False,
        },
        output_schema={"type": "object"},
        risk_class=RiskLane.GREEN,
        side_effect_class=SideEffectClass.WRITE_LOCAL,
        authority=AuthorityClass.INTERNAL_AUTONOMOUS,
        allowed_agents=_OWNERS_GREEN,
        allowed_tenant_scopes=_TENANTS,
        requires_idempotency=True,
        timeout_seconds=30,
        cost_class="free",
        executor_ref="app.marketing.video_production.cell.create_daily_brief",
        enabled_by_default=True,
    )
    _reg(
        name="video.script.write",
        version="1.0.0",
        description="Write hook/script/CTA/caption from brief; never invent prices.",
        input_schema={
            "type": "object",
            "properties": {"brief": {"type": "object"}},
            "required": ["brief"],
            "additionalProperties": False,
        },
        risk_class=RiskLane.GREEN,
        side_effect_class=SideEffectClass.NONE,
        authority=AuthorityClass.INTERNAL_AUTONOMOUS,
        allowed_agents=_OWNERS_GREEN,
        allowed_tenant_scopes=_TENANTS,
        timeout_seconds=60,
        cost_class="free",
        executor_ref="app.marketing.video_production.cell.write_script",
        enabled_by_default=True,
    )
    _reg(
        name="video.render.social",
        version="1.0.0",
        description="Local FFmpeg render via video_pipeline; queues customer review.",
        input_schema={
            "type": "object",
            "properties": {
                "client_id": {"type": "string", "maxLength": 60},
                "note": {"type": "string", "maxLength": 500},
                "revision": {"type": "integer"},
                "ratio": {"type": "string", "maxLength": 8},
            },
            "required": ["client_id"],
            "additionalProperties": False,
        },
        risk_class=RiskLane.GREEN,
        side_effect_class=SideEffectClass.WRITE_TENANT,
        authority=AuthorityClass.INTERNAL_AUTONOMOUS,
        allowed_agents=_OWNERS_GREEN,
        allowed_tenant_scopes=_TENANTS,
        requires_idempotency=True,
        timeout_seconds=300,
        cost_class="free",
        executor_ref="app.marketing.video_production.cell.render_and_queue_review",
        enabled_by_default=True,
    )
    _reg(
        name="video.qa.run",
        version="1.0.0",
        description="FFmpeg/ffprobe automated QA before customer review.",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "maxLength": 500},
                "expected_slides": {"type": "integer"},
                "ratio": {"type": "string", "maxLength": 8},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
        risk_class=RiskLane.GREEN,
        side_effect_class=SideEffectClass.READ_ONLY,
        authority=AuthorityClass.INTERNAL_AUTONOMOUS,
        allowed_agents=_OWNERS_COMPLIANCE | _OWNERS_GREEN,
        allowed_tenant_scopes=_TENANTS,
        timeout_seconds=60,
        cost_class="free",
        executor_ref="app.marketing.video_pipeline._qa_check",
        enabled_by_default=True,
    )
    _reg(
        name="video.review.whatsapp_send",
        version="1.0.0",
        description="Send WhatsApp video preview (opt-in, suppression, quiet hours).",
        input_schema={
            "type": "object",
            "properties": {
                "video_ad_id": {"type": "string", "maxLength": 40},
                "client_id": {"type": "string", "maxLength": 60},
            },
            "required": ["video_ad_id", "client_id"],
            "additionalProperties": False,
        },
        risk_class=RiskLane.AMBER,
        side_effect_class=SideEffectClass.EXTERNAL_SEND,
        authority=AuthorityClass.APPROVAL_REQUIRED,
        allowed_agents=_OWNERS_GREEN,
        allowed_tenant_scopes=_TENANTS,
        requires_approval=True,
        approval_policy="owner_os_amber",
        requires_idempotency=True,
        timeout_seconds=60,
        cost_class="free",
        network_policy="restricted",
        executor_ref="app.marketing.video_production.review_whatsapp.send_review_whatsapp",
        enabled_by_default=True,
    )
    _reg(
        name="video.feedback.ingest",
        version="1.0.0",
        description="Ingest customer WA/dashboard feedback into structured revision tasks.",
        input_schema={
            "type": "object",
            "properties": {
                "from_phone": {"type": "string", "maxLength": 20},
                "text": {"type": "string", "maxLength": 2000},
                "message_id": {"type": "string", "maxLength": 120},
            },
            "required": ["from_phone", "text"],
            "additionalProperties": False,
        },
        risk_class=RiskLane.GREEN,
        side_effect_class=SideEffectClass.WRITE_TENANT,
        authority=AuthorityClass.INTERNAL_AUTONOMOUS,
        allowed_agents=_OWNERS_GREEN,
        allowed_tenant_scopes=_TENANTS,
        requires_idempotency=True,
        timeout_seconds=30,
        cost_class="free",
        executor_ref="app.marketing.video_production.review_whatsapp.ingest_inbound",
        enabled_by_default=True,
    )
    _reg(
        name="video.version.approve",
        version="1.0.0",
        description="Approve exact video version (version-bound).",
        input_schema={
            "type": "object",
            "properties": {
                "video_ad_id": {"type": "string", "maxLength": 40},
                "expected_revision": {"type": "integer"},
            },
            "required": ["video_ad_id"],
            "additionalProperties": False,
        },
        risk_class=RiskLane.AMBER,
        side_effect_class=SideEffectClass.WRITE_TENANT,
        authority=AuthorityClass.APPROVAL_REQUIRED,
        allowed_agents=_OWNERS_GREEN | _OWNERS_PUBLISH,
        allowed_tenant_scopes=_TENANTS,
        requires_approval=True,
        requires_idempotency=True,
        timeout_seconds=30,
        cost_class="free",
        executor_ref="app.marketing.video_production.cell.approve_version",
        enabled_by_default=True,
    )
    _reg(
        name="video.social.schedule",
        version="1.0.0",
        description="Schedule/publish ONLY final-approved version via Postiz/social_engine.",
        input_schema={
            "type": "object",
            "properties": {"video_ad_id": {"type": "string", "maxLength": 40}},
            "required": ["video_ad_id"],
            "additionalProperties": False,
        },
        risk_class=RiskLane.AMBER,
        side_effect_class=SideEffectClass.EXTERNAL_SEND,
        authority=AuthorityClass.APPROVAL_REQUIRED,
        allowed_agents=_OWNERS_PUBLISH,
        allowed_tenant_scopes=_TENANTS,
        requires_approval=True,
        approval_policy="owner_os_amber",
        requires_idempotency=True,
        timeout_seconds=120,
        cost_class="free",
        network_policy="restricted",
        executor_ref="app.marketing.video_production.cell.schedule_approved",
        enabled_by_default=True,
    )


__all__ = ["register_video_tools"]
