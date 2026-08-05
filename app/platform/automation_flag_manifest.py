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
    "VOICE_CLOSE_WHATSAPP": _m(
        "VOICE_CLOSE_WHATSAPP",
        FlagValueKind.BOOLEAN,
        FlagGovernance.OWNER_APPROVAL_REQUIRED,
        notes="Close-signal WA; needs sender gate",
        risk="outbound",
        customer=True,
        companions=("WHATSAPP_AUTO_SEND",),
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
