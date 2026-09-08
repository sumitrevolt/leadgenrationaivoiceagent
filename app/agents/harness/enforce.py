"""Inert enforcement pipeline for the agent harness (canary-preparation).

This module adds the *decision + execution* tier that turns the canonical
registry from a record-only classifier into an enforceable gate — for exactly
ONE registered internal GREEN tool, and ONLY when explicit per-agent, per-loop,
per-tool allowlists are set. It is INERT by default:

    AGENT_HARNESS_ENFORCE unset/0  => resolve_mode() never returns ENFORCE.

Design invariants (see docs/runbooks/BATCH_HARNESS_ENFORCEMENT_CANARY.md):
  * evaluate() NEVER executes anything (pure decision).
  * execute_registered() runs ONLY the registry-BOUND executor, at most once
    per (deterministic) execution key, and re-checks the live kill switch.
  * The caller-supplied arbitrary callable is NEVER authoritative in ENFORCE
    mode — the registry-bound executor wins.
  * Owner OS stays the sole mutation authority: OWNER_OS_REQUIRED / APPROVAL /
    ALWAYS_REFUSED / RED / non-GREEN all DENY here (executor never called).
  * No dynamic import / dotted-path / callable scanning: bindings are explicit.
  * Fail-closed everywhere; any ambiguity denies.
"""

from __future__ import annotations

import collections
import os
import time
import uuid
from enum import Enum
from typing import Any, Awaitable, Callable, Optional

from pydantic import BaseModel, ConfigDict, Field

from . import audit
from .contracts import SYSTEM_TENANT, RunContext, ToolCall
from .registry import REGISTRY, AuthorityClass, CanonicalToolRegistry, RegistryStatus, RiskLane
from .stop import StopController

try:
    from app.utils.logger import setup_logger

    logger = setup_logger(__name__)
except Exception:  # pragma: no cover
    import logging

    logger = logging.getLogger(__name__)


_SOURCE_LOOP = "batch_harness"


# --------------------------------------------------------------------------- #
# Mode + denial enums
# --------------------------------------------------------------------------- #
class HarnessMode(str, Enum):
    OFF = "off"
    SHADOW = "shadow"
    ENFORCE = "enforce"


class DenialReason(str, Enum):
    UNREGISTERED_TOOL = "UNREGISTERED_TOOL"
    VERSION_MISMATCH = "VERSION_MISMATCH"
    SCHEMA_MISMATCH = "SCHEMA_MISMATCH"
    AGENT_NOT_ALLOWED = "AGENT_NOT_ALLOWED"
    TENANT_NOT_ALLOWED = "TENANT_NOT_ALLOWED"
    TOOL_DISABLED = "TOOL_DISABLED"
    TOOL_NOT_ALLOWLISTED = "TOOL_NOT_ALLOWLISTED"  # registered but not in canary allowlist
    RISK_NOT_GREEN = "RISK_NOT_GREEN"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    OWNER_OS_REQUIRED = "OWNER_OS_REQUIRED"
    ALWAYS_REFUSED = "ALWAYS_REFUSED"
    IDEMPOTENCY_REQUIRED = "IDEMPOTENCY_REQUIRED"
    SANDBOX_REQUIRED = "SANDBOX_REQUIRED"
    BUDGET_DENIED = "BUDGET_DENIED"
    KILL_SWITCH = "KILL_SWITCH"
    STOP_REQUESTED = "STOP_REQUESTED"
    EXECUTOR_NOT_BOUND = "EXECUTOR_NOT_BOUND"
    EXECUTOR_ERROR = "EXECUTOR_ERROR"
    INVALID_MODE = "INVALID_MODE"
    NOT_ENFORCE_ELIGIBLE = "NOT_ENFORCE_ELIGIBLE"


# --------------------------------------------------------------------------- #
# Flag helpers (read at call-time; repo convention)
# --------------------------------------------------------------------------- #
def _flag_on(name: str) -> bool:
    v = (os.getenv(name) or "").strip().lower()
    return bool(v) and v not in ("0", "false", "no", "off")


