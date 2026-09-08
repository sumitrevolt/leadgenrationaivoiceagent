"""W1.13 — per-job Prometheus metrics (dependency-free), fed from record_run.

Core marketing/agent engines emitted zero Prometheus job metrics — no way to see, in
Grafana/Alertmanager, whether a job succeeded/failed or how long it took. This adds
per-job success/fail counts + duration, recorded at the ONE common completion path
(`automation_health.record_run`, which W1.2 made status-accurate) and exposed on
/metrics in the existing dependency-free text-exposition style (prometheus_client is
not vendored). Flag-gated exposition, fail-open.
"""

from __future__ import annotations

import app.platform.job_metrics as jm


def _reset():
    jm._runs_total.clear()
    jm._dur_sum.clear()
    jm._dur_count.clear()


def test_record_accumulates_counts_and_duration():
    _reset()
    jm.record("content", True, 1.5)
    jm.record("content", True, 2.0)
    jm.record("content", False, 0.5)
    assert jm._runs_total[("content", "ok")] == 2
    assert jm._runs_total[("content", "fail")] == 1
    assert round(jm._dur_sum["content"], 2) == 4.0
    assert jm._dur_count["content"] == 3


def test_render_gated_by_flag(monkeypatch):
    _reset()
    jm.record("content", True, 1.0)
    monkeypatch.delenv("PROMETHEUS_JOB_METRICS", raising=False)
    assert jm.render_job_metrics() == [], "exposition must be empty unless flag enabled"
    monkeypatch.setenv("PROMETHEUS_JOB_METRICS", "1")
    lines = jm.render_job_metrics()
    assert any(ln == 'leadgen_job_runs_total{job="content",status="ok"} 1' for ln in lines)
    assert any(ln.startswith("leadgen_job_duration_seconds_sum") for ln in lines)


def test_record_run_wires_job_metrics(monkeypatch, tmp_path):
    import app.platform.automation_health as ah

    calls = []
    monkeypatch.setattr(jm, "record", lambda job, ok, seconds=0.0: calls.append((job, ok, seconds)))
    monkeypatch.setattr(ah, "_RUNS", lambda: str(tmp_path / "runs.jsonl"))
    monkeypatch.setattr(ah, "_BEATS", lambda: str(tmp_path / "beats.json"))

    ah.record_run("testjob", True, 1.25)

    assert ("testjob", True, 1.25) in calls, "record_run must feed job_metrics.record"
