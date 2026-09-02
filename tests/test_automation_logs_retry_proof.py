"""ADR-065 deeper logs part 2/3 (no-migration slice):
- `team_scheduler._run_job` accepts a `retry_count` (Celery `run_staff_job`
  threads `self.request.retries`), surfaced in the admin Automation Runs panel.
- The Automation Runs panel renders a Proof column from existing fields
  (`meta_json.path` report artifact / a URL in `output_summary`) — no DB column,
  so no migration on the live prod DB.
"""

import inspect
from pathlib import Path

HTML = (
    Path(__file__).resolve().parents[1] / "frontend" / "delivery_command_center.html"
).read_text(encoding="utf-8")


def test_run_job_accepts_retry_count():
    from app.platform import team_scheduler

    sig = inspect.signature(team_scheduler._run_job)
    assert "retry_count" in sig.parameters
    assert sig.parameters["retry_count"].default == 0


def test_run_staff_job_threads_retries():
    # The Celery wrapper must pass the current retry number into _run_job.
    src = (Path(__file__).resolve().parents[1] / "app" / "tasks" / "staff_jobs.py").read_text(
        encoding="utf-8"
    )
    assert "retry_count=int(getattr(self.request" in src


def test_panel_has_proof_column():
    assert "<th>Proof</th>" in HTML
    assert "meta_json" in HTML  # proof parsed from existing meta_json field
    assert "proofCell" in HTML


def test_panel_retries_column_still_present():
    # No-removal guard for the existing Retries column.
    assert "<th>Retries</th>" in HTML
