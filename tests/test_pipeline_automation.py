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


def test_extra_pass_jobs_in_worker_beat():
    from app.worker import celery_app

    beat = celery_app.conf.beat_schedule
    assert "staff-afternoon-content-daily" in beat
    assert "staff-evening-prospect-daily" in beat
    assert beat["staff-evening-prospect-daily"]["args"] == ("evening_prospect",)


@pytest.mark.asyncio
async def test_extra_pass_jobs_dispatch_noop_when_flag_off(monkeypatch):
    """Flag OFF (default) -> dispatch branch no-ops, never raises."""
    from app.platform import team_scheduler

    monkeypatch.delenv("AFTERNOON_CONTENT", raising=False)
    monkeypatch.delenv("EVENING_PROSPECT", raising=False)
    await team_scheduler._run_job("afternoon_content")
    await team_scheduler._run_job("evening_prospect")
