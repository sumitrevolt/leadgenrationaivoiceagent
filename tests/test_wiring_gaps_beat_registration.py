"""Beat-registration wiring-gap tests (2026-09-06, blueprint Phase-1 item 1).

Closes the dormant-wiring detection class: the daily-social incident (#468)
shipped 3x/day beat entries whose task function was NEVER registered as a
Celery task — the worker rejected the name and the job silently never ran.
"Flag on" checks alone can't see this. automation_health.wiring_gaps() now
reports BEAT_REG:* gaps for every beat entry whose task name does not resolve.
"""

from __future__ import annotations

import pytest

from app.platform import automation_health as ah


@pytest.fixture(autouse=True)
def _reset_cache():
    ah._BEAT_REG_CACHE["ts"] = 0.0
    ah._BEAT_REG_CACHE["gaps"] = []
    yield
    ah._BEAT_REG_CACHE["ts"] = 0.0
    ah._BEAT_REG_CACHE["gaps"] = []


def test_real_beat_registry_clean():
    """Regression pin: TODAY's beat registry is fully registered (post-#468).
    Any future unregistered beat entry shows up here automatically."""
    gaps = ah.wiring_gaps()
    beat_reg = [g for g in gaps if str(g.get("key", "")).startswith("BEAT_REG:")]
    assert beat_reg == []


def test_unregistered_task_name_reports_gap(monkeypatch):
    """Module imports fine but task name absent from registry (#468 pattern)."""
    from app.worker import celery_app

    fake = {
        "staff-daily-social-post-morning": {
            "task": "app.tasks.daily_social_post.run_daily_social_post_DOES_NOT_EXIST",
            "schedule": __import__("celery").schedules.crontab(hour=9, minute=30),
        }
    }
    monkeypatch.setattr(celery_app.conf, "beat_schedule", fake, raising=False)
    gaps = ah._beat_registration_gaps()
    assert len(gaps) == 1
    assert gaps[0]["key"] == "BEAT_REG:staff-daily-social-post-morning"
    assert "UNREGISTERED" in gaps[0]["note"]


def test_broken_module_reports_own_gap(monkeypatch):
    """Nonexistent module -> per-entry gap, whole check must NOT die silently."""
    from app.worker import celery_app

    fake = {
        "test-broken-mod": {
            "task": "app.tasks.no_such_module_xyz.run_thing",
            "schedule": __import__("celery").schedules.crontab(hour=9, minute=30),
        }
    }
    monkeypatch.setattr(celery_app.conf, "beat_schedule", fake, raising=False)
    gaps = ah._beat_registration_gaps()
    assert len(gaps) == 1
    assert gaps[0]["key"] == "BEAT_REG:test-broken-mod"
    assert "import failed" in gaps[0]["note"]


def test_ttl_cache_returns_cached_result(monkeypatch):
    """Second call inside TTL window returns the cached list (no re-sweep)."""
    from app.worker import celery_app

    fake = {
        "test-cache-entry": {
            "task": "app.tasks.no_such_module_xyz.run_thing",
            "schedule": __import__("celery").schedules.crontab(hour=9, minute=30),
        }
    }
    monkeypatch.setattr(celery_app.conf, "beat_schedule", fake, raising=False)
    first = ah._beat_registration_gaps()
    assert len(first) == 1
    # Now make the registry look clean — cached result must still come back
    monkeypatch.setattr(celery_app.conf, "beat_schedule", {}, raising=False)
    second = ah._beat_registration_gaps()
    assert second == first
    # Expire the TTL -> fresh sweep finds nothing
    ah._BEAT_REG_CACHE["ts"] = 0.0
    third = ah._beat_registration_gaps()
    assert third == []


def test_wiring_gaps_never_raises_with_beat_check():
    """wiring_gaps() end-to-end stays fail-open with the new check wired in."""
    gaps = ah.wiring_gaps()
    assert isinstance(gaps, list)


def test_whatsapp_automation_task_registered():
    """2026-09-06 fix pin: run_whatsapp_automation was a PLAIN function — the
    hourly beat entry (staff-whatsapp-automation-hourly) was silently dead.
    Direct in-process callers (team_scheduler, staff_jobs) call the task
    object synchronously, so decoration must not change their semantics."""
    from app.tasks.whatsapp_automation import run_whatsapp_automation
    from app.worker import celery_app

    name = "app.tasks.whatsapp_automation.run_whatsapp_automation"
    assert name in celery_app.tasks
    # Task object still callable in-process (synchronous run, not enqueue)
    result = run_whatsapp_automation()
    assert isinstance(result, dict) and "status" in result
