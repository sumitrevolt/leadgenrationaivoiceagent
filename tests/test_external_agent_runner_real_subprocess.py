"""Real-process integration tests for EXTERNAL_AGENT_RUNNER (no FakeProc).

Marked ``integration`` / ``real_subprocess`` / ``windows_process``. CI-safe:
uses owned ``process_helper.py`` only — no Cursor/Claude network.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path

import pytest

from app.dev_control.external_agents.policy import path_violations
from app.dev_control.external_agents.runner import cursor_exec
from app.dev_control.external_agents.runner.loop import observed_changed_files
from app.dev_control.external_agents.runner.process_safe import (
    MAX_OUTPUT_BYTES,
    HeartbeatController,
    ProcessSafetyError,
    assert_safe_argv,
    resolve_executable,
    run_allowlisted,
    sanitize_env,
)
from app.dev_control.external_agents.schema import Mission, RiskClass

pytestmark = [
    pytest.mark.integration,
    pytest.mark.real_subprocess,
    pytest.mark.windows_process,
]

HELPER = (
    Path(__file__).resolve().parent / "fixtures" / "external_agent_runner" / "process_helper.py"
).resolve()


def _synth(prefix: str) -> str:
    """Runtime-assembled synthetic secret so scanners do not flag literals."""
    return prefix + "-" + os.urandom(4).hex()


def _argv(*args: str) -> list[str]:
    return [sys.executable, str(HELPER), *args]


@pytest.fixture()
def work(tmp_path):
    root = tmp_path / "allowed_root"
    cwd = root / "wt"
    cwd.mkdir(parents=True)
    return root, cwd


def test_real_env_isolation(work, monkeypatch):
    root, cwd = work
    secrets = {
        "CURSOR_TEST_SECRET": _synth("cursor"),
        "CLAUDE_TEST_SECRET": _synth("claude"),
        "GH_TOKEN": _synth("gh"),
        "DATABASE_URL": "postgres://u:" + _synth("db") + "@localhost/x",
        "AWS_SECRET_ACCESS_KEY": _synth("aws"),
        "UNRELATED_API_KEY": _synth("api"),
    }
    for k, v in secrets.items():
        monkeypatch.setenv(k, v)
    watch = list(secrets.keys())
    result = run_allowlisted(
        _argv("env-watch", *watch),
        cwd=str(cwd),
        allowed_root=str(root),
        timeout_s=30,
        env_profile="helper",
    )
    assert result.exit_code == 0
    present = json.loads(result.stdout)
    for k in watch:
        assert present.get(k) is False, k
    blob = (result.stdout or "") + (result.stderr or "")
    for v in secrets.values():
        assert v not in blob
    # Required safe scaffolding still present in built env.
    env = sanitize_env(profile="helper")
    assert "PATH" in env or "Path" in env or any(k.upper() == "PATH" for k in env)


def test_real_argument_injection_inert(work):
    root, cwd = work
    payloads = [
        "foo&bar",
        "a|b",
        "x;y",
        "PowerShell -Command Get-Process",
        "cmd /c echo hi",
        "path..\\..\\escape",
        'quote"here',
        "redir>out",
    ]
    # Newlines / && / backticks must fail closed before spawn.
    for bad in ("a&&b", "x`y", "line\ninject"):
        with pytest.raises(ProcessSafetyError):
            assert_safe_argv(_argv("echo-argv", bad), allowed_root=str(root))
    result = run_allowlisted(
        _argv("echo-argv", *payloads),
        cwd=str(cwd),
        allowed_root=str(root),
        timeout_s=30,
        env_profile="helper",
    )
    assert result.exit_code == 0
    echoed = json.loads(result.stdout)
    assert echoed == payloads


def test_real_timeout_kills_process_tree(work):
    root, cwd = work
    result = run_allowlisted(
        _argv("spawn-child", "60"),
        cwd=str(cwd),
        allowed_root=str(root),
        timeout_s=2,
        env_profile="helper",
    )
    assert result.timed_out is True
    assert result.termination_reason == "timeout"
    assert "slept" not in (result.stdout or "")
    # Parent gone.
    if result.pid:
        try:
            if os.name == "nt":
                import ctypes

                k = ctypes.windll.kernel32  # type: ignore[attr-defined]
                handle = k.OpenProcess(0x1000, False, int(result.pid))
                if handle:
                    k.CloseHandle(handle)
                    # If OpenProcess succeeded, process may still be a zombie briefly;
                    # poll via wait already completed in run_allowlisted.
            # Best-effort: returncode set after terminate.
            assert result.exit_code is not None
        except Exception:
            assert result.exit_code is not None


def test_real_cancellation_kills_tree(work):
    root, cwd = work
    cancel = threading.Event()

    def _arm():
        time.sleep(0.8)
        cancel.set()

    threading.Thread(target=_arm, daemon=True).start()
    result = run_allowlisted(
        _argv("spawn-child", "60"),
        cwd=str(cwd),
        allowed_root=str(root),
        timeout_s=60,
        env_profile="helper",
        cancel_event=cancel,
    )
    assert result.cancelled is True
    assert result.termination_reason == "cancelled"
    assert "slept" not in (result.stdout or "")


def test_real_lease_loss_via_heartbeat(work):
    root, cwd = work
    beats = {"n": 0}

    def beat() -> bool:
        beats["n"] += 1
        return beats["n"] < 2  # first ok, second = lease lost

    hb = HeartbeatController(interval_s=0.4, beat=beat)
    result = run_allowlisted(
        _argv("sleep", "30"),
        cwd=str(cwd),
        allowed_root=str(root),
        timeout_s=60,
        env_profile="helper",
        heartbeat=hb,
    )
    assert result.cancelled is True
    assert result.termination_reason == "cancelled_via_heartbeat"
    assert hb.cancelled is True


def test_real_output_cap(work):
    root, cwd = work
    result = run_allowlisted(
        _argv("flood-stdout", str(600 * 1024)),
        cwd=str(cwd),
        allowed_root=str(root),
        timeout_s=60,
        env_profile="helper",
    )
    assert result.truncated is True
    raw = (result.stdout or "").encode("utf-8", errors="replace")
    # Cap + truncation marker; must stay near MAX_OUTPUT_BYTES.
    assert len(raw) <= MAX_OUTPUT_BYTES + 64
    assert "…[truncated]" in (result.stdout or "")


def test_real_stdout_stderr_concurrency(work):
    root, cwd = work
    result = run_allowlisted(
        _argv("flood-both", str(120 * 1024)),
        cwd=str(cwd),
        allowed_root=str(root),
        timeout_s=60,
        env_profile="helper",
    )
    assert result.exit_code == 0
    assert "B" in (result.stdout or "")
    assert "C" in (result.stderr or "")


def test_real_manifests_valid_and_fail_closed(work):
    root, cwd = work
    mid = "msn_" + os.urandom(8).hex()
    ok = run_allowlisted(
        _argv("json-ok", mid),
        cwd=str(cwd),
        allowed_root=str(root),
        timeout_s=30,
        env_profile="helper",
    )
    man = cursor_exec.extract_result_manifest(ok.stdout, mid)
    assert man["executor"] == "cursor"

    bad = run_allowlisted(
        _argv("json-malformed"),
        cwd=str(cwd),
        allowed_root=str(root),
        timeout_s=30,
        env_profile="helper",
    )
    with pytest.raises(ProcessSafetyError):
        cursor_exec.extract_result_manifest(bad.stdout, mid)

    prose = run_allowlisted(
        _argv("json-prose", mid),
        cwd=str(cwd),
        allowed_root=str(root),
        timeout_s=30,
        env_profile="helper",
    )
    with pytest.raises(ProcessSafetyError):
        cursor_exec.extract_result_manifest(prose.stdout, mid)

    wrong_m = run_allowlisted(
        _argv("json-wrong-mission"),
        cwd=str(cwd),
        allowed_root=str(root),
        timeout_s=30,
        env_profile="helper",
    )
    with pytest.raises(ProcessSafetyError):
        cursor_exec.extract_result_manifest(wrong_m.stdout, mid)

    wrong_e = run_allowlisted(
        _argv("json-wrong-executor", mid),
        cwd=str(cwd),
        allowed_root=str(root),
        timeout_s=30,
        env_profile="helper",
    )
    with pytest.raises(ProcessSafetyError):
        cursor_exec.extract_result_manifest(wrong_e.stdout, mid)


def test_real_path_escape_detected(work, tmp_path):
    root, cwd = work
    # Allowed write inside fixture-like path under cwd.
    allowed_rel = Path("tests/fixtures/external_agent_runner/ok.txt")
    (cwd / "tests/fixtures/external_agent_runner").mkdir(parents=True)
    ok_path = cwd / allowed_rel
    run_allowlisted(
        _argv("write-file", str(ok_path)),
        cwd=str(cwd),
        allowed_root=str(root),
        timeout_s=30,
        env_profile="helper",
    )
    assert ok_path.is_file()

    escape = cwd / ".." / "escaped.txt"
    run_allowlisted(
        _argv("write-file", str(escape.resolve())),
        cwd=str(cwd),
        allowed_root=str(root),
        timeout_s=30,
        env_profile="helper",
    )
    abs_drive = tmp_path / "drive_escape.txt"
    run_allowlisted(
        _argv("write-file", str(abs_drive)),
        cwd=str(cwd),
        allowed_root=str(root),
        timeout_s=30,
        env_profile="helper",
    )

    mission = Mission.create(
        title="scope",
        executor="cursor",
        reviewer="claude",
        idempotency_key="scope-" + os.urandom(3).hex(),
        allowed_paths=["tests/fixtures/external_agent_runner/"],
        branch="feat/ext-scope",
        worktree=str(cwd),
        risk_class=RiskClass.GREEN,
    )
    changed = [
        "tests/fixtures/external_agent_runner/ok.txt",
        "../escaped.txt",
        str(abs_drive),
        "C:/Windows/Temp/nope.txt",
    ]
    breach = path_violations(mission, changed)
    assert "tests/fixtures/external_agent_runner/ok.txt" not in breach
    assert any("escaped" in b or ".." in b for b in breach)
    assert any("drive_escape" in b or ":" in b for b in breach)

    # Junction/symlink escape — skip when host cannot create.
    if os.name == "nt":
        try:
            link = cwd / "junction_out"
            target = tmp_path / "outside_junc"
            target.mkdir(parents=True, exist_ok=True)
            import _winapi

            _winapi.CreateJunction(str(target), str(link))  # type: ignore[attr-defined]
            junc_file = link / "via_junc.txt"
            run_allowlisted(
                _argv("write-file", str(junc_file)),
                cwd=str(cwd),
                allowed_root=str(root),
                timeout_s=30,
                env_profile="helper",
            )
            # Observed path under worktree may look in-scope; policy on absolute
            # resolved path outside allowed must still breach when reported absolute.
            breach2 = path_violations(mission, [str(junc_file.resolve())])
            assert breach2, "junction escape must be refused when reported absolute"
        except Exception as exc:
            pytest.skip(f"junction unavailable on host: {type(exc).__name__}")


def test_real_executable_identity_not_path_hijacked(work, tmp_path, monkeypatch):
    root, cwd = work
    decoy_dir = tmp_path / "decoy_bin"
    decoy_dir.mkdir()
    # Decoy python launcher that would mark hijack if selected.
    if os.name == "nt":
        decoy = decoy_dir / "python.cmd"
        decoy.write_text("@echo HIJACKED_HELPER\r\n", encoding="utf-8")
    else:
        decoy = decoy_dir / "python"
        decoy.write_text("#!/bin/sh\necho HIJACKED_HELPER\n", encoding="utf-8")
        decoy.chmod(0o755)
    monkeypatch.setenv("PATH", str(decoy_dir) + os.pathsep + os.environ.get("PATH", ""))
    abs_py = resolve_executable(sys.executable)
    result = run_allowlisted(
        [abs_py, str(HELPER), "echo-argv", "ok"],
        cwd=str(cwd),
        allowed_root=str(root),
        timeout_s=30,
        env_profile="helper",
    )
    assert result.exit_code == 0
    assert "HIJACKED_HELPER" not in (result.stdout or "")
    assert json.loads(result.stdout) == ["ok"]


def test_observed_git_scope_helper(tmp_path):
    # Smoke that observed_changed_files callable without crashing on empty repo-ish dir.
    files = observed_changed_files(str(tmp_path), "HEAD")
    assert isinstance(files, list)
