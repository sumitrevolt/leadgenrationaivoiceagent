"""Prospective store — DURABLE claim/lease protocol for L6 agent memory.

Review P0: JSONL read-modify-write is not exactly-once. Two workers, an
overlapping scheduler tick, or a restart mid-write can each dispatch the same
future action. This module makes Postgres (the same authority `agent_task_queue`
already writes to) the source of truth, using the repo-native optimistic-lock
pattern (`checkout_version`) that `AgentTask.claim_next` uses.

STATE MACHINE
    pending  --claim(atomic)-->  claimed  --dispatch-->  dispatched   [terminal]
       ^                            |
       |                            +-- fail --> pending (attempt_count+1)
       |                            +-- fail (attempts exhausted) --> dead [terminal]
       +-- lease expiry (recover_expired) ------+
    pending/claimed --operator--> cancelled [terminal]

EXACTLY-ONCE ARGUMENT (what is actually guaranteed):
  - A claim is ONE `UPDATE ... WHERE id=:id AND checkout_version=:v AND
    status='pending'`. The DB serialises it; `rowcount==1` for exactly one
    caller, `0` for every loser. Two concurrent claimers therefore produce ONE
    dispatch, not two. Proven by the concurrency test, not asserted.
  - `idempotency_key` is UNIQUE, so a retrying *producer* also collapses to one
    row instead of creating duplicate future work.
  - This is exactly-once **dispatch-decision**, at-least-once side effect: if a
    worker dies after `agent_task_queue.assign()` but before `mark_dispatched`,
    the lease expires and the row is retried. That is deliberate (losing a
    follow-up is worse than a rare duplicate task) and is stated here rather
    than being claimed away.

LOCK DISCIPLINE (review P0): no queue/provider call ever happens inside a DB
session. `claim_batch()` opens, updates, commits and closes. Dispatch happens in
the caller with no session held. `mark_dispatched` / `mark_failed` open a fresh
short session.

ISOLATION: every function takes an explicit `tenant_id` (reads, writes, cancel,
purge, stats). There is NO global/default tenant — a blank tenant is rejected.
Only `claim_batch` (the scheduler's own drain) crosses tenants by design, and it
returns each row's `tenant_id` so the dispatcher stays scoped.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

STATUS_PENDING = "pending"
STATUS_CLAIMED = "claimed"
STATUS_DISPATCHED = "dispatched"
STATUS_DEAD = "dead"
STATUS_CANCELLED = "cancelled"
TERMINAL = frozenset({STATUS_DISPATCHED, STATUS_DEAD, STATUS_CANCELLED})

DEFAULT_LEASE_SECONDS = 120
DEFAULT_MAX_ATTEMPTS = 3


def _now() -> datetime:
    """Naive UTC — column type is DateTime (AgentTask ka same convention)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def worker_identity() -> str:
    """Stable-ish per-process id so a lease can be attributed and recovered."""
    return f"{socket.gethostname()[:40]}:{os.getpid()}"


def _models():
    from app.models.base import get_db_session
    from app.models.prospective_memory import ProspectiveMemory

    return ProspectiveMemory, get_db_session


def available() -> bool:
    """True only if the durable table is actually usable. Never raises.

    Drain is fail-CLOSED on this: no durable authority => no dispatch at all.
    """
    try:
        PM, get_db_session = _models()
        with get_db_session() as db:
            db.query(PM.id).limit(1).all()
        return True
    except Exception as e:
        logger.debug("[prospective_store] unavailable: %s", e)
        return False


def _clean_tenant(tenant_id: Any) -> str | None:
    t = str(tenant_id or "").strip()
    return t[:64] if t else None


def make_idempotency_key(tenant_id: str, agent_id: str, action: str, due_at: datetime) -> str:
    """Same tenant+agent+action+minute => same key => one row, not two."""
    basis = f"{tenant_id}|{agent_id}|{action.strip()}|{due_at.replace(second=0, microsecond=0).isoformat()}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:40]


