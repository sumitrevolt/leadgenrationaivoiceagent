"""Telegram command mirror — OCC-side reader (Wave 7 Gap 2 deliverable).

The Jarvis dispatcher writes ONE line per command invocation to
``data/telegram_command_mirror.jsonl`` (append-only). This module exposes
the **reader** surface that the OCC dashboard consumes, proving:

  1. The mirror file IS being consumed (not just append-only dead weight).
  2. The dashboard can rebuild its "Recent owner commands" view from this
     file alone — no parallel store, no fabricated data.
  3. Owner can see real-time correlation: which command → status → result.

Hard rules (per directive):
  * Read-only over the mirror file. NEVER writes.
  * Returns explicit UNKNOWN / NOT_INSTRUMENTED when the file is missing.
  * Returns OK/EMPTY/UNAVAILABLE based on actual rows.
  * Never fabricates counts — if the file is empty, count is 0.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


MIRROR_FILENAME = "telegram_command_mirror.jsonl"


@dataclass
class MirrorRow:
    """One parsed row from the mirror file."""

    command: str
    status: str  # "OK" | "EMPTY" | "UNAVAILABLE" | "NOT_INSTRUMENTED" | "BLOCKED" | "command"
    fetched_at: str
    elapsed_ms: float
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "status": self.status,
            "fetched_at": self.fetched_at,
            "elapsed_ms": self.elapsed_ms,
            "data": self.data,
        }


def _mirror_path() -> Path:
    """Resolve the mirror file location.

    Order of precedence (mirror file may live under any of):
      1. ``$TELEGRAM_COMMAND_MIRROR_PATH`` (env override)
      2. ``<repo>/data/telegram_command_mirror.jsonl``
      3. ``<cwd>/data/telegram_command_mirror.jsonl``
    """
    env = os.getenv("TELEGRAM_COMMAND_MIRROR_PATH")
    if env:
        return Path(env)
    repo_data = Path(__file__).resolve().parents[2] / "data" / MIRROR_FILENAME
    if repo_data.parent.is_dir():
        return repo_data
    cwd_data = Path.cwd() / "data" / MIRROR_FILENAME
    return cwd_data


def read_recent(limit: int = 50) -> list[MirrorRow]:
    """Read up to ``limit`` most-recent rows from the mirror file.

    Returns an empty list if the file is missing or unreadable. Per §3
    directive: missing data is NEVER treated as healthy / fabricated.
    """
    path = _mirror_path()
    if not path.is_file():
        return []
    rows: list[MirrorRow] = []
    try:
        # Read all, then tail — the file is append-only, last N are most recent.
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except Exception:
                    continue
                rows.append(
                    MirrorRow(
                        command=str(payload.get("command", "")),
                        status=str(payload.get("status", "UNKNOWN")),
                        fetched_at=str(payload.get("fetched_at", "")),
                        elapsed_ms=float(payload.get("elapsed_ms", 0.0) or 0.0),
                        data=dict(payload.get("data") or {}),
                    )
                )
    except Exception as exc:
        logger.debug("read_recent(%s) failed: %s", path, type(exc).__name__)
        return []
    return rows[-limit:]


def command_count_by_status() -> dict[str, int]:
    """Aggregate counts grouped by status across the mirror file.

    Returns ONLY the statuses that actually appear. An empty file returns
    an empty dict (NOT ``{"OK": 0}`` — fabrication is forbidden).
    """
    rows = read_recent(limit=10_000)
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.status] = counts.get(row.status, 0) + 1
    return counts


def latest_for_command(cmd: str, limit: int = 5) -> list[MirrorRow]:
    """Last ``limit`` mirror rows for one specific command."""
    cmd_norm = cmd.lower().strip()
    rows = [r for r in read_recent(limit=10_000) if r.command.lower().strip() == cmd_norm]
    return rows[-limit:]


def summary() -> dict[str, Any]:
    """Build an OCC-card summary of the mirror file state.

    The summary is the structured JSON the dashboard can ingest directly.
    """
    rows = read_recent(limit=10_000)
    counts = command_count_by_status()
    fetched_at = _now_iso()

    if not rows:
        return {
            "kind": "telegram_command_mirror_summary",
            "status": "NOT_INSTRUMENTED",
            "fetched_at": fetched_at,
            "total_rows": 0,
            "command_count_by_status": {},
            "latest_commands": [],
            "note": (
                "Mirror file empty or missing. The Jarvis dispatcher writes here on "
                "every command invocation. When the dispatcher is not running (no "
                "live Telegram token), this file will stay empty until commands are "
                "actually issued. NO fabrication — empty = NOT_INSTRUMENTED."
            ),
        }

    latest = rows[-10:]
    return {
        "kind": "telegram_command_mirror_summary",
        "status": "OK",
        "fetched_at": fetched_at,
        "total_rows": len(rows),
        "command_count_by_status": counts,
        "unique_commands": sorted({r.command for r in rows}),
        "latest_commands": [r.to_dict() for r in latest],
        "latest_fetched_at": latest[-1].fetched_at if latest else None,
    }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


__all__ = [
    "MirrorRow",
    "MIRROR_FILENAME",
    "read_recent",
    "command_count_by_status",
    "latest_for_command",
    "summary",
]