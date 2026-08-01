"""The HTTP histogram must be accurate at its production alert boundary."""

import pytest

from app.middleware.http_metrics import _BUCKETS, enabled


def test_latency_histogram_has_exact_two_second_slo_bucket() -> None:
    assert tuple(sorted(_BUCKETS)) == _BUCKETS
    assert (1.5, 2.0, 2.5) == tuple(bucket for bucket in _BUCKETS if 1.5 <= bucket <= 2.5)


def test_http_metrics_default_on_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unset flag => production default-ON so SLO alerts can fire (2026-08-01)."""
    monkeypatch.delenv("PROMETHEUS_HTTP_METRICS", raising=False)
    monkeypatch.setenv("APP_ENV", "production")
    assert enabled() is True


def test_http_metrics_default_off_in_development(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PROMETHEUS_HTTP_METRICS", raising=False)
    monkeypatch.setenv("APP_ENV", "development")
    assert enabled() is False


def test_http_metrics_explicit_off_wins_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROMETHEUS_HTTP_METRICS", "0")
    monkeypatch.setenv("APP_ENV", "production")
    assert enabled() is False


def test_http_metrics_explicit_on_wins_in_development(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROMETHEUS_HTTP_METRICS", "1")
    monkeypatch.setenv("APP_ENV", "development")
    assert enabled() is True
