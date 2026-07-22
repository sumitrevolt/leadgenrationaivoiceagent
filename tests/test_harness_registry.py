"""Canonical tool registry + structured action-contract tests (shadow-only)."""

import asyncio
import json

import pytest
from pydantic import BaseModel, ConfigDict

from app.agents.harness import Harness, RiskClass, RunContext, ToolCall, ToolRegistry
from app.agents.harness.registry import (
    REGISTRY,
    AuthorityClass,
    CanonicalToolRegistry,
    RegistryConflict,
    RiskLane,
    SideEffectClass,
    ToolDefinition,
    claimed_lane,
)

SAFE = "batch.internal.safe_calculation"


def _def(name, **kw):
    base = {
        "name": name,
        "version": "1.0.0",
        "description": "t",
        "risk_class": RiskLane.GREEN,
        "side_effect_class": SideEffectClass.READ_ONLY,
        "authority": AuthorityClass.INTERNAL_AUTONOMOUS,
        "allowed_agents": frozenset({"nikhil"}),
        "allowed_tenant_scopes": frozenset({"__system__"}),
    }
    base.update(kw)
    return ToolDefinition(**base)


# ---- definitions -----------------------------------------------------
def test_valid_registers():
    r = CanonicalToolRegistry()
    r.register(_def("a.b.c"))
    assert r.resolve("a.b.c", "1.0.0")


def test_invalid_name_rejected():
    with pytest.raises(Exception):  # noqa: B017
        _def("run_dev")  # not dotted/domain form


def test_invalid_version_rejected():
    with pytest.raises(Exception):  # noqa: B017
        _def("a.b.c", version="v1")


def test_unknown_enum_rejected():
    with pytest.raises(Exception):  # noqa: B017
        ToolDefinition(
            name="a.b.c",
            version="1.0.0",
            description="t",
            risk_class="PURPLE",
            side_effect_class=SideEffectClass.NONE,
            authority=AuthorityClass.INTERNAL_AUTONOMOUS,
        )


def test_duplicate_identical_idempotent():
    r = CanonicalToolRegistry()
    r.register(_def("a.b.c"))
    r.register(_def("a.b.c"))  # no raise
    assert len(r.list_versions("a.b.c")) == 1


def test_conflicting_duplicate_rejected():
    r = CanonicalToolRegistry()
    r.register(_def("a.b.c"))
    with pytest.raises(RegistryConflict):
        r.register(_def("a.b.c", description="DIFFERENT"))


def test_disabled_denied():
    r = CanonicalToolRegistry()
    r.register(_def("a.b.c", enabled_by_default=False))
    e = r.evaluate_action(
        tool_name="a.b.c",
        tool_version="1.0.0",
        arguments={},
        agent_id="nikhil",
        tenant_id="__system__",
        idempotency_key=None,
        claimed_risk=None,
    )
    assert e["registry_comparison"] == "DISABLED" and e["would_deny"] is True


def test_listing_no_callables():
    tools = REGISTRY.list_tools()
    blob = json.dumps(tools)
    assert "executor" not in blob.lower() or "fn=" not in blob  # public view omits raw callables
    assert all("input_schema_keys" in t for t in tools)


# ---- versioning / manifest ------------------------------------------
def test_exact_version_resolves():
    r = CanonicalToolRegistry()
    r.register(_def("a.b.c"))
    r.register(_def("a.b.c", version="2.0.0"))
    assert r.resolve("a.b.c", "1.0.0").version == "1.0.0"


def test_unknown_tool_fail_closed():
    e = REGISTRY.evaluate_action(
        tool_name="no.such.tool",
        tool_version="1.0.0",
        arguments={},
        agent_id="nikhil",
        tenant_id="__system__",
        idempotency_key=None,
        claimed_risk=None,
    )
    assert e["registry_comparison"] == "UNREGISTERED_TOOL" and e["would_deny"] is True


def test_major_not_auto_upgraded():
    e = REGISTRY.evaluate_action(
        tool_name=SAFE,
        tool_version="2.0.0",
        arguments={"id": "x"},
        agent_id="nikhil",
        tenant_id="__system__",
        idempotency_key=None,
        claimed_risk=None,
    )
    assert e["registry_comparison"] == "VERSION_MISMATCH"


def test_manifest_hash_stable_and_changes():
    r1 = CanonicalToolRegistry()
    r1.register(_def("a.b.c"))
    r2 = CanonicalToolRegistry()
    r2.register(_def("a.b.c"))
    assert r1.manifest_hash() == r2.manifest_hash()
    r2.register(_def("a.b.d"))
    assert r1.manifest_hash() != r2.manifest_hash()


