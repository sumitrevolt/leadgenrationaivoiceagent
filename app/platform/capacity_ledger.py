"""Capacity Ledger — single source for channel caps + gap computation (M2, P1).

WHY THIS EXISTS
---------------
ARCH §M2: Contact capacity ~875/week vs required ~85,000/week = **97× gap**.
This module computes the gap honestly and exposes capacity dials so owner
can measure + scale (new human channels) without touching compliance.

Design:
* Reads channel caps from env vars + existing flags
* Computes weekly capacity per channel (email, voice, WhatsApp)
* Aggregates total capacity + gap-to-target
* Writes `data/capacity_snapshot.json` (consumed by M5 KPI tracking)
* Never raises — returns zeroes if env vars missing

Evidence label: CODE-PRESENT (stub, needs wiring to auto_outreach.py)
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Target: 85,000 contacts/week for ₹1 Cr/month
TARGET_WEEKLY_CONTACTS = 85000

# Default caps (from env vars or hardcoded defaults)
DEFAULT_EMAIL_CAP_PER_DAY = 25
DEFAULT_VOICE_DAILY_LIMIT = 100
DEFAULT_WHATSAPP_CAP_PER_DAY = 0  # cold WhatsApp OFF by design


class CapacitySnapshot:
    """Weekly capacity snapshot — consumed by M5 KPI tracking."""

    def __init__(
        self,
        email_capacity: int,
        voice_capacity: int,
        whatsapp_capacity: int,
        total_capacity: int,
        gap_to_target: int,
        utilization: float,
        blocked_by_compliance: int,
    ):
        self.email_capacity = email_capacity
        self.voice_capacity = voice_capacity
        self.whatsapp_capacity = whatsapp_capacity
        self.total_capacity = total_capacity
        self.gap_to_target = gap_to_target
        self.utilization = utilization  # 0.0–1.0
        self.blocked_by_compliance = blocked_by_compliance
        self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "email_capacity": self.email_capacity,
            "voice_capacity": self.voice_capacity,
            "whatsapp_capacity": self.whatsapp_capacity,
            "total_capacity": self.total_capacity,
            "target_capacity": TARGET_WEEKLY_CONTACTS,
            "gap_to_target": self.gap_to_target,
            "utilization": self.utilization,
            "blocked_by_compliance": self.blocked_by_compliance,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CapacitySnapshot":
        return cls(
            email_capacity=data["email_capacity"],
            voice_capacity=data["voice_capacity"],
            whatsapp_capacity=data["whatsapp_capacity"],
            total_capacity=data["total_capacity"],
            gap_to_target=data["gap_to_target"],
            utilization=data["utilization"],
            blocked_by_compliance=data["blocked_by_compliance"],
        )


class CapacityLedger:
    """Computes and persists weekly capacity snapshot."""

    def __init__(self, snapshot_path: str = "data/capacity_snapshot.json"):
        self.snapshot_path = snapshot_path
        self.snapshot: Optional[CapacitySnapshot] = None
        self._load()

    def _load(self):
        """Load existing snapshot (if exists)."""
        if not os.path.exists(self.snapshot_path):
            return
        try:
            with open(self.snapshot_path, "r") as f:
                data = json.load(f)
                self.snapshot = CapacitySnapshot.from_dict(data)
        except Exception as e:
            logger.warning(f"[capacity_ledger] Failed to load snapshot: {e}")

    def _save(self):
        """Persist snapshot to disk."""
        if self.snapshot is None:
            return
        try:
            os.makedirs(os.path.dirname(self.snapshot_path), exist_ok=True)
            with open(self.snapshot_path, "w") as f:
                json.dump(self.snapshot.to_dict(), f, indent=2)
        except Exception as e:
            logger.warning(f"[capacity_ledger] Failed to save snapshot: {e}")

    def compute(self) -> CapacitySnapshot:
        """Compute capacity from env vars + existing flags.

        Reads:
        * EMAIL_OUTREACH_CAP (default: 25/day)
        * PLATFORM_DIAL_LIMIT (default: 100/day)
        * SALES_AUTOPILOT_WHATSAPP_ENABLED (default: OFF = 0)
        """
        # Email capacity
        email_cap_env = os.environ.get("EMAIL_OUTREACH_CAP", str(DEFAULT_EMAIL_CAP_PER_DAY))
        try:
            email_daily = int(email_cap_env)
        except ValueError:
            email_daily = DEFAULT_EMAIL_CAP_PER_DAY
        email_weekly = email_daily * 7

        # Voice capacity
        voice_daily_env = os.environ.get("PLATFORM_DIAL_LIMIT", str(DEFAULT_VOICE_DAILY_LIMIT))
        try:
            voice_daily = int(voice_daily_env)
        except ValueError:
            voice_daily = DEFAULT_VOICE_DAILY_LIMIT
        voice_weekly = voice_daily * 7

        # WhatsApp capacity (cold = OFF by design)
        whatsapp_enabled = os.environ.get("SALES_AUTOPILOT_WHATSAPP_ENABLED", "0")
        whatsapp_weekly = 0 if whatsapp_enabled != "1" else 1000  # placeholder if enabled

        # Total capacity
        total_weekly = email_weekly + voice_weekly + whatsapp_weekly

        # Gap to target
        gap = max(0, TARGET_WEEKLY_CONTACTS - total_weekly)

        # Utilization (assume 50% baseline if no live metrics)
        utilization = min(1.0, total_weekly / TARGET_WEEKLY_CONTACTS) if TARGET_WEEKLY_CONTACTS > 0 else 0.0

        # Blocked by compliance (voice window 09:00-19:00 IST = ~50% effective)
        blocked_by_compliance = int(voice_weekly * 0.5)  # conservative estimate

        self.snapshot = CapacitySnapshot(
            email_capacity=email_weekly,
            voice_capacity=voice_weekly,
            whatsapp_capacity=whatsapp_weekly,
            total_capacity=total_weekly,
            gap_to_target=gap,
            utilization=utilization,
            blocked_by_compliance=blocked_by_compliance,
        )
        self._save()
        return self.snapshot

    def get_snapshot(self) -> Optional[CapacitySnapshot]:
        """Get last computed snapshot (or None if not computed yet)."""
        return self.snapshot

    def print_status(self):
        """Print human-readable capacity status."""
        snapshot = self.compute()
        print(f"\n{'='*60}")
        print(f"  CAPACITY SNAPSHOT (weekly)")
        print(f"{'='*60}")
        print(f"  Email:    {snapshot.email_capacity:6,d} contacts/week")
        print(f"  Voice:    {snapshot.voice_capacity:6,d} contacts/week")
        print(f"  WhatsApp: {snapshot.whatsapp_capacity:6,d} contacts/week")
        print(f"  {'─'*50}")
        print(f"  Total:    {snapshot.total_capacity:6,d} contacts/week")
        print(f"  Target:   {TARGET_WEEKLY_CONTACTS:6,d} contacts/week")
        print(f"  Gap:      {snapshot.gap_to_target:6,d} contacts/week ({snapshot.gap_to_target/TARGET_WEEKLY_CONTACTS*100:.1f}%)")
        print(f"  Utilization: {snapshot.utilization*100:.1f}%")
        print(f"  Blocked by compliance: {snapshot.blocked_by_compliance:,d}")
        print(f"{'='*60}\n")


# Module-level singleton
_ledger: Optional[CapacityLedger] = None


def get_ledger() -> CapacityLedger:
    """Get or create singleton CapacityLedger."""
    global _ledger
    if _ledger is None:
        _ledger = CapacityLedger()
    return _ledger


def compute_and_print():
    """Convenience: compute + print status."""
    ledger = get_ledger()
    ledger.print_status()
    return ledger.get_snapshot()


__all__ = [
    "CapacitySnapshot",
    "CapacityLedger",
    "get_ledger",
    "compute_and_print",
    "TARGET_WEEKLY_CONTACTS",
]
