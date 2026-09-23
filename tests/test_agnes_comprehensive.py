"""
End-to-end mission lifecycle tests for the Agnes external-executor adapter.

Isolation model (verified against the real store resolution):
- The local checkout runs in LEGACY authority mode, so the EXTERNAL_MISSION_DIR
  env override genuinely redirects the canonical external mission store to a
  fresh temp dir (see runtime_data_authority.resolve_store_authority).
- cas.reset_backend() forces the FileLock CAS backend to re-probe the new root.
- EXTERNAL_AGENT_ORCHESTRATOR / EXTERNAL_AGENT_COORDINATION_BACKEND are set via
  a module-scoped fixture and restored on teardown, so no global env mutation
  leaks into other test modules.
- We do NOT touch app.platform.automation_orchestrator.DATA_DIR: that is the
  internal automation ledger, a different store from the external mission store.
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
from app.dev_control.external_agents import policy
from app.dev_control.external_agents import store as ext_store
from app.dev_control.external_agents.adapters import (
    AgnesAdapter,
    get_adapter,
    known_executors,
)
from app.dev_control.external_agents.orchestrator import (
    OrchestratorDisabled,
    advance,
    claim,
    create_mission,
    heartbeat,
    preflight,
    start,
    submit_result,
    submit_review,
)
from app.dev_control.external_agents.schema import Mission, MissionState, RiskClass

# ---------------------------------------------------------------- fixtures


@pytest.fixture(scope="module")
def agnes_env():
    """Redirect the real external mission store + enable the orchestrator, scoped.

    Restores the environment and resets the cached CAS backend on teardown so
    later test modules / production state are not contaminated.
    """
    saved = {}
    tmp = Path(tempfile.mkdtemp(prefix=f"agnes_ext_mission_{uuid.uuid4().hex[:8]}_"))
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


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def _ok(result: dict, what: str) -> dict:
    assert result.get("ok") is True, f"{what} failed: {result.get('reason')}"
    return result


# ---------------------------------------------------------------- adapter


def test_agnes_in_known_executors(agnes_env):
    executors = known_executors()
    assert "agnes" in executors
    assert executors == ["agnes", "claude", "cursor"]


def test_get_agnes_adapter(agnes_env):
    adapter = get_adapter("agnes")
    assert isinstance(adapter, AgnesAdapter)
    assert adapter.name == "agnes"
    assert adapter.role == "executor"
    assert adapter.requires_worktree is True


def test_agnes_build_packet_structure(agnes_env):
    mission = Mission.create(
        title="packet",
        executor="agnes",
        reviewer="claude",
        risk_class=RiskClass.GREEN,
        idempotency_key=_unique("pkt"),
        allowed_paths=["tests/"],
        branch="feat/pkt",
        worktree="wt-pkt",
    )
    packet = get_adapter("agnes").build_packet(mission)
    assert packet["mission_id"] == mission.mission_id
    assert packet["adapter"] == "agnes"
    assert packet["role"] == "executor"
    assert packet["capabilities"]["github_api"] is True
    assert packet["capabilities"]["gui_automation"] is False


def test_agnes_validate_result_rejects_scope_breach(agnes_env):
    mission = Mission.create(
        title="breach",
        executor="agnes",
        reviewer="claude",
        risk_class=RiskClass.GREEN,
        idempotency_key=_unique("br"),
        allowed_paths=["tests/"],
        branch="feat/br",
        worktree="wt-br",
    )
    adapter = get_adapter("agnes")
    good = adapter.validate_result(
        mission,
        {
            "mission_id": mission.mission_id,
            "executor": "agnes",
            "changed_files": ["tests/agnes_demo.py"],
            "tests": [{"command": "pytest", "exit_code": 0}],
        },
    )
    assert good["accepted"] is True

    bad = adapter.validate_result(
        mission,
        {
            "mission_id": mission.mission_id,
            "executor": "agnes",
            "changed_files": [".env", "app/billing/x.py"],
            "tests": [],
        },
    )
    assert bad["accepted"] is False
    assert any("scope_breach" in v for v in bad["violations"])


def test_agnes_requires_worktree(agnes_env):
    mission = Mission.create(
        title="noworktree",
        executor="agnes",
        reviewer="claude",
        risk_class=RiskClass.GREEN,
        idempotency_key=_unique("nw"),
        allowed_paths=["tests/"],
        branch="",
        worktree="",
    )
    validation = get_adapter("agnes").validate_result(
        mission,
        {
            "mission_id": mission.mission_id,
            "executor": "agnes",
            "changed_files": ["tests/x.py"],
        },
    )
    assert validation["accepted"] is False
    assert any("worktree" in v for v in validation["violations"])


# ---------------------------------------------------------------- isolation


def test_production_ledger_isolated(agnes_env):
    """Missions we create must land in the temp store, not the in-repo data dir."""
    root = str(cas_mod.get_backend(root=str(agnes_env / ".root")) or agnes_env)
    backend = cas_mod.get_backend()
    assert backend.name == "filelock"
    # The store resolves its root from EXTERNAL_MISSION_DIR (our temp dir), not
    # the in-checkout data/external_missions.
    live_root = ext_store._root()
    assert str(live_root).startswith(str(agnes_env)), f"mission store not isolated: {live_root}"
    _ = root  # silence unused


def test_orchestrator_disabled_outside_fixture():
    """Without the fixture env, the orchestrator must be inert (fail-closed)."""
    # Read the current (restored) value; if a prior fixture set it, restore first.
    saved = os.environ.pop("EXTERNAL_AGENT_ORCHESTRATOR", None)
    try:
        cas_mod.reset_backend()
        with pytest.raises(OrchestratorDisabled):
            create_mission(
                title="should-refuse",
                executor="agnes",
                reviewer="claude",
                idempotency_key=_unique("ref"),
            )
    finally:
        if saved is not None:
            os.environ["EXTERNAL_AGENT_ORCHESTRATOR"] = saved
        cas_mod.reset_backend()


# ---------------------------------------------------------------- lifecycle


def test_full_mission_lifecycle_end_to_end(agnes_env):
    """Drive one GREEN Agnes mission through the entire canonical loop.

    create -> preflight -> claim -> heartbeat -> start(RUNNING)
           -> submit_result -> submit_review -> advance(VERIFIED) -> COMPLETE
    Each step asserts the returned status; nothing is self-marked.
    """
    branch = _unique("feat/full")
    worktree = f"wt-{branch}"
    scope = _unique("scope")
    allowed = [f"tests/{scope}/"]
    changed = [f"tests/{scope}/demo.py"]

    created = _ok(
        create_mission(
            title="Agnes full lifecycle demo",
            description="Non-destructive end-to-end mission",
            executor="agnes",
            reviewer="claude",
            idempotency_key=_unique("full"),
            allowed_paths=allowed,
            branch=branch,
            worktree=worktree,
            rollback_plan="revert commit and close PR",
            required_tests=["tests/"],
        ),
        "create",
    )
    mid = created["mission"]["mission_id"]
    assert created["mission"]["status"] == MissionState.CREATED.value
    assert created["reused"] is False

    pf = _ok(preflight(mid), "preflight")
    assert pf["mission"]["status"] == MissionState.PREFLIGHT.value
    assert "packet" in pf  # preflight returns the adapter packet

    cl = _ok(claim(mid, "agnes"), "claim")
    assert cl["mission"]["lease_owner"] == "agnes"
    assert cl["mission"]["status"] == MissionState.CLAIMED.value

    # Lease ownership: a different owner cannot heartbeat.
    assert heartbeat(mid, "agnes")["ok"] is True
    assert heartbeat(mid, "other-owner")["ok"] is False

    st = _ok(start(mid, "agnes"), "start")
    assert st["mission"]["status"] == MissionState.RUNNING.value

    result = {
        "mission_id": mid,
        "executor": "agnes",
        "changed_files": changed,
        "commands": ["python -m pytest tests/"],
        "tests": [{"command": "python -m pytest tests/", "exit_code": 0, "summary": "passed"}],
    }
    sr = _ok(submit_result(mid, "agnes", result), "submit_result")
    assert sr["mission"]["status"] == MissionState.REVIEW_REQUIRED.value

    # Stale/fencing: a non-lease owner cannot submit a result.
    stale = submit_result(mid, "stale-owner", result)
    assert stale.get("ok") is False
    assert stale.get("reason") == "lease_not_owned"

    # Review separation: the executor name may not self-approve.
    self_review = submit_review(
        mid,
        {
            "mission_id": mid,
            "reviewer": "agnes",
            "verdict": "PASS",
            "citations": [changed[0]],
        },
    )
    assert self_review.get("ok") is False
    assert self_review.get("reason") == "review_rejected"

    rv = _ok(
        submit_review(
            mid,
            {
                "mission_id": mid,
                "reviewer": "claude",
                "verdict": "PASS",
                "citations": [changed[0], "tests passed exit 0"],
            },
        ),
        "submit_review",
    )
    assert rv["verdict"] == "PASS"
    assert rv["mission"]["status"] == MissionState.REVIEW_PASSED.value

    # Honest boundary: a local non-destructive mission completes the canonical
    # executor + review loop up to REVIEW_PASSED using only code/test/review
    # evidence that genuinely exists on the mission. The remaining states
    # (PR_OPEN -> CI_RUNNING -> MERGE_QUEUED -> MERGED -> VERIFIED -> COMPLETE)
    # each require real external events (an opened PR, green CI, a merge, a
    # deploy) that are NOT fabricated here. We assert the map governs them
    # instead of force-advancing to COMPLETE, which would be a false signal.
    from app.dev_control.external_agents.schema import VALID_TRANSITIONS

    assert MissionState.PR_OPEN in VALID_TRANSITIONS[MissionState.REVIEW_PASSED]
    assert MissionState.COMPLETE in VALID_TRANSITIONS[MissionState.VERIFIED]

    # Persisted + retrievable at the genuine ceiling state.
    persisted = ext_store.get(mid)
    assert persisted is not None
    assert persisted.status is MissionState.REVIEW_PASSED
    assert persisted.lease_owner == "agnes"
    kinds = persisted.evidence_kinds()
    assert {"result_manifest", "review", "tests"} <= kinds


def test_duplicate_mission_idempotency(agnes_env):
    key = _unique("dup")
    first = _ok(
        create_mission(
            title="dup",
            description="",
            executor="agnes",
            reviewer="claude",
            idempotency_key=key,
            allowed_paths=["tests/"],
            branch=_unique("b"),
            worktree=_unique("wt"),
        ),
        "first",
    )
    second = _ok(
        create_mission(
            title="dup",
            description="",
            executor="agnes",
            reviewer="claude",
            idempotency_key=key,
            allowed_paths=["tests/"],
            branch=_unique("b"),
            worktree=_unique("wt"),
        ),
        "second",
    )
    assert first["reused"] is False
    assert second["reused"] is True
    assert first["mission"]["mission_id"] == second["mission"]["mission_id"]


def test_stale_result_rejected_when_not_running(agnes_env):
    key = _unique("stale")
    scope = _unique("stale-scope")
    created = _ok(
        create_mission(
            title="stale",
            description="",
            executor="agnes",
            reviewer="claude",
            idempotency_key=key,
            allowed_paths=[f"tests/{scope}/"],
            branch=_unique("b"),
            worktree=_unique("wt"),
        ),
        "create",
    )
    mid = created["mission"]["mission_id"]
    # A mission not in RUNNING must reject a result submission (fencing).
    res = submit_result(mid, "agnes", {"mission_id": mid, "executor": "agnes"})
    assert res.get("ok") is False
    assert (
        str(res.get("reason", "")).startswith("stale_transition:")
        or res.get("reason") == "lease_not_owned"
    )


def test_execution_order_independence(agnes_env):
    """Two missions created in either order must not collide (unique scopes)."""
    a = _ok(
        create_mission(
            title="A",
            description="",
            executor="agnes",
            reviewer="claude",
            idempotency_key=_unique("ordA"),
            allowed_paths=[f"tests/{_unique('a')}/"],
            branch=_unique("bA"),
            worktree=_unique("wtA"),
        ),
        "A",
    )
    b = _ok(
        create_mission(
            title="B",
            description="",
            executor="agnes",
            reviewer="claude",
            idempotency_key=_unique("ordB"),
            allowed_paths=[f"tests/{_unique('b')}/"],
            branch=_unique("bB"),
            worktree=_unique("wtB"),
        ),
        "B",
    )
    assert a["mission"]["mission_id"] != b["mission"]["mission_id"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
