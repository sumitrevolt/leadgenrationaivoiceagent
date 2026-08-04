"""Append-only Coordination Hub events + tool presence projection.

Not a mission ledger / STAFF registry — presence only for Hub dashboard.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Module-level path literals — runtime-data scanner + allowlist bind here.
_ROOT = "data/coordination_hub"
_EVENTS = "data/coordination_hub/events.jsonl"
_PRESENCE = "data/coordination_hub/presence.json"
_PRESENCE_TMP = "data/coordination_hub/presence.json.tmp"
_MAX_EVENT_BYTES = 4000
_MAX_TAIL = 200


def append_event(
    *,
    tool_id: str,
    event_type: str,
    payload: dict[str, Any] | None = None,
    nonce_fp: str = "",
    body_sha256: str = "",
) -> dict[str, Any]:
    """Append one provenanced event. Never raises; never stores secrets."""
    out: dict[str, Any] = {"ok": False}
    try:
        safe_payload = _sanitize_payload(payload or {})
        row = {
            "ts": int(time.time()),
            "tool_id": str(tool_id or "")[:32],
            "event_type": str(event_type or "")[:64],
            "nonce_fp": str(nonce_fp or "")[:64],
            "payload_sha": str(body_sha256 or "")[:64],
            "payload": safe_payload,
            "provenance": "coordination_hub",
        }
        os.makedirs(_ROOT, exist_ok=True)
        line = json.dumps(row, ensure_ascii=False, separators=(",", ":"))
        if len(line.encode("utf-8")) > _MAX_EVENT_BYTES:
            row["payload"] = {"truncated": True}
            line = json.dumps(row, ensure_ascii=False, separators=(",", ":"))
        with open(_EVENTS, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        out["ok"] = True
        out["ts"] = row["ts"]
        return out
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("[coord_hub_events] append skip: %s", e)
        out["error"] = str(e)[:120]
        return out


def list_events(limit: int = 50) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit or 50), _MAX_TAIL))
    if not os.path.isfile(_EVENTS):
        return []
    try:
        with open(_EVENTS, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return []
    rows: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def update_presence(
    *,
    tool_id: str,
    status: str = "online",
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Upsert tool presence projection. Not a STAFF registry write."""
    out: dict[str, Any] = {"ok": False}
    try:
        os.makedirs(_ROOT, exist_ok=True)
        data: dict[str, Any] = {}
        if os.path.isfile(_PRESENCE):
            try:
                with open(_PRESENCE, encoding="utf-8") as fh:
                    data = json.load(fh)
            except (OSError, json.JSONDecodeError):
                data = {}
        tools = data.get("tools") if isinstance(data.get("tools"), dict) else {}
        tid = str(tool_id or "").strip().lower()[:32]
        tools[tid] = {
            "tool_id": tid,
            "status": str(status or "online")[:32],
            "last_seen": int(time.time()),
            "meta": _sanitize_payload(meta or {}),
        }
        data = {"tools": tools, "updated_at": int(time.time())}
        with open(_PRESENCE_TMP, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        os.replace(_PRESENCE_TMP, _PRESENCE)
        out["ok"] = True
        out["tool"] = tools[tid]
        return out
    except Exception as e:  # pragma: no cover
        logger.debug("[coord_hub_events] presence skip: %s", e)
        out["error"] = str(e)[:120]
        return out


def list_presence() -> dict[str, Any]:
    if not os.path.isfile(_PRESENCE):
        return {"tools": {}, "updated_at": None}
    try:
        with open(_PRESENCE, encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return {"tools": {}, "updated_at": None}
        tools = data.get("tools") if isinstance(data.get("tools"), dict) else {}
        return {"tools": tools, "updated_at": data.get("updated_at")}
    except (OSError, json.JSONDecodeError):
        return {"tools": {}, "updated_at": None}


_SECRET_KEYS = frozenset(
    {
        "secret",
        "token",
        "password",
        "api_key",
        "apikey",
        "authorization",
        "admin_api_key",
        "bearer",
    }
)


def _sanitize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in list(payload.items())[:40]:
        key = str(k)[:64]
        if key.lower() in _SECRET_KEYS or "secret" in key.lower() or "token" in key.lower():
            out[key] = "[redacted]"
            continue
        if isinstance(v, str | int | float | bool) or v is None:
            s = str(v) if not isinstance(v, bool) and v is not None else v
            if isinstance(s, str) and len(s) > 500:
                out[key] = s[:500] + "…"
            else:
                out[key] = s if isinstance(s, str) else v
        else:
            out[key] = str(v)[:200]
    return out


__all__ = [
    "append_event",
    "list_events",
    "update_presence",
    "list_presence",
]
