"""Pydantic models for Task management."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Priority(str, Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class Status(str, Enum):
    """Admin Kanban task statuses.

    The canonical set now includes ``ready`` and ``blocked`` so that ledger
    rows written by agent/pilot workflows (which already persist those two
    values) do NOT crash the admin Kanban board read path. Legacy 4-value
    rows remain fully valid; any unknown status value is handled fail-safe
    by ``task_ledger._row_to_task`` (no 500).
    """

    BACKLOG = "backlog"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    REVIEW = "review"
    DONE = "done"


class TaskBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    description: str | None = None
    owner: str | None = None
    priority: Priority = Priority.P2
    status: Status = Status.BACKLOG
    deadline: str | None = None
    evidence: str | None = None


class TaskCreate(TaskBase):
    auto_assign: bool = False


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    owner: str | None = None
    priority: Priority | None = None
    status: Status | None = None
    deadline: str | None = None
    evidence: str | None = None


class Task(TaskBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WorkerStatus(BaseModel):
    name: str
    active_tasks: int
    is_idle: bool


class DuplicateMatch(BaseModel):
    task_id: int
    title: str
    similarity: float
    matched_task_id: int
    matched_title: str


class KanbanBoard(BaseModel):
    """Kanban board: six columns covering every canonical Status value.

    ``ready`` and ``blocked`` are first-class columns so that agent/pilot
    task records no longer disappear from the board, and the read path
    (``/admin/api/tasks/kanban``) can no longer 500 on those statuses.
    """

    backlog: list[Task] = []
    ready: list[Task] = []
    in_progress: list[Task] = []
    blocked: list[Task] = []
    review: list[Task] = []
    done: list[Task] = []


class AutoAssignResult(BaseModel):
    task_id: int
    title: str
    assigned_to: str
