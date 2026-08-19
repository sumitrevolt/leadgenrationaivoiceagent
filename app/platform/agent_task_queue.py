"""
Agent Task Queue — Paperclip-inspired per-agent work queue with atomic checkout.
=================================================================================

Usage:
    from app.platform import agent_task_queue as atq

    # Assign task (human/manager → agent)
    task = await atq.assign("rohan", "Follow up 3 hot leads", client_id="abc")

    # Delegate (agent → agent)
    sub = await atq.delegate("manager", "neha", "Rescore pipeline leads", parent_task_id=task["id"])

    # Agent claims next task (atomic — no double-work)
    claimed = await atq.claim_next("rohan")

    # Agent completes task
    await atq.complete(task_id, result="3 emails sent", tokens_in=500, tokens_out=200)

    # Query
    pending = await atq.list_tasks("rohan", status="pending")
    queue = await atq.agent_queue_snapshot()  # all agents' queue depth
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _id() -> str:
    return str(uuid.uuid4())


# Deterministic-id namespace for idempotent dispatch (memory-stack L6 and any
# other producer that may retry). Fixed constant — changing it would make old
# dispatch keys map to new task ids and reopen the duplicate window.
_DISPATCH_NS = uuid.UUID("6f1c2f4e-6a1a-4d0f-9c9a-2f0b8a5c31d7")


def dispatch_task_id(dispatch_key: str) -> str:
    """Same logical intent -> same task id, forever. Used as the PK."""
    return str(uuid.uuid5(_DISPATCH_NS, str(dispatch_key or "")))


async def assign_idempotent(
    agent_id: str,
    goal: str,
    *,
    dispatch_key: str,
    **kwargs: Any,
) -> dict[str, Any]:
    """`assign()` that is safe to retry — at-most-ONE logical task per key.

    WHY (review P0): a producer that crashes after `assign()` but before it can
    record the result will retry, and a random uuid PK would happily create a
    SECOND task. Here the PK is derived from `dispatch_key`, so the retry either
    finds the existing row or loses the insert race — never duplicates.

    Returns the normal assign shape plus `duplicate: bool`. Never raises.
    """
    key = str(dispatch_key or "").strip()
    if not key:
        return {"ok": False, "error": "dispatch_key required"}
    task_id = dispatch_task_id(key)
    try:
        from app.models.agent_task import AgentTask
        from app.models.base import get_db_session

        with get_db_session() as db:
            existing = db.query(AgentTask).filter(AgentTask.id == task_id).first()
            if existing is not None:
                return {
                    "ok": True,
                    "id": task_id,
                    "agent_id": existing.agent_id,
                    "goal": existing.goal,
                    "duplicate": True,
                }
    except Exception as e:
        logger.warning(f"[atq] assign_idempotent lookup failed: {e}")
        return {"ok": False, "error": str(e)}

    out = await assign(agent_id, goal, task_id=task_id, **kwargs)
    if not out.get("ok"):
        # Lost the insert race (unique PK) => the other writer's task IS our task.
        try:
            from app.models.agent_task import AgentTask
            from app.models.base import get_db_session

            with get_db_session() as db:
                raced = db.query(AgentTask).filter(AgentTask.id == task_id).first()
                if raced is not None:
                    return {
                        "ok": True,
                        "id": task_id,
                        "agent_id": raced.agent_id,
                        "goal": raced.goal,
                        "duplicate": True,
                    }
        except Exception:
            pass
        return out
    out["duplicate"] = False
    return out


async def assign(
    agent_id: str,
    goal: str,
    *,
    client_id: str | None = None,
    campaign_id: str | None = None,
    goal_text: str = "",
    delegated_by: str = "human",
    parent_task_id: str | None = None,
    task_id: str | None = None,
) -> dict[str, Any]:
    """Create a new task for an agent. Returns the task dict.

    `task_id` optional — callers that need retry-safety pass a deterministic id
    (see `assign_idempotent`). Default stays a random uuid (unchanged behaviour).
    """
    try:
        from app.models.agent_task import AgentTask
        from app.models.base import get_db_session

        task_id = task_id or _id()
        # Org chart depth
        _depth = 0
        try:
            from app.platform import org_chart

            _depth = org_chart.request_depth(agent_id)
        except Exception:
            pass
        with get_db_session() as db:
            task = AgentTask(
                id=task_id,
                agent_id=agent_id.strip().lower(),
                status="pending",
                goal=goal[:500],
                client_id=client_id,
                campaign_id=campaign_id,
                goal_text=goal_text[:500],
                parent_task_id=parent_task_id,
                delegated_by=delegated_by,
                request_depth=_depth,
                created_at=_now(),
            )
            db.add(task)
            db.commit()

        _log_event(agent_id, "task_assigned", f"📋 {goal[:100]}")
        _bridge_on_assign(agent_id, goal, task_id, delegated_by=delegated_by, client_id=client_id)
        return {"ok": True, "id": task_id, "agent_id": agent_id, "goal": goal}
    except Exception as e:
        logger.warning(f"[atq] assign failed: {e}")
        return {"ok": False, "error": str(e)}


async def delegate(
    from_agent: str,
    to_agent: str,
    goal: str,
    *,
    parent_task_id: str | None = None,
    client_id: str | None = None,
    campaign_id: str | None = None,
    goal_text: str = "",
) -> dict[str, Any]:
    """Agent→Agent delegation. Creates a sub-task linked to parent."""
    result = await assign(
        to_agent,
        goal,
        client_id=client_id,
        campaign_id=campaign_id,
        goal_text=goal_text,
        delegated_by=from_agent,
        parent_task_id=parent_task_id,
    )
    if result.get("ok"):
        _log_event(from_agent, "task_delegated", f"→ {to_agent}: {goal[:80]}")
    return result


async def claim_next(agent_id: str) -> dict[str, Any] | None:
    """Atomically claim the oldest pending task for this agent.
    Returns task dict or None if queue empty.
    Uses optimistic locking (checkout_version) to prevent double-claim."""
    try:
        from app.models.agent_task import AgentTask
        from app.models.base import get_db_session

        key = agent_id.strip().lower()
        with get_db_session() as db:
            task = (
                db.query(AgentTask)
                .filter(AgentTask.agent_id == key, AgentTask.status == "pending")
                .order_by(AgentTask.created_at.asc())
                .first()
            )
            if not task:
                return None

            # Optimistic lock — if another worker claimed between read and update,
            # the version won't match and we retry (or return None).
            old_ver = task.checkout_version
            rows = (
                db.query(AgentTask)
                .filter(
                    AgentTask.id == task.id,
                    AgentTask.checkout_version == old_ver,
                    AgentTask.status == "pending",
                )
                .update(
                    {
                        "status": "claimed",
                        "claimed_at": _now(),
                        "checkout_version": old_ver + 1,
                    },
                    synchronize_session=False,
                )
            )
            db.commit()

            if rows == 0:
                return None  # someone else claimed it

            _log_event(key, "task_claimed", f"🔒 {task.goal[:80]}")
            _bridge_on_claimed(key, task.goal, task.id)
            return {
                "id": task.id,
                "agent_id": key,
                "goal": task.goal,
                "client_id": task.client_id,
                "campaign_id": task.campaign_id,
                "goal_text": task.goal_text,
                "parent_task_id": task.parent_task_id,
            }
    except Exception as e:
        logger.warning(f"[atq] claim_next failed: {e}")
        return None


async def start(task_id: str) -> dict[str, Any]:
    """Mark a claimed task as running."""
    return await _update_status(task_id, "claimed", "running")


async def begin(task_id: str) -> dict[str, Any]:
    """Mark a SELF-ASSIGNED task as running: ``pending -> running``.

    For producers where the assigner IS the executor there is no queue hand-off,
    so ``claim_next()`` never runs and the row never reaches ``claimed``. Those
    producers were calling ``start()`` (which requires ``claimed``), so it
    no-op'd, and the later ``complete()`` — which matches ``claimed|running`` —
    no-op'd too. Both discard their ``{"ok": False}``, so the row silently
    leaked as ``pending`` forever.

    Only ``fail()`` accepts ``pending``, which is why FAILING routines closed
    correctly while SUCCEEDING ones leaked. Production showed the asymmetry
    exactly: 12,631 orphaned ``pending`` vs 7 ``failed`` (2026-08-06).

    Deliberately a separate verb rather than widening ``complete()`` to accept
    ``pending``: that guard is what stops a genuine queue task from being
    completed by someone who never claimed it, and it must stay strict.
    """
    return await _update_status(task_id, "pending", "running")


async def complete(
    task_id: str,
    *,
    result: str = "",
    tokens_in: int = 0,
    tokens_out: int = 0,
    cost_usd: float = 0.0,
    provider: str = "",
) -> dict[str, Any]:
    """Mark a task as done with result + cost data.
    Paperclip billing-code pattern: child task cost rolls up to parent_task_id chain."""
    try:
        from app.models.agent_task import AgentTask
        from app.models.base import get_db_session

        with get_db_session() as db:
            rows = (
                db.query(AgentTask)
                .filter(
                    AgentTask.id == task_id,
                    AgentTask.status.in_(["claimed", "running"]),
                )
                .update(
                    {
                        "status": "done",
                        "result_summary": result[:1000] if result else "",
                        "completed_at": _now(),
                        "cost_tokens_in": tokens_in,
                        "cost_tokens_out": tokens_out,
                        "cost_usd": cost_usd,
                        "provider": provider,
                    },
                    synchronize_session=False,
                )
            )
            db.commit()
            if rows == 0:
                return {"ok": False, "error": "task not found or not claimable"}

            # --- Billing-code roll-up: propagate cost to parent chain ---
            if tokens_in or tokens_out or cost_usd:
                _rollup_cost_to_parent(db, task_id, tokens_in, tokens_out, cost_usd)

        _bridge_on_complete(task_id, result)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def fail(task_id: str, error: str = "") -> dict[str, Any]:
    """Mark a task as failed."""
    try:
        from app.models.agent_task import AgentTask
        from app.models.base import get_db_session

        with get_db_session() as db:
            db.query(AgentTask).filter(
                AgentTask.id == task_id,
                AgentTask.status.in_(["claimed", "running", "pending"]),
            ).update(
                {
                    "status": "failed",
                    "result_summary": error[:1000],
                    "completed_at": _now(),
                },
                synchronize_session=False,
            )
            db.commit()
        _bridge_on_fail(task_id, error)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def list_tasks(
    agent_id: str | None = None,
    *,
    status: str | None = None,
    client_id: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Query tasks with optional filters."""
    try:
        from app.models.agent_task import AgentTask
        from app.models.base import get_db_session

        with get_db_session() as db:
            q = db.query(AgentTask)
            if agent_id:
                q = q.filter(AgentTask.agent_id == agent_id.strip().lower())
            if status:
                q = q.filter(AgentTask.status == status)
            if client_id:
                q = q.filter(AgentTask.client_id == client_id)
            q = q.order_by(AgentTask.created_at.desc()).limit(limit)
            return [
                {
                    "id": t.id,
                    "agent_id": t.agent_id,
                    "status": t.status,
                    "goal": t.goal,
                    "client_id": t.client_id,
                    "goal_text": t.goal_text,
                    "delegated_by": t.delegated_by,
                    "parent_task_id": t.parent_task_id,
                    "cost_tokens_in": t.cost_tokens_in,
                    "cost_tokens_out": t.cost_tokens_out,
                    "cost_usd": t.cost_usd,
                    "provider": t.provider,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                    "completed_at": t.completed_at.isoformat() if t.completed_at else None,
                }
                for t in q.all()
            ]
    except Exception as e:
        logger.warning(f"[atq] list_tasks failed: {e}")
        return []


