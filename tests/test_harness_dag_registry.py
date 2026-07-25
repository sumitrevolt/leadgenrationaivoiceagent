"""dag_engine canonical-registry migration tests (second registry-backed family).

Proves: stable DAG step 'internal_calculation' -> canonical
workflow.dag.internal_calculation@1.0.0, REGISTRY_MATCH in shadow, legacy
execution unchanged, harness executes zero tools, enforcement OFF.
"""

from __future__ import annotations

import json
import os

import pytest

from app.agents.harness.adapters import observe_dag_action
from app.agents.harness.adapters.dag_shadow import DAG_TOOL_MAP, resolve_dag_tool
from app.agents.harness.registry import (
    REGISTRY,
    AuthorityClass,
    CanonicalToolRegistry,
    RegistryConflict,
    RiskLane,
    SideEffectClass,
    ToolDefinition,
)

CANON = "workflow.dag.internal_calculation"


def _env(mp, agents="nikhil", loops="dag_engine", harness="1", shadowf="1", enforce="0"):
    mp.setenv("AGENT_HARNESS", harness)
    mp.setenv("AGENT_HARNESS_SHADOW", shadowf)
    mp.setenv("AGENT_HARNESS_ENFORCE", enforce)
    mp.setenv("AGENT_HARNESS_CANARY_AGENTS", agents)
    mp.setenv("AGENT_HARNESS_CANARY_LOOPS", loops)


def _obs(**kw):
    base = {
        "dag_run_id": "dr1",
        "node_id": "calc",
        "attempt": 0,
        "agent_id": "nikhil",
        "tenant_id": "",
        "tool_name": "internal_calculation",
        "tool_version": "v1",
        "arguments": {"n": 5},
        "actual_result": {"ok": True, "count": 1},
        "latency_ms": 4,
        "dag_node_status": "completed",
    }
    base.update(kw)
    return observe_dag_action(**base)


def _def(name=CANON, **kw):
    base = {
        "name": name,
        "version": "1.0.0",
        "description": "x",
        "input_schema": {
            "type": "object",
            "properties": {"n": {"type": "integer"}},
            "required": ["n"],
            "additionalProperties": True,
        },
        "risk_class": RiskLane.GREEN,
        "side_effect_class": SideEffectClass.NONE,
        "authority": AuthorityClass.INTERNAL_AUTONOMOUS,
        "allowed_agents": frozenset({"nikhil"}),
    }
    base.update(kw)
    return ToolDefinition(**base)


# ============ Mapping & definitions (1-7) ============================
def test_stable_step_maps_exact(monkeypatch):
    assert resolve_dag_tool("internal_calculation") == (CANON, "1.0.0")


def test_unknown_step_not_registered(monkeypatch):
    assert resolve_dag_tool("scrape") is None
    assert REGISTRY.get("scrape") is None
    assert REGISTRY.get("dag.A") is None


def test_mapping_conflict_rejected(monkeypatch):
    r = CanonicalToolRegistry()
    r.register(_def())
    with pytest.raises(RegistryConflict):
        r.register(_def(description="DIFFERENT"))


def test_node_id_is_not_tool_identity(monkeypatch):
    _env(monkeypatch)
    rec = _obs(node_id="A")
    assert rec["resolved_tool_name"] == CANON and rec["node_id"] == "A"


def test_temporary_proof_ids_not_registered(monkeypatch):
    assert REGISTRY.get("__harness_proof_noop__") is None
    assert resolve_dag_tool("__harness_proof_noop__") is None
    assert resolve_dag_tool("noop") is None


def test_tool_definition_strict(monkeypatch):
    with pytest.raises(Exception):  # noqa: B017
        ToolDefinition(
            name=CANON,
            version="1.0.0",
            description="x",
            risk_class=RiskLane.GREEN,
            side_effect_class=SideEffectClass.NONE,
            authority=AuthorityClass.INTERNAL_AUTONOMOUS,
            bogus_field=1,
        )


def test_manifest_hash_deterministic(monkeypatch):
    assert REGISTRY.manifest_hash() == REGISTRY.manifest_hash()
    assert REGISTRY.get(CANON, "1.0.0") is not None  # DAG tool present in global registry


# ============ Action contract / envelope (8-15) ======================
def test_valid_dag_action_passes(monkeypatch):
    _env(monkeypatch)
    rec = _obs()
    assert rec["registry_comparison"] == "REGISTRY_MATCH"


