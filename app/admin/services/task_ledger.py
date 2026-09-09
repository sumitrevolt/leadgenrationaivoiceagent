"""Task Ledger service: SQLite-backed task management with auto-assign and duplicate detection."""

from __future__ import annotations

import difflib
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.admin.models import (
    KanbanBoard,
    Priority,
    Status,
    Task,
    TaskCreate,
    TaskUpdate,
    WorkerStatus,
)

# Known workers from Hermes profiles
WORKERS = [
    "board",
    "claude",
    "engineering",
    "guardian",
    "hunter",
    "openclaw",
    "operations",
    "pilot",
    "platform",
    "sales",
    "success",
    "verdant",
    "workbuddy",
]

DB_PATH = Path(__file__).resolve().parent.parent.parent.parent / "data" / "admin_tasks.db"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _get_conn() -> sqlite3.Connection:
    os.makedirs(DB_PATH.parent, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _row_to_task(row) -> Task:
    if isinstance(row, tuple):
        row = {
            "id": row[0],
            "title": row[1],
            "description": row[2],
            "owner": row[3],
            "priority": row[4],
            "status": row[5],
            "deadline": row[6],
            "evidence": row[7],
            "created_at": row[8],
            "updated_at": row[9],
        }
    return Task(
        id=row["id"],
        title=row["title"],
        description=row["description"],
        owner=row["owner"],
        priority=Priority(row["priority"]),
        status=Status(row["status"]),
        deadline=row["deadline"],
        evidence=row["evidence"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def init_db() -> None:
    """Create the tasks table if it does not exist."""
    conn = _get_conn()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                owner TEXT,
                priority TEXT NOT NULL DEFAULT 'P2',
                status TEXT NOT NULL DEFAULT 'backlog',
                deadline TEXT,
                evidence TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.commit()
    finally:
        conn.close()


def _priority_sort_value(p: str) -> int:
    order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    return order.get(p, 99)


def create_task(task_in: TaskCreate) -> Task:
    """Insert a new task into the ledger."""
    init_db()
    now = _utc_now().isoformat()
    conn = _get_conn()
    try:
        cursor = conn.execute(
            """INSERT INTO tasks (title, description, owner, priority, status, deadline, evidence, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                task_in.title,
                task_in.description,
                task_in.owner,
                task_in.priority.value,
                task_in.status.value,
                task_in.deadline,
                task_in.evidence,
                now,
                now,
            ),
        )
        conn.commit()
        task_id = cursor.lastrowid
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return _row_to_task(row)
    finally:
        conn.close()


def get_task(task_id: int) -> Task | None:
    """Fetch a single task by id."""
    init_db()
    conn = _get_conn()
    try:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return _row_to_task(row) if row else None
    finally:
        conn.close()


def list_tasks(
    status_filter: str | None = None,
    owner_filter: str | None = None,
    priority_filter: str | None = None,
) -> list[Task]:
    """Return all tasks with optional filters, sorted by priority then created_at."""
    init_db()
    query = "SELECT * FROM tasks WHERE 1=1"
    params: list = []
    if status_filter:
        query += " AND status = ?"
        params.append(status_filter)
    if owner_filter:
        query += " AND owner = ?"
        params.append(owner_filter)
    if priority_filter:
        query += " AND priority = ?"
        params.append(priority_filter)
    conn = _get_conn()
    try:
        rows = conn.execute(query, params).fetchall()
        tasks = [_row_to_task(r) for r in rows]
        tasks.sort(key=lambda t: (_priority_sort_value(t.priority.value), str(t.created_at)))
        return tasks
    finally:
        conn.close()


def update_task(task_id: int, task_upd: TaskUpdate) -> Task | None:
    """Patch fields on an existing task. Returns updated task or None."""
    existing = get_task(task_id)
    if existing is None:
        return None
    init_db()
    now = _utc_now().isoformat()
    fields: list[str] = ["updated_at = ?"]
    params: list = [now]

    data = task_upd.model_dump(exclude_unset=True)
    for key, val in data.items():
        if val is not None:
            if hasattr(val, "value"):
                val = val.value
            fields.append(f"{key} = ?")
            params.append(val)
    params.append(task_id)
    conn = _get_conn()
    try:
        conn.execute(f"UPDATE tasks SET {', '.join(fields)} WHERE id = ?", params)
        conn.commit()
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return _row_to_task(row)
    finally:
        conn.close()


def delete_task(task_id: int) -> bool:
    """Delete a task. Returns True if a row was removed."""
    init_db()
    conn = _get_conn()
    try:
        cursor = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def get_worker_statuses() -> list[WorkerStatus]:
    """Return each worker's active-task count and idle flag."""
    init_db()
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT owner, COUNT(*) as cnt FROM tasks WHERE status = 'in_progress' GROUP BY owner"
        ).fetchall()
        active_map = {r["owner"]: r["cnt"] for r in rows if r["owner"]}
    finally:
        conn.close()

    statuses = []
    for name in WORKERS:
        cnt = active_map.get(name, 0)
        statuses.append(WorkerStatus(name=name, active_tasks=cnt, is_idle=(cnt == 0)))
    return statuses


def get_idle_workers() -> list[str]:
    """Return names of workers with zero active tasks."""
    return [ws.name for ws in get_worker_statuses() if ws.is_idle]


def auto_assign(task: Task) -> str | None:
    """Assign a task to an idle worker with the fewest tasks. Returns worker name or None."""
    idle = get_idle_workers()
    if not idle:
        return None

    init_db()
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT owner, COUNT(*) as cnt FROM tasks WHERE owner IN ({}) AND status != 'done' GROUP BY owner".format(
                ",".join("?" for _ in idle)
            ),
            idle,
        ).fetchall()
        task_count = {r["owner"]: r["cnt"] for r in rows}
    finally:
        conn.close()

    for name in idle:
        task_count.setdefault(name, 0)

    # Pick the idle worker with fewest non-done tasks
    chosen = min(idle, key=lambda n: task_count.get(n, 0))

    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE tasks SET owner = ?, updated_at = ? WHERE id = ?",
            (chosen, _utc_now().isoformat(), task.id),
        )
        conn.commit()
    finally:
        conn.close()
    return chosen


