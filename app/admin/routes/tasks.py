"""REST API routes for Task Ledger."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.admin.models import (
    AutoAssignResult,
    DuplicateMatch,
    KanbanBoard,
    Task,
    TaskCreate,
    TaskUpdate,
)
from app.admin.services.task_ledger import (
    auto_assign_all,
    create_task,
    delete_task,
    detect_duplicates,
    get_kanban,
    get_task,
    get_worker_tasks,
    list_tasks,
    update_task,
)

router = APIRouter()


@router.get("/admin/api/tasks", response_model=list[Task])
async def get_tasks(
    status: str | None = Query(None, description="Filter by status"),
    owner: str | None = Query(None, description="Filter by owner"),
    priority: str | None = Query(None, description="Filter by priority"),
):
    """List all tasks with optional filters."""
    return list_tasks(status_filter=status, owner_filter=owner, priority_filter=priority)


@router.get("/admin/api/tasks/kanban", response_model=KanbanBoard)
async def kanban():
    """Return tasks grouped by status for Kanban view."""
    return get_kanban()


@router.post("/admin/api/tasks", response_model=Task)
async def create_new_task(task_in: TaskCreate):
    """Create a new task. Optionally auto-assign to an idle worker."""
    task = create_task(task_in)
    if task_in.auto_assign and task.owner is None:
        from app.admin.services.task_ledger import auto_assign
        worker = auto_assign(task)
        if worker:
            task = update_task(task.id, TaskUpdate(owner=worker))
    return task


@router.put("/admin/api/tasks/{task_id}", response_model=Task)
async def update_existing_task(task_id: int, task_upd: TaskUpdate):
    """Update an existing task."""
    updated = update_task(task_id, task_upd)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return updated


@router.delete("/admin/api/tasks/{task_id}")
async def delete_existing_task(task_id: int):
    """Delete a task by id."""
    deleted = delete_task(task_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return {"status": "deleted", "task_id": task_id}


@router.post("/admin/api/tasks/auto-assign")
async def auto_assign_unassigned():
    """Assign all unassigned backlog tasks to idle workers."""
    results = auto_assign_all()
    return {"assigned": results, "count": len(results)}


@router.get("/admin/api/tasks/duplicates")
async def find_duplicates(title: str = Query(..., description="Title to check for duplicates")):
    """Find potential duplicate tasks by fuzzy title matching."""
    matches = detect_duplicates(title)
    return {"query": title, "matches": matches, "count": len(matches)}


@router.get("/admin/api/tasks/worker/{worker_name}", response_model=list[Task])
async def worker_tasks(worker_name: str):
    """Get all tasks assigned to a specific worker."""
    return get_worker_tasks(worker_name)
