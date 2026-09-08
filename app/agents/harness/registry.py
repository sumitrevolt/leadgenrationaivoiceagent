"""Canonical tool registry + structured tool definitions (single source of truth).

This is the ONE authoritative store of executable tool identity, version, schema,
risk lane, authority, permissions and execution requirements. Adapters may
*describe* actions; they may not redefine registry policy. Owner OS remains the
sole mutation authority — a definition can require OWNER_OS_REQUIRED but the
registry never executes anything.

Shadow-only in this phase: `evaluate_action` returns what enforcement WOULD
decide (registry_comparison + would_allow/deny/require_approval). Nothing is
enforced; nothing is executed here.

Reconciliation (Graphify):
- app/agents/harness/tool_registry.py  = per-RUN lightweight registry used by the
  observe() throwaway path (kept; unchanged).
- app/dev_control/registry.py          = MODEL/provider catalog (not tools; kept).
- app/integrations/openclaw/policies.py= OpenClaw COMMAND lanes (kept).
- THIS module                          = canonical TOOL registry (new, additive).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, field_validator

from app.agents.harness.contracts import RiskClass  # existing side-effect-ish enum


# --------------------------------------------------------------------------- #
# Enums (unknown values fail validation)
# --------------------------------------------------------------------------- #
class RiskLane(str, Enum):
    GREEN = "GREEN"
    AMBER = "AMBER"
    RED = "RED"


class SideEffectClass(str, Enum):
    NONE = "NONE"
    READ_ONLY = "READ_ONLY"
    WRITE_LOCAL = "WRITE_LOCAL"
    WRITE_TENANT = "WRITE_TENANT"
    EXTERNAL_SEND = "EXTERNAL_SEND"
    BILLING = "BILLING"
    CALLING = "CALLING"
    DEPLOYMENT = "DEPLOYMENT"
    CODE_EXECUTION = "CODE_EXECUTION"


class AuthorityClass(str, Enum):
    INTERNAL_AUTONOMOUS = "INTERNAL_AUTONOMOUS"
    OWNER_OS_REQUIRED = "OWNER_OS_REQUIRED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    ALWAYS_REFUSED = "ALWAYS_REFUSED"


class RegistryStatus(str, Enum):
    REGISTRY_MATCH = "REGISTRY_MATCH"
    UNREGISTERED_TOOL = "UNREGISTERED_TOOL"
    VERSION_MISMATCH = "VERSION_MISMATCH"
    SCHEMA_MISMATCH = "SCHEMA_MISMATCH"
    AGENT_NOT_ALLOWED = "AGENT_NOT_ALLOWED"
    TENANT_NOT_ALLOWED = "TENANT_NOT_ALLOWED"
    RISK_CLASS_MISMATCH = "RISK_CLASS_MISMATCH"
    IDEMPOTENCY_REQUIRED = "IDEMPOTENCY_REQUIRED"
    DISABLED = "DISABLED"


_NAME_RE = re.compile(r"^[a-z][a-z0-9]*(?:\.[a-z0-9_]+){1,}$")  # <domain>.<capability>.<action>
_VER_RE = re.compile(r"^\d+\.\d+\.\d+$")

# Map the existing (side-effect-ish) RiskClass a model/adapter *claims* to a lane.
_CLAIM_LANE = {
    RiskClass.READ: RiskLane.GREEN,
    RiskClass.WRITE_LOCAL: RiskLane.GREEN,
    RiskClass.EXTERNAL_SEND: RiskLane.AMBER,
    RiskClass.TELEPHONY: RiskLane.AMBER,
    RiskClass.MONEY: RiskLane.AMBER,
    RiskClass.CODE_EXEC: RiskLane.RED,
}


def claimed_lane(rc: Any) -> RiskLane | None:
    try:
        return _CLAIM_LANE.get(RiskClass(rc)) if rc is not None else None
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Deterministic canonicalization for the manifest fingerprint.
#
# The manifest hash is a CHANGE / CONFORMANCE fingerprint (NOT an auth token and
# NOT an authorization mechanism): the same registry definitions must always
# produce the same hash, independent of PYTHONHASHSEED randomization, process,
# container or restart. The only non-determinism source is unordered collections
# (frozenset/set) which model_dump serializes to iteration-order-dependent lists.
# We canonicalize by sorting set/frozenset members and dict keys deterministically
# while PRESERVING list/tuple order (which may be semantically meaningful, e.g. a
# JSON-Schema ``required`` array). No repr(), no Python object hashes, no
# insertion-order reliance; unsupported leaf types fail loudly at json.dumps.
# --------------------------------------------------------------------------- #
def _canonical_json(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def canonicalize_manifest_value(value: Any) -> Any:
    """Recursively convert *value* into a deterministic, JSON-native structure."""
    if isinstance(value, BaseModel):
        return canonicalize_manifest_value(value.model_dump(mode="python"))
    if isinstance(value, Enum):
        return canonicalize_manifest_value(value.value)
    if isinstance(value, Mapping):
        return {
            str(k): canonicalize_manifest_value(value[k])
            for k in sorted(value, key=lambda item: str(item))
        }
    if isinstance(value, set | frozenset):
        items = [canonicalize_manifest_value(v) for v in value]
        return sorted(items, key=_canonical_json)
    if isinstance(value, tuple | list):
        return [canonicalize_manifest_value(v) for v in value]
    return value


# --------------------------------------------------------------------------- #
# Tool definition
# --------------------------------------------------------------------------- #
class ToolDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    version: str
    description: str
    input_schema: dict = {}
    output_schema: dict | None = None
    risk_class: RiskLane
    side_effect_class: SideEffectClass
    authority: AuthorityClass
    allowed_agents: frozenset[str] = frozenset()
    allowed_tenant_scopes: frozenset[str] = frozenset({"__system__"})
    requires_approval: bool = False
    approval_policy: str | None = None
    requires_idempotency: bool = False
    timeout_seconds: int = 30
    max_retries: int = 0
    cost_class: str = "free"
    budget_scope: str | None = None
    rate_limit_scope: str | None = None
    sandbox_required: bool = False
    network_policy: str = "deny"
    executor_ref: str = ""
    enabled_by_default: bool = True

    @field_validator("name")
    @classmethod
    def _name_ok(cls, v: str) -> str:
        if not _NAME_RE.match(v):
            raise ValueError(
                f"invalid canonical tool name: {v!r} (want <domain>.<capability>.<action>)"
            )
        return v

    @field_validator("version")
    @classmethod
    def _ver_ok(cls, v: str) -> str:
        if not _VER_RE.match(v):
            raise ValueError(f"invalid version: {v!r} (want semver MAJOR.MINOR.PATCH)")
        return v

    def public_view(self) -> dict:
        """Listing-safe view — no executor callables/secrets."""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "risk_class": self.risk_class.value,
            "side_effect_class": self.side_effect_class.value,
            "authority": self.authority.value,
            "allowed_agents": sorted(self.allowed_agents),
            "allowed_tenant_scopes": sorted(self.allowed_tenant_scopes),
            "requires_approval": self.requires_approval,
            "requires_idempotency": self.requires_idempotency,
            "timeout_seconds": self.timeout_seconds,
            "sandbox_required": self.sandbox_required,
            "network_policy": self.network_policy,
            "enabled": self.enabled_by_default,
            "input_schema_keys": sorted((self.input_schema.get("properties") or {}).keys()),
        }


class RegistryConflict(Exception):
    pass


def _minimal_schema_check(schema: dict, args: dict) -> tuple[bool, str]:
    """Strict JSON-Schema subset: object type, required present, declared property
    types, additionalProperties=false rejects unknown keys, bounded strings. Fails
    CLOSED on anything it cannot positively validate."""
    if not schema:
        return True, ""
    if schema.get("type", "object") != "object":
        return False, "schema root must be object"
    props = schema.get("properties") or {}
    required = schema.get("required") or []
    addl = schema.get("additionalProperties", True)
    if not isinstance(args, dict):
        return False, "arguments must be an object"
    for r in required:
        if r not in args:
            return False, f"missing required argument: {r}"
    if addl is False:
        extra = set(args) - set(props)
        if extra:
            return False, f"unexpected argument(s): {sorted(extra)}"
    _pytypes = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "object": dict,
        "array": list,
    }
    for k, v in args.items():
        spec = props.get(k)
        if not spec:
            continue
        t = spec.get("type")
        if t and t in _pytypes and not isinstance(v, _pytypes[t]):
            return False, f"argument {k!r} wrong type (want {t})"
        if t == "string" and isinstance(v, str):
            mx = spec.get("maxLength", 4000)
            if len(v) > int(mx):
                return False, f"argument {k!r} exceeds maxLength {mx}"
    return True, ""


class CanonicalToolRegistry:
    def __init__(self) -> None:
        self._defs: dict[tuple[str, str], ToolDefinition] = {}

    # ---- registration (explicit only; never auto-discovers callables) ----
    def register(self, defn: ToolDefinition) -> None:
        key = (defn.name, defn.version)
        existing = self._defs.get(key)
        if existing is not None:
            if existing.model_dump() == defn.model_dump():
                return  # exact duplicate = idempotent
            raise RegistryConflict(f"conflicting definition for {defn.name}@{defn.version}")
        self._defs[key] = defn

    def get(self, name: str, version: str | None = None) -> ToolDefinition | None:
        if version is not None:
            return self._defs.get((name, version))
        vs = self.list_versions(name)
        return self._defs.get((name, vs[-1])) if vs else None

    def resolve(self, name: str, version: str | None = None) -> ToolDefinition | None:
        return self.get(name, version)

    def list_versions(self, name: str) -> list[str]:
        vs = [v for (n, v) in self._defs if n == name]
        return sorted(vs, key=lambda s: tuple(int(x) for x in s.split(".")))

    def list_tools(self) -> list[dict]:
        return [
            d.public_view() for d in sorted(self._defs.values(), key=lambda d: (d.name, d.version))
        ]

    def is_agent_allowed(self, defn: ToolDefinition, agent: str) -> bool:
        a = (agent or "").strip().lower()
        return "*" in defn.allowed_agents or a in {x.lower() for x in defn.allowed_agents}

    def is_tenant_scope_allowed(self, defn: ToolDefinition, tenant: str) -> bool:
        t = tenant or "__system__"
        return "*" in defn.allowed_tenant_scopes or t in defn.allowed_tenant_scopes

    def manifest_hash(self) -> str:
        # Deterministic conformance fingerprint (see canonicalize_manifest_value):
        # dump in python mode so set/frozenset survive, canonicalize (sort sets +
        # dict keys, preserve list order), then stable-encode. Independent of
        # PYTHONHASHSEED / process / container / registration order.
        payload = [
            canonicalize_manifest_value(self._defs[k].model_dump(mode="python"))
            for k in sorted(self._defs)
        ]
        blob = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]

    # ---- shadow evaluation (no execution, no enforcement) ----------------
    def evaluate_action(
        self,
        *,
        tool_name: str,
        tool_version: str | None,
        arguments: dict,
        agent_id: str,
        tenant_id: str,
        idempotency_key: str | None,
        claimed_risk: RiskLane | None,
    ) -> dict:
        names = {n for (n, _) in self._defs}
        out: dict[str, Any] = {
            "registry_comparison": None,
            "resolved_tool_name": None,
            "resolved_tool_version": None,
            "schema_validation": None,
            "agent_permission": None,
            "tenant_permission": None,
            "registry_risk_class": None,
            "claimed_risk_class": (claimed_risk.value if claimed_risk else None),
            "risk_class_mismatch": None,
            "authority": None,
            "approval_requirement": None,
            "idempotency_requirement": None,
            "timeout_policy": None,
            "sandbox_requirement": None,
            "would_allow": None,
            "would_require_approval": None,
            "would_deny": None,
            "would_deny_reason": None,
        }
        if tool_name not in names:
            out.update(
                registry_comparison=RegistryStatus.UNREGISTERED_TOOL.value,
                would_allow=False,
                would_deny=True,
                would_require_approval=False,
                would_deny_reason="tool not in canonical registry (fail-closed)",
            )
            return out
        defn = self.resolve(tool_name, tool_version)
        if defn is None:
            out.update(
                registry_comparison=RegistryStatus.VERSION_MISMATCH.value,
                resolved_tool_name=tool_name,
                would_allow=False,
                would_deny=True,
                would_deny_reason=f"version {tool_version} not registered",
            )
            return out
        out.update(
            resolved_tool_name=defn.name,
            resolved_tool_version=defn.version,
            registry_risk_class=defn.risk_class.value,
            authority=defn.authority.value,
            timeout_policy=defn.timeout_seconds,
            sandbox_requirement=defn.sandbox_required,
        )
        if not defn.enabled_by_default:
            out.update(
                registry_comparison=RegistryStatus.DISABLED.value,
                would_allow=False,
                would_deny=True,
                would_deny_reason="tool disabled",
            )
            return out
        ok_schema, serr = _minimal_schema_check(defn.input_schema, arguments)
        out["schema_validation"] = ok_schema
        if not ok_schema:
            out.update(
                registry_comparison=RegistryStatus.SCHEMA_MISMATCH.value,
                would_allow=False,
                would_deny=True,
                would_deny_reason=f"schema: {serr}",
            )
            return out
        agent_ok = self.is_agent_allowed(defn, agent_id)
        tenant_ok = self.is_tenant_scope_allowed(defn, tenant_id)
        out["agent_permission"] = agent_ok
        out["tenant_permission"] = tenant_ok
        if not agent_ok:
            out.update(
                registry_comparison=RegistryStatus.AGENT_NOT_ALLOWED.value,
                would_allow=False,
                would_deny=True,
                would_deny_reason=f"agent {agent_id} not allowed",
            )
            return out
        if not tenant_ok:
            out.update(
                registry_comparison=RegistryStatus.TENANT_NOT_ALLOWED.value,
                would_allow=False,
                would_deny=True,
                would_deny_reason="tenant scope not allowed",
            )
            return out
        out["idempotency_requirement"] = defn.requires_idempotency
        if defn.requires_idempotency and not idempotency_key:
            out.update(
                registry_comparison=RegistryStatus.IDEMPOTENCY_REQUIRED.value,
                would_allow=False,
                would_deny=True,
                would_deny_reason="mutation requires idempotency key",
            )
            return out
        # risk-class mismatch (registry wins; a claim cannot downgrade)
        mism = claimed_risk is not None and claimed_risk != defn.risk_class
        out["risk_class_mismatch"] = mism
        # authority + lane decide would_* (registry authoritative)
        red = defn.risk_class is RiskLane.RED or defn.authority is AuthorityClass.ALWAYS_REFUSED
        amber = (
            defn.risk_class is RiskLane.AMBER
            or defn.authority
            in (AuthorityClass.APPROVAL_REQUIRED, AuthorityClass.OWNER_OS_REQUIRED)
            or defn.requires_approval
        )
        out["approval_requirement"] = bool(amber and not red)
        if red:
            out.update(
                registry_comparison=RegistryStatus.REGISTRY_MATCH.value,
                would_allow=False,
                would_deny=True,
                would_require_approval=False,
                would_deny_reason="authority ALWAYS_REFUSED / RED lane",
            )
        elif amber:
            out.update(
                registry_comparison=(
                    RegistryStatus.RISK_CLASS_MISMATCH.value
                    if mism
                    else RegistryStatus.REGISTRY_MATCH.value
                ),
                would_allow=False,
                would_require_approval=True,
                would_deny=False,
                would_deny_reason=None,
            )
        else:
            out.update(
                registry_comparison=(
                    RegistryStatus.RISK_CLASS_MISMATCH.value
                    if mism
                    else RegistryStatus.REGISTRY_MATCH.value
                ),
                would_allow=True,
                would_require_approval=False,
                would_deny=False,
            )
        return out


REGISTRY = CanonicalToolRegistry()


def _safe_calculation_executor():  # explicit executor mapping (never auto-discovered)
    return "app.agents.batch_harness:<caller-provided GREEN async fn>"


def _register_builtins() -> None:
    """Explicit, code-defined built-in tools. No auto-discovery of callables."""
    try:
        REGISTRY.register(
            ToolDefinition(
                name="batch.internal.safe_calculation",
                version="1.0.0",
                description="Deterministic internal read-only calculation over a bounded batch item.",
                input_schema={
                    "type": "object",
                    "properties": {"id": {"type": "string", "maxLength": 200}},
                    "required": ["id"],
                    "additionalProperties": False,
                },
                output_schema={"type": "object"},
                risk_class=RiskLane.GREEN,
                side_effect_class=SideEffectClass.READ_ONLY,
                authority=AuthorityClass.INTERNAL_AUTONOMOUS,
                allowed_agents=frozenset({"nikhil"}),
                allowed_tenant_scopes=frozenset({"__system__"}),
                requires_approval=False,
                requires_idempotency=False,
                timeout_seconds=30,
                cost_class="free",
                sandbox_required=False,
                network_policy="deny",
                executor_ref="app.agents.batch_harness.run_batch(fn=<green_internal>)",
                enabled_by_default=True,
            )
        )
    except Exception:
        pass
    try:
        # Second registry-backed family: dag_engine. Maps the stable, explicitly
        # named internal process-library step 'internal_calculation' — a
        # deterministic read-only calc isolated from business behaviour. NOT a
        # promoted business step, NOT the temporary shadow proof name.
        REGISTRY.register(
            ToolDefinition(
                name="workflow.dag.internal_calculation",
                version="1.0.0",
                description="Deterministic internal read-only DAG calculation step (no I/O, no mutation).",
                input_schema={
                    "type": "object",
                    "properties": {"n": {"type": "integer"}},
                    "required": ["n"],
                    "additionalProperties": True,
                },
                output_schema={"type": "object"},
                risk_class=RiskLane.GREEN,
                side_effect_class=SideEffectClass.NONE,
                authority=AuthorityClass.INTERNAL_AUTONOMOUS,
                allowed_agents=frozenset({"nikhil", "manager"}),
                allowed_tenant_scopes=frozenset({"__system__"}),
                requires_approval=False,
                requires_idempotency=False,
                timeout_seconds=30,
                cost_class="free",
                sandbox_required=False,
                network_policy="deny",
                executor_ref="app.agents.process_library.execute_step(action=internal_calculation)",
                enabled_by_default=True,
            )
        )
    except Exception:
        pass
    try:
        # Third registry-backed family: staff.run_member/Nikhil. HONEST composite
        # classification — run_nikhil() runs revenue_digest + client_health +
        # usage_alerts; usage_alerts CAN send customer-facing upsell emails, so
        # the composite is AMBER / EXTERNAL_SEND / APPROVAL_REQUIRED (NOT a simple
        # autonomous GREEN). Registry classification is authoritative; this is
        # deliberately NOT enforcement-eligible without an approval channel.
        REGISTRY.register(
            ToolDefinition(
                name="agent.nikhil.revenue_operations",
                version="1.0.0",
                description=(
                    "Nikhil Revenue-Ops composite: revenue_digest + client_health + "
                    "usage_alerts. Composite side-effect = WRITE_LOCAL (digests/health "
                    "records) + EXTERNAL_SEND (usage_alerts customer upsell emails). "
                    "Partial-failure independent per component."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "requested_by": {"type": "string", "maxLength": 120},
                        "scope": {"type": "string"},
                    },
                    "required": [],
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "object",
                    "properties": {"ok": {"type": "boolean"}, "results": {"type": "object"}},
                },
                risk_class=RiskLane.AMBER,
                side_effect_class=SideEffectClass.EXTERNAL_SEND,
                authority=AuthorityClass.APPROVAL_REQUIRED,
                allowed_agents=frozenset({"nikhil"}),
                allowed_tenant_scopes=frozenset({"__system__"}),
                requires_approval=True,
                approval_policy="owner_os_amber",
                requires_idempotency=True,
                timeout_seconds=120,
                cost_class="free",
                budget_scope="internal_ops",
                sandbox_required=False,
                network_policy="restricted",
                executor_ref="app.agents.staff.run_nikhil",
                enabled_by_default=True,
            )
        )
    except Exception:
        pass
    try:
        # Fourth registry-backed family: coordinator. ONE honestly-safe delegation
        # is registered: agent.delegate.dev -> downstream _tool_dev = hashtags.research,
        # which is read-only research (no publish/mutate/deploy/code-exec/external-send;
        # template fallback). All OTHER coordinator delegations/tools stay
        # UNREGISTERED_TOOL (isha/kavya/arjun/meera + side-effect agents). The
        # delegation ACT is GREEN internal routing; downstream agent controls remain
        # authoritative. NOT enforcement-wired (no executor binding).
        REGISTRY.register(
            ToolDefinition(
                name="agent.delegate.dev",
                version="1.0.0",
                description=(
                    "Coordinator delegation to Dev (research). Downstream executor "
                    "= app.agents.coordinator._tool_dev -> hashtags.research (read-only, "
                    "no publish/mutate/deploy/exec/external-send)."
                ),
                input_schema={
                    "type": "object",
                    "properties": {"task": {"type": "string", "maxLength": 2000}},
                    "required": [],
                    "additionalProperties": True,
                },
                output_schema={"type": "object"},
                risk_class=RiskLane.GREEN,
                side_effect_class=SideEffectClass.READ_ONLY,
                authority=AuthorityClass.INTERNAL_AUTONOMOUS,
                allowed_agents=frozenset({"dev"}),
                allowed_tenant_scopes=frozenset({"__system__"}),
                requires_approval=False,
                requires_idempotency=False,
                timeout_seconds=30,
                cost_class="free",
                budget_scope="coordinator",
                sandbox_required=False,
                network_policy="restricted",
                executor_ref="app.agents.coordinator._tool_dev (hashtags.research, read-only)",
                enabled_by_default=True,
            )
        )
    except Exception:
        pass
    try:
        # 4b. Sixth family (coordinator continue): agent.delegate.isha. Honest
        # classification: _tool_isha -> post_generator.generate_post = PURE
        # read-only content generation (LLM caption/hashtags/image_idea, no
        # file/DB write, no external send). GREEN/READ_ONLY, same as dev.
        # kavya/arjun/meera stay UNREGISTERED_TOOL by design: _tool_kavya ->
        # staff.run_ops() has data-retention PRUNING (DELETE side-effect),
        # _tool_arjun -> run_qa writes eval records, _tool_meera -> run_trainer
        # writes. Registry classification is authoritative; NOT enforcement-wired.
        REGISTRY.register(
            ToolDefinition(
                name="agent.delegate.isha",
                version="1.0.0",
                description=(
                    "Coordinator delegation to Isha (marketing content). Downstream "
                    "executor = app.agents.coordinator._tool_isha -> post_generator.generate_post "
                    "(pure content-gen, read-only, no publish/mutate/exec/external-send)."
                ),
                input_schema={
                    "type": "object",
                    "properties": {"task": {"type": "string", "maxLength": 2000}},
                    "required": [],
                    "additionalProperties": True,
                },
                output_schema={"type": "object"},
                risk_class=RiskLane.GREEN,
                side_effect_class=SideEffectClass.READ_ONLY,
                authority=AuthorityClass.INTERNAL_AUTONOMOUS,
                allowed_agents=frozenset({"isha"}),
                allowed_tenant_scopes=frozenset({"__system__"}),
                requires_approval=False,
                requires_idempotency=False,
                timeout_seconds=30,
                cost_class="free",
                budget_scope="coordinator",
                sandbox_required=False,
                network_policy="restricted",
                executor_ref="app.agents.coordinator._tool_isha (post_generator.generate_post, read-only)",
                enabled_by_default=True,
            )
        )
    except Exception:
        pass
    try:
        # Fifth family: supervisor/staff_supervisor. The data route REUSES the
        # existing agent.delegate.dev (GREEN, read-only) — one canonical capability
        # invoked from multiple orchestrators, no duplicate policy. The leads route
        # delegates to Rohan, whose canonical role is OUTREACH (customer-facing
        # send). Even though this specific supervisor leads_agent_node only drafts
        # a plan, the SHARED identity agent.delegate.rohan is classified by Rohan's
        # broadest real capability = AMBER / EXTERNAL_SEND / APPROVAL_REQUIRED. NOT
        # forced GREEN. Not enforcement-wired (no executor binding).
        REGISTRY.register(
            ToolDefinition(
                name="agent.delegate.rohan",
                version="1.0.0",
                description=(
                    "Supervisor/coordinator delegation to Rohan (leads/outreach). Rohan's "
                    "canonical capability is customer outreach (email/CRM), so this shared "
                    "identity is AMBER external-send even when a given route only drafts."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "task": {"type": "string", "maxLength": 2000},
                        "route_label": {"type": "string", "maxLength": 60},
                        "supervisor_implementation": {"type": "string", "maxLength": 40},
                        "graph_run_id": {"type": "string", "maxLength": 120},
                        "graph_step": {"type": "integer"},
                    },
                    "required": [],
                    "additionalProperties": True,
                },
                output_schema={"type": "object"},
                risk_class=RiskLane.AMBER,
                side_effect_class=SideEffectClass.EXTERNAL_SEND,
                authority=AuthorityClass.APPROVAL_REQUIRED,
                allowed_agents=frozenset({"rohan"}),
                allowed_tenant_scopes=frozenset({"__system__"}),
                requires_approval=True,
                approval_policy="owner_os_amber",
                requires_idempotency=True,
                timeout_seconds=60,
                cost_class="free",
                budget_scope="supervisor",
                sandbox_required=False,
                network_policy="restricted",
                executor_ref="supervisor.leads_agent_node / staff outreach (Rohan) — approval-gated",
                enabled_by_default=True,
            )
        )
    except Exception:
        pass


_register_builtins()

# Video Production Cell tools (additive; idempotent; fail-soft).
try:
    from app.marketing.video_production.harness_tools import register_video_tools

    register_video_tools()
except Exception:
    pass
