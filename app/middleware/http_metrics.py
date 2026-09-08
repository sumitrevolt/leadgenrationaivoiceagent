"""Dependency-free Prometheus HTTP metrics (OBS-001 council fix 2026-06-26).

The /metrics endpoint historically emitted only custom ``leadgen_*`` gauges, so
the two most important SLO alerts in monitoring/alert_rules.yml —
``HighHttp5xxRate`` (needs ``http_requests_total{status=~"5.."}``) and
``HighRequestLatencyP95`` (needs ``http_request_duration_seconds_bucket{le}``) —
referenced metrics that were never produced and could therefore never fire.

This module records those two series in-process with ZERO new dependencies
(prometheus_client is not vendored), matching the existing hand-built text
exposition in app/api/health.py. The exposition is read by
``render_http_metrics()`` and appended to the /metrics response.

Design constraints honoured for this project:
- Pure-ASGI middleware (not BaseHTTPMiddleware) → WebSocket/streaming voice paths
  pass straight through, never wrapped.
- asyncio is single-threaded per worker → plain dict increments are safe (no lock,
  no ``await`` between read-modify-write).
- Fail-open everywhere: a recording error never affects the response.
- Flag-gated: active when ``PROMETHEUS_HTTP_METRICS`` is truthy, OR by default in
  production (SLO alerts need these series — 2026-08-01 enterprise audit fix).
  Explicit ``PROMETHEUS_HTTP_METRICS=0|false|off`` still turns it off anywhere.
- Bounded cardinality: labels are ``method`` + ``status`` only (no raw path), and
  the latency histogram is global (``le`` only). ~tens of series, never unbounded.
"""

from __future__ import annotations

import os
import time

# Prometheus-style latency buckets (seconds). Keep exact buckets around the 2s
# alert boundary: histogram_quantile linearly interpolates inside a bucket, so
# the old 1.0 -> 2.5 gap could report p95 >2s when every real request was <2s.
# +Inf is emitted separately.
_BUCKETS: tuple[float, ...] = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    1.5,
    2.0,
    2.5,
    5.0,
    10.0,
)

# (method, status) -> request count
_req_total: dict[tuple[str, str], int] = {}
# le-bound -> count of observations <= bound (already cumulative by construction)
_lat_buckets: dict[float, int] = dict.fromkeys(_BUCKETS, 0)
_lat_inf: int = 0
_lat_sum: float = 0.0
_lat_count: int = 0


def _is_prod() -> bool:
    return (os.getenv("APP_ENV") or os.getenv("ENVIRONMENT") or "").strip().lower() == "production"


def enabled() -> bool:
    raw = os.getenv("PROMETHEUS_HTTP_METRICS", "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "off", "no"):
        return False
    # Unset → default-on in production so SLO alerts (HighHttp5xxRate /
    # HighRequestLatencyP95) can actually fire; additive elsewhere (dev keeps
    # the metric surface unchanged unless explicitly enabled).
    return _is_prod()


def _record(method: str, status: int, dur: float) -> None:
    global _lat_inf, _lat_sum, _lat_count
    key = (method, str(status))
    _req_total[key] = _req_total.get(key, 0) + 1
    for b in _BUCKETS:
        if dur <= b:
            _lat_buckets[b] += 1
    _lat_inf += 1
    _lat_sum += dur
    _lat_count += 1


class HttpMetricsMiddleware:
    """Pure-ASGI middleware: times each HTTP request and records its status."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET")
        status_holder = {"code": 500}  # default to 5xx if the app never sends a start
        start = time.perf_counter()

        async def _send(message):
            if message.get("type") == "http.response.start":
                status_holder["code"] = message.get("status", 500)
            await send(message)

        try:
            await self.app(scope, receive, _send)
        finally:
            try:
                _record(method, status_holder["code"], time.perf_counter() - start)
            except Exception:
                pass  # metrics never break the request path


def render_http_metrics() -> list[str]:
    """Prometheus text exposition for the HTTP metrics. Empty when disabled."""
    if not enabled():
        return []
    lines: list[str] = [""]
    lines.append("# HELP http_requests_total Total HTTP requests by method and status")
    lines.append("# TYPE http_requests_total counter")
    for (method, status), n in list(_req_total.items()):
        lines.append(f'http_requests_total{{method="{method}",status="{status}"}} {n}')
    lines.append("")
    lines.append("# HELP http_request_duration_seconds HTTP request latency in seconds")
    lines.append("# TYPE http_request_duration_seconds histogram")
    for b in _BUCKETS:
        lines.append(f'http_request_duration_seconds_bucket{{le="{b}"}} {_lat_buckets[b]}')
    lines.append(f'http_request_duration_seconds_bucket{{le="+Inf"}} {_lat_inf}')
    lines.append(f"http_request_duration_seconds_sum {_lat_sum}")
    lines.append(f"http_request_duration_seconds_count {_lat_count}")
    return lines
