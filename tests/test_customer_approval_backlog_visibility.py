"""The customer-approval pile must be VISIBLE to the owner.

Prod evidence (2026-08-09): 32 of 39 video records sat at `pending` customer
review, only 4 were ever published, and the owner-facing "Aaj" tab reported no
problem — because `_pending_decisions()` reads `approvals_bridge` (the agentic
draft queue), which contains no reference to `content_approval` at all. So the
one queue that decides whether a generated video ever reaches a customer was
counted by nothing.

A video the customer never approves is never delivered, which makes this a
revenue signal, not a queue statistic.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.platform import today_overview


def _row(days_old: int, kind: str = "video_ad", client_id: str = "c1") -> dict:
    created = datetime.now(timezone.utc) - timedelta(days=days_old)
    return {
        "client_id": client_id,
        "status": "pending",
        "created_at": created.isoformat(),
        "content": {"type": kind},
    }


@pytest.fixture
def _fake_pending(monkeypatch):
    def _set(rows):
        import app.marketing.content_approval as ca

        monkeypatch.setattr(ca, "pending", lambda client_id="": list(rows))

    return _set


def test_backlog_counts_age_and_type(_fake_pending):
    _fake_pending([_row(9, "video_ad", "jiya"), _row(1, "post", "other"), _row(4, "video_ad")])
    out = today_overview._customer_approval_backlog()
    assert out["total"] == 3
    assert out["by_type"] == {"video_ad": 2, "post": 1}
    assert out["oldest_days"] == 9
    assert out["oldest_client"] == "jiya"


def test_unreadable_store_reports_nothing_rather_than_false_alarm(monkeypatch):
    import app.marketing.content_approval as ca

    def _boom(client_id=""):
        raise RuntimeError("store unreadable")

    monkeypatch.setattr(ca, "pending", _boom)
    assert today_overview._customer_approval_backlog()["total"] == 0


def test_small_same_day_queue_stays_quiet(_fake_pending):
    """Two fresh approvals is normal review flow, not a problem to escalate."""
    _fake_pending([_row(0), _row(0)])
    out = today_overview.build()
    assert not [p for p in out["problems"] if "approval ka intezaar" in str(p.get("kya"))]


def test_pile_becomes_an_owner_facing_problem(_fake_pending):
    _fake_pending([_row(20), _row(18), _row(15)])
    out = today_overview.build()
    hits = [p for p in out["problems"] if "approval ka intezaar" in str(p.get("kya"))]
    assert hits, "an ageing customer-approval pile must surface on the Aaj tab"
    assert "20 din" in hits[0]["kya"]
    assert hits[0]["fix"]


def test_a_single_old_item_still_surfaces(_fake_pending):
    """One approval ignored for days is the shape the 32-pile started as."""
    _fake_pending([_row(11)])
    out = today_overview.build()
    assert [p for p in out["problems"] if "approval ka intezaar" in str(p.get("kya"))]


def test_totals_keep_owner_and_customer_queues_separate(_fake_pending, monkeypatch):
    """Collapsing them would hide a delivery blocker inside an ops number."""
    _fake_pending([_row(5), _row(2)])
    monkeypatch.setattr(today_overview, "_pending_decisions", lambda: 7)
    out = today_overview.build()
    assert out["totals"]["needs_decision"] == 7
    assert out["totals"]["customer_approvals_pending"] == 2
    assert out["totals"]["customer_approvals_oldest_days"] == 5
