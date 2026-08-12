"""
Sandbox executor (SB-01 / SB-02 / SB-03).

Replaces the executor in `app/agents/code_exec.py`, which self-admits
"YEH EK TRUE SANDBOX NAHI HAI" and runs model code via `python -I -c` as a
plain child sharing the container's secrets, filesystem and network.

This module provides a real (if minimal) isolation boundary out of the box and
a backend hook for stronger isolation in production:

* ``subprocess`` backend (default): POSIX ``resource`` rlimits (CPU seconds,
  address space, file size, no core dumps), an **environment scrubbed of every
  secret**, a throwaway temp CWD, wall-clock timeout+kill, and output caps.
  Egress is *not* trusted to the process — the allow-list is advisory here and
  MUST be backed by a network namespace / firewall in prod.
* ``container`` / ``gvisor`` / ``microvm`` backends (prod): selected via
  ``SANDBOX_BACKEND`` — stubs that raise NotImplementedError until wired to
  your Docker/Firecracker tooling, so you cannot silently ship the weak backend
  to prod thinking it is strong.

NOTE: real egress default-deny requires OS-level isolation. On the subprocess
backend we scrub credentials so leaked code cannot *authenticate* to your
providers, which is the highest-value mitigation; treat network containment as
a prod-backend responsibility.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from dataclasses import dataclass, field
from typing import List, Optional

try:
    from app.utils.logger import setup_logger  # type: ignore

    logger = setup_logger(__name__)
except Exception:  # pragma: no cover
    import logging

    logger = logging.getLogger(__name__)

# Any env var whose NAME matches these fragments is stripped before exec.
_SECRET_FRAGMENTS = (
    "KEY",
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "PASSWD",
    "DSN",
    "CREDENTIAL",
    "PRIVATE",
    "SID",
    "AUTH",
    "WEBHOOK",
    "VPA",
)


@dataclass
class SandboxResult:
    ok: bool
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    timed_out: bool = False


@dataclass
class SandboxPolicy:
    cpu_seconds: int = 5
    address_space_mb: int = 512
    file_size_mb: int = 16
    wall_clock_s: float = 15.0
    max_output_chars: int = 4000
    allowed_egress: list[str] = field(default_factory=list)  # advisory on subprocess backend


def _scrubbed_env() -> dict:
    env = {}
    for k, v in os.environ.items():
        upper = k.upper()
        if any(frag in upper for frag in _SECRET_FRAGMENTS):
            continue
        env[k] = v
    # Minimal, predictable PATH/локация; no user site.
    env.setdefault("PYTHONNOUSERSITE", "1")
    env["HARNESS_SANDBOX"] = "1"
    return env


def _apply_rlimits(policy: SandboxPolicy):
    """Returns a preexec_fn that sets POSIX rlimits, or None on non-POSIX."""
    try:
        import resource  # POSIX only
    except Exception:
        return None

    def _limit():
        resource.setrlimit(resource.RLIMIT_CPU, (policy.cpu_seconds, policy.cpu_seconds))
        mem = policy.address_space_mb * 1024 * 1024
        try:
            resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
        except Exception:
            pass
        fsz = policy.file_size_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_FSIZE, (fsz, fsz))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        os.setsid()  # own process group so we can kill the whole tree

    return _limit


class Sandbox:
    def __init__(self, policy: SandboxPolicy | None = None) -> None:
        self.policy = policy or SandboxPolicy()
        self.backend = os.getenv("SANDBOX_BACKEND", "subprocess").lower()

    async def run_python(self, script: str) -> SandboxResult:
        if self.backend in ("container", "gvisor", "microvm"):
            return await self._run_strong(script)
        return await self._run_subprocess(script)

    async def _run_strong(self, script: str) -> SandboxResult:  # pragma: no cover
        raise NotImplementedError(
            f"SANDBOX_BACKEND={self.backend!r} not wired. Implement the "
            "container/microVM runner (see docs Phase 0) before using in prod. "
            "Refusing to silently fall back to the weak subprocess backend."
        )

    async def _run_subprocess(self, script: str) -> SandboxResult:
        p = self.policy
        with tempfile.TemporaryDirectory(prefix="harness_sbx_") as cwd:
            try:
                proc = await asyncio.create_subprocess_exec(
                    sys.executable,
                    "-I",
                    "-B",
                    "-c",
                    script,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=cwd,
                    env=_scrubbed_env(),
                    preexec_fn=_apply_rlimits(p),
                    start_new_session=True,
                )
            except Exception as e:
                logger.warning("harness.sandbox: spawn failed: %s", e)
                return SandboxResult(ok=False, stderr=f"spawn failed: {e}", exit_code=None)

            try:
                out, err = await asyncio.wait_for(proc.communicate(), timeout=p.wall_clock_s)
            except asyncio.TimeoutError:
                await self._kill_tree(proc)
                return SandboxResult(ok=False, stderr="wall-clock timeout", timed_out=True)

            code = proc.returncode
            return SandboxResult(
                ok=(code == 0),
                stdout=out.decode("utf-8", "replace")[: p.max_output_chars],
                stderr=err.decode("utf-8", "replace")[: p.max_output_chars],
                exit_code=code,
            )

    @staticmethod
    async def _kill_tree(proc) -> None:
        try:
            import signal

            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
