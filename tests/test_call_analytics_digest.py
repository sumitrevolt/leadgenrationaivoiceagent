"""Tests for the Lekha call-KPI daily digest (Task 3 — fixes missing log_event wiring)."""

from __future__ import annotations

from unittest.mock import patch

from app.voice_agent import call_analytics


def test_run_daily_digest_calls_compute_call_kpis():
    fake_kpis = {
        "window_days": 1,
        "web_calls": 12,
        "avg_duration_s": 145.2,
        "qualified_phone": 4,
        "booking_rate_pct": 10.0,
        "reply_latency_ms": {"p50": 900, "p95": 2200},
    }
    with patch.object(call_analytics, "compute_call_kpis", return_value=fake_kpis) as m:
        result = call_analytics.run_daily_digest()
    m.assert_called_once_with(days=1)
    assert result == fake_kpis


def test_run_daily_digest_logs_event_under_lekha():
    fake_kpis = {"web_calls": 5, "avg_duration_s": 88.0, "qualified_phone": 2}
    with patch.object(call_analytics, "compute_call_kpis", return_value=fake_kpis):
        with patch("app.platform.team.log_event") as mock_log:
            call_analytics.run_daily_digest()
    mock_log.assert_called_once()
    args, kwargs = mock_log.call_args
    assert args[0] == "lekha"
    assert args[1] == "call_kpi_digest"
    detail = args[2] if len(args) > 2 else kwargs.get("detail", "")
    assert "Aaj 5 calls · 2 qualified" in detail


def test_run_daily_digest_never_raises_on_compute_failure():
    with patch.object(call_analytics, "compute_call_kpis", side_effect=RuntimeError("boom")):
        result = call_analytics.run_daily_digest()
    assert result == {}
