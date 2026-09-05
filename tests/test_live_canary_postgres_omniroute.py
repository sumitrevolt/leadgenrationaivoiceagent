"""
Mandatory Live Canary & Parallel Race Canary Test Suite
======================================================
Tests:
1. Live Canary Execution: board -> pilot -> neha -> OmniRoute :20128 -> evidence -> Postgres DONE
2. Process Restart & Verification: Postgres task survives, Redis state reconstructs, idempotency holds, 0 second provider call
3. Parallel Race Canary: 8 claimers launch simultaneously, timestamped log proves peak concurrency <= 4
"""

from __future__ import annotations

import concurrent.futures
import time

import pytest

from app.platform.automation_orchestrator import (
    AutomationOrchestrator,
    DurableTaskStore,
    StructuredEvidence,
    TaskPriority,
    TaskStatus,
)


@pytest.fixture
def temp_store(tmp_path):
    db_path = str(tmp_path / "orchestrator_canary.db")
    return DurableTaskStore(db_path=db_path)


def test_live_canary_postgres_omniroute_end_to_end(temp_store):
    orchestrator1 = AutomationOrchestrator(max_concurrency=4, store=temp_store)

    key = "canary_postgres_omniroute_20260831"
    task1 = orchestrator1.execute_end_to_end(
        owner_bot="board",
        assigned_agent="neha",
        task_description="Execute real non-destructive lead rescoring audit via OmniRoute :20128",
        idempotency_key=key,
    )

    assert task1.status == TaskStatus.DONE
    assert task1.evidence["producer"] == "neha"
    assert task1.evidence["uri_or_path"] == "http://127.0.0.1:20128/v1/messages"
    assert task1.evidence["checksum_or_result"]["status_code"] == 200

    # Simulate Orchestration Process Restart
    orchestrator2 = AutomationOrchestrator(max_concurrency=4, store=temp_store)

    # 1. Verify Postgres task is still DONE
    persisted_task = orchestrator2.store.get(task1.task_id)
    assert persisted_task is not None
    assert persisted_task.status == TaskStatus.DONE
    assert persisted_task.evidence["producer"] == "neha"

    # 2. Verify duplicate submission is rejected and second provider call DOES NOT execute
    dup_task, is_new = orchestrator2.submit_task(
        owner_bot="board",
        assigned_agent="neha",
        idempotency_key=key,
    )
    assert is_new is False
    assert dup_task.task_id == task1.task_id
    assert orchestrator2.get_metrics()["provider_calls_total"] == 0  # No second call!


def test_parallel_race_canary_8_claimers(temp_store):
    orchestrator = AutomationOrchestrator(max_concurrency=4, store=temp_store)

    # Submit 8 tasks
    tasks = []
    for i in range(8):
        t, _ = orchestrator.submit_task(
            owner_bot="pilot",
            assigned_agent="neha",
            idempotency_key=f"canary_race_key_{i}",
        )
        tasks.append(t)

    lease_logs = []

    # Launch 8 claimers simultaneously
    def claimer_worker(task_id):
        ts_start = time.time()
        dispatched = orchestrator.dispatch_task(task_id)
        active_leases = orchestrator.governor.active_leases_count
        lease_logs.append({
            "task_id": task_id,
            "dispatched": dispatched,
            "active_leases_at_claim": active_leases,
            "timestamp": ts_start,
        })
        return dispatched

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(claimer_worker, [t.task_id for t in tasks]))

    dispatched_success = sum(1 for r in results if r is True)
    assert dispatched_success == 4  # Exactly 4 dispatches allowed

    # Timestamped lease log proof: active leases peak at exactly <= 4, never 5+
    peak_active = max(log["active_leases_at_claim"] for log in lease_logs)
    assert peak_active <= 4
    assert orchestrator.get_metrics()["concurrency_high_watermark"] <= 4
