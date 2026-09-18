"""Tests for dev_workers.py â€” execution proof module (M1, P0).

Run: pytest tests/test_dev_workers.py -v
"""

import json
import os
import tempfile
from pathlib import Path

import pytest

# Import the module under test
from app.platform.dev_workers import (
    DevWorkerProver,
    DevWorkerRecord,
    get_prover,
    prove_execution,
)


class TestDevWorkerRecord:
    """Test DevWorkerRecord dataclass."""

    def test_creation(self):
        """Test basic record creation."""
        record = DevWorkerRecord(
            worker_id="dw_test123",
            task_id="task_abc456",
            lease_token="token_xyz",
            state="claimed",
            evidence="data/output.json",
        )
        assert record.worker_id == "dw_test123"
        assert record.task_id == "task_abc456"
        assert record.state == "claimed"
        assert record.evidence == "data/output.json"
        assert record.claimed_at > 0
        assert record.heartbeat_at > 0

    def test_to_dict(self):
        """Test serialization to dict."""
        record = DevWorkerRecord(
            worker_id="dw_test",
            task_id="task_123",
            lease_token="token_abc",
            state="done",
            evidence="evidence.txt",
        )
        data = record.to_dict()
        assert data["worker_id"] == "dw_test"
        assert data["task_id"] == "task_123"
        assert data["state"] == "done"
        assert "claimed_at" in data
        assert "heartbeat_at" in data

    def test_from_dict(self):
        """Test deserialization from dict."""
        data = {
            "worker_id": "dw_test",
            "task_id": "task_123",
            "lease_token": "token_abc",
            "state": "running",
            "evidence": "evidence.txt",
            "claimed_at": 1000.0,
            "heartbeat_at": 1001.0,
            "done_at": None,
        }
        record = DevWorkerRecord.from_dict(data)
        assert record.worker_id == "dw_test"
        assert record.state == "running"
        assert record.claimed_at == 1000.0


class TestDevWorkerProver:
    """Test DevWorkerProver class."""

    @pytest.fixture
    def temp_ledger(self, tmp_path):
        """Create temp ledger file."""
        ledger_file = tmp_path / "test_ledger.json"
        return str(ledger_file)

    def test_claim_task(self, temp_ledger):
        """Test claiming a task creates execution proof."""
        prover = DevWorkerProver(ledger_path=temp_ledger)
        worker_id = prover.claim("task_123", "lease_token_abc")

        assert worker_id == "dw_task_123"
        assert prover.get_active_count() == 1

        # Verify saved to disk
        assert os.path.exists(temp_ledger)
        with open(temp_ledger) as f:
            data = json.load(f)
        assert len(data["dev_workers"]) == 1
        assert data["dev_workers"][0]["task_id"] == "task_123"

    def test_heartbeat(self, temp_ledger):
        """Test heartbeat updates worker state."""
        prover = DevWorkerProver(ledger_path=temp_ledger)
        worker_id = prover.claim("task_456", "lease_token_xyz")

        # Heartbeat should change state to "running"
        prover.heartbeat(worker_id)
        record = prover.workers[worker_id]
        assert record.state == "running"

    def test_done_with_evidence(self, temp_ledger):
        """Test marking task as done with evidence."""
        prover = DevWorkerProver(ledger_path=temp_ledger)
        worker_id = prover.claim("task_789", "lease_token_def")
        prover.heartbeat(worker_id)
        prover.done(worker_id, "data/output.json")

        record = prover.workers[worker_id]
        assert record.state == "done"
        assert record.evidence == "data/output.json"
        assert record.done_at is not None
        assert prover.get_active_count() == 0  # No longer active

    def test_failed(self, temp_ledger):
        """Test marking task as failed."""
        prover = DevWorkerProver(ledger_path=temp_ledger)
        worker_id = prover.claim("task_fail", "lease_token_fail")
        prover.failed(worker_id, "timeout exceeded")

        record = prover.workers[worker_id]
        assert record.state == "failed"
        assert "FAILED" in record.evidence

    def test_persistence_across_instances(self, temp_ledger):
        """Test that records persist across prover instances."""
        # Create first prover and add records
        prover1 = DevWorkerProver(ledger_path=temp_ledger)
        prover1.claim("task_persist", "lease_token_persist")

        # Create second prover (simulates restart)
        prover2 = DevWorkerProver(ledger_path=temp_ledger)
        assert prover2.get_active_count() == 1
        assert "dw_task_persist" in prover2.workers


class TestModuleLevelFunctions:
    """Test module-level convenience functions."""

    def test_get_prover_singleton(self, tmp_path):
        """Test that get_prover returns singleton."""
        # Clear singleton for test
        import app.platform.dev_workers as dw_module

        original_prover = dw_module._prover
        dw_module._prover = None

        try:
            prover1 = get_prover()
            prover2 = get_prover()
            assert prover1 is prover2  # Same instance
        finally:
            dw_module._prover = original_prover

    def test_prove_execution_convenience(self, tmp_path):
        """Test prove_execution convenience function."""
        import app.platform.dev_workers as dw_module

        original_prover = dw_module._prover
        dw_module._prover = None

        try:
            worker_id = prove_execution("task_full", "lease_token", "evidence.txt")
            assert worker_id == "dw_task_full"

            # Verify it went through full lifecycle
            prover = get_prover()
            record = prover.workers[worker_id]
            assert record.state == "done"
            assert record.evidence == "evidence.txt"
        finally:
            dw_module._prover = original_prover


class TestExecutionProof:
    """Test that execution proof is actually written."""

    def test_dev_workers_becomes_nonzero(self, tmp_path):
        """Verify dev_workers goes from 0 to >0 rows."""
        import app.platform.dev_workers as dw_module

        original_prover = dw_module._prover
        dw_module._prover = None

        try:
            # Initial state: 0 active workers
            prover = get_prover()
            initial_count = prover.get_active_count()
            assert initial_count == 0

            # Trigger execution proof
            worker_id = prove_execution("task_proof", "lease_token_proof", "test_evidence")

            # Verify: >0 active workers (or done workers)
            assert prover.get_active_count() == 0  # Done, not active
            assert len(prover.workers) == 1
            assert worker_id in prover.workers
        finally:
            dw_module._prover = original_prover
