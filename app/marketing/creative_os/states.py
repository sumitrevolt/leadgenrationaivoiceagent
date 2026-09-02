"""Explicit Creative OS lifecycle transitions — fail-closed."""

from __future__ import annotations

from typing import Any

ALLOWED: dict[str, frozenset[str]] = {
    "queued": frozenset({"generating", "failed", "quarantined"}),
    "generating": frozenset({"qa_failed", "approval_pending", "failed", "quarantined"}),
    "qa_failed": frozenset({"queued", "quarantined", "failed"}),
    "approval_pending": frozenset({"approved", "changes_requested", "quarantined"}),
    "approved": frozenset({"changes_requested", "scheduled", "quarantined"}),
    "changes_requested": frozenset({"queued", "quarantined"}),
    "scheduled": frozenset({"published", "failed", "quarantined"}),
    "published": frozenset({"quarantined"}),
    "failed": frozenset({"queued", "quarantined"}),
    "quarantined": frozenset(),
}

APPROVABLE = frozenset({"approval_pending"})
CHANGEABLE = frozenset({"approval_pending", "approved", "qa_failed"})


def can_transition(current: str, new: str) -> bool:
    cur = (current or "").strip().lower()
    nxt = (new or "").strip().lower()
    if cur == nxt:
        return True
    return nxt in ALLOWED.get(cur, frozenset())


def assert_transition(current: str, new: str) -> dict[str, Any]:
    if can_transition(current, new):
        return {"ok": True, "from": current, "to": new}
    return {
        "ok": False,
        "error": "invalid_transition",
        "from": current,
        "to": new,
    }


__all__ = [
    "ALLOWED",
    "APPROVABLE",
    "CHANGEABLE",
    "assert_transition",
    "can_transition",
]
