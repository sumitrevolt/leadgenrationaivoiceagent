"""Tests for new pipeline/kb automation modules."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_pipeline_ops_run_daily_no_db():
    from app.platform import pipeline_ops

    out = await pipeline_ops.run_daily()
    assert "ok" in out


@pytest.mark.asyncio
async def test_kb_refresh_disabled_by_default(monkeypatch):
    from app.platform import kb_refresh

    monkeypatch.delenv("KB_WEEKLY_REFRESH", raising=False)
    monkeypatch.setenv("USE_CONTEXTUAL_INGEST", "0")
    out = await kb_refresh.run_weekly_if_enabled()
    assert out.get("skipped") == "disabled"


def test_staff_jobs_include_new_pipeline_jobs():
    from app.tasks.staff_jobs import STAFF_JOBS

    for j in (
        "pipeline",
        "email_followup",
        "kb_refresh",
        "midday_prospect",
        "evening_wrap",
        "weekly_marketing",
        "saturday_hygiene",
        "obsidian_push",
    ):
        assert j in STAFF_JOBS


@pytest.mark.asyncio
async def test_scheduled_ops_evening_wrap():
    from app.platform import scheduled_ops

    out = await scheduled_ops.run_evening_wrap()
    assert out.get("ok") is True


@pytest.mark.asyncio
async def test_scheduled_ops_weekly_marketing_skippable(monkeypatch):
    from app.platform import scheduled_ops

    monkeypatch.setenv("WEEKLY_MARKETING_PACK", "0")
    out = await scheduled_ops.run_weekly_marketing()
    assert out.get("skipped")


@pytest.mark.asyncio
async def test_scheduled_ops_hygiene_trims_every_routed_queue(monkeypatch):
    """2026-07-02: Saturday hygiene used to only ever check/trim the default
    "celery" queue. leadgen_worker was fixed to actually consume
    calling/scraping/reporting/sync/training/heavy (previously undrained,
    silently accumulating) — hygiene must now watch all of them, not just
    the one it always watched."""
    from app.platform import scheduled_ops

    class _FakeRedis:
        def __init__(self):
            self.store = {
                "celery": 900,
                "calling": 50,
                "scraping": 1000,
                "reporting": 0,
                "sync": 799,
                "training": 0,
                "heavy": 5,
                "dlq:failed_tasks": 2,
            }
            self.deleted: list[str] = []

        def llen(self, key):
            return self.store.get(key, 0)

        def delete(self, key):
            self.deleted.append(key)
            self.store[key] = 0

    fake = _FakeRedis()
    monkeypatch.setattr("redis.Redis.from_url", lambda *a, **k: fake)
    monkeypatch.setenv("CELERY_TRIM_MIN_DEPTH", "800")
    monkeypatch.setattr("app.platform.team.log_event", lambda *a, **k: None)

    out = await scheduled_ops.run_saturday_hygiene()

    assert out["queue_depths"]["celery"] == 900
    assert out["queue_depths"]["scraping"] == 1000
    assert out["queue_depths"]["sync"] == 799
    # only queues AT/OVER the threshold get trimmed
    assert set(out["queues_trimmed"].keys()) == {"celery", "scraping"}
    assert fake.store["celery"] == 0
    assert fake.store["scraping"] == 0
    # below-threshold queues untouched
    assert fake.store["sync"] == 799
    assert fake.store["calling"] == 50


@pytest.mark.asyncio
async def test_scheduled_ops_hygiene_never_auto_deletes_calling_queue(monkeypatch):
    """ "calling" carries run_campaign_task (admin-launched, never
    beat-regenerated — deleting a queued one silently drops the campaign AND
    leaks its launch lock since the delete skips the task's own `finally:
    release_campaign_lock()`) and process_callbacks' make_call_task (only
    re-enqueued inside a 1-hour window — past that, gone for good). Unlike
    every other routed queue, it must be ALERT-ONLY here, never
    auto-deleted, even when its depth blows past the trim threshold."""
    from app.platform import scheduled_ops

    class _FakeRedis:
        def __init__(self):
            self.store = {
                "celery": 0,
                "calling": 5000,  # way over threshold
                "scraping": 0,
                "reporting": 0,
                "sync": 0,
                "training": 0,
                "heavy": 0,
                "dlq:failed_tasks": 0,
            }
            self.deleted: list[str] = []

        def llen(self, key):
            return self.store.get(key, 0)

        def delete(self, key):
            self.deleted.append(key)
            self.store[key] = 0

    fake = _FakeRedis()
    monkeypatch.setattr("redis.Redis.from_url", lambda *a, **k: fake)
    monkeypatch.setenv("CELERY_TRIM_MIN_DEPTH", "800")
    monkeypatch.setattr("app.platform.team.log_event", lambda *a, **k: None)

    out = await scheduled_ops.run_saturday_hygiene()

    assert "calling" not in fake.deleted
    assert fake.store["calling"] == 5000
    assert "calling" not in out.get("queues_trimmed", {})
    assert out.get("queues_alerted") == {"calling": 5000}


@pytest.mark.asyncio
async def test_scheduled_ops_hygiene_never_raises_when_redis_down(monkeypatch):
    from app.platform import scheduled_ops

    def _boom(*a, **k):
        raise RuntimeError("redis down")

    monkeypatch.setattr("redis.Redis.from_url", _boom)
    out = await scheduled_ops.run_saturday_hygiene()
    assert out.get("ok") is True
    assert "queue_depths" not in out


# --- 2026-06-22: extra agent passes (afternoon_content + evening_prospect) ---


def test_staff_jobs_include_extra_pass_jobs():
    from app.tasks.staff_jobs import STAFF_JOBS

    assert "afternoon_content" in STAFF_JOBS
    assert "evening_prospect" in STAFF_JOBS


def test_extra_pass_jobs_boot_grace_and_registry():
    """6-layer parity: tick registry + durable boot-grace window present."""
    from app.platform import boot_grace, team_scheduler

    for j in ("afternoon_content", "evening_prospect"):
        assert j in team_scheduler._last_ran
        assert j in boot_grace._HEAVY_WINDOWS


def test_scheduler_loop_uses_defined_ist_now_for_email_windows():
    """Rollback in-process scheduler path must not reference an undefined clock."""
    import inspect

    from app.platform import team_scheduler

    src = inspect.getsource(team_scheduler.scheduler_loop)
    assert "now_ist" not in src
    assert 'f"{day_key}:{now.hour}"' in src


def test_extra_pass_jobs_in_worker_beat():
    from app.worker import celery_app

    beat = celery_app.conf.beat_schedule
    assert "staff-afternoon-content-daily" in beat
    assert "staff-evening-prospect-daily" in beat
    assert "staff-obsidian-push-daily" in beat
    assert beat["staff-evening-prospect-daily"]["args"] == ("evening_prospect",)
    assert beat["staff-obsidian-push-daily"]["args"] == ("obsidian_push",)


@pytest.mark.asyncio
async def test_extra_pass_jobs_dispatch_noop_when_flag_off(monkeypatch):
    """Flag OFF (default) -> dispatch branch no-ops, never raises."""
    from app.platform import team_scheduler

    monkeypatch.delenv("AFTERNOON_CONTENT", raising=False)
    monkeypatch.delenv("EVENING_PROSPECT", raising=False)
    await team_scheduler._run_job("afternoon_content")
    await team_scheduler._run_job("evening_prospect")