def _csv_set(name: str) -> set[str]:
    raw = (os.getenv(name) or "").strip()
    return {p.strip().lower() for p in raw.split(",") if p.strip()}


def resolve_mode(
    *, agent_id: str, source_loop: str, tool_token: str | None = None
) -> tuple[HarnessMode, list[str]]:
    """Deterministic mode resolver. Fail-closed: any invalid/ambiguous combo -> OFF.

    tool_token (optional) = "<name>@<version>" for per-tool allowlist refinement.
    Run-level callers pass tool_token=None (agent+loop eligibility only); the
    per-item gate re-checks the exact tool allowlist."""
    notes: list[str] = []
    if not _flag_on("AGENT_HARNESS"):
        return HarnessMode.OFF, ["harness_disabled"]
    shadow = _flag_on("AGENT_HARNESS_SHADOW")
    enforce = _flag_on("AGENT_HARNESS_ENFORCE")
    if shadow and enforce:
        # Invalid: never silently pick a mode. Safest convention = OFF (no
        # enforcement AND no shadow) so nothing executes and nothing is observed
        # under an ambiguous configuration.
        return HarnessMode.OFF, ["INVALID_MODE:shadow+enforce_both_set->fail_closed_off"]
    if enforce:
        aid = (agent_id or "").strip().lower()
        loop = (source_loop or "").strip().lower()
        loops = _csv_set("AGENT_HARNESS_ENFORCE_LOOPS")
        agents = _csv_set("AGENT_HARNESS_ENFORCE_AGENTS")
        tools = _csv_set("AGENT_HARNESS_ENFORCE_TOOLS")
        # No wildcard support in the first canary — a wildcard is a config error.
        if "*" in loops or "*" in agents or "*" in tools:
            return HarnessMode.OFF, ["INVALID_MODE:wildcard_not_allowed_in_first_canary"]
        if not loops or loop not in loops:
            return HarnessMode.OFF, ["loop_not_allowlisted"]
        if not agents or aid not in agents:
            return HarnessMode.OFF, ["agent_not_allowlisted"]
        if tool_token is not None and (not tools or tool_token.lower() not in tools):
            return HarnessMode.OFF, ["tool_not_allowlisted"]
        return HarnessMode.ENFORCE, notes
    if shadow:
        return HarnessMode.SHADOW, notes
    return HarnessMode.OFF, ["no_mode_flag"]


# --------------------------------------------------------------------------- #
# Executor binding (explicit only; never auto-discovers callables)
# --------------------------------------------------------------------------- #
ExecutorFn = Callable[..., Awaitable[Any]]


class ExecutorBindingConflict(Exception):
    pass


class ExecutorBindingRegistry:
    """Maps exact (tool_name, version) -> an async callable. No dynamic import,
    no dotted-path resolution, no scanning. Callables are NEVER exposed through a
    read API (only names/versions are listable)."""

    def __init__(self) -> None:
        self._b: dict[tuple[str, str], ExecutorFn] = {}

    def bind(self, name: str, version: str, fn: ExecutorFn) -> None:
        key = (name, version)
        existing = self._b.get(key)
        if existing is not None:
            if existing is fn:
                return  # idempotent identical binding
            raise ExecutorBindingConflict(f"conflicting executor binding for {name}@{version}")
        if not callable(fn):
            raise ExecutorBindingConflict(f"executor for {name}@{version} is not callable")
        self._b[key] = fn

    def get(self, name: str, version: str) -> ExecutorFn | None:
        return self._b.get((name, version))

    def is_bound(self, name: str, version: str) -> bool:
        return (name, version) in self._b

    def bound_identities(self) -> list[str]:
        """Listing-safe: identities only, NEVER the callables."""
        return sorted(f"{n}@{v}" for (n, v) in self._b)


