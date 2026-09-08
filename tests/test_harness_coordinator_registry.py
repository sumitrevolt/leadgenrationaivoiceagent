"""coordinator structured action contract + registry migration tests (4th family).

CoordinatorPlanV1/ActionV1 strict contract; legacy heuristic normalization with
honest provenance; dual-plan comparison; both executor boundaries observed;
agent.delegate.dev@1.0.0 the one honestly-safe registered delegation (GREEN,
read-only research). Enforcement OFF; legacy coordinator authoritative.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from pydantic import ValidationError

from app.agents.harness import coordinator_contract as cc
from app.agents.harness.adapters import observe_coordinator_action
from app.agents.harness.adapters.coordinator_shadow import (
    COORDINATOR_TOOL_MAP,
    resolve_coordinator_tool,
)
from app.agents.harness.contracts import RiskClass
from app.agents.harness.registry import (
    REGISTRY,
    AuthorityClass,
    CanonicalToolRegistry,
    RegistryConflict,
    RiskLane,
    SideEffectClass,
    claimed_lane,
)

DELEG = "agent.delegate.dev"
AT = cc.CoordinatorActionType


def _act(**kw):
    base = {
        "action_id": "a0",
        "sequence": 0,
        "action_type": AT.DELEGATE_AGENT,
        "target_agent": "dev",
        "task": "do research",
    }
    base.update(kw)
    return cc.CoordinatorActionV1(**base)


def _env(mp, agents="dev,isha", loops="coordinator"):
    mp.setenv("AGENT_HARNESS", "1")
    mp.setenv("AGENT_HARNESS_SHADOW", "1")
    mp.setenv("AGENT_HARNESS_ENFORCE", "0")
    mp.setenv("AGENT_HARNESS_CANARY_AGENTS", agents)
    mp.setenv("AGENT_HARNESS_CANARY_LOOPS", loops)


def _obs(agent="dev", boundary="_run_agent", **kw):
    base = {
        "coordinator_run_id": "c1",
        "orchestration_path": "coordinate",
        "action_index": 0,
        "agent_id": agent,
        "tenant_id": "",
        "normalized_action": {"tool": agent, "task": "t"},
        "actual_executor": f"_TOOLS[{agent}]",
        "actual_result": {"tool": "x"},
        "boundary": boundary,
    }
    base.update(kw)
    return observe_coordinator_action(**base)


# ============ Contract validation (1-12) ============================
def test_valid_plan_passes():
    p = cc.CoordinatorPlanV1(objective="g", actions=[_act()])
    assert p.actions[0].action_type is AT.DELEGATE_AGENT


def test_extra_fields_fail():
    with pytest.raises(ValidationError):
        cc.CoordinatorActionV1(action_id="a", sequence=0, action_type=AT.STOP, bogus=1)


def test_unknown_action_type_fails():
    with pytest.raises(ValidationError):
        cc.CoordinatorActionV1(action_id="a", sequence=0, action_type="TELEPORT")


def test_duplicate_action_ids_fail():
    with pytest.raises(ValidationError):
        cc.CoordinatorPlanV1(
            objective="g", actions=[_act(action_id="x"), _act(action_id="x", sequence=1)]
        )


def test_invalid_sequence_fails():
    with pytest.raises(ValidationError):
        _act(sequence=-1)


def test_unknown_target_agent_fails_delegation():
    ok, err = cc.validate_delegation_target("nobody")
    assert ok is False and "unknown" in err


def test_kavach_target_fails():
    ok, err = cc.validate_delegation_target("kavach")
    assert ok is False and "kavach" in err.lower()


def test_unbounded_task_fails():
    with pytest.raises(ValidationError):
        _act(task="x" * 3000)


def test_invalid_argument_type_fails():
    with pytest.raises(ValidationError):
        cc.CoordinatorActionV1(action_id="a", sequence=0, action_type=AT.STOP, arguments="notdict")


def test_red_command_classified():
    a = _act(
        action_type=AT.INVOKE_INTERNAL_TOOL, tool_name="shell.exec.run", claimed_risk=RiskLane.RED
    )
    assert a.claimed_risk is RiskLane.RED


def test_invalid_schema_version_fails():
    with pytest.raises(ValidationError):
        cc.CoordinatorActionV1(action_id="a", sequence=0, action_type=AT.STOP, schema_version="2.0")


def test_empty_action_list_explicit():
    p = cc.CoordinatorPlanV1(objective="g", actions=[])
    assert p.actions == []


# ============ Legacy normalization (13-18) ==========================
def test_legacy_json_extract_normalizes():
    p = cc.normalize_legacy_plan([{"agent": "dev", "task": "a"}])
    assert p.plan_source is cc.PlanSource.LEGACY_JSON_EXTRACT
    assert p.actions[0].target_agent == "dev"


def test_legacy_regex_normalizes():
    p = cc.normalize_legacy_plan([{"agent": "dev", "task": "a"}], regex_used=True)
    assert p.plan_source is cc.PlanSource.LEGACY_REGEX


def test_fallback_normalizes_with_provenance():
    p = cc.normalize_legacy_plan([{"agent": "dev", "task": "a"}], fallback_used=True)
    assert p.plan_source is cc.PlanSource.FALLBACK_DEFAULT


def test_failed_parse_honest():
    p = cc.normalize_legacy_plan([])
    assert p.actions == [] and p.plan_source is cc.PlanSource.LEGACY_JSON_EXTRACT


def test_heuristic_never_marked_native():
    p = cc.normalize_legacy_plan([{"agent": "dev", "task": "a"}])
    assert p.plan_source is not cc.PlanSource.STRUCTURED_NATIVE


def test_legacy_ordering_preserved():
    p = cc.normalize_legacy_plan([{"agent": "dev", "task": "a"}, {"agent": "isha", "task": "b"}])
    assert [a.target_agent for a in p.actions] == ["dev", "isha"]
    assert [a.sequence for a in p.actions] == [0, 1]


# ============ Plan comparison (19-26) ===============================
def _legacy(pairs, fallback=False):
    return cc.normalize_legacy_plan(
        [{"agent": a, "task": t} for a, t in pairs], fallback_used=fallback
    )


def _structured(specs):
    acts = [
        cc.CoordinatorActionV1(
            action_id=f"s{i}",
            sequence=i,
            action_type=AT.DELEGATE_AGENT,
            target_agent=a,
            tool_name=tn,
            arguments=(args or {}),
        )
        for i, (a, tn, args) in enumerate(specs)
    ]
    return cc.CoordinatorPlanV1(objective="g", actions=acts)


def test_exact_plans_match():
    leg = _legacy([("dev", "a"), ("isha", "b")])
    st = _structured([("dev", None, {}), ("isha", None, {})])
    assert cc.compare_plans(st, leg).comparison_verdict is cc.CoordinatorPlanVerdict.PLAN_MATCH


def test_target_mismatch_detected():
    leg = _legacy([("dev", "a")])
    st = _structured([("kavya", None, {})])
    assert cc.compare_plans(st, leg).comparison_verdict is cc.CoordinatorPlanVerdict.TARGET_MISMATCH


def test_tool_mismatch_detected():
    leg = _legacy([("dev", "a")])
    st = _structured([("dev", "some.tool", {})])  # legacy has no tool_name
    assert cc.compare_plans(st, leg).comparison_verdict is cc.CoordinatorPlanVerdict.TOOL_MISMATCH


def test_argument_mismatch_detected():
    leg = _legacy([("dev", "a")])
    st = _structured([("dev", None, {"x": 1})])
    assert (
        cc.compare_plans(st, leg).comparison_verdict is cc.CoordinatorPlanVerdict.ARGUMENT_MISMATCH
    )


def test_action_count_mismatch_detected():
    leg = _legacy([("dev", "a"), ("isha", "b")])
    st = _structured([("dev", None, {})])
    assert (
        cc.compare_plans(st, leg).comparison_verdict
        is cc.CoordinatorPlanVerdict.ACTION_COUNT_MISMATCH
    )


def test_invalid_structured_detected():
    leg = _legacy([("dev", "a")])
    assert (
        cc.compare_plans(None, leg).comparison_verdict
        is cc.CoordinatorPlanVerdict.STRUCTURED_INVALID
    )


def test_legacy_fallback_verdict():
    leg = _legacy([("dev", "x"), ("rohan", "y"), ("isha", "z")], fallback=True)
    st = _structured([("dev", None, {}), ("rohan", None, {}), ("isha", None, {})])
    assert cc.compare_plans(st, leg).comparison_verdict is cc.CoordinatorPlanVerdict.LEGACY_FALLBACK


def test_differences_bounded():
    leg = _legacy([("dev", "a"), ("isha", "b")])
    st = _structured([("kavya", None, {"z": 1}), ("meera", None, {})])
    diffs = cc.compare_plans(st, leg).differences
    assert isinstance(diffs, list) and len(diffs) <= 20
    assert all(len(str(d.get("structured", ""))) <= 120 for d in diffs)


# ============ Execution safety + boundaries (27-41) =================
def _patch_coord(monkeypatch, tmp_path, steps, tools_counter):
    coord = pytest.importorskip("app.agents.coordinator")
    from app.agents.harness import audit

    monkeypatch.setattr(audit, "_RUN_LOG", str(tmp_path / "runs.jsonl"))
    _env(monkeypatch)

    async def fake_plan(goal, max_steps=5, hint=""):
        return steps

    monkeypatch.setattr(coord, "plan", fake_plan)
    newtools = {}
    for name in ("dev", "isha", "kavya", "arjun", "meera"):

        def mk(n):
            async def t(task, goal):
                tools_counter[n] = tools_counter.get(n, 0) + 1
                return {"tool": f"{n}_tool", "ok": True}

            return t

        newtools[name] = mk(name)
    monkeypatch.setattr(coord, "_TOOLS", newtools)
    return coord


def _shadow_rows(tmp_path, agent=None):
    rows = [json.loads(x) for x in open(tmp_path / "runs.jsonl", encoding="utf-8")]
    r = [
        x["extra"]
        for x in rows
        if x.get("kind") == "shadow" and x["extra"].get("source_loop") == "coordinator"
    ]
    return [x for x in r if agent is None or x.get("agent") == agent]


def test_legacy_action_executes_once(monkeypatch, tmp_path):
    tc = {}
    coord = _patch_coord(monkeypatch, tmp_path, [{"agent": "dev", "task": "a"}], tc)
    asyncio.run(coord.coordinate("build something real", execute=True))
    assert tc.get("dev") == 1  # legacy executed exactly once


def test_harness_executes_zero(monkeypatch, tmp_path):
    tc = {}
    coord = _patch_coord(monkeypatch, tmp_path, [{"agent": "dev", "task": "a"}], tc)
    asyncio.run(coord.coordinate("build something real", execute=True))
    rows = _shadow_rows(tmp_path, "dev")
    assert rows and rows[-1]["execution_comparison"] == "MATCH"  # observed, not executed by harness


def test_dev_delegation_registry_match(monkeypatch, tmp_path):
    tc = {}
    coord = _patch_coord(monkeypatch, tmp_path, [{"agent": "dev", "task": "a"}], tc)
    asyncio.run(coord.coordinate("build something real", execute=True))
    ex = _shadow_rows(tmp_path, "dev")[-1]
    assert ex["registry_comparison"] == "REGISTRY_MATCH"
    assert ex["resolved_tool_name"] == DELEG and ex["registry_risk_class"] == "GREEN"
    assert ex["executor_boundary"] == "_run_agent" and ex["enforcement_applied"] is False


def test_peer_delegation_unregistered(monkeypatch, tmp_path):
    # kavya/arjun/meera = side-effectful (run_ops prunes DELETES, run_qa/run_trainer
    # write) -> stay UNREGISTERED_TOOL. isha IS registered (pure content-gen).
    tc = {}
    coord = _patch_coord(monkeypatch, tmp_path, [{"agent": "kavya", "task": "b"}], tc)
    _env(monkeypatch, agents="dev,kavya")  # after _patch_coord (it resets env)
    asyncio.run(coord.coordinate("build something real", execute=True))
    ex = _shadow_rows(tmp_path, "kavya")[-1]
    assert ex["registry_comparison"] == "UNREGISTERED_TOOL" and tc.get("kavya") == 1


def test_isha_delegation_registry_match(monkeypatch, tmp_path):
    tc = {}
    coord = _patch_coord(monkeypatch, tmp_path, [{"agent": "isha", "task": "c"}], tc)
    asyncio.run(coord.coordinate("build something real", execute=True))
    ex = _shadow_rows(tmp_path, "isha")[-1]
    assert ex["registry_comparison"] == "REGISTRY_MATCH"
    assert ex["resolved_tool_name"] == "agent.delegate.isha"
    assert ex["registry_risk_class"] == "GREEN"
    assert ex["executor_boundary"] == "_run_agent" and ex["enforcement_applied"] is False


def test_no_duplicate_delegation(monkeypatch, tmp_path):
    tc = {}
    coord = _patch_coord(monkeypatch, tmp_path, [{"agent": "dev", "task": "a"}], tc)
    asyncio.run(coord.coordinate("build something real", execute=True))
    assert tc.get("dev") == 1 and len(_shadow_rows(tmp_path, "dev")) == 1


def test_observer_error_no_alter(monkeypatch, tmp_path):
    tc = {}
    coord = _patch_coord(monkeypatch, tmp_path, [{"agent": "dev", "task": "a"}], tc)
    monkeypatch.setattr(
        "app.agents.harness.loop.Harness.observe",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    res = asyncio.run(coord.coordinate("build something real", execute=True))
    assert tc.get("dev") == 1 and isinstance(res, dict)


def test_expert_contribution_observed(monkeypatch, tmp_path):
    coord = pytest.importorskip("app.agents.coordinator")
    from app.agents.harness import audit

    monkeypatch.setattr(audit, "_RUN_LOG", str(tmp_path / "runs.jsonl"))
    _env(monkeypatch)
    calls = {"n": 0}

    async def dev_tool(task, goal):
        calls["n"] += 1
        return {"tool": "hashtags.research", "ok": True}

    monkeypatch.setattr(coord, "_TOOLS", {"dev": dev_tool})
    out = asyncio.run(
        coord._expert_contribution(
            {"role": "Researcher", "staff": "dev"}, "goal here", "board", True
        )
    )
    assert out["mode"] == "executed" and calls["n"] == 1
    rows = _shadow_rows(tmp_path, "dev")
    assert rows and rows[-1]["executor_boundary"] == "_expert_contribution"
    assert rows[-1]["registry_comparison"] == "REGISTRY_MATCH"


def test_both_boundaries_distinct_identities(monkeypatch, tmp_path):
    coord = pytest.importorskip("app.agents.coordinator")
    from app.agents.harness import audit

    monkeypatch.setattr(audit, "_RUN_LOG", str(tmp_path / "runs.jsonl"))
    _env(monkeypatch)

    async def dev_tool(task, goal):
        return {"tool": "hashtags.research", "ok": True}

    monkeypatch.setattr(coord, "_TOOLS", {"dev": dev_tool})
    _obs(agent="dev", boundary="_run_agent")
    asyncio.run(coord._expert_contribution({"role": "R", "staff": "dev"}, "g", "b", True))
    boundaries = {r["executor_boundary"] for r in _shadow_rows(tmp_path, "dev")}
    assert boundaries == {"_run_agent", "_expert_contribution"}


def test_flags_off_no_records(monkeypatch, tmp_path):
    coord = pytest.importorskip("app.agents.coordinator")
    from app.agents.harness import audit

    monkeypatch.setattr(audit, "_RUN_LOG", str(tmp_path / "runs.jsonl"))
    for k in (
        "AGENT_HARNESS",
        "AGENT_HARNESS_SHADOW",
        "AGENT_HARNESS_ENFORCE",
        "AGENT_HARNESS_CANARY_AGENTS",
        "AGENT_HARNESS_CANARY_LOOPS",
    ):
        monkeypatch.delenv(k, raising=False)
    assert _obs(agent="dev") is None


# ============ Delegation identity (42-48) ===========================
def test_known_agent_delegation_validates():
    ok, _ = cc.validate_delegation_target("dev")
    assert ok is True
    assert cc.delegation_identity("dev") == "agent.delegate.dev"


def test_peer_identity_scoped():
    assert resolve_coordinator_tool("isha") == ("agent.delegate.isha", "1.0.0")
    # side-effectful peers are NOT mapped (honest registry boundary)
    assert resolve_coordinator_tool("kavya") is None
    assert resolve_coordinator_tool("arjun") is None
    assert resolve_coordinator_tool("meera") is None
    assert set(COORDINATOR_TOOL_MAP) == {"dev", "isha"}  # only read-only mapped


def test_unknown_agent_denied_delegation():
    ok, err = cc.validate_delegation_target("ghost")
    assert ok is False


def test_manager_semantics_preserved():
    ok, _ = cc.validate_delegation_target("manager")
    assert ok is True  # manager is a real member/target
    assert resolve_coordinator_tool("manager") is None  # but NOT auto-registered


def test_kavach_not_delegatable():
    ok, err = cc.validate_delegation_target("kavach")
    assert ok is False


def test_tenant_identity_preserved(monkeypatch):
    _env(monkeypatch)
    assert _obs(agent="dev", tenant_id="")["tenant_id"] == "__system__"


def test_delegation_no_unrestricted_permissions():
    # agent.delegate.dev is scoped to dev only — another agent context is denied
    e = REGISTRY.evaluate_action(
        tool_name=DELEG,
        tool_version="1.0.0",
        arguments={},
        agent_id="isha",
        tenant_id="__system__",
        idempotency_key=None,
        claimed_risk=None,
    )
    assert e["registry_comparison"] == "AGENT_NOT_ALLOWED"


# ============ Registry compatibility (49-55) ========================
def _ev(**kw):
    base = {
        "tool_name": DELEG,
        "tool_version": "1.0.0",
        "arguments": {},
        "agent_id": "dev",
        "tenant_id": "__system__",
        "idempotency_key": None,
        "claimed_risk": claimed_lane(RiskClass.READ),
    }
    base.update(kw)
    return REGISTRY.evaluate_action(**base)


def test_registered_delegation_registry_match():
    assert _ev()["registry_comparison"] == "REGISTRY_MATCH" and _ev()["would_allow"] is True


def test_unregistered_coordinator_action():
    e = REGISTRY.evaluate_action(
        tool_name="isha",
        tool_version="v1",
        arguments={},
        agent_id="isha",
        tenant_id="__system__",
        idempotency_key=None,
        claimed_risk=None,
    )
    assert e["registry_comparison"] == "UNREGISTERED_TOOL"


def _cust(name, **kw):
    from app.agents.harness.registry import ToolDefinition

    base = {
        "name": name,
        "version": "1.0.0",
        "description": "x",
        "input_schema": {},
        "risk_class": RiskLane.GREEN,
        "side_effect_class": SideEffectClass.READ_ONLY,
        "authority": AuthorityClass.INTERNAL_AUTONOMOUS,
        "allowed_agents": frozenset({"dev"}),
    }
    base.update(kw)
    r = CanonicalToolRegistry()
    r.register(ToolDefinition(**base))
    return r


def test_risk_downgrade_detected():
    e = _ev(claimed_risk=claimed_lane(RiskClass.EXTERNAL_SEND))  # claim AMBER vs registry GREEN
    assert e["risk_class_mismatch"] is True and e["registry_risk_class"] == "GREEN"


def test_amber_approval_visible():
    r = _cust(
        "agent.delegate.amber",
        risk_class=RiskLane.AMBER,
        authority=AuthorityClass.APPROVAL_REQUIRED,
        requires_approval=True,
    )
    e = r.evaluate_action(
        tool_name="agent.delegate.amber",
        tool_version="1.0.0",
        arguments={},
        agent_id="dev",
        tenant_id="__system__",
        idempotency_key="k",
        claimed_risk=None,
    )
    assert e["would_require_approval"] is True and e["would_allow"] is False


def test_owner_os_preserved():
    r = _cust("agent.delegate.oos", authority=AuthorityClass.OWNER_OS_REQUIRED)
    e = r.evaluate_action(
        tool_name="agent.delegate.oos",
        tool_version="1.0.0",
        arguments={},
        agent_id="dev",
        tenant_id="__system__",
        idempotency_key="k",
        claimed_risk=None,
    )
    assert e["authority"] == "OWNER_OS_REQUIRED" and e["would_allow"] is False


def test_red_refusal_visible():
    r = _cust(
        "agent.delegate.red", risk_class=RiskLane.RED, authority=AuthorityClass.ALWAYS_REFUSED
    )
    e = r.evaluate_action(
        tool_name="agent.delegate.red",
        tool_version="1.0.0",
        arguments={},
        agent_id="dev",
        tenant_id="__system__",
        idempotency_key="k",
        claimed_risk=None,
    )
    assert e["would_deny"] is True


def test_manifest_deterministic():
    assert REGISTRY.manifest_hash() == REGISTRY.manifest_hash()


# ============ Compatibility (56-63) =================================
def test_conformance_coordinator_registered():
    from app.integrations.openclaw.harness_commands import _registry_conformance

    fam = _registry_conformance({}, actor="t", correlation_id="c")["result"]["families"]
    assert fam["coordinator"] == "registered"
    assert fam["staff.run_member"] == "registered" and fam["dag_engine"] == "registered"
    assert fam["batch_harness"] == "registered"  # supervisor registered in a later slice


def test_coordinator_read_commands():
    from app.integrations.openclaw.harness_commands import (
        _coord_contract,
        _coord_readiness,
        _coord_samples,
    )

    c = _coord_contract({}, actor="t", correlation_id="c")["result"]
    assert "DELEGATE_AGENT" in c["action_types"] and c["contract_version"] == "1.0"
    s = _coord_samples({}, actor="t", correlation_id="c")["result"]
    assert s["boundary_coverage"] == "2/2"
    r = _coord_readiness({}, actor="t", correlation_id="c")["result"]
    assert "NOT READY" in r["coordinator"] and r["enforcement"] == "OFF"


def test_staff_count_still_31():
    from app.platform import agent_registry as ar

    assert len(ar.build_registry()) == ar.CANONICAL_COUNT == 31


def test_all_enforcement_off():
    from app.agents.harness.enforce import enforcement_state

    assert enforcement_state()["AGENT_HARNESS_ENFORCE"] is False
