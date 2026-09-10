"""Pure worker-liveness math for the 24x7 plane — stdlib only, no ORM, no I/O.

Split out of ``app/models/dev_worker.py`` for the same reason
``app/dev_control/ledger_hash.py`` exists: the part that must be provably
correct (health classification, staleness, authority) should be testable under
a bare interpreter, because this repo's ``.venv`` is frequently missing and a
rule that cannot be tested without SQLAlchemy is a rule that silently rots.

``app/models/dev_worker.py`` is the persistence adapter; it re-exports
everything here so callers need a single import.

Contract (docs/architecture/24X7_ARCHITECTURE_RECORD.md §3)
-----------------------------------------------------------
    heartbeat interval  60 s
    lease TTL           600 s  (lockstep: app/dev_control/claims.py DEFAULT_LEASE_SECONDS)
    degrade after       180 s  (3 missed beats)
    dead after          600 s  (10 missed beats == lease expiry)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Iterable

# ---- liveness constants (single source of truth) ---------------------------
HEARTBEAT_INTERVAL_SECONDS = 60
LEASE_TTL_SECONDS = 600
DEGRADE_AFTER_SECONDS = 180
DEAD_AFTER_SECONDS = 600

KIND_CLI = "cli"
KIND_API = "api"
KIND_DESKTOP = "desktop"
VALID_KINDS = (KIND_CLI, KIND_API, KIND_DESKTOP)

HEALTH_HEALTHY = "healthy"
HEALTH_DEGRADED = "degraded"
HEALTH_DEAD = "dead"
HEALTH_UNKNOWN = "unknown"
VALID_HEALTH = (HEALTH_HEALTHY, HEALTH_DEGRADED, HEALTH_DEAD, HEALTH_UNKNOWN)

# Desktop rows (Hermes / Claude / OpenClaw / WorkBuddy / Codex) are visible but
# never authoritative for task ownership until HMAC-attested.
NON_AUTHORITATIVE_KINDS = (KIND_DESKTOP,)


def utcnow() -> datetime:
    """Naive UTC now — matches every other DateTime column in this repo.

    Naive (not tz-aware) so comparisons against SQLAlchemy's naive DATETIME
    columns never raise "can't compare offset-naive and offset-aware".
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def encode_capabilities(capabilities: Iterable[str] | None) -> str | None:
    """JSON-encode a capability list; None in -> None out (never ``"null"``)."""
    if capabilities is None:
        return None
    return json.dumps(sorted({str(c) for c in capabilities}))


def decode_capabilities(raw: str | None) -> list[str]:
    """Best-effort decode. Corrupt JSON degrades to ``[]`` instead of raising."""
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    if isinstance(value, str):
        return [value]
    return []


def normalise_kind(kind: str | None, default: str = KIND_CLI) -> str:
    """Clamp an unknown kind to ``default`` rather than persisting garbage."""
    return kind if kind in VALID_KINDS else default


def classify_health(
    heartbeat_ts: datetime | None,
    now: datetime | None = None,
    *,
    degrade_after: int = DEGRADE_AFTER_SECONDS,
    dead_after: int = DEAD_AFTER_SECONDS,
) -> str:
    """Map heartbeat age -> health. Never raises; never guesses.

    * ``heartbeat_ts is None`` -> ``unknown``. A worker that just registered and
      has not emitted its first beat is NOT dead — collapsing it into ``dead``
      would fire a false alarm on every single restart.
    * Negative age (clock skew, beat stamped in the future) is clamped to 0 and
      reported ``healthy`` — a future beat is proof of life, just skewed.
    """
    if heartbeat_ts is None:
        return HEALTH_UNKNOWN
    now = now or utcnow()
    try:
        age = (now - heartbeat_ts).total_seconds()
    except TypeError:
        return HEALTH_UNKNOWN
    if age < 0:
        age = 0.0
    if age >= dead_after:
        return HEALTH_DEAD
    if age >= degrade_after:
        return HEALTH_DEGRADED
    return HEALTH_HEALTHY


def is_stale(
    heartbeat_ts: datetime | None,
    now: datetime | None = None,
    *,
    dead_after: int = DEAD_AFTER_SECONDS,
) -> bool:
    """True when the worker's lease window has fully elapsed."""
    return classify_health(heartbeat_ts, now, dead_after=dead_after) == HEALTH_DEAD


def is_authoritative(kind: str | None) -> bool:
    """Desktop rows are advisory until HMAC-attested — never ownership truth."""
    return normalise_kind(kind) not in NON_AUTHORITATIVE_KINDS


def worker_to_dict(worker: Any, *, now: datetime | None = None) -> dict[str, Any]:
    """Render-safe projection. No secrets by construction — this table has none.

    Accepts any object or mapping exposing the DevWorker attribute names, so it
    works on ORM rows, dataclasses and plain dicts alike.
    """

    def get(name: str, default: Any = None) -> Any:
        if isinstance(worker, dict):
            return worker.get(name, default)
        return getattr(worker, name, default)

    heartbeat = get("heartbeat_ts")
    kind = normalise_kind(get("kind"))
    computed = classify_health(heartbeat, now)
    return {
        "worker_id": get("worker_id"),
        "kind": kind,
        "supervisor_bot": get("supervisor_bot"),
        "capabilities": decode_capabilities(get("capabilities")),
        "version": get("version"),
        "started_at": get("started_at"),
        "heartbeat_ts": heartbeat,
        "health": computed,
        "stored_health": get("health"),
        "authoritative": is_authoritative(kind),
        "lease_id": get("lease_id"),
        "current_task_id": get("current_task_id"),
        "queue_depth": int(get("queue_depth", 0) or 0),
        "success_count": int(get("success_count", 0) or 0),
        "failure_count": int(get("failure_count", 0) or 0),
        "combo_id": get("combo_id"),
        "pid_host": get("pid_host"),
    }


__all__ = [
    "DEAD_AFTER_SECONDS",
    "DEGRADE_AFTER_SECONDS",
    "HEALTH_DEAD",
    "HEALTH_DEGRADED",
    "HEALTH_HEALTHY",
    "HEALTH_UNKNOWN",
    "HEARTBEAT_INTERVAL_SECONDS",
    "KIND_API",
    "KIND_CLI",
    "KIND_DESKTOP",
    "LEASE_TTL_SECONDS",
    "NON_AUTHORITATIVE_KINDS",
    "VALID_HEALTH",
    "VALID_KINDS",
    "classify_health",
    "decode_capabilities",
    "encode_capabilities",
    "is_authoritative",
    "is_stale",
    "normalise_kind",
    "utcnow",
    "worker_to_dict",
]
