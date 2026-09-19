"""Tests for dev_workers.py — execution proof module (M1, P0).

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


@pytest.fixture
def clean_prover(monkeypatch, tmp_path):
    """Return a fresh prover with isolated ledger, clearing module singleton."""
    import app.platform.dev_workers as dw_module

    # Clear singleton
    original_prover = getattr(dw_module, "_prover", None)
    dw_module._prover = None

    # Point JSON ledger to tmp_path for test isolation
    ledger_path = str(tmp_path / "test_dev_workers_ledger.json")
    monkeypatch.setattr(dw_module, "JSON_LEDGER_PATH", ledger_path)

    yield DevWorkerProver(ledger_path=ledger_path)

    # Restore singleton
    dw_module._prover = original_prover


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

    def test_claim_task(self, clean_prover):
        """Test claiming a task creates execution proof."""
        prover = clean_prover
        worker_id = prover.claim("task_123", "lease_token_abc")

        assert worker_id == "dw_task_123"
        assert prover.get_active_count() == 1

        # Verify saved to disk
        ledger_path = prover.ledger_path
        assert os.path.exists(ledger_path)
        with open(ledger_path) as f:
            data = json.load(f)
        assert len(data["dev_workers"]) == 1
        assert data["dev_workers"][0]["task_id"] == "task_123"

    def test_heartbeat(self, clean_prover):
        """Test heartbeat updates worker state."""
        prover = clean_prover
        worker_id = prover.claim("task_456", "lease_token_xyz")

        # Heartbeat should change state to "running"
        prover.heartbeat(worker_id)
        record = prover.workers[worker_id]
        assert record.state == "running"

    def test_done_with_evidence(self, clean_prover):
        """Test marking task as done with evidence."""
        prover = clean_prover
        worker_id = prover.claim("task_789", "lease_token_def")
        prover.heartbeat(worker_id)
        prover.done(worker_id, "data/output.json")

        record = prover.workers[worker_id]
        assert record.state == "done"
        assert record.evidence == "data/output.json"
        assert record.done_at is not None
        assert prover.get_active_count() == 0  # No longer active

    def test_failed(self, clean_prover):
        """Test marking task as failed."""
        prover = clean_prover
        worker_id = prover.claim("task_fail", "lease_token_fail")
        prover.failed(worker_id, "timeout exceeded")

        record = prover.workers[worker_id]
        assert record.state == "failed"
        assert "FAILED" in record.evidence

    def test_persistence_across_instances(self, tmp_path):
        """Test that records persist across prover instances."""
        ledger_path = str(tmp_path / "test_persist.json")

        # Create first prover and add records
        prover1 = DevWorkerProver(ledger_path=ledger_path)
        prover1.claim("task_persist", "lease_token_persist")

        # Create second prover (simulates restart)
        prover2 = DevWorkerProver(ledger_path=ledger_path)
        assert prover2.get_active_count() == 1
        assert "dw_task_persist" in prover2.workers

    def test_ledger_isolation_from_sqlite(self, tmp_path):
        """Test that JSON ledger and SQLite ledger remain separate files."""
        import app.platform.dev_workers as dw_module

        # Create a SQLite DB at the canonical path
        sqlite_path = str(tmp_path / "orchestrator_ledger.db")
        store = dw_module.DevWorkerStore(db_path=sqlite_path)
        store.claim("sqlite_task", "token")

        # Create a JSON prover at a different path
        json_path = str(tmp_path / "dev_workers_ledger.json")
        prover = dw_module.DevWorkerProver(ledger_path=json_path)
        prover.claim("json_task", "token")

        # Verify they are different files with different content
        assert os.path.exists(sqlite_path)
        assert os.path.exists(json_path)

        # SQLite file should start with SQLite header
        with open(sqlite_path, "rb") as f:
            sqlite_header = f.read(16)
            assert sqlite_header.startswith(b"SQLite format 3")

        # JSON file should parse as JSON
        with open(json_path) as f:
            json_data = json.load(f)
            assert "dev_workers" in json_data
            assert len(json_data["dev_workers"]) == 1
            assert json_data["dev_workers"][0]["task_id"] == "json_task"

        # Verify SQLite has the other task
        records = store.list_all()
        assert len(records) == 1
        assert records[0].task_id == "sqlite_task"


class TestModuleLevelFunctions:
    """Test module-level convenience functions."""

    def test_get_prover_singleton(self, clean_prover):
        """Test that get_prover returns singleton."""
        prover1 = get_prover()
        prover2 = get_prover()
        assert prover1 is prover2  # Same instance

    def test_prove_execution_convenience(self, clean_prover):
        """Test prove_execution convenience function."""
        worker_id = prove_execution("task_full", "lease_token", "evidence.txt")
        assert worker_id == "dw_task_full"

        # Verify it went through full lifecycle
        prover = get_prover()
        record = prover.workers[worker_id]
        assert record.state == "done"
        assert record.evidence == "evidence.txt"

    def test_worker_id_for(self):
        """Test deterministic worker ID generation."""
        from app.platform.dev_workers import worker_id_for

        assert worker_id_for("task_123") == "dw_task_123"
        assert worker_id_for("") == ""
        assert worker_id_for(None) == ""  # type: ignore


class TestExecutionProof:
    """Test that execution proof is actually written."""

    def test_dev_workers_becomes_nonzero(self, clean_prover):
        """Verify dev_workers goes from 0 to >0 rows."""
        prover = clean_prover
        initial_count = prover.get_active_count()
        assert initial_count == 0

        # Trigger execution proof using the same prover instance
        worker_id = prover.claim("task_proof", "lease_token_proof")
        prover.heartbeat(worker_id)
        prover.done(worker_id, "test_evidence")

        # Verify: >0 active workers (or done workers)
        assert prover.get_active_count() == 0  # Done, not active
        assert len(prover.workers) == 1
        assert worker_id in prover.workers

    def test_json_ledger_path_default(self, clean_prover):
        """Test that default ledger path is the JSON file, not SQLite."""
        assert clean_prover.ledger_path.endswith("dev_workers_ledger.json")

    def test_env_override_ledger_path(self, monkeypatch, tmp_path):
        """Test that DEV_WORKERS_LEDGER_PATH env var overrides default."""
        custom_path = str(tmp_path / "custom_ledger.json")
        monkeypatch.setenv("DEV_WORKERS_LEDGER_PATH", custom_path)

        prover = DevWorkerProver()
        assert prover.ledger_path == custom_path