# ---- action validation ----------------------------------------------
def test_valid_action_registry_match():
    e = REGISTRY.evaluate_action(
        tool_name=SAFE,
        tool_version="1.0.0",
        arguments={"id": "x"},
        agent_id="nikhil",
        tenant_id="__system__",
        idempotency_key=None,
        claimed_risk=claimed_lane(RiskClass.READ),
    )
    assert e["registry_comparison"] == "REGISTRY_MATCH" and e["would_allow"] is True


def test_wrong_arg_type_fails():
    e = REGISTRY.evaluate_action(
        tool_name=SAFE,
        tool_version="1.0.0",
        arguments={"id": 123},
        agent_id="nikhil",
        tenant_id="__system__",
        idempotency_key=None,
        claimed_risk=None,
    )
    assert e["registry_comparison"] == "SCHEMA_MISMATCH"


def test_missing_required_fails():
    e = REGISTRY.evaluate_action(
        tool_name=SAFE,
        tool_version="1.0.0",
        arguments={},
        agent_id="nikhil",
        tenant_id="__system__",
        idempotency_key=None,
        claimed_risk=None,
    )
    assert e["registry_comparison"] == "SCHEMA_MISMATCH"


def test_unexpected_arg_fails():
    e = REGISTRY.evaluate_action(
        tool_name=SAFE,
        tool_version="1.0.0",
        arguments={"id": "x", "z": 1},
        agent_id="nikhil",
        tenant_id="__system__",
        idempotency_key=None,
        claimed_risk=None,
    )
    assert e["registry_comparison"] == "SCHEMA_MISMATCH"


def test_agent_not_allowed():
    e = REGISTRY.evaluate_action(
        tool_name=SAFE,
        tool_version="1.0.0",
        arguments={"id": "x"},
        agent_id="manager",
        tenant_id="__system__",
        idempotency_key=None,
        claimed_risk=None,
    )
    assert e["registry_comparison"] == "AGENT_NOT_ALLOWED"


def test_tenant_not_allowed():
    e = REGISTRY.evaluate_action(
        tool_name=SAFE,
        tool_version="1.0.0",
        arguments={"id": "x"},
        agent_id="nikhil",
        tenant_id="client:acme",
        idempotency_key=None,
        claimed_risk=None,
    )
    assert e["registry_comparison"] == "TENANT_NOT_ALLOWED"


def test_idempotency_required():
    r = CanonicalToolRegistry()
    r.register(
        _def(
            "crm.lead.write",
            side_effect_class=SideEffectClass.WRITE_TENANT,
            requires_idempotency=True,
            allowed_tenant_scopes=frozenset({"*"}),
        )
    )
    e = r.evaluate_action(
        tool_name="crm.lead.write",
        tool_version="1.0.0",
        arguments={},
        agent_id="nikhil",
        tenant_id="client:x",
        idempotency_key=None,
        claimed_risk=None,
    )
    assert e["registry_comparison"] == "IDEMPOTENCY_REQUIRED" and e["would_deny"] is True


def test_risk_downgrade_detected():
    r = CanonicalToolRegistry()
    r.register(_def("x.y.z", risk_class=RiskLane.AMBER, authority=AuthorityClass.APPROVAL_REQUIRED))
    e = r.evaluate_action(
        tool_name="x.y.z",
        tool_version="1.0.0",
        arguments={},
        agent_id="nikhil",
        tenant_id="__system__",
        idempotency_key=None,
        claimed_risk=RiskLane.GREEN,
    )
    assert e["risk_class_mismatch"] is True and e["would_require_approval"] is True


# ---- negative AMBER / RED (tripwire never invoked) ------------------
def test_amber_requires_approval_no_exec():
    r = CanonicalToolRegistry()
    r.register(
        _def(
            "content.draft.customer",
            risk_class=RiskLane.AMBER,
            authority=AuthorityClass.APPROVAL_REQUIRED,
            requires_approval=True,
        )
    )
    e = r.evaluate_action(
        tool_name="content.draft.customer",
        tool_version="1.0.0",
        arguments={},
        agent_id="nikhil",
        tenant_id="__system__",
        idempotency_key=None,
        claimed_risk=None,
    )
    assert e["would_require_approval"] is True and e["authority"] == "APPROVAL_REQUIRED"
    assert e["would_allow"] is False


