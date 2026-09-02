"""Dependency-free per-job Prometheus metrics (W1.13).

Core marketing/agent engines emitted zero Prometheus job metrics. This records
per-job success/fail counts + total duration, fed from the ONE common completion
path (``automation_health.record_run`` — which W1.2 made status-accurate) so every
scheduler job is covered without touching each engine.

Design mirrors ``app/middleware/http_metrics.py``:
- Dependency-free (``prometheus_client`` is not vendored) — plain dicts + hand-built
  text exposition appended to /metrics.
- asyncio single-threaded per worker → plain dict increments are safe (no lock).
- Fail-open: a recording error never affects the caller.
- Flag-gated exposition (``PROMETHEUS_JOB_METRICS``) → additive rollout, metric
  surface unchanged until enabled.
- Bounded cardinality: ``job`` (truncated) × ``status`` (ok/fail); ~40 known jobs.
"""

from __future__ import annotations

import os

# (job, status) -> run count
_runs_total: dict[tuple[str, str], int] = {}
# job -> total seconds / run count (for average duration)
_dur_sum: dict[str, float] = {}
_dur_count: dict[str, int] = {}
# job -> error-return count (staff jobs returning {"error":...} instead of raising, W1.14)
_errors_total: dict[str, int] = {}


def enabled() -> bool:
    return os.getenv("PROMETHEUS_JOB_METRICS", "").lower() in ("1", "true", "yes", "on")


def record(job: str, ok: bool, seconds: float = 0.0) -> None:
    """Record one job run. Fail-open, fast. Always accumulates (cheap); the flag only
    gates EXPOSITION, so metrics are ready the moment it's enabled."""
    try:
        j = (job or "?")[:40]
        status = "ok" if ok else "fail"
        _runs_total[(j, status)] = _runs_total.get((j, status), 0) + 1
        s = float(seconds)
        if s >= 0:
            _dur_sum[j] = _dur_sum.get(j, 0.0) + s
            _dur_count[j] = _dur_count.get(j, 0) + 1
    except Exception:
        pass


def record_error(job: str) -> None:
    """W1.14: staff job jo {"error":...} return karta (raise nahi) — dedicated error
    counter (record_run ke ok=True se double-count avoid karta). Fail-open."""
    try:
        j = (job or "?")[:40]
        _errors_total[j] = _errors_total.get(j, 0) + 1
    except Exception:
        pass


def _esc(v: str) -> str:
    return v.replace("\\", "\\\\").replace('"', '\\"')


def render_job_metrics() -> list[str]:
    """Prometheus text-exposition lines. Empty if disabled or nothing recorded."""
    if not enabled():
        return []
    out: list[str] = []
    try:
        if _runs_total:
            out.append("# HELP leadgen_job_runs_total Scheduler/agent job runs by status.")
            out.append("# TYPE leadgen_job_runs_total counter")
            for (job, status), n in sorted(_runs_total.items()):
                out.append(f'leadgen_job_runs_total{{job="{_esc(job)}",status="{status}"}} {n}')
        if _dur_count:
            out.append("# HELP leadgen_job_duration_seconds_sum Total job run seconds.")
            out.append("# TYPE leadgen_job_duration_seconds_sum counter")
            for job, s in sorted(_dur_sum.items()):
                out.append(f'leadgen_job_duration_seconds_sum{{job="{_esc(job)}"}} {round(s, 3)}')
            out.append("# HELP leadgen_job_duration_seconds_count Job runs (for avg = sum/count).")
            out.append("# TYPE leadgen_job_duration_seconds_count counter")
            for job, c in sorted(_dur_count.items()):
                out.append(f'leadgen_job_duration_seconds_count{{job="{_esc(job)}"}} {c}')
        if _errors_total:
            out.append("# HELP leadgen_job_errors_total Staff jobs that returned an error.")
            out.append("# TYPE leadgen_job_errors_total counter")
            for job, n in sorted(_errors_total.items()):
                out.append(f'leadgen_job_errors_total{{job="{_esc(job)}"}} {n}')
    except Exception:
        return []
    return out
