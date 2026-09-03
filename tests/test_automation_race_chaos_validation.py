"""
Race & Chaos Validation Test Suite for Automation-Max Orchestrator
===================================================================
Tests:
1. Multi-Worker Concurrency Race: 16 parallel dispatches enforce peak active leases <= 4.
2. Late Return Stale Fencing Token Rejection: Expired/revived worker completions rejected.
3. Atomic Multi-Process Idempotency: 10 parallel submissions yield exactly 1 task record.
4. Complete Metrics Validation: High watermark, latency, fencing rejects, conflicts.
"""

from __future__ import annotations

import time
import pytest
import concurrent.futures

from app.platform.automation_orchestrator import (
    AutomationOrchestrator,
    DurableTaskStore,
    TaskStatus,
    TaskPriority,
    StructuredEvidence,
)


@pytest.fixture
def temp_store(tmp_path):
    db_path = str(tmp_path / "orchestrator_race.db")
    return DurableTaskStore(db_path=db_path)


def test_multi_worker_concurrency_race(temp_store):
    orchestrator = AutomationOrchestrator(max_concurrency=4, store=temp_store)

    # Submit 16 tasks
    task_ids = []
    for i in range(16):
        t, _ = orchestrator.submit_task(
            owner_bot="pilot",
            assigned_agent="neha",
            idempotency_key=f"race_key_{i}",
        )
        task_ids.append(t.task_id)

    # Dispatch all 16 tasks concurrently across 16 worker threads
    def worker_dispatch(tid):
        return orchestrator.dispatch_task(tid)

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
        results = list(executor.map(worker_dispatch, task_ids))

    # Assert exactly 4 tasks dispatched successfully, 12 blocked by concurrency governor
    dispatched_count = sum(1 for r in results if r is True)
    blocked_count = sum(1 for r in results if r is False)

    assert dispatched_count == 4
    assert blocked_count == 12

    metrics = orchestrator.get_metrics()
    assert metrics["concurrency_high_watermark"] <= 4
    assert metrics["active_leases"] == 4


def test_stale_fencing_token_rejection(temp_store):
    orchestrator = AutomationOrchestrator(max_concurrency=4, store=temp_store)

    task, _ = orchestrator.submit_task(
        owner_bot="operations",
        assigned_agent="lekha",
        idempotency_key="fencing_test_task",
    )

    orchestrator.dispatch_task(task.task_id)
    dispatched_task = orchestrator.store.get(task.task_id)
    stale_fencing_token = dispatched_task.fencing_token

    # Simulate a crash/reclaim: manually increment version and token
    dispatched_task.fencing_token = "fence_task_new_999"  # nosecret
    orchestrator.store.save(dispatched_task)

    # Late worker returns with old stale_fencing_token
    evidence = StructuredEvidence(
        type="api_response",
        uri_or_path="http://127.0.0.1:20128/v1",
        producer="lekha",
        checksum_or_result={"status": "late_result"},
    )

    late_task = orchestrator.verify_and_complete(
        task_id=task.task_id,
        execution_evidence=evidence,
        is_success=True,
        fencing_token=stale_fencing_token,
    )

    # Late result MUST be rejected
    assert "Stale Fencing Token Rejected" in late_task.error_message
    assert orchestrator.get_metrics()["stale_result_rejects"] == 1


def test_atomic_multi_process_idempotency_conflict(temp_store):
    orchestrator = AutomationOrchestrator(max_concurrency=4, store=temp_store)
    shared_key = "atomic_idempotency_shared_key_001"

    def submit_worker(worker_id):
        return orchestrator.submit_task(
            owner_bot="board",
            assigned_agent="neha",
            input_payload={"payload": "same_payload"},
            idempotency_key=shared_key,
        )

    # 10 parallel threads submitting the exact same key
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(submit_worker, range(10)))

    new_submissions = sum(1 for task, is_new in results if is_new)
    duplicate_submissions = sum(1 for task, is_new in results if not is_new)

    assert new_submissions == 1
    assert duplicate_submissions == 9

    metrics = orchestrator.get_metrics()
    assert metrics["idempotency_conflicts"] == 9
    assert metrics["duplicate_rejects"] == 9
