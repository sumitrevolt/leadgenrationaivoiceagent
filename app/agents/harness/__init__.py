"""
app.agents.harness — a thin control tier that unifies the harness controls the
existing engines already half-implement.

Turn on with ``AGENT_HARNESS=1`` (INERT by default, canary like AGENT_RUNTIME).
See docs/HARNESS_STANDARD_IMPLEMENTATION_PLAN.md for the full rollout.

Wire-first: this package CALLS your existing modules (agent_permissions,
risk_approve, agent_checkpoints, context_packets, budgets, budget_guard,
observability_llm, dev_control.gateway) rather than duplicating them.
"""

from .contracts import (
    DANGEROUS,
    MUTATING,
    ActionRequest,
    RiskClass,
    RunContext,
    StopReason,
    ToolCall,
    ToolResult,
)
from .enforce import (
    EXECUTORS,
    DenialReason,
    EnforcementDecision,
    EnforcementGate,
    HarnessMode,
    enforcement_state,
    resolve_mode,
)
from .loop import Harness, enabled
from .sandbox import Sandbox, SandboxPolicy
from .session import SessionEvent, SessionEventType, session_events_enabled
from .stop import Budget, StopController
from .tool_registry import REGISTRY, ToolRegistry, ToolSpec

__all__ = [
    "ActionRequest",
    "RiskClass",
    "RunContext",
    "StopReason",
    "ToolCall",
    "ToolResult",
    "DANGEROUS",
    "MUTATING",
    "REGISTRY",
    "ToolRegistry",
    "ToolSpec",
    "Budget",
    "StopController",
    "Sandbox",
    "SandboxPolicy",
    "Harness",
    "enabled",
    "HarnessMode",
    "EnforcementGate",
    "EnforcementDecision",
    "DenialReason",
    "resolve_mode",
    "EXECUTORS",
    "enforcement_state",
    "SessionEvent",
    "SessionEventType",
    "session_events_enabled",
]
