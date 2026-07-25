"""Tenant-scoped generation-attempt budget (append-only events)."""

from __future__ import annotations

import datetime as _dt
import json
import os
import threading
from typing import Any

_LOCK = threading.Lock()
_DEFAULT = os.path.join("data", "creative_os", "budget")


def _root() -> str:
    return os.getenv("CREATIVE_BUDGET_ROOT", _DEFAULT)


def _day() -> str:
    return _dt.datetime.utcnow().strftime("%Y-%m-%d")


def _path(tenant_id: str) -> str:
    safe = "".join(c for c in (tenant_id or "") if c.isalnum() or c in "-_")[:60]
    return os.path.join(_root(), safe or "_invalid", f"{_day()}.jsonl")


def record_attempt(
    tenant_id: str,
    *,
    creative_id: str,
    kind: str,
    revision: int = 0,
) -> dict[str, Any]:
    """Append one generation/regeneration attempt. Never raises."""
    try:
        tid = (tenant_id or "").strip()
        if not tid:
            return {"ok": False, "error": "tenant_id required"}
        if kind not in ("initial", "regeneration", "fallback"):
            return {"ok": False, "error": "invalid_kind"}
        fp = _path(tid)
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        row = {
            "ts": _dt.datetime.utcnow().isoformat() + "Z",
            "tenant_id": tid,
            "creative_id": creative_id,
            "kind": kind,
            "revision": int(revision or 0),
            "day": _day(),
        }
        line = json.dumps(row, ensure_ascii=False) + "\n"
        with _LOCK:
            with open(fp, "a", encoding="utf-8") as f:
                f.write(line)
                f.flush()
                os.fsync(f.fileno())
        return {"ok": True, "count": count_attempts_today(tid)}
    except Exception as e:
        return {"ok": False, "error": str(e)[:160]}


def count_attempts_today(tenant_id: str) -> int:
    try:
        fp = _path(tenant_id)
        if not os.path.isfile(fp):
            return 0
        n = 0
        with open(fp, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    n += 1
        return n
    except Exception:
        return 0


__all__ = ["count_attempts_today", "record_attempt"]
