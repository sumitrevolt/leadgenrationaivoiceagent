"""Direct test of run_staff_job wrapper behavior for gated-inert fix.

This test invokes the actual run_staff_job Celery task wrapper with mocked
dependencies to prove the fix prevents false DLQ entries for gated-off jobs.

Fix for semantic bug (2026-09-18): when VIDEO_TELEGRAM_DELIVERY_ENABLED=0
(or any gated job OFF), team_scheduler._run_job returns ok=False and records
status="gated_inert" for observability. Before the fix, run_staff_job() treated
ok=False as a failure and raised RuntimeError, triggering Celery retry
(max_retries=2) and filling dlq:failed_tasks/dlq:dead with false positives.

After the fix, run_staff_job() checks automation_health.gated_inert(job) before
raising. If gated, returns {"ok": True, "job": job, "status": "gated_inert"}
— no retry, no DLQ.

Direct test proves:
1. gated_inert=True → run_staff_job.run() returns ok=True, no RuntimeError raised
2. gated_inert=False → run_staff_job.run() raises RuntimeError (triggers retry/DLQ)
3. gated_inert() exception → fail-closed, still raises RuntimeError
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestGatedInertDirectWrapper:
    """Directly exercise run_staff_job.run() Celery wrapper with mocked deps."""

    def test_gated_job_no_retry_triggered(self):
        """gated_inert=True → run_staff_job.run() returns ok=True, no self.retry() call.

        Direct proof: when _run_job returns False but job is gated, the wrapper
        must NOT raise RuntimeError (which triggers Celery retry → DLQ).
        """
        from app.tasks.staff_jobs import run_staff_job

        # Setup mock self (Celery task instance)
        mock_self = MagicMock()
        mock_self.request = MagicMock()
        mock_self.request.id = "test-task-id"
        mock_self.request.retries = 0

        # Track if retry was called
        retry_called = False

        def mock_retry(*args, **kwargs):
            nonlocal retry_called
            retry_called = True
            raise Exception("retry should not be called for gated job")

        mock_self.retry = mock_retry

        # Mock _run_async to return False (gated job returns False)
        with patch("app.tasks.staff_jobs._run_async", new_callable=AsyncMock, return_value=False):
            # Mock gated_inert to return True (job is gated)
            with patch("app.tasks.staff_jobs.automation_health.gated_inert", return_value=True):
                # Call the actual run_staff_job.run() wrapper
                result = run_staff_job.run(mock_self, job="video_delivery_retry")

                # Should return gated_inert result, NOT raise
                assert result["ok"] is True
                assert result["status"] == "gated_inert"
                assert "error" not in result
                assert not retry_called, "Celery retry should NOT be called for gated job"

    def test_real_failure_triggers_retry(self):
        """gated_inert=False → run_staff_job.run() raises RuntimeError, triggers retry.

        Direct proof: when _run_job returns False and job is NOT gated, the wrapper
        must raise RuntimeError (which triggers Celery retry → DLQ).
        """
        from app.tasks.staff_jobs import run_staff_job

        # Setup mock self
        mock_self = MagicMock()
        mock_self.request = MagicMock()
        mock_self.request.id = "test-task-id"
        mock_self.request.retries = 0

        # Track if retry was called
        retry_called = False

        def mock_retry(*args, **kwargs):
            nonlocal retry_called
            retry_called = True

        mock_self.retry = mock_retry

        # Mock _run_async to return False (failure)
        with patch("app.tasks.staff_jobs._run_async", new_callable=AsyncMock, return_value=False):
            # Mock gated_inert to return False (NOT gated — real failure)
            with patch("app.tasks.staff_jobs.automation_health.gated_inert", return_value=False):
                # Should raise RuntimeError
                with pytest.raises(RuntimeError, match="reported failure"):
                    run_staff_job.run(mock_self, job="some_job")

                # Retry should have been called
                assert retry_called, "Celery retry SHOULD be called for real failure"

    def test_gated_inert_exception_fails_closed(self):
        """gated_inert() raises → fall through to RuntimeError (fail-closed).

        Safety proof: if the gate check itself breaks, we still treat it as failure.
        """
        from app.tasks.staff_jobs import run_staff_job

        # Setup mock self
        mock_self = MagicMock()
        mock_self.request = MagicMock()
        mock_self.request.id = "test-task-id"
        mock_self.request.retries = 0

        # Track if retry was called
        retry_called = False

        def mock_retry(*args, **kwargs):
            nonlocal retry_called
            retry_called = True

        mock_self.retry = mock_retry

        # Mock _run_async to return False
        with patch("app.tasks.staff_jobs._run_async", new_callable=AsyncMock, return_value=False):
            # Mock gated_inert to raise exception
            with patch("app.tasks.staff_jobs.automation_health.gated_inert", side_effect=Exception("boom")):
                # Should raise RuntimeError (fail-closed)
                with pytest.raises(RuntimeError):
                    run_staff_job.run(mock_self, job="video_delivery_retry")

                # Retry should have been called (fail-closed path)
                assert retry_called, "Celery retry SHOULD be called when gated_inert raises"

    def test_source_matches_fix(self):
        """Verify the source code contains the exact fix pattern.

        This proves the fix is actually in staff_jobs.py and not just in tests.
        """
        import inspect

        from app.tasks import staff_jobs

        # Get the source of run_staff_job
        source = inspect.getsource(staff_jobs.run_staff_job)

        # Verify the fix pattern exists
        assert "gated_inert" in source, "Fix pattern 'gated_inert' not found in run_staff_job"
        assert "automation_health" in source, (
            "Fix pattern 'automation_health' not found in run_staff_job"
        )
        assert 'return {"ok": True, "job": job, "status": "gated_inert"}' in source, (
            "Fix return pattern not found in run_staff_job"
        )
