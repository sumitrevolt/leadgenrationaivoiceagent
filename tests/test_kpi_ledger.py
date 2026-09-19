"""Tests for kpi_ledger.py â€” verified vs claimed metrics (M5, P4).

Run: pytest tests/test_kpi_ledger.py -v
"""

import json
import os
import tempfile
from pathlib import Path

import pytest

from app.platform.kpi_ledger import KpiLedger, KpiRecord, get_ledger, record_kpi, compute_and_print


class TestKpiRecord:
    """Test KpiRecord dataclass."""

    def test_creation_verified(self):
        """Test creating verified record."""
        record = KpiRecord(
            metric_name="paid_today",
            value=5.0,
            verified=True,
            evidence="data/invoices.jsonl",
            source="billing"
        )
        assert record.metric_name == "paid_today"
        assert record.verified is True
        assert record.evidence == "data/invoices.jsonl"
        assert record.ts is not None

    def test_creation_unverified(self):
        """Test creating unverified record."""
        record = KpiRecord(
            metric_name="estimated_revenue",
            value=100000.0,
            verified=False,
            evidence="",
            source="inference"
        )
        assert record.verified is False
        assert record.evidence == ""

    def test_to_dict(self):
        """Test serialization."""
        record = KpiRecord(
            metric_name="test_metric",
            value=42.0,
            verified=True,
            evidence="test_evidence",
            tags={"env": "test"}
        )
        data = record.to_dict()
        assert data["metric"] == "test_metric"
        assert data["value"] == 42.0
        assert data["verified"] is True
        assert "ts" in data

    def test_from_dict(self):
        """Test deserialization."""
        data = {
            "ts": "2026-09-17T00:00:00Z",
            "metric": "test",
            "value": 100.0,
            "verified": True,
            "evidence": "ev.txt",
            "source": "test",
            "tags": {"key": "value"}
        }
        record = KpiRecord.from_dict(data)
        assert record.metric_name == "test"
        assert record.value == 100.0
        assert record.tags == {"key": "value"}

    def test_repr(self):
        """Test string representation."""
        record = KpiRecord("metric", 10.0, True, "evidence")
        repr_str = repr(record)
        assert "metric" in repr_str
        assert "\u2713" in repr_str  # verified indicator

        record2 = KpiRecord("metric", 10.0, False, "")
        repr_str2 = repr(record2)
        assert "\u2717" in repr_str2  # unverified indicator


@pytest.fixture
def tmp_path(tmp_path):
    """Create temp ledger file."""
    ledger_file = tmp_path / "kpi_ledger.jsonl"
    return str(ledger_file)