async def agent_queue_snapshot() -> dict[str, dict[str, int]]:
    """Per-agent queue depth: {agent_id: {pending: N, running: N, done_today: N}}."""
    try:
        from sqlalchemy import func

        from app.models.agent_task import AgentTask
        from app.models.base import get_db_session

        with get_db_session() as db:
            rows = (
                db.query(
                    AgentTask.agent_id,
                    AgentTask.status,
                    func.count(AgentTask.id),
                )
                .group_by(AgentTask.agent_id, AgentTask.status)
                .all()
            )
            snap: dict[str, dict[str, int]] = {}
            for agent_id, status, count in rows:
                if agent_id not in snap:
                    snap[agent_id] = {
                        "pending": 0,
                        "claimed": 0,
                        "running": 0,
                        "done": 0,
                        "failed": 0,
                        "cancelled": 0,
                    }
                snap[agent_id][status] = count
            return snap
    except Exception as e:
        logger.warning(f"[atq] snapshot failed: {e}")
        return {}


async def _update_status(task_id: str, from_status: str, to_status: str) -> dict[str, Any]:
    try:
        from app.models.agent_task import AgentTask
        from app.models.base import get_db_session

        with get_db_session() as db:
            rows = (
                db.query(AgentTask)
                .filter(AgentTask.id == task_id, AgentTask.status == from_status)
                .update({"status": to_status}, synchronize_session=False)
            )
            db.commit()
            return {"ok": rows > 0}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _rollup_cost_to_parent(
    db: Any, task_id: str, tokens_in: int, tokens_out: int, cost_usd: float
) -> None:
    """Paperclip billing-code pattern: walk parent_task_id chain and add child cost.
    Max 5 hops to prevent infinite loops. Best-effort, never raises."""
    try:
        from app.models.agent_task import AgentTask

        current_id = task_id
        for _ in range(5):  # max delegation depth
            task = db.query(AgentTask).filter(AgentTask.id == current_id).first()
            if not task or not task.parent_task_id:
                break
            parent = db.query(AgentTask).filter(AgentTask.id == task.parent_task_id).first()
            if not parent:
                break
            parent.cost_tokens_in = (parent.cost_tokens_in or 0) + int(tokens_in or 0)
            parent.cost_tokens_out = (parent.cost_tokens_out or 0) + int(tokens_out or 0)
            parent.cost_usd = round((parent.cost_usd or 0.0) + float(cost_usd or 0.0), 6)
            current_id = parent.id
        db.commit()
    except Exception as e:
        logger.debug(f"[atq] rollup skip: {e}")


