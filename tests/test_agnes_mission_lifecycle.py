"""Test mission lifecycle for Agnes adapter."""

import os
import sys
import pytest
import uuid
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parents[2]))

# Enable the orchestrator for this test
os.environ["EXTERNAL_AGENT_ORCHESTRATOR"] = "1"
# Use local-file mode for testing (no Redis required)
os.environ["EXTERNAL_AGENT_COORDINATION_BACKEND"] = "local-file"

from app.dev_control.external_agents.schema import Mission, RiskClass, MissionState
from app.dev_control.external_agents.adapters import AgnesAdapter, get_adapter
from app.dev_control.external_agents.orchestrator import create_mission, OrchestratorDisabled


def test_orchestrator_enabled():
    """Orchestrator must be enabled for this test."""
    from app.dev_control.external_agents import policy
    assert policy.orchestrator_enabled() is True


def test_create_agnes_mission():
    """Create a mission for Agnes executor."""
    unique_key = f"test-agnes-mission-{uuid.uuid4().hex[:8]}"
    unique_path = f"tests/agnes_test_{uuid.uuid4().hex[:8]}/"
    mission = create_mission(
        title="Test Agnes Mission",
        description="Verify Agnes adapter integration",
        executor="agnes",
        reviewer="manager",
        idempotency_key=unique_key,
        allowed_paths=[unique_path],
        branch=f"feat/test-agnes-mission-{uuid.uuid4().hex[:8]}",
        worktree=f"/tmp/test-worktree-agnes-{uuid.uuid4().hex[:8]}",
        acceptance_criteria=[
            "Mission created successfully",
            "Adapter packet built correctly",
            "Result validated successfully",
        ],
    )
    
    assert mission["ok"] is True, f"Mission creation failed: {mission}"
    assert "mission" in mission
    assert mission["mission"]["executor"] == "agnes"
    assert mission["mission"]["risk_class"] == "GREEN"
    
    return mission["mission"]


def test_mission_lifecycle():
    """Test full mission lifecycle."""
    unique_key = f"test-agnes-lifecycle-{uuid.uuid4().hex[:8]}"
    unique_path = f"tests/agnes_lifecycle_{uuid.uuid4().hex[:8]}/"
    result = create_mission(
        title="Test Agnes Mission Lifecycle",
        description="Test full lifecycle: CREATED -> COMPLETE",
        executor="agnes",
        reviewer="manager",
        idempotency_key=unique_key,
        allowed_paths=[unique_path],
        branch=f"feat/test-agnes-lifecycle-{uuid.uuid4().hex[:8]}",
        worktree=f"/tmp/test-worktree-lifecycle-{uuid.uuid4().hex[:8]}",
    )
    
    # Debug: print result to see what's returned
    print(f"Mission creation result: {result}")
    if not result.get("ok"):
        pytest.fail(f"Mission creation failed: {result}")
    mission = result["mission"]
    
    # Verify mission was created successfully
    assert mission["status"] in [
        MissionState.CREATED.value,
        MissionState.PREFLIGHT.value,
        MissionState.CLAIMED.value,
    ], f"Mission status unexpected: {mission['status']}"
    
    return mission


def test_agnes_adapter_packet():
    """Test that Agnes adapter builds correct packet."""
    mission = Mission.create(
        title="Test Agnes Packet",
        description="Test adapter packet building",
        executor="agnes",
        reviewer="manager",
        risk_class=RiskClass.GREEN,
        idempotency_key=f"test-agnes-packet-{uuid.uuid4().hex[:8]}",
        allowed_paths=["tests/", "app/dev_control/"],
        branch=f"feat/test-agnes-packet-{uuid.uuid4().hex[:8]}",
        worktree=f"/tmp/test-worktree-packet-{uuid.uuid4().hex[:8]}",
    )
    
    adapter = get_adapter("agnes")
    packet = adapter.build_packet(mission)
    
    # Verify packet structure
    assert packet["mission_id"] == mission.mission_id
    assert packet["adapter"] == "agnes"
    assert packet["role"] == "executor"
    assert packet["risk_class"] == "GREEN"
    assert "capabilities" in packet
    assert packet["capabilities"]["file_reads"] is True
    assert packet["capabilities"]["github_api"] is True
    assert packet["capabilities"]["gui_automation"] is False
    
    # Verify prohibited actions
    assert len(packet["prohibited_actions"]) > 0
    assert any("env" in action for action in packet["prohibited_actions"])
    
    # Verify required evidence
    assert "file_changes" in packet["required_evidence"]
    assert "test_results" in packet["required_evidence"]
    assert "github_commits" in packet["required_evidence"]


def test_agnes_validate_result():
    """Agnes adapter must validate results correctly."""
    unique_path = f"tests/agnes_result_{uuid.uuid4().hex[:8]}/"
    mission = Mission.create(
        title="Test Agnes Result Validation",
        description="Test result validation",
        executor="agnes",
        reviewer="manager",
        risk_class=RiskClass.GREEN,
        idempotency_key=f"test-agnes-result-{uuid.uuid4().hex[:8]}",
        allowed_paths=[unique_path],
        branch=f"feat/test-agnes-result-{uuid.uuid4().hex[:8]}",
        worktree=f"/tmp/test-worktree-result-{uuid.uuid4().hex[:8]}",
        required_tests=["test_agnes_adapter.py"],
    )
    
    adapter = get_adapter("agnes")
    
    # Valid result
    result = {
        "mission_id": mission.mission_id,
        "executor": "agnes",
        "changed_files": [unique_path + "test_file.py"],
        "commands": ["python -m pytest tests/test_agnes_adapter.py"],
        "tests": [{"command": "python -m pytest tests/test_agnes_adapter.py", "exit_code": 0, "summary": "passed"}],
        "summary": "Test passed",
        "evidence": {"type": "test_result", "path": unique_path + "test_file.py"},
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
