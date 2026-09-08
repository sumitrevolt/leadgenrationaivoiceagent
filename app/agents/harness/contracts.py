"""
Typed action contracts for the agent harness.

This is the spine the audit found missing: instead of scraping freeform
Hinglish / JSON out of LLM text (coordinator._extract_list), the model is
required to emit a validated ``ToolCall``. Everything downstream — permission
checks, argument bounds, approval, checkpoint, sandbox, trace — keys off these
types.

Pydantic v2. No app.* imports here on purpose: contracts must stay importable
in isolation (CI, unit tests, other services).
"""

from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class RiskClass(str, Enum):
    """How dangerous a tool is. Drives approval + sandbox tier."""

    READ = "read"  # no side effects (search, read_file, lookup)
    WRITE_LOCAL = "write_local"  # mutates local/DB state (draft, checkpoint)
    EXTERNAL_SEND = "external_send"  # email / whatsapp / social publish
    TELEPHONY = "telephony"  # place_call — DLT/DND gated
    MONEY = "money"  # spend / activate subscription / refund
    CODE_EXEC = "code_exec"  # runs model-generated code — highest tier


# Which risk classes MUST pass a human-in-the-loop approval gate (PM-03).
DANGEROUS = {
    RiskClass.EXTERNAL_SEND,
    RiskClass.TELEPHONY,
    RiskClass.MONEY,
    RiskClass.CODE_EXEC,
}

# Which risk classes mutate state and therefore require a pre-action
# checkpoint (SB-04).
MUTATING = {
    RiskClass.WRITE_LOCAL,
    RiskClass.EXTERNAL_SEND,
    RiskClass.TELEPHONY,
    RiskClass.MONEY,
    RiskClass.CODE_EXEC,
}


class ToolCall(BaseModel):
    """A single validated action the model wants to take (a.k.a. ActionRequest).

    The model returns this (via app.llm.structured / instructor), never raw
    text. ``name`` must resolve in the tool registry; ``args`` are validated
    against that tool's declared Pydantic schema before execution (VA-01/VA-02).

    Carries the full governed-action field set required by the harness spec so
    every action is attributable, budgeted, idempotent and auditable.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field("1.0", description="ActionRequest contract version")
    name: str = Field(..., description="Registered tool name")
    args: dict[str, Any] = Field(default_factory=dict)
    reason: str = Field("", description="Model's short justification (audited, NOT trusted)")
    call_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    action_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])

    # Governed-action metadata (spec field set).
    tool_version: str = Field("v1", description="Contract version of the target tool")
    risk_class: RiskClass | None = Field(
        None, description="Optional model-declared risk; the registry's value is authoritative"
    )
    idempotency_key: str | None = Field(
        None, description="Required for MUTATING actions; dedupes effects on replay"
    )
    budget_scope: str = Field("run", description="Which budget bucket this call charges")
    approval_reference: str | None = Field(
        None, description="Owner OS approval id once an AMBER/dangerous action is cleared"
    )
    expected_effect: str = Field("", description="Human-readable declared effect (audited)")
    timeout_s: float = Field(30.0, description="Per-call wall-clock timeout")


# Spec alias — the loop/registry accept either name.
ActionRequest = ToolCall


class ToolResult(BaseModel):
    """Outcome of executing a ToolCall."""

    model_config = ConfigDict(extra="forbid")

    call_id: str
    ok: bool
    output: Any = None
    error: str | None = None
    cost_usd: float = 0.0
    tokens: int = 0
    latency_ms: int = 0
    # Populated by the loop as controls run, for the audit trail.
    control_trail: list[str] = Field(default_factory=list)


class StopReason(str, Enum):
    GOAL_MET = "goal_met"
    MAX_ITERATIONS = "max_iterations"
    BUDGET_EXHAUSTED = "budget_exhausted"
    WALL_CLOCK = "wall_clock"
    NO_PROGRESS = "no_progress"
    KILL_SWITCH = "kill_switch"
    DENIED = "denied"  # permission / approval refused
    ERROR = "error"


# Explicit non-customer tenant sentinel for internal/system operations.
# (No approved system-tenant constant exists in the repo; this value is
# obviously not a customer id, so it never fabricates tenant context.)
SYSTEM_TENANT = "__system__"


class ComparisonVerdict(str, Enum):
    MATCH = "MATCH"
    POLICY_MISMATCH = "POLICY_MISMATCH"  # harness would have denied what legacy did
    ARGUMENT_MISMATCH = "ARGUMENT_MISMATCH"
    TOOL_MISMATCH = "TOOL_MISMATCH"
    MISSING_CONTEXT = "MISSING_CONTEXT"
    SHADOW_ERROR = "SHADOW_ERROR"
    LEGACY_ERROR = "LEGACY_ERROR"
    RETRY_OBSERVED = "RETRY_OBSERVED"  # legacy gate failed, DAG will retry
    PARSER_AMBIGUITY = "PARSER_AMBIGUITY"  # coordinator parse was ambiguous
    FALLBACK_OBSERVED = "FALLBACK_OBSERVED"  # legacy took a fallback path
    DELEGATION_OBSERVED = "DELEGATION_OBSERVED"  # coordinator delegated to another loop
    RESUME_SKIPPED = "RESUME_SKIPPED"  # batch item skipped on resume (NOT executed)
    DUPLICATE_SUPPRESSED = "DUPLICATE_SUPPRESSED"  # duplicate shadow write suppressed


class RunContext(BaseModel):
    """Per-run state threaded through the whole loop. The single ``run_id`` is
    the join key that makes OB-02 (replayable audit) possible."""

    model_config = ConfigDict(extra="allow")

    run_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    task_id: str = ""
    tenant_id: str = ""  # AC-03 data-residency / client isolation
    agent: str = "default"  # maps to agent_permissions matrix + task profile
    actor_id: str = ""  # who triggered the run (operator/scheduler)
    shadow_run_id: str = ""  # set in shadow mode: shadow:<real_run_id>:<idx>
    source_loop: str = ""  # e.g. staff.run_member
    started_at: float = Field(default_factory=time.time)

    # Accumulators the StopController reads (ST-01/02).
    iterations: int = 0
    tool_calls: int = 0
    spent_usd: float = 0.0
    spent_tokens: int = 0
    recent_signatures: list[str] = Field(default_factory=list)  # no-progress detection

    def elapsed_s(self) -> float:
        return time.time() - self.started_at
