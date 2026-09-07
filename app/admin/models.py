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
    BACKLOG = "backlog"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    DONE = "done"


class TaskBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = None
    owner: Optional[str] = None
    priority: Priority = Priority.P2
    status: Status = Status.BACKLOG
    deadline: Optional[str] = None
    evidence: Optional[str] = None


class TaskCreate(TaskBase):
    auto_assign: bool = False


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    owner: Optional[str] = None
    priority: Optional[Priority] = None
    status: Optional[Status] = None
    deadline: Optional[str] = None
    evidence: Optional[str] = None


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
    backlog: list[Task] = []
    in_progress: list[Task] = []
    review: list[Task] = []
    done: list[Task] = []


class AutoAssignResult(BaseModel):
    task_id: int
    title: str
    assigned_to: str
