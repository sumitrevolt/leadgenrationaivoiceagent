"""today_overview — plain-Hinglish '🏠 Aaj' admin snapshot.

Guards the admin-friendly contract: build() never raises, returns the expected
shape, and every scheduled job has a human Hinglish label (no raw job-keys leak
to the non-technical admin's home tab).
"""
from datetime import datetime as real_datetime

from app.platform import today_overview


def test_build_shape_never_raises():
    d = today_overview.build()
    for k in ("headline", "problems", "staff", "jobs", "flags_off", "totals", "at"):
        assert k in d
    assert isinstance(d["headline"], str) and d["headline"]
    assert isinstance(d["problems"], list)
    assert isinstance(d["jobs"], list)


def test_problems_are_actionable():
    """Every surfaced problem must carry an actionable 'fix' (pattern rule)."""
    for p in today_overview.build().get("problems", []):
        assert p.get("kya"), "problem needs a 'kya'"
        assert p.get("fix"), "problem needs an actionable 'fix'"


def test_job_info_covers_every_scheduled_job():
    """Parity guard: each scheduler job has a Hinglish label so the 'Aaj' tab
    never shows a raw job-key. Add a new scheduler job -> add JOB_INFO too."""
    from app.platform.team_scheduler import _last_ran

    missing = sorted(set(_last_ran) - set(today_overview.JOB_INFO))
    assert not missing, f"JOB_INFO missing Hinglish labels for: {missing}"


def test_new_jobs_labelled():
    for key in (
        "revenue_snapshot",
        "meter_watch",
        "process_autostart",
        "engineer_dbre",
        "engineer_dataquality",
        "engineer_deps",
        "obsidian_push",
    ):
        info = today_overview.JOB_INFO.get(key)
        assert info and info.get("label") and info.get("kya")


def test_future_scheduled_jobs_are_not_due_yet(monkeypatch):
    class FakeDateTime(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return real_datetime(2026, 6, 26, 0, 58, tzinfo=tz)

    monkeypatch.setattr(today_overview, "datetime", FakeDateTime)

    assert today_overview._job_due_yet("obsidian_push") is False
    assert today_overview._job_due_yet("engineer_dbre") is False
    assert today_overview._job_due_yet("engineer_dataquality") is False
    assert today_overview._job_due_today("engineer_deps") is False
    assert today_overview._job_due_yet("revenue_snapshot") is True
