"""Tests for Hermes3D real coordinator integration.

Verifies:
1. Unsupported actions are rejected with explicit error
2. Supported actions create real persisted tasks
3. Idempotent retry returns same task
4. Real handler execution with verifiable effects
"""

from __future__ import annotations

import pytest

from app.platform.hermes3d_bridge import Hermes3DBridge, get_hermes3d_bridge


def test_handle_command_rejects_unsupported_action():
    """Bridge must reject unsupported actions with explicit error."""
    bridge = Hermes3DBridge()
    result = bridge.handle_command("destroy_all_evidence", target_agent="isha")
    assert result["success"] is False
    assert result["error"] == "unsupported_action"
    assert "destroy_all_evidence" in result["message"]


def test_handle_command_creates_real_canonical_task():
    """Command creates a real persisted task in canonical ledger."""
    bridge = Hermes3DBridge()
    result = bridge.handle_command("run_cycle", target_agent="isha", parameters={"test": True})
    assert result["success"] is True
    assert "task_id" in result
    assert result["is_new"] is True
    assert result["status"] in ("DONE", "REVIEW", "RUNNING")

    # Verify task persisted in ledger
    from app.platform.automation_orchestrator import DurableTaskStore
    store = DurableTaskStore()
    task = store.get(result["task_id"])
    assert task is not None
    assert task.owner_bot == "guardian"
    assert task.input_payload["action"] == "run_cycle"


def test_handle_command_idempotent_retry():
    """Retrying identical command returns existing task."""
    bridge = Hermes3DBridge()
    params = {"idempotent_key": "test-123"}
    result1 = bridge.handle_command("status_check", target_agent="isha", parameters=params)
    result2 = bridge.handle_command("status_check", target_agent="isha", parameters=params)
    assert result1["success"] is True
    assert result2["success"] is True
    assert result1["task_id"] == result2["task_id"]


def test_pause_agent_persists_state():
    """pause_agent handler sets paused flag in team.STAFF."""
    bridge = Hermes3DBridge()
    result = bridge.handle_command("pause_agent", target_agent="isha", parameters={"reason": "testing"})
    assert result["success"] is True
    assert result["execution_result"]["new_state"] == "paused"
    assert result["execution_result"]["action"] == "pause_agent"


def test_resume_agent_after_pause():
    """resume_agent handler clears paused flag."""
    bridge = Hermes3DBridge()
    bridge.handle_command("pause_agent", target_agent="isha", parameters={})
    result = bridge.handle_command("resume_agent", target_agent="isha", parameters={})
    assert result["success"] is True
    assert result["execution_result"]["new_state"] == "active"


def test_focus_agent_returns_zoom():
    """focus_agent handler returns zoom parameter."""
    bridge = Hermes3DBridge()
    result = bridge.handle_command("focus_agent", target_agent="isha", parameters={"zoom": 2.0})
    assert result["success"] is True
    assert result["execution_result"]["zoom"] == 2.0


def test_status_check_returns_current_state():
    """status_check handler returns current agent status."""
    bridge = Hermes3DBridge()
    result = bridge.handle_command("status_check", target_agent="isha", parameters={})
    assert result["success"] is True
    assert "paused" in result["execution_result"]


def test_run_cycle_returns_cycle_id():
    """run_cycle handler returns a cycle_id."""
    bridge = Hermes3DBridge()
    result = bridge.handle_command("run_cycle", target_agent="isha", parameters={})
    assert result["success"] is True
    assert "cycle_id" in result["execution_result"]


def test_handle_command_with_unknown_agent():
    """Command with unknown agent returns appropriate error."""
    bridge = Hermes3DBridge()
    result = bridge.handle_command("pause_agent", target_agent="nonexistent_agent_xyz", parameters={})
    assert result["success"] is False
