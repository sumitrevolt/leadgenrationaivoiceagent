"""Test for Agnes adapter registration and functionality."""

import pytest

from app.dev_control.external_agents.adapters import AgnesAdapter, get_adapter, known_executors
from app.dev_control.external_agents.schema import Mission, RiskClass


def test_agnes_in_known_executors():
    """Agnes must be in the known executors list."""
    executors = known_executors()
    assert "agnes" in executors, f"Agnes not in known executors: {executors}"


def test_get_agnes_adapter():
    """Must be able to get the Agnes adapter."""
    adapter = get_adapter("agnes")
    assert isinstance(adapter, AgnesAdapter)
    assert adapter.name == "agnes"
    assert adapter.role == "executor"
    assert adapter.requires_worktree is True


def test_agnes_build_packet():
    """Agnes adapter must build a valid packet."""
    mission = Mission.create(
        title="Test Agnes Mission",
        description="Test mission for Agnes adapter",
        executor="agnes",
        reviewer="manager",
        risk_class=RiskClass.GREEN,
        idempotency_key="test-agnes-mission-001",
        allowed_paths=["app/dev_control/"],
        branch="feat/test-agnes",
        worktree="/tmp/test-worktree",
    )

    adapter = get_adapter("agnes")
    packet = adapter.build_packet(mission)

    assert packet["mission_id"] == mission.mission_id
    assert packet["adapter"] == "agnes"
    assert (
        packet["interface"]
        == "Agnes Desktop — file reads, GitHub API, web research, shell (when available)"
    )
    assert packet["capabilities"]["file_reads"] is True
    assert packet["capabilities"]["github_api"] is True
    assert packet["capabilities"]["gui_automation"] is False
    assert packet["prohibited_actions"]
    assert packet["required_evidence"]


def test_agnes_validate_result():
    """Agnes adapter must validate results correctly."""
    mission = Mission.create(
        title="Test Agnes Mission",
        description="Test mission for Agnes adapter",
        executor="agnes",
        reviewer="manager",
        risk_class=RiskClass.GREEN,
        idempotency_key="test-agnes-mission-002",
        allowed_paths=["app/dev_control/"],
        branch="feat/test-agnes",
        worktree="/tmp/test-worktree",
        required_tests=["test_agnes_adapter.py"],
    )

    adapter = get_adapter("agnes")

    # Valid result
    result = {
        "mission_id": mission.mission_id,
        "executor": "agnes",
        "changed_files": ["app/dev_control/external_agents/adapters.py"],
        "commands": ["python -m pytest tests/test_agnes_adapter.py"],
        "tests": [
            {
                "command": "python -m pytest tests/test_agnes_adapter.py",
                "exit_code": 0,
                "summary": "passed",
            }
        ],
        "summary": "Test passed",
        "evidence": {"type": "test_result", "path": "tests/test_agnes_adapter.py"},
        "scope_breach": False,
    }

    validation = adapter.validate_result(mission, result)
    assert validation["accepted"] is True
    assert validation["violations"] == []

    # Invalid result (scope breach)
    result_breach = result.copy()
    result_breach["changed_files"] = [".env"]
    validation_breach = adapter.validate_result(mission, result_breach)
    assert validation_breach["accepted"] is False
    assert any("scope_breach" in v for v in validation_breach["violations"])


def test_agnes_requires_worktree():
    """Agnes missions must have a worktree."""
    mission = Mission.create(
        title="Test Agnes Mission No Worktree",
        description="Test mission without worktree",
        executor="agnes",
        reviewer="manager",
        risk_class=RiskClass.GREEN,
        idempotency_key="test-agnes-mission-003",
        allowed_paths=["app/dev_control/"],
        branch="",  # Empty branch
        worktree="",  # Empty worktree
    )

    adapter = get_adapter("agnes")
    result = {
        "mission_id": mission.mission_id,
        "executor": "agnes",
        "changed_files": [],
        "tests": [],
        "scope_breach": False,
    }

    validation = adapter.validate_result(mission, result)
    assert validation["accepted"] is False
    assert any("worktree" in v for v in validation["violations"])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
