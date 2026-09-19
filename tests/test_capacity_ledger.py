"""Tests for capacity_ledger.py â€” 97Ã— gap computation (M2, P1).

Run: pytest tests/test_capacity_ledger.py -v
"""

import json
import os
import tempfile
from pathlib import Path

import pytest

from app.platform.capacity_ledger import CapacityLedger, CapacitySnapshot, get_ledger, compute_and_print


class TestCapacitySnapshot:
    """Test CapacitySnapshot dataclass."""

    def test_creation(self):
        """Test basic snapshot creation."""
        snapshot = CapacitySnapshot(
            email_capacity=175,
            voice_capacity=700,
            whatsapp_capacity=0,
            total_capacity=875,
            gap_to_target=84125,
            utilization=0.0103,
            blocked_by_compliance=350
        )
        assert snapshot.email_capacity == 175
        assert snapshot.gap_to_target == 84125
        assert snapshot.utilization == pytest.approx(0.0103)

    def test_to_dict(self):
        """Test serialization."""
        snapshot = CapacitySnapshot(
            email_capacity=100,
            voice_capacity=200,
            whatsapp_capacity=0,
            total_capacity=300,
            gap_to_target=84700,
            utilization=0.0035,
            blocked_by_compliance=100
        )
        data = snapshot.to_dict()
        assert data["email_capacity"] == 100
        assert data["target_capacity"] == 85000  # From constant
        assert "timestamp" in data

    def test_from_dict(self):
        """Test deserialization."""
        data = {
            "timestamp": "2026-09-17T00:00:00Z",
            "email_capacity": 100,
            "voice_capacity": 200,
            "whatsapp_capacity": 0,
            "total_capacity": 300,
            "target_capacity": 85000,
            "gap_to_target": 84700,
            "utilization": 0.0035,
            "blocked_by_compliance": 100
        }
        snapshot = CapacitySnapshot.from_dict(data)
        assert snapshot.email_capacity == 100
        assert snapshot.gap_to_target == 84700


class TestCapacityLedger:
    """Test CapacityLedger class."""

    @pytest.fixture
    def snapshot_path(self, tmp_path):
        """Create temp snapshot file path (str) using pytest's built-in tmp_path."""
        snapshot_file = tmp_path / "capacity_snapshot.json"
        return str(snapshot_file)

    def test_compute_baseline(self, snapshot_path):
        """Test baseline capacity computation (default caps)."""
        ledger = CapacityLedger(snapshot_path=snapshot_path)
        snapshot = ledger.compute()

        # Default caps: email=25/day, voice=100/day, WhatsApp=OFF
        assert snapshot.email_capacity == 175  # 25 * 7
        assert snapshot.voice_capacity == 700  # 100 * 7
        assert snapshot.whatsapp_capacity == 0
        assert snapshot.total_capacity == 875
        assert snapshot.gap_to_target == 84125  # 85000 - 875
        # Use looser tolerance for floating point
        assert snapshot.utilization == pytest.approx(0.0103, rel=0.01)

    def test_compute_with_env_overrides(self, snapshot_path, monkeypatch):
        """Test capacity computation with env var overrides."""
        # Override caps via env vars
        monkeypatch.setenv("EMAIL_OUTREACH_CAP", "50")
        monkeypatch.setenv("PLATFORM_DIAL_LIMIT", "500")
        monkeypatch.setenv("SALES_AUTOPILOT_WHATSAPP_ENABLED", "1")

        ledger = CapacityLedger(snapshot_path=snapshot_path)
        snapshot = ledger.compute()

        assert snapshot.email_capacity == 350  # 50 * 7
        assert snapshot.voice_capacity == 3500  # 500 * 7
        assert snapshot.whatsapp_capacity == 1000  # placeholder
        assert snapshot.total_capacity == 4850  # 350 + 3500 + 1000

    def test_persistence(self, snapshot_path):
        """Test snapshot persists to disk."""
        ledger = CapacityLedger(snapshot_path=snapshot_path)
        ledger.compute()

        # Verify file exists
        assert os.path.exists(snapshot_path)

        # Verify content
        with open(snapshot_path, "r") as f:
            data = json.load(f)
        assert data["total_capacity"] == 875
        assert data["gap_to_target"] == 84125

    def test_load_existing(self, snapshot_path):
        """Test loading existing snapshot."""
        # Create initial snapshot
        ledger1 = CapacityLedger(snapshot_path=snapshot_path)
        ledger1.compute()

        # Create new instance (simulates restart)
        ledger2 = CapacityLedger(snapshot_path=snapshot_path)
        assert ledger2.get_snapshot() is not None
        assert ledger2.get_snapshot().total_capacity == 875

    def test_print_status(self, snapshot_path, capsys):
        """Test status printing."""
        ledger = CapacityLedger(snapshot_path=snapshot_path)
        ledger.print_status()

        captured = capsys.readouterr()
        assert "CAPACITY SNAPSHOT" in captured.out
        assert "875" in captured.out  # total capacity
        assert "84,125" in captured.out  # gap


class TestGapComputation:
    """Test the 97Ã— gap computation (core business requirement)."""

    def test_97x_gap_verified(self, tmp_path):
        """Verify 97Ã— gap: 875/week current vs 85,000/week target."""
        ledger = CapacityLedger(snapshot_path=tmp_path)
        snapshot = ledger.compute()

        # Core requirement: gap should be ~97Ã—
        expected_gap = 85000 - 875  # 84,125
        assert snapshot.gap_to_target == expected_gap

        # Utilization should be tiny (~1%)
        assert snapshot.utilization == pytest.approx(0.0103, abs=0.001)

    def test_scaling_scenarios(self, tmp_path, monkeypatch):
        """Test various scaling scenarios."""
        # Scenario 1: Double email cap
        monkeypatch.setenv("EMAIL_OUTREACH_CAP", "50")
        ledger = CapacityLedger(snapshot_path=tmp_path)
        snapshot = ledger.compute()
        assert snapshot.email_capacity == 350  # 50 * 7

        # Scenario 2: Enable WhatsApp
        monkeypatch.setenv("SALES_AUTOPILOT_WHATSAPP_ENABLED", "1")
        snapshot2 = ledger.compute()
        assert snapshot2.whatsapp_capacity == 1000  # placeholder

        # Scenario 3: Both scaled
        monkeypatch.setenv("EMAIL_OUTREACH_CAP", "100")
        monkeypatch.setenv("PLATFORM_DIAL_LIMIT", "1000")
        snapshot3 = ledger.compute()
        assert snapshot3.total_capacity == 700 + 7000 + 1000  # email + voice + WA


class TestIntegration:
    """Integration tests with real ledger."""

    def test_end_to_end_compute_and_save(self, tmp_path):
        """Test full compute -> save -> load cycle."""
        snap_file = str(tmp_path / "capacity_snapshot.json")
        # Compute
        ledger = CapacityLedger(snapshot_path=snap_file)
        snapshot1 = ledger.compute()

        # Load
        ledger2 = CapacityLedger(snapshot_path=snap_file)
        snapshot2 = ledger2.get_snapshot()

        # Verify consistency
        assert snapshot1.total_capacity == snapshot2.total_capacity
        assert snapshot1.gap_to_target == snapshot2.gap_to_target

    def test_module_level_function(self, tmp_path, monkeypatch):
        """Test compute_and_print module-level function."""
        snap_file = str(tmp_path / "cap.json")
        monkeypatch.setattr("app.platform.capacity_ledger.get_ledger", lambda: CapacityLedger(snap_file))
        result = compute_and_print()
        assert result is not None
        assert isinstance(result, CapacitySnapshot)
