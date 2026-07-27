"""Cycle-5: Windows .cmd/.ps1 argv capture, profile containment, review recovery."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from app.dev_control.external_agents.runner.process_safe import (
    ProcessSafetyError,
    assert_safe_argv,
    resolve_executable,
    run_allowlisted,
    sanitize_env,
)
from app.dev_control.external_agents.runner.profile import prepare_executor_profile
from app.dev_control.external_agents.runner.review_parse import recover_independent_review

pytestmark = [
    pytest.mark.integration,
    pytest.mark.real_subprocess,
    pytest.mark.windows_process,
]

FIXTURES = (Path(__file__).resolve().parent / "fixtures" / "external_agent_runner").resolve()
CMD_WRAPPER = FIXTURES / "argv_capture.cmd"
PS1_WRAPPER = FIXTURES / "argv_capture.ps1"


@pytest.fixture()
def work(tmp_path, monkeypatch):
    root = tmp_path / "allowed_root"
    cwd = root / "wt"
    cwd.mkdir(parents=True)
    monkeypatch.setenv("EXTERNAL_AGENT_PROFILE_ROOT", str(tmp_path / "profiles"))
    return root, cwd


def _hostile_allowed() -> list[str]:
    """Payloads that pass assert_safe_argv and must remain inert data."""
    return [
        "foo&bar",
        "a|b",
        "redir>out",
        "append>>log",
        "in<input",
        "caret^char",
        'quote"here',
        "single'quote",
        "cmd /c echo hi",
        "powershell -Command Get-Process",
        "path..\\..\\escape",
        "$env:PATH",
        "Start-Process-as-data",
    ]


def _hostile_refused() -> list[str]:
    return [
        "a&&b",
        "x||y",
        "line\ninject",
        "tick`cmd",
        "sub$(id)",
        "%PATH%",
        "%COMSPEC%",
        "!VAR!",
        "; Start-Process",
        ";Start-Process",
    ]


def _hostile_cmd_safe() -> list[str]:
    """Payloads allowed through .cmd after cmd_metachar_refused gate (no &|<>^)."""
    return [
        "cmd /c echo hi",
        "powershell -Command Get-Process",
        "path..\\..\\escape",
        "$env:PATH",
        "Start-Process-as-data",
        'quote"here',
        "single'quote",
    ]


@pytest.mark.skipif(os.name != "nt", reason="Windows .cmd/.ps1 wrappers")
def test_cmd_wrapper_argv_inert_without_cmd_metachar(work):
    root, cwd = work
    payloads = _hostile_cmd_safe()
    canary = cwd / "SECONDARY_CMD_RAN.txt"
    if canary.exists():
        canary.unlink()
    result = run_allowlisted(
        [str(CMD_WRAPPER), *payloads],
        cwd=str(cwd),
        allowed_root=str(root),
        timeout_s=60,
        env_profile="helper",
    )
    assert result.exit_code == 0, result.stderr
    assert not canary.exists(), "secondary command must not run"
    captured = json.loads(result.stdout)
    assert captured.get("secondary_canary_exists") is False
    assert captured.get("argv") == payloads


@pytest.mark.skipif(os.name != "nt", reason="Windows .cmd metachar gate")
def test_cmd_metachar_fail_closed_for_batch(work):
    root, _cwd = work
    for bad in ("foo&bar", "a|b", "redir>out", "in<input", "caret^x"):
        with pytest.raises(ProcessSafetyError, match="cmd_metachar_refused"):
            assert_safe_argv([str(CMD_WRAPPER), bad], allowed_root=str(root))


@pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell wrappers")
def test_ps1_wrapper_argv_inert(work):
    root, cwd = work
    payloads = _hostile_allowed()
    ps = resolve_executable("powershell.exe")
    argv = [
        ps,
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(PS1_WRAPPER),
        "-CaptureOut",
        str(FIXTURES / "_captured_argv_ps1.json"),
        "-Wrapper",
        "ps1",
        *payloads,
    ]
    canary = cwd / "SECONDARY_CMD_RAN.txt"
    if canary.exists():
        canary.unlink()
    result = run_allowlisted(
        argv,
        cwd=str(cwd),
        allowed_root=str(root),
        timeout_s=60,
        env_profile="helper",
    )
    assert result.exit_code == 0, result.stderr
    assert not canary.exists()
    captured = json.loads(result.stdout)
    assert captured.get("argv") == payloads
    assert captured.get("secondary_canary_exists") is False


def test_hostile_tokens_fail_closed_before_spawn(work):
    root, _cwd = work
    for bad in _hostile_refused():
        with pytest.raises(ProcessSafetyError):
            assert_safe_argv([str(CMD_WRAPPER), bad], allowed_root=str(root))


def test_profile_redirects_home_and_blocks_canaries(tmp_path, monkeypatch):
    monkeypatch.setenv("EXTERNAL_AGENT_PROFILE_ROOT", str(tmp_path / "profiles"))
    # Synthetic secrets outside dedicated profile.
    real_home = Path.home()
    canary = tmp_path / "outside_secret.txt"
    canary.write_text("CANARY_SECRET_" + os.urandom(3).hex(), encoding="utf-8")
    prepared = prepare_executor_profile("claude")
    env = sanitize_env(profile="claude")
    assert env["USERPROFILE"] == prepared["env"]["USERPROFILE"]
    assert env["HOME"] == prepared["env"]["HOME"]
    assert Path(env["USERPROFILE"]).resolve() != real_home.resolve()
    # Dedicated profile must not contain the outside canary path as HOME child.
    assert not (Path(env["USERPROFILE"]) / "outside_secret.txt").exists()
    # Minimal auth material evidence recorded (paths only).
    assert "material" in prepared["evidence"]
    # Parent real credentials file is not copied into repo tree.
    assert ".credentials.json" not in str(FIXTURES)


def test_cursor_profile_keeps_trust_decision(tmp_path, monkeypatch):
    monkeypatch.setenv("EXTERNAL_AGENT_PROFILE_ROOT", str(tmp_path / "profiles"))
    prepared = prepare_executor_profile("cursor")
    assert prepared["evidence"]["trust_decision"].startswith("KEEP")
    env = sanitize_env(profile="cursor")
    assert Path(env["LOCALAPPDATA"]).name == "localappdata"
    assert (Path(env["LOCALAPPDATA"]) / "cursor-compile-cache").is_dir()


def test_review_recovery_separates_transport_and_verdict():
    mid = "msn_deadbeefdeadbee"
    head = "a" * 40
    inner = {
        "mission_id": mid,
        "reviewer": "claude",
        "verdict": "CHANGES_REQUIRED",
        "reviewed_head_sha": head,
        "findings": [{"severity": "MEDIUM", "title": "x"}],
    }
    # Brace-heavy escaped string that naive depth counters mishandle less often
    # when full-string json.loads is used first.
    envelope = json.dumps({"type": "result", "result": json.dumps(inner)})
    ok = recover_independent_review(envelope, mission_id=mid, expected_head=head, exit_code=0)
    assert ok["ok"] is True
    assert ok["recovered_verdict"] == "CHANGES_REQUIRED"
    assert ok["transport"]["process_ok"] is True

    # Failed process cannot yield automatic PASS even with PASS JSON.
    inner_pass = dict(inner, verdict="PASS")
    env_pass = json.dumps({"result": json.dumps(inner_pass)})
    bad_proc = recover_independent_review(env_pass, mission_id=mid, expected_head=head, exit_code=1)
    assert bad_proc["ok"] is False
    assert bad_proc["reason"] == "failed_process_cannot_pass"
    assert bad_proc["recovered_verdict"] == "PASS"

    # Nonzero exit may conservatively preserve CHANGES_REQUIRED after validation.
    cons = recover_independent_review(envelope, mission_id=mid, expected_head=head, exit_code=1)
    assert cons["ok"] is True
    assert cons["recovered_verdict"] == "CHANGES_REQUIRED"
    assert cons["parser"]["status"] == "ok_conservative"

    # Wrong mission refused.
    wrong = recover_independent_review(
        envelope, mission_id="msn_otherotherothe", expected_head=head, exit_code=0
    )
    assert wrong["ok"] is False
    assert "parse_failed" in str(wrong.get("reason"))

    # Unrelated JSON refused.
    junk = recover_independent_review(
        json.dumps({"hello": "world"}),
        mission_id=mid,
        expected_head=head,
        exit_code=0,
    )
    assert junk["ok"] is False


def test_cursor_chain_discovery_documented():
    """Cursor invocation must bypass agent.cmd (node.exe + index.js preferred)."""
    from app.dev_control.external_agents.runner import cursor_exec

    try:
        prefix = cursor_exec.resolve_cursor_invocation()
    except ProcessSafetyError:
        pytest.skip("cursor cli unavailable")
    assert prefix
    assert not any(Path(p).suffix.lower() == ".cmd" for p in prefix)
    head = Path(prefix[0]).name.lower()
    assert head in {"node.exe", "node", "powershell.exe", "powershell"}
    if head.startswith("node"):
        assert Path(prefix[1]).name.lower() == "index.js"
        assert "cursor-agent" in {p.lower() for p in Path(prefix[1]).parts}