async def task_cost_tree(task_id: str) -> dict[str, Any]:
    """Get cost tree for a task — own cost + all children's cost (Paperclip billing-code view)."""
    try:
        from app.models.agent_task import AgentTask
        from app.models.base import get_db_session

        with get_db_session() as db:
            task = db.query(AgentTask).filter(AgentTask.id == task_id).first()
            if not task:
                return {"error": "task not found"}
            # Find all children
            children = db.query(AgentTask).filter(AgentTask.parent_task_id == task_id).all()
            child_costs = [
                {
                    "id": c.id,
                    "agent_id": c.agent_id,
                    "goal": c.goal[:100],
                    "tokens_in": c.cost_tokens_in or 0,
                    "tokens_out": c.cost_tokens_out or 0,
                    "cost_usd": c.cost_usd or 0.0,
                    "status": c.status,
                }
                for c in children
            ]
            return {
                "task_id": task_id,
                "agent_id": task.agent_id,
                "goal": task.goal[:200],
                "own_tokens_in": task.cost_tokens_in or 0,
                "own_tokens_out": task.cost_tokens_out or 0,
                "own_cost_usd": task.cost_usd or 0.0,
                "children": child_costs,
                "total_tokens": (task.cost_tokens_in or 0) + (task.cost_tokens_out or 0),
            }
    except Exception as e:
        return {"error": str(e)}