class TestKpiLedger:
    """Test KpiLedger class."""

    def test_record_verified(self, tmp_path):
        """Test recording verified KPI."""
        ledger = KpiLedger(ledger_path=tmp_path)
        ledger.record("paid_today", 5.0, True, "data/invoices.jsonl", "billing")

        records = ledger.get_all("paid_today")
        assert len(records) == 1
        assert records[0].verified is True
        assert records[0].value == 5.0

    def test_record_unverified(self, tmp_path):
        """Test recording unverified KPI."""
        ledger = KpiLedger(ledger_path=tmp_path)
        ledger.record("estimated_revenue", 100000.0, False, "", "inference")

        records = ledger.get_all("estimated_revenue")
        assert len(records) == 1
        assert records[0].verified is False

    def test_separation_verified_vs_unverified(self, tmp_path):
        """Test that verified and unverified are kept separate."""
        ledger = KpiLedger(ledger_path=tmp_path)

        # Record both types
        ledger.record("revenue", 1000.0, True, "invoices.jsonl", "billing")
        ledger.record("revenue", 500.0, False, "", "estimate")

        # Query separately
        verified = ledger.get_verified("revenue")
        unverified = ledger.get_unverified("revenue")

        assert len(verified) == 1
        assert len(unverified) == 1
        assert verified[0].value == 1000.0
        assert unverified[0].value == 500.0

    def test_persistence(self, tmp_path):
        """Test that records persist to disk."""
        ledger = KpiLedger(ledger_path=tmp_path)
        ledger.record("test_metric", 42.0, True, "test_evidence")

        # Verify file created
        assert os.path.exists(tmp_path)

        # Verify content
        with open(tmp_path, "r") as f:
            line = f.readline()
            data = json.loads(line)
        assert data["metric"] == "test_metric"
        assert data["value"] == 42.0
        assert data["verified"] is True

    def test_load_existing(self, tmp_path):
        """Test loading existing records."""
        # Create and save
        ledger1 = KpiLedger(ledger_path=tmp_path)
        ledger1.record("metric1", 100.0, True, "ev1")
        ledger1.record("metric2", 200.0, False, "")

        # Load in new instance
        ledger2 = KpiLedger(ledger_path=tmp_path)
        records = ledger2.get_all()
        assert len(records) == 2

    def test_get_summary(self, tmp_path):
        """Test summary computation."""
        ledger = KpiLedger(ledger_path=tmp_path)

        # Record multiple metrics
        ledger.record("paid_today", 5.0, True, "invoices")
        ledger.record("paid_today", 3.0, True, "invoices")
        ledger.record("paid_today", 10.0, False, "")
        ledger.record("revenue", 10000.0, True, "billing")

        summary = ledger.get_summary()
        assert "paid_today" in summary
        assert summary["paid_today"]["verified"] == 2
        assert summary["paid_today"]["unverified"] == 1
        assert summary["revenue"]["verified"] == 1

    def test_print_status(self, tmp_path, capsys):
        """Test status printing."""
        ledger = KpiLedger(ledger_path=tmp_path)
        ledger.record("test_metric", 100.0, True, "evidence")
        ledger.print_status()

        captured = capsys.readouterr()
        assert "KPI LEDGER" in captured.out
        assert "test_metric" in captured.out


class TestTraceability:
    """Test evidence traceability (core requirement)."""

    def test_evidence_required_for_verified(self, tmp_path):
        """Test that verified records should have evidence."""
        ledger = KpiLedger(ledger_path=tmp_path)

        # Good: verified with evidence
        ledger.record("good_metric", 100.0, True, "data/source.json")

        # Bad: verified without evidence (should still work, but flag it)
        ledger.record("risky_metric", 200.0, True, "")

        records = ledger.get_all()
        assert len(records) == 2

        # First in get_all is the most recent (risky_metric), second is good_metric
        good = next(r for r in records if r.metric_name == "good_metric")
        risky = next(r for r in records if r.metric_name == "risky_metric")
        assert good.evidence == "data/source.json"
        assert risky.evidence == ""

    def test_source_tracking(self, tmp_path):
        """Test that source is tracked for audit."""
        ledger = KpiLedger(ledger_path=tmp_path)

        ledger.record("metric", 100.0, True, "evidence", "billing_module")
        ledger.record("metric2", 200.0, True, "evidence2", "outreach_module")

        records = ledger.get_all()
        sources = [r.source for r in records]
        assert "billing_module" in sources
        assert "outreach_module" in sources


class TestIntegration:
    """Integration tests."""

    def test_end_to_end_workflow(self, tmp_path):
        """Test full workflow: record â†’ query â†’ summary."""
        ledger = KpiLedger(ledger_path=tmp_path)

        # Record KPIs
        ledger.record("paid_today", 5.0, True, "invoices.jsonl", "billing")
        ledger.record("paid_today", 3.0, True, "invoices.jsonl", "billing")
        ledger.record("paid_today", 10.0, False, "", "estimate")

        # Query
        verified = ledger.get_verified("paid_today")
        unverified = ledger.get_unverified("paid_today")
        summary = ledger.get_summary()

        # Verify
        assert len(verified) == 2
        assert len(unverified) == 1
        assert summary["paid_today"]["verified"] == 2
        assert summary["paid_today"]["unverified"] == 1

    def test_module_level_function(self, tmp_path, monkeypatch):
        """Test record_kpi module-level function."""
        monkeypatch.setattr("app.platform.kpi_ledger.get_ledger", lambda: KpiLedger(tmp_path))
        record_kpi("test", 42.0, True, "evidence")

        ledger = KpiLedger(ledger_path=tmp_path)
        records = ledger.get_all("test")
        assert len(records) == 1
        assert records[0].value == 42.0


