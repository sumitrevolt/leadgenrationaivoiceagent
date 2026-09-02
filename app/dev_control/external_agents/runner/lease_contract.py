"""Lease TTL ↔ heartbeat interval safety contract (PR #147 cycle-6)."""

from __future__ import annotations

import math
import time
from typing import Any

SAFETY_FACTOR = 3
DEFAULT_HEARTBEAT_INTERVAL_S = 25.0
MIN_LEASE_TTL_S = 30


def validate_heartbeat_contract(
    *,
    lease_ttl_s: int | float,
    heartbeat_interval_s: float,
    cancel_poll_s: float | None = None,
) -> dict[str, Any]:
    """Fail-closed config check: interval <= lease_ttl / SAFETY_FACTOR."""
    ttl = float(lease_ttl_s)
    interval = float(heartbeat_interval_s)
    if ttl <= 0 or interval <= 0:
        return {
            "ok": False,
            "reason": "non_positive_ttl_or_interval",
            "lease_ttl_s": ttl,
            "heartbeat_interval_s": interval,
        }
    max_interval = ttl / float(SAFETY_FACTOR)
    if interval > max_interval + 1e-9:
        return {
            "ok": False,
            "reason": "heartbeat_interval_exceeds_lease_safety_ratio",
            "lease_ttl_s": ttl,
            "heartbeat_interval_s": interval,
            "max_interval_s": max_interval,
            "safety_factor": SAFETY_FACTOR,
        }
    if cancel_poll_s is not None and float(cancel_poll_s) > interval + 1e-9:
        return {
            "ok": False,
            "reason": "cancel_poll_exceeds_heartbeat_interval",
            "cancel_poll_s": float(cancel_poll_s),
            "heartbeat_interval_s": interval,
        }
    return {
        "ok": True,
        "lease_ttl_s": ttl,
        "heartbeat_interval_s": interval,
        "max_interval_s": max_interval,
        "safety_factor": SAFETY_FACTOR,
    }


def derive_lease_and_interval(
    exec_timeout_s: int,
    *,
    preferred_interval_s: float = DEFAULT_HEARTBEAT_INTERVAL_S,
) -> dict[str, Any]:
    """Pick a lease TTL and heartbeat interval that satisfy the safety ratio.

    Lease renewal TTL is at least ``max(exec_timeout, preferred*SAFETY_FACTOR, MIN_LEASE)``
    so a fixed ~25s beat remains valid even when wall_timeout floors at 30s.
    """
    preferred = float(preferred_interval_s)
    if preferred <= 0:
        return {"ok": False, "reason": "non_positive_interval"}
    lease_ttl = max(
        MIN_LEASE_TTL_S,
        int(exec_timeout_s or MIN_LEASE_TTL_S),
        int(math.ceil(preferred * SAFETY_FACTOR)),
    )
    interval = min(preferred, lease_ttl / float(SAFETY_FACTOR))
    check = validate_heartbeat_contract(lease_ttl_s=lease_ttl, heartbeat_interval_s=interval)
    if not check.get("ok"):
        return check
    return {
        "ok": True,
        "lease_ttl_s": int(lease_ttl),
        "heartbeat_interval_s": float(interval),
        "contract": check,
        "monotonic_clock": "time.monotonic",
    }


class HeartbeatWatch:
    """Monotonic delayed-heartbeat detector (no wall-clock dependence)."""

    def __init__(self, interval_s: float, *, grace_factor: float = 2.0) -> None:
        self.interval_s = float(interval_s)
        self.grace_s = float(interval_s) * float(grace_factor)
        self._last_ok = time.monotonic()
        self.delayed = False

    def mark_ok(self) -> None:
        self._last_ok = time.monotonic()
        self.delayed = False

    def check(self) -> bool:
        """Return True when still within grace; False if delayed."""
        elapsed = time.monotonic() - self._last_ok
        if elapsed > self.grace_s:
            self.delayed = True
            return False
        return True