def test_red_always_refused_no_exec():
    r = CanonicalToolRegistry()
    r.register(
        _def(
            "shell.exec.run",
            risk_class=RiskLane.RED,
            side_effect_class=SideEffectClass.CODE_EXECUTION,
            authority=AuthorityClass.ALWAYS_REFUSED,
            sandbox_required=True,
        )
    )
    e = r.evaluate_action(
        tool_name="shell.exec.run",
        tool_version="1.0.0",
        arguments={},
        agent_id="nikhil",
        tenant_id="__system__",
        idempotency_key=None,
        claimed_risk=RiskLane.GREEN,
    )
    assert (
        e["would_allow"] is False and e["would_deny"] is True and e["authority"] == "ALWAYS_REFUSED"
    )


# ---- observe() layering (execution vs registry) ---------------------
class _AnyArgs(BaseModel):
    model_config = ConfigDict(extra="allow")


def _observe(tool, tver, args, agent="nikhil", tenant="__system__"):
    reg = ToolRegistry(permission_fn=lambda a, t: True)
    reg.register(tool, lambda **_: None, _AnyArgs, RiskClass.READ)
    ctx = RunContext(agent=agent, tenant_id=tenant, source_loop="batch_harness")
    call = ToolCall(name=tool, tool_version=tver, args=args, idempotency_key="shadow:x")
    return Harness(registry=reg).observe(ctx, call, actual_result={"ok": True})


def test_observe_registered_layered():
    rec = _observe(SAFE, "1.0.0", {"id": "x"})
    assert rec["execution_comparison"] == "MATCH"  # execution layer unchanged
    assert rec["registry_comparison"] == "REGISTRY_MATCH"  # registry layer added
    assert rec["registry_would_allow"] is True and rec["authority"] == "INTERNAL_AUTONOMOUS"


def test_observe_unregistered_layered():
    rec = _observe("batch.execute.safe_calc", "v1", {"id": "x"})
    assert rec["execution_comparison"] == "MATCH"  # legacy execution still MATCH
    assert rec["registry_comparison"] == "UNREGISTERED_TOOL"
    assert rec["registry_would_deny"] is True


# ---- REAL run_batch: registered vs unregistered ---------------------
def test_real_batch_registered_vs_unregistered(monkeypatch, tmp_path):
    bh = pytest.importorskip("app.agents.batch_harness")
    from app.agents.harness import audit

    monkeypatch.setattr(audit, "_RUN_LOG", str(tmp_path / "r.jsonl"))
    monkeypatch.setattr(bh, "_DIR", str(tmp_path / "b"))
    for k, v in {
        "AGENT_HARNESS": "1",
        "AGENT_HARNESS_SHADOW": "1",
        "AGENT_HARNESS_ENFORCE": "0",
        "AGENT_HARNESS_CANARY_AGENTS": "nikhil",
        "AGENT_HARNESS_CANARY_LOOPS": "batch_harness",
    }.items():
        monkeypatch.setenv(k, v)

    calls = {"n": 0}

    async def green_calc(item):
        calls["n"] += 1
        return {"ok": True, "summary": item["id"]}

    items = [{"id": f"i{i}"} for i in range(3)]
    # registered
    out = asyncio.run(
        bh.run_batch(
            green_calc,
            items,
            concurrency=2,
            ckpt_id="reg",
            agent_id="nikhil",
            tenant_id="__system__",
            tool_name="batch.internal.safe_calculation",
            tool_version="1.0.0",
        )
    )
    assert out["done"] == 3 and calls["n"] == 3
    rows = [json.loads(x) for x in open(tmp_path / "r.jsonl", encoding="utf-8")]
    reg_acts = [
        r for r in rows if r.get("kind") == "shadow" and r["extra"].get("batch_run_id") == "reg"
    ]
    assert len(reg_acts) == 3
    assert all(r["extra"]["registry_comparison"] == "REGISTRY_MATCH" for r in reg_acts)
    assert all(r["extra"]["execution_comparison"] == "MATCH" for r in reg_acts)

    # unregistered legacy (no tool_name) — still executes, records UNREGISTERED_TOOL
    calls["n"] = 0
    out2 = asyncio.run(
        bh.run_batch(green_calc, items, concurrency=2, ckpt_id="unreg", agent_id="nikhil")
    )
    assert out2["done"] == 3 and calls["n"] == 3
    rows2 = [json.loads(x) for x in open(tmp_path / "r.jsonl", encoding="utf-8")]
    unreg = [
        r for r in rows2 if r.get("kind") == "shadow" and r["extra"].get("batch_run_id") == "unreg"
    ]
    assert len(unreg) == 3
    assert all(r["extra"]["registry_comparison"] == "UNREGISTERED_TOOL" for r in unreg)
    assert all(r["extra"]["execution_comparison"] == "MATCH" for r in unreg)
