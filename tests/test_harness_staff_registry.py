"""staff.run_member / Nikhil canonical-registry migration tests (third family).

Nikhil composite (revenue_digest + client_health + usage_alerts) is honestly
AMBER / EXTERNAL_SEND / APPROVAL_REQUIRED because usage_alerts can send
customer upsell emails. REGISTRY_MATCH on identity; would_require_approval;
enforcement OFF; legacy run_nikhil authoritative.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from app.agents.harness.adapters import shadow
from app.agents.harness.contracts import RiskClass
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

NIK = "agent.nikhil.revenue_operations"


def _canary_env(
    mp, agents="nikhil", loops="staff.run_member", harness="1", shadowf="1", enforce="0"
):
    mp.setenv("AGENT_HARNESS", harness)
    mp.setenv("AGENT_HARNESS_SHADOW", shadowf)
    mp.setenv("AGENT_HARNESS_ENFORCE", enforce)
    mp.setenv("AGENT_HARNESS_CANARY_AGENTS", agents)
    mp.setenv("AGENT_HARNESS_CANARY_LOOPS", loops)


def _obs(member="nikhil", **kw):
    base = {
        "actual_result": {
            "ok": True,
            "results": {
                "revenue": {"ok": True},
                "client_health": {"ok": True},
                "usage_alerts": {"ok": True},
            },
        },
        "real_run_id": "r1",
    }
    base.update(kw)
    return shadow.observe_legacy_run(member, **base)


def _def(name=NIK, **kw):
    base = {
        "name": name,
        "version": "1.0.0",
        "description": "x",
        "input_schema": {
            "type": "object",
            "properties": {"requested_by": {"type": "string", "maxLength": 120}},
            "required": [],
            "additionalProperties": False,
        },
        "risk_class": RiskLane.AMBER,
        "side_effect_class": SideEffectClass.EXTERNAL_SEND,
        "authority": AuthorityClass.APPROVAL_REQUIRED,
        "requires_approval": True,
        "requires_idempotency": True,
        "allowed_agents": frozenset({"nikhil"}),
    }
    base.update(kw)
    return ToolDefinition(**base)


def _eval(**kw):
    base = {
        "tool_name": NIK,
        "tool_version": "1.0.0",
        "arguments": {},
        "agent_id": "nikhil",
        "tenant_id": "__system__",
        "idempotency_key": "shadow:x",
        "claimed_risk": claimed_lane(RiskClass.EXTERNAL_SEND),
    }
    base.update(kw)
    return REGISTRY.evaluate_action(**base)


# ============ Mapping (1-6) ==========================================
def test_nikhil_maps_exact():
    assert shadow.resolve_staff_tool("nikhil") == (NIK, "1.0.0")


def test_peer_member_unmapped():
    assert shadow.resolve_staff_tool("kavya") is None
    assert shadow.resolve_staff_tool("manager") is None


def test_unknown_member_unmapped():
    assert shadow.resolve_staff_tool("does_not_exist") is None


def test_mapping_conflict_rejected():
    r = CanonicalToolRegistry()
    r.register(_def())
    with pytest.raises(RegistryConflict):
        r.register(_def(description="DIFFERENT"))


def test_no_wildcard_or_auto_registration():
    # Only the one mapped member; the map is not derived from STAFF membership.
    assert set(shadow.STAFF_TOOL_MAP) == {"nikhil"}
    assert "*" not in shadow.STAFF_TOOL_MAP


def test_function_name_not_public_identity():
    assert REGISTRY.get("run_nikhil") is None
    assert REGISTRY.get("staff.run_nikhil") is None
    assert REGISTRY.get(NIK, "1.0.0") is not None


# ============ Definition & schema (7-17) =============================
def test_definition_validates():
    d = REGISTRY.get(NIK, "1.0.0")
    assert d.risk_class is RiskLane.AMBER
    assert d.side_effect_class is SideEffectClass.EXTERNAL_SEND
    assert d.authority is AuthorityClass.APPROVAL_REQUIRED


def test_canonical_dotted_format():
    import re

    assert re.match(r"^[a-z][a-z0-9]*(?:\.[a-z0-9_]+){1,}$", NIK)


def test_exact_version_resolves():
    assert REGISTRY.resolve(NIK, "1.0.0").version == "1.0.0"
    assert REGISTRY.resolve(NIK, "9.9.9") is None


def test_valid_input_passes():
    assert _eval(arguments={})["registry_comparison"] == "REGISTRY_MATCH"
    assert _eval(arguments={"requested_by": "scheduler"})["registry_comparison"] == "REGISTRY_MATCH"


def test_unexpected_field_fails():
    assert _eval(arguments={"foo": 1})["registry_comparison"] == "SCHEMA_MISMATCH"


def test_wrong_type_fails():
    assert _eval(arguments={"requested_by": 123})["registry_comparison"] == "SCHEMA_MISMATCH"


def test_oversized_input_bounded():
    assert _eval(arguments={"requested_by": "x" * 5000})["registry_comparison"] == "SCHEMA_MISMATCH"


def test_output_schema_present():
    d = REGISTRY.get(NIK, "1.0.0")
    assert d.output_schema and d.output_schema.get("type") == "object"


def test_budget_metadata_visible():
    d = REGISTRY.get(NIK, "1.0.0")
    assert d.cost_class == "free" and d.budget_scope == "internal_ops"


def test_idempotency_metadata_visible():
    d = REGISTRY.get(NIK, "1.0.0")
    assert d.requires_idempotency is True
    # no idempotency key => IDEMPOTENCY_REQUIRED
    assert _eval(idempotency_key=None)["registry_comparison"] == "IDEMPOTENCY_REQUIRED"


def test_approval_metadata_visible():
    d = REGISTRY.get(NIK, "1.0.0")
    assert d.requires_approval is True


# ============ Identity & policy (18-28) =============================
def test_nikhil_agent_allowed():
    assert _eval(agent_id="nikhil")["agent_permission"] is True


def test_peer_agent_denied():
    assert _eval(agent_id="rohan")["registry_comparison"] == "AGENT_NOT_ALLOWED"


def test_manager_no_implicit_permission():
    assert _eval(agent_id="manager")["registry_comparison"] == "AGENT_NOT_ALLOWED"


def test_system_scope_allowed():
    assert _eval(tenant_id="__system__")["tenant_permission"] is True


def test_wrong_tenant_denied():
    assert _eval(tenant_id="client:acme")["registry_comparison"] == "TENANT_NOT_ALLOWED"


def test_registry_risk_wins_over_claimed():
    # claim GREEN (READ) vs registry AMBER -> mismatch, registry wins
    e = _eval(claimed_risk=claimed_lane(RiskClass.READ))
    assert e["risk_class_mismatch"] is True
    assert e["registry_risk_class"] == "AMBER"


def test_approval_requirement_visible():
    e = _eval()
    assert e["would_require_approval"] is True and e["would_allow"] is False


def test_owner_os_authority_preserved():
    r = CanonicalToolRegistry()
    r.register(_def(name="agent.nikhil.owneros", authority=AuthorityClass.OWNER_OS_REQUIRED))
    e = r.evaluate_action(
        tool_name="agent.nikhil.owneros",
        tool_version="1.0.0",
        arguments={},
        agent_id="nikhil",
        tenant_id="__system__",
        idempotency_key="k",
        claimed_risk=None,
    )
    assert e["authority"] == "OWNER_OS_REQUIRED" and e["would_allow"] is False


def test_disabled_definition_denies():
    r = CanonicalToolRegistry()
    r.register(_def(name="agent.nikhil.disabled", enabled_by_default=False))
    e = r.evaluate_action(
        tool_name="agent.nikhil.disabled",
        tool_version="1.0.0",
        arguments={},
        agent_id="nikhil",
        tenant_id="__system__",
        idempotency_key="k",
        claimed_risk=None,
    )
    assert e["registry_comparison"] == "DISABLED" and e["would_deny"] is True


def test_version_mismatch_visible():
    assert _eval(tool_version="2.0.0")["registry_comparison"] == "VERSION_MISMATCH"


def test_unknown_member_unregistered_eval():
    e = REGISTRY.evaluate_action(
        tool_name="staff.run_kavya",
        tool_version="v1",
        arguments={},
        agent_id="kavya",
        tenant_id="__system__",
        idempotency_key="k",
        claimed_risk=None,
    )
    assert e["registry_comparison"] == "UNREGISTERED_TOOL"


# ============ Real-loop integration (29-40) =========================
def _run_real(monkeypatch, tmp_path, member="nikhil", nikhil_result=None, raise_exc=False):
    staff = pytest.importorskip("app.agents.staff")
    from app.agents.harness import audit

    monkeypatch.setattr(audit, "_RUN_LOG", str(tmp_path / "runs.jsonl"))
    _canary_env(monkeypatch, agents="nikhil,kavya")
    monkeypatch.setattr("app.platform.agent_controls.is_paused", lambda k: False, raising=False)
    calls = {"n": 0}
    res_default = {
        "ok": True,
        "results": {
            "revenue": {"ok": True},
            "client_health": {"ok": True},
            "usage_alerts": {"ok": True},
        },
    }

    async def fake_nikhil():
        calls["n"] += 1
        if raise_exc:
            raise RuntimeError("nikhil boom")
        return nikhil_result if nikhil_result is not None else res_default

    monkeypatch.setattr(staff, "run_nikhil", fake_nikhil)
    res = asyncio.run(staff.run_member(member))
    rows = [json.loads(x) for x in open(tmp_path / "runs.jsonl", encoding="utf-8")]
    sh = [
        r["extra"] for r in rows if r.get("kind") == "shadow" and r["extra"].get("agent") == member
    ]
    return staff, res, calls, (sh[-1] if sh else None)


def test_real_legacy_executes_once(monkeypatch, tmp_path):
    _, res, calls, ex = _run_real(monkeypatch, tmp_path)
    assert calls["n"] == 1 and res.get("ok") is True


def test_real_harness_executes_zero(monkeypatch, tmp_path):
    # observer must never invoke the tool; only the one legacy call happens
    _, res, calls, ex = _run_real(monkeypatch, tmp_path)
    assert calls["n"] == 1 and ex is not None


def test_real_registry_match(monkeypatch, tmp_path):
    _, res, calls, ex = _run_real(monkeypatch, tmp_path)
    assert ex["execution_comparison"] == "MATCH"
    assert ex["registry_comparison"] == "REGISTRY_MATCH"
    assert ex["resolved_tool_name"] == NIK and ex["resolved_tool_version"] == "1.0.0"
    assert ex["registry_risk_class"] == "AMBER" and ex["authority"] == "APPROVAL_REQUIRED"
    assert ex["registry_would_require_approval"] is True
    assert ex["enforcement_applied"] is False


def test_real_success_result_unchanged(monkeypatch, tmp_path):
    _, res, calls, ex = _run_real(monkeypatch, tmp_path)
    assert res == {
        "ok": True,
        "results": {
            "revenue": {"ok": True},
            "client_health": {"ok": True},
            "usage_alerts": {"ok": True},
        },
    }


def test_real_exception_path(monkeypatch, tmp_path):
    _, res, calls, ex = _run_real(monkeypatch, tmp_path, raise_exc=True)
    assert res.get("error") and calls["n"] == 1
    assert ex["comparison_verdict"] == "LEGACY_ERROR"


def test_real_observer_failure_no_alter(monkeypatch, tmp_path):
    staff = pytest.importorskip("app.agents.staff")
    _canary_env(monkeypatch)
    monkeypatch.setattr("app.platform.agent_controls.is_paused", lambda k: False, raising=False)
    monkeypatch.setattr(
        "app.agents.harness.loop.Harness.observe",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    calls = {"n": 0}

    async def fake_nikhil():
        calls["n"] += 1
        return {"ok": True, "results": {"revenue": {"ok": True}}}

    monkeypatch.setattr(staff, "run_nikhil", fake_nikhil)
    res = asyncio.run(staff.run_member("nikhil"))
    assert res.get("ok") is True and calls["n"] == 1  # unaffected


def test_real_peer_unregistered(monkeypatch, tmp_path):
    staff = pytest.importorskip("app.agents.staff")
    from app.agents.harness import audit

    monkeypatch.setattr(audit, "_RUN_LOG", str(tmp_path / "runs.jsonl"))
    _canary_env(monkeypatch, agents="nikhil,kavya")
    monkeypatch.setattr("app.platform.agent_controls.is_paused", lambda k: False, raising=False)
    calls = {"n": 0}

    async def fake_ops():
        calls["n"] += 1
        return {"ok": True}

    monkeypatch.setattr(staff, "run_ops", fake_ops)  # kavya -> run_ops
    asyncio.run(staff.run_member("kavya"))
    rows = [json.loads(x) for x in open(tmp_path / "runs.jsonl", encoding="utf-8")]
    sh = [
        r["extra"] for r in rows if r.get("kind") == "shadow" and r["extra"].get("agent") == "kavya"
    ]
    assert sh and sh[-1]["registry_comparison"] == "UNREGISTERED_TOOL"
    assert calls["n"] == 1


def test_real_flags_off_no_records(monkeypatch, tmp_path):
    staff = pytest.importorskip("app.agents.staff")
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
    monkeypatch.setattr("app.platform.agent_controls.is_paused", lambda k: False, raising=False)
    calls = {"n": 0}

    async def fake_nikhil():
        calls["n"] += 1
        return {"ok": True, "results": {"revenue": {"ok": True}}}

    monkeypatch.setattr(staff, "run_nikhil", fake_nikhil)
    res = asyncio.run(staff.run_member("nikhil"))
    assert res.get("ok") is True and calls["n"] == 1
    import os

    assert not os.path.exists(tmp_path / "runs.jsonl")  # no records written


def test_explain_shows_layers(monkeypatch, tmp_path):
    from app.agents.harness import audit
    from app.integrations.openclaw.harness_commands import _explain

    monkeypatch.setattr(audit, "_RUN_LOG", str(tmp_path / "runs.jsonl"))
    _canary_env(monkeypatch)
    shadow.observe_legacy_run(
        "nikhil",
        real_run_id="exp1",
        actual_result={"ok": True, "results": {"revenue": {"ok": True}}},
    )
    res = _explain({"run_id": "exp1"}, actor="t", correlation_id="c")
    assert res["result"]["layers"].get("shadow_observation", 0) >= 1


# ============ Composite & failure semantics (41-46) =================
def test_composite_summary_bounded(monkeypatch):
    _canary_env(monkeypatch)
    rec = _obs()
    assert rec["composite_action"] is True
    assert rec["components"] == ["client_health", "revenue", "usage_alerts"]
    assert rec["component_count"] == 3


def test_partial_failure_not_full_success(monkeypatch):
    _canary_env(monkeypatch)
    rec = _obs(
        actual_result={
            "ok": True,
            "results": {
                "revenue": {"ok": True},
                "client_health": {"ok": True},
                "usage_alerts": {"error": "smtp down"},
            },
        }
    )
    assert rec["partial_success"] is True and rec["full_success"] is False
    assert rec["components_failed"] == 1 and rec["components_ok"] == 2


def test_full_failure_represented(monkeypatch):
    _canary_env(monkeypatch)
    rec = _obs(
        actual_result={
            "ok": True,
            "results": {
                "revenue": {"error": "a"},
                "client_health": {"error": "b"},
                "usage_alerts": {"error": "c"},
            },
        }
    )
    assert rec["full_success"] is False and rec["components_failed"] == 3
    assert rec["partial_success"] is False  # zero ok => not partial


def test_total_latency_captured(monkeypatch):
    _canary_env(monkeypatch)
    rec = _obs(latency_ms=1234)
    assert rec["latency_ms"] == 1234


def test_side_effect_classification_accurate(monkeypatch):
    _canary_env(monkeypatch)
    rec = _obs()
    assert rec["side_effect_class"] == "external_send"  # usage_alerts can send


def test_shadow_ref_stable_no_real_idempotency(monkeypatch):
    _canary_env(monkeypatch)
    a = _obs(real_run_id="R", action_index=0)
    b = _obs(real_run_id="R", action_index=0)
    assert a["shadow_run_id"] == b["shadow_run_id"] == "shadow:R:0"  # stable, non-executable
    assert a["shadow_run_id"].startswith("shadow:")  # NOT a real idempotency key


# ============ Compatibility (47-54) =================================
def test_staff_count_still_31():
    from app.platform import agent_registry as ar

    assert len(ar.build_registry()) == ar.CANONICAL_COUNT == 31


def test_three_families_registered():
    from app.integrations.openclaw.harness_commands import _registry_conformance

    fam = _registry_conformance({}, actor="t", correlation_id="c")["result"]["families"]
    assert fam["staff.run_member"] == "registered"
    assert fam["dag_engine"] == "registered"
    assert fam["batch_harness"] == "registered"
    # coordinator + supervisor registered in later slices (agent.delegate.*)


def test_harness_tool_shows_nikhil_definition():
    from app.integrations.openclaw.harness_commands import _tool

    d = _tool({"name": NIK}, actor="t", correlation_id="c")["result"]["definition"]
    assert d["risk_class"] == "AMBER" and d["authority"] == "APPROVAL_REQUIRED"
    assert d["requires_approval"] is True and d["requires_idempotency"] is True
    # listing-safe: no callable/executor exposed
    assert "executor" not in json.dumps(d).lower()


def test_manifest_hash_deterministic():
    assert REGISTRY.manifest_hash() == REGISTRY.manifest_hash()


def test_kavach_outside_staff_roster():
    from app.platform import agent_registry as ar

    reg = ar.build_registry()
    ids = set(reg.keys()) if isinstance(reg, dict) else {getattr(a, "agent_id", a) for a in reg}
    assert "kavach" not in {str(x).lower() for x in ids}
