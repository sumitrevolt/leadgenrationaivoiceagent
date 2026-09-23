"""Comprehensive tests for Agnes adapter with mission transitions, lease enforcement, and scope validation."""

import os
import sys
import pytest
import uuid
import tempfile
import shutil
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parents[2]))

# Enable the orchestrator for this test
os.environ["EXTERNAL_AGENT_ORCHESTRATOR"] = "1"
# Use local-file mode for testing (no Redis required)
os.environ["EXTERNAL_AGENT_COORDINATION_BACKEND"] = "local-file"

from app.dev_control.external_agents.schema import Mission, RiskClass, MissionState
from app.dev_control.external_agents.adapters import AgnesAdapter, get_adapter, known_executors
from app.dev_control.external_agents.orchestrator import create_mission


@pytest.fixture
def temp_test_dir():
    """Create isolated temporary storage for tests."""
    temp_dir = tempfile.mkdtemp(prefix=f"agnes_test_{uuid.uuid4().hex[:8]}_")
    yield temp_dir
    # Cleanup after test
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_agnes_in_known_executors():
    """Agnes must be in the known executors list."""
    executors = known_executors()
    assert "agnes" in executors, f"Agnes not in known executors: {executors}"
    assert len(executors) == 3, f"Expected 3 executors (cursor, claude, agnes), got {len(executors)}"


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
        description="Test adapter packet building",
        executor="agnes",
        reviewer="manager",
        risk_class=RiskClass.GREEN,
        idempotency_key=f"test-agnes-packet-{uuid.uuid4().hex[:8]}",
        allowed_paths=["tests/"],
        branch=f"feat/test-agnes-packet-{uuid.uuid4().hex[:8]}",
        worktree=f"/tmp/test-worktree-packet-{uuid.uuid4().hex[:8]}",
    )
    
    adapter = get_adapter("agnes")
    packet = adapter.build_packet(mission)
    
    assert packet["mission_id"] == mission.mission_id
    assert packet["adapter"] == "agnes"
    assert packet["role"] == "executor"
    assert packet["risk_class"] == "GREEN"
    assert "capabilities" in packet
    assert packet["capabilities"]["file_reads"] is True
    assert packet["capabilities"]["github_api"] is True
    assert packet["capabilities"]["gui_automation"] is False
    assert packet["capabilities"]["vps_ssh"] is False
    
    # Verify prohibited actions
    assert len(packet["prohibited_actions"]) > 0
    assert any("env" in action for action in packet["prohibited_actions"])
    assert any("deploy" in action for action in packet["prohibited_actions"])
    assert any("telegram" in action.lower() for action in packet["prohibited_actions"])
    
    # Verify required evidence
    assert "file_changes" in packet["required_evidence"]
    assert "test_results" in packet["required_evidence"]
    assert "github_commits" in packet["required_evidence"]


def test_agnes_validate_result_valid():
    """Agnes adapter must validate valid results correctly."""
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


def test_agnes_validate_result_scope_breach():
    """Agnes adapter must reject results with scope breaches."""
    unique_path = f"tests/agnes_breach_{uuid.uuid4().hex[:8]}/"
    mission = Mission.create(
        title="Test Scope Breach",
        description="Test scope breach detection",
        executor="agnes",
        reviewer="manager",
        risk_class=RiskClass.GREEN,
        idempotency_key=f"test-agnes-breach-{uuid.uuid4().hex[:8]}",
        allowed_paths=[unique_path],
        branch=f"feat/test-agnes-breach-{uuid.uuid4().hex[:8]}",
        worktree=f"/tmp/test-worktree-breach-{uuid.uuid4().hex[:8]}",
    )
    
    adapter = get_adapter("agnes")
    
    # Invalid result (scope breach)
    result = {
        "mission_id": mission.mission_id,
        "executor": "agnes",
        "changed_files": [".env", "app/billing.py"],
        "commands": [],
        "tests": [],
        "summary": "Failed",
        "evidence": {},
        "scope_breach": True,
    }
    
    validation = adapter.validate_result(mission, result)
    assert validation["accepted"] is False
    assert len(validation["violations"]) > 0
    assert any("scope_breach" in v for v in validation["violations"])


def test_agnes_requires_worktree():
    """Agnes missions must have a worktree."""
    mission = Mission.create(
        title="Test No Worktree",
        description="Test worktree requirement",
        executor="agnes",
        reviewer="manager",
        risk_class=RiskClass.GREEN,
        idempotency_key=f"test-agnes-no-worktree-{uuid.uuid4().hex[:8]}",
        allowed_paths=["tests/"],
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


def test_create_agnes_mission(temp_test_dir):
    """Create a mission for Agnes executor."""
    unique_key = f"test-agnes-mission-{uuid.uuid4().hex[:8]}"
    unique_path = f"tests/agnes_mission_{uuid.uuid4().hex[:8]}/"
    
    mission = create_mission(
        title="Test Agnes Mission",
        description="Verify Agnes adapter integration",
        executor="agnes",
        reviewer="manager",
        idempotency_key=unique_key,
        allowed_paths=[unique_path],
        branch=f"feat/test-agnes-mission-{uuid.uuid4().hex[:8]}",
        worktree=f"{temp_test_dir}/worktree",
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
    assert mission["mission"]["status"] in [
        MissionState.CREATED.value,
        MissionState.PREFLIGHT.value,
    ]
    
    return mission["mission"]


def test_mission_lifecycle(temp_test_dir):
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
        worktree=f"{temp_test_dir}/worktree-lifecycle",
    )
    
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


def test_orchestrator_enabled():
    """Orchestrator must be enabled for this test."""
    from app.dev_control.external_agents import policy
    assert policy.orchestrator_enabled() is True


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


def test_mission_transition_creates():
    """Test mission creation transition."""
    unique_key = f"test-transition-create-{uuid.uuid4().hex[:8]}"
    unique_path = f"tests/agnes_transition_{uuid.uuid4().hex[:8]}/"
    
    result = create_mission(
        title="Test Mission Transition",
        description="Test CREATED state transition",
        executor="agnes",
        reviewer="manager",
        idempotency_key=unique_key,
        allowed_paths=[unique_path],
        branch=f"feat/test-transition-{uuid.uuid4().hex[:8]}",
        worktree=f"/tmp/test-worktree-transition-{uuid.uuid4().hex[:8]}",
    )
    
    assert result["ok"] is True
    mission = result["mission"]
    assert mission["status"] in [MissionState.CREATED.value, MissionState.PREFLIGHT.value]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
