"""Budget-skipped engines must be VISIBLE.

Regression guard for a whole outage class, not one bug: when a mega-job runs out
of its wall-clock budget, `team_scheduler._run_content_engine` closes the
coroutine and returns False. Before 2026-08-09 that happened with no exception
and no log naming the engine, so an engine could stop running for weeks while
every dashboard said "healthy".

Prod evidence that the mechanism really trips: the `content` job exceeded its
420s budget on 15 consecutive daily runs (2026-07-18 → 2026-08-01, 452–530s).
"""

from __future__ import annotations

import asyncio
import json

import pytest

from app.platform import automation_health
from app.platform.job_time_budget import JobBudget


@pytest.fixture(autouse=True)
def _isolated_skip_ledger(tmp_path, monkeypatch):
    path = tmp_path / "job_engine_skips.jsonl"
    monkeypatch.setattr(automation_health, "_SKIPS", lambda: str(path))
    return path


class _ExhaustedBudget(JobBudget):
    """A budget with nothing left — what the 15 over-budget prod runs produced."""

    def __init__(self) -> None:
        super().__init__(0.0, label="content")

    def ok(self, need: float = 8.0) -> bool:
        return False


def test_skip_is_recorded_with_job_and_engine_names(_isolated_skip_ledger):
    automation_health.record_engine_skip("content", "video_ad_cycle", "budget_exhausted")
    rows = [json.loads(x) for x in _isolated_skip_ledger.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["job"] == "content"
    assert rows[0]["engine"] == "video_ad_cycle"
    assert rows[0]["reason"] == "budget_exhausted"


def test_skip_is_logged_before_it_is_persisted(monkeypatch, caplog):
    """A storage failure must not also swallow the signal — that is the exact bug
    class being fixed, so the warning is emitted before any write is attempted."""

    def _boom():
        raise OSError("disk full")

    monkeypatch.setattr(automation_health, "_SKIPS", _boom)
    with caplog.at_level("WARNING"):
        automation_health.record_engine_skip("content", "cadence")
    joined = " ".join(r.getMessage() for r in caplog.records)
    assert "cadence" in joined
    assert "content" in joined


def test_run_content_engine_records_the_skip_it_used_to_swallow():
    from app.platform import team_scheduler

    ran = {"v": False}

    async def _engine():
        ran["v"] = True

    ok = asyncio.run(
        team_scheduler._run_content_engine("video_ad_cycle", _engine(), _ExhaustedBudget())
    )
    assert ok is False
    assert ran["v"] is False, "engine must not run when the budget is gone"

    summary = automation_health.engine_skip_summary(hours=48)
    assert summary["total"] == 1
    assert summary["by_engine"]["video_ad_cycle"] == 1
    assert summary["by_job"]["content"] == 1


def test_healthy_budget_runs_the_engine_and_records_nothing():
    from app.platform import team_scheduler

    ran = {"v": False}

    async def _engine():
        ran["v"] = True

    ok = asyncio.run(
        team_scheduler._run_content_engine("cadence", _engine(), JobBudget(600.0, label="content"))
    )
    assert ok is True and ran["v"] is True
    assert automation_health.engine_skip_summary()["total"] == 0


def test_engine_failure_still_isolated_and_not_counted_as_a_skip(caplog):
    """An engine that RAISES is a different failure than one that never ran —
    keep them distinguishable, or the new signal becomes noise."""
    from app.platform import team_scheduler

    async def _engine():
        raise RuntimeError("provider down")

    with caplog.at_level("WARNING"):
        ok = asyncio.run(
            team_scheduler._run_content_engine(
                "dunning", _engine(), JobBudget(600.0, label="content")
            )
        )
    assert ok is False
    assert automation_health.engine_skip_summary()["total"] == 0


def test_health_reports_degraded_and_names_the_engines(monkeypatch):
    """A skipped engine is real un-run work — 'healthy' would be a lie."""
    automation_health.record_engine_skip("content", "video_ad_cycle")
    automation_health.record_engine_skip("content", "cadence")

    h = automation_health.health()
    assert h["engines_skipped_recently"] is True
    assert h["ok"] is False
    assert h["status"] == "degraded"
    assert set(h["engine_skips"]["by_engine"]) == {"video_ad_cycle", "cadence"}


def test_owner_facing_aaj_tab_surfaces_the_skip_in_hinglish(monkeypatch):
    """The non-technical surface must say it too, with an actionable fix."""
    from app.platform import today_overview

    monkeypatch.setattr(
        automation_health,
        "health",
        lambda: {
            "status": "degraded",
            "ok": False,
            "overdue": [],
            "never_ran": [],
            "queue": {},
            "jobs": [],
            "engine_skips": {
                "total": 3,
                "by_engine": {"video_ad_cycle": 3},
                "by_job": {"content": 3},
            },
            "engines_skipped_recently": True,
        },
    )
    out = today_overview.build()
    hits = [p for p in out.get("problems") or [] if "video_ad_cycle" in str(p.get("kya"))]
    assert hits, "budget-skipped engine must appear in the Aaj tab problems list"
    assert hits[0]["fix"]


def test_summary_window_excludes_old_skips(_isolated_skip_ledger):
    _isolated_skip_ledger.write_text(
        json.dumps({"job": "content", "engine": "old", "at": "2020-01-01T00:00:00+00:00"}) + "\n",
        encoding="utf-8",
    )
    assert automation_health.engine_skip_summary(hours=48)["total"] == 0
