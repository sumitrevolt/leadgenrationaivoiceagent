"""Kavach (OpenClaw harness controller) — safety & wiring tests.

Runs in the repo venv (imports app.integrations.openclaw + app.agents.harness).
Proves: Kavach is non-dispatchable / non-STAFF, harness commands classify into
the right safety lanes, the OpenClaw gate stays fail-closed, and RED stays RED.
"""

import importlib

import pytest


# ---- identity --------------------------------------------------------
def test_kavach_is_not_dispatchable_or_staff():
    from app.integrations.openclaw.agents.harness_agent import (
        KAVACH_AGENT,
        is_dispatchable,
        is_enabled,
    )

    assert KAVACH_AGENT["id"] == "openclaw_harness"
    assert KAVACH_AGENT["display_name"] == "Kavach"
    assert KAVACH_AGENT["dispatchable"] is False
    assert KAVACH_AGENT["staff_member"] is False
    assert KAVACH_AGENT["counts_toward_staff"] is False
    assert KAVACH_AGENT["second_dispatcher"] is False
    assert is_dispatchable() is False
    assert is_enabled() is False  # INERT by default


# ---- NL classification ----------------------------------------------
@pytest.mark.parametrize(
    "text,expected,lane",
    [
        ("harness status batao", "harness.status", "GREEN"),
        ("show conformance", "harness.conformance", "GREEN"),
        ("explain run_id=abc123def", "harness.explain", "GREEN"),
        ("enable shadow for agent nikhil", "harness.shadow.enable", "AMBER"),
        ("enable canary agent nikhil", "harness.canary.enable", "AMBER"),
        ("harness kill", "harness.kill", "AMBER"),
        ("pause agent nikhil", "harness.pause", "AMBER"),
        ("random gibberish", "harness.status", "GREEN"),  # ambiguous -> safe read
    ],
)
def test_classify_harness_nl(text, expected, lane):
    from app.integrations.openclaw.agents.harness_agent import classify_harness_nl

    plan = classify_harness_nl(text)
    assert plan["command"] == expected
    assert plan["safety_lane"] == lane
    assert plan["agent"] == "openclaw_harness"


# ---- policy wiring + fail-closed ------------------------------------
def test_harness_commands_registered_in_lanes():
    from app.integrations.openclaw import policies

    importlib.reload(policies)
    assert "harness.status" in policies.GREEN_COMMANDS
    assert "harness.conformance" in policies.GREEN_COMMANDS
    assert "harness.kill" in policies.AMBER_COMMANDS
    assert policies.safety_lane_for("harness.status") == "GREEN"
    assert policies.safety_lane_for("harness.kill") == "AMBER"
    # unknown harness verb -> RED (fail-safe classification)
    assert policies.safety_lane_for("harness.nuke_everything") == "RED"


def test_gate_fail_closed_when_openclaw_disabled(monkeypatch):
    from app.integrations.openclaw import policies

    monkeypatch.delenv("OPENCLAW_ENABLED", raising=False)
    ok, reason = policies.command_permitted("harness.status")
    assert ok is False and "OPENCLAW_ENABLED" in reason


def test_red_still_refused_through_kavach_path():
    from app.integrations.openclaw import policies

    assert policies.safety_lane_for("shell.execute") == "RED"
    assert policies.safety_lane_for("sql.execute") == "RED"
    ok, reason = policies.command_permitted("shell.execute")
    assert ok is False


def test_harness_handlers_present_in_registry():
    from app.integrations.openclaw import commands

    importlib.reload(commands)
    assert "harness.status" in commands.HANDLERS
    assert "harness.explain" in commands.HANDLERS
    assert callable(commands.HANDLERS["harness.status"])
