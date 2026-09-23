"""Mission-lifecycle tests for the Agnes external-executor adapter.

All orchestrator/store setup is done through a module-scoped fixture that
redirects the *real* external mission store (EXTERNAL_MISSION_DIR, in LEGACY
mode) to a fresh temp dir and enables EXTERNAL_AGENT_ORCHESTRATOR, restoring
the environment and resetting the cached CAS backend on teardown. No
module-level environment mutation and no patching of the unrelated internal
automation ledger.
"""

import os
import shutil
import sys
import tempfile
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2]))

from app.dev_control.external_agents import cas as cas_mod
from app.dev_control.external_agents import store as ext_store
from app.dev_control.external_agents.adapters import AgnesAdapter, get_adapter
from app.dev_control.external_agents.orchestrator import create_mission
from app.dev_control.external_agents.schema import Mission, MissionState, RiskClass


def _u(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


@pytest.fixture(scope="module")
def agnes_env():
    saved = {}
    tmp = Path(tempfile.mkdtemp(prefix=f"agnes_lifecycle_{uuid.uuid4().hex[:8]}_"))
    try:
        for var in (
            "EXTERNAL_AGENT_ORCHESTRATOR",
            "EXTERNAL_AGENT_COORDINATION_BACKEND",
            "EXTERNAL_MISSION_DIR",
        ):
            saved[var] = os.environ.get(var)
        os.environ["EXTERNAL_AGENT_ORCHESTRATOR"] = "1"
        os.environ["EXTERNAL_AGENT_COORDINATION_BACKEND"] = "local-file"
        os.environ["EXTERNAL_MISSION_DIR"] = str(tmp)
        cas_mod.reset_backend()
        yield tmp
    finally:
        cas_mod.reset_backend()
        for var, val in saved.items():
            if val is None:
                os.environ.pop(var, None)
            else:
                os.environ[var] = val
        shutil.rmtree(tmp, ignore_errors=True)


def test_orchestrator_enabled(agnes_env):
    from app.dev_control.external_agents import policy

    assert policy.orchestrator_enabled() is True


def test_store_isolated_to_temp(agnes_env):
    """Missions persist under the fixture's temp dir, not the in-repo data dir."""
    live_root = ext_store._root()
    assert str(live_root).startswith(str(agnes_env)), f"store not isolated: {live_root}"
    assert cas_mod.get_backend().name == "filelock"


def test_create_agnes_mission(agnes_env):
    mission = create_mission(
        title="Test Agnes Mission",
        description="Verify Agnes adapter integration",
        executor="agnes",
        reviewer="claude",
        idempotency_key=_u("create"),
        allowed_paths=[f"tests/{_u('scope')}/"],
        branch=_u("feat"),
        worktree=_u("wt"),
    )
    assert mission["ok"] is True, f"creation failed: {mission.get('reason')}"
    m = mission["mission"]
    assert m["executor"] == "agnes"
    assert m["risk_class"] == "GREEN"
    assert m["status"] == MissionState.CREATED.value
    # It actually persisted to the isolated store.
    assert ext_store.get(m["mission_id"]) is not None


def test_agnes_adapter_packet():
    mission = Mission.create(
        title="packet",
        executor="agnes",
        reviewer="claude",
        risk_class=RiskClass.GREEN,
        idempotency_key=_u("pkt"),
        allowed_paths=["tests/"],
        branch="feat/pkt",
        worktree="wt-pkt",
    )
    packet = get_adapter("agnes").build_packet(mission)
    assert packet["adapter"] == "agnes"
    assert packet["role"] == "executor"
    assert packet["capabilities"]["github_api"] is True
    assert packet["capabilities"]["gui_automation"] is False
    assert any("env" in a for a in packet["prohibited_actions"])


def test_agnes_validate_result(agnes_env):
    scope = _u("scope")
    mission = Mission.create(
        title="validation",
        executor="agnes",
        reviewer="claude",
        risk_class=RiskClass.GREEN,
        idempotency_key=_u("val"),
        allowed_paths=[f"tests/{scope}/"],
        branch="feat/val",
        worktree="wt-val",
        required_tests=["tests/"],
    )
    adapter = get_adapter("agnes")
    good = adapter.validate_result(
        mission,
        {
            "mission_id": mission.mission_id,
            "executor": "agnes",
            "changed_files": [f"tests/{scope}/demo.py"],
            "tests": [{"command": "pytest", "exit_code": 0}],
        },
    )
    assert good["accepted"] is True

    bad = adapter.validate_result(
        mission,
        {
            "mission_id": mission.mission_id,
            "executor": "agnes",
            "changed_files": [".env"],
        },
    )
    assert bad["accepted"] is False
    assert any("scope_breach" in v for v in bad["violations"])


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