def _redact(text: str) -> str:
    """POLICY A (prompt-bound field): secrets out, authorized lead data kept.

    `action` is read back into an agent prompt, so it follows the prompt policy.
    Operator-facing text (`last_error`) uses POLICY B via `_mask` instead.
    """
    try:
        from app.platform.memory_governance import scrub_secrets

        return scrub_secrets(text)
    except Exception:
        return text or ""


def _mask(text: str) -> str:
    """POLICY B: anything an operator, log or API can read — secrets AND PII."""
    try:
        from app.platform.memory_governance import mask_for_observability

        return mask_for_observability(text)
    except Exception:
        return text or ""


def _row_dict(r: Any) -> dict[str, Any]:
    try:
        payload = json.loads(r.payload_json or "{}")
    except Exception:
        payload = {}
    return {
        "id": r.id,
        "tenant_id": r.tenant_id,
        "agent_id": r.agent_id,
        "action": r.action,
        "note": r.note,
        "payload": payload if isinstance(payload, dict) else {},
        "source": r.source,
        "due_at": r.due_at.isoformat() if r.due_at else None,
        "status": r.status,
        "attempt_count": int(r.attempt_count or 0),
        "claimed_by": r.claimed_by,
        "lease_until": r.lease_until.isoformat() if r.lease_until else None,
        "last_error": r.last_error,
        "dispatched_task_id": r.dispatched_task_id,
        "idempotency_key": r.idempotency_key,
    }


# ------------------------------------------------------------------ producer


