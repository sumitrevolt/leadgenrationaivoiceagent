"""Owner feed event store — append-only JSONL (T-02 of OWNER_TELEGRAM_FEED_DESIGN.md).

WHY THIS EXISTS
---------------
The owner asked that desktop workers, bots and the 31 agents all be visible in
Telegram. Before any egress (T-01) can exist, there must be one append-only,
schema-validated event log every source writes to. This module is that store.
It is deliberately **stdlib-only** so it can be imported and tested without the
repo `.venv` (which is currently missing — see COORDINATION_BROADCAST.md §5).

DESIGN RULES (non-negotiable)
-----------------------------
1. **Never raises.** A telemetry store must never take down a worker. Every
   public function returns a bool / empty result on failure.
2. **Fail-closed on truth.** `verified=True` is only honoured for trusted
   sources. `workforce` is force-downgraded to `verified=False` until T-05
   (the probe fix) lands — see the TRUTH GATE note below.
3. **Append-only.** No update, no delete. Corrupt lines are skipped on read and
   counted, never silently dropped from the report.

TRUTH GATE — why `workforce` can never be verified today
--------------------------------------------------------
`data/workforce_live_status.json` reports `status=RUNNING_24_7_PARALLEL` and
`actions_today=592` while `active_workers=0`, `active_members=0`,
`task_execution_verified=false` and `evidence_kind=inference_probe_only`.
Piping that to the owner would be false confidence. Until T-05 makes the probe
honest, every `workforce` event is written with `verified=false`.

Schema (one JSON object per line):
    ts        ISO-8601 UTC timestamp (auto-filled if omitted)
    source    str  — e.g. workbuddy / openclaw / hermes / prod / bot_fleet
    actor     str  — e.g. nova / hermes-gui / bot:sales
    severity  "P0" | "P1" | "info"
    kind      task_claimed | ack | blocked | done | incident | heartbeat
    text      str  — human-readable, Hinglish OK
    evidence  str  — file path / pid / url. Empty string if none.
    verified  bool — did we actually observe this, or only infer it?
    dedupe_key  optional str — suppresses repeat events within lookback window
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from app.utils.file_lock import locked_append

_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FEED_PATH = _REPO_ROOT / "data" / "owner_feed_events.jsonl"

SEVERITIES = ("P0", "P1", "info")
KINDS = ("task_claimed", "ack", "blocked", "done", "incident", "heartbeat")

REQUIRED_FIELDS = ("ts", "source", "actor", "severity", "kind", "text", "evidence", "verified")

MAX_TEXT_CHARS = 1000
MAX_EVIDENCE_CHARS = 500

# Sources allowed to self-declare `verified=True`. Override with env
# OWNER_FEED_TRUSTED_SOURCES (comma-separated). Default is intentionally small.
DEFAULT_TRUSTED_SOURCES = frozenset({"hermes", "prod", "guardian", "workbuddy", "openclaw"})

# Force-downgraded to verified=False regardless of input, until T-05 lands.
# See the TRUTH GATE note in this module's docstring. Remove only with owner
# sign-off after `task_execution_verified` becomes genuinely true.
FORCE_UNVERIFIED_SOURCES = frozenset({"workforce"})

_DEDUPE_LOOKBACK = 200


def feed_path(path: str | os.PathLike | None = None) -> Path:
    """Resolve the feed path: explicit arg > env OWNER_FEED_PATH > repo default."""
    if path:
        return Path(path)
    env = os.getenv("OWNER_FEED_PATH", "").strip()
    return Path(env) if env else DEFAULT_FEED_PATH


def _trusted_sources() -> frozenset[str]:
    raw = os.getenv("OWNER_FEED_TRUSTED_SOURCES", "").strip()
    if not raw:
        return DEFAULT_TRUSTED_SOURCES
    return frozenset(part.strip().lower() for part in raw.split(",") if part.strip())


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _validate(event: dict[str, Any]) -> tuple[bool, str]:
    """Return (ok, reason). Pure function — no I/O, no side effects."""
    for field in REQUIRED_FIELDS:
        if field not in event:
            return False, f"missing_field:{field}"
    if not isinstance(event["source"], str) or not event["source"].strip():
        return False, "bad_source"
    if not isinstance(event["actor"], str) or not event["actor"].strip():
        return False, "bad_actor"
    if event["severity"] not in SEVERITIES:
        return False, f"bad_severity:{event['severity']}"
    if event["kind"] not in KINDS:
        return False, f"bad_kind:{event['kind']}"
    if not isinstance(event["text"], str) or not event["text"].strip():
        return False, "empty_text"
    if len(event["text"]) > MAX_TEXT_CHARS:
        return False, "text_too_long"
    if not isinstance(event["evidence"], str) or len(event["evidence"]) > MAX_EVIDENCE_CHARS:
        return False, "bad_evidence"
    if not isinstance(event["verified"], bool):
        return False, "verified_not_bool"
    return True, ""


def build_event(
    *,
    source: str,
    actor: str,
    text: str,
    severity: str = "info",
    kind: str = "heartbeat",
    evidence: str = "",
    verified: bool = False,
    ts: str | None = None,
    dedupe_key: str | None = None,
) -> dict[str, Any]:
    """Build a schema-correct event, applying the fail-closed truth gate.

    `verified=True` is downgraded to False when the source is not trusted, or
    when the source is in FORCE_UNVERIFIED_SOURCES (currently: workforce).
    """
    src = str(source or "").strip().lower()
    trusted = _trusted_sources()
    if src in FORCE_UNVERIFIED_SOURCES or src not in trusted:
        verified = False

    event: dict[str, Any] = {
        "ts": ts or _utc_now(),
        "source": src,
        "actor": str(actor or "").strip(),
        "severity": severity,
        "kind": kind,
        "text": str(text or "").strip(),
        "evidence": str(evidence or ""),
        "verified": bool(verified),
    }
    if dedupe_key:
        event["dedupe_key"] = str(dedupe_key)
    return event


def _recent_dedupe_keys(path: Path, lookback: int = _DEDUPE_LOOKBACK) -> set[str]:
    """Best-effort scan of the tail for dedupe keys. Never raises."""
    keys: set[str] = set()
    try:
        if not path.exists():
            return keys
        with open(path, encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()[-lookback:]
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except (ValueError, TypeError):
                continue
            if isinstance(obj, dict) and isinstance(obj.get("dedupe_key"), str):
                keys.add(obj["dedupe_key"])
    except OSError:
        pass
    return keys


def append_event(event: dict[str, Any], path: str | os.PathLike | None = None) -> bool:
    """Validate + append one event. **Never raises.** Returns True if written."""
    try:
        ok, _reason = _validate(event)
        if not ok:
            return False
        target = feed_path(path)
        key = event.get("dedupe_key")
        if isinstance(key, str) and key:
            if key in _recent_dedupe_keys(target):
                return False
        line = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
        return locked_append(str(target), line)
    except Exception:
        return False


def emit(
    *,
    source: str,
    actor: str,
    text: str,
    severity: str = "info",
    kind: str = "heartbeat",
    evidence: str = "",
    verified: bool = False,
    dedupe_key: str | None = None,
    path: str | os.PathLike | None = None,
) -> bool:
    """Convenience: build + append in one call. Never raises."""
    return append_event(
        build_event(
            source=source,
            actor=actor,
            text=text,
            severity=severity,
            kind=kind,
            evidence=evidence,
            verified=verified,
            dedupe_key=dedupe_key,
        ),
        path=path,
    )


def read_events(
    path: str | os.PathLike | None = None, limit: int | None = None
) -> tuple[list[dict[str, Any]], int]:
    """Read back events. Returns (events, corrupt_line_count). Never raises.

    `limit` keeps the **most recent** N events.
    """
    events: list[dict[str, Any]] = []
    corrupt = 0
    try:
        target = feed_path(path)
        if not target.exists():
            return [], 0
        with open(target, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except (ValueError, TypeError):
                    corrupt += 1
                    continue
                if isinstance(obj, dict):
                    events.append(obj)
                else:
                    corrupt += 1
    except OSError:
        return [], corrupt
    if limit is not None and limit >= 0:
        events = events[-limit:]
    return events, corrupt


def iter_events(path: str | os.PathLike | None = None) -> Iterable[dict[str, Any]]:
    """Stream events (memory-safe for large files). Never raises."""
    events, _corrupt = read_events(path)
    yield from events


__all__ = [
    "SEVERITIES",
    "KINDS",
    "REQUIRED_FIELDS",
    "append_event",
    "build_event",
    "emit",
    "feed_path",
    "read_events",
    "iter_events",
]
