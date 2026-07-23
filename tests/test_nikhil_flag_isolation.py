"""Nikhil isolated flag + ungated-dispatchable ban + canary preflight."""

from __future__ import annotations

import pytest

from app.platform import agent_canary_preflight as pf
from app.platform import agent_registry as ar
from app.platform import agent_runtime as rt
from app.platform.agent_runtime_workforce import ACTION_DELIVERY_SCAN, ensure_workforce_registered
from app.platform.team import STAFF


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    monkeypatch.setattr(rt, "_STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setattr(rt, "_USAGE_PATH", str(tmp_path / "usage.json"))
    monkeypatch.setattr(rt, "_DLQ_PATH", str(tmp_path / "dlq.jsonl"))
    monkeypatch.setattr(rt, "_BACKOFF_BASE_S", 0.0)
    monkeypatch.setattr(rt, "_kill_engaged", lambda key: False)
    monkeypatch.setattr(rt, "_owner_admission_blocked", lambda aid: (False, ""))
    monkeypatch.setenv("AGENT_RUNTIME_CANCEL_BACKEND", "memory")
    monkeypatch.setenv("AGENT_RUNTIME_IDEM_BACKEND", "memory")
    from app.platform import agent_runtime_cancellation as crc
    from app.platform import agent_runtime_idempotency as arid

    crc.reset_memory_for_tests()
    arid.reset_memory_for_tests()
    rt._ACTIVE.clear()
    ensure_workforce_registered()
    monkeypatch.setenv("AGENT_RUNTIME", "1")
    # Peer pilot flags OFF for isolation tests
    for fl in (
        "OPS_HEALTH_AGENT",
        "AFTERNOON_CONTENT",
        "SOCIAL_ENGINE",
        "INFRA_HANDLER",
        "SRE_AGENT",
        "FINOPS_AGENT",
        "SECURITY_POSTURE_AGENT",
        "DBRE_AGENT",
        "DATA_INTEGRITY_AGENT",
        "DEPS_AGENT",
        "MCP_ENGINEER",
        "DELIVERY_ASSURANCE_AGENT",
    ):
        monkeypatch.setenv(fl, "0")
    yield
    crc.reset_memory_for_tests()
    arid.reset_memory_for_tests()
    rt._ACTIVE.clear()


def test_nikhil_has_isolated_flag_and_green_lane():
    c = ar.get_contract("nikhil")
    assert c.primary_flag == "DELIVERY_ASSURANCE_AGENT"
    assert c.lane == "GREEN"
    assert c.default_mode == "live"
    assert c.customer_contact_cap_day == 0
    assert ar.validate_registry() == []


def test_all_pilots_have_nonempty_flags():
    for aid in sorted(rt.PILOT_AGENTS):
        flag = (ar.get_contract(aid).primary_flag or "").strip()
        assert flag, f"{aid} ungated"


def test_validate_registry_rejects_ungated_pilot(monkeypatch):
    # Force a temporary empty flag on nikhil in built registry via monkeypatch of _GOVERNANCE
    original = ar._GOVERNANCE["nikhil"]
    monkeypatch.setitem(
        ar._GOVERNANCE,
        "nikhil",
        {**original, "primary_flag": ""},
    )
    problems = ar.validate_registry()
    assert any("nikhil" in p and "primary_flag" in p for p in problems)


async def test_nikhil_flag_off_blocks_no_engine(monkeypatch):
    ran = {"n": 0}

    def boom(*a, **k):
        ran["n"] += 1
        return {"status": "success"}

    monkeypatch.setenv("DELIVERY_ASSURANCE_AGENT", "0")
    monkeypatch.setattr("app.marketing.delivery_assurance.scan_missed_deliverables", boom)
    res = await rt.submit(
        "nikhil",
        ACTION_DELIVERY_SCAN,
        idempotency_key="nikhil-flag-off-1",
    )
    assert res.status == "skipped"
    assert res.reason == "flag_disabled:DELIVERY_ASSURANCE_AGENT"
    assert ran["n"] == 0
    assert "leased" not in res.lifecycle
    # blocked skip must not burn idem as success — second attempt still skipped same way
    res2 = await rt.submit(
        "nikhil",
        ACTION_DELIVERY_SCAN,
        idempotency_key="nikhil-flag-off-1",
    )
    assert res2.status == "skipped"
    assert ran["n"] == 0


async def test_nikhil_flag_on_runs_engine(monkeypatch):
    monkeypatch.setenv("DELIVERY_ASSURANCE_AGENT", "1")

    def fake(limit=100, include_healthy=False):
        return {
            "status": "success",
            "checked": 1,
            "missed_count": 0,
            "at_risk_count": 0,
            "items": [],
            "read_only": True,
        }

    monkeypatch.setattr("app.marketing.delivery_assurance.scan_missed_deliverables", fake)
    res = await rt.submit("nikhil", ACTION_DELIVERY_SCAN)
    assert res.status == "succeeded"
    assert res.output["read_only"] is True
    assert res.lane == "GREEN"
    assert "leased" in res.lifecycle and "running" in res.lifecycle


async def test_agent_flag_missing_blocks_if_empty(monkeypatch):
    # Simulate policy seeing empty flag on a pilot without re-running full validate
    c = ar.get_contract("nikhil")

    class _C:
        pass

    fake = _C()
    for k in c.__dataclass_fields__:
        setattr(fake, k, getattr(c, k))
    fake.primary_flag = ""
    monkeypatch.setattr(
        ar, "get_contract", lambda aid: fake if aid == "nikhil" else ar.build_registry().get(aid)
    )
    res = await rt.submit("nikhil", ACTION_DELIVERY_SCAN)
    assert res.status == "blocked"
    assert res.reason == "agent_flag_missing"
    assert res.decision and res.decision["reason_code"] == "agent_flag_missing"


def test_census_31_and_boss_once():
    census = pf.agent_flag_census(assume_runtime_on=False)
    assert census["canonical_count"] == 31
    assert len(STAFF) == 31
    assert census["boss_count"] == 1
    assert census["ungated_dispatchable_count"] == 0
    labels = {r["label"] for r in census["agents"]}
    assert any("Nikhil" in x and "Revenue" in x for x in labels)
    assert any("Pranav" in x and "SRE" in x for x in labels)


def test_isolation_ok_when_only_nikhil_flag_on(monkeypatch):
    monkeypatch.setenv("DELIVERY_ASSURANCE_AGENT", "1")
    out = pf.canary_isolation_preflight("nikhil", assume_runtime_on=True)
    assert out["allowed"] is True
    assert out["eligible_agents"] == ["nikhil"]
    assert out["unexpected_agents"] == []


def test_isolation_fails_when_peer_flag_on(monkeypatch):
    monkeypatch.setenv("DELIVERY_ASSURANCE_AGENT", "1")
    monkeypatch.setenv("OPS_HEALTH_AGENT", "1")  # kavya
    out = pf.canary_isolation_preflight("nikhil", assume_runtime_on=True)
    assert out["allowed"] is False
    assert out["reason_code"] == "canary_agent_isolation_failed"
    assert "kavya" in out["unexpected_agents"]
    assert "nikhil" in out["eligible_agents"]


async def test_peer_pilot_stays_off_while_nikhil_on(monkeypatch):
    monkeypatch.setenv("DELIVERY_ASSURANCE_AGENT", "1")
    monkeypatch.setenv("SRE_AGENT", "0")
    monkeypatch.setattr(
        "app.marketing.delivery_assurance.scan_missed_deliverables",
        lambda *a, **k: {
            "status": "success",
            "checked": 0,
            "missed_count": 0,
            "at_risk_count": 0,
            "items": [],
        },
    )
    ok = await rt.submit("nikhil", ACTION_DELIVERY_SCAN)
    assert ok.status == "succeeded"
    pranav = await rt.submit("pranav", "run_owned_workflow")
    assert pranav.status == "skipped"
    assert "SRE_AGENT" in pranav.reason


async def test_nikhil_inherits_pause(monkeypatch):
    monkeypatch.setenv("DELIVERY_ASSURANCE_AGENT", "1")
    monkeypatch.setattr(rt, "_owner_admission_blocked", lambda aid: (True, "agent_paused"))
    res = await rt.submit("nikhil", ACTION_DELIVERY_SCAN)
    assert res.status == "blocked" and res.reason == "agent_paused"


async def test_swara_still_red():
    res = await rt.submit("swara", "frozen_transfer_status")
    assert res.status == "blocked"
    assert "red_lane" in res.reason


async def test_unknown_nikhil_capability_fails_closed(monkeypatch):
    monkeypatch.setenv("DELIVERY_ASSURANCE_AGENT", "1")
    res = await rt.submit("nikhil", "remediate_delivery")
    assert res.status == "blocked"
    assert res.reason.startswith("capability_not_registered")
