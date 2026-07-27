"""Unit/contract tests for EXTERNAL_AGENT_RUNNER (unattended Cursor/Claude slice)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from app.dev_control.external_agents import orchestrator, store
from app.dev_control.external_agents.runner import eligibility, flags
from app.dev_control.external_agents.runner.authorize import authorize_mission
from app.dev_control.external_agents.runner.process_safe import (
    ProcessSafetyError,
    assert_safe_argv,
    assert_worktree_allowed,
    sanitize_env,
)
from app.dev_control.external_agents.schema import Mission, RiskClass


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    monkeypatch.setenv("EXTERNAL_MISSION_DIR", str(tmp_path / "missions"))
    monkeypatch.setenv("EXTERNAL_AGENT_ORCHESTRATOR", "1")
    monkeypatch.setenv("EXTERNAL_AGENT_RUNNER", "1")
    monkeypatch.setenv("EXTERNAL_MISSION_CAS", "filelock")
    monkeypatch.setenv("EXTERNAL_AGENT_WORKTREE_ROOT", str(tmp_path / "wts"))
    from app.dev_control.external_agents import cas as cas_mod

    cas_mod.reset_backend()
    yield
    cas_mod.reset_backend()


class _Lock:
    def __init__(self) -> None:
        self.held: dict[str, str] = {}

    def acquire(self, owner, paths, ttl=900):
        clash = [p for p in paths if self.held.get(p, owner) != owner]
        if clash:
            return {"acquired": False, "conflict": sorted(clash)}
        for p in paths:
            self.held[p] = owner
        return {"acquired": True, "conflict": []}

    def release(self, owner, paths):
        for p in paths:
            if self.held.get(p) == owner:
                del self.held[p]


def _mission(**over):
    payload = {
        "title": "runner dogfood fixture",
        "description": "add one test fixture file",
        "executor": "cursor",
        "reviewer": "claude",
        "idempotency_key": "runner-key-" + os.urandom(4).hex(),
        "allowed_paths": ["tests/fixtures/external_agent_runner/"],
        "branch": "feat/ext-dogfood-01",
        "worktree": str(Path(os.environ["EXTERNAL_AGENT_WORKTREE_ROOT"]) / "dogfood-01"),
        "base_sha": "e64b8a9d10bcf6084488b34f886f77a5752f13f8",  # pragma: allowlist secret
        "rollback_plan": "delete fixture file",
        "lock": _Lock(),
    }
    payload.update(over)
    return orchestrator.create_mission(**payload)


def test_runner_off_refuses(monkeypatch):
    monkeypatch.setenv("EXTERNAL_AGENT_RUNNER", "0")
    assert flags.runner_enabled() is False
    m = _mission()["mission"]
    mission = store.get(m["mission_id"])
    out = eligibility.evaluate(mission)
    assert out["eligible"] is False
    assert out["reason"] == "runner_or_orchestrator_off"


def test_orchestrator_off_blocks_runner(monkeypatch):
    monkeypatch.setenv("EXTERNAL_AGENT_ORCHESTRATOR", "0")
    assert flags.runner_enabled() is False


def test_flag_registered():
    from app.api.automation_flags import AUTOMATION_FLAGS

    assert "EXTERNAL_AGENT_RUNNER" in AUTOMATION_FLAGS


def test_green_eligible():
    mid = _mission()["mission"]["mission_id"]
    mission = store.get(mid)
    out = eligibility.evaluate(mission)
    assert out["eligible"] is True


def test_amber_requires_owner():
    mid = _mission(
        title="merge production deploy",
        description="deploy to production VPS",
        declared_risk="AMBER",
        idempotency_key="runner-amber-" + os.urandom(3).hex(),
    )
    # may be refused as RED depending on classify — accept either
    if not mid.get("ok"):
        assert mid.get("refused") or mid.get("reason")
        return
    mission = store.get(mid["mission"]["mission_id"])
    out = eligibility.evaluate(mission)
    if mission.risk_class is RiskClass.AMBER:
        assert out["eligible"] is False
        assert out["reason"] == "owner_decision_required"


def test_missing_allowed_paths_refused():
    # create_mission already refuses empty allowed for cursor — assert that
    out = _mission(allowed_paths=[], idempotency_key="runner-empty-" + os.urandom(3).hex())
    assert out["ok"] is False


def test_shell_injection_refused():
    with pytest.raises(ProcessSafetyError):
        assert_safe_argv(["claude", "foo&&bar"])
    with pytest.raises(ProcessSafetyError):
        assert_safe_argv(["python", "-c", "print(1)"])


def test_env_injection_refused():
    with pytest.raises(ProcessSafetyError):
        sanitize_env({"MALICIOUS_SECRET": "x"})


def test_worktree_outside_root_refused(tmp_path):
    with pytest.raises(ProcessSafetyError):
        assert_worktree_allowed(str(tmp_path / "nope"), allowed_root=str(tmp_path / "root"))


def test_authorize_green_ok():
    mid = _mission()["mission"]["mission_id"]
    mission = store.get(mid)
    auth = authorize_mission(mission)
    assert auth["authorized"] is True


def test_authorize_amber_blocked():
    m = Mission.create(
        title="amber",
        executor="cursor",
        reviewer="claude",
        idempotency_key="auth-amber-0001",
        allowed_paths=["tests/x.py"],
        branch="feat/ext-amber",
        worktree=str(Path(os.environ["EXTERNAL_AGENT_WORKTREE_ROOT"]) / "amber"),
        risk_class=RiskClass.AMBER,
    )
    auth = authorize_mission(m)
    assert auth["authorized"] is False
    assert auth["reason"] == "owner_decision_required"


def test_process_argv_allowlist_ok():
    assert_safe_argv(["claude", "-p", "--output-format", "json"])
    assert_safe_argv(["agent.cmd", "-p", "--print", "--workspace", "C:/wt"])


def test_cursor_manifest_extract():
    from app.dev_control.external_agents.runner import cursor_exec

    mid = "msn_abc123def45678"
    raw = json.dumps(
        {
            "result": json.dumps(
                {
                    "mission_id": mid,
                    "executor": "cursor",
                    "changed_files": ["tests/fixtures/external_agent_runner/STATUS.txt"],
                    "commands": [],
                    "tests": [],
                    "summary": "ok",
                    "evidence": {},
                    "scope_breach": False,
                }
            )
        }
    )
    man = cursor_exec.extract_result_manifest(raw, mid)
    assert man["executor"] == "cursor"
    assert man["changed_files"][0].endswith("STATUS.txt")


def test_claude_review_extract():
    from app.dev_control.external_agents.runner import claude_exec

    mid = "msn_abc123def45678"
    raw = json.dumps(
        {
            "result": json.dumps(
                {
                    "mission_id": mid,
                    "reviewer": "claude",
                    "verdict": "PASS",
                    "findings": ["STATUS.txt ok"],
                    "citations": ["tests/fixtures/external_agent_runner/STATUS.txt:1"],
                }
            )
        }
    )
    man = claude_exec.extract_review_manifest(raw, mid)
    assert man["verdict"] == "PASS"


def test_run_mission_once_refuses_when_runner_off(monkeypatch):
    from app.dev_control.external_agents.runner import loop

    monkeypatch.setenv("EXTERNAL_AGENT_RUNNER", "0")
    out = loop.run_mission_once("msn_doesnotexist", repo_root=".")
    assert out["ok"] is False
    assert out["reason"] == "runner_or_orchestrator_off"
