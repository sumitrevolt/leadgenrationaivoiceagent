"""Boot-grace skips must remain truthful in the scheduler dead-man view."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone


def _wire_beats(tmp_path, monkeypatch, beat: dict):
    from app.platform import automation_health as ah

    path = tmp_path / "beats.json"
    path.write_text(json.dumps(beat), encoding="utf-8")
    monkeypatch.setattr(ah, "_BEATS", lambda: str(path))
    monkeypatch.setattr(
        ah,
        "queue_depth",
        lambda: {"celery": 0, "heavy": 0, "dlq": 0, "dead": 0},
    )
    return ah


def test_same_day_boot_grace_is_scheduled_off_not_overdue(tmp_path, monkeypatch):
    """A restart-protection skip is not a failed/late prospect run (inside window)."""
    from zoneinfo import ZoneInfo

    from app.platform import automation_health as ah
    from app.platform import boot_grace

    ist = ZoneInfo("Asia/Kolkata")
    # Pin "now" inside prospect heavy window 09:30–11:30 IST.
    fixed = datetime(2026, 7, 25, 10, 0, tzinfo=ist).astimezone(timezone.utc)
    monkeypatch.setattr(ah, "_now", lambda: fixed)
    monkeypatch.setattr(
        boot_grace,
        "marker_still_active",
        lambda job, marker_at, now=None: True,
    )
    _wire_beats(
        tmp_path,
        monkeypatch,
        {
            "prospect": {
                "job": "prospect",
                "ok": True,
                "s": 0.0,
                "at": fixed.isoformat(),
                "note": "boot_grace",
            }
        },
    )

    out = ah.health()
    row = next(j for j in out["jobs"] if j["job"] == "prospect")
    assert row["status"] == "scheduled_off"
    assert row["note"] == "boot_grace"
    assert "prospect" not in out["overdue"]


def test_same_day_boot_grace_after_window_is_recoverable(tmp_path, monkeypatch):
    """Lost deferred countdown after window → overdue so run_due can re-dispatch."""
    from zoneinfo import ZoneInfo

    from app.platform import automation_health as ah

    ist = ZoneInfo("Asia/Kolkata")
    # Content window ends 09:00 IST; 12:00 IST is well past +5m slack.
    fixed = datetime(2026, 7, 25, 12, 0, tzinfo=ist).astimezone(timezone.utc)
    marker = datetime(2026, 7, 25, 7, 5, tzinfo=ist).astimezone(timezone.utc)
    monkeypatch.setattr(ah, "_now", lambda: fixed)
    _wire_beats(
        tmp_path,
        monkeypatch,
        {
            "content": {
                "job": "content",
                "ok": True,
                "s": 0.0,
                "at": marker.isoformat(),
                "note": "boot_grace",
            }
        },
    )

    out = ah.health()
    row = next(j for j in out["jobs"] if j["job"] == "content")
    assert row["status"] == "overdue"
    assert row["note"] == "boot_grace_lost_defer"
    assert "content" in out["overdue"]


def test_boot_grace_marker_expires_next_day(tmp_path, monkeypatch):
    """A stale marker cannot hide a missed run forever."""
    from app.platform import automation_health as ah

    fixed = datetime.now(timezone.utc).replace(microsecond=0)
    monkeypatch.setattr(ah, "_now", lambda: fixed)
    _wire_beats(
        tmp_path,
        monkeypatch,
        {
            "prospect": {
                "job": "prospect",
                "ok": True,
                "s": 0.0,
                "at": (fixed - timedelta(days=2)).isoformat(),
                "note": "boot_grace",
            }
        },
    )

    out = ah.health()
    assert "prospect" in out["overdue"]


def test_staff_boot_grace_records_actual_job_heartbeat(monkeypatch):
    """Celery boot-grace branch must write a real job marker."""
    from app.platform import automation_health, boot_grace
    from app.tasks import staff_jobs

    events: list[tuple] = []
    monkeypatch.setattr(boot_grace, "should_skip_boot_grace", lambda _job: True)
    monkeypatch.setattr(boot_grace, "defer_seconds", lambda _job: 120)
    monkeypatch.setattr(
        automation_health,
        "record_run",
        lambda *args, **kwargs: events.append((args, kwargs)),
    )
    monkeypatch.setattr(staff_jobs.run_staff_job, "apply_async", lambda *a, **k: None)

    out = staff_jobs.run_staff_job.run("prospect")

    assert out["skipped"] == "boot_grace"
    assert events
    args, kwargs = events[-1]
    assert args[:3] == ("prospect", True, 0.0)
    assert kwargs == {"note": "boot_grace"}


def test_staff_boot_grace_enqueue_failure_stays_visible(monkeypatch):
    from app.platform import automation_health, boot_grace
    from app.tasks import staff_jobs

    events: list[tuple] = []
    monkeypatch.setattr(boot_grace, "should_skip_boot_grace", lambda _job: True)
    monkeypatch.setattr(boot_grace, "defer_seconds", lambda _job: 120)
    monkeypatch.setattr(
        automation_health,
        "record_run",
        lambda *args, **kwargs: events.append((args, kwargs)),
    )

    def _fail_enqueue(*_args, **_kwargs):
        raise RuntimeError("broker unavailable")

    monkeypatch.setattr(staff_jobs.run_staff_job, "apply_async", _fail_enqueue)
    out = staff_jobs.run_staff_job.run("prospect")

    assert out["skipped"] == "boot_grace"
    args, kwargs = events[-1]
    assert args[:3] == ("prospect", False, 0.0)
    assert kwargs == {"note": "boot_grace_enqueue_failed"}
