"""Admin live-stats truth fields (emails aaj, real calls, job timeline)."""

from __future__ import annotations

from datetime import datetime, timezone

from app.api.admin_dashboard import _collect_live_stats, _is_today_iso


def test_is_today_iso_utc():
    today = datetime.utcnow().date().isoformat()
    assert _is_today_iso(f"{today}T10:00:00") is True
    assert _is_today_iso("2020-01-01T10:00:00") is False


def test_collect_live_stats_has_ops_fields():
    stats = _collect_live_stats()
    for key in (
        "emails_sent_today",
        "real_calls_today",
        "job_timeline",
        "automation_status",
        "celery_queue",
        "dlq_count",
        "ops_headline",
        "staff_snapshot",
    ):
        assert key in stats
