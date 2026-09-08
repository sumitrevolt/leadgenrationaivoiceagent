"""Owner OS V1.1 — per-agent execution controls (Isha vertical slice first).

Durable controls with explicit scopes. Does NOT force-kill customer-critical work.
Enforcement points:
  - manual_pause → staff.run_member / Owner OS pause (also syncs agent_controls)
  - scheduled_pause / drain → scheduler_dispatch_allowed(job→agent) + apply_async
  - stop_claims / drain → run_staff_job + team_scheduler._run_job claim gate
  - cancel queued → Celery revoke(terminate=False) only when not started
  - request cancel running → cooperative Redis flag; unsupported if job ignores it

Fail-closed on ambiguous control state for NEW dispatch/claims.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.platform import owner_os_store as store
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

CONTROL_STORE = os.path.join("data", "owner_agent_controls.jsonl")
CANCEL_KEY_PREFIX = "owner_os:cancel_request:"
AGENT_ABORT_PREFIX = "owner_os:agent_abort:"
RUNNING_KEY_PREFIX = "owner_os:agent_running:"

# Jobs owned by Isha (scheduler_config.JOB_META owner=isha) — slice focus.
AGENT_JOBS: dict[str, frozenset[str]] = {
    # Must stay in sync with scheduler_config.JOB_META owners — a job owned by
    # Isha there but missing here would keep running after the owner pauses her,
    # i.e. a silent hole in the Owner OS control plane (guarded by
    # tests/test_owner_agent_execution.py::test_isha_job_registry_drift_guard).
    "isha": frozenset(
        {
            "content",
            "blog",
            "afternoon_content",
            "weekly_marketing",
            "social_drain",
            "daily_video",
        }
    ),
}

CONTROL_FIELDS = (
    "manual_pause",
    "scheduled_pause",
    "stop_claims",
    "drain",
)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canon_agent(agent_id: str) -> str:
    from app.platform.agent_controls import _canon

    return _canon(agent_id)


def jobs_for_agent(agent_id: str) -> frozenset[str]:
    aid = _canon_agent(agent_id)
    if aid in AGENT_JOBS:
        return AGENT_JOBS[aid]
    # Derive from scheduler registry for other agents (read-only fallback).
    try:
        from app.platform.scheduler_config import JOB_META

        return frozenset(j for j, meta in JOB_META.items() if str(meta.get("owner") or "") == aid)
    except Exception:
        return frozenset()


def agent_for_job(job: str) -> str | None:
    job_s = str(job or "").strip()
    if not job_s:
        return None
    for agent, jobs in AGENT_JOBS.items():
        if job_s in jobs:
            return agent
    try:
        from app.platform.scheduler_config import JOB_META

        owner = str((JOB_META.get(job_s) or {}).get("owner") or "").strip()
        return owner or None
    except Exception:
        return None


def _default_control(agent_id: str) -> dict[str, Any]:
    return {
        "agent_id": agent_id,
        "manual_pause": False,
        "scheduled_pause": False,
        "stop_claims": False,
        "drain": False,
        "drain_state": "idle",
        "reason": "",
        "by": "",
        "changed_by": "",
        "at": None,
        "changed_at": None,
        "expiry": None,
        "version": 1,
        "meta": {},
    }


def _expired(rec: dict[str, Any]) -> bool:
    exp = rec.get("expiry")
    if not exp:
        return False
    try:
        if isinstance(exp, datetime):
            dt = exp.replace(tzinfo=None) if exp.tzinfo else exp
        else:
            dt = datetime.fromisoformat(str(exp).replace("Z", "+00:00")).replace(tzinfo=None)
        return dt <= _now()
    except Exception:
        return False  # ambiguous expiry → treat as not expired for safety of existing pause


def _effective(rec: dict[str, Any]) -> dict[str, Any]:
    out = dict(rec)
    if _expired(rec):
        for f in CONTROL_FIELDS:
            out[f] = False
        out["drain_state"] = "idle"
        out["expired"] = True
    else:
        out["expired"] = False
    # Drain implies stop_claims + scheduled_pause for NEW work.
    if out.get("drain"):
        out["stop_claims"] = True
        out["scheduled_pause"] = True
        if out.get("drain_state") not in ("draining", "drained"):
            out["drain_state"] = "draining"
    return out


def get_control(agent_id: str) -> dict[str, Any]:
    aid = _canon_agent(agent_id)
    if not aid:
        return _default_control("")
    rec = _load(aid) or _default_control(aid)
    # Mirror legacy manual pause sidecar (V1) into effective view.
    try:
        from app.platform import agent_controls

        if agent_controls.is_paused(aid):
            rec = {**rec, "manual_pause": True}
    except Exception:
        pass
    return _effective(rec)


def _load(agent_id: str) -> dict[str, Any] | None:
    if store.storage_mode() == "db":
        try:
            from app.models.base import get_db_session
            from app.models.owner_os import OwnerAgentControl

            with get_db_session() as db:
                row = (
                    db.query(OwnerAgentControl)
                    .filter(OwnerAgentControl.agent_id == agent_id)
                    .first()
                )
                if not row:
                    return None
                meta = {}
                if row.meta_json:
                    try:
                        meta = json.loads(row.meta_json)
                    except Exception:
                        meta = {}
                return {
                    "agent_id": row.agent_id,
                    "manual_pause": bool(row.manual_pause),
                    "scheduled_pause": bool(row.scheduled_pause),
                    "stop_claims": bool(row.stop_claims),
                    "drain": bool(row.drain),
                    "drain_state": row.drain_state or "idle",
                    "reason": row.reason or "",
                    "by": row.changed_by or "",
                    "changed_by": row.changed_by or "",
                    "at": row.changed_at.isoformat() if row.changed_at else None,
                    "changed_at": row.changed_at.isoformat() if row.changed_at else None,
                    "expiry": row.expiry.isoformat() if row.expiry else None,
                    "version": int(row.version or 1),
                    "meta": meta,
                }
        except Exception as e:
            logger.debug("[owner_agent_execution] load db: %s", e)
    latest: dict[str, dict[str, Any]] = {}
    for r in store._read_jsonl(CONTROL_STORE):
        k = str(r.get("agent_id") or "")
        if k:
            latest[k] = r
    return latest.get(agent_id)


def _save(rec: dict[str, Any]) -> dict[str, Any]:
    aid = rec["agent_id"]
    if store.storage_mode() == "db":
        try:
            from app.models.base import get_db_session
            from app.models.owner_os import OwnerAgentControl

            with get_db_session() as db:
                row = db.query(OwnerAgentControl).filter(OwnerAgentControl.agent_id == aid).first()
                exp = None
                if rec.get("expiry"):
                    try:
                        exp = datetime.fromisoformat(
                            str(rec["expiry"]).replace("Z", "+00:00")
                        ).replace(tzinfo=None)
                    except Exception:
                        exp = None
                if row:
                    row.manual_pause = bool(rec.get("manual_pause"))
                    row.scheduled_pause = bool(rec.get("scheduled_pause"))
                    row.stop_claims = bool(rec.get("stop_claims"))
                    row.drain = bool(rec.get("drain"))
                    row.drain_state = str(rec.get("drain_state") or "idle")[:20]
                    row.reason = (rec.get("reason") or "")[:200]
                    row.changed_by = (rec.get("by") or rec.get("changed_by") or "")[:120]
                    row.changed_at = _now()
                    row.expiry = exp
                    row.version = int(row.version or 1) + 1
                    row.meta_json = json.dumps(rec.get("meta") or {}, ensure_ascii=False)[:4000]
                    rec["version"] = row.version
                else:
                    db.add(
                        OwnerAgentControl(
                            agent_id=aid,
                            manual_pause=bool(rec.get("manual_pause")),
                            scheduled_pause=bool(rec.get("scheduled_pause")),
                            stop_claims=bool(rec.get("stop_claims")),
                            drain=bool(rec.get("drain")),
                            drain_state=str(rec.get("drain_state") or "idle")[:20],
                            reason=(rec.get("reason") or "")[:200],
                            changed_by=(rec.get("by") or "")[:120],
                            changed_at=_now(),
                            expiry=exp,
                            version=1,
                            meta_json=json.dumps(rec.get("meta") or {}, ensure_ascii=False)[:4000],
                        )
                    )
                    rec["version"] = 1
            return get_control(aid)
        except Exception as e:
            logger.warning("[owner_agent_execution] save db fail → jsonl: %s", type(e).__name__)
    store._append_jsonl(CONTROL_STORE, {**rec, "at": _now_iso(), "changed_at": _now_iso()})
    return get_control(aid)


def _audit(actor: str, action: str, agent_id: str, meta: dict[str, Any]) -> None:
    try:
        from app.platform import owner_os

        owner_os.audit(actor, action, {"target": agent_id, "agent_id": agent_id, **meta})
    except Exception:
        pass


def set_control(
    agent_id: str,
    *,
    by: str = "admin",
    reason: str = "",
    ttl_hours: int | None = None,
    idempotency_key: str | None = None,
    **flags: Any,
) -> dict[str, Any]:
    """Set one or more control flags. Unknown flags rejected. Idempotent on key+flags."""
    aid = _canon_agent(agent_id)
    if not aid:
        return {"ok": False, "error": "agent_id required"}
    if aid != "isha" and not jobs_for_agent(aid):
        # Slice allows any agent with known jobs; unknown/non-runnable still ok for manual.
        pass
    unknown = [k for k in flags if k not in CONTROL_FIELDS]
    if unknown:
        return {"ok": False, "error": f"unknown_controls:{','.join(unknown)}"}

    cur = _load(aid) or _default_control(aid)
    if idempotency_key:
        prev_key = (cur.get("meta") or {}).get("idempotency_key")
        if prev_key and prev_key == idempotency_key:
            eff = get_control(aid)
            return {"ok": True, "deduped": True, "control": control_view(aid, eff)}

    nxt = dict(cur)
    for k, v in flags.items():
        nxt[k] = bool(v)
    if nxt.get("drain"):
        nxt["stop_claims"] = True
        nxt["scheduled_pause"] = True
        nxt["drain_state"] = "draining"
    elif flags.get("drain") is False:
        nxt["drain_state"] = "idle"
    # Cooperative mid-run abort: engage on drain/stop_claims; clear when both off.
    if nxt.get("drain") or nxt.get("stop_claims"):
        set_agent_abort(aid, engaged=True, by=by)
    elif (
        ("drain" in flags or "stop_claims" in flags)
        and not nxt.get("drain")
        and not nxt.get("stop_claims")
    ):
        set_agent_abort(aid, engaged=False, by=by)
    nxt["reason"] = (reason or nxt.get("reason") or "")[:200]
    nxt["by"] = (by or "admin")[:80]
    nxt["changed_by"] = nxt["by"]
    nxt["at"] = _now_iso()
    nxt["changed_at"] = nxt["at"]
    if ttl_hours is not None:
        try:
            hrs = max(1, min(int(ttl_hours), 168))
            nxt["expiry"] = (_now() + timedelta(hours=hrs)).isoformat()
        except Exception:
            return {"ok": False, "error": "invalid_ttl"}
    meta = dict(nxt.get("meta") or {})
    if idempotency_key:
        meta["idempotency_key"] = str(idempotency_key)[:80]
    nxt["meta"] = meta
    nxt["agent_id"] = aid

    # Keep V1 manual pause sidecar in sync (do not weaken it).
    if "manual_pause" in flags:
        try:
            from app.platform import agent_controls

            if flags["manual_pause"]:
                agent_controls.pause(aid, by=by, note=reason or "owner_os execution control")
            else:
                agent_controls.resume(aid, by=by)
        except Exception as e:
            logger.debug("[owner_agent_execution] agent_controls sync: %s", e)

    saved = _save(nxt)
    _audit(
        by,
        "agent_execution_control_set",
        aid,
        {
            "flags": {k: bool(flags[k]) for k in flags},
            "reason": (reason or "")[:200],
            "drain_state": saved.get("drain_state"),
        },
    )
    return {"ok": True, "control": control_view(aid, saved)}


def restore_defaults(agent_id: str, *, by: str = "admin", reason: str = "") -> dict[str, Any]:
    out = set_control(
        agent_id,
        by=by,
        reason=reason or "restore_default_controls",
        manual_pause=False,
        scheduled_pause=False,
        stop_claims=False,
        drain=False,
    )
    set_agent_abort(agent_id, engaged=False, by=by)
    return out


def resume(agent_id: str, *, by: str = "admin", reason: str = "") -> dict[str, Any]:
    """Resume = clear pause/claims/drain (same as restore for slice)."""
    return restore_defaults(agent_id, by=by, reason=reason or "resume")


def control_view(agent_id: str, rec: dict[str, Any] | None = None) -> dict[str, Any]:
    aid = _canon_agent(agent_id)
    r = _effective(rec or get_control(aid))
    jobs = sorted(jobs_for_agent(aid))
    return {
        "agent_id": aid,
        "effective_scope": {
            "manual_pause": bool(r.get("manual_pause")),
            "scheduled_pause": bool(r.get("scheduled_pause")),
            "stop_claims": bool(r.get("stop_claims")),
            "drain": bool(r.get("drain")),
            "drain_state": r.get("drain_state") or "idle",
        },
        "actor": r.get("by") or r.get("changed_by") or "",
        "reason": r.get("reason") or "",
        "timestamp": r.get("at") or r.get("changed_at"),
        "expiry": r.get("expiry"),
        "queued_task_behavior": (
            "already-queued Celery messages may still be consumed unless stop_claims/drain "
            "blocks worker claim/start"
        ),
        "running_task_behavior": (
            "in-flight tasks are not force-killed; drain waits for zero active work"
        ),
        "scheduled_behavior": (
            "new scheduled enqueue blocked when scheduled_pause or drain or global kill"
        ),
        "rollback_action": "resume / restore_default_controls",
        "jobs": jobs,
        "version": int(r.get("version") or 1),
        "expired": bool(r.get("expired")),
    }


def scheduled_dispatch_blocked(
    agent_id: str | None = None, job: str | None = None
) -> tuple[bool, str]:
    """True if NEW scheduled enqueue must be skipped for this agent/job.

    Fail-closed on ambiguous control-store errors for known agent-scoped jobs.
    """
    try:
        aid = _canon_agent(agent_id or "") if agent_id else agent_for_job(str(job or ""))
        if not aid:
            return False, ""
        c = get_control(aid)
        if c.get("drain"):
            return True, "agent_drain"
        if c.get("scheduled_pause"):
            return True, "agent_scheduled_pause"
        return False, ""
    except Exception:
        # Ambiguous state → block NEW dispatch for known Isha/agent jobs only.
        job_s = str(job or "")
        if agent_id or agent_for_job(job_s):
            return True, "agent_control_state_ambiguous"
        return False, ""


def claim_allowed(agent_id: str | None = None, job: str | None = None) -> tuple[bool, str]:
    """False = worker must not start/claim new work for this scope.

    NOTE: manual_pause intentionally does NOT block here — staff.run_member /
    agent_controls.is_paused owns that path. Drain / stop_claims do block.
    agent_runtime uses ``runtime_admission_blocked`` which ALSO honors pause.

    Fail-closed on ambiguous control-store errors for known agent-scoped jobs.
    """
    try:
        aid = _canon_agent(agent_id or "") if agent_id else agent_for_job(str(job or ""))
        if not aid:
            return True, ""
        c = get_control(aid)
        if c.get("drain") or c.get("stop_claims"):
            return (
                False,
                (
                    "agent_stop_claims"
                    if c.get("stop_claims") and not c.get("drain")
                    else "agent_drain"
                ),
            )
        return True, ""
    except Exception:
        job_s = str(job or "")
        if agent_id or agent_for_job(job_s):
            return False, "agent_control_state_ambiguous"
        return True, ""


def runtime_admission_blocked(
    agent_id: str | None = None, job: str | None = None
) -> tuple[bool, str]:
    """Shared agent_runtime admission gate (pause + drain + stop-claims).

    Returns (blocked, reason_code). Canonical reason codes:
      agent_draining | agent_claims_stopped | agent_paused | agent_control_state_ambiguous

    Precedence among Owner OS execution controls (kill/flags checked elsewhere):
      drain before bare stop_claims (drain implies stop_claims — report agent_draining),
      then stop_claims, then manual_pause (+ V1 agent_controls sidecar).

    Fail-CLOSED on ambiguous control-store errors for known agent ids.
    """
    try:
        aid = _canon_agent(agent_id or "") if agent_id else agent_for_job(str(job or ""))
        if not aid:
            return False, ""
        c = get_control(aid)
        # Drain implies stop_claims; prefer agent_draining when drain is engaged.
        if c.get("drain"):
            return True, "agent_draining"
        if c.get("stop_claims"):
            return True, "agent_claims_stopped"
        if c.get("manual_pause"):
            return True, "agent_paused"
        try:
            from app.platform import agent_controls

            if agent_controls.is_paused(aid):
                return True, "agent_paused"
        except Exception:
            pass
        return False, ""
    except Exception:
        job_s = str(job or "")
        if agent_id or agent_for_job(job_s):
            return True, "agent_control_state_ambiguous"
        return False, ""


def refresh_drain_state(agent_id: str, *, queued: int = 0, running: int = 0) -> dict[str, Any]:
    """Mark drained only when active work is zero while drain engaged."""
    aid = _canon_agent(agent_id)
    cur = _load(aid) or _default_control(aid)
    if not cur.get("drain"):
        return get_control(aid)
    active = max(0, int(queued)) + max(0, int(running))
    if active == 0:
        cur["drain_state"] = "drained"
    else:
        cur["drain_state"] = "draining"
    cur["meta"] = {**(cur.get("meta") or {}), "queued": int(queued), "running": int(running)}
    cur["agent_id"] = aid
    return _save(cur)


def task_counts_for_agent(agent_id: str) -> dict[str, int]:
    """Best-effort queued/running counts for agent-owned staff jobs (never raises)."""
    aid = _canon_agent(agent_id)
    jobs = jobs_for_agent(aid)
    queued = 0
    running = 0
    try:
        from app.platform import celery_app as _ca

        app = getattr(_ca, "celery_app", None) or getattr(_ca, "app", None)
        if app is None:
            from app.worker import celery_app as app  # type: ignore
        insp = app.control.inspect(timeout=1.0)
        if insp:
            for bucket in (insp.active() or {}).values():
                for t in bucket or []:
                    args = t.get("args") or []
                    if args and str(args[0]) in jobs:
                        running += 1
            for bucket in (insp.reserved() or {}).values():
                for t in bucket or []:
                    args = t.get("args") or []
                    if args and str(args[0]) in jobs:
                        queued += 1
    except Exception as e:
        logger.debug("[owner_agent_execution] inspect skip: %s", e)
    return {"queued": queued, "running": running, "failed": 0}


def cancel_queued_task(
    agent_id: str,
    task_id: str,
    *,
    by: str = "admin",
    reason: str = "",
) -> dict[str, Any]:
    """Revoke only if task has not started. Honest refuse otherwise."""
    aid = _canon_agent(agent_id)
    tid = str(task_id or "").strip()
    if not tid:
        return {"ok": False, "error": "task_id required"}
    try:
        from app.worker import celery_app

        async_result = celery_app.AsyncResult(tid)
        state = str(async_result.state or "")
        if state in ("STARTED", "SUCCESS", "FAILURE", "RETRY"):
            return {
                "ok": False,
                "error": "task_already_started_or_finished",
                "state": state,
                "note": "Use request_cancel_running for cooperative cancellation of running work.",
            }
        # Verify job belongs to agent when args available.
        info = async_result.info if isinstance(async_result.info, dict) else {}
        job = None
        try:
            # Celery may not expose args on pending; optional check via inspect reserved.
            from app.platform import celery_app as _ca

            app = getattr(_ca, "celery_app", None)
            if app is None:
                app = celery_app
            insp = app.control.inspect(timeout=1.0)
            for bucket in (insp.reserved() or {}).values():
                for t in bucket or []:
                    if t.get("id") == tid:
                        args = t.get("args") or []
                        job = str(args[0]) if args else None
            for bucket in (insp.scheduled() or {}).values():
                for t in bucket or []:
                    req = t.get("request") or t
                    if req.get("id") == tid:
                        args = req.get("args") or []
                        job = str(args[0]) if args else None
        except Exception:
            pass
        if job:
            owner = agent_for_job(job)
            if owner and owner != aid:
                return {"ok": False, "error": "task_not_in_agent_scope", "job": job}
        celery_app.control.revoke(tid, terminate=False)
        _audit(
            by,
            "agent_cancel_queued_task",
            aid,
            {"task_id": tid, "job": job, "reason": (reason or "")[:200], "state": state},
        )
        return {
            "ok": True,
            "cancelled": True,
            "task_id": tid,
            "state_before": state,
            "job": job,
            "force_kill": False,
        }
    except Exception as e:
        return {"ok": False, "error": f"revoke_failed:{type(e).__name__}"}


def request_cancel_running(
    agent_id: str,
    task_id: str,
    *,
    by: str = "admin",
    reason: str = "",
    command_id: str = "",
) -> dict[str, Any]:
    """Cooperative cancel request. Does not claim stopped until worker acks.

    Agent-runtime runs (``art_*`` task ids) use the Redis cancellation store
    (``agentrt:cancel:<agent>:<run>``). Legacy staff jobs keep the older
    ``owner_os:cancel_request:`` key + abort flag path.
    """
    aid = _canon_agent(agent_id)
    tid = str(task_id or "").strip()
    if not tid:
        return {"ok": False, "error": "task_id required", "reason_code": "malformed_target"}

    # Agent Runtime distributed cancel (run-specific, cross-process).
    if tid.startswith("art_"):
        from app.platform import agent_runtime as art

        cmd = str(command_id or "").strip() or f"ocmd_cancel_{uuid.uuid4().hex[:10]}"
        out = art.request_cancel_run(
            aid,
            tid,
            requested_by=by,
            reason=reason,
            command_id=cmd,
            correlation_id=tid,
        )
        if not out.get("ok"):
            return {
                "ok": False,
                "error": out.get("error") or out.get("reason_code") or "cancel_failed",
                "reason_code": out.get("reason_code") or out.get("error"),
                "command_id": cmd,
                "agent_id": aid,
                "targeted_run_ids": [],
                "cancellation_backend": out.get("cancellation_backend"),
                "stopped": False,
            }
        status = "cancel_requested"
        if out.get("already_requested"):
            status = "already_requested"
        return {
            "ok": True,
            "command_id": cmd,
            "status": status,
            "agent_id": aid,
            "targeted_run_ids": [tid],
            "cancellation_backend": out.get("cancellation_backend") or "redis",
            "requested_count": 0 if out.get("already_requested") else 1,
            "already_requested_count": 1 if out.get("already_requested") else 0,
            "requested": True,
            "acknowledged": False,
            "stopped": False,
            "task_id": tid,
            "newly_created": out.get("newly_created"),
            "note": (
                "Distributed Redis cancellation requested for runtime run. "
                "Worker checkpoints observe the record across processes."
            ),
        }

    try:
        r = _redis()
        key = f"{CANCEL_KEY_PREFIX}{tid}"
        payload = json.dumps(
            {
                "agent_id": aid,
                "by": by[:80],
                "reason": (reason or "")[:200],
                "at": _now_iso(),
            },
            ensure_ascii=False,
        )
        r.setex(key, 3600, payload)
        set_agent_abort(aid, engaged=True, by=by)
        _audit(
            by,
            "agent_request_cancel_running",
            aid,
            {"task_id": tid, "reason": (reason or "")[:200], "cooperative": True},
        )
        return {
            "ok": True,
            "requested": True,
            "acknowledged": False,
            "stopped": False,
            "task_id": tid,
            "command_id": str(command_id or "")[:64],
            "status": "cancel_requested",
            "agent_id": aid,
            "targeted_run_ids": [tid],
            "cancellation_backend": "redis_legacy_staff",
            "requested_count": 1,
            "already_requested_count": 0,
            "note": (
                "Cooperative cancellation requested. Task is not marked stopped until "
                "the worker acknowledges. Isha content loop polls agent_abort between clients."
            ),
            "unsupported_if_ignored": True,
        }
    except Exception as e:
        return {
            "ok": False,
            "error": f"cancel_request_unsupported:{type(e).__name__}",
            "stopped": False,
            "note": "Could not record cooperative cancel flag.",
        }


def _redis():
    import redis

    from app.config import settings

    url = (
        getattr(settings, "redis_url", None) or os.getenv("REDIS_URL") or "redis://localhost:6379/0"
    )
    return redis.Redis.from_url(url, socket_timeout=1)


def cancel_requested(task_id: str) -> bool:
    tid = str(task_id or "").strip()
    if not tid:
        return False
    try:
        return bool(_redis().get(f"{CANCEL_KEY_PREFIX}{tid}"))
    except Exception:
        return False


def set_agent_abort(agent_id: str, *, engaged: bool = True, by: str = "admin") -> bool:
    """Cooperative mid-run abort flag for an agent (Redis). Never raises."""
    aid = _canon_agent(agent_id)
    if not aid:
        return False
    try:
        r = _redis()
        key = f"{AGENT_ABORT_PREFIX}{aid}"
        if engaged:
            r.setex(
                key,
                3600,
                json.dumps({"by": by[:80], "at": _now_iso()}, ensure_ascii=False),
            )
        else:
            r.delete(key)
        return True
    except Exception:
        return False


def agent_abort_requested(agent_id: str) -> bool:
    """True if cooperative abort flag is set for this agent."""
    aid = _canon_agent(agent_id)
    if not aid:
        return False
    try:
        return bool(_redis().get(f"{AGENT_ABORT_PREFIX}{aid}"))
    except Exception:
        return False


def register_running_task(agent_id: str, job: str, task_id: str) -> None:
    """Best-effort running-task register for cancel/drain visibility."""
    aid = _canon_agent(agent_id)
    tid = str(task_id or "").strip()
    if not aid or not tid:
        return
    try:
        r = _redis()
        key = f"{RUNNING_KEY_PREFIX}{aid}"
        payload = json.dumps(
            {"task_id": tid, "job": str(job or "")[:64], "at": _now_iso()},
            ensure_ascii=False,
        )
        r.setex(key, 7200, payload)
    except Exception:
        pass


def clear_running_task(agent_id: str, task_id: str | None = None) -> None:
    aid = _canon_agent(agent_id)
    if not aid:
        return
    try:
        r = _redis()
        key = f"{RUNNING_KEY_PREFIX}{aid}"
        if task_id:
            cur = r.get(key)
            if cur:
                try:
                    data = json.loads(cur)
                    if str(data.get("task_id") or "") != str(task_id):
                        return
                except Exception:
                    pass
        r.delete(key)
    except Exception:
        pass


def get_running_task(agent_id: str) -> dict[str, Any] | None:
    aid = _canon_agent(agent_id)
    if not aid:
        return None
    try:
        raw = _redis().get(f"{RUNNING_KEY_PREFIX}{aid}")
        if not raw:
            return None
        data = json.loads(raw)
        return {
            "task_id": str(data.get("task_id") or ""),
            "job": str(data.get("job") or ""),
            "at": data.get("at"),
        }
    except Exception:
        return None


def isha_execution_snapshot() -> dict[str, Any]:
    """Single-agent vertical slice view for Owner OS."""
    aid = "isha"
    ctrl = control_view(aid)
    counts = task_counts_for_agent(aid)
    if ctrl["effective_scope"].get("drain"):
        refresh_drain_state(aid, queued=counts["queued"], running=counts["running"])
        ctrl = control_view(aid)
    route = {}
    try:
        from app.platform.agent_os_routing import get_agent_policy

        p = get_agent_policy("isha", "marketing")
        # Display-only snapshot; task→combo resolution lives in omniroute_client
        # _TASK_ROUTES (canonical 14-combo map, 2026-09-05).
        route = {
            "work_type": p.category,
            "primary_route": p.omniroute_task,
            "fallback_route": "leadsgen combo 13",
            "timeout_seconds": p.timeout_seconds,
            "latency_target_ms": 5000,
            "privacy_class": p.privacy_class,
            "cost_class": "low_cost_bulk",
            "omniroute_eligible": bool(p.omniroute_task),
        }
    except Exception:
        pass
    workflows = []
    try:
        from app.platform import scheduler_config

        jobs = scheduler_config.list_jobs().get("jobs") or []
        for j in jobs:
            if j.get("owner") == "isha" or j.get("job") in jobs_for_agent("isha"):
                workflows.append(
                    {
                        "workflow_id": j.get("job"),
                        "kind": "scheduled_job",
                        "label": j.get("label"),
                        "schedule": j.get("cadence"),
                        "enabled": j.get("enabled"),
                        "last_run": j.get("last_run"),
                        "status": j.get("status"),
                    }
                )
    except Exception:
        pass
    try:
        from app.agents import process_library

        proc = process_library.get_process("client_content") or {}
        if proc:
            workflows.append(
                {
                    "workflow_id": "client_content",
                    "kind": "process",
                    "label": proc.get("name"),
                    "steps": [s.get("id") for s in (proc.get("steps") or [])],
                    "external_side_effects": "none_until_human_review_breakpoint",
                }
            )
    except Exception:
        pass
    running_task = get_running_task(aid)
    return {
        "ok": True,
        "agent_id": "isha",
        "control": ctrl,
        "counts": counts,
        "running_task": running_task,
        "agent_abort_requested": agent_abort_requested(aid),
        "workflows": workflows,
        "omniroute": route,
        "calling_hard_off": True,
    }
