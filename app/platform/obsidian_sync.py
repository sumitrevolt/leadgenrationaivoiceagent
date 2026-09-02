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
    """git add -A + commit + push. 60s timeout. Alerts ops on failure. Never raises.

    NOTE: in production the worker/scheduler container has NO git binary and NO
    SSH deploy key — the actual nightly push is owned by the HOST cron
    (scripts/obsidian_host_push.sh @ 20:45 UTC). So if git is unavailable we skip
    SILENTLY (no ops alert) rather than failing every night. This stays useful for
    any environment where the runtime does have git+SSH."""
    if not _enabled():
        return False
    if not _VAULT.exists():
        logger.debug("[obsidian] vault dir missing — skip push")
        return False
    import shutil

    if shutil.which("git") is None:
        logger.debug("[obsidian] no git in runtime — host cron owns the push, skip")
        return False
    try:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        cmds = [
            ["git", "-C", str(_VAULT), "add", "-A"],
            [
                "git",
                "-C",
                str(_VAULT),
                "commit",
                "--allow-empty",
                "-m",
                f"brain: nightly sync {date_str}",
            ],
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


def write_council_verdict(
    question: str, verdict: str, stage1: list[dict[str, Any]] | None = None
) -> bool:
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
    return write_note(
        "System", check_name.replace(" ", "-").lower(), result, tags=["system", "health"]
    )


def write_daily_session(date_str: str, summary: str) -> bool:
    """Write daily digest to Sessions/ folder."""
    return write_note("Sessions", date_str, summary, tags=["session", "daily"])


def _alert(msg: str) -> None:
    try:
        from app.platform import ops_alerts

        ops_alerts._ntfy(f"[obsidian] {msg}")
    except Exception:
        pass


def recall(query: str, k: int = 3) -> list[dict]:
    """Search vault notes by query-word overlap. Returns top-k matching notes.

    Each result: {folder, slug, excerpt, updated, score}
    Never raises. Skips root-level files (only subfolder notes).
    Max 2000 files scanned to prevent OOM.
    """
    if not _enabled():
        return []
    try:
        if not _VAULT.exists():
            return []
        # Tokenize query — skip short words
        words = [w.lower() for w in query.split() if len(w) >= 3]
        if not words:
            return []

        results: list[dict] = []
        scanned = 0
        for path in _VAULT.rglob("*.md"):
            if scanned >= 2000:
                break
            # Skip root-level files — only include files inside subfolders
            if path.parent == _VAULT:
                continue
            scanned += 1
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
                text_lower = text.lower()
                score = sum(1 for w in words if w in text_lower)
                if score == 0:
                    continue
                # Strip frontmatter for excerpt
                body = text
                if text.startswith("---"):
                    end = text.find("---", 3)
                    if end != -1:
                        body = text[end + 3 :].lstrip()
                excerpt = body[:300].replace("\n", " ").strip()
                stat = path.stat()
                updated = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).strftime(
                    "%Y-%m-%d %H:%M UTC"
                )
                results.append(
                    {
                        "folder": path.parent.name,
                        "slug": path.stem,
                        "excerpt": excerpt,
                        "updated": updated,
                        "score": score,
                    }
                )
            except Exception as e:
                logger.debug("[obsidian] recall skip %s: %s", path, e)
                continue

        # Sort: score desc, then mtime DESC (newest-first within a score tie). `updated`
        # is "%Y-%m-%d %H:%M UTC" (fixed-width => lexicographic == chronological). Sort by
        # updated desc first, then a STABLE sort by score desc preserves updated-desc
        # within ties (the old code sorted updated ASC, so newest was truncated away).
        results.sort(key=lambda r: r["updated"], reverse=True)
        results.sort(key=lambda r: -r["score"])
        return results[:k]
    except Exception as e:
        logger.debug("[obsidian] recall failed for %r: %s", query, e)
        return []


def brain_context(query: str, k: int = 3) -> str:
    """Return formatted brain context string for agent prompts.

    Calls recall(query, k) and formats results as:
      ## Brain Context (past decisions):
      - [Folder/slug | updated] excerpt...

    Returns "" when no results. Max 1200 chars total. Never raises.
    """
    try:
        notes = recall(query, k)
        if not notes:
            return ""
        header = "## Brain Context (past decisions):\n"
        bullets = []
        for n in notes:
            line = f"- [{n['folder']}/{n['slug']} | {n['updated']}] {n['excerpt'][:200]}"
            bullets.append(line)
        body = header + "\n".join(bullets)
        if len(body) > 1200:
            body = body[:1197] + "..."
        return body
    except Exception as e:
        logger.debug("[obsidian] brain_context failed for %r: %s", query, e)
        return ""


__all__ = [
    "write_note",
    "append_note",
    "push_to_git",
    "compact_folder",
    "write_council_verdict",
    "write_system_health",
    "write_daily_session",
    "recall",
    "brain_context",
]
