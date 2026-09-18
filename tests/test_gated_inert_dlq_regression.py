"""DLQ misclassification regression for gated-inert tasks (PR #520).

When `_run_job()` returns `False`, the wrapper must distinguish:
  - Gated/inert: job intentionally disabled (provider/key missing, config not ready)
  - Real failure: transient error, connection issue, logic bug

Gated tasks must return early with `status: "gated_inert"` — NO retry, NO DLQ.
Real failures must still raise `RuntimeError` — existing retry/DLQ path unchanged.

Gold pattern follows tests/test_job_time_budget_dlq.py:
  - Uses staff_jobs.run_staff_job.run() wrapper (not manual reproduction)
  - Patches _run_async as synchronous helper (not AsyncMock)
  - Returns False from normal function
  - Patches boot_grace to avoid deferred retry path
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from celery.exceptions import CeleryError

from app.tasks import staff_jobs


class _RetrySentinel(CeleryError):
    """Deterministic sentinel to prove retry() was invoked."""


def test_gated_inert_returns_ok_not_raises():
    """Gated task returns status=gated_inert, NO retry, NO DLQ."""
    with (
        patch.object(staff_jobs, "_run_async", return_value=False),
        patch("app.platform.automation_health.gated_inert", return_value=True),
        patch("app.platform.boot_grace.should_skip_boot_grace", return_value=False),
        patch.object(staff_jobs.run_staff_job, "retry") as mock_retry,
    ):
        # Call the wrapper directly (gold pattern from test_job_time_budget_dlq.py)
        out = staff_jobs.run_staff_job.run("gsc_rank")

        # Should return early with gated_inert status
        assert out["ok"] is True
        assert out.get("status") == "gated_inert"
        assert out.get("job") == "gsc_rank"

        # retry must NOT be called for gated tasks
        mock_retry.assert_not_called()


def test_real_failure_still_raises():
    """Real failure → retry called with failure exception."""
    with (
        patch.object(staff_jobs, "_run_async", return_value=False),
        patch("app.platform.automation_health.gated_inert", return_value=False),
        patch("app.platform.boot_grace.should_skip_boot_grace", return_value=False),
        patch.object(staff_jobs.run_staff_job, "retry", side_effect=_RetrySentinel("retry-called")),
    ):
        # Production code: RuntimeError → except Exception → self.retry(exc=e)
        with pytest.raises(_RetrySentinel, match="retry-called"):
            staff_jobs.run_staff_job.run("prospect")


def test_gate_check_exception_falls_to_retry():
    """If gated_inert() raises, fall back to retry path (fail-open).

    When the gate check itself breaks, we treat it as a real failure and
    let the normal retry path handle it.
    """
    with (
        patch.object(staff_jobs, "_run_async", return_value=False),
        patch(
            "app.platform.automation_health.gated_inert", side_effect=RuntimeError("gate broken")
        ),
        patch("app.platform.boot_grace.should_skip_boot_grace", return_value=False),
        patch.object(staff_jobs.run_staff_job, "retry", side_effect=_RetrySentinel("retry-called")),
    ):
        # Exception in gate check → pass → RuntimeError → except Exception → self.retry(exc=e)
        with pytest.raises(_RetrySentinel, match="retry-called"):
            staff_jobs.run_staff_job.run("content")


def test_gated_inert_video_delivery_retry():
    """Specific regression: video_delivery_retry gated → no retry, no DLQ."""
    with (
        patch.object(staff_jobs, "_run_async", return_value=False),
        patch("app.platform.automation_health.gated_inert", return_value=True),
        patch("app.platform.boot_grace.should_skip_boot_grace", return_value=False),
        patch.object(staff_jobs.run_staff_job, "retry") as mock_retry,
    ):
        out = staff_jobs.run_staff_job.run("video_delivery_retry")

        assert out["ok"] is True
        assert out.get("status") == "gated_inert"
        mock_retry.assert_not_called()
