"""PR Factory → external_agents.create_mission bridge (dual-gate, tmp store)."""

from __future__ import annotations

import inspect

import pytest

from app.dev_control.external_agents import cas as cas_mod
from app.dev_control.external_agents import orchestrator as ext_orch
from app.dev_control.external_agents import store as ext_store
from app.dev_control.external_agents.schema import Mission, MissionState
from app.platform.automation_flag_manifest import FlagGovernance, describe_flag
from tools.pr_factory import factory_enabled
from tools.pr_factory import orchestrator as factory_orch
from tools.pr_factory.orchestrator import FactoryDisabled, submit_task
from tools.pr_factory.reviewer_runner import ReviewSeparationError, assert_independent


class _Lock:
    def __init__(self) -> None:
        self.held: dict[str, str] = {}

    def acquire(self, owner, paths, ttl=900):
        clash = [p for p in paths if self.held.get(p, owner) != owner]
        if clash:
            return {"acquired": False, "conflict": sorted(clash)}
        for p in paths:
            self.held[p] = owner
        return {"acquired": True, "conflict": []}

    def release(self, owner, paths):
        for p in paths:
            if self.held.get(p) == owner:
                del self.held[p]


@pytest.fixture
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("EXTERNAL_MISSION_DIR", str(tmp_path / "missions"))
    monkeypatch.setenv("EXTERNAL_MISSION_CAS", "filelock")
    monkeypatch.setenv("EXTERNAL_AGENT_COORDINATION_BACKEND", "local-file")
    cas_mod.reset_backend()
    yield
    cas_mod.reset_backend()


def _task(**over):
    payload = {
        "title": "add unit test for helper",
        "description": "isolated factory bridge test",
        "executor": "cursor",
        "reviewer": "claude",
        "idempotency_key": "prf-bridge-0001",
        "allowed_paths": ["tests/test_helper.py"],
        "acceptance_criteria": ["helper covered"],
        "required_tests": ["pytest tests/test_helper.py -q"],
        "rollback_plan": "git revert the squash merge commit",
        "issue_id": "42",
    }
    payload.update(over)
    return payload


def test_pr_factory_flag_default_off_in_manifest():
    meta = describe_flag("PR_FACTORY_ENABLED")
    assert meta.governance == FlagGovernance.CANARY_ONLY
    assert meta.default_hint == "0"


def test_factory_inert_when_flags_off(monkeypatch, _isolated):
    monkeypatch.delenv("PR_FACTORY_ENABLED", raising=False)
    monkeypatch.delenv("EXTERNAL_AGENT_ORCHESTRATOR", raising=False)
    assert factory_enabled() is False
    with pytest.raises(FactoryDisabled):
        submit_task(_task(), lock=_Lock())


def test_factory_inert_when_only_factory_on(monkeypatch, _isolated):
    monkeypatch.setenv("PR_FACTORY_ENABLED", "1")
    monkeypatch.setenv("EXTERNAL_AGENT_ORCHESTRATOR", "0")
    assert factory_enabled() is False
    with pytest.raises(FactoryDisabled):
        submit_task(_task(), lock=_Lock())


def test_dual_gate_creates_mission_via_create_mission(monkeypatch, _isolated):
    monkeypatch.setenv("PR_FACTORY_ENABLED", "1")
    monkeypatch.setenv("EXTERNAL_AGENT_ORCHESTRATOR", "1")
    assert factory_enabled() is True
    out = submit_task(_task(), lock=_Lock())
    assert out["ok"] is True, out
    assert out["mission"]["title"] == "add unit test for helper"
    assert out["mission"]["executor"] == "cursor"
    assert out.get("factory_extras", {}).get("issue_id") == "42"
    # Evidence attached inside create_mission(initial_evidence=…), not a second ledger.
    kinds = [e.get("kind") for e in out["mission"].get("evidence_refs") or []]
    assert "pr_factory_task_extras" in kinds
    assert "classification" in kinds


def test_factory_module_does_not_touch_mission_store():
    # Import line + call sites (ignore docstring mentions of the anti-pattern).
    assert not hasattr(factory_orch, "ext_store")
    import_block = "\n".join(
        line
        for line in inspect.getsource(factory_orch).splitlines()
        if line.startswith("from ") or line.startswith("import ")
    )
    assert "external_agents import store" not in import_block
    assert "external_agents import store as" not in import_block
    body = inspect.getsource(factory_orch.submit_task)
    assert "initial_evidence" in body
    assert "ext_store.get" not in body
    assert "ext_store.save" not in body
    assert "store.save(" not in body
    assert "store.get(" not in body


