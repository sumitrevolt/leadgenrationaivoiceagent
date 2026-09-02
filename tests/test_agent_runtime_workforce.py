"""Workforce factory — 31 capabilities, Wave-B pilots, Swara frozen transfer."""

from __future__ import annotations

import pytest

from app.platform import agent_registry as ar
from app.platform import agent_runtime as rt
from app.platform import agent_runtime_workforce as wf
from app.platform.team import STAFF


@pytest.fixture(autouse=True)
def isolated_runtime(tmp_path, monkeypatch):
    monkeypatch.setattr(rt, "_STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setattr(rt, "_USAGE_PATH", str(tmp_path / "usage.json"))
    monkeypatch.setattr(rt, "_DLQ_PATH", str(tmp_path / "dlq.jsonl"))
    monkeypatch.setattr(rt, "_BACKOFF_BASE_S", 0.0)
    monkeypatch.setattr(rt, "_kill_engaged", lambda key: False)
    monkeypatch.setattr(rt, "_approval_approved", lambda tenant, ref: False)

    caps_snapshot = dict(rt._CAPABILITIES)
    monkeypatch.setenv("AGENT_RUNTIME_CANCEL_BACKEND", "memory")
    monkeypatch.setenv("AGENT_RUNTIME_IDEM_BACKEND", "memory")
    from app.platform import agent_runtime_cancellation as crc
    from app.platform import agent_runtime_idempotency as arid

    crc.reset_memory_for_tests()
    arid.reset_memory_for_tests()
    rt._ACTIVE.clear()
    rt._ACTIVE_TASKS.clear()
    rt._CAPABILITIES.clear()

    monkeypatch.setenv("AGENT_RUNTIME", "1")
    monkeypatch.setenv("OPS_HEALTH_AGENT", "1")
    monkeypatch.setenv("AFTERNOON_CONTENT", "1")
    monkeypatch.setenv("SOCIAL_ENGINE", "1")
    monkeypatch.setenv("SRE_AGENT", "1")
    monkeypatch.setenv("INFRA_HANDLER", "1")
    monkeypatch.setenv("MCP_ENGINEER", "1")
    monkeypatch.setenv("DBRE_AGENT", "1")
    monkeypatch.setenv("DATA_INTEGRITY_AGENT", "1")
    yield
    rt._CAPABILITIES.clear()
    rt._CAPABILITIES.update(caps_snapshot)
    crc.reset_memory_for_tests()
    arid.reset_memory_for_tests()
    rt._ACTIVE.clear()
    rt._ACTIVE_TASKS.clear()


def test_workforce_registers_all_31_staff():
    wf.ensure_workforce_registered()
    wf.ensure_workforce_registered()  # idempotent
    assert len(STAFF) == 31
    for aid in STAFF:
        assert rt.capabilities_for(aid), f"{aid} missing capability"


async def test_swara_red_blocked_async():
    wf.ensure_workforce_registered()
    assert wf.ACTION_FROZEN in rt.capabilities_for("swara")
    assert "swara" not in rt.PILOT_AGENTS
    res = await rt.submit("swara", wf.ACTION_FROZEN)
    assert res.status == "blocked"
    assert "red_lane" in res.reason


async def test_wave_b_pranav_sre_success(monkeypatch):
    wf.ensure_workforce_registered()

    def _fake_sre():
        return {"ok": True, "score": 88, "read_only": True}

    monkeypatch.setattr(
        "app.platform.engineer_agents.run_sre",
        _fake_sre,
    )
    res = await rt.submit("pranav", wf.ACTION_OWNED)
    assert res.status == "succeeded"
    assert res.output["check"] == "sre"
    assert res.output["result"]["score"] == 88


async def test_nikhil_delivery_scan_read_only(monkeypatch):
    wf.ensure_workforce_registered()
    monkeypatch.setenv("DELIVERY_ASSURANCE_AGENT", "1")
    monkeypatch.setenv("AGENT_RUNTIME", "1")

    def _fake_scan(limit=100, include_healthy=False):
        return {"missed": [], "at_risk": [], "limit": limit}

    monkeypatch.setattr(
        "app.marketing.delivery_assurance.scan_missed_deliverables",
        _fake_scan,
    )
    res = await rt.submit("nikhil", wf.ACTION_DELIVERY_SCAN)
    assert res.status == "succeeded"
    assert res.output["read_only"] is True
    assert res.output["customer_contacted"] is False


async def test_runtime_context_carries_enterprise_profile_and_tenant_scope(monkeypatch):
    monkeypatch.delenv("AGENT_MATURITY_CONTEXT", raising=False)
    seen = {}

    async def _probe(ctx):
        seen["profile"] = ctx.maturity_profile
        seen["skills"] = ctx.skill_brief
        seen["knowledge"] = ctx.knowledge_brief
        return {"ok": True}

    rt.register_capability(
        rt.AgentCapability(
            agent_id="kavya",
            action="maturity_probe",
            fn=_probe,
            side_effect="none",
            tenant_scoped=True,
        )
    )
    res = await rt.submit("kavya", "maturity_probe", tenant_id="tenant-A")
    assert res.status == "succeeded"
    assert seen["profile"]["setup_state"] == "enterprise_profile_ready"
    assert seen["profile"]["memory"]["namespace"].startswith("staff/kavya/tenant/")
    assert seen["skills"] == "" and seen["knowledge"] == ""


async def test_amber_hold_not_in_pilot():
    wf.ensure_workforce_registered()
    assert "rohan" not in rt.PILOT_AGENTS
    assert wf.ACTION_OWNED in rt.capabilities_for("rohan")
    res = await rt.submit("rohan", wf.ACTION_OWNED)
    assert res.status == "blocked"
    assert res.reason == "not_in_pilot_rollout"


def test_rollout_state_matrix_honest():
    wf.ensure_workforce_registered()
    out = wf.workforce_rollout_state()
    assert out["staff_count"] == 31
    assert "swara" in out["frozen_voice"]
    by_id = {a["agent_id"]: a for a in out["agents"]}
    assert by_id["swara"]["rollout_state"] == "intentionally_disabled"
    assert by_id["kavya"]["rollout_state"] == "canary_ready"
    assert by_id["rohan"]["rollout_state"] == "rollout_hold"
    assert by_id["neha"]["rollout_state"] == "rollout_hold"
    assert "neha" not in rt.PILOT_AGENTS
    assert "pranav" in rt.PILOT_AGENTS
    assert ar.validate_registry() == []


async def test_neha_mutate_hold_not_dispatchable():
    wf.ensure_workforce_registered()
    res = await rt.submit("neha", wf.ACTION_OWNED)
    assert res.status == "blocked"
    assert res.reason == "not_in_pilot_rollout"


def test_openclaw_swara_status_transfer():
    from app.integrations.openclaw.commands import _agent_status

    out = _agent_status({"agent_id": "swara"}, actor="test", correlation_id="c1")
    assert out["status"] == "SUCCEEDED"
    assert out["result"]["openclaw_transfer"]["status"] == "FROZEN"
    assert out["result"]["openclaw_transfer"]["modification_permission"] == "NONE"


def test_openclaw_nl_unhealthy_and_runtime():
    from app.integrations.openclaw.commands import classify_nl

    u = classify_nl("Show me unhealthy agents")
    assert u["command"] == "agents.unhealthy"
    assert u["safety_lane"] == "GREEN"
    r = classify_nl("Show agent runtime status")
    assert r["command"] == "runtime.status"
    s = classify_nl("Swara status frozen?")
    # may extract swara as agent_id
    assert s["command"] in ("agent.status", "platform.status", "runtime.status")
