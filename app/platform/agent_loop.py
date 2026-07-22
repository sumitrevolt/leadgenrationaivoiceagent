"""
Agent Loop Engine (M1) — Typed Multi-Turn Loop Core & Budget Enforcement.
========================================================================

WHY (2026-07-22, Agent Harness Engineering Standard M1):
Provides a typed state machine governing multi-turn agent execution turns.
Enforces turn budgets, step bounds, execution timeouts, and standardized
termination states (COMPLETED, MAX_TURNS_EXCEEDED, BUDGET_EXHAUSTED,
POLICY_REFUSED, FAILED).

Import-safe; zero side-effects on import.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class LoopTerminationReason(str, Enum):
    COMPLETED = "completed"
    MAX_TURNS_EXCEEDED = "max_turns_exceeded"
    BUDGET_EXHAUSTED = "budget_exhausted"
    POLICY_REFUSED = "policy_refused"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class AgentTurnState:
    turn_index: int = 0
    max_turns: int = 5
    tokens_used: int = 0
    max_tokens: int = 4000
    cost_inr: float = 0.0
    max_cost_inr: float = 10.0
    start_time_s: float = field(default_factory=time.time)
    max_duration_s: float = 60.0
    history: list[dict[str, Any]] = field(default_factory=list)
    termination_reason: LoopTerminationReason | None = None
    final_output: dict[str, Any] = field(default_factory=dict)
    error_message: str = ""

    def is_expired(self) -> bool:
        if self.turn_index >= self.max_turns:
            self.termination_reason = LoopTerminationReason.MAX_TURNS_EXCEEDED
            return True
        if self.tokens_used >= self.max_tokens or self.cost_inr >= self.max_cost_inr:
            self.termination_reason = LoopTerminationReason.BUDGET_EXHAUSTED
            return True
        if (time.time() - self.start_time_s) >= self.max_duration_s:
            self.termination_reason = LoopTerminationReason.BUDGET_EXHAUSTED
            return True
        return False

    def record_step(self, action: str, result: dict[str, Any], tokens: int = 0, cost: float = 0.0) -> None:
        self.turn_index += 1
        self.tokens_used += tokens
        self.cost_inr += cost
        self.history.append({
            "turn": self.turn_index,
            "action": action,
            "result": result,
            "tokens": tokens,
            "cost_inr": cost,
            "timestamp_s": time.time(),
        })


class AgentLoopEngine:
    """Core multi-turn execution harness managing agent steps and budget bounds."""

    def __init__(self, max_turns: int = 5, max_tokens: int = 4000, max_cost_inr: float = 10.0, max_duration_s: float = 60.0) -> None:
        self.max_turns = max_turns
        self.max_tokens = max_tokens
        self.max_cost_inr = max_cost_inr
        self.max_duration_s = max_duration_s

    def create_turn_state(self) -> AgentTurnState:
        return AgentTurnState(
            max_turns=self.max_turns,
            max_tokens=self.max_tokens,
            max_cost_inr=self.max_cost_inr,
            max_duration_s=self.max_duration_s,
        )

    async def run_loop(
        self,
        initial_payload: dict[str, Any],
        step_handler: Callable[[AgentTurnState, dict[str, Any]], Awaitable[dict[str, Any]]],
    ) -> AgentTurnState:
        state = self.create_turn_state()
        current_input = dict(initial_payload)

        while not state.is_expired():
            try:
                result = await step_handler(state, current_input)
                is_done = bool(result.get("done", True))
                state.record_step(
                    action=str(result.get("action") or "step"),
                    result=result,
                    tokens=int(result.get("tokens_used") or 0),
                    cost=float(result.get("cost_inr") or 0.0),
                )
                if is_done:
                    state.termination_reason = LoopTerminationReason.COMPLETED
                    state.final_output = result
                    break
                current_input = result.get("next_input") or {}
            except Exception as e:
                logger.error("[agent_loop] Step failed at turn %d: %s", state.turn_index, e, exc_info=True)
                state.termination_reason = LoopTerminationReason.FAILED
                state.error_message = str(e)
                break

        if state.termination_reason is None and state.is_expired():
            logger.warning("[agent_loop] Loop terminated due to budget/turn limits: %s", state.termination_reason)

        return state
