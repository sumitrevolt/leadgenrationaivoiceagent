"""DLQ SoftTimeLimit closure contracts (2026-07-23 onboard/content + prospect dead).

Root causes fixed without global timeout bumps:
  - JobBudget wall-clock for content/onboard/prospect (margin under soft=540)
  - SoftTimeLimit → graceful partial SUCCESS (no Celery retry / DLQ fill)
  - Audited resolve_from_list → dlq:resolved (no blind purge)
"""

from __future__ import annotations

import json

import pytest


def test_budget_seconds_clamps_and_defaults(monkeypatch):
    from app.platform.job_time_budget import budget_seconds

    monkeypatch.delenv("CONTENT_TIME_BUDGET_S", raising=False)
    assert budget_seconds("CONTENT_TIME_BUDGET_S") == 420.0
    monkeypatch.setenv("CONTENT_TIME_BUDGET_S", "9999")
    assert budget_seconds("CONTENT_TIME_BUDGET_S") == 480.0
    monkeypatch.setenv("CONTENT_TIME_BUDGET_S", "5")
    assert budget_seconds("CONTENT_TIME_BUDGET_S") == 30.0
    monkeypatch.setenv("CONTENT_TIME_BUDGET_S", "nope")
    assert budget_seconds("CONTENT_TIME_BUDGET_S") == 420.0


def test_job_budget_ok_exhausts(monkeypatch):
    from app.platform import job_time_budget as jtb

    tick = {"t": 0.0}

    class _FakeTime:
        @staticmethod
        def monotonic():
            return tick["t"]

    monkeypatch.setattr(jtb, "time", _FakeTime)
    b = jtb.JobBudget(100.0, label="content")
    assert b.ok(need=20.0) is True
    tick["t"] = 95.0
    assert b.ok(need=20.0) is False
    assert b.exhausted is True
    # still 5s left — smaller need can pass; exhausted flag is log-once only
    assert b.ok(need=1.0) is True
    tick["t"] = 100.0
    assert b.ok(need=1.0) is False


def test_content_engine_skips_when_budget_exhausted():
    import asyncio

    from app.platform import team_scheduler

    class _DeadBudget:
        def ok(self, need=8.0):
            return False

    async def _boom():
        raise AssertionError("engine must not run when budget exhausted")

    tok = team_scheduler._active_job_budget.set(_DeadBudget())
    try:
        ok = asyncio.run(team_scheduler._run_content_engine("auto_content", _boom()))
    finally:
        team_scheduler._active_job_budget.reset(tok)
    assert ok is False


def test_onboard_sweep_skips_when_budget_gone(monkeypatch):
    import asyncio

    from app.marketing import onboarding

    class _Dead:
        def ok(self, need=8.0):
            return False

        def remaining(self):
            return 0.0

        def snapshot(self):
            return {"exhausted": True, "limit_s": 30, "elapsed_s": 30, "remaining_s": 0}

    monkeypatch.setattr(
        "app.platform.job_time_budget.JobBudget.from_env",
        classmethod(lambda cls, *_a, **_k: _Dead()),
    )
    monkeypatch.setenv("AUTO_ONBOARD", "0")

    out = asyncio.run(onboarding.run_onboarding_sweep(limit=2))
    assert out["renudge"] == {"skipped": "time_budget"}
    assert out["delivery"] == {"skipped": "time_budget"}
    assert out.get("skipped") == "AUTO_ONBOARD off"


class _FakeRedis:
    def __init__(self):
        self.lists: dict[str, list[str]] = {}

    def llen(self, key):
        return len(self.lists.get(key, []))

    def rpop(self, key):
        lst = self.lists.get(key) or []
        if not lst:
            return None
        return lst.pop()

    def lpush(self, key, value):
        self.lists.setdefault(key, []).insert(0, value)
        return len(self.lists[key])

    def ltrim(self, key, start, end):
        lst = self.lists.get(key, [])
        self.lists[key] = lst[start : end + 1]


def test_resolve_from_list_audited_no_blind_purge():
    from app.platform import dlq_retry

    r = _FakeRedis()
    keep = {"args": "('content',)", "exc": "SoftTimeLimitExceeded()"}
    move = {"args": "('prospect',)", "exc": "SoftTimeLimitExceeded()"}
    # list left=newest; rpop takes rightmost = oldest first in our push order
    r.lists[dlq_retry.DEAD_KEY] = [
        json.dumps(keep),
        json.dumps(move),
        json.dumps({"args": "('prospect',)", "exc": "TimeLimitExceeded(600)"}),
    ]
    out = dlq_retry.resolve_from_list(
        source_key=dlq_retry.DEAD_KEY,
        resolution="STALE_EXPIRED",
        job="prospect",
        note="harvest budget already on main",
        max_items=20,
        r=r,
    )
    assert out["moved"] == 2
    assert out["kept"] == 1
    assert r.llen(dlq_retry.DEAD_KEY) == 1
    assert r.llen(dlq_retry.RESOLVED_KEY) == 2
    resolved = json.loads(r.lists[dlq_retry.RESOLVED_KEY][0])
    assert resolved["resolution"] == "STALE_EXPIRED"
    assert "resolved_at" in resolved
    assert "prospect" in str(resolved.get("args"))


def test_resolve_rejects_invalid_resolution():
    from app.platform import dlq_retry

    out = dlq_retry.resolve_from_list(
        source_key=dlq_retry.DEAD_KEY,
        resolution="YEET",
        r=_FakeRedis(),
    )
    assert out["moved"] == 0
    assert "invalid_resolution" in out.get("error", "")


def test_soft_time_limit_partial_no_customer_side_effects(monkeypatch):
    """Soft limit path must not enqueue publish/call/billing — only return partial."""
    from celery.exceptions import SoftTimeLimitExceeded

    from app.platform import boot_grace
    from app.tasks import staff_jobs

    side = {"wa": 0, "email": 0, "social": 0, "call": 0, "bill": 0}

    def _soft(_coro):
        try:
            _coro.close()
        except Exception:
            pass
        raise SoftTimeLimitExceeded()

    monkeypatch.setattr(boot_grace, "should_skip_boot_grace", lambda _j: False)
    monkeypatch.setattr(staff_jobs, "_run_async", _soft)
    out = staff_jobs.run_staff_job.run("content")
    assert out == {
        "ok": True,
        "job": "content",
        "partial": True,
        "reason": "soft_time_limit",
    }
    assert side == {"wa": 0, "email": 0, "social": 0, "call": 0, "bill": 0}
