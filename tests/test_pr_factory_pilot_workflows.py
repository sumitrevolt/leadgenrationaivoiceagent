"""Pilot registry + workflow contract: additive only, nothing weakened."""

from __future__ import annotations

from pathlib import Path

import yaml

from app.platform.automation_flag_manifest import FlagGovernance, describe_flag

ROOT = Path(__file__).resolve().parents[1]
CI_REPAIR = ROOT / ".github" / "workflows" / "pr-factory-ci-repair.yml"


def test_pilot_flag_registered_in_manifest_default_off():
    meta = describe_flag("PR_FACTORY_PILOT_ENABLED")
    assert meta.governance == FlagGovernance.CANARY_ONLY
    assert meta.default_hint == "0"
    assert meta.risk_lane == "dev_control"
    assert meta.customer_side_effect is False
    assert meta.provider_side_effect is False


def test_pilot_flag_registered_in_automation_flags_registry():
    from app.api.automation_flags import AUTOMATION_FLAGS

    assert "PR_FACTORY_PILOT_ENABLED" in AUTOMATION_FLAGS


def test_existing_ci_repair_workflow_still_read_only():
    """Regression guard: the pilot must NOT have weakened the Wave-1 workflow."""
    data = yaml.safe_load(CI_REPAIR.read_text(encoding="utf-8"))
    perms = data["permissions"]
    assert perms.get("contents") == "read"
    assert perms.get("actions") == "read"
    assert perms.get("pull-requests") == "write"
    assert "write" not in str(perms.get("contents"))
    on_block = data.get("on", data.get(True))
    assert "workflow_dispatch" in on_block
    assert "issue_comment" not in on_block
    assert "pull_request" not in on_block


def test_no_new_write_capable_pilot_action_workflow():
    """The pilot is a local CLI, not a GitHub Action with contents:write."""
    text = CI_REPAIR.read_text(encoding="utf-8")
    assert "anthropics/claude-code-action@" not in text
    assert "contents: write" not in text


def test_pilot_enabled_triple_gate_defaults_off(monkeypatch):
    from tools.pr_factory.pilot import describe_state, pilot_enabled

    monkeypatch.delenv("PR_FACTORY_PILOT_ENABLED", raising=False)
    monkeypatch.delenv("PR_FACTORY_ENABLED", raising=False)
    monkeypatch.delenv("EXTERNAL_AGENT_ORCHESTRATOR", raising=False)
    state = describe_state()
    assert state["pilot_enabled"] is False
    assert pilot_enabled() is False
    assert state["max_repair_attempts"] == 2


def test_pilot_enabled_requires_all_three_flags(monkeypatch):
    from tools.pr_factory.pilot import pilot_enabled

    monkeypatch.setenv("PR_FACTORY_PILOT_ENABLED", "1")
    monkeypatch.setenv("PR_FACTORY_ENABLED", "1")
    monkeypatch.setenv("EXTERNAL_AGENT_ORCHESTRATOR", "1")
    assert pilot_enabled() is True

    monkeypatch.setenv("EXTERNAL_AGENT_ORCHESTRATOR", "0")
    assert pilot_enabled() is False
