"""
Obsidian Second Brain — Git-sync vault writer.
=================================================

VPS agents write markdown notes to data/obsidian_staging/ (local, instant).
Nightly Celery job compacts + git-pushes to remote → user pulls in Obsidian.

Design:
  - write_note(folder, slug, content, tags): atomic write, never raises
  - append_note(folder, slug, entry): append timestamped entry to existing note
  - push_to_git(): git add/commit/push with 60s timeout
  - compact_folder(folder): archive if >N files
  - Flag gate: OBSIDIAN_SYNC=1 — all functions are no-ops when unset
  - Per-agent throttle in append_note: max 1 write per THROTTLE_S per agent

Vault structure (data/obsidian_staging/):
  Leads/        ← per-prospect timeline (phone10.md)
  Clients/      ← per-client profile (client_id.md)
  Agents/       ← per-staff daily digest (MemberName.md)
  Decisions/    ← council verdicts + ADRs
  Campaigns/    ← campaign results, A/B outcomes
  System/       ← prod_check, health snapshots, scheduler status
  Skills/       ← key skill docs mirrored
  Sessions/     ← daily digest summaries
  Inbox/        ← raw agent outputs not yet categorized
"""

from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("platform.obsidian_sync")

_DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
_VAULT = _DATA_DIR / "obsidian_staging"
_LOCK = threading.Lock()

# Per-agent write throttle (member → last_write_ts)
_agent_last_write: dict[str, float] = {}
_THROTTLE_S = 300  # 5 minutes between writes per agent

_GIT_REMOTE = os.getenv("OBSIDIAN_GIT_REMOTE", "")


def _enabled() -> bool:
    return os.getenv("OBSIDIAN_SYNC", "0").strip().lower() in ("1", "true", "yes", "on")


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _folder_path(folder: str) -> Path:
    return _VAULT / folder.strip("/")


def write_note(folder: str, slug: str, content: str, tags: list[str] | None = None) -> bool:
    """Write (overwrite) a markdown note. Atomic via temp→rename. Never raises."""
    if not _enabled():
        return False
    try:
        p = _folder_path(folder) / f"{slug}.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        tag_line = ""
        if tags:
            tag_line = "tags: [" + ", ".join(tags) + "]\n"
        full = f"---\n{tag_line}updated: {_ts()}\n---\n\n{content}"
        tmp = p.with_suffix(".tmp")
        tmp.write_text(full, encoding="utf-8")
        tmp.replace(p)
        return True
    except Exception as e:
        logger.debug("[obsidian] write_note failed %s/%s: %s", folder, slug, e)
        return False


def append_note(
    folder: str,
    slug: str,
    entry: str,
    *,
    member: str = "",
    tags: list[str] | None = None,
) -> bool:
    """Append a timestamped entry to a note. Creates if missing.
    Throttled: max 1 write per THROTTLE_S per member (for high-frequency callers like log_event).
    Never raises."""
    if not _enabled():
        return False
    if member:
        now = time.monotonic()
        key = member.lower()
        with _LOCK:
            if now - _agent_last_write.get(key, 0.0) < _THROTTLE_S:
                return False
            _agent_last_write[key] = now
    try:
        p = _folder_path(folder) / f"{slug}.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        header = ""
        if not p.exists():
            tag_line = ("tags: [" + ", ".join(tags) + "]\n") if tags else ""
            header = f"---\n{tag_line}created: {_ts()}\n---\n\n# {slug}\n\n"
        line = f"\n- **{_ts()}** — {entry.strip()}"
        with p.open("a", encoding="utf-8") as f:
            f.write(header + line + "\n")
        return True
    except Exception as e:
        logger.debug("[obsidian] append_note failed %s/%s: %s", folder, slug, e)
        return False


def push_to_git() -> bool:
    """git add -A + commit + push. 60s timeout. Alerts ops on failure. Never raises."""
    if not _enabled():
        return False
    if not _VAULT.exists():
        logger.debug("[obsidian] vault dir missing — skip push")
        return False
    try:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        cmds = [
            ["git", "-C", str(_VAULT), "add", "-A"],
            ["git", "-C", str(_VAULT), "commit", "--allow-empty", "-m", f"brain: nightly sync {date_str}"],
            ["git", "-C", str(_VAULT), "push"],
        ]
        for cmd in cmds:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode not in (0, 1):  # 1 = nothing to commit is ok
                logger.warning("[obsidian] git cmd failed: %s → %s", cmd, result.stderr[:200])
        logger.info("[obsidian] nightly push complete")
        return True
    except subprocess.TimeoutExpired:
        logger.warning("[obsidian] git push timed out after 60s")
        _alert("obsidian git push timed out")
    except Exception as e:
        logger.warning("[obsidian] push_to_git error: %s", e)
        _alert(f"obsidian push failed: {e}")
    return False


def compact_folder(folder: str, max_files: int = 200) -> None:
    """Archive oldest files when folder exceeds max_files. Never raises."""
    if not _enabled():
        return
    try:
        p = _folder_path(folder)
        if not p.exists():
            return
        files = sorted(p.glob("*.md"), key=lambda f: f.stat().st_mtime)
        if len(files) <= max_files:
            return
        archive = p / "archive"
        archive.mkdir(exist_ok=True)
        to_move = files[: len(files) - max_files]
        for f in to_move:
            f.rename(archive / f.name)
        logger.info("[obsidian] compact_folder %s: archived %d files", folder, len(to_move))
    except Exception as e:
        logger.debug("[obsidian] compact_folder failed %s: %s", folder, e)


def write_council_verdict(question: str, verdict: str, stage1: list[dict[str, Any]] | None = None) -> bool:
    """Write a council decision to Decisions/ folder."""
    if not _enabled():
        return False
    slug = "council-" + datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M")
    q_short = question[:120].replace("\n", " ")
    opinions = ""
    if stage1:
        opinions = "\n\n## Opinions\n" + "\n".join(
            f"- **{r.get('label', r.get('provider', '?'))}**: {r.get('response', '')[:200]}"
            for r in stage1
        )
    content = f"## Question\n{q_short}\n\n## Chairman Verdict\n{verdict}{opinions}"
    return write_note("Decisions", slug, content, tags=["council", "decision"])


def write_system_health(check_name: str, result: str) -> bool:
    """Write a system check result to System/ folder."""
    return write_note("System", check_name.replace(" ", "-").lower(), result, tags=["system", "health"])


def write_daily_session(date_str: str, summary: str) -> bool:
    """Write daily digest to Sessions/ folder."""
    return write_note("Sessions", date_str, summary, tags=["session", "daily"])


def _alert(msg: str) -> None:
    try:
        from app.platform import ops_alerts

        ops_alerts._ntfy(f"[obsidian] {msg}")
    except Exception:
        pass


__all__ = [
    "write_note",
    "append_note",
    "push_to_git",
    "compact_folder",
    "write_council_verdict",
    "write_system_health",
    "write_daily_session",
]
