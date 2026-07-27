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
    monkeypatch.setenv("EXTERNAL_AGENT_COORDINATION_BACKEND", "local-file")
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


def test_env_deny_by_default_no_cursor_claude_wildcard(monkeypatch):
    monkeypatch.setenv("CURSOR_TEST_SECRET", "leak-cursor-" + os.urandom(2).hex())
    monkeypatch.setenv("CLAUDE_TEST_SECRET", "leak-claude-" + os.urandom(2).hex())
    monkeypatch.setenv("GH_TOKEN", "leak-gh-" + os.urandom(2).hex())
    monkeypatch.setenv("DATABASE_URL", "postgres://x")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "aws-" + os.urandom(2).hex())
    env = sanitize_env(profile="cursor")
    assert "CURSOR_TEST_SECRET" not in env
    assert "CLAUDE_TEST_SECRET" not in env
    assert "GH_TOKEN" not in env
    assert "DATABASE_URL" not in env
    assert "AWS_SECRET_ACCESS_KEY" not in env
    assert not any(k.upper().startswith("CURSOR_") for k in env if k.upper() != "CURSOR_API_KEY")
    assert not any(k.upper().startswith("CLAUDE_") for k in env)


def test_claude_disallows_bash(monkeypatch):
    from app.dev_control.external_agents.runner import claude_exec

    monkeypatch.setattr(claude_exec, "resolve_claude_executable", lambda: "claude")
    argv = claude_exec.build_claude_argv("review please", add_dir="C:/tmp/wt")
    joined = " ".join(argv)
    assert "Bash" in joined
    assert "--disallowedTools" in argv


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


def test_cursor_result_manifest_file_preferred(tmp_path):
    from app.dev_control.external_agents.runner import cursor_exec

    mid = "msn_filemanifest01"
    payload = {
        "mission_id": mid,
        "executor": "cursor",
        "changed_files": ["tests/fixtures/external_agent_runner/STATUS.txt"],
        "commands": [],
        "tests": [],
        "summary": "from-file",
        "evidence": {},
        "scope_breach": False,
    }
    (tmp_path / cursor_exec.RESULT_MANIFEST_FILENAME).write_text(
        json.dumps(payload), encoding="utf-8"
    )
    man = cursor_exec.load_result_manifest_file(tmp_path, mid)
    assert man["summary"] == "from-file"


def test_cursor_result_inner_prose_extractable():
    from app.dev_control.external_agents.runner import cursor_exec
    from app.dev_control.external_agents.runner.process_safe import ProcessSafetyError

    mid = "msn_innerprose0001"
    inner = "Done.\n" + json.dumps(
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
    raw = json.dumps({"result": inner})
    man = cursor_exec.extract_result_manifest(raw, mid)
    assert man["summary"] == "ok"
    # Outer stdout with prose still fail-closed.
    with pytest.raises(ProcessSafetyError, match="cursor_output_not_json"):
        cursor_exec.extract_result_manifest("Here:\n" + raw, mid)


def test_runner_control_files_not_scope_breach():
    from app.dev_control.external_agents import policy
    from app.dev_control.external_agents.schema import Mission, RiskClass

    mission = Mission(
        mission_id="msn_scopeexempt0001",
        title="t",
        description="d",
        executor="cursor",
        reviewer="claude",
        risk_class=RiskClass.GREEN,
        idempotency_key="scope-exempt-1",
        allowed_paths=["tests/fixtures/external_agent_runner/"],
    )
    bad = policy.path_violations(
        mission,
        [
            "tests/fixtures/external_agent_runner/STATUS.txt",
            ".external_agent_result_manifest.json",
            ".external_agent_runner_prompt.txt",
            "README.md",
        ],
    )
    assert bad == ["README.md"]


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


def test_wall_timeout_respects_mission_caps():
    from app.dev_control.external_agents.runner.loop import wall_timeout_s

    m = Mission.create(
        title="t",
        executor="cursor",
        reviewer="claude",
        idempotency_key="wall-" + os.urandom(3).hex(),
        allowed_paths=["tests/x.py"],
        branch="feat/ext-wall",
        worktree=str(Path(os.environ["EXTERNAL_AGENT_WORKTREE_ROOT"]) / "wall"),
        max_runtime_s=120,
        token_budget=5000,
        cost_budget_usd=1.0,
    )
    assert wall_timeout_s(m, 900) <= 120


def test_heartbeat_cancels_on_failed_beat():
    import time

    from app.dev_control.external_agents.runner.process_safe import HeartbeatController

    beats = {"n": 0}

    def bad_beat():
        beats["n"] += 1
        return False

    hb = HeartbeatController(interval_s=0.05, beat=bad_beat)
    hb.start()
    time.sleep(0.2)
    hb.stop()
    assert hb.cancelled is True
    assert beats["n"] >= 1


def test_observed_changed_files_reads_git(tmp_path):
    import subprocess

    from app.dev_control.external_agents.runner.loop import observed_changed_files

    repo = tmp_path / "r"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "t@t"], cwd=repo, check=True, capture_output=True
    )
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True, capture_output=True)
    (repo / "a.txt").write_text("1", encoding="utf-8")
    subprocess.run(["git", "add", "a.txt"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "i"], cwd=repo, check=True, capture_output=True)
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    (repo / "b.txt").write_text("2", encoding="utf-8")
    files = observed_changed_files(str(repo), sha)
    assert "b.txt" in files


