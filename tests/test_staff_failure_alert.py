"""W1.14 — staff-job failures must emit a metric + ntfy alert (were silent).

Bug: run_qa/run_trainer/run_ops/run_digest signalled failure only by RETURNING
`{"error": …}`. Because they return (not raise), the scheduler wrapper records them
as ok=True (dead-man switch + W1.13 job metric think they succeeded), and nobody is
paged. Fix: a dedicated `leadgen_job_errors_total{job}` counter + an OPS_ALERTS-gated
ntfy alert, both driven from `_staff_job_failed`, called at each job's error path.
"""
from __future__ import annotations

import app.agents.staff as staff
import app.platform.job_metrics as jm


def test_record_error_counter_and_render(monkeypatch):
    jm._errors_total.clear()
    jm.record_error("trainer")
    jm.record_error("trainer")
    assert jm._errors_total["trainer"] == 2
    monkeypatch.setenv("PROMETHEUS_JOB_METRICS", "1")
    lines = jm.render_job_metrics()
    assert any(ln == 'leadgen_job_errors_total{job="trainer"} 2' for ln in lines)


def test_staff_job_failed_records_and_alerts(monkeypatch):
    jm._errors_total.clear()
    alerts = []
    monkeypatch.setattr(
        "app.platform.ops_alerts.alert_staff_failure",
        lambda job, detail="": alerts.append((job, detail)),
    )
    staff._staff_job_failed("qa", "boom")
    assert jm._errors_total.get("qa") == 1, "staff failure must bump the error counter"
    assert ("qa", "boom") in alerts, "staff failure must fire the ntfy alert"
