"""Web-call test sessions — durable transcript log (jsonl, import-safe).

Each browser `lead_key` gets a stable identity for agent_memory recall
(`web:{lead_key}`) and a chronological call history with ISO timestamps.
Never raises.
"""

from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_STORE = Path("data") / "web_call_sessions.jsonl"
_LOCK = threading.Lock()
_LEAD_RE = re.compile(r"^[a-zA-Z0-9_-]{8,64}$")
_SID_RE = re.compile(r"^[a-zA-Z0-9_-]{8,64}$")


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _valid_lead(lead_key: str | None) -> str | None:
    k = (lead_key or "").strip()
    return k if k and _LEAD_RE.match(k) else None


def _valid_sid(session_id: str | None) -> str | None:
    s = (session_id or "").strip()
    return s if s and _SID_RE.match(s) else None


def append_session(record: dict[str, Any]) -> bool:
    """Append one completed session. Returns False on validation/IO error."""
    try:
        sid = _valid_sid(record.get("session_id"))
        lead = _valid_lead(record.get("lead_key"))
        if not sid or not lead:
            return False
        row = {
            "session_id": sid,
            "lead_key": lead,
            "started_at": str(record.get("started_at") or _now_iso()),
            "ended_at": str(record.get("ended_at") or _now_iso()),
            "duration_s": int(record.get("duration_s") or 0),
            "niche": str(record.get("niche") or "general")[:64],
            "flow": str(record.get("flow") or "qualify")[:32],
            "client_name": str(record.get("client_name") or "Demo Co")[:80],
            "source": "web_call_test",
            "memory_subject": str(record.get("memory_subject") or f"web:{lead}")[:96],
            "turns": list(record.get("turns") or [])[:200],
            "turn_count": int(record.get("turn_count") or len(record.get("turns") or [])),
        }
        _STORE.parent.mkdir(parents=True, exist_ok=True)
        with _LOCK:
            with open(_STORE, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return True
    except Exception:
        return False


def list_sessions(
    lead_key: str,
    *,
    limit: int = 30,
    include_turns: bool = False,
) -> list[dict[str, Any]]:
    """Newest-first sessions for one browser lead_key."""
    lead = _valid_lead(lead_key)
    if not lead or not _STORE.is_file():
        return []
    limit = max(1, min(int(limit or 30), 50))
    rows: list[dict[str, Any]] = []
    try:
        with _LOCK:
            with open(_STORE, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except Exception:
                        continue
                    if row.get("lead_key") != lead:
                        continue
                    rows.append(row)
    except Exception:
        return []
    rows.sort(key=lambda r: str(r.get("started_at") or ""), reverse=True)
    out: list[dict[str, Any]] = []
    for r in rows[:limit]:
        item = {
            "session_id": r.get("session_id"),
            "started_at": r.get("started_at"),
            "ended_at": r.get("ended_at"),
            "duration_s": r.get("duration_s"),
            "niche": r.get("niche"),
            "flow": r.get("flow"),
            "client_name": r.get("client_name"),
            "turn_count": r.get("turn_count") or len(r.get("turns") or []),
        }
        if include_turns:
            item["turns"] = r.get("turns") or []
        out.append(item)
    return out


def get_session(session_id: str, lead_key: str) -> dict[str, Any] | None:
    """Fetch one session if it belongs to lead_key (last matching row wins)."""
    sid = _valid_sid(session_id)
    lead = _valid_lead(lead_key)
    if not sid or not lead or not _STORE.is_file():
        return None
    found: dict[str, Any] | None = None
    try:
        with _LOCK:
            with open(_STORE, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except Exception:
                        continue
                    if row.get("session_id") == sid and row.get("lead_key") == lead:
                        found = row
    except Exception:
        return None
    return found


def normalize_lead_key(lead_key: str | None) -> str | None:
    return _valid_lead(lead_key)


def normalize_session_id(session_id: str | None) -> str | None:
    return _valid_sid(session_id)
