"""Pure-python tests for app.billing.meter_watch + usage meter-failure recording.

No network / DB / real-LLM / real-redis. Redis llen + ntfy are monkeypatched.
"""

from __future__ import annotations

import importlib

import pytest


@pytest.fixture()
def mw(tmp_path, monkeypatch):
    """Fresh meter_watch module with DATA_DIR pointed at tmp + flag ON.

    Re-import so module-level threshold/cooldown env are picked up per-test.
    """
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("METER_ALERTS", "1")
    monkeypatch.setenv("METER_ALERT_GROWTH_THRESHOLD", "5")
    monkeypatch.setenv("METER_ALERT_COOLDOWN_SEC", "3600")
    import app.billing.meter_watch as _m

    _m = importlib.reload(_m)
    return _m


def _patch_llen(mw, monkeypatch, value):
    monkeypatch.setattr(mw, "_redis_list_len", lambda: value)


def _capture_alerts(mw, monkeypatch):
    fired = []
    monkeypatch.setattr(mw, "_alert", lambda count, delta: fired.append((count, delta)))
    return fired


def test_disabled_is_inert(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("METER_ALERTS", raising=False)
    import app.billing.meter_watch as _m

    _m = importlib.reload(_m)
    assert _m.enabled() is False
    out = _m.check_meter_failures()
    assert out["alerted"] is False
    assert out["reason"] == "disabled"


def test_redis_unavailable(mw, monkeypatch):
    _patch_llen(mw, monkeypatch, -1)
    out = mw.check_meter_failures()
    assert out == {"alerted": False, "reason": "redis_unavailable"}


def test_below_threshold_no_alert(mw, monkeypatch):
    fired = _capture_alerts(mw, monkeypatch)
    _patch_llen(mw, monkeypatch, 3)  # delta 3 < 5
    out = mw.check_meter_failures()
    assert out["alerted"] is False
    assert out["reason"] == "below_threshold"
    assert out["delta"] == 3
    assert fired == []


def test_growth_over_threshold_fires(mw, monkeypatch):
    fired = _capture_alerts(mw, monkeypatch)
    _patch_llen(mw, monkeypatch, 10)  # delta 10 >= 5
    out = mw.check_meter_failures()
    assert out["alerted"] is True
    assert out["delta"] == 10
    assert out["count"] == 10
    assert fired == [(10, 10)]


def test_cooldown_blocks_second_alert(mw, monkeypatch):
    fired = _capture_alerts(mw, monkeypatch)
    _patch_llen(mw, monkeypatch, 10)
    assert mw.check_meter_failures()["alerted"] is True
    # next run with more growth, but cooldown active -> no alert
    _patch_llen(mw, monkeypatch, 20)
    out = mw.check_meter_failures()
    assert out["alerted"] is False
    assert out["reason"] == "cooldown"
    assert len(fired) == 1  # only the first alert fired


def test_state_persists_last_count(mw, monkeypatch):
    _capture_alerts(mw, monkeypatch)
    _patch_llen(mw, monkeypatch, 4)
    mw.check_meter_failures()  # below threshold, but records last_count=4
    # now grows to 7 -> delta 3 (< 5) so still no alert (delta measured from 4)
    _patch_llen(mw, monkeypatch, 7)
    out = mw.check_meter_failures()
    assert out["delta"] == 3
    assert out["alerted"] is False


def test_trim_does_not_negative_delta(mw, monkeypatch):
    _capture_alerts(mw, monkeypatch)
    _patch_llen(mw, monkeypatch, 10)
    mw.check_meter_failures()
    # list got replayed/trimmed -> shorter; delta must clamp to 0, no crash
    _patch_llen(mw, monkeypatch, 2)
    out = mw.check_meter_failures()
    assert out["delta"] == 0
    assert out["alerted"] is False


def test_check_never_raises(mw, monkeypatch):
    def _boom():
        raise RuntimeError("redis blew up")

    # _redis_list_len itself is hardened, but ensure the public fn is robust even
    # if an internal helper raises unexpectedly.
    monkeypatch.setattr(mw, "_read_state", lambda: (_ for _ in ()).throw(ValueError("x")))
    _patch_llen(mw, monkeypatch, 10)
    # Should not propagate — meter_watch is best-effort. It may return a dict or
    # swallow; assert it does not raise.
    try:
        mw.check_meter_failures()
    except Exception as e:  # pragma: no cover
        pytest.fail(f"check_meter_failures raised: {e}")


# --------------------------------------------------------------------------- #
# usage.py fail-open meter-failure recording
# --------------------------------------------------------------------------- #
def test_usage_record_meter_failure_logs_and_lpushes(monkeypatch):
    import app.billing.usage as usage

    pushed = []

    class _FakeRedis:
        def lpush(self, key, val):
            pushed.append((key, val))

        def ltrim(self, key, a, b):
            pass

    class _FakeRedisMod:
        @staticmethod
        def from_url(url, socket_timeout=2):
            return _FakeRedis()

    monkeypatch.setenv("REDIS_URL", "redis://fake:6379/0")
    monkeypatch.setitem(__import__("sys").modules, "redis", _FakeRedisMod)

    usage._record_meter_failure({"client_id": "c1", "kind": "minutes", "duration_seconds": 120})
    assert len(pushed) == 1
    assert pushed[0][0] == "billing:meter_failures"
    assert "minutes" in pushed[0][1]


def test_usage_record_meter_failure_no_redis_url(monkeypatch):
    import app.billing.usage as usage

    monkeypatch.delenv("REDIS_URL", raising=False)
    # Must not raise even with no redis configured.
    usage._record_meter_failure({"client_id": "c1", "kind": "minutes"})
