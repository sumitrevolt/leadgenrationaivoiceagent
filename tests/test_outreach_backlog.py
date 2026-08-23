"""Tests for the outreach backlog fix — prospector.pending_for_outreach().

Bug: run_email_outreach used list_prospects(limit=500) which hard-caps at the 500
NEWEST prospects; once those are all emailed, 470 reachable (email + unemailed) older
prospects stayed invisible forever → outreach stalled → no new leads. Fix surfaces
ALL reachable+unemailed prospects, oldest-first.
"""

from app.platform import prospector


def test_pending_for_outreach_surfaces_backlog(monkeypatch):
    data = [
        {"id": "a", "status": "ready", "email": "old@x.com", "found_at": "2026-01-01"},  # ✓ oldest
        {"id": "b", "status": "ready", "email": "new@x.com", "found_at": "2026-06-01"},  # ✓
        {
            "id": "c",
            "status": "ready",
            "email": "done@x.com",
            "emailed_at": "2026-06-02",
            "found_at": "2026-02-01",
        },  # already emailed
        {"id": "d", "status": "ready", "email": "", "found_at": "2026-03-01"},  # no email
        {
            "id": "e",
            "status": "contacted",
            "email": "x@x.com",
            "found_at": "2026-04-01",
        },  # not ready
        {
            "id": "f",
            "status": "ready",
            "email": "bademail",
            "found_at": "2026-05-01",
        },  # invalid email
    ]
    monkeypatch.setattr(prospector, "_read_all", lambda: list(data))
    out = prospector.pending_for_outreach(limit=500)
    assert [r["id"] for r in out] == ["a", "b"]  # only reachable+unemailed+ready, oldest-first


def test_pending_for_outreach_respects_limit(monkeypatch):
    data = [
        {"id": str(i), "status": "ready", "email": f"u{i}@x.com", "found_at": f"2026-01-{i:02d}"}
        for i in range(1, 10)
    ]
    monkeypatch.setattr(prospector, "_read_all", lambda: list(data))
    assert len(prospector.pending_for_outreach(limit=3)) == 3


def test_pending_for_outreach_never_raises(monkeypatch):
    def boom():
        raise RuntimeError("read fail")

    monkeypatch.setattr(prospector, "_read_all", boom)
    assert prospector.pending_for_outreach() == []


def test_pending_excludes_when_all_emailed(monkeypatch):
    data = [
        {"id": "a", "status": "ready", "email": "a@x.com", "emailed_at": "2026-06-01"},
        {"id": "b", "status": "ready", "email": "b@x.com", "emailed_at": "2026-06-01"},
    ]
    monkeypatch.setattr(prospector, "_read_all", lambda: list(data))
    assert prospector.pending_for_outreach() == []
