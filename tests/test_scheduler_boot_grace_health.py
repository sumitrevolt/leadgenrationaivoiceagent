"""Boot-grace skips must remain truthful in the scheduler dead-man view."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone


def _wire_beats(tmp_path, monkeypatch, beat: dict):
    from app.platform import automation_health as ah

    path = tmp_path / "beats.json"
    path.write_text(json.dumps(beat), encoding="utf-8")
    monkeypatch.setattr(ah, "_BEATS", str(path))
    monkeypatch.setattr(
        ah,
        "queue_depth",
        lambda: {"celery": 0, "heavy": 0, "dlq": 0, "dead": 0},
    )
    return ah


def test_same_day_boot_grace_is_scheduled_off_not_overdue(tmp_path, monkeypatch):
    """A restart-protection skip is not a failed/late prospect run."""
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
