"""Static code diagnostics for engineering agents — OpenCode (anomalyco/opencode) parity.

OpenCode ka defining engineering feature: jab agent code edit karta hai, woh LSP server
se diagnostics (syntax/undefined-name/type errors) leke wapas LLM ko deta hai → LLM khud
self-correct karta. Yeh "diagnostics-before-trust" loop is project me missing tha.

Adapted honestly to our architecture (agents code GENERATE/APPLY nahi karte — sirf
proposals/sketches dete, deploy-gated): yeh module woh validation 2 jagah deta jahan
genuine value hai —
  1. `check_references()` → Vikram code_upgrader ke proposal-cited paths REALLY exist
     karte hain ya nahi (hallucinated file-path = top LLM failure-mode). Gated, low-noise.
  2. `check_code()` (ast syntax + optional ruff lint) → admin diagnostics endpoint, taaki
     admin patch-code ko approve karne se PEHLE validate kare (human-in-loop = hamara
     deploy-gated philosophy).

Design (project patterns): never-raise, stdlib-baseline (`ast` always; `ruff` OPTIONAL —
present ho to undefined-name/F-rules milte, warna sirf syntax). Read-only, import-safe.

Flag: CODE_DIAGNOSTICS=1 (gates the AUTOMATIC Vikram self-check; admin endpoint
flag-independent).
"""

from __future__ import annotations

import ast
import os
import shutil
import subprocess
import textwrap
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_MSG_CAP = 240


def enabled() -> bool:
    """Gates AUTOMATIC agent self-check (Vikram). Admin endpoint flag-independent."""
    return (os.getenv("CODE_DIAGNOSTICS") or "").strip().lower() in ("1", "true", "yes")


def check_code(code: str, run_lint: bool = True) -> list[dict[str, Any]]:
    """Validate a Python snippet → diagnostics list.

    Returns [{level, code, line, col, message}]. Empty = clean. Never raises.
    Baseline = `ast` syntax (stdlib). If `ruff` binary present, adds pyflakes-class
    rules (undefined names etc.) — the LSP-diagnostics equivalent; absent → syntax-only.
    """
    src = textwrap.dedent(code or "").strip("\n")
    if not src.strip():
        return []

    diags: list[dict[str, Any]] = []
    try:
        ast.parse(src)
    except SyntaxError as e:
        diags.append(
            {
                "level": "error",
                "code": "syntax",
                "line": int(e.lineno or 0),
                "col": int(e.offset or 0),
                "message": (e.msg or "syntax error")[:_MSG_CAP],
            }
        )
        return diags  # unparseable → linting impossible
    except Exception as e:  # pragma: no cover - defensive
        logger.debug(f"check_code ast failed: {e}")
        return diags

    if run_lint:
        diags.extend(_ruff_lint(src))
    return diags


def _ruff_lint(src: str) -> list[dict[str, Any]]:
    """Optional ruff pass (pyflakes 'F' rules = undefined-name etc.). [] if ruff absent."""
    try:
        exe = shutil.which("ruff")
        if not exe:
            return []
        proc = subprocess.run(  # noqa: S603 - fixed args, stdin only
            [
                exe,
                "check",
                "--quiet",
                "--output-format",
                "json",
                "--select",
                "F",
                "--stdin-filename",
                "agent_snippet.py",
                "-",
            ],
            input=src,
            capture_output=True,
            text=True,
            timeout=15,
        )
        out = (proc.stdout or "").strip()
        if not out:
            return []
        import json as _json

        rows = _json.loads(out)
        res: list[dict[str, Any]] = []
        for r in rows or []:
            loc = r.get("location") or {}
            res.append(
                {
                    "level": "warning",
                    "code": str(r.get("code") or "lint"),
                    "line": int(loc.get("row") or 0),
                    "col": int(loc.get("column") or 0),
                    "message": str(r.get("message") or "")[:_MSG_CAP],
                }
            )
        return res
    except Exception as e:  # pragma: no cover - ruff missing / json skew / timeout
        logger.debug(f"ruff lint skipped: {e}")
        return []


def check_references(paths: list[str], project_root: str = ".") -> list[dict[str, Any]]:
    """Verify each cited path exists in the repo (catches hallucinated file refs).

    `paths` may carry a ":line-range" suffix (e.g. "app/x.py:10-20") — stripped.
    Never raises.
    """
    diags: list[dict[str, Any]] = []
    try:
        root = os.path.abspath(project_root)
    except Exception:
        root = os.path.abspath(".")
    seen: set[str] = set()
    for p in paths or []:
        if not isinstance(p, str):
            continue
        rel = p.split(":", 1)[0].replace("\\", "/").strip()
        if not rel or rel in seen:
            continue
        seen.add(rel)
        try:
            if not os.path.exists(os.path.join(root, rel)):
                diags.append(
                    {
                        "level": "error",
                        "code": "missing-file",
                        "line": 0,
                        "col": 0,
                        "message": f"referenced path not found: {rel}",
                    }
                )
        except Exception:
            continue
    return diags


def summary(diags: list[dict[str, Any]]) -> str:
    """Compact human/LLM-readable diagnostics summary."""
    if not diags:
        return "ok — no diagnostics"
    errs = sum(1 for d in diags if d.get("level") == "error")
    warns = len(diags) - errs
    lines = [
        f"  [{d.get('level')}] {d.get('code')} L{d.get('line')}: {d.get('message')}"
        for d in diags[:8]
    ]
    return f"{errs} error(s), {warns} warning(s)\n" + "\n".join(lines)


__all__ = ["enabled", "check_code", "check_references", "summary"]
