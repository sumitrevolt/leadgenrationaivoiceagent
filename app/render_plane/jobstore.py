"""Render-job persistence: lease / heartbeat / complete / reclaim (T02).

The job ledger is the durable source of truth for the render plane. It mirrors
the engineering control plane's proven lease model **without forking it**:

  * the conditional-UPDATE claim is the ONE in ``app.dev_control.claims``
    (generalised to a :class:`~app.dev_control.claims.LeaseSpec`, reused here);
  * the expired-lease reclaim decision is the pure
    ``app.dev_control.lease_policy.plan_lease_reclaim`` (60s·2^n backoff, 15m cap,
    jitter) — no second lease engine exists.

State machine (design §7 — no new vocabulary invented)::

    queued → leased → rendering → uploading → done
    failed → queued        (retryable, exponential backoff)
    leased|rendering|uploading → queued|failed   (expired-lease reclaim)

Every public entry returns a dict and **never raises** (mirrors ``store.py``).
Tenant isolation is enforced on every read: a cross-tenant id is
``tenant_mismatch``, never another tenant's row.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Column, DateTime, Integer, String, Text, func, select

from app.dev_control.claims import (
    DEFAULT_LEASE_SECONDS,
    LeaseSpec,
    claim_next_row,
    heartbeat_row,
)
from app.dev_control.lease_policy import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_RECONCILE_LIMIT,
    plan_lease_reclaim,
    sample_retry_backoff_seconds,
)
from app.models.base import Base
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# ---------------------------------------------------------------- vocabulary
STATE_QUEUED = "queued"
STATE_LEASED = "leased"
STATE_RENDERING = "rendering"
STATE_UPLOADING = "uploading"
STATE_DONE = "done"
STATE_FAILED = "failed"
STATE_EXPIRED = "expired"

RENDER_JOB_STATES: frozenset[str] = frozenset(
    {
        STATE_QUEUED,
        STATE_LEASED,
        STATE_RENDERING,
        STATE_UPLOADING,
        STATE_DONE,
        STATE_FAILED,
        STATE_EXPIRED,
    }
)

#: States whose lease can expire and be reclaimed.
_IN_FLIGHT = (STATE_LEASED, STATE_RENDERING, STATE_UPLOADING)

LEASE_SECONDS_ENV = "RENDER_PLANE_LEASE_SECONDS"


def lease_seconds() -> int:
    """Worker lease TTL, read at call time (flag table: default 600)."""
    try:
        return max(30, min(86_400, int(os.getenv(LEASE_SECONDS_ENV, str(DEFAULT_LEASE_SECONDS)))))
    except Exception:
        return DEFAULT_LEASE_SECONDS


def job_id_for(tenant_id: str, creative_id: str, revision: int) -> str:
    """Stable, collision-free job id: ``rp:<tenant>:<creative>:rev<N>``."""
    return f"rp:{str(tenant_id or '').strip()}:{str(creative_id or '').strip()}:rev{int(revision or 0)}"


# ------------------------------------------------------------- datetimes
def _utcnow() -> datetime:
    return datetime.utcnow()


def _dt_to_epoch(value: datetime | None) -> float:
    """Naive UTC datetimes (how the DB stores them) → epoch seconds."""
    if value is None:
        return 0.0
    try:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return float(value.timestamp())
    except Exception:
        return 0.0


def _epoch_to_dt(value: float | None) -> datetime | None:
    try:
        ts = float(value or 0.0)
    except (TypeError, ValueError):
        return None
    if ts <= 0.0:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)


# --------------------------------------------------------------- dataclass
@dataclass
class RenderJob:
    """The render job as the worker sees it (floats for times, JSON for evidence)."""

    job_id: str
    idempotency_key: str
    tenant_id: str
    creative_id: str
    revision: int
    spec_hash: str = ""
    template_id: str = ""
    aspect_ratio: str = ""
    state: str = STATE_QUEUED
    lease_owner: str = ""
    lease_until: float = 0.0
    attempt: int = 0
    retry_count: int = 0
    next_eligible_at: float = 0.0
    artifact_path: str = ""
    artifact_sha256: str = ""
    artifact_bytes: int = 0
    manifest_hash: str = ""
    network_isolation: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ------------------------------------------------------------- SQLAlchemy row
class RenderJobRow(Base):
    """Durable render-job row. Lease columns mirror ``DevTask`` exactly."""

    __tablename__ = "render_jobs"

    id = Column(String(180), primary_key=True)
    idempotency_key = Column(String(180), nullable=False, unique=True, index=True)
    tenant_id = Column(String(64), nullable=False, index=True)
    creative_id = Column(String(80), nullable=False, index=True)
    revision = Column(Integer, nullable=False, default=0)
    spec_hash = Column(String(64), nullable=False, default="")
    template_id = Column(String(80), nullable=False, default="")
    aspect_ratio = Column(String(16), nullable=False, default="")
    state = Column(String(24), nullable=False, default=STATE_QUEUED, index=True)
    lease_owner = Column(String(120), nullable=True)
    lease_until = Column(DateTime, nullable=True, index=True)
    attempt = Column(Integer, nullable=False, default=0)
    retry_count = Column(Integer, nullable=False, default=0)
    next_eligible_at = Column(DateTime, nullable=True, index=True)
    artifact_path = Column(String(500), nullable=False, default="")
    artifact_sha256 = Column(String(64), nullable=False, default="")
    artifact_bytes = Column(Integer, nullable=False, default=0)
    manifest_hash = Column(String(64), nullable=False, default="")
    network_isolation = Column(Text, nullable=False, default="{}")
    error = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, nullable=False, default=_utcnow, index=True)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)


def render_job_spec() -> LeaseSpec:
    """The :class:`LeaseSpec` that lets ``claims`` lease a ``RenderJobRow``."""
    return LeaseSpec(
        model=RenderJobRow,
        queued_value=STATE_QUEUED,
        claimed_value=STATE_LEASED,
        heartbeat_values=(STATE_LEASED, STATE_RENDERING),
        order_columns=(RenderJobRow.created_at.asc(),),
    )


# ------------------------------------------------------------------ mapping
def _row_to_job(row: RenderJobRow) -> RenderJob:
    iso: dict[str, Any] = {}
    try:
        parsed = json.loads(row.network_isolation or "{}")
        if isinstance(parsed, dict):
            iso = parsed
    except Exception:
        iso = {}
    return RenderJob(
        job_id=str(row.id),
        idempotency_key=str(row.idempotency_key),
        tenant_id=str(row.tenant_id),
        creative_id=str(row.creative_id),
        revision=int(row.revision or 0),
        spec_hash=str(row.spec_hash or ""),
        template_id=str(row.template_id or ""),
        aspect_ratio=str(row.aspect_ratio or ""),
        state=str(row.state or STATE_QUEUED),
        lease_owner=str(row.lease_owner or ""),
        lease_until=_dt_to_epoch(row.lease_until),
        attempt=int(row.attempt or 0),
        retry_count=int(row.retry_count or 0),
        next_eligible_at=_dt_to_epoch(row.next_eligible_at),
        artifact_path=str(row.artifact_path or ""),
        artifact_sha256=str(row.artifact_sha256 or ""),
        artifact_bytes=int(row.artifact_bytes or 0),
        manifest_hash=str(row.manifest_hash or ""),
        network_isolation=iso,
        error=str(row.error or ""),
        created_at=_dt_to_epoch(row.created_at),
        updated_at=_dt_to_epoch(row.updated_at),
    )


def _ok(job: RenderJob | None, **extra: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"ok": True, "job": job.to_dict() if job else None}
    out.update(extra)
    return out


def _fail(code: str, **extra: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"ok": False, "error": code}
    out.update(extra)
    return out


# -------------------------------------------------------------- lease token
def _lease_token(job_id: str, worker: str, attempt: int) -> str:
    """A derived capability binding a lease to (job, worker, attempt).

    NOT the worker token: the shared secret is the HMAC key and is never emitted.
    """
    secret = (os.getenv("RENDER_PLANE_WORKER_TOKEN") or "").encode("utf-8")
    msg = f"{job_id}|{worker}|{int(attempt or 0)}".encode("utf-8")
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()[:32]


def verify_lease_token(job_id: str, worker: str, attempt: int, token: str) -> bool:
    """Constant-time check of a lease token. Never raises."""
    try:
        expected = _lease_token(job_id, worker, attempt)
        return hmac.compare_digest(expected, str(token or ""))
    except Exception:
        return False


# ------------------------------------------------------------------- writes
async def ensure_table(engine) -> bool:
    """Create the ``render_jobs`` table if absent (tests / first boot). Never raises."""
    try:
        async with engine.begin() as conn:
            await conn.run_sync(RenderJobRow.__table__.create, checkfirst=True)
        return True
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("[render_plane] ensure_table failed: %s", exc)
        return False


async def create_job(
    db,
    *,
    tenant_id: str,
    creative_id: str,
    revision: int = 0,
    spec_hash: str = "",
    template_id: str = "",
    aspect_ratio: str = "",
) -> dict[str, Any]:
    """Idempotently create (or fetch) the job row for one creative revision."""
    try:
        tid = str(tenant_id or "").strip()
        cid = str(creative_id or "").strip()
        if not tid or not cid:
            return _fail("invalid_request")
        job_id = job_id_for(tid, cid, revision)
        existing = await db.get(RenderJobRow, job_id)
        if existing is not None:
            return _ok(_row_to_job(existing), created=False)

        now = _utcnow()
        row = RenderJobRow(
            id=job_id,
            idempotency_key=job_id,
            tenant_id=tid,
            creative_id=cid,
            revision=int(revision or 0),
            spec_hash=str(spec_hash or "")[:64],
            template_id=str(template_id or "")[:80],
            aspect_ratio=str(aspect_ratio or "")[:16],
            state=STATE_QUEUED,
            attempt=0,
            retry_count=0,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        try:
            await db.commit()
        except Exception:
            # Unique idempotency_key: a concurrent create won. Re-fetch.
            await db.rollback()
            existing = await db.get(RenderJobRow, job_id)
            if existing is not None:
                return _ok(_row_to_job(existing), created=False)
            raise
        return _ok(_row_to_job(row), created=True)
    except Exception as exc:
        logger.warning("[render_plane] create_job failed: %s", exc)
        return _fail(f"create_failed:{type(exc).__name__}")


async def claim_next_job(
    db,
    worker: str,
    *,
    lease_seconds_: int | None = None,
    scan_limit: int = 10,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Atomically lease the oldest queued job. Returns ``job=None`` when idle."""
    try:
        lease = int(lease_seconds_ or lease_seconds())
        claimed = await claim_next_row(
            db,
            render_job_spec(),
            worker,
            lease_seconds=lease,
            scan_limit=scan_limit,
            now=now,
        )
        if not claimed:
            return _ok(None, leased=False)
        row = await db.get(RenderJobRow, claimed["task_id"])
        if row is None:  # pragma: no cover - defensive
            return _fail("job_vanished")
        row.attempt = int(row.attempt or 0) + 1
        row.updated_at = now or _utcnow()
        await db.commit()
        job = _row_to_job(row)
        return _ok(
            job,
            leased=True,
            lease_token=_lease_token(job.job_id, worker, job.attempt),
            expires_at=job.lease_until,
        )
    except Exception as exc:
        logger.warning("[render_plane] claim_next_job failed: %s", exc)
        return _fail(f"claim_failed:{type(exc).__name__}")


