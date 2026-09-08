"""Goal hierarchy — Paperclip-inspired first-class goal records.

Company → team → agent goals with status lifecycle
(planned → active → achieved | cancelled), optional task linkage and
customer isolation. Additive: does NOT touch AgentTask / agent_task_queue —
task linkage is advisory (goal.linked_task_ids), so the task queue's atomic
checkout stays the single source of truth for task state.

Storage: Postgres `agent_goals` table (SQLite fallback compatible), same
get_db_session pattern as app.platform.agent_task_queue.

Usage:
    from app.platform import goals

    g = await goals.create_goal("Onboard 2 new paid customers", level="company")
    await goals.update_goal(g["id"], status="active")
    await goals.link_task(g["id"], task_id)
    await goals.add_progress_note(g["id"], "Jiya madeover renew ho gaya")
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

GOAL_LEVELS = ("company", "team", "agent")
GOAL_STATUSES = ("planned", "active", "achieved", "cancelled")

# Forward-only lifecycle; achieved/cancelled are terminal.
_GOAL_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "planned": ("active", "achieved", "cancelled"),
    "active": ("achieved", "cancelled"),
    "achieved": (),
    "cancelled": (),
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _id() -> str:
    return str(uuid.uuid4())


def _valid_level(level: str) -> bool:
    return level in GOAL_LEVELS


def _valid_status(status: str) -> bool:
    return status in GOAL_STATUSES


def _load_linked(raw: str | None) -> list[str]:
    try:
        return list(json.loads(raw or "[]"))
    except (ValueError, TypeError):
        return []


def _serialize_linked(ids: list[str]) -> str:
    return json.dumps(list(dict.fromkeys(ids)))


def _row_to_dict(row: Any) -> dict[str, Any]:
    try:
        linked = json.loads(row.linked_task_ids or "[]")
    except (ValueError, TypeError):
        linked = []
    return {
        "id": row.id,
        "title": row.title,
        "description": row.description or "",
        "level": row.level,
        "status": row.status,
        "parent_goal_id": row.parent_goal_id,
        "owner_agent_id": row.owner_agent_id,
        "client_id": row.client_id,
        "campaign_id": row.campaign_id,
        "target_metric": row.target_metric or "",
        "progress_notes": (row.progress_notes or "").rstrip("\n"),
        "linked_task_ids": linked,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "achieved_at": row.achieved_at.isoformat() if row.achieved_at else None,
    }


async def create_goal(
    title: str,
    *,
    level: str = "team",
    status: str = "planned",
    description: str = "",
    parent_goal_id: str | None = None,
    owner_agent_id: str | None = None,
    client_id: str | None = None,
    campaign_id: str | None = None,
    target_metric: str = "",
) -> dict[str, Any]:
    """Create one goal record. Returns the created row dict. Never raises."""
    title = (title or "").strip()
    level = (level or "team").strip()
    status = (status or "planned").strip()
    if not title:
        return {"ok": False, "error": "title required"}
    if not _valid_level(level):
        return {"ok": False, "error": f"invalid level {level!r} — {GOAL_LEVELS}"}
    if not _valid_status(status):
        return {"ok": False, "error": f"invalid status {status!r} — {GOAL_STATUSES}"}
    parent_goal_id = (parent_goal_id or "").strip() or None
    if parent_goal_id:
        parent = await get_goal(parent_goal_id)
        if not parent:
            return {"ok": False, "error": f"parent goal {parent_goal_id!r} not found"}
    try:
        from app.models.agent_goal import AgentGoal
        from app.models.base import get_db_session

        goal = AgentGoal(
            id=_id(),
            title=title[:500],
            description=(description or "")[:4000],
            level=level,
            status=status,
            parent_goal_id=parent_goal_id,
            owner_agent_id=(owner_agent_id or "").strip() or None,
            client_id=(client_id or "").strip() or None,
            campaign_id=(campaign_id or "").strip() or None,
            target_metric=(target_metric or "")[:200],
            progress_notes="",
            linked_task_ids="[]",
            achieved_at=_now() if status == "achieved" else None,
        )
        with get_db_session() as db:
            db.add(goal)
            db.commit()
            db.refresh(goal)
        return {"ok": True, **goal.to_dict()}
    except Exception as e:  # pragma: no cover — DB down path
        logger.warning("goals.create_goal failed: %s", e)
        return {"ok": False, "error": str(e)}


async def get_goal(goal_id: str) -> dict[str, Any] | None:
    """Fetch one goal as dict, or None. Never raises."""
    try:
        from app.models.agent_goal import AgentGoal
        from app.models.base import get_db_session

        with get_db_session() as db:
            row = db.query(AgentGoal).filter(AgentGoal.id == goal_id).first()
            return _row_to_dict(row) if row else None
    except Exception as e:  # pragma: no cover
        logger.warning("goals.get_goal failed: %s", e)
        return None


async def list_goals(
    *,
    level: str | None = None,
    status: str | None = None,
    client_id: str | None = None,
    parent_goal_id: str | None = None,
    owner_agent_id: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """List goals with optional filters, newest first. Never raises."""
    try:
        from app.models.agent_goal import AgentGoal
        from app.models.base import get_db_session

        with get_db_session() as db:
            q = db.query(AgentGoal)
            if level and _valid_level(level):
                q = q.filter(AgentGoal.level == level)
            if status and _valid_status(status):
                q = q.filter(AgentGoal.status == status)
            if client_id:
                q = q.filter(AgentGoal.client_id == client_id)
            if parent_goal_id:
                q = q.filter(AgentGoal.parent_goal_id == parent_goal_id)
            if owner_agent_id:
                q = q.filter(AgentGoal.owner_agent_id == owner_agent_id)
            rows = q.order_by(AgentGoal.created_at.desc()).limit(max(1, min(limit, 500))).all()
            return [_row_to_dict(r) for r in rows]
    except Exception as e:  # pragma: no cover
        logger.warning("goals.list_goals failed: %s", e)
        return []


async def update_goal(
    goal_id: str,
    *,
    title: str | None = None,
    description: str | None = None,
    status: str | None = None,
    target_metric: str | None = None,
    owner_agent_id: str | None = None,
    progress_note: str | None = None,
) -> dict[str, Any]:
    """Update fields + enforce the forward-only status lifecycle. Never raises."""
    try:
        from app.models.agent_goal import AgentGoal
        from app.models.base import get_db_session

        with get_db_session() as db:
            row = db.query(AgentGoal).filter(AgentGoal.id == goal_id).first()
            if row is None:
                return {"ok": False, "error": "goal not found"}
            if title is not None:
                t = (title or "").strip()
                if not t:
                    return {"ok": False, "error": "title required"}
                row.title = t[:500]
            if description is not None:
                row.description = (description or "")[:4000]
            if target_metric is not None:
                row.target_metric = (target_metric or "")[:200]
            if owner_agent_id is not None:
                row.owner_agent_id = (owner_agent_id or "").strip() or None
            if status is not None:
                s = (status or "").strip()
                if not _valid_status(s):
                    return {"ok": False, "error": f"invalid status {s!r} — {GOAL_STATUSES}"}
                if s != row.status:
                    allowed = _GOAL_TRANSITIONS.get(row.status, ())
                    if s not in allowed:
                        return {
                            "ok": False,
                            "error": f"cannot move goal from {row.status!r} to {s!r}",
                        }
                    row.status = s
                    if s == "achieved" and not row.achieved_at:
                        row.achieved_at = _now()
            if progress_note is not None:
                note = (progress_note or "").strip()
                if note:
                    stamp = _now().strftime("%Y-%m-%d %H:%M UTC")
                    row.progress_notes = (row.progress_notes or "").rstrip("\n") + (
                        f"\n[{stamp}] {note[:2000]}"
                        if row.progress_notes
                        else f"[{stamp}] {note[:2000]}"
                    )
            db.commit()
            db.refresh(row)
        return {"ok": True, **_row_to_dict(row)}
    except Exception as e:  # pragma: no cover
        logger.warning("goals.update_goal failed: %s", e)
        return {"ok": False, "error": str(e)}


async def add_progress_note(goal_id: str, note: str) -> dict[str, Any]:
    """Append one timestamped progress note. Thin wrapper over update_goal."""
    return await update_goal(goal_id, progress_note=note)


async def link_task(goal_id: str, task_id: str) -> dict[str, Any]:
    """Advisory link: record task_id on the goal. Never touches AgentTask rows.

    A task may be linked to at most one goal (goal is the "why" of the task);
    linking to a second goal moves the task there instead of double-linking.
    """
    try:
        from app.models.agent_goal import AgentGoal
        from app.models.base import get_db_session

        task_id = (task_id or "").strip()
        if not task_id:
            return {"ok": False, "error": "task_id required"}
        with get_db_session() as db:
            row = db.query(AgentGoal).filter(AgentGoal.id == goal_id).first()
            if row is None:
                return {"ok": False, "error": "goal not found"}
            linked = _load_linked(row.linked_task_ids)
            if task_id in linked:
                return {"ok": True, "goal_id": goal_id, "task_id": task_id, "already": True}
            linked.append(task_id)
            row.linked_task_ids = _serialize_linked(linked)
            # Move the task to THIS goal if it was linked elsewhere (one "why" per task).
            db.query(AgentGoal).filter(
                AgentGoal.linked_task_ids.like(f"%{task_id}%"),
                AgentGoal.id != goal_id,
            ).update({"linked_task_ids": None}, synchronize_session=False)
            db.commit()
            db.refresh(row)
        return {"ok": True, "goal_id": goal_id, "task_id": task_id, "already": False}
    except Exception as e:  # pragma: no cover
        logger.warning("goals.link_task failed: %s", e)
        return {"ok": False, "error": str(e)}


async def task_goal_lookup(task_id: str) -> dict[str, Any] | None:
    """Reverse lookup: which goal is this task linked to? Never raises."""
    try:
        from app.models.agent_goal import AgentGoal
        from app.models.base import get_db_session

        with get_db_session() as db:
            rows = db.query(AgentGoal).all()
            for row in rows:
                if task_id in _load_linked(row.linked_task_ids):
                    return _row_to_dict(row)
            return None
    except Exception as e:  # pragma: no cover
        logger.warning("goals.task_goal_lookup failed: %s", e)
        return None
