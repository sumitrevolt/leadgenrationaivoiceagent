"""Loop-social-7 (2026-07-11): extended content_approval state machine.

Contract:
- Extended states: pending, ready_for_review, changes_requested, approved,
  rejected, scheduled, publishing, published, partially_published, cancelled.
- `transition(approval_id, new_status, actor, note, extra)` enforces
  `_ALLOWED_TRANSITIONS` — illegal moves refused with `illegal_transition`.
- `cancel(id)` / `request_changes(id)` are sugar over `transition()`.
- Every legal transition appends a JSONL row (audit trail) + emits the mapped
  canonical delivery-ledger event.
- Legacy 3-state `_STATUSES` (`pending/approved/rejected`) still works — old
  `approve()`/`reject()` unchanged.
- Terminal states (published, cancelled) refuse further transitions.
"""

from __future__ import annotations

import os
import tempfile

import pytest


@pytest.fixture()
def ca(monkeypatch):
    """Isolated JSONL store — every test starts empty."""
    from app.marketing import content_approval as _ca

    td = tempfile.mkdtemp()
    monkeypatch.setattr(_ca, "_FILE", lambda: os.path.join(td, "content_approvals.jsonl"))
    return _ca


def _submit(ca, cid="clientA") -> str:
    rec = ca.submit(cid, {"title": "Test", "caption": "hi"})
    assert rec.get("ok"), rec
    return rec["approval"]["id"]


# --------------------------------------------------------------------------- #
# Enum + transitions basics                                                    #
# --------------------------------------------------------------------------- #
def test_extended_status_set_contains_all_canonical_states(ca):
    for s in (
        "pending",
        "ready_for_review",
        "changes_requested",
        "approved",
        "rejected",
        "scheduled",
        "publishing",
        "published",
        "partially_published",
        "cancelled",
    ):
        assert s in ca._EXTENDED_STATUSES


def test_transition_refuses_unknown_state(ca):
    aid = _submit(ca)
    r = ca.transition(aid, "MOON_MODE")
    assert r["ok"] is False
    assert r["error"] == "invalid_status"


def test_transition_refuses_unknown_approval(ca):
    r = ca.transition("does_not_exist", "cancelled")
    assert r["ok"] is False
    assert r["error"] == "approval_not_found"


def test_pending_to_approved_ok(ca):
    aid = _submit(ca)
    r = ca.transition(aid, "approved", actor="customer", note="looks good")
    assert r["ok"] is True
    assert r["from"] == "pending"
    assert r["to"] == "approved"
    assert r["approval"]["status"] == "approved"


def test_illegal_direct_pending_to_publishing(ca):
    """`publishing` requires `approved` / `scheduled` first."""
    aid = _submit(ca)
    r = ca.transition(aid, "publishing")
    assert r["ok"] is False
    assert r["error"] == "illegal_transition"
    assert r["from"] == "pending"


def test_full_happy_path_approved_scheduled_publishing_published(ca):
    aid = _submit(ca)
    assert ca.transition(aid, "approved")["ok"]
    assert ca.transition(aid, "scheduled", extra={"scheduled_time": "2026-07-12T10:00"})["ok"]
    assert ca.transition(aid, "publishing")["ok"]
    assert ca.transition(aid, "published")["ok"]


def test_published_is_terminal(ca):
    aid = _submit(ca)
    for s in ("approved", "publishing", "published"):
        assert ca.transition(aid, s)["ok"], f"failed at {s}"
    r = ca.transition(aid, "publishing")
    assert r["ok"] is False
    assert r["error"] == "illegal_transition"


def test_cancelled_is_terminal_and_ledger_emits(ca, monkeypatch):
    """cancel() sugar + delivery_ledger.log_event('post_cancelled') emit."""
    from app.marketing import delivery_ledger

    captured: list[tuple[str, str]] = []
    monkeypatch.setattr(
        delivery_ledger,
        "log_event",
        lambda cid, ev, detail="", **kw: captured.append((cid, ev)),
    )
    aid = _submit(ca, cid="clientA")
    r = ca.cancel(aid, actor="customer", note="changed my mind")
    assert r["ok"] is True
    assert r["to"] == "cancelled"
    # Cancelled is terminal.
    r2 = ca.transition(aid, "publishing")
    assert r2["ok"] is False
    # Ledger emitted the canonical event.
    assert ("clientA", "post_cancelled") in captured


def test_partially_published_can_recover_to_publishing(ca):
    aid = _submit(ca)
    assert ca.transition(aid, "approved")["ok"]
    assert ca.transition(aid, "publishing")["ok"]
    assert ca.transition(
        aid,
        "partially_published",
        extra={"platforms_published": ["facebook"], "platforms_pending": ["instagram"]},
    )["ok"]
    # A retry can move it back to publishing (multi-platform recovery).
    r = ca.transition(aid, "publishing")
    assert r["ok"] is True


def test_request_changes_sugar(ca):
    aid = _submit(ca)
    r = ca.request_changes(aid, note="tone tighter please")
    assert r["ok"] is True
    assert r["to"] == "changes_requested"


def test_no_change_short_circuits(ca):
    aid = _submit(ca)
    r = ca.transition(aid, "pending")
    assert r["ok"] is True
    assert r.get("no_change") is True
