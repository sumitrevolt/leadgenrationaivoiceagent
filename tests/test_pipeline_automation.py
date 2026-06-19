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

    for j in ("pipeline", "email_followup", "kb_refresh"):
        assert j in STAFF_JOBS