async def heartbeat_job(
    db,
    job_id: str,
    worker: str,
    *,
    lease_seconds_: int | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Extend a lease the caller owns. A steal attempt is refused, not raised."""
    try:
        lease = int(lease_seconds_ or lease_seconds())
        extended = await heartbeat_row(
            db,
            render_job_spec(),
            str(job_id or ""),
            worker,
            lease_seconds=lease,
            now=now,
        )
        row = await db.get(RenderJobRow, str(job_id or ""))
        expires_at = _dt_to_epoch(row.lease_until) if row is not None else 0.0
        return {"ok": True, "extended": bool(extended), "expires_at": expires_at}
    except Exception as exc:
        logger.warning("[render_plane] heartbeat_job failed: %s", exc)
        return _fail(f"heartbeat_failed:{type(exc).__name__}")


async def mark_rendering(db, job_id: str, worker: str) -> dict[str, Any]:
    """Move a leased job to ``rendering`` (owned lease only). Never raises."""
    return await _set_inflight_state(db, job_id, worker, STATE_RENDERING)


async def mark_uploading(db, job_id: str, worker: str) -> dict[str, Any]:
    """Move a rendering job to ``uploading`` (owned lease only). Never raises."""
    return await _set_inflight_state(db, job_id, worker, STATE_UPLOADING)


async def _set_inflight_state(db, job_id: str, worker: str, state: str) -> dict[str, Any]:
    try:
        row = await db.get(RenderJobRow, str(job_id or ""))
        if row is None:
            return _fail("job_not_found")
        if str(row.lease_owner or "") != str(worker or ""):
            return _fail("lease_not_owned")
        if row.state not in _IN_FLIGHT:
            return _fail(f"illegal_state:{row.state}")
        row.state = state
        row.updated_at = _utcnow()
        await db.commit()
        return _ok(_row_to_job(row))
    except Exception as exc:
        logger.warning("[render_plane] mark_state(%s) failed: %s", state, exc)
        return _fail(f"state_failed:{type(exc).__name__}")


async def complete_job(
    db,
    *,
    job_id: str,
    worker: str,
    revision: int = 0,
    attempt: int = 0,
    sha256: str = "",
    manifest_hash: str = "",
    artifact_path: str = "",
    artifact_bytes: int = 0,
    network_isolation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Record a finished artifact. Idempotent on ``(job_id, revision, sha256)``.

    * same ``(job_id, revision, sha256)`` already ``done`` → idempotent success;
    * same ``(job_id, revision)`` different ``sha256`` → conflict, first wins.
    """
    try:
        jid = str(job_id or "")
        row = await db.get(RenderJobRow, jid)
        if row is None:
            return _fail("job_not_found")

        digest = str(sha256 or "")
        if row.state == STATE_DONE:
            if str(row.artifact_sha256 or "") == digest and int(row.revision or 0) == int(
                revision or 0
            ):
                return _ok(_row_to_job(row), idempotent=True, conflict=False)
            return _fail(
                "artifact_conflict",
                job=_row_to_job(row).to_dict(),
                idempotent=False,
                conflict=True,
            )

        if str(row.lease_owner or "") != str(worker or ""):
            return _fail("lease_not_owned", stale_attempt=True)

        row.state = STATE_DONE
        row.artifact_path = str(artifact_path or "")[:500]
        row.artifact_sha256 = digest[:64]
        row.artifact_bytes = max(0, int(artifact_bytes or 0))
        row.manifest_hash = str(manifest_hash or "")[:64]
        if isinstance(network_isolation, dict) and network_isolation:
            row.network_isolation = json.dumps(network_isolation, ensure_ascii=False)[:2000]
        row.error = ""
        row.lease_owner = None
        row.lease_until = None
        row.updated_at = _utcnow()
        await db.commit()
        return _ok(_row_to_job(row), idempotent=False, conflict=False)
    except Exception as exc:
        logger.warning("[render_plane] complete_job failed: %s", exc)
        return _fail(f"complete_failed:{type(exc).__name__}")


async def fail_job(
    db,
    *,
    job_id: str,
    worker: str = "",
    error: str = "",
    retryable: bool = False,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> dict[str, Any]:
    """Fail a job, or requeue it with exponential backoff when ``retryable``."""
    try:
        row = await db.get(RenderJobRow, str(job_id or ""))
        if row is None:
            return _fail("job_not_found")
        if worker and str(row.lease_owner or "") not in ("", str(worker)):
            return _fail("lease_not_owned", stale_attempt=True)

        now = _utcnow()
        next_retry = int(row.retry_count or 0) + 1
        if retryable and next_retry <= int(max_retries or 0):
            backoff = sample_retry_backoff_seconds(next_retry)
            row.state = STATE_QUEUED
            row.retry_count = next_retry
            row.next_eligible_at = now + _seconds(backoff)
        else:
            row.state = STATE_FAILED
            row.retry_count = next_retry
            row.next_eligible_at = None
        row.error = str(error or "")[:500]
        row.lease_owner = None
        row.lease_until = None
        row.updated_at = now
        await db.commit()
        return _ok(_row_to_job(row), requeued=row.state == STATE_QUEUED)
    except Exception as exc:
        logger.warning("[render_plane] fail_job failed: %s", exc)
        return _fail(f"fail_failed:{type(exc).__name__}")


def _seconds(n: int):
    from datetime import timedelta

    return timedelta(seconds=int(n))


async def reclaim_render_leases(
    db,
    *,
    now: datetime | None = None,
    max_retries: int = DEFAULT_MAX_RETRIES,
    limit: int = DEFAULT_RECONCILE_LIMIT,
) -> dict[str, Any]:
    """Reclaim in-flight jobs whose lease expired. Idempotent + bounded.

    The decision is the SAME pure ``plan_lease_reclaim`` the control plane uses —
    requeue with ``60s·2^n`` backoff (15m cap, jitter) or fail past the retry cap,
    so a poison job cannot hot-loop.
    """
    try:
        now = now or _utcnow()
        bounded = max(1, int(limit or DEFAULT_RECONCILE_LIMIT))
        stmt = (
            select(RenderJobRow)
            .where(
                RenderJobRow.state.in_(_IN_FLIGHT),
                RenderJobRow.lease_until.is_not(None),
                RenderJobRow.lease_until < now,
            )
            .order_by(RenderJobRow.lease_until.asc())
            .limit(bounded)
        )
        rows = (await db.scalars(stmt)).all()
        requeued = failed = 0
        for row in rows:
            plan = plan_lease_reclaim(
                state=row.state,
                retry_count=row.retry_count,
                max_retries=max_retries,
                now=now,
            )
            row.state = plan["state"]
            row.retry_count = plan["retry_count"]
            row.lease_owner = plan["lease_owner"]
            row.lease_until = plan["lease_until"]
            row.next_eligible_at = plan["next_eligible_at"]
            row.error = str(plan["blocked_reason"] or "")[:500]
            row.updated_at = now
            if plan["outcome"] == "failed":
                failed += 1
            else:
                requeued += 1
        await db.commit()
        return {
            "ok": True,
            "scanned": len(rows),
            "requeued": requeued,
            "failed": failed,
            "at": now.isoformat(),
            "limit": bounded,
            "capped": len(rows) >= bounded,
        }
    except Exception as exc:
        logger.warning("[render_plane] reclaim_render_leases failed: %s", exc)
        return _fail(f"reclaim_failed:{type(exc).__name__}")


# -------------------------------------------------------------------- reads
async def get_job(db, job_id: str, *, tenant_id: str | None = None) -> dict[str, Any]:
    """Fetch one job. A cross-tenant id is ``tenant_mismatch``, never a leak."""
    try:
        row = await db.get(RenderJobRow, str(job_id or ""))
        if row is None:
            return _fail("job_not_found")
        if tenant_id is not None and str(row.tenant_id) != str(tenant_id):
            return _fail("tenant_mismatch")
        return _ok(_row_to_job(row))
    except Exception as exc:
        logger.warning("[render_plane] get_job failed: %s", exc)
        return _fail(f"get_failed:{type(exc).__name__}")


async def list_jobs(
    db,
    *,
    state: str = "",
    tenant_id: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """List jobs (newest last), optionally filtered by state / tenant. Never raises."""
    try:
        bounded = max(1, min(500, int(limit or 50)))
        stmt = select(RenderJobRow).order_by(RenderJobRow.created_at.asc()).limit(bounded)
        if state:
            stmt = stmt.where(RenderJobRow.state == str(state))
        if tenant_id is not None:
            stmt = stmt.where(RenderJobRow.tenant_id == str(tenant_id))
        rows = (await db.scalars(stmt)).all()
        return {"ok": True, "items": [_row_to_job(r).to_dict() for r in rows], "count": len(rows)}
    except Exception as exc:
        logger.warning("[render_plane] list_jobs failed: %s", exc)
        return _fail(f"list_failed:{type(exc).__name__}")


def _done_item(row: RenderJobRow) -> dict[str, Any]:
    """Compact view of one completed job for health/ops readers."""
    return {
        "job_id": str(row.id),
        "tenant_id": str(row.tenant_id),
        "creative_id": str(row.creative_id or ""),
        "revision": int(row.revision or 0),
        "state": STATE_DONE,
        # ``updated_at`` is stamped at the done transition (complete_job), so it
        # IS the finished-at time — there is no separate finished_at column.
        "finished_at": _dt_to_epoch(row.updated_at),
        "artifact_path": str(row.artifact_path or ""),
        "artifact_sha256": str(row.artifact_sha256 or ""),
        "artifact_bytes": int(row.artifact_bytes or 0),
        "manifest_hash": str(row.manifest_hash or ""),
    }


def _recent_done_sync(db, *, limit: int = 50, tenant_id: str | None = None) -> dict[str, Any]:
    """Core of :func:`recent_done` against a *synchronous* Session (testable)."""
    try:
        bounded = max(1, min(500, int(limit or 50)))
    except (TypeError, ValueError):
        bounded = 50
    stmt = select(RenderJobRow).where(RenderJobRow.state == STATE_DONE)
    if tenant_id is not None:
        stmt = stmt.where(RenderJobRow.tenant_id == str(tenant_id))
    stmt = stmt.order_by(RenderJobRow.updated_at.desc()).limit(bounded)
    rows = db.execute(stmt).scalars().all()
    items = [_done_item(r) for r in rows]
    return {"ok": True, "items": items, "count": len(items), "done": len(items)}


def recent_done(limit: int = 50, *, tenant_id: str | None = None) -> dict[str, Any]:
    """**Synchronous** reader: recently COMPLETED jobs, newest first. Never raises.

    WHY THIS EXISTS (and why it is sync, not async)
    ----------------------------------------------
    ``app/marketing/video_health.py::probe_local_render`` runs in the web process
    outside any event loop, so it cannot ``await`` the async :func:`list_jobs`.
    Before this reader the probe degraded into ``plane_error`` and could therefore
    NEVER report ``produced`` — it could only ever say "the plane exists", never
    "the plane finished something" (the exact ran-vs-produced fake-green this
    project has been burned by). This is the missing sync seam.

    * Additive only — :func:`list_jobs` and every other async API are unchanged.
    * Returns ``{"ok": True, "items": [...], "count": N, "done": N}`` on success.
    * Returns ``{"ok": False, "error": <code>}`` when the store is genuinely
      unreadable, so the caller reports an honest ``plane_error`` — never a
      fabricated ``0``-as-success.
    * Every read is tenant-scopable via ``tenant_id``; a scoped call returns only
      that tenant's rows (no cross-tenant leak).
    """
    try:
        from app.models.base import get_db_session

        with get_db_session() as db:
            return _recent_done_sync(db, limit=limit, tenant_id=tenant_id)
    except Exception as exc:
        logger.warning("[render_plane] recent_done failed: %s", exc)
        return _fail(f"recent_done_failed:{type(exc).__name__}")


async def status_snapshot(db, *, tenant_id: str | None = None) -> dict[str, Any]:
    """Read-only rollup by state (optionally tenant-scoped). Never raises."""
    try:
        stmt = select(RenderJobRow.state, func.count()).group_by(RenderJobRow.state)
        if tenant_id is not None:
            stmt = stmt.where(RenderJobRow.tenant_id == str(tenant_id))
        by_state: dict[str, int] = {}
        for state, count in (await db.execute(stmt)).all():
            by_state[str(state)] = int(count)
        return {
            "ok": True,
            "by_state": by_state,
            "total": sum(by_state.values()),
            "in_flight": sum(by_state.get(s, 0) for s in _IN_FLIGHT),
            "queued": by_state.get(STATE_QUEUED, 0),
            "done": by_state.get(STATE_DONE, 0),
            "failed": by_state.get(STATE_FAILED, 0),
        }
    except Exception as exc:
        logger.warning("[render_plane] status_snapshot failed: %s", exc)
        return _fail(f"status_failed:{type(exc).__name__}")


__all__ = [
    "LEASE_SECONDS_ENV",
    "RENDER_JOB_STATES",
    "RenderJob",
    "RenderJobRow",
    "STATE_DONE",
    "STATE_EXPIRED",
    "STATE_FAILED",
    "STATE_LEASED",
    "STATE_QUEUED",
    "STATE_RENDERING",
    "STATE_UPLOADING",
    "claim_next_job",
    "complete_job",
    "create_job",
    "ensure_table",
    "fail_job",
    "get_job",
    "heartbeat_job",
    "job_id_for",
    "lease_seconds",
    "list_jobs",
    "mark_rendering",
    "mark_uploading",
    "recent_done",
    "reclaim_render_leases",
    "render_job_spec",
    "status_snapshot",
    "verify_lease_token",
]
