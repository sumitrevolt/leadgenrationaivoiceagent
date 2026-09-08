"""OpenClaw Automation-Max GREEN commands — observe only."""

from __future__ import annotations

import json
from pathlib import Path

from app.integrations.openclaw import automation_commands as ac
from app.integrations.openclaw import commands as oc_cmd
from app.integrations.openclaw import policies


def test_automation_commands_are_green():
    assert "automation.status" in policies.GREEN_COMMANDS
    assert "automation.agents" in policies.GREEN_COMMANDS
    assert policies.safety_lane_for("automation.status") == "GREEN"
    assert "automation.status" in oc_cmd.HANDLERS
    assert "automation.agents" in oc_cmd.HANDLERS


def test_automation_status_handler(monkeypatch, tmp_path):
    monkeypatch.setenv("CADENCE_ENGINE", "1")
    monkeypatch.setenv("OPS_WATCHDOG", "1")
    monkeypatch.setenv("JOURNEY_ENGINE", "1")
    monkeypatch.setenv("PLATFORM_DIAL_DAILY", "0")
    monkeypatch.setenv("WHATSAPP_AUTO_SEND", "0")
    monkeypatch.setenv("AUTO_EMAIL_OUTREACH", "0")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "job_heartbeats.json").write_text("{}", encoding="utf-8")

    def _fake_stats():
        return {"engine_on": True, "active": 10, "done": 2, "enrolled": 12}

    monkeypatch.setattr("app.marketing.cadence.stats", _fake_stats)
    monkeypatch.setattr(
        "app.platform.approval_notifier.approval_client_allowlist",
        lambda: {"jiya-makeover"},
    )

    out = ac._automation_status({}, actor="t", correlation_id="c1")
    assert out["status"] == "SUCCEEDED"
    assert out["result"]["flags"]["CADENCE_ENGINE"] is True
    assert out["result"]["flags"]["PLATFORM_DIAL_DAILY"] is False
    assert "jiya-makeover" in out["result"]["approval_email_allowlist"]
    assert any(a["id"] == "anika" for a in out["result"]["automation_agents"])


def test_automation_agent_package_anika(monkeypatch):
    monkeypatch.setenv("CADENCE_ENGINE", "1")

    def _fake_stats():
        return {"engine_on": True, "active": 5, "done": 1, "enrolled": 6}

    monkeypatch.setattr("app.marketing.cadence.stats", _fake_stats)
    pkg = ac.automation_agent_package("anika")
    assert pkg is not None
    assert pkg["status"] == "AUTOMATION_OBSERVE"
    assert pkg["cadence"]["active"] == 5
    assert pkg["mutation_via_openclaw"] is False


def test_agent_status_includes_automation_package(monkeypatch):
    monkeypatch.setenv("OPS_WATCHDOG", "1")

    class _Reg:
        @staticmethod
        def agent_registry():
            return {
                "agents": [
                    {
                        "id": "kavya",
                        "name": "Kavya",
                        "status": "active",
                        "paused": False,
                        "product": "ops",
                    }
                ]
            }

    monkeypatch.setattr("app.platform.owner_os.agent_registry", _Reg.agent_registry)
    monkeypatch.setattr(
        "app.platform.owner_agent_execution.control_view",
        lambda _aid: {"agent_id": "kavya", "effective_scope": {"scheduled_pause": False}},
    )
    out = oc_cmd._agent_status({"agent_id": "kavya"}, actor="t", correlation_id="c2")
    assert out["status"] == "SUCCEEDED"
    assert "openclaw_automation" in (out.get("result") or {})
    assert out["result"]["openclaw_automation"]["role"] == "Ops / Watchdog"


def test_classify_nl_automation_status():
    prop = oc_cmd.classify_nl("automation status dikhao — kaun sa engine on")
    assert prop["command"] == "automation.status"
    assert prop["safety_lane"] == "GREEN"


def test_automation_agents_unknown():
    out = ac._automation_agents({"agent_id": "swara"}, actor="t", correlation_id="c3")
    assert out["status"] == "FAILED"
    assert "anika" in out["result"]["known"]
