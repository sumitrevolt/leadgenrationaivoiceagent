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


# --------------------------------------------------------------------------- #
# ADR-104 Phase F (2026-07-15): build()'s problems[] only ever checked
# queue_backlogged (live celery/heavy depth) -- dead_tasks_present and
# retryable_failed_present (Phase B authoritative fields off the SAME
# automation_health.health() call already made a few lines above) were never
# read. Live discovery: /app/control-center's Problems panel and
# /app/automation's "Aaj" tab (both fed by this exact function) said "Koi
# problem nahi mili" while 4 tasks sat dead/exhausted.
# --------------------------------------------------------------------------- #
def test_dead_tasks_present_surfaces_as_an_actionable_problem(monkeypatch):
    import app.platform.automation_health as automation_health

    def _health():
        return {
            "jobs": [],
            "overdue": [],
            "never_ran": [],
            "queue": {"celery": 0, "heavy": 0, "dlq": 0, "dead": 4},
            "queue_backlogged": False,
            "dead_tasks_present": True,
            "retryable_failed_present": False,
        }

    monkeypatch.setattr(automation_health, "health", _health)
    d = today_overview.build()
    dead_problems = [
        p
        for p in d["problems"]
        if "stuck" in p["kya"].lower() or "dead" in p["kya"] or "exhausted" in p["kya"]
    ]
    assert dead_problems, f"expected a dead/exhausted problem, got: {d['problems']}"
    assert dead_problems[0]["fix"]
    assert dead_problems[0].get("href") == "/app/office#reliability"


def test_retryable_failed_present_surfaces_when_not_already_backlogged(monkeypatch):
    """Avoid a duplicate/redundant entry when queue_backlogged already covers it --
    only add the dedicated retry-failed problem when backlog isn't already flagged."""
    import app.platform.automation_health as automation_health

    def _health():
        return {
            "jobs": [],
            "overdue": [],
            "never_ran": [],
            "queue": {"celery": 0, "heavy": 0, "dlq": 7, "dead": 0},
            "queue_backlogged": False,
            "dead_tasks_present": False,
            "retryable_failed_present": True,
        }

    monkeypatch.setattr(automation_health, "health", _health)
    d = today_overview.build()
    retry_problems = [
        p
        for p in d["problems"]
        if ("DLQ" in p["kya"] or "dubara try" in p["kya"]) and "retry-able" in p["kya"]
    ]
    assert retry_problems, f"expected a retry-able DLQ problem, got: {d['problems']}"
    assert retry_problems[0].get("href") == "/app/office#reliability"


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