EXECUTORS = ExecutorBindingRegistry()


# --------------------------------------------------------------------------- #
# Enforcement decision contract (immutable)
# --------------------------------------------------------------------------- #
class EnforcementDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    allowed: bool
    mode: HarnessMode

    tool_name: str
    tool_version: str

    registry_status: str | None = None
    schema_valid: bool | None = None
    agent_allowed: bool | None = None
    tenant_allowed: bool | None = None

    risk_lane: RiskLane | None = None
    authority: AuthorityClass | None = None

    approval_required: bool = False
    idempotency_required: bool = False
    sandbox_required: bool = False
    owner_os_routing_required: bool = False

    executor_bound: bool = False
    budget_allowed: bool | None = None
    kill_switch_clear: bool | None = None
    stop_allowed: bool | None = None

    denial_reasons: list[str] = Field(default_factory=list)
    decision_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    execution_key: str = ""

    @property
    def allowed_for_enforcement(self) -> bool:
        return self.allowed and not self.denial_reasons


# --------------------------------------------------------------------------- #
# Exactly-once execution guard (harness-specific; separate from prod idempotency)
# --------------------------------------------------------------------------- #
_INFLIGHT: collections.OrderedDict[str, int] = collections.OrderedDict()
_RESULTS: collections.OrderedDict[str, Any] = collections.OrderedDict()
_GUARD_MAX = 8192


def _claim(key: str) -> bool:
    """Synchronous check-and-set (no await inside). Returns True if NEWLY claimed
    (caller may execute); False if already claimed (duplicate -> suppress)."""
    if key in _INFLIGHT:
        return False
    _INFLIGHT[key] = 1
    if len(_INFLIGHT) > _GUARD_MAX:
        _INFLIGHT.popitem(last=False)
    return True


def _store_result(key: str, result: Any) -> None:
    _RESULTS[key] = result
    if len(_RESULTS) > _GUARD_MAX:
        _RESULTS.popitem(last=False)


def _reset_guard() -> None:
    """Test-only: clear the exactly-once guard state."""
    _INFLIGHT.clear()
    _RESULTS.clear()


