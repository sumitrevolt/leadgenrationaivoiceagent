"""W1.2 — dead-man switch must record REAL sub-job status, not always-success.

Bug: `_run_job_inner` wrapped the whole job dispatcher in one big try/except whose
outer handler LOGGED the exception and swallowed it (fell through, returned None).
So `_run_job` never saw a failure and `automation_health.record_run(job, True, …)`
recorded success forever — the dead-man / overdue alert could never fire for a job
that throws on every run.

Fix: `_run_job_inner` returns False when its outer except catches; `_run_job`
threads that into `record_run` as ok=False — WITHOUT re-raising (the tick's other
jobs must still run; scheduler_loop runs the whole tick under one try).
"""
from __future__ import annotations

import asyncio


def _run(coro):
    return asyncio.run(coro)


def test_run_job_records_failure_when_job_raises(monkeypatch):
    """End-to-end: a job that raises must be recorded ok=False by the dead-man switch."""
    import app.platform.automation_health as ah
    import app.platform.growth_engine as ge
    import app.platform.scheduler_config as sc
    import app.platform.team_scheduler as ts

    captured: dict = {}

    def _fake_record(job, ok, dur, note=None):
        captured["job"] = job
        captured["ok"] = ok

    async def _boom(*a, **k):
        raise RuntimeError("simulated job failure")

    monkeypatch.setattr(ah, "record_run", _fake_record)
    monkeypatch.setattr(ge, "pulse", _boom)  # 'growth' branch blows up at its first await
    monkeypatch.setattr(sc, "is_enabled", lambda job: True)

    _run(ts._run_job("growth"))

    assert captured.get("job") == "growth"
    assert captured.get("ok") is False, (
        "dead-man switch must record ok=False when the job raises (bug recorded True forever)"
    )


def test_run_job_inner_returns_false_on_failure(monkeypatch):
    """Unit: `_run_job_inner` reports failure via its return value, not silent None."""
    import app.platform.growth_engine as ge
    import app.platform.team_scheduler as ts

    async def _boom(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(ge, "pulse", _boom)
    res = _run(ts._run_job_inner("growth"))
    assert res is False, "_run_job_inner must return False when its outer except catches"
