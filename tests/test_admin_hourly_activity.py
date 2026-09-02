"""Admin hourly-activity endpoint + recent_events(hours=) signature fix.

Regression guard for two things shipped 2026-06-25:
  1. team.recent_events() now accepts `hours=` (pehle TypeError → _manager()
     monitor hamesha "standby" pe gir jata tha — signature drift bug).
  2. /api/admin/hourly-activity buckets agent_events into IST hour groups so the
     admin dashboard can show "har ghante kya kya hua" (user feedback).
"""

from __future__ import annotations


def test_recent_events_accepts_hours():
    """recent_events(hours=1) must NOT raise (was TypeError before fix)."""
    from app.platform.team import recent_events

    out = recent_events(hours=1)
    assert isinstance(out, list)


def test_recent_events_default_still_works():
    from app.platform.team import recent_events

    assert isinstance(recent_events(limit=5), list)


def test_hourly_activity_endpoint_shape():
    """Endpoint best-effort dict with bucketed structure, never 500."""
    from app.api.admin_dashboard import get_hourly_activity

    res = get_hourly_activity(hours=24, _user=None)
    assert isinstance(res, dict)
    assert "buckets" in res and isinstance(res["buckets"], list)
    assert "total" in res and isinstance(res["total"], int)
    # No DB rows in test env → empty buckets, but well-formed (no crash).
    for b in res["buckets"]:
        assert "label" in b and "count" in b and "samples" in b
        assert isinstance(b.get("members"), list)
