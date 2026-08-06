"""Enterprise maturity profiles and bounded context for the 31 STAFF agents.

This is a projection over the existing Agent-OS, not a second control plane.
Every profile is derived from ``agent_registry`` and the runtime capability
factory, then enriched with:

* an agent-private, tenant-scoped memory namespace;
* an agent-private role/tenant knowledge namespace;
* a shared SaaS engineering baseline plus role-specific competencies; and
* the existing budgets, retries, idempotency, kills and escalation contract.

``setup_state`` describes whether the profile is complete.  It deliberately
does NOT mean the agent is live: ``rollout_state`` remains the runtime truth.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

PROFILE_VERSION = "2026-08-06.v1"
CANONICAL_COUNT = 31

COMMON_SAAS_SKILLS: tuple[str, ...] = (
    "tenant-isolation",
    "dpdp-data-minimisation",
    "compliance-fail-closed",
    "idempotency-retry-dlq",
    "observability-evidence",
    "budget-rate-limit",
    "incident-escalation",
    "safe-rollback",
)

_ROLE_SKILLS: dict[str, tuple[str, ...]] = {
    "manager": ("mission-decomposition", "boss-routing", "handoff-verification"),
    "swara": ("consent-aware-conversation", "dnd-trai-gating", "ai-disclosure"),
    "ananya": ("calendar-booking", "consent-aware-reminders", "slot-idempotency"),
    "riya": ("inbound-triage", "safe-department-routing", "message-handoff"),
    "dev": ("tenant-kb-seeding", "rag-grounding", "source-quality"),
    "rohan": ("lead-qualification", "campaign-targeting", "handoff-to-sales"),
    "arjun": ("conversation-qa", "regression-contracts", "failure-reproduction"),
    "meera": ("transcript-analysis", "quality-coaching", "safe-tuning-proposals"),
    "lekha": ("call-kpi-design", "latency-analysis", "quality-trends"),
    "raksha": ("human-escalation", "context-handoff", "availability-truth"),
    "kavya": ("health-monitoring", "provider-readiness", "alert-triage"),
    "hermes": ("infra-diagnostics", "queue-assurance", "backup-readiness"),
    "isha": ("content-strategy", "approval-bound-publishing", "brand-safety"),
    "tara": ("telephony-readiness", "provider-chain-diagnostics", "compliance-posture"),
    "nikhil": ("revenue-assurance", "dunning-analysis", "mrr-integrity"),
    "vikram": ("change-proposals", "test-evidence", "human-gated-core-code"),
    "guru": ("skill-curation", "lesson-quality", "capability-evaluation"),
    "pranav": ("slo-reliability", "incident-response", "capacity-analysis"),
    "vidya": ("finops", "cost-anomaly-detection", "free-tier-governance"),
    "arnav": ("threat-modelling", "secret-safety", "compliance-controls"),
    "kabir": ("database-reliability", "migration-safety", "query-performance"),
    "diya": ("data-quality", "reconciliation", "integrity-guardrails"),
    "aryan": ("dependency-security", "lockfile-discipline", "supply-chain-triage"),
    "arya": ("mcp-contracts", "tool-least-privilege", "connector-observability"),
    "ravi": ("technical-seo", "search-intent", "content-gap-analysis"),
    "neha": ("pipeline-operations", "queue-hygiene", "sla-follow-through"),
    "kiran": ("campaign-experiments", "conversion-analysis", "bounded-optimisation"),
    "priya": ("crm-sync", "identity-reconciliation", "duplicate-prevention"),
    "zara": ("social-scheduling", "approval-bound-send", "channel-safety"),
    "anika": ("cadence-policy", "contact-caps", "suppression-enforcement"),
    "ira": ("journey-orchestration", "state-machine-safety", "lifecycle-handoffs"),
}

_SAFE_ID = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
_PROVISIONED_ROLE_NAMESPACES: set[str] = set()


def _safe_agent(agent_id: str) -> str:
    aid = str(agent_id or "").strip().lower()
    return aid if _SAFE_ID.fullmatch(aid) else ""


def _tenant_token(tenant_id: str) -> str:
    """Opaque stable token; tenant names/PII never become vector namespaces."""
    tid = str(tenant_id or "").strip()
    if not tid:
        return "platform"
    return hashlib.sha256(tid.encode("utf-8")).hexdigest()[:16]


def memory_namespace(agent_id: str, tenant_id: str = "") -> str:
    aid = _safe_agent(agent_id)
    return f"staff/{aid}/tenant/{_tenant_token(tenant_id)}" if aid else ""


def knowledge_namespaces(agent_id: str, tenant_id: str = "") -> dict[str, Any]:
    aid = _safe_agent(agent_id)
    if not aid:
        return {}
    token = _tenant_token(tenant_id)
    return {
        "private": f"staff:{aid}:tenant:{token}",
        "role": f"staff:{aid}:role",
        "shared_read_only": ["okf", "skills"],
        "tenant_required_for_customer_data": True,
    }


def _rollout_by_agent() -> dict[str, dict[str, Any]]:
    try:
        from app.platform.agent_runtime_workforce import (
            ensure_workforce_registered,
            workforce_rollout_state,
        )

        ensure_workforce_registered()
        return {
            str(row.get("agent_id")): row for row in (workforce_rollout_state().get("agents") or [])
        }
    except Exception:
        return {}


def _coordination_profile(agent_id: str, rollout_state: str, lane: str) -> dict[str, Any]:
    """Per-agent projection of the canonical Office/Boss topology."""
    try:
        from app.platform.office_hq import MEMBER_ROOM

        team_id = str(MEMBER_ROOM.get(agent_id) or "")
    except Exception:
        team_id = ""
    is_boss = agent_id == "manager"
    return {
        "ready": bool(team_id),
        "boss": "manager",
        "role": "boss" if is_boss else "worker",
        "team": team_id,
        "routing": "boss_direct" if is_boss else "boss_via_domain_team",
        "decision_authority": "boss_within_agent_contract",
        "owner_required": ["manual_upi_credit_confirmation"],
        "system_hard_gates": [
            "dnd_trai_consent_dpdp",
            "kill_switches_and_budgets",
            "red_lane_and_prohibited_actions",
        ],
        "execution_state": rollout_state,
        "execution_note": (
            "advisory_or_status_only" if lane == "RED" else "subject_to_runtime_rollout_and_policy"
        ),
    }


def profile(
    agent_id: str,
    tenant_id: str = "",
    *,
    _contract: Any = None,
    _rollout: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from app.platform import agent_registry as registry

    aid = _safe_agent(agent_id)
    contract = _contract or (registry.get_contract(aid) if aid else None)
    if contract is None:
        return {"ok": False, "error": "unknown_agent", "agent_id": aid or str(agent_id)}
    rollout = (_rollout if _rollout is not None else _rollout_by_agent().get(aid)) or {}
    role_skills = list(_ROLE_SKILLS.get(aid) or ())
    capabilities = list(rollout.get("capabilities") or ())
    mem_ns = memory_namespace(aid, tenant_id)
    kb_ns = knowledge_namespaces(aid, tenant_id)
    controls = {
        "tenant_isolation": True,
        "kill_switches": list(contract.kill_switches),
        "autonomy": contract.autonomy,
        "lane": contract.lane,
        "default_mode": contract.default_mode,
        "idempotency": contract.idempotency,
        "retry_policy": contract.retry_policy,
        "max_concurrency": contract.max_concurrency,
        "timeout_s": contract.run_timeout_s,
        "cost_budget_inr_day": contract.cost_budget_inr_day,
        "api_calls_day": contract.api_calls_day,
        "customer_contact_cap_day": contract.customer_contact_cap_day,
        "heartbeat_gap_min": contract.heartbeat_gap_min,
        "useful_work_gap_min": contract.useful_work_gap_min,
        "escalation": contract.escalation,
        "test_ref": contract.test_ref,
    }
    coordination = _coordination_profile(
        aid,
        str(rollout.get("rollout_state") or "unknown"),
        str(contract.lane),
    )
    problems: list[str] = []
    if not mem_ns:
        problems.append("missing_memory_namespace")
    if not kb_ns.get("private") or not kb_ns.get("role"):
        problems.append("missing_knowledge_namespace")
    if len(role_skills) < 2:
        problems.append("missing_role_skill_pack")
    if "owner_all_agents" not in contract.kill_switches:
        problems.append("missing_global_kill")
    if not capabilities:
        problems.append("missing_runtime_capability")
    if not coordination.get("ready"):
        problems.append("missing_boss_coordination_route")
    return {
        "ok": not problems,
        "profile_version": PROFILE_VERSION,
        "agent_id": aid,
        "name": contract.name,
        "team": contract.team,
        "title": contract.title,
        "responsibility": contract.responsibility,
        "memory": {
            "namespace": mem_ns,
            "layers": ["working", "episodic", "semantic", "procedural", "prospective", "shared"],
            "private_by_default": True,
            "tenant_required_for_customer_data": True,
            "durable_write_gate": "memory_governance",
        },
        "knowledge": kb_ns,
        "skills": {
            "enterprise_baseline": list(COMMON_SAAS_SKILLS),
            "role_specific": role_skills,
            "runtime_capabilities": capabilities,
        },
        "governance": controls,
        "coordination": coordination,
        "setup_state": "enterprise_profile_ready" if not problems else "incomplete",
        "rollout_state": str(rollout.get("rollout_state") or "unknown"),
        "pilot": bool(rollout.get("pilot")),
        "problems": problems,
    }


def validate_profiles(_profiles: list[dict[str, Any]] | None = None) -> list[str]:
    from app.platform import agent_registry as registry

    problems: list[str] = []
    if _profiles is None:
        contracts = registry.build_registry()
        rollout = _rollout_by_agent()
        profiles = [
            profile(
                aid,
                "validation-tenant",
                _contract=contract,
                _rollout=rollout.get(aid) or {},
            )
            for aid, contract in contracts.items()
        ]
    else:
        profiles = _profiles
    if len(profiles) != CANONICAL_COUNT:
        problems.append(f"profile count {len(profiles)} != canonical {CANONICAL_COUNT}")
    private_kb = [p.get("knowledge", {}).get("private") for p in profiles]
    role_kb = [p.get("knowledge", {}).get("role") for p in profiles]
    mem = [p.get("memory", {}).get("namespace") for p in profiles]
    if len(set(private_kb)) != len(private_kb):
        problems.append("private knowledge namespaces are not unique")
    if len(set(role_kb)) != len(role_kb):
        problems.append("role knowledge namespaces are not unique")
    if len(set(mem)) != len(mem):
        problems.append("memory namespaces are not unique")
    for p in profiles:
        for issue in p.get("problems") or []:
            problems.append(f"{p.get('agent_id')}: {issue}")
    return problems


def portfolio() -> dict[str, Any]:
    from app.platform import agent_registry as registry

    contracts = registry.build_registry()
    rollout = _rollout_by_agent()
    rows = [
        profile(aid, _contract=contract, _rollout=rollout.get(aid) or {})
        for aid, contract in contracts.items()
    ]
    rollout_counts: dict[str, int] = {}
    for row in rows:
        key = str(row.get("rollout_state") or "unknown")
        rollout_counts[key] = rollout_counts.get(key, 0) + 1
    ready = sum(1 for row in rows if row.get("setup_state") == "enterprise_profile_ready")
    problems = validate_profiles(rows)
    try:
        from app.platform.office_hq import coordination_topology

        coordination = coordination_topology()
    except Exception as exc:
        coordination = {"coverage_ok": False, "error": type(exc).__name__}
    if not coordination.get("coverage_ok"):
        problems.append("Boss coordination topology does not cover canonical STAFF")
    return {
        "ok": not problems,
        "profile_version": PROFILE_VERSION,
        "staff_count": len(rows),
        "enterprise_profiles_ready": ready,
        "rollout_counts": rollout_counts,
        "coordination": coordination,
        "claim_note": "Profile-ready is not rollout-live; rollout_state is authoritative.",
        "agents": rows,
        "problems": problems,
    }


def context_enabled() -> bool:
    return str(os.getenv("AGENT_MATURITY_CONTEXT") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _role_document(agent_id: str) -> str:
    p = profile(agent_id)
    if not p.get("ok"):
        return ""
    g = p["governance"]
    return (
        f"Agent: {p['name']} ({p['agent_id']})\nRole: {p['title']}\n"
        f"Responsibility: {p['responsibility']}\n"
        f"Role skills: {', '.join(p['skills']['role_specific'])}\n"
        f"Enterprise baseline: {', '.join(p['skills']['enterprise_baseline'])}\n"
        f"Autonomy: {g['autonomy']} lane={g['lane']} mode={g['default_mode']}\n"
        f"Escalation: {g['escalation']}; prohibited actions remain governed by agent_registry."
    )


async def _ensure_role_knowledge(agent_id: str) -> bool:
    """Idempotent lazy role seed. Runs only when context canary is explicitly on."""
    aid = _safe_agent(agent_id)
    ns = knowledge_namespaces(aid).get("role") if aid else ""
    if not ns or ns in _PROVISIONED_ROLE_NAMESPACES:
        return bool(ns)
    text = _role_document(aid)
    if not text:
        return False
    try:
        from app.voice_agent.knowledge_base import get_knowledge_base

        kb = get_knowledge_base()
        added = await asyncio.wait_for(
            asyncio.to_thread(
                kb.add_documents,
                [text],
                f"staff-profile:{aid}:{PROFILE_VERSION}",
                ns,
                True,
            ),
            timeout=3.0,
        )
        if int(added or 0) > 0:
            _PROVISIONED_ROLE_NAMESPACES.add(ns)
            return True
    except Exception as exc:
        logger.debug("[agent_maturity] role KB seed skipped for %s: %s", aid, exc)
    return False


async def runtime_briefs(agent_id: str, tenant_id: str, query: str) -> dict[str, Any]:
    """Bounded role/KB context. No LLM call; empty and fail-open while flag is OFF."""
    p = profile(agent_id, tenant_id)
    if not context_enabled() or not p.get("ok"):
        return {"enabled": False, "skill_brief": "", "knowledge_brief": ""}
    await _ensure_role_knowledge(agent_id)
    skill_brief = "Enterprise: " + ", ".join(p["skills"]["enterprise_baseline"][:5])
    skill_brief += "\nRole: " + ", ".join(p["skills"]["role_specific"])
    hits: list[str] = []
    try:
        from app.voice_agent.knowledge_base import get_knowledge_base

        kb = get_knowledge_base()
        namespaces = [p["knowledge"]["private"], p["knowledge"]["role"]]
        for ns in namespaces:
            rows = await asyncio.wait_for(
                asyncio.to_thread(kb.retrieve, (query or p["title"])[:300], 2, ns, False),
                timeout=1.5,
            )
            for row in rows or []:
                body = str(row.get("text") or "").strip()
                if body and body not in hits:
                    hits.append(body[:500])
    except Exception as exc:
        logger.debug("[agent_maturity] KB recall skipped for %s: %s", agent_id, exc)
    return {
        "enabled": True,
        "profile_version": PROFILE_VERSION,
        "skill_brief": skill_brief[:1200],
        "knowledge_brief": "\n".join(hits)[:1600],
        "memory_namespace": p["memory"]["namespace"],
        "knowledge_namespaces": p["knowledge"],
    }


__all__ = [
    "CANONICAL_COUNT",
    "COMMON_SAAS_SKILLS",
    "PROFILE_VERSION",
    "context_enabled",
    "knowledge_namespaces",
    "memory_namespace",
    "portfolio",
    "profile",
    "runtime_briefs",
    "validate_profiles",
]
