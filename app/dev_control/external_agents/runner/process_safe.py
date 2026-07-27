"""Allowlisted subprocess runner — argument arrays only, no shell."""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

MAX_OUTPUT_BYTES = 512 * 1024
DEFAULT_TIMEOUT_S = 900

# Only these basename executables may be invoked.
_ALLOWED_BASENAMES = frozenset(
    {
        "claude",
        "claude.exe",
        "agent",
        "agent.cmd",
        "agent.ps1",
        "cursor-agent",
        "cursor-agent.cmd",
    }
)

_ENV_ALLOW = frozenset(
    {
        "APPDATA",
        "HOME",
        "HOMEDRIVE",
        "HOMEPATH",
        "LOCALAPPDATA",
        "PATH",
        "PATHEXT",
        "PROGRAMDATA",
        "PROGRAMFILES",
        "PROGRAMFILES(X86)",
        "SYSTEMDRIVE",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "USERDOMAIN",
        "USERNAME",
        "USERPROFILE",
        "WINDIR",
        "COMSPEC",
        "OS",
        "NUMBER_OF_PROCESSORS",
        "PROCESSOR_ARCHITECTURE",
        "PROCESSOR_IDENTIFIER",
        "CURSOR_API_KEY",  # Cursor agent auth (value never logged)
        "CURSOR_AGENT",
        "TERM",
        "NO_COLOR",
        "LANG",
        "LC_ALL",
    }
)


class ProcessSafetyError(RuntimeError):
    """Fail-closed refusal before spawn."""


@dataclass
class ProcessResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_s: float
    timed_out: bool = False
    cancelled: bool = False
    termination_reason: str = ""
    pid: int | None = None
    truncated: bool = False


@dataclass
class HeartbeatController:
    """Background heartbeats while a child runs."""

    interval_s: float = 30.0
    beat: Callable[[], bool] | None = None
    cancel_check: Callable[[], bool] | None = None
    _stop: threading.Event = field(default_factory=threading.Event)
    beats: int = 0
    cancelled: bool = False

    def start(self) -> None:
        if self.beat is None:
            return
        t = threading.Thread(target=self._loop, name="ext-agent-hb", daemon=True)
        t.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.wait(self.interval_s):
            if self.cancel_check and self.cancel_check():
                self.cancelled = True
                self._stop.set()
                return
            try:
                ok = bool(self.beat())
                if ok:
                    self.beats += 1
                else:
                    # Lost/stolen lease or heartbeat refusal → cancel child promptly.
                    self.cancelled = True
                    self._stop.set()
                    return
            except Exception:
                self.cancelled = True
                self._stop.set()
                return


def sanitize_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    base: dict[str, str] = {}
    for k, v in os.environ.items():
        ku = k.upper()
        if ku in _ENV_ALLOW or ku.startswith("CURSOR_") or ku.startswith("CLAUDE_"):
            base[k] = v
    if extra:
        for k, v in extra.items():
            ku = k.upper()
            if (
                ku not in _ENV_ALLOW
                and not ku.startswith("CURSOR_")
                and not ku.startswith("CLAUDE_")
            ):
                raise ProcessSafetyError(f"env_injection_refused:{k}")
            base[k] = v
    return base


def assert_safe_argv(argv: list[str]) -> None:
    if not argv or not isinstance(argv, list):
        raise ProcessSafetyError("argv_required")
    if any(not isinstance(a, str) for a in argv):
        raise ProcessSafetyError("argv_must_be_strings")
    # Defense in depth: never shell=True. Refuse classic shell chaining tokens only
    # (single | inside JSON/prompt text is allowed — prompts are not shell-eval'd).
    for a in argv:
        if any(tok in a for tok in ("&&", "||", "`", "$(", "${", "\n", "\r")):
            raise ProcessSafetyError("shell_metachar_refused")
        if ";" in a and not a.startswith("--") and "PASS" not in a:
            # Allow JSON/verdict text; refuse `;` command chaining shapes.
            if "; " in a or a.strip().startswith(";"):
                raise ProcessSafetyError("shell_metachar_refused")
    exe = Path(argv[0]).name.lower()
    if exe not in _ALLOWED_BASENAMES:
        raise ProcessSafetyError(f"executable_not_allowlisted:{exe}")


