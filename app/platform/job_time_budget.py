"""Wall-clock budgets for Celery staff mega-jobs.

Celery soft_time_limit (~540s) pe SoftTimeLimitExceeded → DLQ. Mega-jobs
(`content`, `onboard`, `prospect`) must finish *before* that kill, with a
partial-but-ok summary — not burn retries on the same oversized workload.

Env seconds are clamped; unset uses the safe default (below soft limit).
"""

from __future__ import annotations

import os
import time
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Keep margin under worker soft_time_limit=540 / hard=600.
_DEFAULTS: dict[str, float] = {
    "CONTENT_TIME_BUDGET_S": 420.0,
    "ONBOARD_TIME_BUDGET_S": 300.0,
    "PROSPECT_TIME_BUDGET_S": 300.0,
}
_CEILING = 480.0
_FLOOR = 30.0


def budget_seconds(env_name: str, default: float | None = None) -> float:
    """Read/clamp a job wall-clock budget from env."""
    base = float(default if default is not None else _DEFAULTS.get(env_name, 300.0))
    raw = (os.getenv(env_name) or "").strip()
    if raw:
        try:
            base = float(raw)
        except ValueError:
            logger.warning(f"[job_budget] {env_name}={raw!r} invalid — using {base}")
    return max(_FLOOR, min(base, _CEILING))


class JobBudget:
    """Monotonic wall-clock budget for one staff-job invocation."""

    def __init__(self, seconds: float, *, label: str = "") -> None:
        self.limit = float(seconds)
        self.label = label or "job"
        self.t0 = time.monotonic()
        self.exhausted = False

    @classmethod
    def from_env(cls, env_name: str, *, label: str = "") -> JobBudget:
        return cls(budget_seconds(env_name), label=label or env_name)

    def elapsed(self) -> float:
        return time.monotonic() - self.t0

    def remaining(self) -> float:
        return self.limit - self.elapsed()

    def ok(self, need: float = 8.0) -> bool:
        """True when at least ``need`` seconds remain before budget end."""
        if self.remaining() >= max(0.0, float(need)):
            return True
        if not self.exhausted:
            self.exhausted = True
            logger.warning(
                f"[job_budget] {self.label} exhausted after {self.elapsed():.0f}s "
                f"(limit={self.limit:.0f}s) — skipping remaining work"
            )
        return False

    def snapshot(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "limit_s": self.limit,
            "elapsed_s": round(self.elapsed(), 1),
            "remaining_s": round(self.remaining(), 1),
            "exhausted": self.exhausted,
        }


__all__ = ["JobBudget", "budget_seconds"]