def auto_assign_all() -> list[dict]:
    """Auto-assign all unassigned backlog tasks. Returns list of {task_id, title, assigned_to}."""
    init_db()
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE owner IS NULL AND status = 'backlog' ORDER BY created_at"
        ).fetchall()
    finally:
        conn.close()

    results = []
    for row in rows:
        task = _row_to_task(row)
        worker = auto_assign(task)
        if worker:
            results.append({"task_id": task.id, "title": task.title, "assigned_to": worker})
    return results


def get_kanban() -> KanbanBoard:
    """Return tasks grouped by status for Kanban view."""
    init_db()
    tasks = list_tasks()
    board = KanbanBoard()
    for t in tasks:
        if t.status == Status.BACKLOG:
            board.backlog.append(t)
        elif t.status == Status.IN_PROGRESS:
            board.in_progress.append(t)
        elif t.status == Status.REVIEW:
            board.review.append(t)
        elif t.status == Status.DONE:
            board.done.append(t)
    return board


def get_worker_tasks(worker_name: str) -> list[Task]:
    """Return all tasks assigned to a specific worker."""
    init_db()
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE owner = ? ORDER BY created_at", (worker_name,)
        ).fetchall()
        return [_row_to_task(r) for r in rows]
    finally:
        conn.close()


def detect_duplicates(new_title: str, threshold: float = 0.75) -> list[dict]:
    """Find existing tasks whose title is similar to new_title (fuzzy match)."""
    init_db()
    conn = _get_conn()
    try:
        rows = conn.execute("SELECT id, title FROM tasks").fetchall()
    finally:
        conn.close()

    matches = []
    new_lower = new_title.lower()
    for row in rows:
        ratio = difflib.SequenceMatcher(None, new_lower, row["title"].lower()).ratio()
        if ratio >= threshold:
            matches.append(
                {
                    "task_id": row["id"],
                    "title": row["title"],
                    "similarity": round(ratio, 3),
                    "matched_title": new_title,
                }
            )
    matches.sort(key=lambda m: m["similarity"], reverse=True)
    return matches
