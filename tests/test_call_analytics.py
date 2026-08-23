"""P4 (2026-06-28): Lekha's call-analytics engine — KPI aggregation from durable
logs. Import-safe, returns a complete dict, never raises."""

from __future__ import annotations


def test_compute_call_kpis_shape():
    from app.voice_agent.call_analytics import compute_call_kpis

    k = compute_call_kpis(7)
    for key in (
        "window_days",
        "web_calls",
        "avg_duration_s",
        "reply_latency_ms",
        "deadair_rate_pct",
        "bookings",
        "booking_rate_pct",
        "generated_at",
    ):
        assert key in k, key
    assert k["window_days"] == 7
    assert isinstance(k["reply_latency_ms"], dict)


def test_compute_call_kpis_clamps_days():
    from app.voice_agent.call_analytics import compute_call_kpis

    assert compute_call_kpis(0)["window_days"] == 7  # 0 → falsy → default 7
    assert compute_call_kpis(-5)["window_days"] == 1  # negative clamps to 1
    assert compute_call_kpis(999)["window_days"] == 90


def test_new_voice_staff_registered():
    from app.platform.team import STAFF

    assert STAFF["lekha"]["product"] == "voice"
    assert STAFF["raksha"]["product"] == "voice"