async def stale_tasks(threshold_minutes: int = 10) -> list[dict[str, Any]]:
    """Paperclip philosophy: surface stuck tasks, don't auto-fix.
    Returns in_progress/claimed tasks older than threshold."""
    try:
        from datetime import timedelta

        from app.models.agent_task import AgentTask
        from app.models.base import get_db_session

        cutoff = _now() - timedelta(minutes=threshold_minutes)
        with get_db_session() as db:
            stuck = (
                db.query(AgentTask)
                .filter(
                    AgentTask.status.in_(["claimed", "running"]),
                    AgentTask.claimed_at < cutoff,
                )
                .order_by(AgentTask.claimed_at.asc())
                .limit(50)
                .all()
            )
            return [
                {
                    "id": t.id,
                    "agent_id": t.agent_id,
                    "status": t.status,
                    "goal": t.goal[:150],
                    "claimed_at": t.claimed_at.isoformat() if t.claimed_at else None,
                    "minutes_stuck": (
                        int((_now() - t.claimed_at).total_seconds() / 60) if t.claimed_at else 0
                    ),
                    "delegated_by": t.delegated_by,
                }
                for t in stuck
            ]
    except Exception as e:
        logger.warning(f"[atq] stale_tasks failed: {e}")
        return []


def lease_reap_enabled() -> bool:
    """`AGENT_TASK_LEASE_REAP` gate — unset/0 = INERT (surface-only, default)."""
    return os.environ.get("AGENT_TASK_LEASE_REAP", "").strip().lower() in ("1", "true", "yes", "on")


