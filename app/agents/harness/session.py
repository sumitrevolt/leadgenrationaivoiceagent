"""Typed session events + per-run hash-chain (dsh pattern steal, ADR-180).

Harvested from DeepSeek Harness ideas — NOT the TypeScript runtime:
* every control-visible action is a typed SessionEvent
* turn vs step envelope (turn_start / turn_end around the loop)
* append-only hash chain (prev_hash -> event_hash) so replay can detect splice

No ``app.*`` imports (same invariant as ``contracts.py``). The env flag
``HARNESS_SESSION_EVENTS`` is read at call-time here; the audit/loop layers
decide whether to stamp. Default OFF keeps historical JSONL byte-compatible.

Chain is process-local (one dict keyed by run_id). Multi-worker WORM is out of
scope until a durable backend stores the tip hash; do not arm this in prod.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

GENESIS_HASH = "0" * 16

# Existing audit.record kinds -> session event when the caller did not set one.
KIND_TO_EVENT = {
    "step": "tool_result",
    "approval": "tool_call",
    "stop": "turn_end",
    "checkpoint": "step_start",
    "eval": "step_end",
    "shadow": "observe",
    "session": None,  # envelope; extra["session_event"] is authoritative
}


class SessionEventType(str, Enum):
    TURN_START = "turn_start"
    TURN_END = "turn_end"
    STEP_START = "step_start"
    STEP_END = "step_end"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    PRE_STEP_REJECT = "pre_step_reject"
    OBSERVE = "observe"


class SessionEvent(BaseModel):
    """Typed envelope. Stored as extra fields on the existing JSONL row."""

    model_config = ConfigDict(extra="forbid")

    event: SessionEventType
    run_id: str
    seq: int = Field(ge=1)
    prev_hash: str = GENESIS_HASH
    event_hash: str = ""


_CHAINS: dict[str, tuple[int, str]] = {}
_LOCK = threading.Lock()


def session_events_enabled() -> bool:
    """INERT default. Call-time env read (never import-cached)."""
    return os.getenv("HARNESS_SESSION_EVENTS", "0") == "1"


def event_for_kind(kind: str, extra: dict[str, Any] | None = None) -> str | None:
    extra = extra or {}
    explicit = extra.get("session_event")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    mapped = KIND_TO_EVENT.get(kind)
    return mapped


def event_hash(payload: dict[str, Any], prev_hash: str) -> str:
    """SHA-256 prefix of canonical JSON. ``event_hash`` itself is excluded."""
    body = {k: v for k, v in payload.items() if k != "event_hash"}
    body["prev_hash"] = prev_hash
    canonical = json.dumps(body, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def stamp(row: dict[str, Any]) -> dict[str, Any]:
    """Mutate ``row`` with seq / prev_hash / event_hash. Never raises."""
    run_id = str(row.get("run_id") or "")
    with _LOCK:
        seq, prev = _CHAINS.get(run_id, (0, GENESIS_HASH))
        seq += 1
        row["seq"] = seq
        row["prev_hash"] = prev
        h = event_hash(row, prev)
        row["event_hash"] = h
        _CHAINS[run_id] = (seq, h)
    return row


def reset_chain(run_id: str | None = None) -> None:
    """Test helper. Clears one run or the whole process-local chain."""
    with _LOCK:
        if run_id is None:
            _CHAINS.clear()
        else:
            _CHAINS.pop(run_id, None)


def verify_chain(events: list[dict[str, Any]]) -> tuple[bool, str]:
    """Return (ok, reason). Events must already be in seq order for one run."""
    if not events:
        return True, "empty"
    ordered = sorted(events, key=lambda r: int(r.get("seq") or 0))
    prev = GENESIS_HASH
    for i, ev in enumerate(ordered, start=1):
        seq = ev.get("seq")
        if seq != i:
            return False, f"seq gap: expected {i} got {seq}"
        if ev.get("prev_hash") != prev:
            return False, f"prev_hash mismatch at seq={i}"
        expected = event_hash(ev, prev)
        if ev.get("event_hash") != expected:
            return False, f"event_hash mismatch at seq={i}"
        prev = ev["event_hash"]
    return True, "ok"