# --------------------------------------------------------------------------- #
# Enforcement gate — separates evaluation from execution
# --------------------------------------------------------------------------- #
class EnforcementGate:
    def __init__(
        self,
        registry: CanonicalToolRegistry | None = None,
        executors: ExecutorBindingRegistry | None = None,
        stop: StopController | None = None,
    ) -> None:
        self.registry = registry or REGISTRY
        self.executors = executors or EXECUTORS
        self.stop = stop or StopController()

    # ---- evaluate: PURE decision; NEVER executes ----------------------
    def evaluate(
        self,
        ctx: RunContext,
        action_request: ToolCall,
        *,
        mode: HarnessMode,
        est_usd: float = 0.0,
        est_tokens: int = 0,
        execution_key: str = "",
    ) -> EnforcementDecision:
        name = action_request.name
        ver = action_request.tool_version or ""
        reasons: list[str] = []
        fields: dict[str, Any] = {}

        if mode is not HarnessMode.ENFORCE:
            reasons.append(DenialReason.INVALID_MODE.value)
            return EnforcementDecision(
                allowed=False,
                mode=mode,
                tool_name=name,
                tool_version=ver,
                denial_reasons=reasons,
                execution_key=execution_key,
            )

        # exact tool/version allowlist (no wildcard)
        tools = _csv_set("AGENT_HARNESS_ENFORCE_TOOLS")
        token = f"{name}@{ver}".lower()

        # registry decision (authoritative risk/authority/schema/permission)
        from .registry import claimed_lane

        reg = self.registry.evaluate_action(
            tool_name=name,
            tool_version=(ver or None),
            arguments=action_request.args,
            agent_id=ctx.agent,
            tenant_id=ctx.tenant_id,
            idempotency_key=action_request.idempotency_key,
            claimed_risk=claimed_lane(action_request.risk_class),
        )
        rc = reg.get("registry_comparison")
        fields.update(
            registry_status=rc,
            schema_valid=reg.get("schema_validation"),
            agent_allowed=reg.get("agent_permission"),
            tenant_allowed=reg.get("tenant_permission"),
        )
        _RS = RegistryStatus
        _map = {
            _RS.UNREGISTERED_TOOL.value: DenialReason.UNREGISTERED_TOOL,
            _RS.VERSION_MISMATCH.value: DenialReason.VERSION_MISMATCH,
            _RS.SCHEMA_MISMATCH.value: DenialReason.SCHEMA_MISMATCH,
            _RS.AGENT_NOT_ALLOWED.value: DenialReason.AGENT_NOT_ALLOWED,
            _RS.TENANT_NOT_ALLOWED.value: DenialReason.TENANT_NOT_ALLOWED,
            _RS.DISABLED.value: DenialReason.TOOL_DISABLED,
            _RS.IDEMPOTENCY_REQUIRED.value: DenialReason.IDEMPOTENCY_REQUIRED,
        }
        if rc in _map:
            reasons.append(_map[rc].value)

        defn = (
            self.registry.resolve(name, ver or None)
            if rc not in (_RS.UNREGISTERED_TOOL.value, _RS.VERSION_MISMATCH.value)
            else None
        )
        if defn is not None:
            fields.update(
                risk_lane=defn.risk_class,
                authority=defn.authority,
                idempotency_required=defn.requires_idempotency,
                sandbox_required=defn.sandbox_required,
            )
            # tool must be in the exact canary allowlist
            if not tools or token not in tools:
                reasons.append(DenialReason.TOOL_NOT_ALLOWLISTED.value)
            # authority + risk (registry authoritative — a claim cannot downgrade)
            if defn.authority is AuthorityClass.ALWAYS_REFUSED:
                reasons.append(DenialReason.ALWAYS_REFUSED.value)
            if defn.risk_class is not RiskLane.GREEN:
                reasons.append(DenialReason.RISK_NOT_GREEN.value)
            if defn.authority is AuthorityClass.OWNER_OS_REQUIRED:
                reasons.append(DenialReason.OWNER_OS_REQUIRED.value)
                fields["owner_os_routing_required"] = True
            if defn.authority is AuthorityClass.APPROVAL_REQUIRED or defn.requires_approval:
                reasons.append(DenialReason.APPROVAL_REQUIRED.value)
                fields["approval_required"] = True
            if defn.sandbox_required:
                reasons.append(DenialReason.SANDBOX_REQUIRED.value)
            # executor binding must exist
            bound = self.executors.is_bound(defn.name, defn.version)
            fields["executor_bound"] = bound
            if not bound:
                reasons.append(DenialReason.EXECUTOR_NOT_BOUND.value)
        else:
            fields["executor_bound"] = False

        # independent run-controls (reported even if registry already denied)
        budget_ok = self.stop.admit(ctx, est_usd, est_tokens)
        kill_clear = not self.stop.killed(ctx)
        cont, _reason = self.stop.check(ctx)
        fields.update(budget_allowed=budget_ok, kill_switch_clear=kill_clear, stop_allowed=cont)
        if not budget_ok:
            reasons.append(DenialReason.BUDGET_DENIED.value)
        if not kill_clear:
            reasons.append(DenialReason.KILL_SWITCH.value)
        if not cont:
            reasons.append(DenialReason.STOP_REQUESTED.value)

        allowed = not reasons
        return EnforcementDecision(
            allowed=allowed,
            mode=mode,
            tool_name=name,
            tool_version=ver,
            denial_reasons=reasons,
            execution_key=execution_key,
            **fields,
        )

    # ---- execute: ONLY the registry-bound executor, at most once ------
    async def execute_registered(
        self, ctx: RunContext, action_request: ToolCall, decision: EnforcementDecision
    ) -> tuple[bool, Any, str | None, bool]:
        """Returns (ok, output, error, duplicate_suppressed). Executes the
        registry-BOUND executor exactly once. The caller-supplied arbitrary
        callable is never touched here."""
        if not decision.allowed_for_enforcement:
            return False, None, "decision_not_allowed", False
        # Atomic re-check of the live kill switch (TOCTOU between evaluate/execute).
        if self.stop.killed(ctx):
            return False, None, DenialReason.KILL_SWITCH.value, False
        fn = self.executors.get(action_request.name, action_request.tool_version)
        if fn is None:
            return False, None, DenialReason.EXECUTOR_NOT_BOUND.value, False
        key = decision.execution_key or action_request.idempotency_key or decision.decision_id
        # Synchronous exactly-once claim (no await before this line).
        if not _claim(key):
            prev = _RESULTS.get(key)
            return True, prev, None, True  # duplicate -> replay, no second execution
        try:
            out = await fn(**dict(action_request.args or {}))
            _store_result(key, out)
            return True, out, None, False
        except Exception as e:
            return False, None, f"{DenialReason.EXECUTOR_ERROR.value}: {str(e)[:200]}", False


