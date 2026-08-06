"""ADR-161: every canonical STAFF agent has an honest enterprise profile."""

from __future__ import annotations

from app.platform import agent_maturity as maturity
from app.platform import agent_runtime as runtime
from app.platform.agent_runtime_workforce import ensure_workforce_registered
from app.platform.team import STAFF


def test_all_31_profiles_are_complete_and_unique():
    ensure_workforce_registered()
    out = maturity.portfolio()

    assert out["ok"] is True, out["problems"]
    assert out["staff_count"] == out["enterprise_profiles_ready"] == 31
    assert len(out["agents"]) == len(STAFF) == 31
    assert maturity.validate_profiles() == []

    memory = {row["memory"]["namespace"] for row in out["agents"]}
    private_kb = {row["knowledge"]["private"] for row in out["agents"]}
    role_kb = {row["knowledge"]["role"] for row in out["agents"]}
    assert len(memory) == len(private_kb) == len(role_kb) == 31


def test_every_profile_has_saas_baseline_role_skills_and_runtime_capability():
    ensure_workforce_registered()
    for agent_id in STAFF:
        row = maturity.profile(agent_id, "tenant-a")
        assert row["setup_state"] == "enterprise_profile_ready", agent_id
        assert len(row["skills"]["enterprise_baseline"]) >= 8, agent_id
        assert len(row["skills"]["role_specific"]) >= 3, agent_id
        assert row["skills"]["runtime_capabilities"] == runtime.capabilities_for(agent_id)
        assert row["governance"]["tenant_isolation"] is True
        assert "owner_all_agents" in row["governance"]["kill_switches"]
        assert row["coordination"]["ready"] is True
        assert row["coordination"]["boss"] == "manager"


def test_tenant_namespaces_are_isolated_and_opaque():
    a = maturity.profile("isha", "client-a@example.com")
    b = maturity.profile("isha", "client-b@example.com")
    other_agent = maturity.profile("rohan", "client-a@example.com")

    assert a["memory"]["namespace"] != b["memory"]["namespace"]
    assert a["knowledge"]["private"] != b["knowledge"]["private"]
    assert a["knowledge"]["private"] != other_agent["knowledge"]["private"]
    assert "client-a@example.com" not in a["memory"]["namespace"]
    assert "client-a@example.com" not in a["knowledge"]["private"]


def test_profile_ready_never_claims_all_agents_live():
    ensure_workforce_registered()
    out = maturity.portfolio()
    assert out["enterprise_profiles_ready"] == 31
    assert out["rollout_counts"].get("canary_ready", 0) < 31
    assert "not rollout-live" in out["claim_note"]


def test_context_is_inert_without_explicit_canary(monkeypatch):
    monkeypatch.delenv("AGENT_MATURITY_CONTEXT", raising=False)
    assert maturity.context_enabled() is False