def test_extras_survive_claim_and_stale_blind_save_is_the_anti_pattern(monkeypatch, _isolated):
    """Factory must not post-create store.save — that can clobber apply_cas claims."""
    monkeypatch.setenv("PR_FACTORY_ENABLED", "1")
    monkeypatch.setenv("EXTERNAL_AGENT_ORCHESTRATOR", "1")

    out = submit_task(_task(idempotency_key="prf-cas-safe-1"), lock=_Lock())
    assert out["ok"], out
    mid = out["mission"]["mission_id"]
    stale_snapshot = ext_store.get(mid)
    assert stale_snapshot is not None
    assert stale_snapshot.status is MissionState.CREATED
    stale_payload = stale_snapshot.to_dict()

    assert ext_orch.preflight(mid)["ok"]
    assert ext_orch.claim(mid, "worker-1")["ok"]
    claimed = ext_store.get(mid)
    assert claimed is not None
    assert claimed.status is MissionState.CLAIMED
    assert "pr_factory_task_extras" in claimed.evidence_kinds()

    # Anti-pattern (what Wave-1 review rejected): blind save of pre-claim object.
    zombie = Mission.from_dict(stale_payload)
    zombie.add_evidence("zombie_factory_extras", {"should_not_win": True})
    ext_store.save(zombie)
    clobbered = ext_store.get(mid)
    assert clobbered is not None
    assert clobbered.status is MissionState.CREATED
    # Claim was lost — proves why submit_task must never store.save after create.
    assert "zombie_factory_extras" in clobbered.evidence_kinds()

    # Fresh mission on a distinct path (avoid path-lock clash with mid).
    out2 = submit_task(
        _task(
            idempotency_key="prf-cas-safe-2",
            allowed_paths=["tests/test_helper_b.py"],
        ),
        lock=_Lock(),
    )
    assert out2["ok"], out2
    mid2 = out2["mission"]["mission_id"]
    assert ext_orch.preflight(mid2)["ok"]
    assert ext_orch.claim(mid2, "worker-2")["ok"]
    alive = ext_store.get(mid2)
    assert alive is not None
    assert alive.status is MissionState.CLAIMED
    assert "pr_factory_task_extras" in alive.evidence_kinds()


def test_create_mission_initial_evidence_attached_before_return(monkeypatch, _isolated):
    monkeypatch.setenv("EXTERNAL_AGENT_ORCHESTRATOR", "1")
    created = ext_orch.create_mission(
        title="add unit test for helper",
        description="initial_evidence contract",
        executor="cursor",
        reviewer="claude",
        idempotency_key="prf-init-ev-1",
        allowed_paths=["tests/test_helper.py"],
        acceptance_criteria=["ok"],
        required_tests=["pytest tests/test_helper.py -q"],
        rollback_plan="git revert",
        lock=_Lock(),
        initial_evidence=[{"kind": "custom_boot", "ref": {"x": 1}, "note": "n"}],
    )
    assert created["ok"], created
    kinds = [e.get("kind") for e in created["mission"].get("evidence_refs") or []]
    assert "custom_boot" in kinds
    assert "classification" in kinds


def test_red_title_refused(monkeypatch, _isolated):
    monkeypatch.setenv("PR_FACTORY_ENABLED", "1")
    monkeypatch.setenv("EXTERNAL_AGENT_ORCHESTRATOR", "1")
    out = submit_task(
        _task(
            title="disable DND scrub and blast cold WhatsApp",
            description="turn off TRAI gates and auto-send WhatsApp to all leads",
            idempotency_key="prf-bridge-red-1",
        ),
        lock=_Lock(),
    )
    assert out.get("ok") is False
    assert out.get("refused") is True or out.get("risk_class") == "RED"


def test_reviewer_separation_helper():
    assert_independent(executor="cursor", reviewer="claude")
    with pytest.raises(ReviewSeparationError):
        assert_independent(executor="claude", reviewer="claude")


def test_merge_train_gate_green_only():
    from tools.pr_factory.merge_train import can_label

    assert can_label(risk_class="GREEN", review_passed=True, checks_green=True)["ok"]
    assert can_label(risk_class="AMBER", review_passed=True, checks_green=True)["ok"] is False
    assert can_label(risk_class="GREEN", review_passed=False, checks_green=True)["ok"] is False


def test_budgets_deploy_refused():
    from tools.pr_factory.budgets import can_claim_slot, wave_slots

    assert wave_slots()["implementation_missions"] == 8
    assert can_claim_slot("deploy")["ok"] is False
    assert can_claim_slot("claude", {"claude": 3})["ok"] is True
    assert can_claim_slot("claude", {"claude": 4})["ok"] is False
