"""The HTTP histogram must be accurate at its production alert boundary."""

from app.middleware.http_metrics import _BUCKETS


def test_latency_histogram_has_exact_two_second_slo_bucket() -> None:
    assert tuple(sorted(_BUCKETS)) == _BUCKETS
    assert (1.5, 2.0, 2.5) == tuple(bucket for bucket in _BUCKETS if 1.5 <= bucket <= 2.5)
