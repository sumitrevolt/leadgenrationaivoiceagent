"""Prospect reliability contracts (2026-07-18 — 7 dead 'prospect' jobs postmortem).

2026-07-17 pe dlq:dead me 7 prospect jobs mile: 6× SoftTimeLimitExceeded (540s)
+ 1× TimeLimitExceeded(600). PROSPECT_MAX_QUERIES fanout cap ke bawajood ek slow
provider chain wall-clock deadline cross kar sakti thi, aur run_staff_job har
soft-timeout pe 2 blind Celery retries (=27 min single heavy worker burn) karta tha.

Contracts:
  1. run_prospecting apna PROSPECT_TIME_BUDGET_S wall-clock budget khud enforce
     karta hai — budget khatam = graceful partial return, kill nahi.
  2. run_staff_job SoftTimeLimitExceeded pe retry NAHI karta — graceful partial
     SUCCESS return (no DLQ fill / no Celery retry storm).
"""

from __future__ import annotations

import asyncio

import pytest


def test_time_budget_breaks_query_loop_gracefully(monkeypatch, tmp_path):
    from app.platform import prospector, team

    calls: list[tuple[str, str]] = []

    # Fake clock: har monotonic() call pe 100s aage — pehli query ke baad hi budget cross.
    tick = {"t": 0.0}

    class _FakeTime:
        @staticmethod
        def monotonic():
            tick["t"] += 100.0
            return tick["t"]

    def _osm(query, city, _limit):
        calls.append((query, city))
        return []

    async def _no_sleep(*_args, **_kwargs):
        return None

    monkeypatch.setenv("PROSPECT_TIME_BUDGET_S", "150")
    monkeypatch.setenv("PROSPECT_MAX_QUERIES", "10")
    monkeypatch.setattr(prospector, "time", _FakeTime)
    monkeypatch.setattr(prospector, "_PROSPECTS_FILE", lambda: str(tmp_path / "prospects.jsonl"))
    monkeypatch.setattr(prospector, "_read_all", lambda: [])
    monkeypatch.setattr(
        prospector,
        "_targets",
        lambda: [
            {
                "niche": "solar_residential",
                "query": "solar installer",
                "cities": ["Pune", "Mumbai", "Nagpur"],
            }
        ],
    )
    monkeypatch.setattr(prospector, "_osm_search", _osm)
    monkeypatch.setattr(prospector.asyncio, "sleep", _no_sleep)
    monkeypatch.setattr(team, "log_event", lambda *a, **k: None)

    result = asyncio.run(prospector.run_prospecting(limit_per_query=1))

    assert result["ok"] is True
    assert result["time_budget_exhausted"] is True
    # t_start=100; check@200 (delta 100 <= 150 OK, query 1 runs); check@300 (delta 200 > 150 break).
    assert len(calls) == 1


def test_full_budget_runs_all_queries(monkeypatch, tmp_path):
    """Real clock + default budget: normal fast run me budget kabhi trigger nahi hota."""
    from app.platform import prospector, team

    calls: list[tuple[str, str]] = []

    def _osm(query, city, _limit):
        calls.append((query, city))
        return []

    async def _no_sleep(*_args, **_kwargs):
        return None

    monkeypatch.delenv("PROSPECT_TIME_BUDGET_S", raising=False)
    monkeypatch.setenv("PROSPECT_MAX_QUERIES", "3")
    monkeypatch.setattr(prospector, "_PROSPECTS_FILE", lambda: str(tmp_path / "prospects.jsonl"))
    monkeypatch.setattr(prospector, "_read_all", lambda: [])
    monkeypatch.setattr(
        prospector,
        "_targets",
        lambda: [
            {
                "niche": "solar_residential",
                "query": "solar installer",
                "cities": ["Pune", "Mumbai", "Nagpur"],
            }
        ],
    )
    monkeypatch.setattr(prospector, "_osm_search", _osm)
    monkeypatch.setattr(prospector.asyncio, "sleep", _no_sleep)
    monkeypatch.setattr(team, "log_event", lambda *a, **k: None)

    result = asyncio.run(prospector.run_prospecting(limit_per_query=1))

    assert result["time_budget_exhausted"] is False
    assert len(calls) == 3


def test_run_staff_job_does_not_retry_on_soft_time_limit(monkeypatch):
    """SoftTimeLimitExceeded → partial SUCCESS (no retry, no DLQ-worthy raise)."""
    from celery.exceptions import SoftTimeLimitExceeded

    from app.platform import boot_grace
    from app.tasks import staff_jobs

    retried = {"n": 0}

    def _soft_kill(_coro):
        # coroutine ko close karo warna "never awaited" warning aati hai.
        try:
            _coro.close()
        except Exception:
            pass
        raise SoftTimeLimitExceeded()

    class _RetryCalled(Exception):
        pass

    def _retry(**_kwargs):
        retried["n"] += 1
        raise _RetryCalled()

    monkeypatch.setattr(boot_grace, "should_skip_boot_grace", lambda _job: False)
    monkeypatch.setattr(staff_jobs, "_run_async", _soft_kill)
    monkeypatch.setattr(staff_jobs.run_staff_job, "retry", _retry)

    out = staff_jobs.run_staff_job.run("prospect")
    assert out["ok"] is True
    assert out.get("partial") is True
    assert out.get("reason") == "soft_time_limit"
    assert retried["n"] == 0


def test_generic_failure_still_retries(monkeypatch):
    """Regression guard: non-timeout invoke failure ka retry path INTACT rahe."""
    from app.platform import boot_grace
    from app.tasks import staff_jobs

    class _RetryCalled(Exception):
        pass

    def _boom(_coro):
        try:
            _coro.close()
        except Exception:
            pass
        raise RuntimeError("provider down")

    def _retry(**_kwargs):
        raise _RetryCalled()

    monkeypatch.setattr(boot_grace, "should_skip_boot_grace", lambda _job: False)
    monkeypatch.setattr(staff_jobs, "_run_async", _boom)
    monkeypatch.setattr(staff_jobs.run_staff_job, "retry", _retry)

    with pytest.raises(_RetryCalled):
        staff_jobs.run_staff_job.run("prospect")
