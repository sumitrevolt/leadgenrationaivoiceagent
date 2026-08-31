"""
Mandatory Canary & Durability Test Suite for Automation-Max Orchestrator
=========================================================================
Tests:
1. End-to-End Canary Run: board -> pilot -> neha -> provider call -> evidence -> guardian -> DONE
2. Process Crash & Restart Simulation: Re-instantiating AutomationOrchestrator from disk/ledger
3. Persistent Idempotency: Deduplication holds across restarts (no duplicate re-execution)
4. Stale RUNNING Task Recovery: Reclaims crashed/idle leases on startup
5. Kill Switch AUTOMATION_STOP_NEW_CLAIMS: Rejects new claims while preserving safety
6. Kanban & Metrics Projection: Reads from actual persisted ledger
"""

from __future__ import annotations

import os
import time
import pytest

from app.platform.automation_orchestrator import (
    AutomationOrchestrator,
    DurableTaskStore,
    TaskStatus,
    TaskPriority,
    StructuredEvidence,
)


@pytest.fixture
def temp_store(tmp_path):
    db_path = str(tmp_path / "orchestrator_durability.db")
    return DurableTaskStore(db_path=db_path)


def test_canary_end_to_end_and_restart_durability(temp_store):
    # Step 1: Initialize Orchestrator #1 & execute end-to-end task
    orchestrator1 = AutomationOrchestrator(max_concurrency=4, store=temp_store)

    key = "canary_neha_rescore_20260831"
    task1 = orchestrator1.execute_end_to_end(
        owner_bot="board",
        assigned_agent="neha",
        task_description="Execute real lead rescoring audit",
        idempotency_key=key,
    )

    assert task1.status == TaskStatus.DONE
    assert task1.evidence["producer"] == "neha"
    assert task1.evidence["checksum_or_result"]["status_code"] == 200

    # Step 2: Simulate Process Crash & Restart (Create Orchestrator #2 with same store)
    orchestrator2 = AutomationOrchestrator(max_concurrency=4, store=temp_store)

    # Prove ledger survived restart
    recovered_task = orchestrator2.store.get(task1.task_id)
    assert recovered_task is not None
    assert recovered_task.status == TaskStatus.DONE
    assert recovered_task.evidence["producer"] == "neha"

    # Prove duplicate execution is blocked via persistent idempotency
    dup_task, is_new = orchestrator2.submit_task(
        owner_bot="board",
        assigned_agent="neha",
        idempotency_key=key,
    )
    assert is_new is False
    assert dup_task.task_id == task1.task_id
    assert orchestrator2.get_metrics()["duplicate_rejects"] == 1


def test_stale_running_task_recovery_on_startup(temp_store):
    orchestrator1 = AutomationOrchestrator(max_concurrency=4, store=temp_store)

    # Create a task and set its status to RUNNING with an old heartbeat (simulating a crash)
    task, _ = orchestrator1.submit_task(
        owner_bot="operations",
        assigned_agent="lekha",
        idempotency_key="stale_task_key_999",
    )
    task.status = TaskStatus.RUNNING
    task.last_heartbeat = time.time() - 120.0  # 120s old (> 60s timeout)
    orchestrator1.store.save(task)

    # Simulate process restart -> Orchestrator #2 recovers stale task
    orchestrator2 = AutomationOrchestrator(max_concurrency=4, store=temp_store)

    recovered = orchestrator2.store.get(task.task_id)
    assert recovered.status == TaskStatus.READY  # Re-queued safely
    assert recovered.retry_count == 1
    assert "Stale RUNNING task reclaimed" in recovered.error_message


def test_kill_switch_automation_stop_new_claims(temp_store, monkeypatch):
    orchestrator = AutomationOrchestrator(max_concurrency=4, store=temp_store)

    # Arm Kill Switch
    monkeypatch.setenv("AUTOMATION_STOP_NEW_CLAIMS", "1")
    assert orchestrator.is_kill_switch_active() is True

    task, _ = orchestrator.submit_task(
        owner_bot="pilot",
        assigned_agent="neha",
        idempotency_key="kill_switch_test_task",
    )

    dispatched = orchestrator.dispatch_task(task.task_id)
    assert dispatched is False
    blocked_task = orchestrator.store.get(task.task_id)
    assert blocked_task.status == TaskStatus.BLOCKED
    assert "AUTOMATION_STOP_NEW_CLAIMS" in blocked_task.error_message

    # Disarm Kill Switch
    monkeypatch.setenv("AUTOMATION_STOP_NEW_CLAIMS", "0")
    assert orchestrator.is_kill_switch_active() is False


def test_structured_guardian_evidence_validation(temp_store):
    orchestrator = AutomationOrchestrator(max_concurrency=4, store=temp_store)

    task, _ = orchestrator.submit_task(
        owner_bot="guardian",
        assigned_agent="kavya",
        idempotency_key="evidence_val_key",
    )
    orchestrator.dispatch_task(task.task_id)

    # Invalid evidence (missing type/producer) -> REVIEW state
    bad_task = orchestrator.verify_and_complete(
        task_id=task.task_id,
        execution_evidence={"raw_text": "unstructured"},
        is_success=True,
    )
    assert bad_task.status == TaskStatus.REVIEW
    assert "Guardian Verification Failed" in bad_task.error_message
    assert orchestrator.get_metrics()["guardian_rejects"] == 1

    # Valid StructuredEvidence -> DONE state
    good_evidence = StructuredEvidence(
        type="test_result",
        uri_or_path="logs/health.log",
        producer="kavya",
        checksum_or_result={"score": 100},
    )
    task.status = TaskStatus.RUNNING
    good_task = orchestrator.verify_and_complete(
        task_id=task.task_id,
        execution_evidence=good_evidence,
        is_success=True,
    )
    assert good_task.status == TaskStatus.DONE
    assert good_task.evidence["type"] == "test_result"


def test_coordination_hub_projection(temp_store):
    from app.platform import coordination_hub

    orchestrator = AutomationOrchestrator(max_concurrency=4, store=temp_store)
    orchestrator.execute_end_to_end(
        owner_bot="board",
        assigned_agent="neha",
        task_description="Hub test task",
        idempotency_key="hub_test_key_007",
    )

    hub_slice = coordination_hub._automation_orchestrator_slice()
    assert hub_slice["ok"] is True
    assert "kanban" in hub_slice
    assert "metrics" in hub_slice
