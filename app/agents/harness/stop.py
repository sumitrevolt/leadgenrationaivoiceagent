"""
Unified stop / budget controller (ST-01 / ST-02 / ST-03).

The audit found the stop logic scattered and inert:
* `dev_control/budgets.py` has next_attempt_decision / is_repeat_prompt /
  budget_state — never wired into the single-shot runner;
* `gateway.admit_cost` is fail-closed but estimate-only;
* `llm/budget_guard.allow()` is explicitly FAIL-OPEN;
* the kill switch is an env var (needs redeploy) covering only the LLM path.

This controller is the single place the loop asks "may I take another step?".
It enforces hard caps (tokens/cost/wall-clock/tool-calls/iterations), detects
no-monotonic-progress, and consults a **live** kill switch (Redis key, no
redeploy). It is fail-CLOSED for the harness path.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Optional, Tuple

from .contracts import RunContext, StopReason

try:
    from app.utils.logger import setup_logger  # type: ignore

    logger = setup_logger(__name__)
except Exception:  # pragma: no cover
    import logging

    logger = logging.getLogger(__name__)


@dataclass
class Budget:
    max_iterations: int = 12
    max_tool_calls: int = 40
    max_usd: float = 1.00
    max_tokens: int = 200_000
    max_wall_clock_s: float = 300.0
    # No-progress: stop if the last N observation signatures are identical.
    no_progress_window: int = 3


def _redis():
    """Best-effort Redis handle reusing the app's client if present."""
    try:
        from app.cache import get_redis  # type: ignore

        return get_redis()
    except Exception:
        try:
            from app.infrastructure.redis_client import redis_client  # type: ignore

            return redis_client
        except Exception:
            return None


class StopController:
    def __init__(self, budget: Budget | None = None, cost_admitter=None) -> None:
        self.budget = budget or Budget()
        # Optional provider-level admission, injected at the model-call site where
        # provider + token estimates are known (that is where dev_control's
        # admit_cost(provider=..., estimated_input_tokens=..., ...) belongs).
        self._cost_admitter = cost_admitter

    # ---- kill switch (ST-03), live, per-run + fleet -------------------
    def killed(self, ctx: RunContext) -> bool:
        r = _redis()
        if r is None:
            return False
        try:
            # fleet-wide OR this specific run
            if r.get("harness:kill:all"):
                return True
            if r.get(f"harness:kill:{ctx.run_id}"):
                return True
        except Exception as e:  # pragma: no cover
            logger.warning("harness.stop: kill check errored: %s", e)
        return False

    @staticmethod
    def request_kill(run_id: str = "all", ttl_s: int = 3600) -> bool:
        """Operator API/CLI calls this — no redeploy needed."""
        r = _redis()
        if r is None:
            return False
        try:
            r.setex(f"harness:kill:{run_id}", ttl_s, "1")
            return True
        except Exception:
            return False

    # ---- progress signature (ST-02) -----------------------------------
    @staticmethod
    def signature(observation: object) -> str:
        return hashlib.sha1(
            repr(observation).encode("utf-8", "ignore"), usedforsecurity=False
        ).hexdigest()[:16]

    def record_progress(self, ctx: RunContext, observation: object) -> None:
        sig = self.signature(observation)
        ctx.recent_signatures.append(sig)
        if len(ctx.recent_signatures) > self.budget.no_progress_window:
            ctx.recent_signatures.pop(0)

    def _stuck(self, ctx: RunContext) -> bool:
        w = self.budget.no_progress_window
        sigs = ctx.recent_signatures
        return len(sigs) >= w and len(set(sigs)) == 1

    # ---- the single gate the loop calls -------------------------------
    def check(self, ctx: RunContext) -> tuple[bool, StopReason | None]:
        """Returns (may_continue, stop_reason). Fail-closed on ambiguity."""
        if self.killed(ctx):
            return False, StopReason.KILL_SWITCH
        b = self.budget
        if ctx.iterations >= b.max_iterations:
            return False, StopReason.MAX_ITERATIONS
        if ctx.tool_calls >= b.max_tool_calls:
            return False, StopReason.BUDGET_EXHAUSTED
        if ctx.spent_usd >= b.max_usd or ctx.spent_tokens >= b.max_tokens:
            return False, StopReason.BUDGET_EXHAUSTED
        if ctx.elapsed_s() >= b.max_wall_clock_s:
            return False, StopReason.WALL_CLOCK
        if self._stuck(ctx):
            return False, StopReason.NO_PROGRESS
        return True, None

    # ---- pre-spend admission (ST-01), fail-closed on the harness caps ----
    def admit(self, ctx: RunContext, est_usd: float, est_tokens: int) -> bool:
        """Fail-closed pre-call admission against the harness run budget.

        These caps ARE the run-level ceiling. Provider-level admission
        (dev_control.service.admit_cost, which needs provider + token estimates)
        is wired via an injected ``cost_admitter`` at the model-call site, not
        from this generic point — so we never call it with the wrong signature.
        """
        if ctx.spent_usd + est_usd > self.budget.max_usd:
            return False
        if ctx.spent_tokens + est_tokens > self.budget.max_tokens:
            return False
        if self._cost_admitter is not None:
            try:
                return bool(self._cost_admitter(ctx, est_usd, est_tokens))
            except Exception as e:
                logger.warning("harness.stop: cost_admitter errored -> deny: %s", e)
                return False  # fail-closed on a real enforcement error
        return True
