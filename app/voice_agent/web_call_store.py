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


def _TRANSCRIPTS_DIR() -> Path:
    """Training transcript dir — resolved per call, never frozen at import."""
    from app.platform.runtime_recording_paths import call_transcripts_dir

    return call_transcripts_dir()


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _valid_lead(lead_key: str | None) -> str | None:
    k = (lead_key or "").strip()
    return k if k and _LEAD_RE.match(k) else None


def _valid_sid(session_id: str | None) -> str | None:
    s = (session_id or "").strip()
    return s if s and _SID_RE.match(s) else None


def _turns_to_messages(turns: list[Any] | None) -> list[dict[str, str]]:
    """Web-call turns {role,text} → vobiz-style {role,content} for training."""
    msgs: list[dict[str, str]] = []
    for t in turns or []:
        if not isinstance(t, dict):
            continue
        role = str(t.get("role") or "user").lower()
        if role not in ("user", "assistant"):
            role = "assistant" if role in ("bot", "swara", "agent") else "user"
        content = str(t.get("text") or t.get("content") or "").strip()
        if content:
            msgs.append({"role": role, "content": content[:2000]})
    return msgs


def _training_transcript_exists(session_id: str) -> bool:
    """Dedupe — same web session do baar training me na aaye."""
    sid = (session_id or "").strip()
    if not sid or not _TRANSCRIPTS_DIR().is_dir():
        return False
    try:
        files = sorted(
            _TRANSCRIPTS_DIR().glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True
        )
        for fp in files[:21]:
            with open(fp, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except Exception:
                        continue
                    if str(rec.get("stream_sid") or "") == sid:
                        return True
                    if str(rec.get("session_id") or "") == sid:
                        return True
    except Exception:
        return False
    return False


def mirror_session_to_training_transcript(row: dict[str, Any]) -> bool:
    """Web test-call → data/call_transcripts/YYYY-MM-DD.jsonl (Meera/voice_learn fuel).

    Same shape as vobiz_stream._persist_transcript so training scripts pick it up.
    Never raises.
    """
    try:
        sid = str(row.get("session_id") or "").strip()
        if not sid or _training_transcript_exists(sid):
            return False
        messages = _turns_to_messages(row.get("turns"))
        if not messages:
            return False
        ended = str(row.get("ended_at") or _now_iso())
        day = ended[:10] if len(ended) >= 10 else datetime.now(timezone.utc).strftime("%Y-%m-%d")
        user_turns = sum(1 for m in messages if m.get("role") == "user")
        rec = {
            "ts": ended,
            "started_at": row.get("started_at") or ended,
            "duration_s": float(row.get("duration_s") or 0),
            "stream_sid": sid,
            "session_id": sid,
            "niche": row.get("niche") or "general",
            "client_id": None,
            "client_name": row.get("client_name") or "Demo Co",
            "voice": "hi-IN-SwaraNeural",
            "user_turns": user_turns,
            "stt_counts": {"web_call": user_turns},
            "messages": messages,
            "source": "web_call_test",
            "flow": row.get("flow") or "qualify",
            "lead_key": row.get("lead_key"),
        }
        _TRANSCRIPTS_DIR().mkdir(parents=True, exist_ok=True)
        out = _TRANSCRIPTS_DIR() / f"{day}.jsonl"
        with _LOCK:
            with open(out, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return True
    except Exception:
        return False


def backfill_training_transcripts(*, limit: int = 200) -> dict[str, int]:
    """Existing web_call_sessions.jsonl → call_transcripts (one-time / repair)."""
    scanned = mirrored = skipped = 0
    if not _STORE.is_file():
        return {"scanned": 0, "mirrored": 0, "skipped": 0}
    limit = max(1, min(int(limit or 200), 2000))
    try:
        with _LOCK:
            lines = _STORE.read_text(encoding="utf-8", errors="ignore").splitlines()
        for line in lines[-limit:]:
            line = line.strip()
            if not line:
                continue
            scanned += 1
            try:
                row = json.loads(line)
            except Exception:
                skipped += 1
                continue
            if mirror_session_to_training_transcript(row):
                mirrored += 1
            else:
                skipped += 1
    except Exception:
        pass
    return {"scanned": scanned, "mirrored": mirrored, "skipped": skipped}


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
        mirror_session_to_training_transcript(row)
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


def list_all_sessions(
    *,
    limit: int = 50,
    include_turns: bool = False,
) -> list[dict[str, Any]]:
    """ADMIN-wide: newest-first sessions across ALL browser lead_keys.

    Unlike list_sessions() this is NOT filtered by lead_key — it is the
    admin cockpit view of every saved web test-call. Never raises.
    """
    if not _STORE.is_file():
        return []
    limit = max(1, min(int(limit or 50), 200))
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
                    rows.append(row)
    except Exception:
        return []
    rows.sort(key=lambda r: str(r.get("started_at") or ""), reverse=True)
    out: list[dict[str, Any]] = []
    for r in rows[:limit]:
        item = {
            "session_id": r.get("session_id"),
            "lead_key": r.get("lead_key"),
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


def count_sessions() -> int:
    """Total saved web test-call sessions (cheap line count). Never raises."""
    if not _STORE.is_file():
        return 0
    try:
        with _LOCK:
            return sum(
                1
                for ln in _STORE.read_text(encoding="utf-8", errors="ignore").splitlines()
                if ln.strip()
            )
    except Exception:
        return 0


def get_session_any(session_id: str) -> dict[str, Any] | None:
    """ADMIN: fetch one session by id WITHOUT lead_key match (last row wins)."""
    sid = _valid_sid(session_id)
    if not sid or not _STORE.is_file():
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
                    if row.get("session_id") == sid:
                        found = row
    except Exception:
        return None
    return found


def normalize_lead_key(lead_key: str | None) -> str | None:
    return _valid_lead(lead_key)


def normalize_session_id(session_id: str | None) -> str | None:
    return _valid_sid(session_id)
