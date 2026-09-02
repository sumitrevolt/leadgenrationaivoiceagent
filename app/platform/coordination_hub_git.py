"""Bounded, redacted git probe for Coordination Hub (read-only).

Allowlisted subcommands only. Timeout + byte cap. Never returns secrets.
"""

from __future__ import annotations

import os
import re
import subprocess
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_DEFAULT_TIMEOUT = 5.0
_MAX_BYTES = 12_000

_SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|secret|password|token|bearer)\s*[=:]\s*\S+"),
    re.compile(r"(?i)\bsk-[A-Za-z0-9_-]{10,}\b"),
    re.compile(r"(?i)\bghp_[A-Za-z0-9]{20,}\b"),
    re.compile(r"(?i)\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"(?i)authorization:\s*bearer\s+\S+"),
    re.compile(r"(?i)\.env\b.*[=:].+"),
)

_ALLOWED = {
    "status": ["status", "--porcelain=v1", "-b"],
    "head": ["rev-parse", "HEAD"],
    "log": ["log", "-n", "5", "--oneline", "--no-decorate"],
}


def redact_git_text(text: str) -> str:
    out = text or ""
    for pat in _SECRET_PATTERNS:
        out = pat.sub("[redacted]", out)
    return out


def _run(args: list[str], *, timeout: float, cwd: str | None) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=cwd or os.getcwd(),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout", "stdout": "", "stderr": "", "args": args}
    except FileNotFoundError:
        return {"ok": False, "error": "git_missing", "stdout": "", "stderr": "", "args": args}
    except Exception as e:  # pragma: no cover
        logger.debug("[coord_hub_git] run fail: %s", e)
        return {"ok": False, "error": str(e)[:120], "stdout": "", "stderr": "", "args": args}

    stdout = redact_git_text((proc.stdout or "")[:_MAX_BYTES])
    stderr = redact_git_text((proc.stderr or "")[:_MAX_BYTES])
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "args": args,
        "truncated": len(proc.stdout or "") > _MAX_BYTES or len(proc.stderr or "") > _MAX_BYTES,
    }


def probe_git(*, cwd: str | None = None, timeout: float | None = None) -> dict[str, Any]:
    """Run allowlisted read-only git probes. Never mutates the repo."""
    t = float(
        timeout if timeout is not None else os.getenv("COORD_HUB_GIT_TIMEOUT", _DEFAULT_TIMEOUT)
    )
    t = max(0.5, min(t, 15.0))
    results: dict[str, Any] = {}
    for name, args in _ALLOWED.items():
        results[name] = _run(args, timeout=t, cwd=cwd)
    head = (results.get("head") or {}).get("stdout", "").strip()
    return {
        "ok": True,
        "head": head[:40],
        "commands": results,
        "timeout_s": t,
        "max_bytes": _MAX_BYTES,
        "redacted": True,
    }


__all__ = ["probe_git", "redact_git_text"]
