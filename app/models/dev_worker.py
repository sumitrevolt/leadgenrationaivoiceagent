"""Worker identity + liveness registry for the 24x7 orchestration plane.

Why this exists
---------------
``dev_tasks`` tells us WHAT has to be done, but nothing in the schema answered
"WHO is doing it, and are they still alive?" — the Owner Command Center question
#"kaunsa bot/agent stuck hai" (Q4) had **no row source at all**. Every candidate
was either an in-memory dict, a Hermes process scan, or
``data/workforce_live_status.json`` (self-refuting, gitignored — banned by the
truth gate in ``AGENTS.md``). This table is the first honest source for that
question.

Contract: ``docs/architecture/24X7_ARCHITECTURE_RECORD.md`` §3 — heartbeat 60 s,
lease TTL 600 s (lockstep with ``app/dev_control/claims.py``
DEFAULT_LEASE_SECONDS), staleness at 10 missed beats, reap sweep 60 s.

The liveness MATH lives in ``app/platform/worker_health.py`` (pure, stdlib-only)
exactly like ``app/dev_control/ledger_hash.py`` does for the audit chain; this
module is the persistence adapter and re-exports those helpers so callers need
one import. Kept split so the rules stay testable while this repo's ``.venv``
is missing.

Desktop workers (Hermes / Claude / OpenClaw / WorkBuddy / Codex) register under
the SAME contract but are **advisory until HMAC-attested** — a desktop row must
never be treated as authoritative for task ownership. Enforced by
``is_authoritative()``, not by convention.

Secrets: this table intentionally has **no credential, token or env column**.
Anything rendered from it can be shown to the owner as-is.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any, Iterable

from sqlalchemy import Column, DateTime, Integer, String, Text, select, update

from app.models.base import Base
from app.platform.worker_health import (  # noqa: F401  (re-exported for callers)
    DEAD_AFTER_SECONDS,
    DEGRADE_AFTER_SECONDS,
    HEALTH_DEAD,
    HEALTH_DEGRADED,
    HEALTH_HEALTHY,
    HEALTH_UNKNOWN,
    HEARTBEAT_INTERVAL_SECONDS,
    KIND_API,
    KIND_CLI,
    KIND_DESKTOP,
    LEASE_TTL_SECONDS,
    VALID_HEALTH,
    VALID_KINDS,
    classify_health,
    decode_capabilities,
    encode_capabilities,
    is_authoritative,
    is_stale,
    normalise_kind,
    worker_to_dict,
)
from app.platform.worker_health import (
    utcnow as _utcnow,
)


class DevWorker(Base):
    """One registered worker process (CLI bot, API supervisor, or desktop app)."""

    __tablename__ = "dev_workers"

    worker_id = Column(String(120), primary_key=True)
    kind = Column(String(20), nullable=False, default=KIND_CLI, index=True)
    supervisor_bot = Column(String(80), nullable=True, index=True)
    capabilities = Column(Text, nullable=True)  # JSON-encoded list[str]
    version = Column(String(60), nullable=True)
    started_at = Column(DateTime, nullable=False, default=_utcnow)
    heartbeat_ts = Column(DateTime, nullable=True, index=True)
    lease_id = Column(String(120), nullable=True)
    current_task_id = Column(String(36), nullable=True, index=True)
    queue_depth = Column(Integer, nullable=False, default=0)
    success_count = Column(Integer, nullable=False, default=0)
    failure_count = Column(Integer, nullable=False, default=0)
    combo_id = Column(String(60), nullable=True, index=True)
    health = Column(String(20), nullable=False, default=HEALTH_UNKNOWN, index=True)
    pid_host = Column(String(255), nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow, index=True)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)


# ---------------------------------------------------------------------------
# Async registry — mirrors app/dev_control/claims.py: single conditional UPDATE,
# never read-then-write, so two supervisors racing on one worker_id cannot both
# believe they own it.
# ---------------------------------------------------------------------------


async def register(
    db,
    worker_id: str,
    *,
    kind: str = KIND_CLI,
    supervisor_bot: str | None = None,
    capabilities: Iterable[str] | None = None,
    version: str | None = None,
    pid_host: str | None = None,
    now: datetime | None = None,
) -> DevWorker:
    """Idempotently register (or re-register) a worker. Safe on restart.

    A restart reuses the same ``worker_id`` and resets ``started_at`` — it does
    NOT reset the success/failure counters, so a crash-looping worker still
    shows its failure history instead of looking brand new.
    """
    now = now or _utcnow()
    kind = normalise_kind(kind)
    existing = await db.get(DevWorker, worker_id)
    if existing is None:
        worker = DevWorker(
            worker_id=worker_id,
            kind=kind,
            supervisor_bot=supervisor_bot,
            capabilities=encode_capabilities(capabilities),
            version=version,
            started_at=now,
            heartbeat_ts=now,
            health=HEALTH_HEALTHY,
            pid_host=pid_host,
            created_at=now,
            updated_at=now,
        )
        db.add(worker)
        await db.flush()
        return worker

    await db.execute(
        update(DevWorker)
        .where(DevWorker.worker_id == worker_id)
        .values(
            kind=kind,
            supervisor_bot=supervisor_bot if supervisor_bot is not None else existing.supervisor_bot,
            capabilities=(
                encode_capabilities(capabilities)
                if capabilities is not None
                else existing.capabilities
            ),
            version=version if version is not None else existing.version,
            pid_host=pid_host if pid_host is not None else existing.pid_host,
            heartbeat_ts=now,
            started_at=now,
            health=HEALTH_HEALTHY,
            updated_at=now,
        )
    )
    await db.flush()
    await db.refresh(existing)
    return existing


async def heartbeat(
    db,
    worker_id: str,
    *,
    current_task_id: str | None = None,
    queue_depth: int | None = None,
    combo_id: str | None = None,
    lease_id: str | None = None,
    now: datetime | None = None,
) -> bool:
    """Record a liveness beat. Returns False for an unregistered worker."""
    now = now or _utcnow()
    values: dict[str, Any] = {
        "heartbeat_ts": now,
        "health": HEALTH_HEALTHY,
        "updated_at": now,
    }
    if current_task_id is not None:
        values["current_task_id"] = current_task_id
    if queue_depth is not None:
        values["queue_depth"] = max(0, int(queue_depth))
    if combo_id is not None:
        values["combo_id"] = combo_id
    if lease_id is not None:
        values["lease_id"] = lease_id
    result = await db.execute(
        update(DevWorker).where(DevWorker.worker_id == worker_id).values(**values)
    )
    await db.flush()
    return bool(result.rowcount or 0)


async def mark_result(
    db,
    worker_id: str,
    *,
    success: bool,
    error: str | None = None,
    now: datetime | None = None,
) -> bool:
    """Bump success/failure counter and clear ``current_task_id``."""
    now = now or _utcnow()
    worker = await db.get(DevWorker, worker_id)
    if worker is None:
        return False
    values: dict[str, Any] = {
        "current_task_id": None,
        "updated_at": now,
        "last_error": None if success else (error or "unspecified failure"),
    }
    if success:
        values["success_count"] = int(worker.success_count or 0) + 1
    else:
        values["failure_count"] = int(worker.failure_count or 0) + 1
    await db.execute(
        update(DevWorker).where(DevWorker.worker_id == worker_id).values(**values)
    )
    await db.flush()
    return True


async def reap_stale(
    db,
    *,
    now: datetime | None = None,
    dead_after: int = DEAD_AFTER_SECONDS,
    limit: int = 200,
) -> list[str]:
    """Mark dead workers ``dead``; returns the reaped worker_ids.

    Deliberately does NOT touch ``dev_tasks`` — releasing a task lease is
    ``app.dev_control.reconcile``'s job (single writer). This only flips the
    registry's own health flag so the dashboard stops showing ghosts as live.
    """
    now = now or _utcnow()
    cutoff = now - timedelta(seconds=max(1, int(dead_after)))
    stale_ids = list(
        (
            await db.scalars(
                select(DevWorker.worker_id)
                .where(
                    DevWorker.heartbeat_ts.is_not(None),
                    DevWorker.heartbeat_ts < cutoff,
                    DevWorker.health != HEALTH_DEAD,
                )
                .limit(max(1, limit))
            )
        ).all()
    )
    if not stale_ids:
        return []
    await db.execute(
        update(DevWorker)
        .where(DevWorker.worker_id.in_(stale_ids))
        .values(health=HEALTH_DEAD, updated_at=now)
    )
    await db.flush()
    return [str(w) for w in stale_ids]


async def snapshot(
    db,
    *,
    now: datetime | None = None,
    limit: int = 500,
) -> dict[str, Any]:
    """Dashboard payload for Owner Command Center module 2 (and Q4 / Q10).

    Never fabricates: with zero rows it reports ``instrumented=False`` so the UI
    renders "24x7 plane not instrumented" instead of a fake green tile.
    """
    now = now or _utcnow()
    rows = list(
        (
            await db.scalars(
                select(DevWorker)
                .order_by(DevWorker.kind.asc(), DevWorker.worker_id.asc())
                .limit(max(1, limit))
            )
        ).all()
    )
    workers = [worker_to_dict(w, now=now) for w in rows]
    return {
        "generated_at": now,
        "instrumented": len(workers) > 0,
        "total": len(workers),
        "healthy": sum(1 for w in workers if w["health"] == HEALTH_HEALTHY),
        "degraded": sum(1 for w in workers if w["health"] == HEALTH_DEGRADED),
        "dead": sum(1 for w in workers if w["health"] == HEALTH_DEAD),
        "unknown": sum(1 for w in workers if w["health"] == HEALTH_UNKNOWN),
        "authoritative": sum(1 for w in workers if w["authoritative"]),
        "advisory_only": sum(1 for w in workers if not w["authoritative"]),
        "stuck": [
            w
            for w in workers
            if w["health"] in (HEALTH_DEAD, HEALTH_DEGRADED) and w["current_task_id"]
        ],
        "workers": workers,
    }


def new_worker_id(prefix: str = "wkr") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


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
    "VALID_HEALTH",
    "VALID_KINDS",
    "DevWorker",
    "classify_health",
    "decode_capabilities",
    "encode_capabilities",
    "heartbeat",
    "is_authoritative",
    "is_stale",
    "mark_result",
    "new_worker_id",
    "normalise_kind",
    "register",
    "reap_stale",
    "snapshot",
    "worker_to_dict",
]
