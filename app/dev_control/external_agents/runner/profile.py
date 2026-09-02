"""Dedicated executor profile roots — minimize HOME/USERPROFILE exposure."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Literal

from app.dev_control.external_agents.runner.process_safe import ProcessSafetyError

ExecutorKind = Literal["cursor", "claude", "helper"]

# Auth material we intentionally expose into the runner profile (paths only — never logged).
_CLAUDE_HOME_FILES = (
    ".credentials.json",
    "settings.json",
)
_CLAUDE_HOME_DIRS = ()  # do not mirror projects/history/shell-snapshots


def profile_root() -> Path:
    forced = (os.getenv("EXTERNAL_AGENT_PROFILE_ROOT") or "").strip()
    if forced:
        root = Path(forced)
    else:
        root = Path(tempfile.gettempdir()) / "leadgen_ext_agent_profiles"
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def _safe_link_or_copy(src: Path, dst: Path) -> str:
    """Link preferred; copy fallback. Never logs file contents."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() or dst.is_symlink():
        try:
            if dst.is_dir() and not dst.is_symlink():
                shutil.rmtree(dst)
            else:
                dst.unlink()
        except Exception:
            pass
    if not src.exists():
        return "missing"
    try:
        os.link(src, dst)
        return "hardlink"
    except Exception:
        pass
    try:
        # Symlink may require privilege on Windows — best-effort.
        os.symlink(src, dst)
        return "symlink"
    except Exception:
        pass
    try:
        shutil.copy2(src, dst)
        return "copy"
    except Exception as exc:
        raise ProcessSafetyError(f"profile_material_unavailable:{src.name}") from exc


def prepare_executor_profile(kind: ExecutorKind) -> dict[str, Any]:
    """Build redirected HOME/USERPROFILE/APPDATA/LOCALAPPDATA for a child.

    Cursor: absolute agent.cmd already resolved; LOCALAPPDATA only needs a
    writable compile-cache dir (not the full user LocalAppData tree).

    Claude: only ``.credentials.json`` (+ optional ``settings.json``) are linked
    into the dedicated home ``.claude/`` — projects/history/shell dumps stay out.
    """
    root = profile_root() / kind
    home = root / "home"
    appdata = root / "appdata"
    local = root / "localappdata"
    tmp = root / "tmp"
    for p in (home, appdata, local, tmp):
        p.mkdir(parents=True, exist_ok=True)

    evidence: dict[str, Any] = {
        "kind": kind,
        "profile_root": str(root),
        "HOME": str(home),
        "USERPROFILE": str(home),
        "APPDATA": str(appdata),
        "LOCALAPPDATA": str(local),
        "TEMP": str(tmp),
        "TMP": str(tmp),
        "material": {},
        "trust_decision": "KEEP --trust" if kind == "cursor" else "n/a",
    }

    if kind == "claude":
        claude_dir = home / ".claude"
        claude_dir.mkdir(parents=True, exist_ok=True)
        src_root = Path.home() / ".claude"
        for name in _CLAUDE_HOME_FILES:
            src = src_root / name
            how = _safe_link_or_copy(src, claude_dir / name) if src.exists() else "absent"
            evidence["material"][name] = how
        for name in _CLAUDE_HOME_DIRS:
            pass
        # Explicitly do NOT link projects/, history, shell-snapshots, chrome, etc.
        evidence["excluded_home_trees"] = [
            "projects",
            "history.jsonl",
            "shell-snapshots",
            "chrome",
            "file-history",
            "plugins",
            "sessions",
        ]

    if kind == "cursor":
        # Writable compile cache only — do not mirror full user LocalAppData.
        (local / "cursor-compile-cache").mkdir(parents=True, exist_ok=True)
        cursor_home = home / ".cursor"
        cursor_home.mkdir(parents=True, exist_ok=True)
        # Minimal Agent CLI auth/state — not chats/extensions/projects.
        src_cursor = Path.home() / ".cursor"
        for name in ("agent-cli-state.json", "cli-config.json", "argv.json"):
            src = src_cursor / name
            how = _safe_link_or_copy(src, cursor_home / name) if src.exists() else "absent"
            evidence["material"][f".cursor/{name}"] = how
        # Desktop Cursor auth.json (Roaming) — exact file only.
        src_auth = (
            Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))
            / "Cursor"
            / "auth.json"
        )
        dst_auth_dir = appdata / "Cursor"
        dst_auth_dir.mkdir(parents=True, exist_ok=True)
        how = (
            _safe_link_or_copy(src_auth, dst_auth_dir / "auth.json")
            if src_auth.exists()
            else "absent"
        )
        evidence["material"]["APPDATA/Cursor/auth.json"] = how
        evidence["material"]["cursor-compile-cache"] = "empty_dir"
        evidence["excluded_home_trees"] = [
            ".cursor/chats",
            ".cursor/extensions",
            ".cursor/projects",
            ".cursor/browser-logs",
            "APPDATA/Cursor/Cache",
            "APPDATA/Cursor/CachedData",
            "APPDATA/Cursor/GPUCache",
        ]
        evidence["trust_rationale"] = (
            "KEEP --trust: Cursor Agent non-interactive print mode requires it; "
            "containment is dedicated worktree + redirected profile env + deny-by-default "
            "secrets + post-run path scope — not the --trust flag itself."
        )

    env = {
        "HOME": str(home),
        "USERPROFILE": str(home),
        "APPDATA": str(appdata),
        "LOCALAPPDATA": str(local),
        "TEMP": str(tmp),
        "TMP": str(tmp),
    }
    # Windows drive/path split for tools that read HOMEDRIVE/HOMEPATH.
    drive, tail = os.path.splitdrive(str(home))
    if drive:
        env["HOMEDRIVE"] = drive
        env["HOMEPATH"] = tail if tail.startswith("\\") else "\\" + tail
    evidence["env"] = {k: env[k] for k in env}
    # Persist evidence (paths only) for dogfood / review.
    marker = root / "profile_evidence.json"
    try:
        import json

        marker.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        evidence["evidence_path"] = str(marker)
    except Exception:
        pass
    return {"env": env, "evidence": evidence}


def apply_profile_env(base: dict[str, str], kind: ExecutorKind) -> dict[str, str]:
    prepared = prepare_executor_profile(kind)
    out = dict(base)
    out.update(prepared["env"])
    return out