# --------------------------------------------------------------------------- #
# Audit events (bounded; no secrets)
# --------------------------------------------------------------------------- #
def _audit_event(
    ctx: RunContext,
    call: ToolCall | None,
    event: str,
    decision: EnforcementDecision | None = None,
    **extra: Any,
) -> None:
    try:
        row: dict[str, Any] = {
            "event": event,
            "mode": HarnessMode.ENFORCE.value,
            "layer": "enforcement",
            "enforcement": True,
        }
        if decision is not None:
            row.update(
                decision_id=decision.decision_id,
                execution_key=decision.execution_key,
                tool_name=decision.tool_name,
                tool_version=decision.tool_version,
                risk=(decision.risk_lane.value if decision.risk_lane else None),
                authority=(decision.authority.value if decision.authority else None),
                denial_reasons=list(decision.denial_reasons),
                registry_status=decision.registry_status,
            )
        row.update(extra)
        audit.record(ctx, call, None, kind="enforce", extra=row)
    except Exception as e:  # audit must never break the batch
        logger.warning("harness.enforce: audit event failed: %s", e)


async def enforce_batch_item(
    *,
    ctx: RunContext,
    batch_run_id: str,
    item_id: str,
    item_index: int,
    attempt: int,
    tool_name: str,
    tool_version: str,
    item: Any,
    gate: EnforcementGate | None = None,
) -> dict:
    """Governed execution of ONE batch item in ENFORCE mode. The caller's
    arbitrary `fn` is NOT passed here and NEVER runs — only the registry-bound
    executor for `tool_name@tool_version` may execute, and only if every gate
    passes. NEVER raises into the batch."""
    gate = gate or EnforcementGate()
    name = tool_name or f"batch.execute.{item_id}"  # no canonical id => unregistered => deny
    ver = tool_version or ""
    exec_key = f"enforce:{batch_run_id}:{item_id}:{attempt}"
    args = item if isinstance(item, dict) else {"item": str(item)}
    try:
        from .contracts import RiskClass

        req = ToolCall(
            name=name,
            args=args,
            tool_version=ver,
            risk_class=RiskClass.READ,
            idempotency_key=exec_key,
            reason="enforced batch item",
            expected_effect=f"batch {batch_run_id} item {item_id}",
        )
    except Exception as e:
        _audit_event(
            ctx,
            None,
            "enforcement_failed",
            None,
            item_id=item_id,
            error=f"action_request_build: {str(e)[:120]}",
        )
        return {"ok": False, "denied": True, "reasons": ["ACTION_REQUEST_INVALID"], "result": None}

    _audit_event(
        ctx,
        req,
        "enforcement_requested",
        None,
        item_id=item_id,
        item_index=item_index,
        batch_run_id=batch_run_id,
    )
    decision = gate.evaluate(ctx, req, mode=HarnessMode.ENFORCE, execution_key=exec_key)
    _audit_event(
        ctx,
        req,
        "enforcement_evaluated",
        decision,
        item_id=item_id,
        executor_called=False,
        result_status="evaluated",
    )

    if not decision.allowed_for_enforcement:
        _audit_event(
            ctx,
            req,
            "enforcement_denied",
            decision,
            item_id=item_id,
            executor_called=False,
            result_status="denied",
        )
        return {
            "ok": False,
            "denied": True,
            "reasons": list(decision.denial_reasons),
            "result": None,
            "decision_id": decision.decision_id,
        }

    t0 = time.time()
    _audit_event(ctx, req, "enforcement_started", decision, item_id=item_id, executor_called=True)
    ok, out, err, dup = await gate.execute_registered(ctx, req, decision)
    latency = int((time.time() - t0) * 1000)
    if dup:
        _audit_event(
            ctx,
            req,
            "enforcement_duplicate_suppressed",
            decision,
            item_id=item_id,
            executor_called=False,
            result_status="duplicate",
            latency_ms=latency,
        )
        return {"ok": True, "duplicate": True, "result": out, "decision_id": decision.decision_id}
    if ok:
        _audit_event(
            ctx,
            req,
            "enforcement_completed",
            decision,
            item_id=item_id,
            executor_called=True,
            result_status="ok",
            latency_ms=latency,
        )
        return {"ok": True, "result": out, "decision_id": decision.decision_id}
    _audit_event(
        ctx,
        req,
        "enforcement_failed",
        decision,
        item_id=item_id,
        executor_called=True,
        result_status="error",
        error=err,
        latency_ms=latency,
    )
    return {
        "ok": False,
        "denied": False,
        "error": err,
        "result": None,
        "decision_id": decision.decision_id,
    }


