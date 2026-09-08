"""
The single typed agent loop — the control tier (VA-01/02, PM-01/03, SB-04,
DL-01, OB-01, ST-01/02/03, GV-01).

This is deliberately NOT a new agent framework. It is the one ordered pipeline
every tool call passes through so that controls are enforced consistently. The
existing engines (`dag_engine.execute_step`, `coordinator._TOOLS`) call
``Harness.step()`` instead of executing tools directly, behind ``AGENT_HARNESS=1``.

Ordered pipeline for every ToolCall:
    1. VA-01  schema validate args           (tool_registry.validate)
    2. VA-02  argument bounds                 (args_schema validators)
    3. PM-01  least-privilege permit          (tool_registry.permit -> agent_permissions)
    4. ST-01  pre-spend admission             (StopController.admit, fail-closed)
    5. PM-03  approval gate if dangerous      (risk_approve / ApprovalQueue)
    6. SB-04  checkpoint if mutating          (agent_checkpoints.snapshot)
    7. DL-01  outbound content scan           (egress_scan hook)
    8. exec   in sandbox for CODE_EXEC        (Sandbox) else registered fn
    9. OB-01  trace + audit.record            (observability_llm / audit)
   10. ST-02  progress + stop check           (StopController.check)

GV-01 is structural: the model only ever produces a ``ToolCall`` (never runs
anything itself), and its ``reason`` is audited but never trusted for control.
"""

from __future__ import annotations

import os
import time
from typing import Awaitable, Callable, List, Optional, Tuple

from pydantic import ValidationError

from . import audit, session
from .contracts import DANGEROUS, MUTATING, RiskClass, RunContext, StopReason, ToolCall, ToolResult
from .sandbox import Sandbox, SandboxPolicy
from .stop import Budget, StopController
from .tool_registry import REGISTRY, PermissionError_, ToolRegistry

try:
    from app.utils.logger import setup_logger  # type: ignore

    logger = setup_logger(__name__)
except Exception:  # pragma: no cover
    import logging

    logger = logging.getLogger(__name__)


def enabled() -> bool:
    """INERT-default flag, matching the repo convention (AGENT_RUNTIME etc.)."""
    return os.getenv("AGENT_HARNESS", "0") == "1"


# Approval callback: (ctx, call, spec_risk) -> bool. Defaults to the repo's
# risk_approve when present; otherwise deny dangerous calls (fail-closed).
ApprovalFn = Callable[[RunContext, ToolCall, RiskClass], Awaitable[bool]]
# Egress/content scan: (ctx, call) -> (allowed, reason). DL-01.
EgressScanFn = Callable[[RunContext, ToolCall], tuple[bool, str]]
# dsh-style agent/pre-step: True = continue, False = reject the turn (ST-03-adjacent).
PreStepFn = Callable[[RunContext], Awaitable[bool]]


async def _default_approval(ctx: RunContext, call: ToolCall, risk: RiskClass) -> bool:
    """Fail-closed. A dangerous action is approved ONLY when it carries an explicit
    Owner OS approval reference. We never auto-approve via a heuristic scorer — the
    real approval channel is Kavach -> Owner OS (AMBER parks for human decision)."""
    if call.approval_reference:
        return True
    # Best-effort: register the pending action for the human queue, then HOLD.
    try:
        from app.agents import risk_approve  # type: ignore

        enq = getattr(risk_approve, "enqueue", None) or getattr(
            risk_approve, "request_approval", None
        )
        if callable(enq):
            enq(run_id=ctx.run_id, tool=call.name, args=call.args)
    except Exception as e:
        logger.warning("harness.loop: approval enqueue errored (still holding): %s", e)
    return False  # hold for Owner OS / human


def _default_egress_scan(ctx: RunContext, call: ToolCall) -> tuple[bool, str]:
    """DL-01 placeholder that refuses obviously secret-bearing outbound payloads.
    Replace with your real content/diff scanner. Fail-closed on error."""
    try:
        blob = str(call.args).lower()
        for frag in ("sk_", "api_key", "authorization", "-----begin"):
            if frag in blob:
                return False, f"outbound payload contains secret-like token {frag!r}"
        return True, "ok"
    except Exception:
        return False, "egress scan error"


