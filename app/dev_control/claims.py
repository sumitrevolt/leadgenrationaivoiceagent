"""Atomic task claiming for the engineering control plane.

The API-layer claim (read -> validate -> write) had a lost-update race: two
workers could both read state=queued, both pass the transition check, and both
commit -- the second silently overwriting the first worker's lease. These
helpers replace that with a single conditional UPDATE whose rowcount proves
exactly one winner (works on Postgres and SQLite alike; no advisory locks
needed). tmux/worker memory is never the source of truth -- the DB row is.

Design rules (mirrors reconcile.py):
  * claim only from QUEUED -- expired in-flight leases are reclaimed by
    ``reconcile.reconcile_leases``, not stolen here.
  * heartbeat only extends a lease the caller actually owns.
  * ``claim_next`` scans a bounded candidate window in priority order and
    atomically claims the first winnable row (loser rows are simply skipped).
  * a task serving an exponential-backoff delay (``next_eligible_at`` set by
    reconcile) is NOT claimable until that timestamp passes.

GENERALISATION (T02)
--------------------
The conditional-UPDATE core used to be hard-coded to ``DevTask``. It is now
expressed **once** against a small :class:`LeaseSpec` so any leaseable row model
can reuse it: the render plane leases ``RenderJob`` rows with the *same*
single-statement semantics. The ``DevTask`` wrappers -- ``atomic_claim``,
``atomic_heartbeat``, ``claim_next`` -- keep their exact signatures and
behaviour (same states, same columns, same priority-then-age ordering). This is
one generalisation, **not** a fork and **not** a second lease engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import or_, select, update

from app.dev_control.service import TaskState

DEFAULT_LEASE_SECONDS = 600
_HEARTBEAT_STATES = (TaskState.CLAIMED.value, TaskState.RUNNING.value)


@dataclass(frozen=True)
class LeaseSpec:
    """Describes a leaseable row: which model, which columns, which states.

    Column names are plain strings (resolved via ``getattr(model, name)``) so
    this module never imports a concrete model at import time -- the DevTask and
    RenderJob specs are built lazily by their owners.
    """

    model: Any
    queued_value: str = "queued"
    claimed_value: str = "claimed"
    heartbeat_values: tuple[str, ...] = ("claimed", "running")
    id_attr: str = "id"
    state_attr: str = "state"
    owner_attr: str = "lease_owner"
    until_attr: str = "lease_until"
    updated_attr: str = "updated_at"
    eligible_attr: str = "next_eligible_at"
    order_columns: tuple[Any, ...] = ()


def dev_task_spec() -> LeaseSpec:
    """The :class:`LeaseSpec` for the canonical DevTask ledger (built lazily)."""
    from app.models.dev_task import DevTask

    return LeaseSpec(
        model=DevTask,
        queued_value=TaskState.QUEUED.value,
        claimed_value=TaskState.CLAIMED.value,
        heartbeat_values=(TaskState.CLAIMED.value, TaskState.RUNNING.value),
        order_columns=(DevTask.priority.desc(), DevTask.created_at.asc()),
    )


def _col(spec: LeaseSpec, attr: str):
    return getattr(spec.model, attr)


def _backoff_predicate_for(spec: LeaseSpec, now: datetime):
    """TRUE when a row is not currently serving an exponential-backoff delay.

    ``next_eligible_at`` is set by ``reconcile`` when an expired lease is
    requeued. NULL means "eligible immediately", so every row created before the
    column existed (and every never-retried row) stays claimable -- the predicate
    is backwards compatible by construction.
    """
    eligible = _col(spec, spec.eligible_attr)
    return or_(eligible.is_(None), eligible <= now)


def _backoff_predicate(now: datetime):
    """DevTask backoff predicate (kept for continuity with the original module)."""
    return _backoff_predicate_for(dev_task_spec(), now)


async def claim_row(
    db,
    spec: LeaseSpec,
    row_id: str,
    worker: str,
    *,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    now: datetime | None = None,
    respect_backoff: bool = False,
) -> bool:
    """Claim ONE queued row of ``spec``. Returns True only for the single winner.

    ``respect_backoff`` rides on the SAME conditional UPDATE -- still a single
    statement, never a read-then-write.
    """
    now = now or datetime.utcnow()
    conditions = [
        _col(spec, spec.id_attr) == row_id,
        _col(spec, spec.state_attr) == spec.queued_value,
    ]
    if respect_backoff:
        conditions.append(_backoff_predicate_for(spec, now))
    result = await db.execute(
        update(spec.model)
        .where(*conditions)
        .values(
            **{
                spec.state_attr: spec.claimed_value,
                spec.owner_attr: worker,
                spec.until_attr: now + timedelta(seconds=lease_seconds),
                spec.updated_attr: now,
            }
        )
    )
    await db.commit()
    return bool(result.rowcount or 0)


async def heartbeat_row(
    db,
    spec: LeaseSpec,
    row_id: str,
    worker: str,
    *,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    now: datetime | None = None,
) -> bool:
    """Extend a lease the caller owns. Returns False on steal attempts."""
    now = now or datetime.utcnow()
    result = await db.execute(
        update(spec.model)
        .where(
            _col(spec, spec.id_attr) == row_id,
            _col(spec, spec.owner_attr) == worker,
            _col(spec, spec.state_attr).in_(spec.heartbeat_values),
        )
        .values(
            **{
                spec.until_attr: now + timedelta(seconds=lease_seconds),
                spec.updated_attr: now,
            }
        )
    )
    await db.commit()
    return bool(result.rowcount or 0)


async def claim_next_row(
    db,
    spec: LeaseSpec,
    worker: str,
    *,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    scan_limit: int = 10,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """Atomically claim the highest-priority queued row of ``spec``; None when idle.

    Candidates are scanned oldest-first within the spec's ordering; each
    candidate is claimed with the same conditional UPDATE, so a concurrent worker
    taking a row just moves us to the next candidate. Backoff is honoured twice:
    once in the candidate SELECT and once inside the claim UPDATE.
    """
    now = now or datetime.utcnow()
    order = spec.order_columns or (_col(spec, "created_at").asc(),)
    stmt = (
        select(_col(spec, spec.id_attr))
        .where(
            _col(spec, spec.state_attr) == spec.queued_value,
            _backoff_predicate_for(spec, now),
        )
        .order_by(*order)
        .limit(max(1, scan_limit))
    )
    for candidate_id in (await db.scalars(stmt)).all():
        if await claim_row(
            db,
            spec,
            candidate_id,
            worker,
            lease_seconds=lease_seconds,
            now=now,
            respect_backoff=True,
        ):
            row = await db.get(spec.model, candidate_id)
            return {"task_id": candidate_id, "task": row}
    return None


# ------------------------------------------------------------ DevTask wrappers
async def atomic_claim(
    db,
    task_id: str,
    worker: str,
    *,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    now: datetime | None = None,
    respect_backoff: bool = False,
) -> bool:
    """Claim one QUEUED DevTask. Returns True only for the single winning worker.

    ``respect_backoff`` defaults to False so the explicit-by-id admin claim
    (``POST /dev-tasks/{id}/claim``) keeps its historical behaviour; the scanner
    ``claim_next`` opts in so a backed-off task cannot be picked up early.
    """
    return await claim_row(
        db,
        dev_task_spec(),
        task_id,
        worker,
        lease_seconds=lease_seconds,
        now=now,
        respect_backoff=respect_backoff,
    )


async def atomic_heartbeat(
    db,
    task_id: str,
    worker: str,
    *,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    now: datetime | None = None,
) -> bool:
    """Extend a DevTask lease the caller owns. Returns False on steal attempts."""
    return await heartbeat_row(
        db,
        dev_task_spec(),
        task_id,
        worker,
        lease_seconds=lease_seconds,
        now=now,
    )


async def claim_next(
    db,
    worker: str,
    *,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    scan_limit: int = 10,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """Atomically claim the highest-priority QUEUED DevTask; None when idle."""
    return await claim_next_row(
        db,
        dev_task_spec(),
        worker,
        lease_seconds=lease_seconds,
        scan_limit=scan_limit,
        now=now,
    )


__all__ = [
    "DEFAULT_LEASE_SECONDS",
    "LeaseSpec",
    "atomic_claim",
    "atomic_heartbeat",
    "claim_next",
    "claim_next_row",
    "claim_row",
    "dev_task_spec",
    "heartbeat_row",
]
