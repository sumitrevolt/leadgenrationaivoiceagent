"""Append-only, hash-chained audit trail for the canonical DevTask ledger.

Why this exists: DevTask is the single canonical 24x7 task truth, so every
state change must be reconstructable and tamper-evident — a supervisor bot has
to be able to answer "who moved this task, from where, to where, and can I
prove the log was not edited?" without trusting the process that wrote it.

The chain math lives in ``app.dev_control.ledger_hash`` (pure, stdlib-only);
this module is only the persistence adapter. Chain rule:

    event_hash = sha256(prev_hash | canonical_json(payload) | from_state |
                        to_state | seq | created_at)
    prev_hash  = previous event's event_hash (genesis = "0" * 64)

Same append-only ``prev_hash -> event_hash`` idea as
``app/agents/harness/session.py`` (ADR-180), but persisted and full-length.

``append_event`` is safe for SINGLE-WRITER use per task: it reads the current
tip (seq + event_hash) and writes the successor inside the caller's
transaction, flushing (never committing) so the caller keeps transaction
control. Multi-writer durability needs a row lock / unique (task_id, seq)
constraint; that is out of scope for this change.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, select

from app.dev_control.ledger_hash import GENESIS_HASH, compute_event_hash, verify_event_chain
from app.models.base import Base


class DevTaskEvent(Base):
    __tablename__ = "dev_task_events"

    id = Column(String(36), primary_key=True)
    task_id = Column(String(36), ForeignKey("dev_tasks.id"), nullable=False, index=True)
    seq = Column(Integer, nullable=False, default=0)
    prev_hash = Column(String(64), nullable=False, default=GENESIS_HASH)
    event_hash = Column(String(64), nullable=False, default=GENESIS_HASH)
    actor = Column(String(120), nullable=True)
    from_state = Column(String(40), nullable=True)
    to_state = Column(String(40), nullable=True)
    payload = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)


def build_event_hash(
    *,
    prev_hash: str,
    payload: Any,
    from_state: str | None,
    to_state: str | None,
    seq: int,
    created_at: datetime,
) -> str:
    """Thin re-export of the pure hasher so callers need one import."""
    return compute_event_hash(
        prev_hash=prev_hash,
        payload=payload,
        from_state=from_state,
        to_state=to_state,
        seq=seq,
        created_at=created_at,
    )


async def append_event(
    session,
    task_id: str,
    actor: str | None,
    from_state: str | None,
    to_state: str | None,
    payload: Any | None = None,
    *,
    now: datetime | None = None,
    event_id: str | None = None,
) -> DevTaskEvent:
    """Append one chained event for ``task_id`` and return the flushed row.

    Reads the chain tip (highest seq) for the task, computes seq = tip+1 and
    prev_hash = tip.event_hash (genesis when this is the first event), then
    adds + flushes the new row. Does NOT commit — the caller owns the
    transaction, so a task update and its audit event land atomically.
    """
    now = now or datetime.utcnow()
    tip = (
        await session.execute(
            select(DevTaskEvent.seq, DevTaskEvent.event_hash)
            .where(DevTaskEvent.task_id == task_id)
            .order_by(DevTaskEvent.seq.desc())
            .limit(1)
        )
    ).first()

    seq = 1
    prev_hash = GENESIS_HASH
    if tip is not None:
        seq = int(tip[0] or 0) + 1
        prev_hash = str(tip[1] or GENESIS_HASH)

    body = dict(payload) if isinstance(payload, dict) else (payload if payload is not None else {})

    event = DevTaskEvent(
        id=event_id or str(uuid.uuid4()),
        task_id=str(task_id),
        seq=seq,
        prev_hash=prev_hash,
        event_hash=compute_event_hash(
            prev_hash=prev_hash,
            payload=body,
            from_state=from_state,
            to_state=to_state,
            seq=seq,
            created_at=now,
        ),
        actor=actor,
        from_state=from_state,
        to_state=to_state,
        payload=body,
        created_at=now,
    )
    session.add(event)
    await session.flush()
    return event


async def verify_task_chain(session, task_id: str) -> tuple[bool, str]:
    """Recompute the whole chain for one task. Returns ``(ok, reason)``."""
    rows = (
        (
            await session.execute(
                select(DevTaskEvent)
                .where(DevTaskEvent.task_id == task_id)
                .order_by(DevTaskEvent.seq.asc())
            )
        )
        .scalars()
        .all()
    )
    return verify_event_chain(list(rows))


def row_to_chain_dict(event: Any) -> dict[str, Any]:
    """Flatten a DevTaskEvent row (or mapping) into the verifier's shape."""
    return {
        "seq": getattr(event, "seq", None),
        "prev_hash": getattr(event, "prev_hash", None),
        "event_hash": getattr(event, "event_hash", None),
        "from_state": getattr(event, "from_state", None),
        "to_state": getattr(event, "to_state", None),
        "payload": getattr(event, "payload", None),
        "created_at": getattr(event, "created_at", None),
    }


__all__ = [
    "DevTaskEvent",
    "append_event",
    "build_event_hash",
    "row_to_chain_dict",
    "verify_task_chain",
]