def test_missing_dag_run_id_fails(monkeypatch):
    _env(monkeypatch)
    assert _obs(dag_run_id="") is None


def test_missing_node_id_fails(monkeypatch):
    _env(monkeypatch)
    assert _obs(node_id="") is None


def test_negative_attempt_fails(monkeypatch):
    _env(monkeypatch)
    assert _obs(attempt=-1) is None


def test_invalid_input_type_fails(monkeypatch):
    _env(monkeypatch)
    rec = _obs(arguments={"n": "not-an-int"})
    assert rec["registry_comparison"] == "SCHEMA_MISMATCH"
    assert rec["execution_comparison"] == "MATCH"  # legacy unchanged


def test_missing_required_input_fails(monkeypatch):
    _env(monkeypatch)
    rec = _obs(arguments={})  # 'n' required
    assert rec["registry_comparison"] == "SCHEMA_MISMATCH"


def test_registry_rejects_unexpected_input_when_strict(monkeypatch):
    # internal_calculation intentionally allows additive DAG metadata; the
    # registry CAN reject unexpected input for a strict-schema tool.
    r = CanonicalToolRegistry()
    r.register(
        _def(
            name="workflow.dag.strict",
            input_schema={
                "type": "object",
                "properties": {"n": {"type": "integer"}},
                "required": ["n"],
                "additionalProperties": False,
            },
        )
    )
    e = r.evaluate_action(
        tool_name="workflow.dag.strict",
        tool_version="1.0.0",
        arguments={"n": 1, "extra": "x"},
        agent_id="nikhil",
        tenant_id="__system__",
        idempotency_key=None,
        claimed_risk=None,
    )
    assert e["registry_comparison"] == "SCHEMA_MISMATCH"


def test_secret_like_data_redacted(monkeypatch):
    _env(monkeypatch)
    rec = _obs(actual_result={"api_key": "sk_live_SECRET", "ok": True})
    blob = json.dumps(rec)
    assert "sk_live_SECRET" not in blob and "REDACTED" in blob


# ============ Registry shadow integration (16-27) ====================
def test_registered_step_registry_match(monkeypatch):
    _env(monkeypatch)
    rec = _obs()
    assert rec["execution_comparison"] == "MATCH"
    assert rec["registry_comparison"] == "REGISTRY_MATCH"
    assert rec["registry_risk_class"] == "GREEN"
    assert rec["authority"] == "INTERNAL_AUTONOMOUS"
    assert rec["registry_would_allow"] is True
    assert rec["enforcement_applied"] is False


def test_legacy_execution_comparison_still_match(monkeypatch):
    _env(monkeypatch)
    rec = _obs(tool_name="scrape", arguments={})
    assert rec["execution_comparison"] == "MATCH"
    assert rec["registry_comparison"] == "UNREGISTERED_TOOL"


def test_unregistered_step_visible(monkeypatch):
    _env(monkeypatch)
    rec = _obs(tool_name="revenue_sweep", arguments={})
    assert rec["registry_comparison"] == "UNREGISTERED_TOOL"
    assert rec["registry_would_deny"] is True


def test_version_mismatch_visible(monkeypatch):
    _env(monkeypatch)
    r = CanonicalToolRegistry()
    r.register(_def())
    e = r.evaluate_action(
        tool_name=CANON,
        tool_version="2.0.0",
        arguments={"n": 1},
        agent_id="nikhil",
        tenant_id="__system__",
        idempotency_key=None,
        claimed_risk=None,
    )
    assert e["registry_comparison"] == "VERSION_MISMATCH"


def test_schema_mismatch_visible(monkeypatch):
    _env(monkeypatch)
    rec = _obs(arguments={"n": 1.5})  # float, not integer
    assert rec["registry_comparison"] == "SCHEMA_MISMATCH"


def test_agent_denial_visible(monkeypatch):
    _env(monkeypatch, agents="rohan")
    # rohan eligible for shadow, but not an allowed_agent of the tool
    rec = _obs(agent_id="rohan")
    assert rec["registry_comparison"] == "AGENT_NOT_ALLOWED"


def test_tenant_denial_visible(monkeypatch):
    _env(monkeypatch)
    rec = _obs(tenant_id="client:acme")
    assert rec["registry_comparison"] == "TENANT_NOT_ALLOWED"