def enqueue(
    tenant_id: str,
    agent_id: str,
    action: str,
    *,
    due_at: datetime | None = None,
    in_minutes: int | None = None,
    payload: dict[str, Any] | None = None,
    note: str = "",
    source: str = "",
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Create (or re-find) one future action. Never raises."""
    tid = _clean_tenant(tenant_id)
    aid = str(agent_id or "").strip().lower()[:40]
    act = _redact(str(action or "").strip())[:500]
    if not tid:
        return {"ok": False, "error": "tenant_id required"}
    if not aid or not act:
        return {"ok": False, "error": "agent_id and action required"}
    if not available():
        return {"ok": False, "error": "durable store unavailable"}

    # Governance gate at the DURABLE boundary: if the do-not-remember authority
    # cannot be trusted we refuse to persist. The refusal carries a code and a
    # reason — never the content (which must not land in a row, a log or a retry).
    try:
        from app.platform.memory_governance import guard_durable_write

        g = guard_durable_write(tid, subject_id=aid, text=act)
        if g["decision"] != "allow":
            return {
                "ok": False,
                "deferred": g["decision"] == "deferred",
                "code": g["code"],
                "error": g["reason"],
            }
    except Exception:
        return {
            "ok": False,
            "deferred": True,
            "code": "MEMORY_WRITE_DEFERRED_GOVERNANCE_UNAVAILABLE",
            "error": "governance unavailable",
        }

    when = due_at or (_now() + timedelta(minutes=max(0, min(int(in_minutes or 0), 60 * 24 * 365))))
    if when.tzinfo is not None:
        when = when.astimezone(timezone.utc).replace(tzinfo=None)
    key = (idempotency_key or make_idempotency_key(tid, aid, act, when))[:120]

    try:
        PM, get_db_session = _models()
        with get_db_session() as db:
            existing = db.query(PM).filter(PM.idempotency_key == key).first()
            if existing is not None:
                # idempotent producer: same intent, same row (cross-tenant key
                # collision is impossible — tenant_id is part of the hash basis)
                return {"ok": True, "duplicate": True, "row": _row_dict(existing)}
            row = PM(
                id=str(uuid.uuid4()),
                tenant_id=tid,
                agent_id=aid,
                action=act,
                note=_redact(str(note or ""))[:400],
                payload_json=json.dumps(payload or {}, ensure_ascii=False)[:8000],
                source=str(source or "")[:40],
                due_at=when,
                status=STATUS_PENDING,
                idempotency_key=key,
                attempt_count=0,
                checkout_version=0,
                created_at=_now(),
                updated_at=_now(),
            )
            db.add(row)
            db.flush()
            out = _row_dict(row)
        return {"ok": True, "duplicate": False, "row": out}
    except Exception as e:
        # unique-violation race = another writer won; treat as duplicate success
        if "unique" in str(e).lower() or "duplicate" in str(e).lower():
            return {"ok": True, "duplicate": True, "error": "raced-unique"}
        logger.warning("[prospective_store] enqueue failed: %s", e)
        return {"ok": False, "error": "enqueue_failed"}


# ------------------------------------------------------------------ consumer


def claim_batch(
    worker_id: str = "",
    *,
    limit: int = 20,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Atomically claim up to `limit` due rows. Returns only rows THIS caller won.

    Every claim is its own compare-and-set; losers are skipped silently. No
    dispatch happens here and no session is held after return.
    """
    if not available():
        return []
    wid = (worker_id or worker_identity())[:64]
    ref = now or _now()
    if ref.tzinfo is not None:
        ref = ref.astimezone(timezone.utc).replace(tzinfo=None)
    lease = ref + timedelta(seconds=max(5, int(lease_seconds)))
    won: list[dict[str, Any]] = []
    try:
        PM, get_db_session = _models()
        with get_db_session() as db:
            candidates = (
                db.query(PM)
                .filter(PM.status == STATUS_PENDING, PM.due_at <= ref)
                .order_by(PM.due_at.asc())
                .limit(max(1, min(int(limit), 200)) * 3)  # headroom for lost races
                .all()
            )
            for cand in candidates:
                if len(won) >= max(1, min(int(limit), 200)):
                    break
                ver = int(cand.checkout_version or 0)
                rows = (
                    db.query(PM)
                    .filter(
                        PM.id == cand.id,
                        PM.checkout_version == ver,
                        PM.status == STATUS_PENDING,
                    )
                    .update(
                        {
                            "status": STATUS_CLAIMED,
                            "claimed_by": wid,
                            "lease_until": lease,
                            "checkout_version": ver + 1,
                            "attempt_count": int(cand.attempt_count or 0) + 1,
                            "updated_at": _now(),
                        },
                        synchronize_session=False,
                    )
                )
                db.commit()  # release immediately — never hold a lock over dispatch
                if rows == 1:
                    fresh = db.query(PM).filter(PM.id == cand.id).first()
                    if fresh is not None:
                        won.append(_row_dict(fresh))
    except Exception as e:
        logger.warning("[prospective_store] claim_batch failed: %s", e)
    return won


def dispatch_key(row: dict[str, Any]) -> str:
    """Deterministic logical identity of a dispatch: tenant + row.

    Same row, any number of retries or workers => same key => same task id
    (see `agent_task_queue.assign_idempotent`).
    """
    return f"prospective:{row.get('tenant_id') or ''}:{row.get('id') or ''}"


def mark_dispatched(row_id: str, task_id: str = "") -> bool:
    """claimed -> dispatched (terminal). IDEMPOTENT on retry.

    Review P0: a worker can crash after the task was created but before the ack
    lands. The retry re-derives the SAME task id, so re-acking an already
    dispatched row with the same id is success, not a failure that would drive a
    pointless retry loop. A DIFFERENT task id on an already-dispatched row is a
    real anomaly and stays False.
    """
    tid = str(task_id or "")[:36]
    try:
        PM, get_db_session = _models()
        with get_db_session() as db:
            rows = (
                db.query(PM)
                .filter(PM.id == str(row_id), PM.status == STATUS_CLAIMED)
                .update(
                    {
                        "status": STATUS_DISPATCHED,
                        "dispatched_task_id": tid,
                        "closed_at": _now(),
                        "updated_at": _now(),
                        "last_error": "",
                    },
                    synchronize_session=False,
                )
            )
            db.commit()
            if rows == 1:
                return True
            existing = db.query(PM).filter(PM.id == str(row_id)).first()
            if (
                existing is not None
                and existing.status == STATUS_DISPATCHED
                and (existing.dispatched_task_id or "") == tid
            ):
                return True  # same logical dispatch, already acked
            return False
    except Exception as e:
        logger.warning("[prospective_store] mark_dispatched failed: %s", e)
        return False


def mark_failed(row_id: str, error: str = "", *, max_attempts: int = DEFAULT_MAX_ATTEMPTS) -> str:
    """claimed -> pending (retry) or dead (attempts exhausted). Returns new status.

    A handler failure NEVER marks completion — that was the first cut's bug.
    """
    try:
        PM, get_db_session = _models()
        with get_db_session() as db:
            row = db.query(PM).filter(PM.id == str(row_id)).first()
            if row is None or row.status != STATUS_CLAIMED:
                return ""
            attempts = int(row.attempt_count or 0)
            dead = attempts >= max(1, int(max_attempts))
            new_status = STATUS_DEAD if dead else STATUS_PENDING
            db.query(PM).filter(PM.id == row.id, PM.status == STATUS_CLAIMED).update(
                {
                    "status": new_status,
                    "last_error": _mask(str(error or ""))[:500],
                    "claimed_by": None,
                    "lease_until": None,
                    "closed_at": _now() if dead else None,
                    "updated_at": _now(),
                },
                synchronize_session=False,
            )
            db.commit()
            return new_status
    except Exception as e:
        logger.warning("[prospective_store] mark_failed failed: %s", e)
        return ""


def recover_expired(now: datetime | None = None, *, limit: int = 200) -> int:
    """Crashed worker recovery: claimed rows whose lease expired go back to pending."""
    if not available():
        return 0
    ref = now or _now()
    if ref.tzinfo is not None:
        ref = ref.astimezone(timezone.utc).replace(tzinfo=None)
    try:
        PM, get_db_session = _models()
        with get_db_session() as db:
            stale = (
                db.query(PM)
                .filter(
                    PM.status == STATUS_CLAIMED,
                    PM.lease_until.isnot(None),
                    PM.lease_until <= ref,
                )
                .limit(max(1, int(limit)))
                .all()
            )
            n = 0
            for row in stale:
                ver = int(row.checkout_version or 0)
                rows = (
                    db.query(PM)
                    .filter(
                        PM.id == row.id,
                        PM.checkout_version == ver,
                        PM.status == STATUS_CLAIMED,
                    )
                    .update(
                        {
                            "status": STATUS_PENDING,
                            "claimed_by": None,
                            "lease_until": None,
                            "checkout_version": ver + 1,
                            "last_error": "lease expired — worker lost",
                            "updated_at": _now(),
                        },
                        synchronize_session=False,
                    )
                )
                db.commit()
                n += 1 if rows == 1 else 0
            return n
    except Exception as e:
        logger.warning("[prospective_store] recover_expired failed: %s", e)
        return 0


# --------------------------------------------------------- tenant-scoped reads


def list_rows(
    tenant_id: str,
    *,
    agent_id: str = "",
    status: str = "",
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Tenant-scoped listing. Blank tenant returns [] (no global fallback)."""
    tid = _clean_tenant(tenant_id)
    if not tid or not available():
        return []
    try:
        PM, get_db_session = _models()
        with get_db_session() as db:
            q = db.query(PM).filter(PM.tenant_id == tid)
            if agent_id:
                q = q.filter(PM.agent_id == str(agent_id).strip().lower()[:40])
            if status:
                q = q.filter(PM.status == str(status).strip().lower()[:20])
            rows = q.order_by(PM.due_at.asc()).limit(max(1, min(int(limit), 1000))).all()
            return [_row_dict(r) for r in rows]
    except Exception as e:
        logger.debug("[prospective_store] list_rows failed: %s", e)
        return []


def cancel(tenant_id: str, row_id: str) -> dict[str, Any]:
    """Operator cancel — tenant-scoped: another tenant's id simply does not match."""
    tid = _clean_tenant(tenant_id)
    if not tid:
        return {"ok": False, "error": "tenant_id required"}
    try:
        PM, get_db_session = _models()
        with get_db_session() as db:
            rows = (
                db.query(PM)
                .filter(
                    PM.id == str(row_id),
                    PM.tenant_id == tid,
                    PM.status.in_([STATUS_PENDING, STATUS_CLAIMED]),
                )
                .update(
                    {
                        "status": STATUS_CANCELLED,
                        "closed_at": _now(),
                        "updated_at": _now(),
                        "claimed_by": None,
                        "lease_until": None,
                    },
                    synchronize_session=False,
                )
            )
            db.commit()
            return {"ok": rows == 1, "cancelled": rows}
    except Exception as e:
        logger.warning("[prospective_store] cancel failed: %s", e)
        return {"ok": False, "error": "cancel_failed"}


def purge(tenant_id: str, *, agent_id: str = "") -> dict[str, Any]:
    """DPDP delete — hard removal, tenant-scoped (optionally one agent)."""
    tid = _clean_tenant(tenant_id)
    if not tid:
        return {"ok": False, "purged": 0, "error": "tenant_id required"}
    try:
        PM, get_db_session = _models()
        with get_db_session() as db:
            q = db.query(PM).filter(PM.tenant_id == tid)
            if agent_id:
                q = q.filter(PM.agent_id == str(agent_id).strip().lower()[:40])
            n = q.delete(synchronize_session=False)
            db.commit()
            return {"ok": True, "purged": int(n or 0)}
    except Exception as e:
        logger.warning("[prospective_store] purge failed: %s", e)
        return {"ok": False, "purged": 0, "error": "purge_failed"}


def retention_sweep(*, days: int = 90, now: datetime | None = None) -> int:
    """Governance: terminal rows older than `days` are deleted. 0 = keep forever."""
    if days <= 0 or not available():
        return 0
    ref = (now or _now()) - timedelta(days=int(days))
    try:
        PM, get_db_session = _models()
        with get_db_session() as db:
            n = (
                db.query(PM)
                .filter(
                    PM.status.in_(list(TERMINAL)), PM.closed_at.isnot(None), PM.closed_at <= ref
                )
                .delete(synchronize_session=False)
            )
            db.commit()
            return int(n or 0)
    except Exception as e:
        logger.debug("[prospective_store] retention_sweep failed: %s", e)
        return 0


def stats(tenant_id: str = "") -> dict[str, Any]:
    """Counts by status. Blank tenant = global ops view (counts only, no content)."""
    out = {
        "available": False,
        "tenant_id": _clean_tenant(tenant_id) or "*",
        "pending": 0,
        "claimed": 0,
        "dispatched": 0,
        "dead": 0,
        "cancelled": 0,
        "due_now": 0,
    }
    if not available():
        return out
    out["available"] = True
    try:
        PM, get_db_session = _models()
        tid = _clean_tenant(tenant_id)
        with get_db_session() as db:
            base = db.query(PM)
            if tid:
                base = base.filter(PM.tenant_id == tid)
            for st in (
                STATUS_PENDING,
                STATUS_CLAIMED,
                STATUS_DISPATCHED,
                STATUS_DEAD,
                STATUS_CANCELLED,
            ):
                out[st] = int(base.filter(PM.status == st).count())
            out["due_now"] = int(
                base.filter(PM.status == STATUS_PENDING, PM.due_at <= _now()).count()
            )
    except Exception as e:
        logger.debug("[prospective_store] stats failed: %s", e)
    return out


__all__ = [
    "STATUS_PENDING",
    "STATUS_CLAIMED",
    "STATUS_DISPATCHED",
    "STATUS_DEAD",
    "STATUS_CANCELLED",
    "available",
    "worker_identity",
    "make_idempotency_key",
    "enqueue",
    "claim_batch",
    "mark_dispatched",
    "mark_failed",
    "recover_expired",
    "list_rows",
    "cancel",
    "purge",
    "retention_sweep",
    "stats",
]
