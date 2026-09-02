"""W3.2 — staff-job happy-path smoke tests (run_ops / run_trainer).

run_qa and run_digest already have behavioural tests (W2.2 niches, W1.15 push, W2.4
synthesis) and every job's failure path is covered by W1.14. This closes the gap:
run_ops and run_trainer must return a well-formed dict on the happy path and never
raise. Prune side effects are stubbed so the smoke test never touches real data.
"""

from __future__ import annotations

import asyncio

import app.agents.staff as staff
from app.platform import team


def test_run_ops_returns_health_dict(monkeypatch):
    monkeypatch.setattr(team, "log_event", lambda *a, **k: None)
    # keep the health snapshot pure — no real DB deletes / file trims
    monkeypatch.setattr(staff, "_prune_old_events", lambda *a, **k: 0)
    monkeypatch.setattr(staff, "_prune_old_transcripts", lambda *a, **k: 0)
    monkeypatch.setattr(staff, "_prune_jsonl_stores", lambda *a, **k: 0)

    res = asyncio.run(staff.run_ops())
    assert isinstance(res, dict)
    assert res.get("status") in ("ok", "warn")
    assert "pruned_jsonl_rows" in res  # W1.8 field wired through


def test_run_trainer_returns_dict(monkeypatch):
    monkeypatch.setattr(team, "log_event", lambda *a, **k: None)
    res = asyncio.run(staff.run_trainer())
    assert isinstance(res, dict)
    # no transcripts in the test env → {"calls": 0}; otherwise a suggestions payload
    assert "calls" in res or "suggestions" in res


def test_run_trainer_does_not_wait_for_blocking_telemetry(monkeypatch):
    """A DB/telemetry stall must not turn the trainer into a 600s Celery task."""
    import time

    def _blocked(*_args, **_kwargs):
        time.sleep(8)

    monkeypatch.setattr(team, "log_event", _blocked)
    started = time.monotonic()
    res = asyncio.run(staff.run_trainer())
    elapsed = time.monotonic() - started
    assert isinstance(res, dict)
    assert elapsed < 6.5
