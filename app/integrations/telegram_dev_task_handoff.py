"""Canonical Telegram -> DevTask -> API-worker verification handoff.

This is intentionally internal/read-only: the work performed is a liveness
snapshot of the six frozen CLI worker profiles. It creates one canonical
Postgres DevTask, claims it as the Telegram Jarvis API worker, persists the
observed result, and terminates the task. No customer/provider side effect.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, update

from app.dev_control.service import TaskState
from app.models.dev_task import DevTask
from app.models.dev_worker import DevWorker

_API_WORKER_ID = "api_telegram_jarvis"
_EXPECTED_CLI = {
    "cli_operations",
    "cli_engineering",
    "cli_platform",
    "cli_guardian",
    "cli_sales",
    "cli_success",
}


def _utcnow() -> datetime:
    return datetime.utcnow()


def run_canonical_handoff(*, session_factory=None, now: datetime | None = None) -> dict[str, Any]:
    """Run one real, non-destructive canonical coordination verification."""
    if session_factory is None:
        from app.models.base import get_db_session

        session_factory = get_db_session

    now = now or _utcnow()
    task_id = str(uuid.uuid4())
    key = f"telegram:test_handoff:{task_id}"
    objective = "Telegram canonical coordination verification: DevTask claim + six CLI worker liveness"

    with session_factory() as db:
        task = DevTask(
            id=task_id,
            idempotency_key=key,
            parent_objective=objective,
            priority=10,
            state=TaskState.QUEUED.value,
            retry_count=0,
            acceptance_criteria=json.dumps(
                {"expected_cli_workers": sorted(_EXPECTED_CLI), "side_effects": "none"},
                sort_keys=True,
            ),
            created_at=now,
            updated_at=now,
        )
        db.add(task)

        worker = db.get(DevWorker, _API_WORKER_ID)
        if worker is None:
            worker = DevWorker(
                worker_id=_API_WORKER_ID,
                kind="api",
                supervisor_bot="pilot",
                capabilities=json.dumps(
                    ["devtask.claim", "dev_worker.heartbeat", "coordination.verify"],
                    sort_keys=True,
                ),
                version="telegram-devtask-handoff.v1",
                started_at=now,
                heartbeat_ts=now,
                health="healthy",
                pid_host="telegram_jarvis",
                created_at=now,
                updated_at=now,
            )
            db.add(worker)
        else:
            worker.kind = "api"
            worker.supervisor_bot = "pilot"
            worker.heartbeat_ts = now
            worker.health = "healthy"
            worker.updated_at = now
        db.commit()

        won = db.execute(
            update(DevTask)
            .where(DevTask.id == task_id, DevTask.state == TaskState.QUEUED.value)
            .values(
                state=TaskState.CLAIMED.value,
                lease_owner=_API_WORKER_ID,
                lease_until=now + timedelta(seconds=120),
                updated_at=now,
            )
        )
        if not (won.rowcount or 0):
            db.rollback()
            return {"ok": False, "task_id": task_id, "reason": "claim_lost"}

        worker.current_task_id = task_id
        worker.heartbeat_ts = now
        db.commit()

        task.state = TaskState.RUNNING.value
        task.updated_at = now
        db.commit()

        rows = list(db.execute(select(DevWorker).where(DevWorker.kind == "cli")).scalars().all())
        live_ids = {
            str(row.worker_id)
            for row in rows
            if row.health == "healthy"
            and row.heartbeat_ts is not None
            and (now - row.heartbeat_ts).total_seconds() <= 600
        }
        missing = sorted(_EXPECTED_CLI - live_ids)
        unexpected = sorted(live_ids - _EXPECTED_CLI)
        ok = not missing and not unexpected and len(live_ids) == len(_EXPECTED_CLI)
        evidence = {
            "worker": _API_WORKER_ID,
            "execution": "read_only_cli_worker_liveness_snapshot",
            "expected_cli_count": len(_EXPECTED_CLI),
            "live_cli_count": len(live_ids),
            "live_cli_workers": sorted(live_ids),
            "missing_cli_workers": missing,
            "unexpected_cli_workers": unexpected,
            "observed_at": now.isoformat(),
        }

        task.state = TaskState.COMPLETED.value if ok else TaskState.FAILED.value
        task.lease_owner = None
        task.lease_until = None
        task.worker_report = json.dumps(evidence, sort_keys=True)
        task.test_evidence = json.dumps(
            {"coordination_probe": "PASS" if ok else "FAIL", "task_id": task_id},
            sort_keys=True,
        )
        task.blocked_reason = None if ok else f"CLI worker liveness mismatch: missing={missing}"
        task.updated_at = now

        worker.current_task_id = None
        worker.heartbeat_ts = now
        if ok:
            worker.success_count = int(worker.success_count or 0) + 1
            worker.last_error = None
        else:
            worker.failure_count = int(worker.failure_count or 0) + 1
            worker.last_error = task.blocked_reason
        db.commit()

        return {
            "ok": ok,
            "task_id": task_id,
            "state": task.state,
            "worker_id": _API_WORKER_ID,
            **evidence,
        }


__all__ = ["run_canonical_handoff"]
