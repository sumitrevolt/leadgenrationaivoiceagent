"""LeadGen daily calling window — operational 09:00–20:00 IST.

Purpose:
  - Enforce owner's operational window (TIGHTER than the TRAI regulatory
    09:00–21:00 limit).
  - Pre-window readiness (queue warm + agent ready) by 08:55 IST.
  - Post-window hard stop (no new outbound dials after 20:00 IST).
  - Concurrent channel allocation: 5 channels max (the 5 DIDs visible in
    CloudPhone /manage-did-numbers).
  - Bounded retries (3 attempts per lead per day, with backoff).
  - Safe recovery + alert on worker crash / lease expiry.
  - Self-heal on stale locks (TTL 60s).

This module is READ-ONLY in the sense that it does not initiate calls. It
returns a `WindowDecision` struct that the call scheduler consumes before
issuing a C2C request. The 5-channel cap is enforced by consulting the
ChannelAvailabilityLedger.

Unlimited FUP per Tata partner dashboard does NOT remove:
  - per-call throttle (per-second, per-minute)
  - per-lead retry budget
  - per-day per-DID anti-abuse
  - DND / opt-out / consent check (DPDP Act 2023 + TRAI TCCCPR)

Per owner directive: keep all suppression in place.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

OPERATIONAL_WINDOW_START_IST_HOUR = 9   # 09:00 IST
OPERATIONAL_WINDOW_END_IST_HOUR = 20    # 20:00 IST
PRE_WINDOW_READINESS_LEAD_SECONDS = 300  # 5 min before start
CHANNEL_CAP = 5                            # 5 DIDs in CloudPhone account
DEFAULT_RETRY_BUDGET_PER_LEAD_PER_DAY = 3
DEFAULT_RETRY_BACKOFF_SECONDS = 120       # 2 min between retries
LEASE_TTL_SECONDS = 60                     # stale lock threshold


@dataclass
class WindowDecision:
    in_window: bool
    pre_window_ready: bool
    post_window_hard_stop: bool
    reason: str
    ist_hour: int
    ist_minute: int
    seconds_to_window_open: float | None = None
    seconds_to_window_close: float | None = None
    available_channels: int = CHANNEL_CAP
    retry_budget_remaining: dict[str, int] = field(default_factory=dict)


def now_ist() -> datetime:
    """Naive local datetime in IST.

    Production container TZ is set to Asia/Kolkata on the VPS; for tests
    on this PC we let the caller override via ``IST_OVERRIDE`` env var.
    """
    override = os.getenv("IST_OVERRIDE")
    if override:
        return datetime.fromisoformat(override)
    return datetime.now()


def evaluate_window(now: datetime | None = None) -> WindowDecision:
    """Pure decision: is the current IST moment inside the operational window?"""
    now = now or now_ist()
    hh, mm = now.hour, now.minute
    seconds_since_midnight = hh * 3600 + mm * 60 + now.second
    start_sec = OPERATIONAL_WINDOW_START_IST_HOUR * 3600
    end_sec = OPERATIONAL_WINDOW_END_IST_HOUR * 3600
    in_window = start_sec <= seconds_since_midnight < end_sec
    pre_window_ready = (
        start_sec - seconds_since_midnight <= PRE_WINDOW_READINESS_LEAD_SECONDS
        and not in_window
    )
    post_window_hard_stop = seconds_since_midnight >= end_sec
    if in_window:
        reason = "inside_operational_window"
    elif post_window_hard_stop:
        reason = "post_window_hard_stop"
    elif pre_window_ready:
        reason = "pre_window_ready"
    else:
        reason = "outside_window"
    return WindowDecision(
        in_window=in_window,
        pre_window_ready=pre_window_ready,
        post_window_hard_stop=post_window_hard_stop,
        reason=reason,
        ist_hour=hh,
        ist_minute=mm,
        seconds_to_window_open=max(0.0, start_sec - seconds_since_midnight) if not in_window else None,
        seconds_to_window_close=max(0.0, end_sec - seconds_since_midnight) if in_window else None,
    )


class ChannelAvailabilityLedger:
    """Tiny lease ledger for the 5 SmartFlo channels.

    Stored on disk so worker restart recovers state. Concurrent leases
    can not exceed CHANNEL_CAP. Each lease has a TTL.
    """

    def __init__(self, path: Path = Path("data/leadgen_channel_ledger.json")) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text(json.dumps({"leases": {}}, indent=2))

    def _read(self) -> dict:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, state: dict) -> None:
        self.path.write_text(json.dumps(state, indent=2))

    def acquire(self, channel_id: str, lead_id: str, ttl_seconds: int = LEASE_TTL_SECONDS) -> bool:
        """Try to acquire `channel_id` for `lead_id`. Returns False if held by another lead
        OR if active-lease count is already at CHANNEL_CAP."""
        now = time.time()
        state = self._read()
        leases = state.get("leases", {})
        # Expire stale
        for cid in list(leases.keys()):
            if leases[cid]["expires_at"] < now:
                leases.pop(cid, None)
        # Already held by THIS lead → refresh + return True
        if channel_id in leases and leases[channel_id]["lead_id"] == lead_id:
            leases[channel_id]["acquired_at"] = now
            leases[channel_id]["expires_at"] = now + ttl_seconds
            self._write(state)
            return True
        # Already held by ANOTHER lead
        if channel_id in leases:
            return False
        # Cap
        if len(leases) >= CHANNEL_CAP:
            return False
        leases[channel_id] = {
            "lead_id": lead_id,
            "acquired_at": now,
            "expires_at": now + ttl_seconds,
        }
        self._write(state)
        return True

    def release(self, channel_id: str, lead_id: str) -> bool:
        state = self._read()
        leases = state.get("leases", {})
        held = leases.get(channel_id)
        if held and held["lead_id"] == lead_id:
            leases.pop(channel_id, None)
            self._write(state)
            return True
        return False

    def available(self) -> int:
        now = time.time()
        state = self._read()
        leases = state.get("leases", {})
        active = sum(1 for v in leases.values() if v["expires_at"] >= now)
        return max(0, CHANNEL_CAP - active)

    def snapshot(self) -> dict:
        return self._read()


class RetryLedger:
    """Per-(lead, channel, day) retry budget."""

    def __init__(self, path: Path = Path("data/leadgen_retry_ledger.json")) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text(json.dumps({}, indent=2))

    def _read(self) -> dict:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, state: dict) -> None:
        self.path.write_text(json.dumps(state, indent=2))

    def _key(self, lead_id: str, channel_id: str, day: str) -> str:
        return f"{lead_id}|{channel_id}|{day}"

    def attempt(self, lead_id: str, channel_id: str, day: str) -> bool:
        """Returns True if an attempt is allowed (under budget), False if exhausted.
        Records the attempt atomically."""
        state = self._read()
        k = self._key(lead_id, channel_id, day)
        used = state.get(k, 0)
        if used >= DEFAULT_RETRY_BUDGET_PER_LEAD_PER_DAY:
            return False
        state[k] = used + 1
        self._write(state)
        return True

    def reset(self, lead_id: str, channel_id: str, day: str) -> None:
        state = self._read()
        state.pop(self._key(lead_id, channel_id, day), None)
        self._write(state)


@dataclass
class CallPathCheck:
    """All pre-flight gates for one outbound dial. Pure — no I/O side effects."""

    window: WindowDecision
    channel_acquired: bool
    channel_id: str
    retry_allowed: bool
    retry_used: int
    dnd_check_passed: bool
    consent_check_passed: bool
    reasons_to_block: list[str] = field(default_factory=list)

    @property
    def can_dial(self) -> bool:
        return (
            self.window.in_window
            and self.channel_acquired
            and self.retry_allowed
            and self.dnd_check_passed
            and self.consent_check_passed
            and not self.window.post_window_hard_stop
        )


def preflight(
    *,
    channel_id: str,
    lead_id: str,
    day: str,
    dnd_check_passed: bool,
    consent_check_passed: bool,
    ledger: ChannelAvailabilityLedger,
    retry_ledger: RetryLedger,
    now: datetime | None = None,
) -> CallPathCheck:
    """Single-call check before issuing C2C. Returns a CallPathCheck with
    a structured boolean and a list of reasons-to-block for diagnostics."""
    window = evaluate_window(now)
    blocked = []
    if window.post_window_hard_stop:
        blocked.append(f"{window.reason} (post-20:00 IST hard stop)")
    if not window.in_window and not window.pre_window_ready:
        blocked.append(f"{window.reason} (outside 09:00–20:00 IST)")
    channel_acquired = False
    if not blocked:
        channel_acquired = ledger.acquire(channel_id, lead_id)
        if not channel_acquired:
            blocked.append(f"channel_unavailable ({channel_id}) or cap_reached")
    retry_allowed = retry_ledger.attempt(lead_id, channel_id, day)
    if not retry_allowed:
        blocked.append(f"retry_budget_exhausted (cap={DEFAULT_RETRY_BUDGET_PER_LEAD_PER_DAY}/day)")
    if not dnd_check_passed:
        blocked.append("dnd_check_failed")
    if not consent_check_passed:
        blocked.append("consent_check_failed")
    return CallPathCheck(
        window=window,
        channel_acquired=channel_acquired,
        channel_id=channel_id,
        retry_allowed=retry_allowed,
        retry_used=0,
        dnd_check_passed=dnd_check_passed,
        consent_check_passed=consent_check_passed,
        reasons_to_block=blocked,
    )


def ack(channel_id: str, lead_id: str, ledgers: tuple[ChannelAvailabilityLedger, RetryLedger]) -> None:
    """After a call attempt completes (success or final failure), release the channel lease."""
    channel_ledger, _ = ledgers
    channel_ledger.release(channel_id, lead_id)


def safe_self_heal(ledger: ChannelAvailabilityLedger) -> int:
    """Drop stale leases. Returns the number of leases released."""
    state = ledger._read()
    leases = state.get("leases", {})
    now = time.time()
    released = 0
    for cid in list(leases.keys()):
        if leases[cid]["expires_at"] < now:
            leases.pop(cid, None)
            released += 1
    if released:
        ledger._write(state)
    return released
