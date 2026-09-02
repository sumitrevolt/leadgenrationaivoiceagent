"""Central Agent OS → OmniRoute routing + governance policy (ADR-109).

Code = truth for admin runbooks and `scripts/gen_agent_os_specs.py`.
OmniRoute remains double-gated (`OMNIROUTE_ENABLED` + `OMNIROUTE_AGENTS`) and
INERT by default. Voice/realtime and billing/compliance agents never get an
OmniRoute task — they stay on the existing free_ai / deterministic paths.

Privacy rule: OmniRoute only admits INTERNAL_SANITIZED (see omniroute_client
`_TASK_ROUTES`). Agents marked CUSTOMER_SENSITIVE / PROHIBITED_EXTERNAL have
`omniroute_task=None` so they cannot be routed even if flags flip.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Task routes that exist in app.platform.omniroute_client._TASK_ROUTES
OMNIROUTE_TASK_AGENT_OPS = "leadgen.agent_ops"
OMNIROUTE_TASK_CODING = "leadgen.coding_primary"
OMNIROUTE_TASK_REPO = "leadgen.repo_analysis"
OMNIROUTE_TASK_TEST = "leadgen.test_generation"

PRIVACY_INTERNAL = "INTERNAL_SANITIZED"
PRIVACY_CUSTOMER = "CUSTOMER_SENSITIVE"
PRIVACY_PROHIBITED = "PROHIBITED_EXTERNAL"
PRIVACY_LOCAL = "SENSITIVE_LOCAL_ONLY"


@dataclass(frozen=True)
class AgentRoutePolicy:
    """Per-agent operating + routing contract (operator-visible, code-enforced where wired)."""

    category: str
    omniroute_task: str | None
    privacy_class: str
    may_write_production_data: bool
    may_contact_customers: bool
    requires_human_approval_before_publish: bool
    may_use_free_models: bool
    auto_run_allowed: bool
    max_retries: int
    timeout_seconds: int
    queue: str
    notes: str = ""


# Product-level defaults — overridden per-agent below when needed.
_PRODUCT_DEFAULTS: dict[str, AgentRoutePolicy] = {
    "voice": AgentRoutePolicy(
        category="voice_calling",
        omniroute_task=None,  # voice hot-path + transcripts stay off OmniRoute
        privacy_class=PRIVACY_CUSTOMER,
        may_write_production_data=False,
        may_contact_customers=True,
        requires_human_approval_before_publish=False,
        may_use_free_models=True,
        auto_run_allowed=True,
        max_retries=2,
        timeout_seconds=30,
        queue="celery",
        notes="Realtime/voice never uses OmniRoute (ADR-108). free_ai chain only.",
    ),
    "marketing": AgentRoutePolicy(
        category="content_generation",
        omniroute_task=OMNIROUTE_TASK_AGENT_OPS,
        privacy_class=PRIVACY_INTERNAL,
        may_write_production_data=True,
        may_contact_customers=False,
        requires_human_approval_before_publish=True,
        may_use_free_models=True,
        auto_run_allowed=True,
        max_retries=2,
        timeout_seconds=45,
        queue="celery",
        notes="Bulk LLM may try OmniRoute when double-gated; publish still needs approval.",
    ),
    "platform": AgentRoutePolicy(
        category="admin_operations",
        omniroute_task=OMNIROUTE_TASK_AGENT_OPS,
        privacy_class=PRIVACY_INTERNAL,
        may_write_production_data=False,
        may_contact_customers=False,
        requires_human_approval_before_publish=False,
        may_use_free_models=True,
        auto_run_allowed=True,
        max_retries=2,
        timeout_seconds=45,
        queue="celery",
        notes="Ops digests/sanitized analysis only; no customer PII to OmniRoute.",
    ),
}

# Explicit overrides — every STAFF key should resolve via product default or here.
_AGENT_OVERRIDES: dict[str, AgentRoutePolicy] = {
    "manager": AgentRoutePolicy(
        category="admin_operations",
        omniroute_task=OMNIROUTE_TASK_AGENT_OPS,
        privacy_class=PRIVACY_INTERNAL,
        may_write_production_data=False,
        may_contact_customers=False,
        requires_human_approval_before_publish=False,
        may_use_free_models=True,
        auto_run_allowed=True,
        max_retries=2,
        timeout_seconds=30,
        queue="celery",
        notes="Supervisor dispatch; OmniRoute optional for bulk reasoning only.",
    ),
    "swara": _PRODUCT_DEFAULTS["voice"],
    "ananya": AgentRoutePolicy(
        category="voice_calling",
        omniroute_task=None,
        privacy_class=PRIVACY_CUSTOMER,
        may_write_production_data=True,
        may_contact_customers=True,
        requires_human_approval_before_publish=False,
        may_use_free_models=True,
        auto_run_allowed=True,
        max_retries=2,
        timeout_seconds=30,
        queue="celery",
        notes="Booking writes CRM state; OmniRoute forbidden.",
    ),
    "riya": _PRODUCT_DEFAULTS["voice"],
    "arjun": AgentRoutePolicy(
        category="voice_qa",
        omniroute_task=None,
        privacy_class=PRIVACY_CUSTOMER,
        may_write_production_data=False,
        may_contact_customers=False,
        requires_human_approval_before_publish=False,
        may_use_free_models=True,
        auto_run_allowed=True,
        max_retries=2,
        timeout_seconds=60,
        queue="celery",
        notes="Call QA may see transcripts — keep on free_ai, never OmniRoute.",
    ),
    "meera": AgentRoutePolicy(
        category="training",
        omniroute_task=None,
        privacy_class=PRIVACY_CUSTOMER,
        may_write_production_data=False,
        may_contact_customers=False,
        requires_human_approval_before_publish=False,
        may_use_free_models=True,
        auto_run_allowed=True,
        max_retries=2,
        timeout_seconds=60,
        queue="celery",
    ),
    "lekha": AgentRoutePolicy(
        category="reporting",
        omniroute_task=None,
        privacy_class=PRIVACY_CUSTOMER,
        may_write_production_data=False,
        may_contact_customers=False,
        requires_human_approval_before_publish=False,
        may_use_free_models=True,
        auto_run_allowed=True,
        max_retries=2,
        timeout_seconds=45,
        queue="celery",
        notes="KPIs from call data — no OmniRoute.",
    ),
    "raksha": AgentRoutePolicy(
        category="customer_success",
        omniroute_task=None,
        privacy_class=PRIVACY_CUSTOMER,
        may_write_production_data=True,
        may_contact_customers=True,
        requires_human_approval_before_publish=False,
        may_use_free_models=True,
        auto_run_allowed=True,
        max_retries=1,
        timeout_seconds=30,
        queue="celery",
        notes="Human escalation — live call path, OmniRoute forbidden.",
    ),
    "tara": AgentRoutePolicy(
        category="monitoring",
        omniroute_task=None,
        privacy_class=PRIVACY_LOCAL,
        may_write_production_data=False,
        may_contact_customers=False,
        requires_human_approval_before_publish=False,
        may_use_free_models=True,
        auto_run_allowed=True,
        max_retries=2,
        timeout_seconds=30,
        queue="celery",
        notes="Voice infra watchdog — local/deterministic preferred.",
    ),
    "dev": AgentRoutePolicy(
        category="reporting",
        omniroute_task=OMNIROUTE_TASK_AGENT_OPS,
        privacy_class=PRIVACY_INTERNAL,
        may_write_production_data=True,
        may_contact_customers=False,
        requires_human_approval_before_publish=False,
        may_use_free_models=True,
        auto_run_allowed=True,
        max_retries=2,
        timeout_seconds=45,
        queue="celery",
    ),
    "rohan": AgentRoutePolicy(
        category="lead_qualification",
        omniroute_task=OMNIROUTE_TASK_AGENT_OPS,
        privacy_class=PRIVACY_INTERNAL,
        may_write_production_data=True,
        may_contact_customers=False,
        requires_human_approval_before_publish=False,
        may_use_free_models=True,
        auto_run_allowed=True,
        max_retries=2,
        timeout_seconds=45,
        queue="celery",
        notes="Lead lists must be masked before any OmniRoute call.",
    ),
    "isha": AgentRoutePolicy(
        category="content_generation",
        omniroute_task=OMNIROUTE_TASK_AGENT_OPS,
        privacy_class=PRIVACY_INTERNAL,
        may_write_production_data=True,
        may_contact_customers=False,
        requires_human_approval_before_publish=True,
        may_use_free_models=True,
        auto_run_allowed=True,
        max_retries=2,
        timeout_seconds=45,
        queue="celery",
    ),
    "ravi": AgentRoutePolicy(
        category="content_generation",
        omniroute_task=OMNIROUTE_TASK_AGENT_OPS,
        privacy_class=PRIVACY_INTERNAL,
        may_write_production_data=True,
        may_contact_customers=False,
        requires_human_approval_before_publish=True,
        may_use_free_models=True,
        auto_run_allowed=True,
        max_retries=2,
        timeout_seconds=45,
        queue="celery",
    ),
    "neha": AgentRoutePolicy(
        category="pipeline_ops",
        omniroute_task=OMNIROUTE_TASK_AGENT_OPS,
        privacy_class=PRIVACY_INTERNAL,
        may_write_production_data=True,
        may_contact_customers=False,
        requires_human_approval_before_publish=False,
        may_use_free_models=True,
        auto_run_allowed=True,
        max_retries=2,
        timeout_seconds=45,
        queue="celery",
    ),
    "kiran": AgentRoutePolicy(
        category="outreach",
        omniroute_task=OMNIROUTE_TASK_AGENT_OPS,
        privacy_class=PRIVACY_INTERNAL,
        may_write_production_data=True,
        may_contact_customers=False,
        requires_human_approval_before_publish=True,
        may_use_free_models=True,
        auto_run_allowed=True,
        max_retries=2,
        timeout_seconds=45,
        queue="celery",
    ),
    "priya": AgentRoutePolicy(
        category="follow_up",
        omniroute_task=None,
        privacy_class=PRIVACY_CUSTOMER,
        may_write_production_data=True,
        may_contact_customers=False,
        requires_human_approval_before_publish=False,
        may_use_free_models=True,
        auto_run_allowed=True,
        max_retries=2,
        timeout_seconds=30,
        queue="celery",
        notes="CRM sync may carry PII — OmniRoute forbidden.",
    ),
    "zara": AgentRoutePolicy(
        category="social_media",
        omniroute_task=OMNIROUTE_TASK_AGENT_OPS,
        privacy_class=PRIVACY_INTERNAL,
        may_write_production_data=True,
        may_contact_customers=True,
        requires_human_approval_before_publish=True,
        may_use_free_models=True,
        auto_run_allowed=True,
        max_retries=2,
        timeout_seconds=45,
        queue="celery",
        notes="Publish path is approval-gated (SOCIAL_ENGINE + admin confirm).",
    ),
    "anika": AgentRoutePolicy(
        category="follow_up",
        omniroute_task=OMNIROUTE_TASK_AGENT_OPS,
        privacy_class=PRIVACY_INTERNAL,
        may_write_production_data=True,
        may_contact_customers=False,
        requires_human_approval_before_publish=True,
        may_use_free_models=True,
        auto_run_allowed=True,
        max_retries=2,
        timeout_seconds=45,
        queue="celery",
    ),
    "ira": AgentRoutePolicy(
        category="customer_onboarding",
        omniroute_task=OMNIROUTE_TASK_AGENT_OPS,
        privacy_class=PRIVACY_INTERNAL,
        may_write_production_data=True,
        may_contact_customers=False,
        requires_human_approval_before_publish=True,
        may_use_free_models=True,
        auto_run_allowed=True,
        max_retries=2,
        timeout_seconds=45,
        queue="celery",
    ),
    "kavya": AgentRoutePolicy(
        category="monitoring",
        omniroute_task=OMNIROUTE_TASK_AGENT_OPS,
        privacy_class=PRIVACY_INTERNAL,
        may_write_production_data=False,
        may_contact_customers=False,
        requires_human_approval_before_publish=False,
        may_use_free_models=True,
        auto_run_allowed=True,
        max_retries=2,
        timeout_seconds=30,
        queue="celery",
    ),
    "hermes": AgentRoutePolicy(
        category="recovery_incident",
        omniroute_task=OMNIROUTE_TASK_REPO,
        privacy_class=PRIVACY_INTERNAL,
        may_write_production_data=False,
        may_contact_customers=False,
        requires_human_approval_before_publish=False,
        may_use_free_models=True,
        auto_run_allowed=True,
        max_retries=2,
        timeout_seconds=45,
        queue="celery",
        notes="Infra watchdog; repo_analysis route if OmniRoute agents enabled.",
    ),
    "nikhil": AgentRoutePolicy(
        category="billing",
        omniroute_task=None,
        privacy_class=PRIVACY_PROHIBITED,
        may_write_production_data=False,
        may_contact_customers=False,
        requires_human_approval_before_publish=False,
        may_use_free_models=True,
        auto_run_allowed=True,
        max_retries=1,
        timeout_seconds=30,
        queue="celery",
        notes="Revenue digests — billing/payment data never to OmniRoute.",
    ),
    "vikram": AgentRoutePolicy(
        category="admin_operations",
        omniroute_task=OMNIROUTE_TASK_CODING,
        privacy_class=PRIVACY_INTERNAL,
        may_write_production_data=False,
        may_contact_customers=False,
        requires_human_approval_before_publish=True,
        may_use_free_models=True,
        auto_run_allowed=False,
        max_retries=1,
        timeout_seconds=60,
        queue="celery",
        notes="Code upgrader gated; human review before any apply.",
    ),
    "guru": AgentRoutePolicy(
        category="training",
        omniroute_task=OMNIROUTE_TASK_AGENT_OPS,
        privacy_class=PRIVACY_INTERNAL,
        may_write_production_data=True,
        may_contact_customers=False,
        requires_human_approval_before_publish=False,
        may_use_free_models=True,
        auto_run_allowed=True,
        max_retries=2,
        timeout_seconds=60,
        queue="heavy",
    ),
    "pranav": AgentRoutePolicy(
        category="monitoring",
        omniroute_task=OMNIROUTE_TASK_REPO,
        privacy_class=PRIVACY_INTERNAL,
        may_write_production_data=False,
        may_contact_customers=False,
        requires_human_approval_before_publish=False,
        may_use_free_models=True,
        auto_run_allowed=True,
        max_retries=2,
        timeout_seconds=45,
        queue="celery",
    ),
    "vidya": AgentRoutePolicy(
        category="billing",
        omniroute_task=None,
        privacy_class=PRIVACY_PROHIBITED,
        may_write_production_data=False,
        may_contact_customers=False,
        requires_human_approval_before_publish=False,
        may_use_free_models=True,
        auto_run_allowed=True,
        max_retries=1,
        timeout_seconds=30,
        queue="celery",
        notes="FinOps — cost/margin data stays off OmniRoute.",
    ),
    "arnav": AgentRoutePolicy(
        category="compliance_privacy",
        omniroute_task=None,
        privacy_class=PRIVACY_PROHIBITED,
        may_write_production_data=False,
        may_contact_customers=False,
        requires_human_approval_before_publish=False,
        may_use_free_models=True,
        auto_run_allowed=True,
        max_retries=1,
        timeout_seconds=45,
        queue="celery",
        notes="Security/compliance posture — local/deterministic only.",
    ),
    "kabir": AgentRoutePolicy(
        category="recovery_incident",
        omniroute_task=None,
        privacy_class=PRIVACY_LOCAL,
        may_write_production_data=False,
        may_contact_customers=False,
        requires_human_approval_before_publish=False,
        may_use_free_models=True,
        auto_run_allowed=True,
        max_retries=1,
        timeout_seconds=45,
        queue="celery",
        notes="DBRE — schema/ops sensitive; no OmniRoute.",
    ),
    "diya": AgentRoutePolicy(
        category="testing_qa",
        omniroute_task=None,
        privacy_class=PRIVACY_CUSTOMER,
        may_write_production_data=False,
        may_contact_customers=False,
        requires_human_approval_before_publish=False,
        may_use_free_models=True,
        auto_run_allowed=True,
        max_retries=2,
        timeout_seconds=45,
        queue="celery",
        notes="Data-integrity may touch tenant rows — no OmniRoute.",
    ),
    "aryan": AgentRoutePolicy(
        category="testing_qa",
        omniroute_task=OMNIROUTE_TASK_TEST,
        privacy_class=PRIVACY_INTERNAL,
        may_write_production_data=False,
        may_contact_customers=False,
        requires_human_approval_before_publish=False,
        may_use_free_models=True,
        auto_run_allowed=True,
        max_retries=2,
        timeout_seconds=60,
        queue="celery",
    ),
    "arya": AgentRoutePolicy(
        category="admin_operations",
        omniroute_task=OMNIROUTE_TASK_REPO,
        privacy_class=PRIVACY_INTERNAL,
        may_write_production_data=False,
        may_contact_customers=False,
        requires_human_approval_before_publish=False,
        may_use_free_models=True,
        auto_run_allowed=True,
        max_retries=2,
        timeout_seconds=45,
        queue="celery",
    ),
}


def get_agent_policy(agent_key: str, product: str | None = None) -> AgentRoutePolicy:
    """Resolve routing/governance for one STAFF key."""
    key = (agent_key or "").strip().lower()
    if key in _AGENT_OVERRIDES:
        return _AGENT_OVERRIDES[key]
    if product and product in _PRODUCT_DEFAULTS:
        return _PRODUCT_DEFAULTS[product]
    return AgentRoutePolicy(
        category="admin_operations",
        omniroute_task=None,
        privacy_class=PRIVACY_PROHIBITED,
        may_write_production_data=False,
        may_contact_customers=False,
        requires_human_approval_before_publish=True,
        may_use_free_models=True,
        auto_run_allowed=False,
        max_retries=0,
        timeout_seconds=15,
        queue="celery",
        notes="Unknown agent — fail-closed (no OmniRoute, no auto-run).",
    )


def omniroute_allowed_for_agent(agent_key: str, product: str | None = None) -> bool:
    """True only if policy assigns an OmniRoute task (flags still required at runtime)."""
    policy = get_agent_policy(agent_key, product)
    return policy.omniroute_task is not None and policy.privacy_class == PRIVACY_INTERNAL


def agent_route_table() -> dict[str, dict[str, Any]]:
    """Operator-visible map: agent_key → policy fields (no secrets)."""
    # Prefer override keys; product defaults fill gaps when specs regenerate from STAFF.
    keys = sorted(_AGENT_OVERRIDES.keys())
    out: dict[str, dict[str, Any]] = {}
    for key in keys:
        p = _AGENT_OVERRIDES[key]
        out[key] = {
            "category": p.category,
            "omniroute_task": p.omniroute_task,
            "privacy_class": p.privacy_class,
            "may_write_production_data": p.may_write_production_data,
            "may_contact_customers": p.may_contact_customers,
            "requires_human_approval_before_publish": p.requires_human_approval_before_publish,
            "may_use_free_models": p.may_use_free_models,
            "auto_run_allowed": p.auto_run_allowed,
            "max_retries": p.max_retries,
            "timeout_seconds": p.timeout_seconds,
            "queue": p.queue,
            "omniroute_eligible": p.omniroute_task is not None
            and p.privacy_class == PRIVACY_INTERNAL,
            "notes": p.notes,
        }
    return out


def policy_markdown_block(agent_key: str, product: str) -> list[str]:
    """Lines for agent-os spec regeneration."""
    p = get_agent_policy(agent_key, product)
    eligible = "yes" if (p.omniroute_task and p.privacy_class == PRIVACY_INTERNAL) else "no"
    return [
        "",
        "## Routing & governance (app/platform/agent_os_routing.py)",
        "",
        f"- **Category:** `{p.category}`",
        f"- **OmniRoute task:** `{p.omniroute_task or 'NONE (forbidden)'}`",
        f"- **Privacy class:** `{p.privacy_class}`",
        f"- **OmniRoute eligible:** {eligible} (still needs `OMNIROUTE_ENABLED` + `OMNIROUTE_AGENTS` + key)",
        f"- **May write production data:** {'yes' if p.may_write_production_data else 'no'}",
        f"- **May contact customers:** {'yes' if p.may_contact_customers else 'no'}",
        f"- **Human approval before publish:** {'yes' if p.requires_human_approval_before_publish else 'no'}",
        f"- **Free models OK:** {'yes' if p.may_use_free_models else 'no'}",
        f"- **Auto-run allowed:** {'yes' if p.auto_run_allowed else 'no'}",
        f"- **Max retries / timeout / queue:** {p.max_retries} / {p.timeout_seconds}s / `{p.queue}`",
        f"- **Notes:** {p.notes or '—'}",
        "",
        "Disable one agent: uska feature gate env unset karo (ya Office HQ pause) — poora system band mat karo.",
        "",
    ]