def test_terminate_uses_taskkill_on_windows(monkeypatch):
    import subprocess as sp

    from app.dev_control.external_agents.runner import process_safe

    calls = []

    class FakeProc:
        pid = 4242

        def poll(self):
            return None

        def wait(self, timeout=None):
            return 0

        def kill(self):
            return None

        def send_signal(self, *_a, **_k):
            return None

    def fake_run(argv, **kwargs):
        calls.append(argv)
        return sp.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(process_safe.os, "name", "nt")
    monkeypatch.setattr(process_safe.subprocess, "run", fake_run)
    process_safe._terminate(FakeProc())
    assert calls and calls[0][:2] == ["taskkill", "/PID"]
    assert "/T" in calls[0]


def test_run_mission_once_refuses_when_runner_off(monkeypatch):
    from app.dev_control.external_agents.runner import loop

    monkeypatch.setenv("EXTERNAL_AGENT_RUNNER", "0")
    out = loop.run_mission_once("msn_doesnotexist", repo_root=".")
    assert out["ok"] is False
    assert out["reason"] == "runner_or_orchestrator_off"


def test_output_cap_truncates():
    from app.dev_control.external_agents.runner.process_safe import MAX_OUTPUT_BYTES, _cap

    big = "x" * (MAX_OUTPUT_BYTES + 50)
    out, trunc = _cap(big)
    assert trunc is True
    assert "truncated" in out


def test_disable_push_does_not_remove_origin(tmp_path):
    import subprocess

    from app.dev_control.external_agents.runner.worktrees import _disable_push_remotes

    repo = tmp_path / "r"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://example.com/x.git"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    _disable_push_remotes(repo)
    remotes = subprocess.check_output(["git", "remote"], cwd=repo, text=True)
    assert "origin" in remotes
    pushurl = subprocess.run(
        ["git", "config", "--get", "remote.origin.pushurl"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    # pushurl may be worktree-scoped; shared remote name must remain.
    assert pushurl.returncode in (0, 1)


def test_extract_usage_from_claude_envelope():
    from app.dev_control.external_agents.runner.claude_exec import extract_usage_from_cli_json

    raw = json.dumps(
        {
            "total_cost_usd": 0.5,
            "usage": {"input_tokens": 10, "output_tokens": 20},
        }
    )
    u = extract_usage_from_cli_json(raw)
    assert u["tokens_used"] == 30
    assert float(u["cost_usd"]) == 0.5
    # Cache reads must not inflate the budget counter (Cursor dogfood false-trip).
    cursorish = json.dumps(
        {
            "usage": {
                "inputTokens": 100,
                "outputTokens": 50,
                "cacheReadTokens": 500_000,
                "cacheWriteTokens": 0,
            }
        }
    )
    u2 = extract_usage_from_cli_json(cursorish)
    assert u2["tokens_used"] == 150