async def _checkpoint(ctx: RunContext, call: ToolCall) -> None:
    """SB-04 — checkpoint before a mutating action.

    File-mutating tools declare ``paths`` in their args -> real file snapshot via
    the repo's agent_checkpoints.snapshot(paths, label). For non-file mutations
    (external send, billing) there is nothing to file-snapshot; the idempotency
    key + audit marker are the replay-safety guarantee, so we record a logical
    checkpoint instead of calling snapshot with the wrong shape."""
    label = f"pre:{call.name}:{call.call_id}"
    paths = call.args.get("paths")
    try:
        if isinstance(paths, list) and paths:
            from app.agents import agent_checkpoints  # type: ignore

            snap = getattr(agent_checkpoints, "snapshot", None)
            if callable(snap):
                snap(paths, label)  # repo signature: snapshot(paths, label="")
        else:
            audit.record(
                ctx,
                call,
                None,
                kind="checkpoint",
                extra={"logical": True, "idempotency_key": call.idempotency_key},
            )
    except Exception as e:
        logger.warning("harness.loop: checkpoint failed (continuing): %s", e)


import hashlib as _hashlib
import json as _json

_SECRET_FRAGS = (
    "key",
    "token",
    "secret",
    "password",
    "authorization",
    "bearer",
    "api_key",
    "vpa",
    "credential",
    "private",
)


def _args_hash(args) -> str:
    try:
        return _hashlib.sha1(
            _json.dumps(args, sort_keys=True, default=str).encode("utf-8"),
            usedforsecurity=False,
        ).hexdigest()[:16]
    except Exception:
        return "unhashable"


def _legacy_status(result) -> str:
    if isinstance(result, dict):
        if result.get("error"):
            return "error"
        if result.get("skipped"):
            return "skipped"
        if result.get("ok") is True:
            return "ok"
    if result is None:
        return "unknown"
    return "ok"


