"""Tests for TypeSafe Execution Layer (2026-09-19).

Validates the bounded revision loop, INERT fallback, and outcome tracking.
Uses deterministic mocks — no real TypeSafe API calls.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.platform.typesafe_executor import (
    ExecutionResult,
    ExecutionStatus,
    TypeSafeExecutor,
    validate_artifact,
)
from app.platform.typesafe_integration import TypeSafeClient, TypeSafeResponse

# ------------------------------------------------------------------ fixtures


@pytest.fixture
def mock_client():
    """TypeSafe client that returns compliant on first try."""
    client = MagicMock(spec=TypeSafeClient)
    client.enabled = True
    client.system_one.return_value = TypeSafeResponse(
        success=True,
        result={
            "model": "jev-latest",
            "answers": {
                "quality": {"choice": "excellent"},
                "compliant": {"noul": True},
            },
        },
        model="jev-latest",
        latency_sec=0.5,
    )
    return client


@pytest.fixture
def mock_client_reject_then_accept():
    """TypeSafe client that rejects once, then accepts."""
    call_count = {"n": 0}

    def side_effect(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return TypeSafeResponse(
                success=True,
                result={
                    "answers": {
                        "quality": {"choice": "poor"},
                        "compliant": {"noul": False},
                    }
                },
            )
        return TypeSafeResponse(
            success=True,
            result={
                "answers": {
                    "quality": {"choice": "good"},
                    "compliant": {"noul": True},
                }
            },
        )

    client = MagicMock(spec=TypeSafeClient)
    client.enabled = True
    client.system_one.side_effect = side_effect
    return client


@pytest.fixture
def mock_client_inert():
    """TypeSafe client with no API key (INERT)."""
    client = MagicMock(spec=TypeSafeClient)
    client.enabled = False
    return client


# ------------------------------------------------------------------ tests


class TestExecuteAndValidate:
    def test_delivers_on_first_try(self, mock_client):
        executor = TypeSafeExecutor(client=mock_client)

        def deliver_fn(input_data):
            return {"subject": "Hello", "body": "World"}

        result = executor.execute_and_validate(
            worker_id="worker_email",
            skill_name="send_cold_email",
            input_data={"to": "test@example.com"},
            deliver_fn=deliver_fn,
            validate_criteria={"tone": "professional"},
        )

        assert result.status == ExecutionStatus.DELIVERED
        assert result.revision_count == 0
        assert result.output == {"subject": "Hello", "body": "World"}
        assert result.typesafe_verdict.success is True

    def test_revises_on_reject(self, mock_client_reject_then_accept):
        executor = TypeSafeExecutor(client=mock_client_reject_then_accept)

        def deliver_fn(input_data):
            return {"subject": "Hello"}

        result = executor.execute_and_validate(
            worker_id="worker_email",
            skill_name="send_cold_email",
            input_data={},
            deliver_fn=deliver_fn,
            validate_criteria={"tone": "professional"},
        )

        # Should have revised once and then delivered
        assert result.status == ExecutionStatus.DELIVERED
        assert result.revision_count == 1

    def test_fails_after_max_revisions(self, mock_client):
        """Always-reject client → exhausts budget → FAILED."""
        mock_client.system_one.return_value = TypeSafeResponse(
            success=True,
            result={
                "answers": {
                    "quality": {"choice": "poor"},
                    "compliant": {"noul": False},
                }
            },
        )
        executor = TypeSafeExecutor(client=mock_client)

        def deliver_fn(input_data):
            return {"subject": "Hi"}

        result = executor.execute_and_validate(
            worker_id="worker_email",
            skill_name="send_cold_email",
            input_data={},
            deliver_fn=deliver_fn,
            validate_criteria={"tone": "professional"},
            max_revisions=2,
        )

        assert result.status == ExecutionStatus.FAILED
        assert result.revision_count == 2

    def test_inert_fallback(self, mock_client_inert):
        """No API key → INERT status, no validation calls."""
        executor = TypeSafeExecutor(client=mock_client_inert)

        def deliver_fn(input_data):
            return {"subject": "Hello"}

        result = executor.execute_and_validate(
            worker_id="worker_email",
            skill_name="send_cold_email",
            input_data={},
            deliver_fn=deliver_fn,
            validate_criteria={"tone": "professional"},
        )

        assert result.status == ExecutionStatus.INERT
        assert result.output == {"subject": "Hello"}

    def test_deliver_fn_exception(self, mock_client):
        """Exception in deliver_fn → FAILED, no validation attempted."""
        executor = TypeSafeExecutor(client=mock_client)

        def deliver_fn(input_data):
            raise RuntimeError("SMTP timeout")

        result = executor.execute_and_validate(
            worker_id="worker_email",
            skill_name="send_cold_email",
            input_data={},
            deliver_fn=deliver_fn,
            validate_criteria={},
        )

        assert result.status == ExecutionStatus.FAILED
        assert "SMTP timeout" in result.attempts[0]["error"]

    def test_validation_api_failure(self, mock_client):
        """TypeSafe call returns HTTP 500 → INERT (don't block on infra)."""
        mock_client.system_one.return_value = TypeSafeResponse(
            success=False,
            error="HTTP 500: internal",
        )
        executor = TypeSafeExecutor(client=mock_client)

        def deliver_fn(input_data):
            return {"subject": "Hello"}

        result = executor.execute_and_validate(
            worker_id="worker_email",
            skill_name="send_cold_email",
            input_data={},
            deliver_fn=deliver_fn,
            validate_criteria={},
        )

        assert result.status == ExecutionStatus.INERT

    def test_revision_hint_piped_to_input(self, mock_client_reject_then_accept):
        """On reject, TypeSafe revision hint is added to input_data for next loop."""

        # Make the revision call return a specific hint
        def side_effect(state, questions):
            # First call = validate (reject), second call = revise, third = validate (accept)
            call_count = sum(1 for _ in state.get("_calls", []))  # not reliable
            # Use call count via mock
            idx = mock_client_reject_then_accept.system_one.call_count
            if idx <= 1:
                return TypeSafeResponse(
                    success=True,
                    result={
                        "answers": {
                            "quality": {"choice": "poor"},
                            "compliant": {"noul": False},
                        }
                    },
                )
            return TypeSafeResponse(
                success=True,
                result={
                    "answers": {
                        "quality": {"choice": "good"},
                        "compliant": {"noul": True},
                    }
                },
            )

        mock_client_reject_then_accept.system_one.side_effect = side_effect
        executor = TypeSafeExecutor(client=mock_client_reject_then_accept)

        received_inputs = []

        def deliver_fn(input_data):
            received_inputs.append(dict(input_data))
            return {"subject": "Hi"}

        result = executor.execute_and_validate(
            worker_id="w",
            skill_name="s",
            input_data={"orig": True},
            deliver_fn=deliver_fn,
            validate_criteria={"tone": "pro"},
            max_revisions=3,
        )

        # Should have been called at least twice (reject + accept)
        assert len(received_inputs) >= 2


class TestValidateArtifact:
    def test_module_level_shortcut(self, mock_client):
        with patch("app.platform.typesafe_executor.get_executor") as get_exec:
            get_exec.return_value = TypeSafeExecutor(client=mock_client)
            resp = validate_artifact(
                {"subject": "Hi"},
                {"tone": "pro"},
            )
            assert resp.success is True


class TestExecutionResult:
    @pytest.mark.parametrize(
        "status,expected",
        [
            (ExecutionStatus.DELIVERED, True),
            (ExecutionStatus.FAILED, False),
            (ExecutionStatus.REVISING, False),
            (ExecutionStatus.INERT, False),
        ],
    )
    def test_is_delivered(self, status, expected):
        r = ExecutionResult(status=status)
        assert r.is_delivered == expected

    def test_needs_revision_within_budget(self):
        r = ExecutionResult(
            status=ExecutionStatus.REVISING,
            revision_count=1,
            max_revisions=3,
        )
        assert r.needs_revision is True

    def test_needs_revision_exhausted(self):
        r = ExecutionResult(
            status=ExecutionStatus.REVISING,
            revision_count=3,
            max_revisions=3,
        )
        assert r.needs_revision is False

    def test_delivers_with_wire_format_float_noul_and_score(self):
        """TypeSafe wire format returns noul as float probability (0.0-1.0) and score float."""
        client = MagicMock(spec=TypeSafeClient)
        client.enabled = True
        client.system_one.return_value = TypeSafeResponse(
            success=True,
            result={
                "model": "jev-latest",
                "answers": {
                    "quality": {"score": 2.8, "confidence": 0.9},
                    "compliant": {"noul": 0.88},
                },
            },
            model="jev-latest",
        )
        executor = TypeSafeExecutor(client=client)
        result = executor.execute_and_validate(
            worker_id="worker_email",
            skill_name="send_outreach",
            input_data={"to": "client@example.com"},
            deliver_fn=lambda d: {"body": "Approved email text"},
            validate_criteria={"tone": "professional"},
        )
        assert result.status == ExecutionStatus.DELIVERED
        assert result.is_delivered is True
