"""Agent Runtime distributed cancellation store — Redis-backed, run-specific.

WHY (2026-07-22): process-local ``_CANCELLED_AGENTS`` cannot cross API↔worker
boundaries. This store is the sole authority for runtime-run cancellation.

Namespace: ``agentrt:cancel:<agent_id>:<runtime_run_id>``
TTL: ``AGENT_RUNTIME_CANCEL_TTL_S`` (default 3600).

Production: Redis only (no silent memory fallback).
Tests may set ``AGENT_RUNTIME_CANCEL_BACKEND=memory|file`` explicitly.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

SCHEMA_VERSION = 1
KEY_PREFIX = "agentrt:cancel:"
DEFAULT_TTL_S = int(os.environ.get("AGENT_RUNTIME_CANCEL_TTL_S", "3600") or "3600")
MAX_REASON_LEN = 200

_BACKEND_ENV = "AGENT_RUNTIME_CANCEL_BACKEND"
_FILE_ENV = "AGENT_RUNTIME_CANCEL_FILE"

# Injectable Redis client factory (tests monkeypatch this).
_redis_factory: Any = None

_MEM: dict[str, tuple[str, float]] = {}
_MEM_LOCK = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canon_agent(agent_id: str) -> str:
    return str(agent_id or "").strip().lower()


def _canon_run(runtime_run_id: str) -> str:
    rid = str(runtime_run_id or "").strip()
    if not rid or len(rid) > 80 or any(c in rid for c in ("/", "\\", "*", "?", "\n", "\r", " ")):
        return ""
    return rid


def cancel_key(agent_id: str, runtime_run_id: str) -> str | None:
    aid = _canon_agent(agent_id)
    rid = _canon_run(runtime_run_id)
    if not aid or not rid:
        return None
    return f"{KEY_PREFIX}{aid}:{rid}"


def _resolve_backend() -> str:
    raw = (os.getenv(_BACKEND_ENV) or "").strip().lower()
    if raw in ("memory", "file", "redis"):
        return raw
    try:
        from app.config import settings

        if str(getattr(settings, "app_env", "") or "").lower() == "production":
            return "redis"
    except Exception:
        pass
    return "redis"


def backend_status() -> dict[str, Any]:
    """Read-only durability projection — no credentials."""
    backend = _resolve_backend()
    fallback = backend != "redis"
    db_label = "unset"
    try:
        from app.config import settings

        url = str(getattr(settings, "redis_url", "") or os.getenv("REDIS_URL") or "")
        if "/" in url.rsplit("@", 1)[-1]:
            tail = url.rsplit("/", 1)[-1]
            if tail.isdigit():
                db_label = f"db{tail}"
            else:
                db_label = "url-present"
        elif url:
            db_label = "url-present"
    except Exception:
        db_label = "unknown"
    return {
        "cancellation_backend": backend,
        "fallback_active": bool(fallback),
        "redis_database": db_label,
        "key_prefix": KEY_PREFIX,
        "default_ttl_s": DEFAULT_TTL_S,
        "schema_version": SCHEMA_VERSION,
    }


def _sync_redis():
    if _redis_factory is not None:
        return _redis_factory()
    import redis

    from app.config import settings

    url = (
        getattr(settings, "redis_url", None) or os.getenv("REDIS_URL") or "redis://localhost:6379/0"
    )
    return redis.Redis.from_url(url, socket_timeout=2, decode_responses=True)


@dataclass
class CancelCheck:
    status: str  # not_requested | cancel_requested | expired | malformed | store_unavailable
    record: dict[str, Any] | None = None
    reason_code: str = ""

    @property
    def requested(self) -> bool:
        return self.status == "cancel_requested"


def _parse_record(raw: Any) -> CancelCheck:
    if raw is None:
        return CancelCheck(status="not_requested")
    try:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        if isinstance(raw, str):
            data = json.loads(raw)
        elif isinstance(raw, dict):
            data = raw
        else:
            return CancelCheck(status="malformed", reason_code="malformed_cancel_record")
        if not isinstance(data, dict):
            return CancelCheck(status="malformed", reason_code="malformed_cancel_record")
        if int(data.get("schema_version") or 0) != SCHEMA_VERSION:
            return CancelCheck(
                status="malformed", reason_code="cancel_schema_mismatch", record=data
            )
        exp = str(data.get("expires_at") or "")
        if exp:
            try:
                exp_dt = datetime.fromisoformat(exp.replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                if exp_dt.tzinfo is None:
                    exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                if exp_dt <= now:
                    return CancelCheck(status="expired", record=data, reason_code="cancel_expired")
            except Exception:
                pass
        return CancelCheck(status="cancel_requested", record=data, reason_code="cancel_requested")
    except Exception:
        return CancelCheck(status="malformed", reason_code="malformed_cancel_record")


def _file_path() -> str:
    return (os.getenv(_FILE_ENV) or "").strip() or os.path.join("data", "agentrt_cancel_store.json")


def _file_load() -> dict[str, Any]:
    path = _file_path()
    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f) or {}
    except Exception:
        pass
    return {}


def _file_save(data: dict[str, Any]) -> None:
    path = _file_path()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = f"{path}.tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


def request(
    agent_id: str,
    runtime_run_id: str,
    *,
    requested_by: str = "owner",
    reason: str = "",
    command_id: str = "",
    correlation_id: str = "",
    tenant_id: str | None = None,
    ttl_s: int | None = None,
) -> dict[str, Any]:
    """Persist a run-specific cancellation. Idempotent on same key."""
    key = cancel_key(agent_id, runtime_run_id)
    if not key:
        return {"ok": False, "error": "malformed_target", "reason_code": "malformed_target"}
    ttl = max(30, min(int(ttl_s or DEFAULT_TTL_S), 86400))
    now = time.time()
    rec = {
        "schema_version": SCHEMA_VERSION,
        "agent_id": _canon_agent(agent_id),
        "runtime_run_id": _canon_run(runtime_run_id),
        "command_id": str(command_id or "")[:64],
        "requested_by": str(requested_by or "owner")[:80],
        "reason": str(reason or "")[:MAX_REASON_LEN],
        "requested_at": _now_iso(),
        "expires_at": datetime.fromtimestamp(now + ttl, tz=timezone.utc).isoformat(),
        "correlation_id": str(correlation_id or "")[:64],
        "tenant_id": (str(tenant_id)[:80] if tenant_id else None),
    }
    payload = json.dumps(rec, ensure_ascii=False)
    backend = _resolve_backend()
    try:
        if backend == "memory":
            with _MEM_LOCK:
                existed = key in _MEM and _MEM[key][1] > now
                _MEM[key] = (payload, now + ttl)
            return {
                "ok": True,
                "status": "cancel_requested",
                "newly_created": not existed,
                "already_requested": existed,
                "key": key,
                "record": rec,
                "cancellation_backend": "memory",
                "fallback_active": True,
            }
        if backend == "file":
            data = _file_load()
            existed = key in data and float(data[key].get("_exp") or 0) > now
            data[key] = {**rec, "_exp": now + ttl, "_payload": payload}
            _file_save(data)
            return {
                "ok": True,
                "status": "cancel_requested",
                "newly_created": not existed,
                "already_requested": existed,
                "key": key,
                "record": rec,
                "cancellation_backend": "file",
                "fallback_active": True,
            }
        r = _sync_redis()
        created = bool(r.set(key, payload, nx=True, ex=ttl))
        if not created:
            r.set(key, payload, ex=ttl)
        return {
            "ok": True,
            "status": "cancel_requested",
            "newly_created": created,
            "already_requested": not created,
            "key": key,
            "record": rec,
            "cancellation_backend": "redis",
            "fallback_active": False,
        }
    except Exception as e:
        logger.warning("[agent_runtime_cancellation] request failed: %s", type(e).__name__)
        return {
            "ok": False,
            "error": "cancellation_store_unavailable",
            "reason_code": "cancellation_store_unavailable",
            "detail": type(e).__name__,
            "cancellation_backend": backend,
        }


def get(agent_id: str, runtime_run_id: str) -> CancelCheck:
    key = cancel_key(agent_id, runtime_run_id)
    if not key:
        return CancelCheck(status="malformed", reason_code="malformed_target")
    backend = _resolve_backend()
    try:
        if backend == "memory":
            with _MEM_LOCK:
                row = _MEM.get(key)
            if not row:
                return CancelCheck(status="not_requested")
            payload, exp = row
            if exp <= time.time():
                with _MEM_LOCK:
                    _MEM.pop(key, None)
                return CancelCheck(status="expired", reason_code="cancel_expired")
            return _parse_record(payload)
        if backend == "file":
            data = _file_load()
            row = data.get(key)
            if not row:
                return CancelCheck(status="not_requested")
            if float(row.get("_exp") or 0) <= time.time():
                data.pop(key, None)
                _file_save(data)
                return CancelCheck(status="expired", record=row, reason_code="cancel_expired")
            return _parse_record(row.get("_payload") or row)
        raw = _sync_redis().get(key)
        return _parse_record(raw)
    except Exception as e:
        logger.warning("[agent_runtime_cancellation] get failed: %s", type(e).__name__)
        return CancelCheck(status="store_unavailable", reason_code="cancellation_store_unavailable")


def is_requested(agent_id: str, runtime_run_id: str) -> CancelCheck:
    return get(agent_id, runtime_run_id)


def clear(agent_id: str, runtime_run_id: str) -> dict[str, Any]:
    key = cancel_key(agent_id, runtime_run_id)
    if not key:
        return {"ok": False, "error": "malformed_target"}
    backend = _resolve_backend()
    try:
        if backend == "memory":
            with _MEM_LOCK:
                existed = key in _MEM
                _MEM.pop(key, None)
            return {"ok": True, "cleared": existed, "key": key}
        if backend == "file":
            data = _file_load()
            existed = key in data
            data.pop(key, None)
            _file_save(data)
            return {"ok": True, "cleared": existed, "key": key}
        n = int(_sync_redis().delete(key) or 0)
        return {"ok": True, "cleared": n > 0, "key": key}
    except Exception as e:
        return {
            "ok": False,
            "error": "cancellation_store_unavailable",
            "reason_code": "cancellation_store_unavailable",
            "detail": type(e).__name__,
        }


def reset_memory_for_tests() -> None:
    with _MEM_LOCK:
        _MEM.clear()


__all__ = [
    "SCHEMA_VERSION",
    "KEY_PREFIX",
    "CancelCheck",
    "backend_status",
    "cancel_key",
    "request",
    "get",
    "is_requested",
    "clear",
    "reset_memory_for_tests",
]