def routine_ledger_enabled() -> bool:
    """`ROUTINE_TASK_LEDGER` gate — **default ON** (current behaviour preserved).

    The scheduler routine bridge writes one `agent_tasks` row per job
    invocation, unconditionally: ~700/day, and nothing in the codebase ever
    prunes this table (no `AGENT_TASK_RETENTION` / TTL exists). `begin()` stops
    those rows leaking as `pending`, but they are still written — so the fix
    converts an unbounded leak into unbounded *correct* growth, ~255k rows/year.

    The authoritative record of every one of these jobs already lives in
    `automation_logs` (matched running/success pairs), so this ledger is a
    duplicate audit trail, not the source of truth. Set `ROUTINE_TASK_LEDGER=0`
    to stop writing it without touching the jobs themselves.

    Default ON deliberately: turning an existing audit trail off is an owner
    decision, not a side effect of deploying a bug fix.
    """
    return os.environ.get("ROUTINE_TASK_LEDGER", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def orphan_reap_enabled() -> bool:
    """`AGENT_TASK_ORPHAN_REAP` gate — unset/0 = INERT (default).

    Separate switch from `AGENT_TASK_LEASE_REAP` on purpose: that one closes
    EXPIRED LEASES (work a worker may have half-done), this one closes rows that
    were never claimable at all. Different risk profile, different owner
    decision — arming one must not silently arm the other.
    """
    return os.environ.get("AGENT_TASK_ORPHAN_REAP", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _write_orphan_backup(rows: list[dict[str, Any]]) -> str:
    """Resolve + write the pre-mutation backup in ONE place. Returns the path.

    Resolve and write are deliberately not split. CI's runtime-data debt ratchet
    classifies a write by the path expression at the `open()` site: when that
    expression comes straight from `resolve_store_path`, it is CANONICAL; when
    it comes from a helper's return value it reads as an undeclared mutable
    path and fails the gate. Keeping both in one function is also the honest
    shape — nothing else should be able to hand this function a path.

    The store is `automation.job_runs`: this file records what a scheduled job
    (`task_lease_reap`) closed, which is exactly that store's purpose. Writing
    beside it rather than inventing a new store keeps the manifest untouched.
    """
    import json as _json
    from pathlib import Path

    from app.platform import runtime_data_authority as _auth

    target = (
        _auth.resolve_store_path(
            store_id="automation.job_runs",
            legacy_path=Path("data") / "job_runs.jsonl",
            target_segments=("automation", "job_runs.jsonl"),
        ).parent
        / f"agent_task_orphans_{_now().strftime('%Y%m%d_%H%M%S')}.jsonl"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "a", encoding="utf-8") as fh:
        for m in rows:
            fh.write(_json.dumps(m, ensure_ascii=False) + "\n")
    return str(target)


async def reap_orphan_routines(
    older_than_hours: int = 24,
    limit: int = 500,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Terminally close rows that were created ``pending`` and never claimable.

    `reap_stale_leases()` cannot touch these. Its predicate is
    ``status IN ('claimed','running') AND claimed_at < cutoff`` — these rows are
    ``pending`` with ``claimed_at IS NULL``, so they fail BOTH clauses (and in
    SQL ``NULL < cutoff`` is NULL, not TRUE, so widening the status alone would
    still not match). The two predicates are disjoint, which is why the reaper
    ran hourly, reported ``scanned: 0``, recorded a green run, and the ledger
    grew to 12,631 rows at ~700/day (measured 2026-08-06).

    Closed as **`cancelled`**, not `failed`: these routines did not fail — most
    of them SUCCEEDED, and their real outcome is already recorded in
    `automation_logs`. Marking them `failed` would fabricate an incident history
    and corrupt any future failure-rate metric. `cancelled` says what actually
    happened: the ledger row was abandoned by a bookkeeping bug.

    NEVER requeues. These wrap real side-effecting jobs (`platform_dial`,
    `email_outreach`, …); re-running one to "resolve" it would place real calls
    or send real email. The work is long since done — only the row is stale.

    Safety: bounded `limit`, `dry_run=True` by default, idempotent (only ever
    matches ``pending``, so a second pass over the same rows is a no-op), and a
    JSONL backup of every row is written BEFORE any mutation. Never raises.
    """
    out: dict[str, Any] = {
        "scanned": 0,
        "cancelled": 0,
        "dry_run": bool(dry_run),
        "backup": "",
        "at": _now().isoformat(),
    }
    try:
        import json as _json
        from datetime import timedelta

        from app.models.agent_task import AgentTask
        from app.models.base import get_db_session

        cutoff = _now() - timedelta(hours=max(1, int(older_than_hours)))
        with get_db_session() as db:
            orphans = (
                db.query(AgentTask)
                .filter(
                    AgentTask.status == "pending",
                    AgentTask.claimed_at.is_(None),
                    AgentTask.created_at < cutoff,
                )
                .order_by(AgentTask.created_at.asc())
                .limit(max(1, int(limit)))
                .all()
            )
            out["scanned"] = len(orphans)
            if not orphans:
                return out

            rows_meta = [
                {
                    "id": t.id,
                    "agent_id": t.agent_id,
                    "goal": (t.goal or "")[:200],
                    "status": t.status,
                    "created_at": str(t.created_at),
                    "delegated_by": t.delegated_by,
                }
                for t in orphans
            ]
            if dry_run:
                out["cancelled"] = len(orphans)
                out["sample"] = rows_meta[:5]
                return out

            # Backup BEFORE mutating — a terminal close is not reversible from
            # the row itself once status/completed_at are overwritten.
            try:
                out["backup"] = _write_orphan_backup(rows_meta)
            except Exception as be:  # backup failure must ABORT, not proceed
                out["error"] = f"backup_failed: {str(be)[:120]}"
                return out

            for t in orphans:
                rows = (
                    db.query(AgentTask)
                    .filter(
                        AgentTask.id == t.id,
                        AgentTask.status == "pending",
                        AgentTask.claimed_at.is_(None),
                    )
                    .update(
                        {
                            "status": "cancelled",
                            "completed_at": _now(),
                            "result_summary": (
                                "orphaned_ledger_row: assigned but never claimable "
                                "(see automation_logs for the real job outcome)"
                            ),
                        },
                        synchronize_session=False,
                    )
                )
                if rows:
                    out["cancelled"] += 1
            db.commit()
    except Exception as e:
        logger.warning(f"[atq] reap_orphan_routines failed: {e}")
        out["error"] = str(e)[:200]
    return out


async def reap_stale_leases(
    threshold_minutes: int = 30,
    limit: int = 50,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Close out expired claim-leases TERMINALLY so stuck work stops being invisible.

    `stale_tasks()` deliberately only SURFACES stuck work ("Paperclip philosophy"), so a
    worker that dies between `claim_next()` and `complete()`/`fail()` leaves its task in
    claimed/running FOREVER — it is never resolved and never re-assigned.

    DELIBERATELY NOT A REQUEUE. Requeueing to `pending` would be unsafe here: `complete()`
    (:197) and `fail()` (:236) match on `id` + `status` only — NEITHER guards on
    `checkout_version`. So a slow-but-alive worker whose lease we requeued would keep
    running, a second agent would claim the same row, and the original's `complete()` would
    silently overwrite the second run. Bumping `checkout_version` on requeue does not help,
    precisely because those two writers ignore it. And these leases wrap real side-effecting
    work (`agent_runtime._durable_open` covers every runtime action; `team_scheduler`:309
    covers every scheduled routine), so a double-run is customer-visible, not queue hygiene.

    Terminal-fail keeps the safety property provable: once reaped, the row is `failed`, and
    the original worker's late `complete()`/`fail()` no longer matches the claimed/running
    filter, so it cannot resurrect or overwrite it. Re-assignment stays a human decision —
    faithful to "surface, don't auto-fix". `checkout_version` is recorded in the reason for
    diagnostics only.

    Default `dry_run=True` — reports what it WOULD do and mutates nothing. Never raises.
    """
    out: dict[str, Any] = {
        "scanned": 0,
        "failed": 0,
        "dry_run": bool(dry_run),
        "at": _now().isoformat(),
    }
    try:
        from datetime import timedelta

        from app.models.agent_task import AgentTask
        from app.models.base import get_db_session

        cutoff = _now() - timedelta(minutes=max(1, int(threshold_minutes)))
        with get_db_session() as db:
            stuck = (
                db.query(AgentTask)
                .filter(
                    AgentTask.status.in_(["claimed", "running"]),
                    AgentTask.claimed_at < cutoff,
                )
                .order_by(AgentTask.claimed_at.asc())
                .limit(max(1, int(limit)))
                .all()
            )
            out["scanned"] = len(stuck)
            for t in stuck:
                attempts = t.checkout_version or 0
                if dry_run:
                    out["failed"] += 1
                    continue
                # Same optimistic-lock guard as claim_next — a reap must never clobber a
                # live worker that finished legitimately between our read and this update.
                rows = (
                    db.query(AgentTask)
                    .filter(
                        AgentTask.id == t.id,
                        AgentTask.checkout_version == attempts,
                        AgentTask.status == t.status,
                    )
                    .update(
                        {
                            "status": "failed",
                            "completed_at": _now(),
                            "result_summary": f"lease_expired_after_{attempts}_attempts",
                        },
                        synchronize_session=False,
                    )
                )
                db.commit()
                if rows:
                    out["failed"] += 1
                    _log_event(
                        t.agent_id,
                        "lease_expired",
                        f"⏱️ {(t.goal or '')[:80]} (attempt {attempts}) — needs re-assign",
                    )
    except Exception as e:
        logger.warning(f"[atq] reap_stale_leases failed: {e}")
        out["error"] = str(e)[:200]
    return out


def _log_event(member: str, action: str, detail: str) -> None:
    """Safe team.log_event — never raises."""
    try:
        from app.platform import team

        team.log_event(member, action, detail)
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# Staff Bus task bridge — publish events so the live SSE stream and OpenClaw
# coordination plane see real work flowing.  Fail-open: bus errors never block
# a task state transition.
# --------------------------------------------------------------------------- #


def _bridge_on_assign(
    agent_id: str,
    goal: str,
    task_id: str,
    *,
    delegated_by: str = "human",
    client_id: str | None = None,
) -> None:
    try:
        from app.platform.staff_bus.task_bridge import on_task_assigned

        on_task_assigned(
            agent_id,
            goal,
            task_id,
            delegated_by=delegated_by,
            client_id=client_id,
        )
    except Exception:
        pass


def _bridge_on_claimed(agent_id: str, goal: str, task_id: str) -> None:
    try:
        from app.platform.staff_bus.task_bridge import on_task_accepted

        on_task_accepted(agent_id, goal, task_id)
    except Exception:
        pass


def _bridge_on_complete(task_id: str, result: str) -> None:
    try:
        from app.platform.staff_bus.task_bridge import on_task_completed

        # Resolve agent_id with a lightweight query (fail-open).
        _aid = ""
        try:
            from app.models.agent_task import AgentTask
            from app.models.base import get_db_session

            with get_db_session() as db:
                row = db.query(AgentTask.agent_id).filter(AgentTask.id == task_id).first()
                if row:
                    _aid = row.agent_id
        except Exception:
            pass
        on_task_completed(_aid or "unknown", task_id, result=result)
    except Exception:
        pass


def _bridge_on_fail(task_id: str, error: str) -> None:
    try:
        from app.platform.staff_bus.task_bridge import on_task_failed

        _aid = ""
        try:
            from app.models.agent_task import AgentTask
            from app.models.base import get_db_session

            with get_db_session() as db:
                row = db.query(AgentTask.agent_id).filter(AgentTask.id == task_id).first()
                if row:
                    _aid = row.agent_id
        except Exception:
            pass
        on_task_failed(_aid or "unknown", task_id, error=error)
    except Exception:
        pass
