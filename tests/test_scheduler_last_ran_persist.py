"""W1.7 — scheduler `_last_ran` must persist across restarts (no re-fire on restart).

Bug: `_last_ran` was an in-memory dict that reset to all-None on process restart, so
hourly/slot jobs (`ops` hourly, `growth` 15-min, `flow_cron` 5-min) re-fired for the
same window they had already run. Fix: persist `_last_ran` to `data/` (load on boot,
save each changed tick). Boot-grace still handles heavy daily jobs in-window at boot.

Covers both the mechanism (save→restart→load round-trip) AND the wiring (scheduler_loop
actually calls load-on-boot + save-per-tick) — the wiring is the real regression risk.
"""

from __future__ import annotations

import asyncio
import contextlib

import app.platform.team_scheduler as ts


def test_last_ran_round_trip(monkeypatch, tmp_path):
    monkeypatch.setattr(ts, "_LAST_RAN_PATH", str(tmp_path / "scheduler_last_ran.json"))
    saved = dict(ts._last_ran)
    try:
        ts._last_ran["ops"] = "2026-07-06 10"
        ts._last_ran["growth"] = "2026-07-06 10:15"
        ts._save_last_ran()
        for k in ts._last_ran:  # simulate restart: wipe in-memory state
            ts._last_ran[k] = None
        ts._load_last_ran()
        assert ts._last_ran["ops"] == "2026-07-06 10"
        assert ts._last_ran["growth"] == "2026-07-06 10:15"
    finally:
        ts._last_ran.update(saved)


def test_load_ignores_missing_file(monkeypatch, tmp_path):
    monkeypatch.setattr(ts, "_LAST_RAN_PATH", str(tmp_path / "nope.json"))
    saved = dict(ts._last_ran)
    try:
        for k in ts._last_ran:
            ts._last_ran[k] = None
        ts._load_last_ran()  # must not raise on missing file
        assert ts._last_ran["ops"] is None
    finally:
        ts._last_ran.update(saved)


def test_scheduler_loop_wires_load_and_save(monkeypatch):
    """Wiring: loop calls _load_last_ran once on boot and _save_last_ran on a changed tick."""
    load_calls = {"n": 0}
    save_calls = {"n": 0}
    saved = dict(ts._last_ran)

    monkeypatch.setattr(
        ts, "_load_last_ran", lambda: load_calls.__setitem__("n", load_calls["n"] + 1)
    )
    monkeypatch.setattr(
        ts, "_save_last_ran", lambda: save_calls.__setitem__("n", save_calls["n"] + 1)
    )

    async def _noop_job(job):
        return None

    async def _stop_sleep(*a, **k):
        raise asyncio.CancelledError()

    monkeypatch.setattr(ts, "_run_job", _noop_job)
    monkeypatch.setattr(ts.asyncio, "sleep", _stop_sleep)  # break loop after first tick

    try:
        with contextlib.suppress(asyncio.CancelledError, RuntimeError):
            asyncio.run(ts.scheduler_loop())
    finally:
        ts._last_ran.update(saved)

    assert load_calls["n"] == 1, "scheduler_loop must load persisted last-run once on boot"
    assert save_calls["n"] >= 1, "scheduler_loop must persist last-run on a changed tick"
