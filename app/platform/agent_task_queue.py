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


async def assign(
    agent_id: str,
    goal: str,
    *,
    client_id: str | None = None,
    campaign_id: str | None = None,
    goal_text: str = "",
    delegated_by: str = "human",
    parent_task_id: str | None = None,
) -> dict[str, Any]:
    """Create a new task for an agent. Returns the task dict."""
    try:
        from app.models.agent_task import AgentTask
        from app.models.base import get_db_session

        task_id = _id()
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
