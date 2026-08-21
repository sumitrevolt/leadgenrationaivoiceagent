"""Typed metadata for AUTOMATION_FLAGS — honesty layer, not a second flag platform.

Every registry entry resolves to an explicit value kind + governance class.
Unknown certainty stays ``unknown_requires_review`` — we never invent production
proof. Non-boolean kinds never contribute to switch enabled counts.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any


class FlagValueKind(str, Enum):
    BOOLEAN = "boolean"
    INTEGER = "integer"
    FLOAT = "float"
    ENUM = "enum"
    CSV_ALLOWLIST = "csv_allowlist"
    URL = "url"
    SECRET = "secret"  # nosecret — enum label, not a credential  # pragma: allowlist secret
    CREDENTIAL_REFERENCE = "credential_reference"
    PATH = "path"
    DURATION = "duration"
    CAPACITY_LIMIT = "capacity_limit"
    DERIVED_STATUS = "derived_status"
    DEPRECATED = "deprecated"
    UNKNOWN_REQUIRES_REVIEW = "unknown_requires_review"


class FlagGovernance(str, Enum):
    SAFETY_INVARIANT = "safety_invariant"
    PRODUCTION_PROVEN = "production_proven"
    SAFE_LOCAL_ONLY = "safe_local_only"
    CANARY_ONLY = "canary_only"
    OWNER_APPROVAL_REQUIRED = "owner_approval_required"
    EXTERNAL_PREREQUISITE = "external_prerequisite"
    CONFIGURATION_NOT_SWITCH = "configuration_not_switch"
    SECRET_NEVER_EXPOSE = "secret_never_expose"  # nosecret — enum label  # pragma: allowlist secret
    DEPRECATED = "deprecated"
    UNKNOWN_REQUIRES_REVIEW = "unknown_requires_review"


# Wave-2 alias
FlagLifecycle = FlagGovernance


@dataclass(frozen=True)
class FlagMeta:
    name: str
    kind: FlagValueKind
    governance: FlagGovernance
    secret: bool
    notes: str = ""
    reviewed: str = "2026-08-03"
    owner: str = "platform"
    risk_lane: str = "ops"
    customer_side_effect: bool = False
    provider_side_effect: bool = False
    companion_flags: tuple[str, ...] = ()
    kill_switch: str = ""
    default_hint: str = ""
    parser: str = "env_truthy_or_raw"
    evidence_label: str = "CODE-PRESENT"
    canary_mechanism: str = "none"

    @property
    def lifecycle(self) -> FlagGovernance:
        """Wave-2 alias."""
        return self.governance

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["kind"] = self.kind.value
        d["governance"] = self.governance.value
        d["lifecycle"] = self.governance.value  # backward compatible
        d["companion_flags"] = list(self.companion_flags)
        return d


def _m(
    name: str,
    kind: FlagValueKind,
    gov: FlagGovernance,
    *,
    secret: bool = False,
    notes: str = "",
    owner: str = "platform",
    risk: str = "ops",
    customer: bool = False,
    provider: bool = False,
    companions: tuple[str, ...] = (),
    kill: str = "",
    default: str = "",
    evidence: str = "CODE-PRESENT",
    canary: str = "none",
    parser: str = "env_truthy_or_raw",
) -> FlagMeta:
    return FlagMeta(
        name=name,
        kind=kind,
        governance=gov,
        secret=secret,
        notes=notes,
        owner=owner,
        risk_lane=risk,
        customer_side_effect=customer,
        provider_side_effect=provider,
        companion_flags=companions,
        kill_switch=kill,
        default_hint=default,
        parser=parser,
        evidence_label=evidence,
        canary_mechanism=canary,
    )


# Explicit overlays — risky / non-obvious / production-known only.
_OVERRIDES: dict[str, FlagMeta] = {
    "REPLY_AUTO_SEND": _m(
        "REPLY_AUTO_SEND",
        FlagValueKind.BOOLEAN,
        FlagGovernance.SAFETY_INVARIANT,
        notes="Cold auto-reply; keep OFF",
        owner="rohan",
        risk="outbound",
        customer=True,
        kill="REPLY_AUTO_SEND_HARD_OFF",
        default="0",
        evidence="CODE-PRESENT",
    ),
    "REPLY_AUTO_SEND_HARD_OFF": _m(
        "REPLY_AUTO_SEND_HARD_OFF",
        FlagValueKind.BOOLEAN,
        FlagGovernance.SAFETY_INVARIANT,
        notes="Fail-closed override",
        owner="rohan",
        risk="outbound",
        default="1",
    ),
    "HQ_AUTO_CHASE": _m(
        "HQ_AUTO_CHASE",
        FlagValueKind.BOOLEAN,
        FlagGovernance.OWNER_APPROVAL_REQUIRED,
        notes=(
            "Hot Queue auto-chase: unactioned inquiry cards (>24h) pe automated EMAIL "
            "follow-up. WhatsApp/call stay 1-click human (ban-safety). Email-only."
        ),
        owner="platform",
        risk="outbound",
        customer=True,
        provider=True,
        companions=(),
        default="0",
        canary="HQ_CHASE_DAILY_CAP=2 first, verify sent+drafts, then raise",
        kill="HQ_AUTO_CHASE=0",
    ),
    "CONTENT_APPROVAL_SWEEP": _m(
        "CONTENT_APPROVAL_SWEEP",
        FlagValueKind.BOOLEAN,
        FlagGovernance.OWNER_APPROVAL_REQUIRED,
        notes=(
            "Orphaned-pending approval retirement sweep (daily 04:30). dry_run by "
            "default; CONTENT_APPROVAL_SWEEP_LIVE=1 actuates writes. Retiring != "
            "approving — terminal 'expired' marker, never publish consent."
        ),
        owner="platform",
        risk="ops",
        customer=True,
        default="0",
        canary="dry_run sweep (reports counts, writes nothing), review, then LIVE",
        kill="CONTENT_APPROVAL_SWEEP=0",
    ),
    "ALLOW_TOS_SCRAPE": _m(
        "ALLOW_TOS_SCRAPE",
        FlagValueKind.BOOLEAN,
        FlagGovernance.SAFETY_INVARIANT,
        notes="ToS-blocked directories stay refused",
        risk="compliance",
        default="0",
    ),
    "UPI_AUTO_ACTIVATE": _m(
        "UPI_AUTO_ACTIVATE",
        FlagValueKind.BOOLEAN,
        FlagGovernance.SAFETY_INVARIANT,
        notes="Manual UPI until ledger-proven",
        risk="billing",
        customer=True,
        companions=("UPI_AUTO_ACTIVATE_CLIENTS",),
        default="0",
    ),
    "UPI_AUTO_ACTIVATE_CLIENTS": _m(
        "UPI_AUTO_ACTIVATE_CLIENTS",
        FlagValueKind.CSV_ALLOWLIST,
        FlagGovernance.CONFIGURATION_NOT_SWITCH,
        notes="Empty fail-closed; * needs graduation",
        risk="billing",
    ),
    "SALES_AUTOPILOT_WHATSAPP_ENABLED": _m(
        "SALES_AUTOPILOT_WHATSAPP_ENABLED",
        FlagValueKind.BOOLEAN,
        FlagGovernance.SAFETY_INVARIANT,
        notes="Cold/bulk WhatsApp stays OFF",
        risk="outbound",
        customer=True,
        provider=True,
        default="0",
    ),
    "WHATSAPP_AUTO_SEND": _m(
        "WHATSAPP_AUTO_SEND",
        FlagValueKind.BOOLEAN,
        FlagGovernance.OWNER_APPROVAL_REQUIRED,
        notes="Sender boundary gate — not cold blast alone",
        risk="outbound",
        customer=True,
        provider=True,
        companions=("WHATSAPP_SEND_ALLOWLIST",),
        canary="WHATSAPP_SEND_ALLOWLIST",
    ),
    "WHATSAPP_SEND_ALLOWLIST": _m(
        "WHATSAPP_SEND_ALLOWLIST",
        FlagValueKind.CSV_ALLOWLIST,
        FlagGovernance.CONFIGURATION_NOT_SWITCH,
        notes="Empty=nobody; *=explicit all",
        risk="outbound",
    ),
    "PLATFORM_DIAL_DAILY": _m(
        "PLATFORM_DIAL_DAILY",
        FlagValueKind.BOOLEAN,
        FlagGovernance.PRODUCTION_PROVEN,
        notes="Boolean arm; cap=PLATFORM_DIAL_LIMIT; Agent Runtime RED separate",
        owner="swara",
        risk="voice",
        customer=True,
        provider=True,
        companions=("PLATFORM_DIAL_LIMIT", "VOICE_LAUNCH_KILL"),
        kill="VOICE_LAUNCH_KILL",
        evidence="PRODUCTION-PROVEN",
        canary="DIAL_TEST_MODE/allowlist historically removed — re-probe prod",
    ),
    "PLATFORM_DIAL_LIMIT": _m(
        "PLATFORM_DIAL_LIMIT",
        FlagValueKind.CAPACITY_LIMIT,
        FlagGovernance.CONFIGURATION_NOT_SWITCH,
        owner="swara",
        risk="voice",
        default="100",
        parser="int_clamp",
    ),
    "VOICE_DAILY_CALL_CAP": _m(
        "VOICE_DAILY_CALL_CAP",
        FlagValueKind.CAPACITY_LIMIT,
        FlagGovernance.CONFIGURATION_NOT_SWITCH,
        owner="swara",
        risk="voice",
        parser="int_clamp",
    ),
    "VOICE_LAUNCH_KILL": _m(
        "VOICE_LAUNCH_KILL",
        FlagValueKind.BOOLEAN,
        FlagGovernance.SAFETY_INVARIANT,
        notes="Global outbound kill when 1",
        owner="swara",
        risk="voice",
        default="1",
    ),
    "DUNNING_ENGINE": _m(
        "DUNNING_ENGINE",
        FlagValueKind.BOOLEAN,
        FlagGovernance.OWNER_APPROVAL_REQUIRED,
        notes=(
            "Issue #307 (2026-08-10): stays OFF / dormant. Not a launch blocker. "
            "Manual-UPI-safe canary only after money-path proof; never auto-charge."
        ),
        owner="nikhil",
        risk="billing",
        customer=True,
        provider=True,
        default="0",
        evidence="CODE-PRESENT",
        kill="DUNNING_ENGINE=0",
        canary="owner-approved tenant + dry-run ledger",
    ),
    "RENEWAL_REMINDER_ENABLED": _m(
        "RENEWAL_REMINDER_ENABLED",
        FlagValueKind.BOOLEAN,
        FlagGovernance.OWNER_APPROVAL_REQUIRED,
        notes=(
            "Independent renewal email. Body no-ops when DUNNING_ENGINE=1 "
            "(run_due already sends period-deduped reminders). In-process loop "
            "is day-keyed; celery topology does not call this path."
        ),
        owner="nikhil",
        risk="billing",
        customer=True,
        default="1",
        evidence="CODE-PRESENT",
        kill="RENEWAL_REMINDER_ENABLED=0",
    ),
    "OKF_INGEST_ENABLED": _m(
        "OKF_INGEST_ENABLED",
        FlagValueKind.BOOLEAN,
        FlagGovernance.OWNER_APPROVAL_REQUIRED,
        notes="ADR-119 Phase-1 OKF→Qdrant ingest; OFF default; dry-run always safe",
        owner="platform",
        risk="ops",
        default="0",
        evidence="CODE-PRESENT",
        companions=("OKF_PUBLIC_BUNDLE",),
        kill="OKF_INGEST_ENABLED",
    ),
    "OKF_PUBLIC_BUNDLE": _m(
        "OKF_PUBLIC_BUNDLE",
        FlagValueKind.BOOLEAN,
        FlagGovernance.SAFE_LOCAL_ONLY,
        notes="Public /okf/ Markdown; default ON; content is git-curated knowledge/",
        owner="platform",
        risk="ops",
        default="1",
        evidence="CODE-PRESENT",
    ),
    "OKF_BUNDLE_DIR": _m(
        "OKF_BUNDLE_DIR",
        FlagValueKind.PATH,
        FlagGovernance.CONFIGURATION_NOT_SWITCH,
        notes="Test/canary override for knowledge/ root",
        owner="platform",
        risk="ops",
        default="knowledge/",
        evidence="CODE-PRESENT",
    ),
    "EXTERNAL_AGENT_ORCHESTRATOR": _m(
        "EXTERNAL_AGENT_ORCHESTRATOR",
        FlagValueKind.BOOLEAN,
        FlagGovernance.CANARY_ONLY,
        notes="ADR-148 records/missions; prod OFF",
        risk="dev_control",
        default="0",
        canary="local/Windows",
    ),
    "EXTERNAL_AGENT_RUNNER": _m(
        "EXTERNAL_AGENT_RUNNER",
        FlagValueKind.BOOLEAN,
        FlagGovernance.CANARY_ONLY,
        notes="ADR-149 dual-gate; prod OFF",
        risk="dev_control",
        companions=("EXTERNAL_AGENT_ORCHESTRATOR",),
        default="0",
        canary="local/Windows",
    ),
    "PR_FACTORY_ENABLED": _m(
        "PR_FACTORY_ENABLED",
        FlagValueKind.BOOLEAN,
        FlagGovernance.CANARY_ONLY,
        notes="ADR-156 thin dispatcher onto external_agents; dual-gate with ORCHESTRATOR; prod OFF",
        risk="dev_control",
        companions=("EXTERNAL_AGENT_ORCHESTRATOR",),
        default="0",
        canary="local/Windows",
        kill="PR_FACTORY_ENABLED=0",
        evidence="CODE-PRESENT",
    ),
    "PR_FACTORY_PILOT_ENABLED": _m(
        "PR_FACTORY_PILOT_ENABLED",
        FlagValueKind.BOOLEAN,
        FlagGovernance.CANARY_ONLY,
        notes="ADR-166 bounded PR-orchestration pilot (triple-gate, task manifest, max 2 repair attempts, no merge/deploy); prod OFF",
        risk="dev_control",
        companions=("EXTERNAL_AGENT_ORCHESTRATOR", "PR_FACTORY_ENABLED"),
        default="0",
        canary="local/Windows",
        kill="PR_FACTORY_PILOT_ENABLED=0",
        evidence="CODE-PRESENT",
    ),
    "CELERY_ONBOARD_QUEUE": _m(
        "CELERY_ONBOARD_QUEUE",
        FlagValueKind.BOOLEAN,
        FlagGovernance.CANARY_ONLY,
        notes="Route onboard_client to existing heavy worker; OFF=default celery; never invent an unconsumed queue",
        risk="ops",
        default="0",
        kill="CELERY_ONBOARD_QUEUE=0",
        evidence="CODE-PRESENT",
    ),
    "ONBOARDING_PIPELINE": _m(
        "ONBOARDING_PIPELINE",
        FlagValueKind.BOOLEAN,
        FlagGovernance.CANARY_ONLY,
        notes="Staged onboarding factory pipeline with retry/DLQ/backpressure; OFF=default (legacy auto_onboard still works)",
        risk="ops",
        default="0",
        kill="ONBOARDING_PIPELINE=0",
        evidence="CODE-PRESENT",
    ),
    "FORM_BUILDER": _m(
        "FORM_BUILDER",
        FlagValueKind.BOOLEAN,
        FlagGovernance.CANARY_ONLY,
        notes="Admin form/survey builder (data/forms.jsonl); OFF=API 503, no checkout writes from the route",
        risk="ops",
        default="0",
        kill="FORM_BUILDER=0",
        evidence="CODE-PRESENT",
    ),
    "PROPOSAL_BUILDER": _m(
        "PROPOSAL_BUILDER",
        FlagValueKind.BOOLEAN,
        FlagGovernance.CANARY_ONLY,
        notes="Admin proposal/quote drafts (data/proposals.jsonl); OFF=API 503; not a billing ledger",
        risk="ops",
        default="0",
        kill="PROPOSAL_BUILDER=0",
        evidence="CODE-PRESENT",
    ),
    "COORDINATION_HUB_ENABLED": _m(
        "COORDINATION_HUB_ENABLED",
        FlagValueKind.BOOLEAN,
        FlagGovernance.CANARY_ONLY,
        notes="ADR-150 Owner OS thin projection; not second control plane; prod OFF",
        risk="owner_os",
        default="0",
        canary="local/admin",
    ),
    "OWNER_OS_LITMUS": _m(
        "OWNER_OS_LITMUS",
        FlagValueKind.BOOLEAN,
        FlagGovernance.PRODUCTION_PROVEN,
        notes="ADR-155 agent-swarm pattern harvest — deterministic Owner OS litmus; default ON",
        risk="owner_os",
        default="1",
        kill="OWNER_OS_LITMUS=0",
        evidence="CODE-PRESENT",
    ),
    "COORD_HUB_BUZZ_SECRET": _m(
        "COORD_HUB_BUZZ_SECRET",
        FlagValueKind.SECRET,
        FlagGovernance.SECRET_NEVER_EXPOSE,
        notes="Buzz webhook HMAC only; never admin bearer",
        risk="security",
    ),
    "COORD_HUB_TOOL_CURSOR_SECRET": _m(
        "COORD_HUB_TOOL_CURSOR_SECRET",
        FlagValueKind.SECRET,
        FlagGovernance.SECRET_NEVER_EXPOSE,
        notes="Per-tool Cursor heartbeat HMAC",
        risk="security",
    ),
    "COORD_HUB_TOOL_CLAUDE_SECRET": _m(
        "COORD_HUB_TOOL_CLAUDE_SECRET",
        FlagValueKind.SECRET,
        FlagGovernance.SECRET_NEVER_EXPOSE,
        notes="Per-tool Claude heartbeat HMAC",
        risk="security",
    ),
    "COORD_PLAN_NODE": _m(
        "COORD_PLAN_NODE",
        FlagValueKind.BOOLEAN,
        FlagGovernance.CANARY_ONLY,
        notes="ADR-159 MetaGPT steal-#1 structured plan canary; prod OFF; legacy _extract_list stays authoritative fallback",
        owner="platform",
        risk="llm_cost",
        companions=("COORD_PLAN_NODE_REVIEWS",),
        default="0",
        canary="coordinator.plan() single caller; measure before graduating",
    ),
    "COORD_PLAN_NODE_REVIEWS": _m(
        "COORD_PLAN_NODE_REVIEWS",
        FlagValueKind.INTEGER,
        FlagGovernance.CONFIGURATION_NOT_SWITCH,
        notes="Bounded review/revise rounds on schema failure; 0 = no review round",
        owner="platform",
        risk="llm_cost",
        default="1",
        parser="int_clamp",
    ),
    "HARNESS_SESSION_EVENTS": _m(
        "HARNESS_SESSION_EVENTS",
        FlagValueKind.BOOLEAN,
        FlagGovernance.CANARY_ONLY,
        notes="ADR-180 dsh steal-#1 typed SessionEvent + process-local hash-chain on harness jsonl; prod OFF; flag-off rows stay historical-key compatible",
        owner="platform",
        risk="ops",
        default="0",
        canary="local pytest + isolated HARNESS_RUN_LOG; do not arm AGENT_HARNESS with this in prod",
        kill="HARNESS_SESSION_EVENTS=0",
    ),
    "DSH_RUNTIME_ENABLED": _m(
        "DSH_RUNTIME_ENABLED",
        FlagValueKind.BOOLEAN,
        FlagGovernance.OWNER_APPROVAL_REQUIRED,
        notes=(
            "Hardened source-built DSH authority gate; OFF uses deterministic direct "
            "executor; never arm automatically"
        ),
        owner="rohan",
        risk="agent_os",
        customer=True,
        provider=True,
        companions=("DSH_AGENT_ALLOWLIST", "DSH_SHADOW_ENABLED"),
        default="0",
        canary="evidence-gated rollout waves after shadow parity",
        kill="DSH_RUNTIME_ENABLED=0",
    ),
    "DSH_SHADOW_ENABLED": _m(
        "DSH_SHADOW_ENABLED",
        FlagValueKind.BOOLEAN,
        FlagGovernance.CANARY_ONLY,
        notes="Proposal-only DSH shadow; child has no mutating capability submit tool",
        owner="platform",
        risk="agent_os",
        companions=("DSH_AGENT_ALLOWLIST",),
        default="0",
        canary="120 golden cases then 2,000 turns / 14-day soak",
        kill="DSH_SHADOW_ENABLED=0",
    ),
    "DSH_AGENT_ALLOWLIST": _m(
        "DSH_AGENT_ALLOWLIST",
        FlagValueKind.CSV_ALLOWLIST,
        FlagGovernance.CONFIGURATION_NOT_SWITCH,
        notes="Bounded executable-agent allowlist; empty means no DSH authority or shadow",
        owner="rohan",
        risk="agent_os",
        companions=("DSH_RUNTIME_ENABLED", "DSH_SHADOW_ENABLED"),
        default="",
        parser="csv",
    ),
    "BOSS_DECISION_GOVERNANCE": _m(
        "BOSS_DECISION_GOVERNANCE",
        FlagValueKind.BOOLEAN,
        FlagGovernance.OWNER_APPROVAL_REQUIRED,
        notes=(
            "Boss+Second-Brain hash-bound decision approvals "
            "(propose→advice→boss→consume); OFF default; "
            "execute fail-closed; Owner OS AMBER verify+one-time consume"
        ),
        owner="rohan",
        risk="ops",
        default="0",
        evidence="CODE-PRESENT",
        canary="coordinator.coordinate_hierarchical adapter + Owner OS inbox",
    ),
    "BOSS_FULL_AUTONOMY": _m(
        "BOSS_FULL_AUTONOMY",
        FlagValueKind.BOOLEAN,
        FlagGovernance.OWNER_APPROVAL_REQUIRED,
        notes=(
            "Boss full-autonomy loop over BOSS_DECISION_GOVERNANCE "
            "(sweep existing decisions -> advice -> review -> consume); "
            "OFF default inert; GREEN auto / AMBER needs_owner / RED+UPI refuse; "
            "advisory absence never executes"
        ),
        owner="rohan",
        risk="ops",
        default="0",
        evidence="CODE-PRESENT",
        canary="app.platform.boss_autonomy sweep (manager held until mutating canary)",
        companions=("BOSS_DECISION_GOVERNANCE",),
    ),
    "STAFF_BUS_ENABLED": _m(
        "STAFF_BUS_ENABLED",
        FlagValueKind.BOOLEAN,
        FlagGovernance.OWNER_APPROVAL_REQUIRED,
        notes=(
            "31-STAFF Buzz collaboration bus (signed bridge projections); "
            "OFF default inert; synthetic canaries may run with allow_synthetic; "
            "never executes protected customer outbound/payment actions"
        ),
        owner="rohan",
        risk="ops",
        default="0",
        evidence="CODE-PRESENT",
        canary="app.platform.staff_bus.run_all_staff_canaries",
    ),
    "SALES_AUTOPILOT_ENABLED": _m(
        "SALES_AUTOPILOT_ENABLED",
        FlagValueKind.BOOLEAN,
        FlagGovernance.PRODUCTION_PROVEN,
        notes="Owner-armed master; channels separate",
        risk="outbound",
        customer=True,
        evidence="PRODUCTION-PROVEN",
    ),
    "SALES_AUTOPILOT_EMAIL_ENABLED": _m(
        "SALES_AUTOPILOT_EMAIL_ENABLED",
        FlagValueKind.BOOLEAN,
        FlagGovernance.PRODUCTION_PROVEN,
        risk="outbound",
        customer=True,
        provider=True,
        evidence="PRODUCTION-PROVEN",
    ),
    "SALES_AUTOPILOT_DRY_RUN": _m(
        "SALES_AUTOPILOT_DRY_RUN",
        FlagValueKind.BOOLEAN,
        FlagGovernance.OWNER_APPROVAL_REQUIRED,
        notes="0 = live on enabled channels",
        risk="outbound",
    ),
    "AGENT_RUNTIME": _m(
        "AGENT_RUNTIME",
        FlagValueKind.BOOLEAN,
        FlagGovernance.CANARY_ONLY,
        notes="Pilot allowlist; RED blocked for Swara/Ananya",
        risk="agent_os",
        canary="PILOT_AGENTS allowlist",
    ),
    "CREATIVE_OS_ENABLED": _m(
        "CREATIVE_OS_ENABLED",
        FlagValueKind.BOOLEAN,
        FlagGovernance.OWNER_APPROVAL_REQUIRED,
        notes="Providers may be inert skeletons",
        risk="creative",
    ),
    "FEATURE_FLAGS": _m(
        "FEATURE_FLAGS",
        FlagValueKind.BOOLEAN,
        FlagGovernance.SAFE_LOCAL_ONLY,
        notes="Master gate for per-tenant FeatureFlagService",
        risk="product",
    ),
    "POST_CALL_WHATSAPP": _m(
        "POST_CALL_WHATSAPP",
        FlagValueKind.BOOLEAN,
        FlagGovernance.OWNER_APPROVAL_REQUIRED,
        notes="Interested-lead path — separate from cold WA",
        risk="outbound",
        customer=True,
        companions=("WHATSAPP_AUTO_SEND",),
    ),
    "ONBOARD_WIZARD_APPLY": _m(
        "ONBOARD_WIZARD_APPLY",
        FlagValueKind.BOOLEAN,
        FlagGovernance.SAFE_LOCAL_ONLY,
        notes=(
            "Business-type wizard auto-setup (salon/clinic/restaurant template apply) — "
            "OFF default; preview/catalog endpoints hamesha available"
        ),
        risk="product",
    ),
    "POST_CALL_SUMMARY": _m(
        "POST_CALL_SUMMARY",
        FlagValueKind.BOOLEAN,
        FlagGovernance.OWNER_APPROVAL_REQUIRED,
        notes=(
            "AI post-call WhatsApp summary + action items to qualified leads — "
            "needs WHATSAPP_AUTO_SEND too; OFF default"
        ),
        risk="outbound",
        customer=True,
        companions=("WHATSAPP_AUTO_SEND",),
    ),
    "VOICE_CLOSE_WHATSAPP": _m(
        "VOICE_CLOSE_WHATSAPP",
        FlagValueKind.BOOLEAN,
        FlagGovernance.OWNER_APPROVAL_REQUIRED,
        notes="Close-signal WA; needs sender gate",
        risk="outbound",
        customer=True,
        companions=("WHATSAPP_AUTO_SEND",),
    ),
    "VOICE_KB_STRICT_GROUNDING": _m(
        "VOICE_KB_STRICT_GROUNDING",
        FlagValueKind.BOOLEAN,
        FlagGovernance.CANARY_ONLY,
        notes=(
            "A1 typed KB grounding: ON = citation jo apne chunk me verbatim verify "
            "na ho wo drop, sab drop ho gaye to refusal. OFF (default) = warn-only. "
            "Reader = app/voice_agent/kb_grounding.py; voice reply path me WIRED "
            "NAHI (Swara/voice FROZEN — wiring owner approval ka kaam)"
        ),
        owner="platform",
        risk="product",
        default="0",
        canary="module present, zero callers; wire one niche namespace first",
    ),
    "VOICE_KB_MIN_GROUND_SCORE": _m(
        "VOICE_KB_MIN_GROUND_SCORE",
        FlagValueKind.INTEGER,
        FlagGovernance.CONFIGURATION_NOT_SWITCH,
        notes=(
            "KB refusal threshold override. Unset = knowledge_base._MIN_GROUND_SCORE "
            "(0.04) — aaj ka behaviour. Scores backend-dependent hain (keyword cosine "
            "vs Chroma 1/(1+dist) vs Qdrant), isliye number guess mat karo"
        ),
        owner="platform",
        risk="product",
        default="",
        parser="float_or_kb_default",
    ),
    "APPROVAL_EMAIL_CLIENT_ALLOWLIST": _m(
        "APPROVAL_EMAIL_CLIENT_ALLOWLIST",
        FlagValueKind.CSV_ALLOWLIST,
        FlagGovernance.CONFIGURATION_NOT_SWITCH,
        risk="outbound",
    ),
    "WARM_SLA_MIN": _m(
        "WARM_SLA_MIN",
        FlagValueKind.DURATION,
        FlagGovernance.CONFIGURATION_NOT_SWITCH,
        parser="int_minutes",
    ),
    "COUNCIL_TIMEOUT_S": _m(
        "COUNCIL_TIMEOUT_S",
        FlagValueKind.DURATION,
        FlagGovernance.CONFIGURATION_NOT_SWITCH,
        parser="int_seconds",
    ),
    "WHATSAPP_PROVIDER": _m(
        "WHATSAPP_PROVIDER",
        FlagValueKind.ENUM,
        FlagGovernance.CONFIGURATION_NOT_SWITCH,
        notes="cloud|waha",
        risk="outbound",
    ),
    "MEM0_BACKEND": _m(
        "MEM0_BACKEND",
        FlagValueKind.ENUM,
        FlagGovernance.CONFIGURATION_NOT_SWITCH,
    ),
    "WORKFORCE_MEMORY_DIR": _m(
        "WORKFORCE_MEMORY_DIR",
        FlagValueKind.PATH,
        FlagGovernance.CONFIGURATION_NOT_SWITCH,
    ),
    "META_OAUTH_APPROVED": _m(
        "META_OAUTH_APPROVED",
        FlagValueKind.DERIVED_STATUS,
        FlagGovernance.EXTERNAL_PREREQUISITE,
        notes="Env ON ≠ oauth_ready until authorize wired",
        risk="social",
    ),
    "GBP_OAUTH_APPROVED": _m(
        "GBP_OAUTH_APPROVED",
        FlagValueKind.DERIVED_STATUS,
        FlagGovernance.EXTERNAL_PREREQUISITE,
        risk="social",
    ),
    "LINKEDIN_OAUTH_APPROVED": _m(
        "LINKEDIN_OAUTH_APPROVED",
        FlagValueKind.DERIVED_STATUS,
        FlagGovernance.EXTERNAL_PREREQUISITE,
        risk="social",
    ),
    "X_OAUTH_APPROVED": _m(
        "X_OAUTH_APPROVED",
        FlagValueKind.DERIVED_STATUS,
        FlagGovernance.EXTERNAL_PREREQUISITE,
        risk="social",
    ),
    "GOOGLE_OAUTH_APPROVED": _m(
        "GOOGLE_OAUTH_APPROVED",
        FlagValueKind.DERIVED_STATUS,
        FlagGovernance.EXTERNAL_PREREQUISITE,
        risk="social",
    ),
    "HERMES_HANDOFF": _m(
        "HERMES_HANDOFF",
        FlagValueKind.BOOLEAN,
        FlagGovernance.DEPRECATED,
        notes="Reserved future — not a live switch",
        evidence="CODE-PRESENT",
    ),
    "CONSENT_CONFIRM": _m(
        "CONSENT_CONFIRM",
        FlagValueKind.BOOLEAN,
        FlagGovernance.EXTERNAL_PREREQUISITE,
        notes="Reserved until DLT unlock paperwork complete",
        risk="compliance",
    ),
}

_SECRET_SUFFIXES = ("_KEY", "_TOKEN", "_SECRET", "PASSWORD", "_DSN")
_DURATION_SUFFIXES = (
    "_TIMEOUT_S",
    "_BUDGET_S",
    "_LAG_WARN_S",
    "_LAG_FAIL_S",
    "_COOLDOWN_SEC",
    "_TIMEOUT",
    "_WINDOW",
    "_DAYS",
    "_MS",
    "_SEC",
    "_DELAY_S",
)
_CAPACITY_SUFFIXES = (
    "_LIMIT",
    "_CAP",
    "_MAX",
    "_MIN",
    "_BATCH",
    "_CONCURRENCY",
    "_THRESHOLD",
    "_DEPTH",
    "_PERCENT",
    "_PCT",
    "_RPM",
    "_TPD",
    "_BUDGET",
    "_CHARS_PER",
    "_TOTAL",
    "_N",
)


def is_secret_name(name: str) -> bool:
    u = (name or "").upper()
    if "PASSWORD" in u:
        return True
    return any(u.endswith(s) for s in _SECRET_SUFFIXES)


def infer_kind(name: str) -> FlagValueKind:
    if name in _OVERRIDES:
        return _OVERRIDES[name].kind
    u = (name or "").upper()
    if is_secret_name(name):
        if u.endswith(("_URL",)):
            return FlagValueKind.URL
        if "MASTER_KEY" in u or u.endswith("_KEY") or u.endswith("_TOKEN"):
            return FlagValueKind.SECRET
        return FlagValueKind.CREDENTIAL_REFERENCE
    if u.endswith("_URL") or u.endswith("_DSN"):
        return FlagValueKind.URL
    if "ALLOWLIST" in u or u.endswith("_CLIENTS") and "ALLOW" in u:
        return FlagValueKind.CSV_ALLOWLIST
    if u.endswith("_CLIENTS") or u.endswith("_BOARD"):
        return FlagValueKind.CSV_ALLOWLIST
    if any(u.endswith(s) for s in _DURATION_SUFFIXES) or u.endswith("_MIN") and "SLA" in u:
        return FlagValueKind.DURATION
    if any(u.endswith(s) for s in _CAPACITY_SUFFIXES):
        return FlagValueKind.CAPACITY_LIMIT
    if u.endswith(("_MODE", "_BACKEND", "_PROVIDER", "_PROFILE", "_NICHE", "_TONE")):
        return FlagValueKind.ENUM
    if u.endswith("_DIR") or u.endswith("_PATH") or u.endswith("_ROOT"):
        return FlagValueKind.PATH
    if u.endswith("_APPROVED"):
        return FlagValueKind.DERIVED_STATUS
    # Typical automation switches
    if (
        u.startswith(("USE_", "ENABLE_", "AUTO_"))
        or u.endswith(("_ENABLED", "_ENABLE", "_ENGINE", "_AGENT", "_LOOP", "_GATE"))
        or u.endswith(("_DAILY", "_WATCH", "_ALERTS", "_SYNC", "_DRAIN"))
    ):
        return FlagValueKind.BOOLEAN
    # Default: treat bare registry names as boolean switches pending review
    return FlagValueKind.BOOLEAN


def describe_flag(name: str) -> FlagMeta:
    if name in _OVERRIDES:
        return _OVERRIDES[name]
    kind = infer_kind(name)
    secret = is_secret_name(name) or kind in {
        FlagValueKind.SECRET,
        FlagValueKind.CREDENTIAL_REFERENCE,
    }
    if secret or kind == FlagValueKind.SECRET:
        gov = FlagGovernance.SECRET_NEVER_EXPOSE
        if kind == FlagValueKind.BOOLEAN:
            kind = FlagValueKind.SECRET
    elif kind in {
        FlagValueKind.INTEGER,
        FlagValueKind.FLOAT,
        FlagValueKind.URL,
        FlagValueKind.CSV_ALLOWLIST,
        FlagValueKind.ENUM,
        FlagValueKind.PATH,
        FlagValueKind.DURATION,
        FlagValueKind.CAPACITY_LIMIT,
        FlagValueKind.DERIVED_STATUS,
    }:
        gov = FlagGovernance.CONFIGURATION_NOT_SWITCH
    elif kind == FlagValueKind.DEPRECATED:
        gov = FlagGovernance.DEPRECATED
    else:
        # Explicit honesty: type may be boolean, governance still unknown
        gov = FlagGovernance.UNKNOWN_REQUIRES_REVIEW
    return FlagMeta(
        name=name,
        kind=kind,
        governance=gov,
        secret=secret,
        notes="heuristic type; governance unknown_requires_review until owner overlay",
        evidence_label="CODE-PRESENT",
    )


@lru_cache(maxsize=1)
def _app_blob() -> str:
    root = Path(__file__).resolve().parents[1]
    chunks: list[str] = []
    for p in root.rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        try:
            chunks.append(p.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            pass
    return "\n".join(chunks)


@lru_cache(maxsize=1)
def _callsite_index() -> dict[str, int]:
    """One-pass token count of AUTOMATION_FLAGS names inside app/."""
    from app.api.automation_flags import AUTOMATION_FLAGS

    names = set(AUTOMATION_FLAGS)
    blob = _app_blob()
    counts: Counter[str] = Counter()
    for token in re.findall(r"\b[A-Z][A-Z0-9_]{2,}\b", blob):
        if token in names:
            counts[token] += 1
    return dict(counts)


def callsite_count(name: str) -> int:
    """Approximate app/ references (registry line counts as ≥1)."""
    return int(_callsite_index().get(name, 0))


def build_manifest(names: list[str] | None = None) -> dict[str, Any]:
    if names is None:
        from app.api.automation_flags import AUTOMATION_FLAGS

        names = list(AUTOMATION_FLAGS)
    items = [describe_flag(n) for n in names]
    by_kind: Counter[str] = Counter()
    by_gov: Counter[str] = Counter()
    for m in items:
        by_kind[m.kind.value] += 1
        by_gov[m.governance.value] += 1
    # Optional expensive index — only when building full manifest once
    sites = _callsite_index()
    flags_out: dict[str, Any] = {}
    for m in items:
        d = m.to_dict()
        d["callsite_count"] = int(sites.get(m.name, 0))
        flags_out[m.name] = d
    return {
        "count": len(items),
        "unique": len({m.name for m in items}),
        "by_kind": dict(by_kind),
        "by_lifecycle": dict(by_gov),  # compat
        "by_governance": dict(by_gov),
        "flags": flags_out,
        "note": (
            "boolean_on_count / switch_on only count FlagValueKind.boolean. "
            "Non-boolean kinds never count as enabled switches. "
            "unknown_requires_review = no invented production certainty. No mass enablement."
        ),
        "reviewed": "2026-08-03",
    }


def enrich_flag_row(
    name: str, row: dict[str, Any], *, include_callsites: bool = False
) -> dict[str, Any]:
    meta = describe_flag(name)
    out = dict(row)
    out["kind"] = meta.kind.value
    out["governance"] = meta.governance.value
    out["lifecycle"] = meta.governance.value
    out["secret"] = meta.secret
    out["evidence_label"] = meta.evidence_label
    out["owner"] = meta.owner
    out["risk_lane"] = meta.risk_lane
    out["customer_side_effect"] = meta.customer_side_effect
    out["provider_side_effect"] = meta.provider_side_effect
    out["companion_flags"] = list(meta.companion_flags)
    out["kill_switch"] = meta.kill_switch
    out["canary_mechanism"] = meta.canary_mechanism
    out["reviewed"] = meta.reviewed
    if include_callsites:
        out["callsite_count"] = callsite_count(name)
    if meta.notes:
        out["meta_notes"] = meta.notes
    if meta.kind == FlagValueKind.BOOLEAN:
        out["switch_on"] = bool(row.get("on"))
    else:
        out["switch_on"] = None
        out["configured"] = bool(row.get("set"))
    return out


# Wave-2 test helpers expected these names
def infer_lifecycle(name: str, kind: FlagValueKind | None = None) -> FlagGovernance:
    return describe_flag(name).governance
