"""W3.1 — team_scheduler boot-grace + time-window routing coverage.

`scheduler_loop` had no test for its two subtlest behaviours (lock/dead-man/content/
last-run are covered by the W1.x suites):
  1. Boot-grace: if the process restarts while a HEAVY daily job's window is active,
     that job is marked done for the day (skipped) to avoid the boot-storm that once
     caused prod-000 (event-loop starve). Growth/hourly jobs are unaffected.
  2. Routing: the 15-min `growth` slot fires on the tick.

Driven by a fixed clock + a one-tick loop (sleep raises CancelledError after tick 1).
This is a regression guard: remove boot-grace and `qa`/`trainer` would fire at 03:00.
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime as _dt

import app.platform.team_scheduler as ts


def test_boot_grace_skips_in_window_heavy_jobs_and_routes_growth(monkeypatch):
    fired: list[str] = []

    async def _rec_job(job):
        fired.append(job)

    async def _stop_sleep(*a, **k):
        raise asyncio.CancelledError()

    class _FixedDT:
        @staticmethod
        def now(tz=None):
            return _dt.datetime(2026, 7, 6, 3, 0, 0, tzinfo=ts._IST)  # 03:00 IST

    saved = dict(ts._last_ran)
    for k in ts._last_ran:
        ts._last_ran[k] = None

    monkeypatch.setattr(ts, "_run_job", _rec_job)
    monkeypatch.setattr(ts, "_load_last_ran", lambda: None)
    monkeypatch.setattr(ts, "_save_last_ran", lambda: None)
    monkeypatch.setattr(ts, "datetime", _FixedDT)
    monkeypatch.setattr(ts.asyncio, "sleep", _stop_sleep)

    qa_marked = None
    trainer_fired_flag = None
    try:
        with contextlib.suppress(asyncio.CancelledError, RuntimeError):
            asyncio.run(ts.scheduler_loop())
        qa_marked = ts._last_ran.get("qa")
        trainer_fired_flag = "trainer" in fired
    finally:
        ts._last_ran.update(saved)

    assert "growth" in fired, "15-min growth slot must route on the tick"
    assert "qa" not in fired, "boot-grace must skip qa (02:30-04:00 window active at boot)"
    assert trainer_fired_flag is False, "boot-grace must skip trainer (03:00-04:30 window)"
    assert qa_marked == "2026-07-06", "boot-grace must mark the skipped heavy job done (day_key)"
