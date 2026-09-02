"""W4.3 — Office momentum alerts built on W4.2 day-over-day trends.

Trends give numbers; this turns worsening momentum into an explicit founder signal in
the snapshot: stuck leads rising (mid-funnel jamming) or hot leads falling (top-funnel
slowing). Deterministic, read-only, thresholds env-tunable, never raises.
"""

from __future__ import annotations

from app.platform import office_hq


def _snap(hot_delta=0, stuck_delta=0, hot_now=5, stuck_now=5):
    return {
        "trends": {
            "day_over_day": {
                "hot": {"now": hot_now, "prev": hot_now - hot_delta, "delta": hot_delta},
                "warm": {"now": 3, "prev": 3, "delta": 0},
                "stuck": {"now": stuck_now, "prev": stuck_now - stuck_delta, "delta": stuck_delta},
            }
        }
    }


def test_stuck_rising_alert(monkeypatch):
    monkeypatch.delenv("OFFICE_STUCK_ALERT_DELTA", raising=False)
    alerts = office_hq.build_trend_alerts(_snap(stuck_delta=5, stuck_now=8))
    assert "stuck_rising" in [a["signal"] for a in alerts]


def test_hot_falling_alert(monkeypatch):
    monkeypatch.delenv("OFFICE_HOT_ALERT_DROP", raising=False)
    alerts = office_hq.build_trend_alerts(_snap(hot_delta=-4, hot_now=2))
    assert "hot_falling" in [a["signal"] for a in alerts]


def test_no_alert_on_small_moves():
    assert office_hq.build_trend_alerts(_snap(stuck_delta=1, hot_delta=-1)) == []


def test_no_trends_no_alerts_and_never_raises():
    assert office_hq.build_trend_alerts({}) == []
    assert office_hq.build_trend_alerts(None) == []