def _redact(obj):
    """Shallow/deep redaction of secret-like keys and obvious secret values."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if any(f in str(k).lower() for f in _SECRET_FRAGS):
                out[k] = "***REDACTED***"
            else:
                out[k] = _redact(v)
        return out
    if isinstance(obj, list):
        return [_redact(x) for x in obj[:50]]
    if isinstance(obj, str) and (
        obj.startswith("sk-")
        or obj.startswith("sk_")
        or obj.startswith("Bearer ")
        or "BEGIN PRIVATE" in obj
    ):
        return "***REDACTED***"
    return obj


def _bounded_summary(result, limit: int = 600):
    red = _redact(result)  # redact keys/values BEFORE serializing
    try:
        s = red if isinstance(red, str) else _json.dumps(red, default=str)
    except Exception:
        return "<unserializable>"
    return s[:limit]


class Harness:
    """One instance per run (cheap)."""

    def __init__(
        self,
        registry: ToolRegistry | None = None,
        budget: Budget | None = None,
        approval: ApprovalFn | None = None,
        egress_scan: EgressScanFn | None = None,
        sandbox_policy: SandboxPolicy | None = None,
        pre_step: PreStepFn | None = None,
    ) -> None:
        self.registry = registry or REGISTRY
        self.stop = StopController(budget)
        self.approval = approval or _default_approval
        self.egress_scan = egress_scan or _default_egress_scan
        self.sandbox = Sandbox(sandbox_policy)
        self.pre_step = pre_step

    async def step(
        self,
        ctx: RunContext,
        call: ToolCall,
        profile: str = "default",
        est_usd: float = 0.0,
        est_tokens: int = 0,
    ) -> ToolResult:
        """Run ONE tool call through every control. Never raises — returns a
        ToolResult with ok=False and the control trail on any refusal/error."""
        t0 = time.time()
        res = ToolResult(call_id=call.call_id, ok=False)
        trail = res.control_trail  # bind to the model's own list (pydantic copies on init)

        # Kill switch first (ST-03).
        if self.stop.killed(ctx):
            res.error = "kill_switch"
            trail.append("ST-03:killed")
            audit.record(ctx, call, res, kind="stop")
            return res

        # 1-2. VA-01 / VA-02
        try:
            parsed = self.registry.validate(call)
            trail.append("VA-01/02:valid")
        except (ValidationError, KeyError) as e:
            res.error = f"schema/bounds reject: {e}"
            trail.append("VA-01/02:reject")
            audit.record(ctx, call, res, kind="step")
            return res

        # 3. PM-01 permit (fail-closed)
        try:
            spec = self.registry.permit(ctx.agent, profile, call)
            trail.append("PM-01:permit")
        except PermissionError_ as e:
            res.error = str(e)
            trail.append("PM-01:deny")
            audit.record(ctx, call, res, kind="step")
            return res

        # 3b. Mutating actions MUST carry an idempotency key (spec: no duplicate effects).
        if spec.risk in MUTATING and not call.idempotency_key:
            res.error = "missing idempotency_key for mutating action"
            trail.append("VA-02:no-idempotency")
            audit.record(ctx, call, res, kind="step")
            return res

        # 4. ST-01 pre-spend admission (fail-closed)
        if not self.stop.admit(ctx, est_usd, est_tokens):
            res.error = "budget admission denied"
            trail.append("ST-01:deny")
            audit.record(ctx, call, res, kind="stop")
            return res

        # 5. PM-03 approval if dangerous
        if spec.risk in DANGEROUS:
            ok = await self.approval(ctx, call, spec.risk)
            if not ok:
                res.error = "awaiting/denied human approval"
                trail.append("PM-03:hold")
                audit.record(ctx, call, res, kind="approval")
                return res
            trail.append("PM-03:approved")

        # 6. SB-04 checkpoint if mutating
        if spec.risk in MUTATING:
            await _checkpoint(ctx, call)
            trail.append("SB-04:checkpoint")

        # 7. DL-01 outbound scan for external sends
        if spec.risk in (RiskClass.EXTERNAL_SEND, RiskClass.TELEPHONY, RiskClass.MONEY):
            allowed, why = self.egress_scan(ctx, call)
            if not allowed:
                res.error = f"DL-01 blocked: {why}"
                trail.append("DL-01:block")
                audit.record(ctx, call, res, kind="step")
                return res
            trail.append("DL-01:clean")

        # 8. execute
        try:
            if spec.risk is RiskClass.CODE_EXEC:
                sbx = await self.sandbox.run_python(call.args.get("script", ""))
                res.ok = sbx.ok
                res.output = {
                    "stdout": sbx.stdout,
                    "stderr": sbx.stderr,
                    "exit_code": sbx.exit_code,
                    "timed_out": sbx.timed_out,
                }
                trail.append("SB-01:sandboxed")
            else:
                res.output = await spec.fn(**parsed.model_dump())
                res.ok = True
            trail.append("exec:done")
        except Exception as e:
            res.ok = False
            res.error = f"tool error: {e}"
            trail.append("exec:error")

        # 9. accounting + trace (OB-01)
        res.cost_usd = est_usd
        res.tokens = est_tokens
        res.latency_ms = int((time.time() - t0) * 1000)
        ctx.tool_calls += 1
        ctx.spent_usd += est_usd
        ctx.spent_tokens += est_tokens
        self.stop.record_progress(ctx, res.output)
        audit.record(ctx, call, res, kind="step")
        return res

    # ---- record-only evaluation (SHADOW) -----------------------------
    def evaluate(
        self,
        ctx: RunContext,
        call: ToolCall,
        profile: str = "default",
        est_usd: float = 0.0,
        est_tokens: int = 0,
    ) -> dict:
        """Run every control DECISION that step() would, but NEVER execute the
        tool. Pure function over the request + context. Returns a decision dict."""
        d = {
            "would_validate": None,
            "would_allow": None,
            "would_require_approval": None,
            "would_checkpoint": None,
            "would_deny_reason": None,
            "predicted_lane": None,
            "budget_decision": None,
            "stop_decision": None,
            "risk_class": None,
        }
        if self.stop.killed(ctx):
            d["stop_decision"] = "kill_switch"
        try:
            self.registry.validate(call)
            d["would_validate"] = True
        except (ValidationError, KeyError) as e:
            d.update(
                would_validate=False,
                would_allow=False,
                would_deny_reason=f"schema/bounds: {e}",
                predicted_lane="RED",
            )
            return d
        try:
            spec = self.registry.permit(ctx.agent, profile, call)
            d["would_allow"] = True
        except PermissionError_ as e:
            d.update(would_allow=False, would_deny_reason=str(e), predicted_lane="RED")
            return d
        d["risk_class"] = spec.risk.value
        if spec.risk in MUTATING and not call.idempotency_key:
            d.update(
                would_allow=False,
                would_deny_reason="missing idempotency_key (mutating)",
                predicted_lane="RED",
            )
            return d
        d["budget_decision"] = "admit" if self.stop.admit(ctx, est_usd, est_tokens) else "deny"
        if d["budget_decision"] == "deny":
            d.update(
                would_allow=False, would_deny_reason="budget admission denied", predicted_lane="RED"
            )
            return d
        d["would_require_approval"] = spec.risk in DANGEROUS
        d["would_checkpoint"] = spec.risk in MUTATING
        cont, reason = self.stop.check(ctx)
        d["stop_decision"] = "continue" if cont else (reason.value if reason else "stop")
        d["predicted_lane"] = "AMBER" if d["would_require_approval"] else "GREEN"
        return d

    def observe(
        self,
        ctx: RunContext,
        action_request: ToolCall,
        actual_result=None,
        actual_error=None,
        execution_metadata: dict | None = None,
        profile: str = "default",
    ) -> dict:
        """SHADOW, record-only. Evaluate controls, compare proposed-vs-actual,
        persist a bounded/redacted audit row. NEVER executes the tool and NEVER
        affects legacy control flow. Returns the shadow record."""
        from .contracts import ComparisonVerdict

        meta = execution_metadata or {}
        try:
            d = self.evaluate(
                ctx,
                action_request,
                profile=profile,
                est_usd=meta.get("est_usd", 0.0),
                est_tokens=meta.get("est_tokens", 0),
            )
        except Exception as e:  # observer must never raise into legacy
            logger.warning("harness.observe: evaluate errored: %s", e)
            rec = {
                "agent": ctx.agent,
                "mode": "shadow",
                "comparison_verdict": ComparisonVerdict.SHADOW_ERROR.value,
                "error": str(e)[:200],
                "run_id": ctx.run_id,
                "shadow_run_id": ctx.shadow_run_id,
            }
            audit.record(ctx, action_request, None, kind="shadow", extra=rec)
            return rec
        if d.get("would_validate") is False:
            verdict = ComparisonVerdict.MISSING_CONTEXT
        elif d.get("would_allow") is False:
            verdict = ComparisonVerdict.POLICY_MISMATCH  # harness would deny; legacy did it
        elif meta.get("verdict_override"):
            # Adapter-supplied observed verdict (FALLBACK/DELEGATION/PARSER_AMBIGUITY)
            # — only honoured once structural gates (validate/permit) have passed.
            try:
                verdict = ComparisonVerdict(meta["verdict_override"])
            except Exception:
                verdict = ComparisonVerdict.MATCH
        elif meta.get("retry_scheduled"):
            verdict = ComparisonVerdict.RETRY_OBSERVED  # legacy gate failed -> DAG retry
        elif actual_error:
            verdict = ComparisonVerdict.LEGACY_ERROR
        else:
            verdict = ComparisonVerdict.MATCH
        rec = {
            "agent": ctx.agent,
            "tenant_id": ctx.tenant_id,
            "actor_id": ctx.actor_id,
            "source_loop": ctx.source_loop,
            "mode": "shadow",
            "enforcement": False,
            "requested_tool": action_request.name,
            "tool_version": action_request.tool_version,
            "args_hash": _args_hash(action_request.args),
            "risk_class": d.get("risk_class"),
            "would_validate": d.get("would_validate"),
            "predicted_lane": d.get("predicted_lane"),
            "would_allow": d.get("would_allow"),
            "would_require_approval": d.get("would_require_approval"),
            "would_checkpoint": d.get("would_checkpoint"),
            "would_deny_reason": d.get("would_deny_reason"),
            "budget_decision": d.get("budget_decision"),
            "stop_decision": d.get("stop_decision"),
            "legacy_tool": meta.get("legacy_tool") or action_request.name,
            "legacy_status": ("error" if actual_error else _legacy_status(actual_result)),
            "legacy_error": (str(actual_error)[:200] if actual_error else None),
            "legacy_result_summary": _bounded_summary(actual_result),
            "latency_ms": meta.get("latency_ms"),
            "side_effect_class": meta.get("side_effect_class", "unknown"),
            "comparison_verdict": verdict.value,
            "execution_comparison": verdict.value,  # explicit alias (execution layer)
            "run_id": ctx.run_id,
            "shadow_run_id": ctx.shadow_run_id,
        }
        # --- Layered CANONICAL REGISTRY evaluation (additive; never changes the
        # execution comparison above; registry decision is namespaced registry_*).
        try:
            from .registry import REGISTRY, claimed_lane

            reg = REGISTRY.evaluate_action(
                tool_name=action_request.name,
                tool_version=action_request.tool_version,
                arguments=action_request.args,
                agent_id=ctx.agent,
                tenant_id=ctx.tenant_id,
                idempotency_key=action_request.idempotency_key,
                claimed_risk=claimed_lane(action_request.risk_class),
            )
            rec["registry_comparison"] = reg.get("registry_comparison")
            for _k in (
                "resolved_tool_name",
                "resolved_tool_version",
                "schema_validation",
                "agent_permission",
                "tenant_permission",
                "registry_risk_class",
                "claimed_risk_class",
                "risk_class_mismatch",
                "authority",
                "approval_requirement",
                "idempotency_requirement",
                "timeout_policy",
                "sandbox_requirement",
            ):
                rec[_k] = reg.get(_k)
            rec["registry_would_allow"] = reg.get("would_allow")
            rec["registry_would_require_approval"] = reg.get("would_require_approval")
            rec["registry_would_deny"] = reg.get("would_deny")
            rec["registry_would_deny_reason"] = reg.get("would_deny_reason")
        except Exception as _e:
            rec["registry_comparison"] = "registry_error"
            logger.warning("harness.observe: registry eval errored: %s", _e)
        # DAG-specific context (present only for dag_engine observations).
        for k in (
            "dag_run_id",
            "node_id",
            "attempt",
            "dag_node_status",
            "retry_scheduled",
            "actual_executor",
            "declared_tool",
            "actual_arguments_hash",
            "source_run_id",
            "source_node_id",
            "source_attempt",
            "step_type",
            "canonical_tool",
            "enforcement_applied",
        ):
            if meta.get(k) is not None:
                rec[k] = meta[k]
        # Coordinator-specific context (present only for coordinator observations).
        for k in (
            "coordinator_run_id",
            "orchestration_path",
            "action_index",
            "parser_type",
            "parser_confidence",
            "raw_response_hash",
            "normalized_tool",
            "normalized_arguments_hash",
            "fallback_used",
            "delegated_agent",
            "parent_run_id",
            "parent_action_id",
            "delegated_run_id",
            "delegated_agent_id",
            "tool_registry_status",
            "executor_boundary",
        ):
            if meta.get(k) is not None:
                rec[k] = meta[k]
        # Supervisor-family context (present only for supervisor observations).
        for k in (
            "supervisor_implementation",
            "graph_run_id",
            "graph_step",
            "tool_call_id",
            "replay_suppressed",
            "selection_source",
            "route_label",
            "actual_node",
            "route_node_mismatch",
        ):
            if meta.get(k) is not None:
                rec[k] = meta[k]
        # Batch-harness context (present only for batch observations).
        for k in (
            "batch_run_id",
            "batch_name",
            "item_id",
            "item_index",
            "operation_name",
            "checkpoint_state",
            "resumed",
        ):
            if meta.get(k) is not None:
                rec[k] = meta[k]
        # Staff composite context (present only for run_member composite observations).
        for k in (
            "composite_action",
            "components",
            "component_count",
            "component_status",
            "components_ok",
            "components_failed",
            "partial_success",
            "full_success",
        ):
            if meta.get(k) is not None:
                rec[k] = meta[k]
        audit.record(ctx, action_request, None, kind="shadow", extra=_redact(rec))
        return rec

    async def run(
        self,
        ctx: RunContext,
        propose: Callable[[RunContext], Awaitable[ToolCall | None]],
        profile: str = "default",
        est_cost: Callable[[ToolCall], tuple[float, int]] = lambda c: (0.0, 0),
    ) -> StopReason:
        """Drive the loop: propose -> step -> stop-check, until a stop reason.

        ``propose`` is your model call that returns a validated ToolCall (via
        app.llm.structured), or None to signal the model considers the goal met.
        """
        if session.session_events_enabled():
            audit.record(
                ctx,
                None,
                None,
                kind="session",
                extra={"session_event": "turn_start", "profile": profile},
            )
        while True:
            cont, reason = self.stop.check(ctx)
            if not cont:
                audit.record(ctx, None, None, kind="stop", extra={"reason": reason})
                return reason or StopReason.MAX_ITERATIONS

            if self.pre_step is not None:
                try:
                    allowed = await self.pre_step(ctx)
                except Exception as e:
                    logger.warning("harness.loop: pre_step errored (rejecting): %s", e)
                    allowed = False
                if not allowed:
                    audit.record(
                        ctx,
                        None,
                        None,
                        kind="stop",
                        extra={"reason": "pre_step_reject", "session_event": "pre_step_reject"},
                    )
                    return StopReason.DENIED

            ctx.iterations += 1
            try:
                call = await propose(ctx)
            except Exception as e:
                logger.warning("harness.loop: propose errored: %s", e)
                if session.session_events_enabled():
                    audit.record(
                        ctx,
                        None,
                        None,
                        kind="session",
                        extra={"session_event": "turn_end", "reason": StopReason.ERROR.value},
                    )
                return StopReason.ERROR
            if call is None:
                if session.session_events_enabled():
                    audit.record(
                        ctx,
                        None,
                        None,
                        kind="session",
                        extra={"session_event": "turn_end", "reason": StopReason.GOAL_MET.value},
                    )
                return StopReason.GOAL_MET

            est_usd, est_tokens = est_cost(call)
            await self.step(ctx, call, profile=profile, est_usd=est_usd, est_tokens=est_tokens)
