"""Celery beat restart recovery stays narrow and bounded."""

from __future__ import annotations


def test_beat_cron_starting_deadline_is_narrow():
    """A near-slot restart may catch up; stale daily work must not replay."""
    from app.worker import celery_app

    assert celery_app.conf.beat_cron_starting_deadline == 900
