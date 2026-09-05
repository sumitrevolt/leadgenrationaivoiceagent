"""Daily social post registration + stale-sweep tests (2026-09-05).

Regression guard: run_daily_social_post was previously a PLAIN function — the
3x daily beat entries sent "app.tasks.daily_social_post.run_daily_social_post"
to the worker, which rejected it as unregistered (silent daily job loss).
These tests pin (a) task registration, (b) sweep idempotency, (c) INERT
default, (d) TRAI-window + compliance-gate skips, (e) success markers.
"""

from __future__ import annotations

import datetime

import pytest

from app.tasks import daily_social_post as dsp


_IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))


class _FakeRedis:
    """Minimal get/set store with TTL args ignored (idempotency semantics only)."""

    def __init__(self):
        self.store: dict[str, str] = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ex=None):
        self.store[key] = str(value)
        return True


@pytest.fixture()
def fake_redis(monkeypatch):
    r = _FakeRedis()
    monkeypatch.setattr(dsp, "_redis_client", lambda: r)
    return r


@pytest.fixture()
def sweep_armed(monkeypatch):
    monkeypatch.setenv("SOCIAL_STALE_SWEEP", "1")


@pytest.fixture(autouse=True)
def _gates_pass(monkeypatch):
    """Local env has no prod creds — real check_gates() returns open gates.
    Default: all gates pass; the gates-skip test overrides in its body."""
    monkeypatch.setattr(dsp, "check_gates", lambda: {})


def _sweep_at(hour: int, minute: int = 30):
    return dsp.run_social_stale_sweep.run(
        datetime.datetime(2026, 9, 5, hour, minute, tzinfo=_IST)
    )


def test_social_tasks_registered():
    """THE regression guard: beat task names must be registered Celery tasks."""
    from app.worker import celery_app

    assert "app.tasks.daily_social_post.run_daily_social_post" in celery_app.tasks
    assert "app.tasks.daily_social_post.run_social_stale_sweep" in celery_app.tasks


def test_sweep_inert_by_default(monkeypatch, fake_redis):
    monkeypatch.delenv("SOCIAL_STALE_SWEEP", raising=False)
    result = dsp.run_social_stale_sweep.run()
    assert result["status"] == "inert"


def test_sweep_fires_once_when_stale(monkeypatch, fake_redis, sweep_armed):
    fired: list[tuple] = []

    class _Stub:
        @staticmethod
        def delay(*a, **kw):
            fired.append((a, kw))
            return None

    monkeypatch.setattr(dsp, "run_daily_social_post", _Stub)

    first = _sweep_at(10, 30)
    assert first["status"] == "rescheduled"
    assert len(fired) == 1
    assert fake_redis.store[dsp.SWEEP_FIRED_KEY] == "2026-09-05"

    second = _sweep_at(11, 30)
    assert second["status"] == "already_swept"
    assert len(fired) == 1  # idempotent: no second enqueue


def test_sweep_healthy_when_success_marker_today(fake_redis, sweep_armed):
    fake_redis.store[dsp.SWEEP_SUCCESS_KEY] = "2026-09-05"
    result = _sweep_at(10, 30)
    assert result["status"] == "healthy"
    assert result["last_success"] == "2026-09-05"


def test_sweep_outside_trai_window_skips(fake_redis, sweep_armed, monkeypatch):
    called: list[tuple] = []

    class _Stub:
        @staticmethod
        def delay(*a, **kw):
            called.append((a, kw))

    monkeypatch.setattr(dsp, "run_daily_social_post", _Stub)
    result = _sweep_at(20, 30)  # 8:30pm — outside 9am-7pm
    assert result["status"] == "skipped"
    assert result["reason"] == "outside_trai_window"
    assert called == []
    assert dsp.SWEEP_FIRED_KEY not in fake_redis.store


def test_sweep_open_gates_skip(fake_redis, sweep_armed, monkeypatch):
    monkeypatch.setattr(
        dsp, "check_gates", lambda: {"voice": "blocked"}
    )
    result = _sweep_at(10, 30)
    assert result["status"] == "skipped"
    assert result["reason"] == "open_compliance_gates"


def test_sweep_redis_unavailable_skips(monkeypatch, sweep_armed):
    monkeypatch.setattr(dsp, "_redis_client", lambda: None)
    result = _sweep_at(10, 30)
    assert result["status"] == "skipped"
    assert result["reason"] == "redis_unavailable"


def test_success_marker_set_on_posted_result(fake_redis):
    dsp._mark_success_if_any(
        {"own_brand": {"posted": True}, "clients": [{"posted": False}]}
    )
    assert fake_redis.store[dsp.SWEEP_SUCCESS_KEY] == datetime.datetime.now(
        _IST
    ).strftime("%Y-%m-%d")


def test_success_marker_not_set_when_nothing_posted(fake_redis):
    dsp._mark_success_if_any(
        {"own_brand": {"posted": False}, "clients": [{"posted": False}]}
    )
    assert dsp.SWEEP_SUCCESS_KEY not in fake_redis.store


def test_beat_sweep_entry_wired():
    from app.worker import celery_app

    entry = (celery_app.conf.beat_schedule or {}).get("staff-social-stale-sweep")
    assert entry, "staff-social-stale-sweep beat entry missing"
    assert entry["task"] == "app.tasks.daily_social_post.run_social_stale_sweep"


def test_parity_beat_targets_stay_clean():
    from app.platform import scheduler_parity as sp

    assert sp.beat_task_targets_ok() == []
