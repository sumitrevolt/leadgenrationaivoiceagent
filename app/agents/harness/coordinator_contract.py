"""Canonical coordinator structured action contracts (shadow-only, v1).

Replaces coordinator ambiguity (raw LLM prose parsed by `_extract_list`) with ONE
strict, versioned structured language: CoordinatorPlanV1 / CoordinatorActionV1.
Raw model prose is NEVER an executable contract. Legacy heuristic parsing stays
available for compatibility and is explicitly marked heuristic (never
"structured_native"). Nothing here executes — it validates, normalizes and
compares; the legacy coordinator executor stays authoritative.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .registry import RiskLane

# Kavach is never a valid delegation target; manager/Boss is not a silent worker.
KAVACH = "kavach"
_MAX_TASK = 2000
_MAX_ARG_BLOB = 8000


class CoordinatorActionType(str, Enum):
    DELEGATE_AGENT = "DELEGATE_AGENT"
    INVOKE_INTERNAL_TOOL = "INVOKE_INTERNAL_TOOL"
    REQUEST_ANALYSIS = "REQUEST_ANALYSIS"
    REQUEST_REVIEW = "REQUEST_REVIEW"
    SYNTHESIZE = "SYNTHESIZE"
    STOP = "STOP"


class PlanSource(str, Enum):
    STRUCTURED_NATIVE = "STRUCTURED_NATIVE"
    STRICT_JSON = "STRICT_JSON"
    LEGACY_JSON_EXTRACT = "LEGACY_JSON_EXTRACT"
    LEGACY_REGEX = "LEGACY_REGEX"
    FALLBACK_DEFAULT = "FALLBACK_DEFAULT"
    FAILED = "FAILED"


class CoordinatorPlanVerdict(str, Enum):
    PLAN_MATCH = "PLAN_MATCH"
    TARGET_MISMATCH = "TARGET_MISMATCH"
    TOOL_MISMATCH = "TOOL_MISMATCH"
    ARGUMENT_MISMATCH = "ARGUMENT_MISMATCH"
    ORDER_MISMATCH = "ORDER_MISMATCH"
    ACTION_COUNT_MISMATCH = "ACTION_COUNT_MISMATCH"
    STRUCTURED_INVALID = "STRUCTURED_INVALID"
    LEGACY_FALLBACK = "LEGACY_FALLBACK"
    UNCOMPARABLE = "UNCOMPARABLE"


class CoordinatorActionV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    action_id: str
    sequence: int
    action_type: CoordinatorActionType
    target_agent: str | None = None
    tool_name: str | None = None
    tool_version: str | None = None
    task: str = ""
    arguments: dict[str, Any] = Field(default_factory=dict)
    expected_effect: str = ""
    claimed_risk: RiskLane = RiskLane.GREEN
    depends_on: list[str] = Field(default_factory=list)
    continue_on_error: bool = False

    @field_validator("sequence")
    @classmethod
    def _seq_ok(cls, v: int) -> int:
        if v < 0:
            raise ValueError("sequence must be >= 0")
        return v

    @field_validator("task")
    @classmethod
    def _task_bounded(cls, v: str) -> str:
        if len(v or "") > _MAX_TASK:
            raise ValueError(f"task exceeds {_MAX_TASK} chars")
        return v


class CoordinatorPlanV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    objective: str = ""
    actions: list[CoordinatorActionV1] = Field(default_factory=list)
    synthesis_required: bool = False
    stop_after_actions: bool = False
    plan_source: PlanSource = PlanSource.STRUCTURED_NATIVE

    @field_validator("actions")
    @classmethod
    def _actions_ok(cls, v: list[CoordinatorActionV1]) -> list[CoordinatorActionV1]:
        ids = [a.action_id for a in v]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate action_id in plan")
        return v


class CoordinatorActionResultV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_id: str
    sequence: int
    status: Literal["succeeded", "failed", "skipped", "blocked", "approval_required"]
    target_agent: str | None = None
    tool_name: str | None = None
    bounded_result: Any | None = None
    error_code: str | None = None
    error_summary: str | None = None
    duration_ms: float = 0.0


class CoordinatorPlanComparison(BaseModel):
    legacy_plan_source: str
    structured_plan_source: str
    legacy_action_count: int
    structured_action_count: int
    matched_actions: int
    missing_actions: int
    extra_actions: int
    target_agent_matches: int
    tool_matches: int
    argument_matches: int
    ordering_matches: bool
    comparison_verdict: CoordinatorPlanVerdict
    differences: list[dict] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Delegation identity standard (reusable by coordinator + future supervisor).
# --------------------------------------------------------------------------- #
def delegation_identity(agent_id: str) -> str:
    return f"agent.delegate.{(agent_id or '').strip().lower()}"


def _known_agents() -> set[str]:
    try:
        from app.platform.team import STAFF

        return {str(k).strip().lower() for k in (STAFF or {}).keys()}
    except Exception:
        return {"manager", "rohan", "swara", "dev", "arjun", "meera", "kavya", "isha"}


def validate_delegation_target(target_agent: str) -> tuple[bool, str]:
    """Delegation target must be a real STAFF member and never Kavach. Manager is
    a real member (not silently a worker) but IS a valid delegation target."""
    t = (target_agent or "").strip().lower()
    if not t:
        return False, "missing target_agent"
    if t == KAVACH:
        return False, "kavach is never a delegation target"
    if t not in _known_agents():
        return False, f"unknown agent: {t}"
    return True, ""


# --------------------------------------------------------------------------- #
# Legacy parser adapter — normalize _extract_list output into the contract.
# NEVER pretends heuristic output is structured_native.
# --------------------------------------------------------------------------- #
def normalize_legacy_plan(
    steps: list[dict], *, fallback_used: bool = False, objective: str = "", regex_used: bool = False
) -> CoordinatorPlanV1:
    """Normalize legacy `[{agent, task}]` selection into a CoordinatorPlanV1 with
    honest provenance. Heuristic/fallback provenance is preserved."""
    if fallback_used:
        src = PlanSource.FALLBACK_DEFAULT
    elif regex_used:
        src = PlanSource.LEGACY_REGEX
    else:
        src = PlanSource.LEGACY_JSON_EXTRACT
    actions: list[CoordinatorActionV1] = []
    for i, s in enumerate(steps or []):
        if not isinstance(s, dict):
            continue
        agent = str(s.get("agent") or "").strip().lower()
        actions.append(
            CoordinatorActionV1(
                action_id=f"legacy-{i}",
                sequence=i,
                action_type=CoordinatorActionType.DELEGATE_AGENT,
                target_agent=agent,
                task=str(s.get("task") or "")[:_MAX_TASK],
                arguments={},
                expected_effect="legacy delegation (draft/execute)",
                claimed_risk=RiskLane.GREEN,
            )
        )
    return CoordinatorPlanV1(
        objective=str(objective or "")[:500],
        actions=actions,
        synthesis_required=False,
        stop_after_actions=False,
        plan_source=src,
    )


def _bounded_diff(seq: int, field: str, a: Any, b: Any) -> dict:
    return {"sequence": seq, "field": field, "structured": str(a)[:120], "legacy": str(b)[:120]}


def compare_plans(
    structured: CoordinatorPlanV1 | None, legacy: CoordinatorPlanV1
) -> CoordinatorPlanComparison:
    """Deterministic structured-vs-legacy comparison. NEVER modifies execution."""
    if structured is None:
        return CoordinatorPlanComparison(
            legacy_plan_source=legacy.plan_source.value,
            structured_plan_source="none",
            legacy_action_count=len(legacy.actions),
            structured_action_count=0,
            matched_actions=0,
            missing_actions=len(legacy.actions),
            extra_actions=0,
            target_agent_matches=0,
            tool_matches=0,
            argument_matches=0,
            ordering_matches=False,
            comparison_verdict=CoordinatorPlanVerdict.STRUCTURED_INVALID,
        )
    if legacy.plan_source is PlanSource.FALLBACK_DEFAULT:
        verdict0 = CoordinatorPlanVerdict.LEGACY_FALLBACK
    else:
        verdict0 = None
    sa, la = structured.actions, legacy.actions
    n = min(len(sa), len(la))
    tgt = tool = arg = 0
    diffs: list[dict] = []
    order_ok = True
    for i in range(n):
        s, l = sa[i], la[i]
        if (s.target_agent or "") == (l.target_agent or ""):
            tgt += 1
        else:
            order_ok = False
            diffs.append(_bounded_diff(i, "target_agent", s.target_agent, l.target_agent))
        if (s.tool_name or "") == (l.tool_name or ""):
            tool += 1
        else:
            diffs.append(_bounded_diff(i, "tool_name", s.tool_name, l.tool_name))
        if s.arguments == l.arguments:
            arg += 1
        else:
            diffs.append(_bounded_diff(i, "arguments", s.arguments, l.arguments))
    matched = tgt
    missing = max(0, len(la) - len(sa))
    extra = max(0, len(sa) - len(la))
    if verdict0 is not None:
        verdict = verdict0
    elif len(sa) != len(la):
        verdict = CoordinatorPlanVerdict.ACTION_COUNT_MISMATCH
    elif tgt != n:
        verdict = CoordinatorPlanVerdict.TARGET_MISMATCH
    elif tool != n:
        verdict = CoordinatorPlanVerdict.TOOL_MISMATCH
    elif arg != n:
        verdict = CoordinatorPlanVerdict.ARGUMENT_MISMATCH
    elif not order_ok:
        verdict = CoordinatorPlanVerdict.ORDER_MISMATCH
    else:
        verdict = CoordinatorPlanVerdict.PLAN_MATCH
    return CoordinatorPlanComparison(
        legacy_plan_source=legacy.plan_source.value,
        structured_plan_source=structured.plan_source.value,
        legacy_action_count=len(la),
        structured_action_count=len(sa),
        matched_actions=matched,
        missing_actions=missing,
        extra_actions=extra,
        target_agent_matches=tgt,
        tool_matches=tool,
        argument_matches=arg,
        ordering_matches=order_ok and len(sa) == len(la),
        comparison_verdict=verdict,
        differences=diffs[:20],
    )


# --------------------------------------------------------------------------- #
# Supervisor decision envelope — REUSES CoordinatorActionV1 (no fork). A route
# label / selected graph node / structured message identity normalizes into the
# shared delegation contract. Raw assistant prose is not an action identity.
# --------------------------------------------------------------------------- #
class SelectionSource(str, Enum):
    GRAPH_ROUTE = "GRAPH_ROUTE"
    MESSAGE_NAME = "MESSAGE_NAME"
    NODE_IDENTITY = "NODE_IDENTITY"
    HEURISTIC = "HEURISTIC"
    UNKNOWN = "UNKNOWN"


class SupervisorVerdict(str, Enum):
    MATCH = "MATCH"
    TARGET_MISMATCH = "TARGET_MISMATCH"
    TOOL_MISMATCH = "TOOL_MISMATCH"
    ARGUMENT_MISMATCH = "ARGUMENT_MISMATCH"
    ROUTE_NODE_MISMATCH = "ROUTE_NODE_MISMATCH"
    MISSING_CONTEXT = "MISSING_CONTEXT"
    HEURISTIC_SELECTION = "HEURISTIC_SELECTION"
    LEGACY_ERROR = "LEGACY_ERROR"
    FALLBACK_OBSERVED = "FALLBACK_OBSERVED"
    REPLAY_SUPPRESSED = "REPLAY_SUPPRESSED"


class SupervisorDecisionV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    decision_id: str
    supervisor_implementation: Literal["supervisor", "staff_supervisor"]
    actor_id: str
    target_agent: str
    task: str = ""
    route_label: str | None = None
    graph_run_id: str
    graph_step: int
    attempt: int = 0
    selection_source: SelectionSource = SelectionSource.UNKNOWN
    arguments: dict[str, Any] = Field(default_factory=dict)

    @field_validator("graph_step")
    @classmethod
    def _step_ok(cls, v: int) -> int:
        if v < 0:
            raise ValueError("graph_step must be >= 0")
        return v

    @field_validator("task")
    @classmethod
    def _task_bounded(cls, v: str) -> str:
        if len(v or "") > _MAX_TASK:
            raise ValueError(f"task exceeds {_MAX_TASK} chars")
        return v

    @field_validator("target_agent")
    @classmethod
    def _target_ok(cls, v: str) -> str:
        ok, err = validate_delegation_target(v)
        if not ok:
            raise ValueError(f"invalid target_agent: {err}")
        return v

    def to_coordinator_action(
        self,
        *,
        tool_name: str | None = None,
        tool_version: str | None = None,
        claimed_risk: RiskLane = RiskLane.GREEN,
    ) -> CoordinatorActionV1:
        """Normalize this supervisor decision into the shared CoordinatorActionV1.
        actor_id and supervisor metadata are preserved in bounded arguments."""
        args = dict(self.arguments or {})
        if len(json_dumps_safe(args)) > _MAX_ARG_BLOB:
            args = {"_truncated": True}
        args.update(
            supervisor_implementation=self.supervisor_implementation,
            graph_run_id=self.graph_run_id,
            graph_step=self.graph_step,
            route_label=self.route_label,
            actor_id=self.actor_id,
            selection_source=self.selection_source.value,
        )
        return CoordinatorActionV1(
            action_id=self.decision_id,
            sequence=self.graph_step,
            action_type=CoordinatorActionType.DELEGATE_AGENT,
            target_agent=self.target_agent,
            tool_name=tool_name,
            tool_version=tool_version,
            task=str(self.task)[:_MAX_TASK],
            arguments=args,
            expected_effect=f"supervisor delegation to {self.target_agent}",
            claimed_risk=claimed_risk,
        )


def json_dumps_safe(obj: Any) -> str:
    import json as _json

    try:
        return _json.dumps(obj, default=str)
    except Exception:
        return ""
