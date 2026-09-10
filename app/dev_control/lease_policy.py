"""Pure lease/backoff policy for the canonical DevTask ledger (stdlib-only).

Split out of ``app/dev_control/reconcile.py`` so the two things a 24x7
supervisor actually needs to reason about — "how long do we wait before
retrying?" and "what does an expired lease turn into?" — are decidable without
a database, a session, or SQLAlchemy. Also means they are unit-testable under a
bare interpreter (the repo `.venv` is currently missing).

Exponential backoff: ``60s * 2^retry_count``, capped at 15 minutes, plus up to
+10% jitter (jitter is applied AFTER the cap, so the worst case is 990s).

The reclaim planner returns a plain dict of field updates. It is PURE: callers
(``reconcile.reconcile_leases`` async / ``reconcile_expired_leases_sync``) own
all I/O. Legal transitions stay exactly CLAIMED/RUNNING -> BLOCKED -> QUEUED or
FAILED per ``app.dev_control.service._TRANSITIONS`` — no new states.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import Any

from app.dev_control.service import TaskState

BACKOFF_BASE_SECONDS = 60
BACKOFF_CAP_SECONDS = 900  # 15 minutes
BACKOFF_MAX_JITTER_RATIO = 0.10

DEFAULT_MAX_RETRIES = 3
DEFAULT_RECONCILE_LIMIT = 200

# States from which BLOCKED is a legal intermediate hop (mirrors _TRANSITIONS).
_LEGAL_TO_BLOCKED = frozenset({TaskState.CLAIMED.value, TaskState.RUNNING.value})


def clamp_retry_count(retry_count: Any) -> int:
    """Coerce a possibly-None/garbage retry counter to a non-negative int."""
    try:
        value = int(retry_count or 0)
    except (TypeError, ValueError):
        return 0
    return value if value > 0 else 0


def clamp_jitter_ratio(jitter_ratio: Any) -> float:
    """Coerce jitter into [0.0, BACKOFF_MAX_JITTER_RATIO]."""
    try:
        value = float(jitter_ratio or 0.0)
    except (TypeError, ValueError):
        return 0.0
    if value < 0.0:
        return 0.0
    return value if value <= BACKOFF_MAX_JITTER_RATIO else BACKOFF_MAX_JITTER_RATIO


def compute_retry_backoff_seconds(retry_count: Any, jitter_ratio: Any = 0.0) -> int:
    """Backoff in whole seconds: min(60 * 2^n, 900) * (1 + jitter).

    ``retry_count`` is the counter AFTER the failed attempt was counted, i.e.
    the first reclaim waits 120s, then 240s, 480s, then the cap at 900s.
    """
    exponent = clamp_retry_count(retry_count)
    base = BACKOFF_BASE_SECONDS * (2**exponent)
    if base > BACKOFF_CAP_SECONDS:
        base = BACKOFF_CAP_SECONDS
    return int(round(base * (1.0 + clamp_jitter_ratio(jitter_ratio))))


def sample_retry_backoff_seconds(retry_count: Any, rng: random.Random | None = None) -> int:
    """Backoff with random jitter in [0%, 10%] — pass an rng for determinism."""
    generator = rng if rng is not None else random.Random()
    return compute_retry_backoff_seconds(
        retry_count, jitter_ratio=generator.uniform(0.0, BACKOFF_MAX_JITTER_RATIO)
    )


def next_eligible_at(
    now: datetime, retry_count: Any, rng: random.Random | None = None
) -> datetime:
    """Absolute time a requeued task becomes claimable again."""
    return now + timedelta(seconds=sample_retry_backoff_seconds(retry_count, rng=rng))


def plan_lease_reclaim(
    *,
    state: str,
    retry_count: Any,
    max_retries: int = DEFAULT_MAX_RETRIES,
    now: datetime,
    rng: random.Random | None = None,
) -> dict[str, Any]:
    """PURE: field updates for ONE in-flight task whose lease has expired.

    Never mutates and never touches the DB. Returned keys:
      ``intermediate_state`` (BLOCKED when legal, else None — fidelity with the
      original two-hop transition), ``state``, ``blocked_reason``,
      ``retry_count``, ``lease_owner``, ``lease_until``, ``next_eligible_at``
      (None when the task is failed), ``outcome`` ("requeued" | "failed"),
      ``backoff_seconds`` (0 when failed).
    """
    current_state = str(state or "")
    new_retry_count = clamp_retry_count(retry_count) + 1

    intermediate_state = None
    if current_state in _LEGAL_TO_BLOCKED:
        intermediate_state = TaskState.BLOCKED.value

    if new_retry_count > int(max_retries or 0):
        return {
            "intermediate_state": intermediate_state,
            "state": TaskState.FAILED.value,
            "blocked_reason": f"lease_expired_max_retries({max_retries})",
            "retry_count": new_retry_count,
            "lease_owner": None,
            "lease_until": None,
            "next_eligible_at": None,
            "outcome": "failed",
            "backoff_seconds": 0,
        }

    backoff_seconds = sample_retry_backoff_seconds(new_retry_count, rng=rng)
    return {
        "intermediate_state": intermediate_state,
        "state": TaskState.QUEUED.value,
        "blocked_reason": "lease_expired_reclaimed",
        "retry_count": new_retry_count,
        "lease_owner": None,
        "lease_until": None,
        "next_eligible_at": now + timedelta(seconds=backoff_seconds),
        "outcome": "requeued",
        "backoff_seconds": backoff_seconds,
    }


__all__ = [
    "BACKOFF_BASE_SECONDS",
    "BACKOFF_CAP_SECONDS",
    "BACKOFF_MAX_JITTER_RATIO",
    "DEFAULT_MAX_RETRIES",
    "DEFAULT_RECONCILE_LIMIT",
    "clamp_jitter_ratio",
    "clamp_retry_count",
    "compute_retry_backoff_seconds",
    "next_eligible_at",
    "plan_lease_reclaim",
    "sample_retry_backoff_seconds",
]
