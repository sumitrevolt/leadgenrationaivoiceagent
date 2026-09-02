"""
circuit_breaker.py — reusable async circuit breaker for EXTERNAL services.
================================================================================
Recommended in docs/GAP_ANALYSIS_SaaS_Infra_Upgrade_2026.md §3.3: the free_ai LLM
chain has its own escalating-cooldown breaker, but other externals (Pollinations
image-gen, Vobiz, SMTP, Google Maps) have NO breaker — a dead 3rd-party endpoint =
every call waits the full httpx timeout, starving workers during an outage.

Yeh ek chhota, free-stack, per-process breaker hai (CLOSED → OPEN → HALF_OPEN):
  - CLOSED:    requests allow; consecutive failures count.
  - OPEN:      `fail_threshold` failures ke baad — `reset_after_s` tak FAST-FAIL
               (allow()=False) → caller turant fallback le (45s wait nahi).
  - HALF_OPEN: cooldown ke baad ek trial allow; success → CLOSED, fail → OPEN again.

MASTER GATE: env `CIRCUIT_BREAKER` (default OFF). OFF hone pe `allow()` HAMESHA True
return karta — ZERO behaviour change (record_* sirf counters update karte, kabhi trip
nahi karte). Flag ON karne pe hi enforcement chalu hota. Instant rollback = `=0`.

FAIL-SAFE: sab in-memory (per-process; multi-worker = independent breakers, acceptable),
import-safe, kabhi raise nahi karta. Koi naya dependency nahi.

Use:
    from app.infrastructure.circuit_breaker import get_breaker

    br = get_breaker("pollinations_image", fail_threshold=4, reset_after_s=60.0)
    if not br.allow():
        return None                      # OPEN → turant fallback
    try:
        result = await call_external()
        br.record_success()
        return result
    except Exception:
        br.record_failure()
        return None
"""

from __future__ import annotations

import logging
import os
import time

logger = logging.getLogger(__name__)


def enabled() -> bool:
    """Master gate. Default OFF = breakers pass-through (allow() always True)."""
    return (os.getenv("CIRCUIT_BREAKER", "") or "").strip().lower() in {"1", "true", "yes", "on"}


class CircuitBreaker:
    """Per-service breaker. Never raises; cheap; in-memory."""

    __slots__ = (
        "name",
        "fail_threshold",
        "reset_after_s",
        "half_open_max",
        "_fails",
        "_state",
        "_opened_at",
        "_half_calls",
    )

    def __init__(
        self,
        name: str,
        fail_threshold: int = 5,
        reset_after_s: float = 30.0,
        half_open_max: int = 1,
    ) -> None:
        self.name = name
        self.fail_threshold = max(1, int(fail_threshold))
        self.reset_after_s = max(1.0, float(reset_after_s))
        self.half_open_max = max(1, int(half_open_max))
        self._fails = 0
        self._state = "closed"  # closed | open | half_open
        self._opened_at = 0.0
        self._half_calls = 0

    @property
    def state(self) -> str:
        return self._state

    def allow(self) -> bool:
        """True if a request may proceed. When the master gate is OFF, ALWAYS True
        (pass-through). Transitions OPEN→HALF_OPEN once the cooldown elapses."""
        if not enabled():
            return True
        if self._state == "open":
            if (time.monotonic() - self._opened_at) >= self.reset_after_s:
                self._state = "half_open"
                self._half_calls = 0
                logger.info("circuit %s: OPEN → HALF_OPEN (trial)", self.name)
            else:
                return False
        if self._state == "half_open":
            if self._half_calls >= self.half_open_max:
                return False
            self._half_calls += 1
        return True

    def record_success(self) -> None:
        """A real call succeeded — close the breaker, clear failures."""
        self._fails = 0
        if self._state != "closed":
            logger.info("circuit %s: → CLOSED (recovered)", self.name)
        self._state = "closed"
        self._half_calls = 0

    def record_failure(self) -> None:
        """A real call failed — count toward the threshold; trip to OPEN if exceeded.
        Counters update even when the gate is OFF (harmless), so enabling later starts
        from a real picture; tripping only blocks when enabled() (see allow())."""
        self._fails += 1
        if self._state == "half_open" or self._fails >= self.fail_threshold:
            if self._state != "open":
                logger.warning(
                    "circuit %s: → OPEN (%d fails, cooldown %.0fs)",
                    self.name,
                    self._fails,
                    self.reset_after_s,
                )
            self._state = "open"
            self._opened_at = time.monotonic()
            self._half_calls = 0

    def snapshot(self) -> dict:
        """Observability — current state (for /api/growth health surfaces)."""
        return {
            "name": self.name,
            "state": self._state,
            "fails": self._fails,
            "fail_threshold": self.fail_threshold,
            "reset_after_s": self.reset_after_s,
            "enforced": enabled(),
        }


_REGISTRY: dict[str, CircuitBreaker] = {}


def get_breaker(
    name: str, fail_threshold: int = 5, reset_after_s: float = 30.0, half_open_max: int = 1
) -> CircuitBreaker:
    """Process-wide named breaker (lazy). Same name → same instance."""
    br = _REGISTRY.get(name)
    if br is None:
        br = CircuitBreaker(name, fail_threshold, reset_after_s, half_open_max)
        _REGISTRY[name] = br
    return br


def all_breakers() -> list[dict]:
    """Snapshots of every registered breaker (observability)."""
    return [b.snapshot() for b in _REGISTRY.values()]


__all__ = ["CircuitBreaker", "get_breaker", "all_breakers", "enabled"]
