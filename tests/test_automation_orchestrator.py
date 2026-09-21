"""
Test Suite for Automation-Max Orchestrator Control Plane
=========================================================
Tests:
1. Idempotency & Duplicate Task Rejection
2. Global Concurrency Governor Hard Cap (Max 4 Leases)
3. End-to-End Task Execution Flow (board -> pilot -> agent -> guardian -> DONE)
4. Guardian Safety Gate Enforcement (RED Lane / HARD_OFF Agents Blocked)
5. Bounded Retries & DLQ Escalation
6. Kanban Sync Status Board
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.platform.automation_orchestrator import (
    AutomationOrchestrator,
    DurableTaskStore,
    TaskPriority,
    TaskStatus,
)

SQLITE_MAGIC = b"SQLite format 3\x00"


@pytest.fixture
def temp_store(tmp_path):
    db_path = str(tmp_path / "orchestrator_orch.db")
    return DurableTaskStore(db_path=db_path)


# ---------------------------------------------------------------------------
# Finding B-9: a non-SQLite file at the ledger path must self-heal, not be fatal
# ---------------------------------------------------------------------------
def test_corrupt_non_sqlite_ledger_is_quarantined_not_fatal(tmp_path):
    """`data/orchestrator_ledger.db` once held JSON. `sqlite3.connect` is lazy, so
    this used to blow up at CREATE TABLE inside __init__ -- the canonical task
    ledger could not be instantiated at all. It must now recover, and keep the
    corrupt bytes as evidence (rename, never delete).
    """
    db = tmp_path / "orchestrator_ledger.db"
    db.write_bytes(b'{\r\n  "dev_workers": []}')  # B-9's observed first bytes

    store = DurableTaskStore(db_path=str(db))

    assert store.quarantined_path, "corrupt ledger must be reported as quarantined"
    kept = Path(store.quarantined_path)
    assert kept.exists() and kept.read_bytes().startswith(b"{")
    assert db.read_bytes().startswith(SQLITE_MAGIC), "fresh ledger must be real SQLite"
    # The recreated ledger is actually usable (table exists, queries run).
    assert store.get("does-not-exist") is None


def test_valid_sqlite_ledger_is_never_quarantined(tmp_path):
    """No data loss path: an existing healthy ledger is untouched on reopen."""
    db = tmp_path / "orchestrator_ledger.db"
    first = DurableTaskStore(db_path=str(db))
    assert first.quarantined_path is None

    second = DurableTaskStore(db_path=str(db))
    assert second.quarantined_path is None
    assert list(tmp_path.glob("*.corrupt-*")) == []


def test_missing_or_empty_ledger_is_not_quarantined(tmp_path):
    """An absent or 0-byte file is a valid SQLite start state, not corruption."""
    db = tmp_path / "absent.db"
    assert DurableTaskStore(db_path=str(db)).quarantined_path is None

    empty = tmp_path / "empty.db"
    empty.write_bytes(b"")
    assert DurableTaskStore(db_path=str(empty)).quarantined_path is None
    assert list(tmp_path.glob("*.corrupt-*")) == []


def test_repeated_corruption_keeps_every_quarantined_copy(tmp_path):
    """Two corrupt writes must both survive -- the second must not clobber the first."""
    db = tmp_path / "orchestrator_ledger.db"
    db.write_bytes(b'{"gen": 1}')
    DurableTaskStore(db_path=str(db))
    db.write_bytes(b'{"gen": 2}')
    DurableTaskStore(db_path=str(db))

    kept = sorted(p.read_bytes() for p in tmp_path.glob("*.corrupt-*"))
    assert kept == [b'{"gen": 1}', b'{"gen": 2}']


def test_hermes_9bot_supervisory_mapping(temp_store):
    orchestrator = AutomationOrchestrator(store=temp_store)
    assert len(orchestrator.HERMES_BOTS) == 9
    assert "board" in orchestrator.HERMES_BOTS
    assert "pilot" in orchestrator.HERMES_BOTS
    assert "guardian" in orchestrator.HERMES_BOTS
    assert "sales" in orchestrator.HERMES_BOTS
    assert "hunter" in orchestrator.HERMES_BOTS
    assert "engineering" in orchestrator.HERMES_BOTS
    assert "platform" in orchestrator.HERMES_BOTS
    assert "operations" in orchestrator.HERMES_BOTS
    assert "success" in orchestrator.HERMES_BOTS


def test_idempotency_duplicate_rejection(temp_store):
    orchestrator = AutomationOrchestrator(store=temp_store)
    key = "uniq_test_key_12345"

    task1, is_new1 = orchestrator.submit_task(
        owner_bot="pilot",
        assigned_agent="neha",
        priority=TaskPriority.HIGH,
        idempotency_key=key,
    )
    assert is_new1 is True
    assert task1.status == TaskStatus.READY

    task2, is_new2 = orchestrator.submit_task(
        owner_bot="pilot",
        assigned_agent="neha",
        priority=TaskPriority.HIGH,
        idempotency_key=key,
    )
    assert is_new2 is False
    assert task2.task_id == task1.task_id


def test_global_concurrency_governor(temp_store):
    orchestrator = AutomationOrchestrator(max_concurrency=4, store=temp_store)
    assert orchestrator.governor.max_leases == 4
    assert orchestrator.governor.active_leases_count == 0

    # Acquire 4 leases
    tasks = []
    for i in range(4):
        t, _ = orchestrator.submit_task(
            owner_bot="pilot",
            assigned_agent="neha",
            idempotency_key=f"task_conc_{i}",
        )
        ok = orchestrator.dispatch_task(t.task_id)
        assert ok is True
        tasks.append(t)

    assert orchestrator.governor.active_leases_count == 4

    # 5th dispatch must be blocked by concurrency limit
    t5, _ = orchestrator.submit_task(
        owner_bot="pilot",
        assigned_agent="neha",
        idempotency_key="task_conc_5",
    )
    ok5 = orchestrator.dispatch_task(t5.task_id)
    assert ok5 is False
    blocked_t5 = orchestrator.store.get(t5.task_id)
    assert blocked_t5.status == TaskStatus.BLOCKED
    assert "Concurrency Limit" in blocked_t5.error_message

    # Release 1 lease
    orchestrator.verify_and_complete(
        task_id=tasks[0].task_id,
        execution_evidence={
            "type": "api_response",
            "uri_or_path": "http://127.0.0.1:20128/v1",
            "producer": "neha",
        },
        is_success=True,
    )
    assert orchestrator.governor.active_leases_count == 3


def test_end_to_end_execution_flow(temp_store):
    orchestrator = AutomationOrchestrator(store=temp_store)

    completed_task = orchestrator.execute_end_to_end(
        owner_bot="board",
        assigned_agent="neha",
        task_description="Run lead rescoring audit for active accounts",
        idempotency_key="e2e_rescore_001",
    )

    assert completed_task.status == TaskStatus.DONE
    assert completed_task.evidence["producer"] == "neha"
    assert completed_task.evidence["checksum_or_result"]["status_code"] == 200
    assert completed_task.error_message is None


def test_guardian_safety_gate_blocks_red_lane(temp_store):
    orchestrator = AutomationOrchestrator(store=temp_store)

    # 'swara' is in RED lane / HARD_OFF mode
    task, _ = orchestrator.submit_task(
        owner_bot="sales",
        assigned_agent="swara",
        idempotency_key="swara_dial_attempt",
    )

    dispatched = orchestrator.dispatch_task(task.task_id)
    assert dispatched is False
    blocked_task = orchestrator.store.get(task.task_id)
    assert blocked_task.status == TaskStatus.BLOCKED
    assert "Guardian Safety Gate" in blocked_task.error_message


def test_typesafe_session_policy_can_route_substantial_task_to_review(temp_store, monkeypatch):
    from app.platform import typesafe_session_policy

    monkeypatch.setattr(
        typesafe_session_policy,
        "judge_task",
        lambda **_kw: {
            "decision_id": "ts-session-1",
            "route": "review",
            "reason": "semantic uncertainty",
            "traced": True,
        },
    )
    orchestrator = AutomationOrchestrator(store=temp_store)
    task, _ = orchestrator.submit_task(
        owner_bot="sales",
        assigned_agent="neha",
        input_payload={"objective": "Choose the highest-value sales follow-up"},
        idempotency_key="typesafe-session-review",
    )

    assert orchestrator.dispatch_task(task.task_id) is False
    saved = orchestrator.store.get(task.task_id)
    assert saved.status == TaskStatus.REVIEW
    assert saved.input_payload["_typesafe_session_policy"]["decision_id"] == "ts-session-1"
    assert saved.fencing_token is None


def test_typesafe_session_policy_is_reused_on_task_retry(temp_store, monkeypatch):
    from app.platform import typesafe_session_policy

    calls = []

    def _judge(**_kw):
        calls.append("called")
        return {
            "decision_id": "ts-session-once",
            "route": "proceed",
            "reason": "typesafe_judgment",
            "traced": True,
        }

    monkeypatch.setattr(typesafe_session_policy, "judge_task", _judge)
    orchestrator = AutomationOrchestrator(store=temp_store)
    task, _ = orchestrator.submit_task(
        owner_bot="sales",
        assigned_agent="neha",
        input_payload={"objective": "Retry one governed sales task"},
        idempotency_key="typesafe-session-retry-once",
    )

    assert orchestrator.dispatch_task(task.task_id) is True
    first = orchestrator.store.get(task.task_id)
    assert first.input_payload["_typesafe_session_policy"]["decision_id"] == "ts-session-once"
    retried = orchestrator.verify_and_complete(
        task_id=task.task_id,
        execution_evidence={},
        is_success=False,
        error_msg="temporary provider timeout",
    )
    assert retried.status == TaskStatus.READY
    assert orchestrator.dispatch_task(task.task_id) is True
    assert calls == ["called"]


def test_bounded_retry_and_dlq_escalation(temp_store):
    orchestrator = AutomationOrchestrator(store=temp_store)

    task, _ = orchestrator.submit_task(
        owner_bot="operations",
        assigned_agent="priya",
        idempotency_key="priya_crm_sync_retry",
    )
    task.max_retries = 2
    orchestrator.store.save(task)

    orchestrator.dispatch_task(task.task_id)

    # Retry 1
    t1 = orchestrator.verify_and_complete(
        task_id=task.task_id,
        execution_evidence={},
        is_success=False,
        error_msg="CRM API Timeout",
    )
    assert t1.retry_count == 1
    assert t1.status == TaskStatus.READY

    # Dispatch & Retry 2 -> Escalates to FAILED
    orchestrator.dispatch_task(task.task_id)
    t2 = orchestrator.verify_and_complete(
        task_id=task.task_id,
        execution_evidence={},
        is_success=False,
        error_msg="CRM API Timeout 2",
    )
    assert t2.retry_count == 2
    assert t2.status == TaskStatus.FAILED


def test_kanban_board_sync(temp_store):
    orchestrator = AutomationOrchestrator(store=temp_store)

    orchestrator.execute_end_to_end(
        owner_bot="operations",
        assigned_agent="lekha",
        task_description="Digest KPIs",
        idempotency_key="kanban_digest_1",
    )

    board = orchestrator.get_kanban_board()
    assert "DONE" in board
    assert len(board["DONE"]) == 1
    assert board["DONE"][0]["assigned_agent"] == "lekha"