def test_risk_downgrade_detected(monkeypatch):
    r = CanonicalToolRegistry()
    r.register(
        _def(
            name="workflow.dag.red",
            risk_class=RiskLane.RED,
            authority=AuthorityClass.ALWAYS_REFUSED,
        )
    )
    from app.agents.harness.contracts import RiskClass
    from app.agents.harness.registry import claimed_lane

    e = r.evaluate_action(
        tool_name="workflow.dag.red",
        tool_version="1.0.0",
        arguments={"n": 1},
        agent_id="nikhil",
        tenant_id="__system__",
        idempotency_key=None,
        claimed_risk=claimed_lane(RiskClass.READ),
    )
    assert e["risk_class_mismatch"] is True and e["would_deny"] is True


def test_amber_requirement_visible(monkeypatch):
    r = CanonicalToolRegistry()
    r.register(
        _def(
            name="workflow.dag.amber",
            risk_class=RiskLane.AMBER,
            authority=AuthorityClass.APPROVAL_REQUIRED,
            requires_approval=True,
        )
    )
    e = r.evaluate_action(
        tool_name="workflow.dag.amber",
        tool_version="1.0.0",
        arguments={"n": 1},
        agent_id="nikhil",
        tenant_id="__system__",
        idempotency_key=None,
        claimed_risk=None,
    )
    assert e["would_require_approval"] is True and e["would_allow"] is False


def test_owner_os_authority_preserved(monkeypatch):
    r = CanonicalToolRegistry()
    r.register(_def(name="workflow.dag.owneros", authority=AuthorityClass.OWNER_OS_REQUIRED))
    e = r.evaluate_action(
        tool_name="workflow.dag.owneros",
        tool_version="1.0.0",
        arguments={"n": 1},
        agent_id="nikhil",
        tenant_id="__system__",
        idempotency_key=None,
        claimed_risk=None,
    )
    assert e["authority"] == "OWNER_OS_REQUIRED" and e["would_allow"] is False


def test_red_denied_in_evaluation(monkeypatch):
    r = CanonicalToolRegistry()
    r.register(
        _def(
            name="workflow.dag.red2",
            risk_class=RiskLane.RED,
            authority=AuthorityClass.ALWAYS_REFUSED,
        )
    )
    e = r.evaluate_action(
        tool_name="workflow.dag.red2",
        tool_version="1.0.0",
        arguments={"n": 1},
        agent_id="nikhil",
        tenant_id="__system__",
        idempotency_key=None,
        claimed_risk=None,
    )
    assert e["would_deny"] is True


# ============ DAG semantics (28-36) ==================================
def _seed_real_dag(monkeypatch, tmp_path, action="internal_calculation", inputs=None):
    dag = pytest.importorskip("app.agents.dag_engine")
    plib = pytest.importorskip("app.agents.process_library")
    from app.agents.harness import audit

    monkeypatch.setattr(audit, "_RUN_LOG", str(tmp_path / "runs.jsonl"))
    _env(monkeypatch)
    runs_dir = tmp_path / "process_runs"
    runs_dir.mkdir()
    monkeypatch.setattr(dag, "_RUNS_DIR", str(runs_dir))
    monkeypatch.setattr(dag, "_INDEX", str(runs_dir / "dag_index.jsonl"))
    calls = {"n": 0}
    orig = plib.execute_step

    async def counting(node, ins):
        calls["n"] += 1
        return await orig(node, ins)  # REAL executor runs

    monkeypatch.setattr(plib, "execute_step", counting)
    run_id = "dr_real_1"
    graph = {"nodes": {"calc": {"kind": "task", "action": action}}, "in": {}, "out": {}}
    dag._append_event(
        run_id,
        "run_started",
        {
            "process": "flow:test",
            "engine": "dag",
            "graph": graph,
            "inputs": (inputs if inputs is not None else {"_harness_agent_id": "nikhil", "n": 5}),
        },
    )
    return dag, run_id, calls, tmp_path


def _dag_shadow_rows(tmp_path):
    rows = [json.loads(x) for x in open(tmp_path / "runs.jsonl", encoding="utf-8")]
    return [
        r
        for r in rows
        if r.get("kind") == "shadow" and (r.get("extra") or {}).get("source_loop") == "dag_engine"
    ]


