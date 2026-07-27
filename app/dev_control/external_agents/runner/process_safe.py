"""Allowlisted subprocess runner — argument arrays only, no shell."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

MAX_OUTPUT_BYTES = 512 * 1024
DEFAULT_TIMEOUT_S = 900
# Independent reviews of large PR diffs may need a higher ceiling (still hard-capped).
_MAX_OUTPUT_HARD_CAP = 4 * 1024 * 1024

# Only these basename executables may be invoked by the runner.
_ALLOWED_BASENAMES = frozenset(
    {
        "claude",
        "claude.exe",
        "agent",
        "agent.cmd",
        "agent.ps1",
        "cursor-agent",
        "cursor-agent.cmd",
        # Test-only helper (CI/local real-process suite). Production path never
        # selects these; argv must also resolve to the owned helper script.
        "python",
        "python.exe",
        "python3",
        "py",
        "py.exe",
        # Windows wrapper capture fixtures (tests only — path-gated below).
        "argv_capture.cmd",
        "argv_capture.ps1",
        "powershell",
        "powershell.exe",
        "node",
        "node.exe",
    }
)

# Linux CI often resolves to python3.12 / python3.11 — allow versioned python3.*
_PYTHON_VERSIONED = ("python3.",)


def _is_allowed_executable_name(name: str) -> bool:
    n = name.lower()
    if n in _ALLOWED_BASENAMES:
        return True
    return any(
        n.startswith(prefix) and n[len(prefix) :].replace(".", "").isdigit()
        for prefix in _PYTHON_VERSIONED
    )


def _is_python_executable_name(name: str) -> bool:
    n = name.lower()
    if n in {"python", "python.exe", "python3", "py", "py.exe"}:
        return True
    return any(
        n.startswith(prefix) and n[len(prefix) :].replace(".", "").isdigit()
        for prefix in _PYTHON_VERSIONED
    )


# Deny-by-default OS scaffolding — no credential prefixes, no wildcards.
_OS_BASE_ENV = frozenset(
    {
        "PATH",
        "PATHEXT",
        "SYSTEMDRIVE",
        "SYSTEMROOT",
        "WINDIR",
        "TEMP",
        "TMP",
        "OS",
        "COMSPEC",
        "NUMBER_OF_PROCESSORS",
        "PROCESSOR_ARCHITECTURE",
        "PROCESSOR_IDENTIFIER",
        "PROGRAMDATA",
        "PROGRAMFILES",
        "PROGRAMFILES(X86)",
        "TERM",
        "NO_COLOR",
        "LANG",
        "LC_ALL",
        "PYTHONUTF8",
        "PYTHONIOENCODING",
    }
)

# Profile dirs for local CLI auth stores (OAuth/keychain files) — not raw API keys.
_AUTH_PROFILE_ENV = frozenset(
    {
        "APPDATA",
        "LOCALAPPDATA",
        "HOME",
        "HOMEDRIVE",
        "HOMEPATH",
        "USERPROFILE",
        "USERDOMAIN",
        "USERNAME",
    }
)

# Explicit secret-shaped names that must never be forwarded even if allowlisted by mistake.
_SECRET_NAME_DENY = (
    "API_KEY",
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "PASSWD",
    "DATABASE_URL",
    "DB_URL",
    "PRIVATE_KEY",
    "ACCESS_KEY",
)

_ENV_PROFILES: dict[str, frozenset[str]] = {
    "minimal": _OS_BASE_ENV,
    "helper": _OS_BASE_ENV | frozenset({"PYTHONPATH"}),
    # Claude Code authenticates via local profile dirs (not env wildcards).
    "claude": _OS_BASE_ENV | _AUTH_PROFILE_ENV,
    # Cursor Agent: local install under LOCALAPPDATA; optional exact key only if
    # EXTERNAL_AGENT_PASS_CURSOR_API_KEY=1 (never logged).
    "cursor": _OS_BASE_ENV | _AUTH_PROFILE_ENV,
}


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
                    self.cancelled = True
                    self._stop.set()
                    return
            except Exception:
                self.cancelled = True
                self._stop.set()
                return


def _is_secret_name(name: str) -> bool:
    ku = name.upper()
    if ku.startswith(("AWS_", "AZURE_", "GOOGLE_", "GCP_")):
        return True
    if ku in {"GITHUB_TOKEN", "GH_TOKEN", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"}:
        return True
    return any(tok in ku for tok in _SECRET_NAME_DENY)


def sanitize_env(
    extra: dict[str, str] | None = None,
    *,
    profile: str = "minimal",
) -> dict[str, str]:
    """Build a deny-by-default child environment.

    No ``CURSOR_*`` / ``CLAUDE_*`` wildcards. Credentials prefer local CLI
    profile directories; optional ``CURSOR_API_KEY`` only when explicitly gated.
    Cursor/Claude profiles redirect HOME/USERPROFILE/APPDATA/LOCALAPPDATA to
    dedicated runner-owned trees (see ``profile.prepare_executor_profile``).
    """
    allowed = _ENV_PROFILES.get(profile)
    if allowed is None:
        raise ProcessSafetyError(f"unknown_env_profile:{profile}")
    base: dict[str, str] = {}
    for k, v in os.environ.items():
        ku = k.upper()
        if _is_secret_name(ku):
            continue
        if ku in allowed:
            base[k] = v
    # Exact optional Cursor key — never wildcard, never logged.
    if profile == "cursor" and (os.getenv("EXTERNAL_AGENT_PASS_CURSOR_API_KEY") or "").strip() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        key = os.environ.get("CURSOR_API_KEY")
        if key:
            base["CURSOR_API_KEY"] = key
    if extra:
        for k, v in extra.items():
            ku = k.upper()
            if _is_secret_name(ku):
                raise ProcessSafetyError(f"env_injection_refused:{k}")
            if ku not in allowed and not (
                profile == "cursor"
                and ku == "CURSOR_API_KEY"
                and (os.getenv("EXTERNAL_AGENT_PASS_CURSOR_API_KEY") or "").strip()
                in {"1", "true", "yes", "on"}
            ):
                raise ProcessSafetyError(f"env_injection_refused:{k}")
            base[k] = v
    # Dedicated profile redirection for real executors (not helper/minimal).
    if profile in {"cursor", "claude"}:
        from app.dev_control.external_agents.runner.profile import apply_profile_env

        base = apply_profile_env(base, profile)  # type: ignore[arg-type]
    return base


HELPER_SCRIPT_NAME = "process_helper.py"
_WRAPPER_FIXTURE_NAMES = frozenset({"argv_capture.cmd", "argv_capture.ps1"})


def _is_fixture_path(path: Path) -> bool:
    parts = {p.lower() for p in path.resolve().parts}
    return "fixtures" in parts and "external_agent_runner" in parts


def resolve_executable(exe: str) -> str:
    """Resolve argv[0] to an absolute path; refuse PATH-relative hijack surfaces.

    Callers (Cursor/Claude resolvers, tests) must pass an absolute path. Relative
    basenames are resolved once via ``shutil.which`` then re-checked against the
    allowlist — production paths always prefer absolute resolution up-front.
    """
    if not exe or not isinstance(exe, str):
        raise ProcessSafetyError("executable_required")
    path = Path(exe)
    if path.is_absolute():
        resolved = path.resolve()
    else:
        found = shutil.which(exe)
        if not found:
            raise ProcessSafetyError(f"executable_not_found:{exe}")
        resolved = Path(found).resolve()
    if not resolved.exists():
        raise ProcessSafetyError(f"executable_missing:{resolved}")
    name = resolved.name.lower()
    if not _is_allowed_executable_name(name):
        raise ProcessSafetyError(f"executable_not_allowlisted:{name}")
    return str(resolved)


def assert_safe_argv(argv: list[str], *, allowed_root: str | None = None) -> None:
    if not argv or not isinstance(argv, list):
        raise ProcessSafetyError("argv_required")
    if any(not isinstance(a, str) for a in argv):
        raise ProcessSafetyError("argv_must_be_strings")
    for a in argv:
        if any(tok in a for tok in ("&&", "||", "`", "$(", "${", "\n", "\r")):
            raise ProcessSafetyError("shell_metachar_refused")
        # Block cmd.exe %VAR% / delayed !VAR! expansion surfaces before spawn.
        if "%" in a and any(a[i + 1 :].find("%") > 0 for i, ch in enumerate(a) if ch == "%"):
            raise ProcessSafetyError("env_expansion_refused")
        if "!" in a and any(a[i + 1 :].find("!") > 0 for i, ch in enumerate(a) if ch == "!"):
            raise ProcessSafetyError("delayed_expansion_refused")
        if ";" in a and not a.startswith("--") and "PASS" not in a:
            if "; " in a or a.strip().startswith(";"):
                raise ProcessSafetyError("shell_metachar_refused")
    exe = Path(argv[0]).name.lower()
    if not _is_allowed_executable_name(exe):
        raise ProcessSafetyError(f"executable_not_allowlisted:{exe}")
    # .cmd/.bat re-parse &|<>^ via cmd.exe — refuse those tokens for batch wrappers.
    if exe.endswith((".cmd", ".bat")):
        for a in argv[1:]:
            if any(ch in a for ch in ("&", "|", "<", ">", "^")):
                raise ProcessSafetyError("cmd_metachar_refused")
    # Python is only for the owned test helper script — never arbitrary -c.
    if _is_python_executable_name(exe):
        if len(argv) < 2 or argv[1] in {"-c", "-m"}:
            raise ProcessSafetyError("python_helper_script_required")
        script = Path(argv[1]).resolve()
        if script.name != HELPER_SCRIPT_NAME:
            raise ProcessSafetyError("python_helper_name_refused")
        # Owned fixture identity — helper lives under tests/fixtures, not inside
        # the mission worktree (cwd). Do not require script ⊆ allowed_root.
        if not _is_fixture_path(script):
            raise ProcessSafetyError("python_helper_path_refused")
        if not script.is_file():
            raise ProcessSafetyError("python_helper_missing")
    # Direct .cmd/.ps1 capture wrappers — fixtures only.
    if exe in _WRAPPER_FIXTURE_NAMES:
        wrapper = Path(argv[0]).resolve()
        if not _is_fixture_path(wrapper) or not wrapper.is_file():
            raise ProcessSafetyError("wrapper_fixture_path_refused")
    # node.exe only when hosting cursor-agent index.js under versions/.
    if exe in {"node", "node.exe"}:
        if len(argv) < 2:
            raise ProcessSafetyError("node_index_required")
        index = Path(argv[1]).resolve()
        parts = {p.lower() for p in index.parts}
        if (
            index.name.lower() != "index.js"
            or "cursor-agent" not in parts
            or "versions" not in parts
        ):
            raise ProcessSafetyError("node_cursor_index_refused")
        if not index.is_file():
            raise ProcessSafetyError("node_cursor_index_missing")
    # PowerShell may host argv_capture.ps1 (fixtures) or cursor-agent/*.ps1.
    if exe in {"powershell", "powershell.exe"}:
        try:
            file_idx = next(i for i, a in enumerate(argv) if a.lower() == "-file")
        except StopIteration as exc:
            raise ProcessSafetyError("powershell_file_required") from exc
        if file_idx + 1 >= len(argv):
            raise ProcessSafetyError("powershell_file_required")
        script = Path(argv[file_idx + 1]).resolve()
        name = script.name.lower()
        parts = {p.lower() for p in script.parts}
        if name == "argv_capture.ps1":
            if not _is_fixture_path(script):
                raise ProcessSafetyError("powershell_wrapper_refused")
        elif name in {"agent.ps1", "cursor-agent.ps1"}:
            if "cursor-agent" not in parts:
                raise ProcessSafetyError("powershell_cursor_ps1_refused")
        else:
            raise ProcessSafetyError("powershell_script_refused")
        if not script.is_file():
            raise ProcessSafetyError("powershell_script_missing")


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


def _bounded_pipe_reader(
    pipe: Any,
    *,
    limit: int,
    chunks: list[str],
    truncated: list[bool],
) -> None:
    """Drain a pipe forever (avoid deadlock) while retaining at most ``limit`` bytes."""
    total = 0
    try:
        while True:
            data = pipe.read(65536)
            if not data:
                break
            raw = data.encode("utf-8", errors="replace") if isinstance(data, str) else data
            if total >= limit:
                truncated[0] = True
                continue
            room = limit - total
            if len(raw) <= room:
                chunks.append(
                    data if isinstance(data, str) else raw.decode("utf-8", errors="replace")
                )
                total += len(raw)
            else:
                keep = raw[:room].decode("utf-8", errors="replace")
                chunks.append(keep)
                total = limit
                truncated[0] = True
    except Exception:
        pass


def run_allowlisted(
    argv: list[str],
    *,
    cwd: str,
    allowed_root: str,
    input_text: str = "",
    timeout_s: int = DEFAULT_TIMEOUT_S,
    env_extra: dict[str, str] | None = None,
    env_profile: str = "minimal",
    heartbeat: HeartbeatController | None = None,
    cancel_event: threading.Event | None = None,
    max_output_bytes: int | None = None,
) -> ProcessResult:
    """Spawn an allowlisted executable with shell=False and bounded I/O."""
    assert_safe_argv(argv, allowed_root=allowed_root)
    resolved_argv = [resolve_executable(argv[0]), *argv[1:]]
    work = assert_worktree_allowed(cwd, allowed_root=allowed_root)
    env = sanitize_env(env_extra, profile=env_profile)
    out_limit = MAX_OUTPUT_BYTES if max_output_bytes is None else int(max_output_bytes)
    out_limit = max(64 * 1024, min(_MAX_OUTPUT_HARD_CAP, out_limit))
    t0 = time.time()
    if heartbeat:
        heartbeat.start()
    proc: subprocess.Popen[str] | None = None
    try:
        proc = subprocess.Popen(
            resolved_argv,
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
        out_chunks: list[str] = []
        err_chunks: list[str] = []
        out_trunc = [False]
        err_trunc = [False]
        readers = [
            threading.Thread(
                target=_bounded_pipe_reader,
                args=(proc.stdout,),
                kwargs={"limit": out_limit, "chunks": out_chunks, "truncated": out_trunc},
                daemon=True,
                name="ext-agent-stdout",
            ),
            threading.Thread(
                target=_bounded_pipe_reader,
                args=(proc.stderr,),
                kwargs={"limit": out_limit, "chunks": err_chunks, "truncated": err_trunc},
                daemon=True,
                name="ext-agent-stderr",
            ),
        ]
        for t in readers:
            t.start()
        if proc.stdin is not None:
            try:
                if input_text:
                    proc.stdin.write(input_text)
                proc.stdin.close()
            except Exception:
                pass
        remaining = max(1, int(timeout_s))
        timed_out = False
        cancelled = False
        termination_reason = "exited"
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
            slice_s = min(1.0, float(remaining))
            try:
                proc.wait(timeout=slice_s)
                break
            except subprocess.TimeoutExpired:
                remaining -= int(max(1, round(slice_s)))
                if remaining <= 0:
                    _terminate(proc)
                    timed_out = True
                    termination_reason = "timeout"
                    break
        for t in readers:
            t.join(timeout=5)
        stdout = "".join(out_chunks)
        stderr = "".join(err_chunks)
        if out_trunc[0] and not stdout.endswith("\n…[truncated]"):
            stdout = stdout + "\n…[truncated]"
        if err_trunc[0] and not stderr.endswith("\n…[truncated]"):
            stderr = stderr + "\n…[truncated]"
        trunc = bool(out_trunc[0] or err_trunc[0])
        if cancelled or timed_out:
            try:
                if proc.poll() is None:
                    _terminate(proc)
            except Exception:
                pass
            return ProcessResult(
                exit_code=proc.returncode if proc.returncode is not None else -1,
                stdout=stdout,
                stderr=stderr,
                duration_s=round(time.time() - t0, 3),
                timed_out=timed_out,
                cancelled=cancelled,
                termination_reason=termination_reason,
                pid=proc.pid,
                truncated=trunc,
            )
        return ProcessResult(
            exit_code=int(proc.returncode if proc.returncode is not None else -1),
            stdout=stdout,
            stderr=stderr,
            duration_s=round(time.time() - t0, 3),
            pid=proc.pid,
            truncated=trunc,
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
