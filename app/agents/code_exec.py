"""Code exec — guarded Python tool-script executor (Hermes execute_code parity).

⚠️  SECURITY-CRITICAL — SUPER-ADMIN + FLAG GATED, DEFAULT OFF (INERT). ⚠️
    Bina `CODE_EXEC=1` ke `execute()` KUCH BHI run NAHI karta — seedha
    {"ok":False,"error":"disabled"} return karta hai (zero subprocess spawn).

YEH EK TRUE SANDBOX NAHI HAI. Sirf ek GUARDED subprocess hai:
  - sys.executable `-I` (isolated mode: PYTHON* env + user site-packages ignore)
    `-c <script>` ke saath, shell=True KABHI nahi (no shell-injection surface).
  - Hard wall-clock timeout (timeout pe process kill).
  - stdout/stderr capture + truncate (4000 chars).
  - Koi network whitelisting / filesystem jail / seccomp PROMISE nahi — agar
    `CODE_EXEC=1` ON hai to script wahi access kar sakta jo container/process ke
    paas hai. Isliye super-admin + flag dono mandatory, aur default OFF rakha gaya.
    Prod pe ON karne se pehle blast-radius samjho (container-isolation pe rely).

Import-safe, kabhi raise nahi. Flag: CODE_EXEC=1
"""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_OUTPUT_CAP = 4000  # stdout/stderr truncate (response bloat + log safety)
_MAX_TIMEOUT_S = 120  # absolute ceiling (caller timeout_s isse upar nahi ja sakta)

# The ONLY identity that may run code WITHOUT an explicit permission grant: the
# require_super_admin /exec HTTP endpoint (a human) passes "super_admin". EVERY other
# caller — including any internal/automation identity — must hold an explicit
# execute_code grant in the agent_permissions matrix (HIGH_RISK, unset = deny). No
# broad "system" sentinel (audit hardening: a derived/forwarded agent name must never
# coast into RCE).
_TRUSTED = {"super_admin"}


def enabled() -> bool:
    """HARD GATE — default OFF. Bina iske execute() inert (kuch run nahi hota)."""
    return (os.getenv("CODE_EXEC") or "").strip().lower() in ("1", "true", "yes")


def _permitted(agent: str) -> bool:
    """Defense-in-depth: trusted human identity always OK; named automation agents
    must hold `execute_code` permission (AGENT_PERMISSIONS). Fail-SAFE (deny on error)
    because this gates arbitrary code execution."""
    a = (agent or "super_admin").strip().lower()
    if a in _TRUSTED:
        return True
    try:
        from app.agents import agent_permissions

        return bool(agent_permissions.can(a, "execute_code"))
    except Exception:
        return False  # RCE gate → unknown = deny


def _trunc(b: bytes | None) -> str:
    try:
        s = (b or b"").decode("utf-8", "replace")
    except Exception:
        s = ""
    return s[:_OUTPUT_CAP]


async def execute(script: str, timeout_s: int = 20, agent: str = "super_admin") -> dict[str, Any]:
    """Python `script` ko ek isolated guarded subprocess me chalao.

    GATED (2 layers, dono pass hone par hi run hota):
      1. enabled() False → {"ok":False,"error":"disabled"} (no spawn).
      2. _permitted(agent) False → {"ok":False,"error":"permission_denied"} (no spawn) —
         defense-in-depth so koi automation-agent RCE self-trigger na kare; sirf trusted
         human (super_admin) ya explicitly-granted agent. AGENT_PERMISSIONS se enforce.
    Yeh true sandbox nahi — guarded subprocess only. Returns {ok, stdout, stderr, ...}.
    """
    if not enabled():
        return {"ok": False, "error": "disabled", "hint": "set CODE_EXEC=1"}

    if not _permitted(agent):
        logger.warning("code_exec blocked: agent=%s lacks execute_code permission", agent)
        return {"ok": False, "error": "permission_denied", "agent": (agent or "").strip().lower()}

    script = script or ""
    try:
        timeout = max(1, min(int(timeout_s or 20), _MAX_TIMEOUT_S))
    except Exception:
        timeout = 20

    proc = None
    try:
        # -I = isolated mode (ignore env PYTHON*/user-site); -c = inline script.
        # NEVER shell=True (no shell-injection / arg-splitting surface).
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-I",
            "-c",
            script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except Exception:
                pass
            try:
                await proc.wait()
            except Exception:
                pass
            return {
                "ok": False,
                "stdout": "",
                "stderr": f"timeout after {timeout}s",
                "returncode": None,
                "timed_out": True,
            }
        rc = proc.returncode
        return {
            "ok": rc == 0,
            "stdout": _trunc(stdout),
            "stderr": _trunc(stderr),
            "returncode": rc,
            "timed_out": False,
        }
    except Exception as e:  # never-raise — guarded executor kabhi caller ko nahi todta
        logger.debug(f"code_exec.execute failed: {e}")
        try:
            if proc is not None:
                proc.kill()
        except Exception:
            pass
        return {
            "ok": False,
            "stdout": "",
            "stderr": str(e)[:_OUTPUT_CAP],
            "returncode": None,
            "timed_out": False,
        }


__all__ = ["enabled", "execute"]