def assert_worktree_allowed(cwd: str, *, allowed_root: str) -> Path:
    root = Path(allowed_root).resolve()
    work = Path(cwd).resolve()
    try:
        work.relative_to(root)
    except ValueError as exc:
        raise ProcessSafetyError("worktree_outside_allowed_root") from exc
    if not work.is_dir():
        raise ProcessSafetyError("worktree_not_directory")
    return work


def _cap(text: str, limit: int = MAX_OUTPUT_BYTES) -> tuple[str, bool]:
    raw = text.encode("utf-8", errors="replace")
    if len(raw) <= limit:
        return text, False
    return raw[:limit].decode("utf-8", errors="replace") + "\n…[truncated]", True


def run_allowlisted(
    argv: list[str],
    *,
    cwd: str,
    allowed_root: str,
    input_text: str = "",
    timeout_s: int = DEFAULT_TIMEOUT_S,
    env_extra: dict[str, str] | None = None,
    heartbeat: HeartbeatController | None = None,
    cancel_event: threading.Event | None = None,
) -> ProcessResult:
    """Spawn an allowlisted executable with shell=False and bounded I/O."""
    assert_safe_argv(argv)
    work = assert_worktree_allowed(cwd, allowed_root=allowed_root)
    env = sanitize_env(env_extra)
    t0 = time.time()
    if heartbeat:
        heartbeat.start()
    proc: subprocess.Popen[str] | None = None
    try:
        proc = subprocess.Popen(
            argv,
            cwd=str(work),
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
            start_new_session=(os.name != "nt"),
        )
        # Slice communicate so lease-loss / cancel can terminate mid-run.
        remaining = max(1, int(timeout_s))
        stdout = ""
        stderr = ""
        timed_out = False
        cancelled = False
        termination_reason = "exited"
        first_input = input_text or None
        while True:
            if cancel_event and cancel_event.is_set():
                _terminate(proc)
                cancelled = True
                termination_reason = "cancelled"
                break
            if heartbeat and heartbeat.cancelled:
                _terminate(proc)
                cancelled = True
                termination_reason = "cancelled_via_heartbeat"
                break
            slice_s = min(5, remaining)
            try:
                stdout, stderr = proc.communicate(input=first_input, timeout=slice_s)
                first_input = None
                break
            except subprocess.TimeoutExpired:
                first_input = None
                remaining -= slice_s
                if remaining <= 0:
                    _terminate(proc)
                    try:
                        stdout, stderr = proc.communicate(timeout=10)
                    except Exception:
                        stdout, stderr = "", ""
                    timed_out = True
                    termination_reason = "timeout"
                    break
        if cancelled or timed_out:
            try:
                if proc.poll() is None:
                    _terminate(proc)
                if not (stdout or stderr):
                    stdout, stderr = proc.communicate(timeout=5)
            except Exception:
                pass
            out, trunc = _cap(stdout or "")
            err, trunc2 = _cap(stderr or "")
            return ProcessResult(
                exit_code=proc.returncode if proc.returncode is not None else -1,
                stdout=out,
                stderr=err,
                duration_s=round(time.time() - t0, 3),
                timed_out=timed_out,
                cancelled=cancelled,
                termination_reason=termination_reason,
                pid=proc.pid,
                truncated=trunc or trunc2,
            )
        out, trunc = _cap(stdout or "")
        err, trunc2 = _cap(stderr or "")
        return ProcessResult(
            exit_code=int(proc.returncode if proc.returncode is not None else -1),
            stdout=out,
            stderr=err,
            duration_s=round(time.time() - t0, 3),
            pid=proc.pid,
            truncated=trunc or trunc2,
            termination_reason="exited",
        )
    finally:
        if heartbeat:
            heartbeat.stop()


def _terminate(proc: subprocess.Popen[str]) -> None:
    """Kill the child and, on Windows, the full process tree (agent.cmd → node)."""
    try:
        if proc.poll() is not None:
            return
        if os.name == "nt" and proc.pid:
            # Parent-process privilege (not executor allowlist): taskkill /T.
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                capture_output=True,
                text=True,
                shell=False,
                timeout=30,
                check=False,
            )
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            return
        try:
            os.killpg(proc.pid, signal.SIGTERM)  # type: ignore[attr-defined]
        except Exception:
            proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
