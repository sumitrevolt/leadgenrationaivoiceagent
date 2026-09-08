"""supervisor / staff_supervisor canonical-registry migration tests (5th family).

Reuses CoordinatorActionV1 via SupervisorDecisionV1. Dev route REUSES
agent.delegate.dev (GREEN). Rohan route registers agent.delegate.rohan (AMBER,
outreach — honest). staff_supervisor real graph is optional-dep gated. Enforcement
OFF; legacy LangGraph authoritative.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from pydantic import ValidationError

from app.agents.harness import coordinator_contract as cc
from app.agents.harness.adapters import observe_supervisor_action
from app.agents.harness.adapters import supervisor_shadow as ss
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

DEV, ROHAN = "agent.delegate.dev", "agent.delegate.rohan"
SS = cc.SelectionSource


def _env(mp, agents="dev,rohan", loops="supervisor"):
    mp.setenv("AGENT_HARNESS", "1")
    mp.setenv("AGENT_HARNESS_SHADOW", "1")
    mp.setenv("AGENT_HARNESS_ENFORCE", "0")
    mp.setenv("AGENT_HARNESS_CANARY_AGENTS", agents)
    mp.setenv("AGENT_HARNESS_CANARY_LOOPS", loops)


def setup_function(_):
    ss._SEEN.clear()


def _obs(agent="dev", route="data_agent", impl="supervisor", **kw):
    base = {
        "supervisor_run_id": "s1",
        "graph_run_id": "g1",
        "graph_step": 1,
        "tool_call_id": None,
        "supervisor_implementation": impl,
        "actor_id": "manager",
        "delegated_agent_id": agent,
        "tenant_id": "",
        "tool_name": route,
        "tool_arguments": {"task": "t"},
        "actual_executor": f"{route}_node",
        "actual_result": {"route": route},
        "graph_metadata": {
            "selection_source": "GRAPH_ROUTE",
            "route_label": route,
            "actual_node": f"{route}_node",
        },
    }
    base.update(kw)
    return observe_supervisor_action(**base)


def _dec(**kw):
    base = {
        "decision_id": "d0",
        "supervisor_implementation": "supervisor",
        "actor_id": "manager",
        "target_agent": "dev",
        "task": "t",
        "route_label": "data_agent",
        "graph_run_id": "g1",
        "graph_step": 0,
        "selection_source": SS.GRAPH_ROUTE,
    }
    base.update(kw)
    return cc.SupervisorDecisionV1(**base)


# ============ Shared contract reuse (1-10) ==========================
def test_decision_converts_to_coordinator_action():
    act = _dec().to_coordinator_action(tool_name=DEV, tool_version="1.0.0")
    assert isinstance(act, cc.CoordinatorActionV1)
    assert act.action_type is cc.CoordinatorActionType.DELEGATE_AGENT
    assert act.target_agent == "dev" and act.tool_name == DEV


def test_no_duplicate_supervisor_schema():
    # SupervisorDecisionV1 normalizes INTO CoordinatorActionV1 — not a fork.
    assert issubclass(cc.CoordinatorActionV1, __import__("pydantic").BaseModel)
    assert _dec().to_coordinator_action().schema_version == "1.0"


def test_schema_version_is_1():
    assert _dec().schema_version == "1.0"


def test_extra_fields_fail():
    with pytest.raises(ValidationError):
        cc.SupervisorDecisionV1(
            decision_id="d",
            supervisor_implementation="supervisor",
            actor_id="m",
            target_agent="dev",
            graph_run_id="g",
            graph_step=0,
            bogus=1,
        )


def test_unknown_implementation_fails():
    with pytest.raises(ValidationError):
        _dec(supervisor_implementation="ceo_bot")


def test_unknown_target_fails():
    with pytest.raises(ValidationError):
        _dec(target_agent="ghost")


def test_kavach_target_fails():
    with pytest.raises(ValidationError):
        _dec(target_agent="kavach")


def test_invalid_graph_step_fails():
    with pytest.raises(ValidationError):
        _dec(graph_step=-1)


def test_oversized_task_fails():
    with pytest.raises(ValidationError):
        _dec(task="x" * 3000)


def test_invalid_arguments_fail():
    with pytest.raises(ValidationError):
        _dec(arguments="notdict")


# ============ supervisor.py mapping (11-20) =========================
def test_data_route_maps_to_dev(monkeypatch):
    _env(monkeypatch)
    rec = _obs(agent="dev", route="data_agent")
    assert rec["resolved_tool_name"] == DEV and rec["registry_comparison"] == "REGISTRY_MATCH"


def test_leads_route_maps_to_rohan(monkeypatch):
    _env(monkeypatch)
    rec = _obs(agent="rohan", route="leads_agent")
    assert rec["resolved_tool_name"] == ROHAN and rec["registry_risk_class"] == "AMBER"


def test_unknown_route_unregistered(monkeypatch):
    _env(monkeypatch, agents="kavya")
    rec = _obs(agent="kavya", route="leads_agent")
    assert rec["registry_comparison"] == "UNREGISTERED_TOOL"


def test_route_node_mismatch_detected(monkeypatch):
    _env(monkeypatch)
    rec = _obs(agent="rohan", route="data_agent")  # route says data (dev), agent is rohan
    assert rec["route_node_mismatch"] is True


def test_actual_executor_recorded(monkeypatch):
    _env(monkeypatch)
    rec = _obs(agent="dev", route="data_agent")
    assert rec["actual_node"] == "data_agent_node"


def test_manager_preserved_as_actor(monkeypatch):
    _env(monkeypatch)
    rec = _obs(agent="dev", actor_id="manager")
    assert rec["actor_id"] == "manager" and rec["delegated_agent"] == "dev"


def test_target_preserved_separately(monkeypatch):
    _env(monkeypatch)
    rec = _obs(agent="dev")
    assert rec["delegated_agent_id"] == "dev" and rec["actor_id"] == "manager"


def test_node_identity_not_public_tool(monkeypatch):
    _env(monkeypatch)
    rec = _obs(agent="dev", route="data_agent")
    assert rec["resolved_tool_name"] == DEV  # canonical, not "data_agent_node"
    assert rec["actual_node"] != rec["resolved_tool_name"]


def test_stable_action_id(monkeypatch):
    _env(monkeypatch)
    rec = _obs(agent="dev")
    assert rec["shadow_run_id"] == "shadow:g1:1:0"


def test_arguments_bounded_hashed(monkeypatch):
    _env(monkeypatch)
    rec = _obs(agent="dev")
    assert "normalized_arguments_hash" in rec and len(rec["normalized_arguments_hash"]) <= 16


# ============ staff_supervisor.py mapping (21-30) ===================
def test_staff_sup_structured_agent_maps(monkeypatch):
    _env(monkeypatch)
    rec = _obs(
        agent="dev",
        impl="staff_supervisor",
        route=None,
        graph_metadata={
            "selection_source": "MESSAGE_NAME",
            "actual_node": "staff_supervisor.graph",
        },
    )
    assert rec["registry_comparison"] == "REGISTRY_MATCH" and rec["resolved_tool_name"] == DEV


def test_staff_sup_message_name_tagged(monkeypatch):
    _env(monkeypatch)
    rec = _obs(
        agent="dev",
        impl="staff_supervisor",
        graph_metadata={"selection_source": "MESSAGE_NAME", "actual_node": "g"},
    )
    assert rec["selection_source"] == "MESSAGE_NAME"


def test_staff_sup_node_identity_tagged(monkeypatch):
    _env(monkeypatch)
    rec = _obs(
        agent="dev",
        impl="staff_supervisor",
        graph_metadata={"selection_source": "NODE_IDENTITY", "actual_node": "g"},
    )
    assert rec["selection_source"] == "NODE_IDENTITY"


def test_heuristic_source_blocks_registry(monkeypatch):
    _env(monkeypatch, agents="kavya")
    rec = _obs(
        agent="kavya",
        impl="staff_supervisor",
        route=None,
        tool_name="",
        graph_metadata={"selection_source": "HEURISTIC", "actual_node": "g"},
    )
    assert rec["selection_source"] == "HEURISTIC"
    assert rec["comparison_verdict"] == "PARSER_AMBIGUITY"
    assert rec["registry_comparison"] == "UNREGISTERED_TOOL"


def test_unknown_selection_missing_context(monkeypatch):
    _env(monkeypatch, agents="kavya")
    rec = _obs(
        agent="kavya",
        impl="staff_supervisor",
        route=None,
        tool_name="",
        graph_metadata={"selection_source": "UNKNOWN", "actual_node": "g"},
    )
    assert rec["comparison_verdict"] == "MISSING_CONTEXT"


def test_staff_sup_real_graph_gated_or_runs(monkeypatch):
    # Honest: staff_supervisor real graph is optional-dep + flag gated. Prove the
    # module constructs and returns a bounded dict (never raises) either way.
    stsup = pytest.importorskip("app.agents.staff_supervisor")
    res = stsup.get_staff_supervisor().run("safe internal status synthesis")
    assert isinstance(res, dict) and ("ok" in res)
    if res.get("ok") is False:
        assert "reason" in res  # explicit optional-dep/flag block reported


def test_observer_failure_no_alter(monkeypatch):
    _env(monkeypatch)
    monkeypatch.setattr(
        "app.agents.harness.loop.Harness.observe",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    assert _obs(agent="dev") is None  # swallowed, never raises


def test_no_duplicate_agent_execution(monkeypatch):
    _env(monkeypatch)
    a = _obs(agent="dev", graph_step=1)
    b = _obs(agent="dev", graph_step=1)  # same key -> dedup
    assert a is not None and b is None  # second suppressed (shadow write only)


def test_actor_target_identity_preserved(monkeypatch):
    _env(monkeypatch)
    rec = _obs(agent="dev", actor_id="manager")
    assert rec["actor_id"] == "manager" and rec["delegated_agent_id"] == "dev"


def test_tenant_preserved(monkeypatch):
    _env(monkeypatch)
    assert _obs(agent="dev", tenant_id="")["tenant_id"] == "__system__"
    assert _obs(agent="dev", tenant_id="client:x", graph_step=2)["tenant_id"] == "client:x"


# ============ Registry (31-42) ======================================
def _ev(tool=DEV, agent="dev", risk=RiskClass.READ, **kw):
    base = {
        "tool_name": tool,
        "tool_version": "1.0.0",
        "arguments": {},
        "agent_id": agent,
        "tenant_id": "__system__",
        "idempotency_key": "k",
        "claimed_risk": claimed_lane(risk),
    }
    base.update(kw)
    return REGISTRY.evaluate_action(**base)


def test_dev_reused_when_semantics_match():
    e = _ev(tool=DEV, agent="dev", risk=RiskClass.READ, idempotency_key=None)
    assert e["registry_comparison"] == "REGISTRY_MATCH" and e["registry_risk_class"] == "GREEN"
    assert REGISTRY.get(DEV, "1.0.0") is not None  # single shared definition


def test_conflicting_dev_rejected():
    from app.agents.harness.registry import ToolDefinition

    r = CanonicalToolRegistry()
    r.register(REGISTRY.get(DEV, "1.0.0"))
    with pytest.raises(RegistryConflict):
        r.register(
            ToolDefinition(
                name=DEV,
                version="1.0.0",
                description="DIFFERENT",
                risk_class=RiskLane.RED,
                side_effect_class=SideEffectClass.NONE,
                authority=AuthorityClass.INTERNAL_AUTONOMOUS,
            )
        )


def test_rohan_registered_amber():
    d = REGISTRY.get(ROHAN, "1.0.0")
    assert d.risk_class is RiskLane.AMBER and d.side_effect_class is SideEffectClass.EXTERNAL_SEND
    assert d.authority is AuthorityClass.APPROVAL_REQUIRED


def test_rohan_route_approval_required():
    e = _ev(tool=ROHAN, agent="rohan", risk=RiskClass.EXTERNAL_SEND)
    assert e["registry_comparison"] == "REGISTRY_MATCH" and e["would_require_approval"] is True
    assert e["would_allow"] is False


def test_peer_agent_denied():
    e = _ev(tool=DEV, agent="rohan", idempotency_key=None)
    assert e["registry_comparison"] == "AGENT_NOT_ALLOWED"


def test_wrong_tenant_denied():
    e = _ev(tool=DEV, agent="dev", tenant_id="client:acme", idempotency_key=None)
    assert e["registry_comparison"] == "TENANT_NOT_ALLOWED"


def test_risk_downgrade_detected():
    e = _ev(tool=ROHAN, agent="rohan", risk=RiskClass.READ)  # claim GREEN vs registry AMBER
    assert e["risk_class_mismatch"] is True and e["registry_risk_class"] == "AMBER"


def test_amber_approval_visible():
    assert (
        _ev(tool=ROHAN, agent="rohan", risk=RiskClass.EXTERNAL_SEND)["would_require_approval"]
        is True
    )


def test_owner_os_preserved():
    from app.agents.harness.registry import ToolDefinition

    r = CanonicalToolRegistry()
    r.register(
        ToolDefinition(
            name="agent.delegate.oos2",
            version="1.0.0",
            description="x",
            risk_class=RiskLane.GREEN,
            side_effect_class=SideEffectClass.NONE,
            authority=AuthorityClass.OWNER_OS_REQUIRED,
            allowed_agents=frozenset({"dev"}),
        )
    )
    e = r.evaluate_action(
        tool_name="agent.delegate.oos2",
        tool_version="1.0.0",
        arguments={},
        agent_id="dev",
        tenant_id="__system__",
        idempotency_key="k",
        claimed_risk=None,
    )
    assert e["authority"] == "OWNER_OS_REQUIRED" and e["would_allow"] is False


def test_red_refusal_visible():
    from app.agents.harness.registry import ToolDefinition

    r = CanonicalToolRegistry()
    r.register(
        ToolDefinition(
            name="agent.delegate.red2",
            version="1.0.0",
            description="x",
            risk_class=RiskLane.RED,
            side_effect_class=SideEffectClass.NONE,
            authority=AuthorityClass.ALWAYS_REFUSED,
            allowed_agents=frozenset({"dev"}),
        )
    )
    e = r.evaluate_action(
        tool_name="agent.delegate.red2",
        tool_version="1.0.0",
        arguments={},
        agent_id="dev",
        tenant_id="__system__",
        idempotency_key="k",
        claimed_risk=None,
    )
    assert e["would_deny"] is True


def test_unregistered_route_honest():
    e = REGISTRY.evaluate_action(
        tool_name="supervisor.staff_supervisor",
        tool_version="v1",
        arguments={},
        agent_id="kavya",
        tenant_id="__system__",
        idempotency_key="k",
        claimed_risk=None,
    )
    assert e["registry_comparison"] == "UNREGISTERED_TOOL"


def test_manifest_deterministic():
    assert REGISTRY.manifest_hash() == REGISTRY.manifest_hash()


# ============ Real supervisor.py graph (43-50) ======================
class _FakeBrain:
    def __init__(self, counter):
        self.c = counter

    async def generate_response(self, **kw):
        self.c["n"] += 1
        return "safe internal plan (fixture)"


def _rows(tmp_path, agent=None):
    rows = [json.loads(x) for x in open(tmp_path / "runs.jsonl", encoding="utf-8")]
    r = [
        x["extra"]
        for x in rows
        if x.get("kind") == "shadow" and x["extra"].get("source_loop") == "supervisor"
    ]
    return [x for x in r if agent is None or x.get("delegated_agent") == agent]


def _real_sup(monkeypatch, tmp_path, route):
    sup = pytest.importorskip("app.agents.supervisor")
    if not sup.AGENTS_AVAILABLE:
        pytest.skip("langgraph not installed")
    from app.agents.harness import audit

    monkeypatch.setattr(audit, "_RUN_LOG", str(tmp_path / "runs.jsonl"))
    _env(monkeypatch, agents="dev,rohan")
    counter = {"n": 0}

    async def fake_route(task):
        return route

    monkeypatch.setattr(sup, "semantic_route_for_task", fake_route)
    monkeypatch.setattr(sup, "_llm_brain", lambda: _FakeBrain(counter))
    res = asyncio.run(sup.run_supervisor_task("internal research/plan task", niche="general"))
    return sup, res, counter


def test_real_data_route_node_once_registry_match(monkeypatch, tmp_path):
    sup, res, counter = _real_sup(monkeypatch, tmp_path, "data_agent")
    assert res["route"] == "data_agent" and counter["n"] == 1  # node executed once
    ex = _rows(tmp_path, "dev")[-1]
    assert ex["registry_comparison"] == "REGISTRY_MATCH" and ex["resolved_tool_name"] == DEV
    assert ex["enforcement_applied"] is False


def test_real_leads_route_rohan_amber(monkeypatch, tmp_path):
    sup, res, counter = _real_sup(monkeypatch, tmp_path, "leads_agent")
    assert res["route"] == "leads_agent" and counter["n"] == 1
    ex = _rows(tmp_path, "rohan")[-1]
    assert ex["registry_comparison"] == "REGISTRY_MATCH" and ex["registry_risk_class"] == "AMBER"
    assert ex["registry_would_require_approval"] is True


def test_real_harness_executes_zero(monkeypatch, tmp_path):
    sup, res, counter = _real_sup(monkeypatch, tmp_path, "data_agent")
    assert counter["n"] == 1  # only the legacy node; harness ran nothing
    assert len(_rows(tmp_path, "dev")) == 1


def test_real_no_extra_iteration(monkeypatch, tmp_path):
    sup, res, counter = _real_sup(monkeypatch, tmp_path, "data_agent")
    assert counter["n"] == 1 and res.get("result")


def test_real_flags_off_no_records(monkeypatch, tmp_path):
    sup = pytest.importorskip("app.agents.supervisor")
    if not sup.AGENTS_AVAILABLE:
        pytest.skip("langgraph not installed")
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
    counter = {"n": 0}

    async def fake_route(task):
        return "data_agent"

    monkeypatch.setattr(sup, "semantic_route_for_task", fake_route)
    monkeypatch.setattr(sup, "_llm_brain", lambda: _FakeBrain(counter))
    res = asyncio.run(sup.run_supervisor_task("task", niche="general"))
    import os

    assert res["route"] == "data_agent" and counter["n"] == 1
    assert not os.path.exists(tmp_path / "runs.jsonl")


# ============ Correlation / replay (51-58) ==========================
def test_parent_action_recorded(monkeypatch):
    _env(monkeypatch)
    rec = _obs(agent="dev")
    assert rec["parent_action_id"].startswith("s1")


def test_target_agent_recorded(monkeypatch):
    _env(monkeypatch)
    assert _obs(agent="dev")["delegated_agent_id"] == "dev"


def test_duplicate_callback_suppressed(monkeypatch):
    _env(monkeypatch)
    a = _obs(agent="dev", graph_step=5)
    b = _obs(agent="dev", graph_step=5)
    assert a is not None and b is None


def test_genuine_retry_separate(monkeypatch):
    _env(monkeypatch)
    a = _obs(agent="dev", graph_step=5, attempt=0)
    b = _obs(agent="dev", graph_step=5, attempt=1)  # distinct attempt
    assert a is not None and b is not None


def test_implementations_no_collide(monkeypatch):
    _env(monkeypatch)
    a = _obs(agent="dev", graph_step=7, impl="supervisor")
    b = _obs(agent="dev", graph_step=7, impl="staff_supervisor", tool_call_id="tc1")
    assert a is not None and b is not None  # different tool_call_id/context


def test_direct_staff_no_fake_child(monkeypatch):
    _env(monkeypatch)
    rec = _obs(agent="dev")
    # only a parent supervisor action; no manufactured downstream child event
    assert rec["parent_run_id"] == rec["source_run_id"]


# ============ Compatibility (59-69) =================================
def test_five_families_conformance():
    from app.integrations.openclaw.harness_commands import _registry_conformance

    fam = _registry_conformance({}, actor="t", correlation_id="c")["result"]["families"]
    for f in ("staff.run_member", "dag_engine", "coordinator", "supervisor", "batch_harness"):
        assert fam[f] == "registered"


def test_supervisor_read_commands():
    from app.integrations.openclaw.harness_commands import (
        _sup_contract,
        _sup_readiness,
        _sup_samples,
    )

    c = _sup_contract({}, actor="t", correlation_id="c")["result"]
    assert "supervisor" in c["implementations"] and "staff_supervisor" in c["implementations"]
    assert _sup_samples({}, actor="t", correlation_id="c")["result"]["registered_delegations"]
    r = _sup_readiness({}, actor="t", correlation_id="c")["result"]
    assert "NOT READY" in r["supervisor_family"] and r["enforcement"] == "OFF"


def test_staff_count_31():
    from app.platform import agent_registry as ar

    assert len(ar.build_registry()) == ar.CANONICAL_COUNT == 31


def test_all_enforcement_off():
    from app.agents.harness.enforce import enforcement_state

    st = enforcement_state()
    assert st["AGENT_HARNESS_ENFORCE"] is False and st["bound_executors"] == [
        "batch.internal.safe_calculation@1.0.0"
    ]  # no supervisor executor binding


def test_harness_tool_shows_rohan_amber():
    from app.integrations.openclaw.harness_commands import _tool

    d = _tool({"name": ROHAN}, actor="t", correlation_id="c")["result"]["definition"]
    assert d["risk_class"] == "AMBER" and d["authority"] == "APPROVAL_REQUIRED"
    assert "executor" not in json.dumps(d).lower()


# ============ staff_supervisor REAL graph proof (closure) ===========
def _fake_supervisor_model():
    """Deterministic local model preserving the REAL langgraph-supervisor graph:
    routes to 'dev' via a handoff tool call once per invocation, then finalizes.
    No network / provider call."""
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatGeneration, ChatResult

    class _Fake(BaseChatModel):
        _bound: object = None

        @property
        def _llm_type(self):
            return "fake-supervisor"

        def bind_tools(self, tools, **kw):
            object.__setattr__(self, "_bound", tools)
            return self

        def _generate(self, messages, stop=None, run_manager=None, **kw):
            names = [
                getattr(t, "name", None) or (t.get("name") if isinstance(t, dict) else None)
                for t in (self._bound or [])
            ]
            transfer = next((n for n in names if n and n.startswith("transfer_to_dev")), None)
            has_dev = any(getattr(m, "name", None) == "dev" for m in (messages or []))
            if transfer and not has_dev:
                m = AIMessage(content="", tool_calls=[{"name": transfer, "args": {}, "id": "c1"}])
            else:
                m = AIMessage(content="dev plan ready (fixture)")
            return ChatResult(generations=[ChatGeneration(message=m)])

    return _Fake()


def test_staff_supervisor_real_graph_registry_match(monkeypatch, tmp_path):
    pytest.importorskip("langgraph_supervisor")
    pytest.importorskip("langchain_openai")
    import langchain_openai

    monkeypatch.setattr(langchain_openai, "ChatOpenAI", lambda *a, **k: _fake_supervisor_model())
    st = pytest.importorskip("app.agents.staff_supervisor")
    from app.agents.harness import audit

    monkeypatch.setattr(audit, "_RUN_LOG", str(tmp_path / "runs.jsonl"))
    _env(monkeypatch, agents="dev,rohan")
    monkeypatch.setenv("USE_LANGGRAPH_SUPERVISOR", "1")
    monkeypatch.setenv("CEREBRAS_API_KEY", "fake-local-key")
    monkeypatch.setattr(st, "_singleton", None, raising=False)

    sup = st.get_staff_supervisor()
    assert sup.active is True  # REAL graph constructed
    res = sup.run("Dev se kb research plan banwao")
    assert res.get("ok") is True  # REAL graph invoked
    import json as _j

    rows = [_j.loads(x) for x in open(tmp_path / "runs.jsonl", encoding="utf-8")]
    sh = [
        r["extra"]
        for r in rows
        if r.get("kind") == "shadow"
        and r["extra"].get("supervisor_implementation") == "staff_supervisor"
    ]
    assert sh, "no staff_supervisor shadow record from real graph"
    ex = sh[-1]
    assert ex["delegated_agent"] == "dev" and ex["selection_source"] == "MESSAGE_NAME"
    assert ex["registry_comparison"] == "REGISTRY_MATCH"
    assert ex["resolved_tool_name"] == DEV and ex["registry_risk_class"] == "GREEN"
    assert ex["enforcement_applied"] is False


def test_staff_supervisor_kavach_never_selectable(monkeypatch):
    # Kavach is not in STAFF, so it can never author a react-agent message.
    from app.platform.team import STAFF

    assert "kavach" not in {str(k).lower() for k in STAFF.keys()}
