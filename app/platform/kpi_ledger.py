"""KPI Ledger — verified metrics with evidence (M5, P4).

WHY THIS EXISTS
---------------
ARCH §M5: KPI design must separate `claimed` vs `verified` metrics.
Blend = bug. This module provides `KpiRecord` schema with `verified: bool`
+ `evidence` field for traceability.

Design:
* KpiRecord: verified bool + evidence string + metric value
* Never blends claimed into verified
* Writes to `data/kpi_ledger.jsonl` (append-only)
* Provides query functions for dashboard

Evidence label: CODE-PRESENT (stub, needs wiring to existing dashboards)
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Ledger path
LEDGER_PATH = "data/kpi_ledger.jsonl"


class KpiRecord:
    """Verified KPI record — traceable to evidence."""

    def __init__(
        self,
        metric_name: str,
        value: float,
        verified: bool,
        evidence: str = "",
        source: str = "",
        tags: dict[str, str] | None = None,
    ):
        self.metric_name = metric_name
        self.value = value
        self.verified = verified
        self.evidence = evidence
        self.source = source
        self.tags = tags or {}
        self.ts = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "ts": self.ts,
            "metric": self.metric_name,
            "value": self.value,
            "verified": self.verified,
            "evidence": self.evidence,
            "source": self.source,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> KpiRecord:
        return cls(
            metric_name=data["metric"],
            value=data["value"],
            verified=data.get("verified", False),
            evidence=data.get("evidence", ""),
            source=data.get("source", ""),
            tags=data.get("tags", {}),
        )

    def __repr__(self):
        status = "✓" if self.verified else "✗"
        return f"KpiRecord({self.metric_name}={self.value} {status} evid={self.evidence[:30]})"


class KpiLedger:
    """Append-only KPI ledger with verified/unverified separation."""

    def __init__(self, ledger_path: str = LEDGER_PATH):
        self.ledger_path = ledger_path
        self._cache: list[KpiRecord] = []
        self._load()

    def _load(self):
        """Load existing records (last 1000 for memory)."""
        if not os.path.exists(self.ledger_path):
            return
        try:
            with open(self.ledger_path) as f:
                lines = f.readlines()
                for line in lines[-1000:]:  # last 1000 records
                    line = line.strip()
                    if line:
                        try:
                            data = json.loads(line)
                            self._cache.append(KpiRecord.from_dict(data))
                        except json.JSONDecodeError:
                            logger.warning(f"[kpi_ledger] Skipped malformed line: {line[:80]}")
        except Exception as e:
            logger.warning(f"[kpi_ledger] Failed to load ledger: {e}")

    def _append(self, record: KpiRecord):
        """Append record to in-memory cache + disk."""
        self._cache.append(record)
        try:
            os.makedirs(os.path.dirname(self.ledger_path), exist_ok=True)
            with open(self.ledger_path, "a") as f:
                f.write(json.dumps(record.to_dict()) + "\n")
        except Exception as e:
            logger.warning(f"[kpi_ledger] Failed to append record: {e}")

    def record(
        self,
        metric_name: str,
        value: float,
        verified: bool,
        evidence: str = "",
        source: str = "",
        tags: dict[str, str] | None = None,
    ):
        """Record a KPI metric (verified or unverified)."""
        record = KpiRecord(
            metric_name=metric_name,
            value=value,
            verified=verified,
            evidence=evidence,
            source=source,
            tags=tags,
        )
        self._append(record)
        logger.info(f"[kpi_ledger] Recorded: {record}")

    def get_verified(self, metric_name: str, limit: int = 10) -> list[KpiRecord]:
        """Get recent verified records for a metric."""
        return [
            r for r in self._cache[::-1]
            if r.metric_name == metric_name and r.verified
        ][:limit]

    def get_unverified(self, metric_name: str, limit: int = 10) -> list[KpiRecord]:
        """Get recent unverified records for a metric."""
        return [
            r for r in self._cache[::-1]
            if r.metric_name == metric_name and not r.verified
        ][:limit]

    def get_all(self, metric_name: str | None = None, limit: int = 100) -> list[KpiRecord]:
        """Get recent records (optionally filtered by metric)."""
        records = self._cache[::-1]
        if metric_name:
            records = [r for r in records if r.metric_name == metric_name]
        return records[:limit]

    def get_summary(self) -> dict[str, dict[str, int]]:
        """Get summary counts: {metric: {verified: N, unverified: N}}."""
        summary: dict[str, dict[str, int]] = {}
        for record in self._cache:
            if record.metric_name not in summary:
                summary[record.metric_name] = {"verified": 0, "unverified": 0}
            if record.verified:
                summary[record.metric_name]["verified"] += 1
            else:
                summary[record.metric_name]["unverified"] += 1
        return summary

    def print_status(self):
        """Print human-readable KPI status."""
        summary = self.get_summary()
        print(f"\n{'='*60}")
        print("  KPI LEDGER STATUS")
        print(f"{'='*60}")
        if not summary:
            print("  No KPI records yet.")
        else:
            for metric, counts in sorted(summary.items()):
                total = counts["verified"] + counts["unverified"]
                verified_pct = counts["verified"] / total * 100 if total > 0 else 0
                print(f"  {metric:30s} ✓{counts['verified']:4d}  ✗{counts['unverified']:4d}  ({verified_pct:.0f}% verified)")
        print(f"{'='*60}\n")


# Module-level singleton
_ledger: KpiLedger | None = None


def get_ledger() -> KpiLedger:
    """Get or create singleton KpiLedger."""
    global _ledger
    if _ledger is None:
        _ledger = KpiLedger()
    return _ledger


def record_kpi(
    metric_name: str,
    value: float,
    verified: bool,
    evidence: str = "",
    source: str = "",
    tags: dict[str, str] | None = None,
):
    """Convenience function to record a KPI."""
    ledger = get_ledger()
    ledger.record(metric_name, value, verified, evidence, source, tags)


def compute_and_print():
    """Convenience: print KPI status."""
    ledger = get_ledger()
    ledger.print_status()
    return ledger.get_summary()


__all__ = [
    "KpiRecord",
    "KpiLedger",
    "get_ledger",
    "record_kpi",
    "compute_and_print",
]