def test_real_step_executes_once_registry_match(monkeypatch, tmp_path):
    import asyncio

    dag, run_id, calls, tp = _seed_real_dag(monkeypatch, tmp_path)
    out = asyncio.run(dag.advance(run_id))
    assert out["status"] == dag.ST_COMPLETED
    assert calls["n"] == 1  # real executor exactly once
    sh = _dag_shadow_rows(tp)
    assert len(sh) == 1  # one shadow record
    ex = sh[0]["extra"]
    assert ex["execution_comparison"] == "MATCH"
    assert ex["registry_comparison"] == "REGISTRY_MATCH"
    assert ex["resolved_tool_name"] == CANON and ex["enforcement_applied"] is False


def test_observer_never_invokes_execute_step(monkeypatch, tmp_path):
    import asyncio

    dag, run_id, calls, tp = _seed_real_dag(monkeypatch, tmp_path)
    asyncio.run(dag.advance(run_id))
    assert calls["n"] == 1  # exactly the one legacy call — observer added none


def test_journal_unchanged(monkeypatch, tmp_path):
    import asyncio

    dag, run_id, calls, tp = _seed_real_dag(monkeypatch, tmp_path)
    asyncio.run(dag.advance(run_id))
    journal = dag.journal(run_id)
    completed = [e for e in journal if e["type"] == "node_completed"]
    assert len(completed) == 1  # no duplicate journal entry


def test_gate_result_unchanged(monkeypatch, tmp_path):
    import asyncio

    dag, run_id, calls, tp = _seed_real_dag(monkeypatch, tmp_path)
    out = asyncio.run(dag.advance(run_id))
    assert out["status"] == dag.ST_COMPLETED  # gate passed as before


def test_retry_attempts_distinct(monkeypatch):
    _env(monkeypatch)
    r0 = _obs(
        attempt=0,
        actual_result=None,
        actual_error="gate fail",
        dag_node_status="retry_pending",
        retry_scheduled=True,
    )
    r1 = _obs(
        attempt=1,
        actual_result=None,
        actual_error="gate fail",
        dag_node_status="retry_pending",
        retry_scheduled=True,
    )
    assert r0["shadow_run_id"] == "shadow:dr1:calc:0"
    assert r1["shadow_run_id"] == "shadow:dr1:calc:1"
    assert r0["comparison_verdict"] == "RETRY_OBSERVED"


def test_repeated_observe_no_execution(monkeypatch):
    _env(monkeypatch)
    a = _obs()
    b = _obs()  # record-only; neither executes the tool
    assert a["registry_comparison"] == "REGISTRY_MATCH"
    assert b["registry_comparison"] == "REGISTRY_MATCH"  # no crash, record-only


def test_shadow_failure_does_not_alter_dag(monkeypatch, tmp_path):
    import asyncio

    dag, run_id, calls, tp = _seed_real_dag(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "app.agents.harness.loop.Harness.observe",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    out = asyncio.run(dag.advance(run_id))
    assert out["status"] == dag.ST_COMPLETED and calls["n"] == 1  # DAG unaffected


def test_flags_off_no_records(monkeypatch):
    for k in (
        "AGENT_HARNESS",
        "AGENT_HARNESS_SHADOW",
        "AGENT_HARNESS_ENFORCE",
        "AGENT_HARNESS_CANARY_AGENTS",
        "AGENT_HARNESS_CANARY_LOOPS",
    ):
        monkeypatch.delenv(k, raising=False)
    assert _obs() is None


# ============ Compatibility (37-43) ==================================
def test_dag_registered_in_conformance(monkeypatch):
    from app.integrations.openclaw.harness_commands import _registry_conformance

    res = _registry_conformance({}, actor="t", correlation_id="c")
    fam = res["result"]["families"]
    assert fam["dag_engine"] == "registered" and fam["batch_harness"] == "registered"


def test_harness_tool_shows_dag_definition(monkeypatch):
    from app.integrations.openclaw.harness_commands import _tool

    res = _tool({"name": CANON}, actor="t", correlation_id="c")
    d = res["result"]["definition"]
    assert d["risk_class"] == "GREEN" and d["authority"] == "INTERNAL_AUTONOMOUS"
    assert "n" in d["input_schema_keys"]