# --------------------------------------------------------------------------- #
# Built-in registry-bound executor (explicit; deterministic; side-effect-free)
# --------------------------------------------------------------------------- #
_SAFE_CALLS = {"n": 0}  # observable call counter for proofs (no system side effect)


async def _safe_calculation_executor(id: str) -> dict:
    """Deterministic, internal, read-only calculation over one bounded item.
    No I/O, no network, no mutation — the only GREEN enforcement candidate."""
    _SAFE_CALLS["n"] += 1
    digest = 0
    for ch in str(id):
        digest = (digest * 31 + ord(ch)) & 0xFFFFFFFF
    return {
        "ok": True,
        "id": id,
        "value": digest % 1000,
        "tool": "batch.internal.safe_calculation",
        "summary": f"calc({id})={digest % 1000}",
    }


def _bind_builtins() -> None:
    try:
        EXECUTORS.bind("batch.internal.safe_calculation", "1.0.0", _safe_calculation_executor)
    except Exception as e:  # pragma: no cover
        logger.warning("harness.enforce: builtin bind failed: %s", e)


_bind_builtins()


def enforcement_state() -> dict:
    """Read-only snapshot of enforcement config + bindings (no callables)."""
    return {
        "AGENT_HARNESS": _flag_on("AGENT_HARNESS"),
        "AGENT_HARNESS_SHADOW": _flag_on("AGENT_HARNESS_SHADOW"),
        "AGENT_HARNESS_ENFORCE": _flag_on("AGENT_HARNESS_ENFORCE"),
        "enforce_agents": sorted(_csv_set("AGENT_HARNESS_ENFORCE_AGENTS")),
        "enforce_loops": sorted(_csv_set("AGENT_HARNESS_ENFORCE_LOOPS")),
        "enforce_tools": sorted(_csv_set("AGENT_HARNESS_ENFORCE_TOOLS")),
        "bound_executors": EXECUTORS.bound_identities(),
        "resolved_batch_mode": resolve_mode(agent_id="nikhil", source_loop=_SOURCE_LOOP)[0].value,
    }
