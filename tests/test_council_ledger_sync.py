"""Idempotency contracts for the canonical council task-ledger sync."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

import scripts.council_ledger_sync as sync


def _task(tasks: list[dict], task_id: str) -> dict:
    return next(task for task in tasks if task.get("id") == task_id)


def test_blocked_gate_note_is_normalized_and_second_sync_is_a_noop():
    reason = sync.BLOCKED_RECORD["PLT-004"]
    marker = f"09-06 council: {reason}"
    initial = [
        {
            "id": "PLT-004",
            "status": "RUNNING",
            "notes": f"original | {marker} | {marker}",
            "updated_at": "before",
        }
    ]

    once, _ = sync.plan_tasks(deepcopy(initial))
    first = deepcopy(_task(once, "PLT-004"))
    twice, log = sync.plan_tasks(once)
    second = _task(twice, "PLT-004")

    assert first["status"] == "BLOCKED"
    assert first["notes"].count(marker) == 1
    assert second == first
    assert any("NO-OP GATE PLT-004" in line for line in log)


def test_overdue_running_task_becomes_stale_but_blocked_task_is_untouched():
    tasks = [
        {
            "id": "OLD-RUN",
            "status": "RUNNING",
            "deadline": "2026-09-06T10:00:00+00:00",
            "updated_at": "2026-09-06T09:00:00+00:00",
        },
        {
            "id": "OWNER-GATE",
            "status": "BLOCKED",
            "deadline": "2026-09-06T10:00:00+00:00",
            "updated_at": "2026-09-06T09:00:00+00:00",
        },
    ]

    out, log = sync.normalize_overdue_tasks(
        deepcopy(tasks), now=datetime(2026, 9, 7, 0, 0, tzinfo=timezone.utc)
    )

    assert _task(out, "OLD-RUN")["status"] == "STALE"
    assert _task(out, "OWNER-GATE")["status"] == "BLOCKED"
    assert any("STALE OLD-RUN" in line for line in log)


def test_recently_updated_overdue_task_stays_running_and_stale_sync_is_idempotent():
    now = datetime(2026, 9, 7, 0, 0, tzinfo=timezone.utc)
    tasks = [
        {
            "id": "RECENT",
            "status": "RUNNING",
            "deadline": "2026-09-06T23:00:00+00:00",
            "updated_at": "2026-09-06T23:30:00+00:00",
        },
        {
            "id": "ALREADY-STALE",
            "status": "STALE",
            "deadline": "2026-09-06T10:00:00+00:00",
            "updated_at": "2026-09-06T09:00:00+00:00",
        },
    ]

    once, _ = sync.normalize_overdue_tasks(deepcopy(tasks), now=now)
    twice, log = sync.normalize_overdue_tasks(deepcopy(once), now=now)

    assert _task(once, "RECENT")["status"] == "RUNNING"
    assert twice == once
    assert not any(line.startswith("STALE ") for line in log)
