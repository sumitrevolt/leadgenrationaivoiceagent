"""Authoritative video workflow state machine.

Legacy video_ad_cycle statuses (pending/approved/published/…) remain the
storage keys. ``workflow_state`` is the richer enterprise machine required by
the OpenClaw Daily Video Production Cell. Transitions are fail-closed.
"""

from __future__ import annotations

from typing import Any

# Primary flow
PLANNED = "PLANNED"
BRIEF_CREATED = "BRIEF_CREATED"
SCRIPT_CREATED = "SCRIPT_CREATED"
STORYBOARD_CREATED = "STORYBOARD_CREATED"
ASSETS_READY = "ASSETS_READY"
RENDERING = "RENDERING"
RENDERED = "RENDERED"
INTERNAL_QA = "INTERNAL_QA"
CLIENT_REVIEW_PENDING = "CLIENT_REVIEW_PENDING"
CHANGES_REQUESTED = "CHANGES_REQUESTED"
REVISING = "REVISING"
APPROVED = "APPROVED"
SCHEDULED = "SCHEDULED"
PUBLISHED = "PUBLISHED"
VERIFIED = "VERIFIED"

# Exception / terminal
INTERNAL_QA_FAILED = "INTERNAL_QA_FAILED"
CLIENT_REJECTED = "CLIENT_REJECTED"
APPROVAL_EXPIRED = "APPROVAL_EXPIRED"
RENDER_FAILED = "RENDER_FAILED"
DELIVERY_FAILED = "DELIVERY_FAILED"
PUBLISH_FAILED = "PUBLISH_FAILED"
CANCELLED = "CANCELLED"
SUPERSEDED = "SUPERSEDED"

_ALLOWED: dict[str, set[str]] = {
    PLANNED: {BRIEF_CREATED, CANCELLED},
    BRIEF_CREATED: {SCRIPT_CREATED, CANCELLED},
    SCRIPT_CREATED: {STORYBOARD_CREATED, CANCELLED},
    STORYBOARD_CREATED: {ASSETS_READY, CANCELLED},
    ASSETS_READY: {RENDERING, CANCELLED},
    RENDERING: {RENDERED, RENDER_FAILED, CANCELLED},
    RENDERED: {INTERNAL_QA, CANCELLED},
    INTERNAL_QA: {CLIENT_REVIEW_PENDING, INTERNAL_QA_FAILED, CANCELLED},
    INTERNAL_QA_FAILED: {RENDERING, CANCELLED},
    CLIENT_REVIEW_PENDING: {
        APPROVED,
        CHANGES_REQUESTED,
        CLIENT_REJECTED,
        APPROVAL_EXPIRED,
        CANCELLED,
    },
    CHANGES_REQUESTED: {REVISING, CANCELLED},
    REVISING: {RENDERING, CANCELLED},
    APPROVED: {SCHEDULED, PUBLISHED, CANCELLED},
    SCHEDULED: {PUBLISHED, PUBLISH_FAILED, CANCELLED},
    PUBLISHED: {VERIFIED, PUBLISH_FAILED},
    VERIFIED: set(),
    CLIENT_REJECTED: {CANCELLED},
    APPROVAL_EXPIRED: {CANCELLED, CLIENT_REVIEW_PENDING},
    RENDER_FAILED: {RENDERING, CANCELLED},
    DELIVERY_FAILED: {CLIENT_REVIEW_PENDING, CANCELLED},
    PUBLISH_FAILED: {SCHEDULED, APPROVED, CANCELLED},
    CANCELLED: set(),
    SUPERSEDED: set(),
}

# Map legacy status → default workflow_state
_LEGACY_TO_WF = {
    "pending": CLIENT_REVIEW_PENDING,
    "approved": APPROVED,
    "published": PUBLISHED,
    "publish_failed": PUBLISH_FAILED,
    "changes_requested": CHANGES_REQUESTED,
    "failed": RENDER_FAILED,
    "held_max_revisions": CANCELLED,
    "superseded": SUPERSEDED,
}

# States from which publishing is FORBIDDEN
_NO_PUBLISH = frozenset(
    {
        CLIENT_REVIEW_PENDING,
        CHANGES_REQUESTED,
        CLIENT_REJECTED,
        REVISING,
        RENDERING,
        RENDERED,
        INTERNAL_QA,
        INTERNAL_QA_FAILED,
        RENDER_FAILED,
        PLANNED,
        BRIEF_CREATED,
        SCRIPT_CREATED,
        STORYBOARD_CREATED,
        ASSETS_READY,
        CANCELLED,
        SUPERSEDED,
        APPROVAL_EXPIRED,
        DELIVERY_FAILED,
    }
)


def can_transition(current: str, new: str) -> bool:
    cur = (current or PLANNED).upper()
    nxt = (new or "").upper()
    if cur == nxt:
        return True
    allowed = _ALLOWED.get(cur)
    if allowed is None:
        return False
    return nxt in allowed


def transition(rec: dict[str, Any], new_state: str) -> dict[str, Any]:
    """Return patch fields for a legal transition, or error dict."""
    cur = str(rec.get("workflow_state") or _LEGACY_TO_WF.get(str(rec.get("status") or ""), PLANNED))
    nxt = (new_state or "").upper()
    if not can_transition(cur, nxt):
        return {"ok": False, "error": "illegal_transition", "from": cur, "to": nxt}
    return {
        "ok": True,
        "workflow_state": nxt,
        "previous_workflow_state": cur,
    }


def workflow_from_legacy(status: str) -> str:
    return _LEGACY_TO_WF.get(str(status or "").lower(), PLANNED)


def publish_allowed(rec: dict[str, Any]) -> tuple[bool, str]:
    """Fail-closed: only APPROVED/SCHEDULED (or legacy approved) may publish."""
    wf = str(rec.get("workflow_state") or "").upper()
    if not wf:
        wf = workflow_from_legacy(str(rec.get("status") or ""))
    if wf in _NO_PUBLISH:
        return False, f"publish_blocked:{wf}"
    if wf not in (APPROVED, SCHEDULED, PUBLISHED):
        # PUBLISHED already done — idempotent skip handled by caller
        if str(rec.get("status") or "") == "approved":
            return True, "legacy_approved"
        return False, f"publish_blocked:{wf or 'unknown'}"
    if not str(rec.get("approval_id") or "").strip():
        return False, "missing_approval_id"
    if not str(rec.get("video_path") or "").strip():
        return False, "missing_video_path"
    return True, "ok"


__all__ = [
    "PLANNED",
    "BRIEF_CREATED",
    "SCRIPT_CREATED",
    "STORYBOARD_CREATED",
    "ASSETS_READY",
    "RENDERING",
    "RENDERED",
    "INTERNAL_QA",
    "CLIENT_REVIEW_PENDING",
    "CHANGES_REQUESTED",
    "REVISING",
    "APPROVED",
    "SCHEDULED",
    "PUBLISHED",
    "VERIFIED",
    "INTERNAL_QA_FAILED",
    "CLIENT_REJECTED",
    "APPROVAL_EXPIRED",
    "RENDER_FAILED",
    "DELIVERY_FAILED",
    "PUBLISH_FAILED",
    "CANCELLED",
    "SUPERSEDED",
    "can_transition",
    "transition",
    "workflow_from_legacy",
    "publish_allowed",
]
