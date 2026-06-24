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


def enabled() -> bool:
    """HARD GATE — default OFF. Bina iske execute() inert (kuch run nahi hota)."""
    return (os.getenv("CODE_EXEC") or "").strip().lower() in ("1", "true", "yes")


def _trunc(b: bytes | None) -> str:
    try:
        s = (b or b"").decode("utf-8", "replace")
    except Exception:
        s = ""
    return s[:_OUTPUT_CAP]


async def execute(script: str, timeout_s: int = 20) -> dict[str, Any]:
    """Python `script` ko ek isolated guarded subprocess me chalao.

    GATED: agar enabled() False → {"ok":False,"error":"disabled","hint":"set CODE_EXEC=1"}
    BINA kuch run kiye (no spawn). Yeh true sandbox nahi — guarded subprocess only
    (super-admin + flag). Returns {ok, stdout, stderr, returncode, timed_out}.
    """
    if not enabled():
        return {"ok": False, "error": "disabled", "hint": "set CODE_EXEC=1"}

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
