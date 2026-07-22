"""Agent Runtime distributed idempotency store — Redis-backed, fail-closed.

WHY (2026-07-22): billing ``idempotency.seen_before_sync`` is Redis-primary with
**memory fail-open**. That allows duplicate execution across API/worker when Redis
blips, and process-local memory is invisible cross-process.

This store is the sole authority for Agent Runtime logical-submission dedupe.

Namespace: ``agentrt:idem:v1:<scope>:<agent>:<capability>:<key_hash>``
TTL: ``AGENT_RUNTIME_IDEM_TTL_S`` (default 14 days).

Production: Redis only (no silent memory fallback).
Tests may set ``AGENT_RUNTIME_IDEM_BACKEND=memory|file`` explicitly.
"""

from __future__ import annotations

import hashlib
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
KEY_PREFIX = "agentrt:idem:v1:"
DEFAULT_TTL_S = int(
    os.environ.get("AGENT_RUNTIME_IDEM_TTL_S", str(14 * 24 * 3600)) or (14 * 24 * 3600)
)
MAX_RAW_KEY_LEN = 128
MAX_CAPABILITY_LEN = 64

_BACKEND_ENV = "AGENT_RUNTIME_IDEM_BACKEND"
_FILE_ENV = "AGENT_RUNTIME_IDEM_FILE"

_redis_factory: Any = None
_MEM: dict[str, tuple[str, float]] = {}
_MEM_LOCK = threading.Lock()
_LAST_ERROR: str | None = None

TERMINAL = frozenset(
    {
        "succeeded",
        "failed",
        "cancelled",
        "cancel_requested_but_engine_completed",
        "aborted",
    }
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _set_err(msg: str | None) -> None:
    global _LAST_ERROR
    _LAST_ERROR = (msg or "")[:120] or None


def _canon_agent(agent_id: str) -> str:
    return str(agent_id or "").strip().lower()


def _canon_capability(capability: str) -> str:
    cap = str(capability or "").strip()
    if not cap or len(cap) > MAX_CAPABILITY_LEN:
        return ""
    if any(c in cap for c in ("/", "\\", "*", "?", "\n", "\r", " ")):
        return ""
    return cap


def _canon_scope(tenant_id: str | None) -> str:
    tid = str(tenant_id or "").strip()
    if not tid:
        return "platform"
    if len(tid) > 80 or any(c in tid for c in ("/", "\\", "*", "?", "\n", "\r", " ")):
        return ""
    return f"tenant:{tid}"


def _canon_raw_key(idempotency_key: str) -> str:
    raw = str(idempotency_key or "").strip()
    if not raw or len(raw) > MAX_RAW_KEY_LEN:
        return ""
    if any(c in raw for c in ("\n", "\r", "\x00")):
        return ""
    return raw


def key_hash(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:32]


def idem_key(
    agent_id: str,
    capability: str,
    idempotency_key: str,
    *,
    tenant_id: str | None = None,
) -> str | None:
    aid = _canon_agent(agent_id)
    cap = _canon_capability(capability)
    scope = _canon_scope(tenant_id)
    raw = _canon_raw_key(idempotency_key)
    if not aid or not cap or not scope or not raw:
        return None
    return f"{KEY_PREFIX}{scope}:{aid}:{cap}:{key_hash(raw)}"


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
    backend = _resolve_backend()
    db_label = "unset"
    try:
        from app.config import settings

        url = str(getattr(settings, "redis_url", "") or os.getenv("REDIS_URL") or "")
        if "/" in url.rsplit("@", 1)[-1]:
            tail = url.rsplit("/", 1)[-1]
            db_label = f"db{tail}" if tail.isdigit() else "url-present"
        elif url:
            db_label = "url-present"
    except Exception:
        db_label = "unknown"
    return {
        "idempotency_backend": backend,
        "fallback_active": backend != "redis",
        "redis_database": db_label,
        "key_prefix": KEY_PREFIX,
        "default_ttl_s": DEFAULT_TTL_S,
        "schema_version": SCHEMA_VERSION,
        "distributed_visibility": backend == "redis",
        "last_backend_error": _LAST_ERROR,
        "fail_open_on_redis_error": False,
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


def _file_path() -> str:
    return os.getenv(_FILE_ENV) or os.path.join("data", "agent_runtime_idem.json")


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


@dataclass
class ClaimResult:
    ok: bool
    claimed: bool = False
    duplicate: bool = False
    reason_code: str = ""
    record: dict[str, Any] | None = None
    redis_key: str = ""
    store_unavailable: bool = False
    backend: str = ""

    @property
    def original_status(self) -> str:
        return str((self.record or {}).get("status") or "")

    @property
    def original_run_id(self) -> str:
        return str((self.record or {}).get("runtime_run_id") or "")


def _parse(raw: str | bytes | None) -> dict[str, Any] | None:
    if raw is None:
        return None
    try:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict) or int(data.get("schema_version") or 0) != SCHEMA_VERSION:
            return None
        return data
    except Exception:
        return None


def _read(key: str) -> tuple[dict[str, Any] | None, str]:
    backend = _resolve_backend()
    now = time.time()
    try:
        if backend == "memory":
            with _MEM_LOCK:
                row = _MEM.get(key)
            if not row:
                return None, "ok"
            payload, exp = row
            if exp <= now:
                with _MEM_LOCK:
                    _MEM.pop(key, None)
                return None, "expired"
            rec = _parse(payload)
            return (rec, "ok") if rec else (None, "malformed")
        if backend == "file":
            data = _file_load()
            row = data.get(key)
            if not row:
                return None, "ok"
            if float(row.get("_exp") or 0) <= now:
                data.pop(key, None)
                _file_save(data)
                return None, "expired"
            rec = _parse(row.get("_payload") or row)
            return (rec, "ok") if rec else (None, "malformed")
        raw = _sync_redis().get(key)
        if raw is None:
            return None, "ok"
        rec = _parse(raw)
        return (rec, "ok") if rec else (None, "malformed")
    except Exception as e:
        _set_err(type(e).__name__)
        logger.warning("[agent_runtime_idempotency] read failed: %s", type(e).__name__)
        return None, "unavailable"


def _write(key: str, rec: dict[str, Any], ttl_s: int, *, nx: bool = False) -> tuple[bool, str]:
    backend = _resolve_backend()
    payload = json.dumps(rec, ensure_ascii=False)
    now = time.time()
    ttl = max(30, min(int(ttl_s), 30 * 24 * 3600))
    try:
        if backend == "memory":
            with _MEM_LOCK:
                if nx and key in _MEM and _MEM[key][1] > now:
                    return False, "exists"
                _MEM[key] = (payload, now + ttl)
            return True, "created" if nx else "updated"
        if backend == "file":
            data = _file_load()
            if nx and key in data and float(data[key].get("_exp") or 0) > now:
                return False, "exists"
            data[key] = {**rec, "_exp": now + ttl, "_payload": payload}
            _file_save(data)
            return True, "created" if nx else "updated"
        r = _sync_redis()
        if nx:
            ok = bool(r.set(key, payload, nx=True, ex=ttl))
            return (True, "created") if ok else (False, "exists")
        rem = r.ttl(key)
        ex = ttl if rem is None or rem < 0 else max(1, int(rem))
        r.set(key, payload, ex=ex)
        return True, "updated"
    except Exception as e:
        _set_err(type(e).__name__)
        logger.warning("[agent_runtime_idempotency] write failed: %s", type(e).__name__)
        return False, "error"


def _delete(key: str) -> bool:
    backend = _resolve_backend()
    try:
        if backend == "memory":
            with _MEM_LOCK:
                return _MEM.pop(key, None) is not None
        if backend == "file":
            data = _file_load()
            existed = key in data
            data.pop(key, None)
            _file_save(data)
            return existed
        return bool(_sync_redis().delete(key))
    except Exception as e:
        _set_err(type(e).__name__)
        return False


def claim(
    agent_id: str,
    capability: str,
    idempotency_key: str,
    *,
    tenant_id: str | None = None,
    runtime_run_id: str = "",
    command_id: str = "",
    ttl_s: int | None = None,
) -> ClaimResult:
    """Atomic first-writer-wins claim. Fail-closed on store errors."""
    backend = _resolve_backend()
    key = idem_key(agent_id, capability, idempotency_key, tenant_id=tenant_id)
    if not key:
        return ClaimResult(ok=False, reason_code="malformed_idempotency_key", backend=backend)
    ttl = int(ttl_s or DEFAULT_TTL_S)
    now = time.time()
    rec = {
        "schema_version": SCHEMA_VERSION,
        "idempotency_key_hash": key_hash(_canon_raw_key(idempotency_key)),
        "agent_id": _canon_agent(agent_id),
        "capability": _canon_capability(capability),
        "scope": _canon_scope(tenant_id),
        "tenant_id": (str(tenant_id).strip() if tenant_id else None),
        "runtime_run_id": str(runtime_run_id or "")[:64],
        "command_id": str(command_id or "")[:64],
        "status": "in_progress",
        "claimed_at": _now_iso(),
        "updated_at": _now_iso(),
        "expires_at": datetime.fromtimestamp(now + ttl, tz=timezone.utc).isoformat(),
        "result_digest": None,
        "terminal_reason": None,
    }
    ok, detail = _write(key, rec, ttl, nx=True)
    if detail == "error":
        return ClaimResult(
            ok=False,
            reason_code="idempotency_store_unavailable",
            store_unavailable=True,
            redis_key=key,
            backend=backend,
        )
    if ok:
        _set_err(None)
        return ClaimResult(
            ok=True,
            claimed=True,
            duplicate=False,
            reason_code="claimed",
            record=rec,
            redis_key=key,
            backend=backend,
        )
    existing, st = _read(key)
    if st == "unavailable":
        return ClaimResult(
            ok=False,
            reason_code="idempotency_store_unavailable",
            store_unavailable=True,
            redis_key=key,
            backend=backend,
        )
    if st == "malformed":
        return ClaimResult(
            ok=False,
            reason_code="idempotency_record_malformed",
            redis_key=key,
            backend=backend,
        )
    if st == "expired" or existing is None:
        ok2, detail2 = _write(key, rec, ttl, nx=True)
        if ok2:
            return ClaimResult(
                ok=True,
                claimed=True,
                reason_code="claimed",
                record=rec,
                redis_key=key,
                backend=backend,
            )
        if detail2 == "error":
            return ClaimResult(
                ok=False,
                reason_code="idempotency_store_unavailable",
                store_unavailable=True,
                redis_key=key,
                backend=backend,
            )
        existing, st = _read(key)
    status = str((existing or {}).get("status") or "in_progress")
    reason = (
        "duplicate_in_progress" if status in ("in_progress", "claimed") else "duplicate_suppressed"
    )
    return ClaimResult(
        ok=True,
        claimed=False,
        duplicate=True,
        reason_code=reason,
        record=existing,
        redis_key=key,
        backend=backend,
    )


def complete(
    agent_id: str,
    capability: str,
    idempotency_key: str,
    *,
    status: str,
    tenant_id: str | None = None,
    terminal_reason: str = "",
    result_digest: str | None = None,
    runtime_run_id: str = "",
) -> ClaimResult:
    key = idem_key(agent_id, capability, idempotency_key, tenant_id=tenant_id)
    if not key:
        return ClaimResult(ok=False, reason_code="malformed_idempotency_key")
    existing, st = _read(key)
    if st == "unavailable":
        return ClaimResult(
            ok=False,
            reason_code="idempotency_store_unavailable",
            store_unavailable=True,
            redis_key=key,
        )
    if not existing:
        existing = {
            "schema_version": SCHEMA_VERSION,
            "idempotency_key_hash": key_hash(_canon_raw_key(idempotency_key) or "x"),
            "agent_id": _canon_agent(agent_id),
            "capability": _canon_capability(capability),
            "scope": _canon_scope(tenant_id),
            "tenant_id": (str(tenant_id).strip() if tenant_id else None),
            "runtime_run_id": str(runtime_run_id or "")[:64],
            "command_id": "",
            "status": status,
            "claimed_at": _now_iso(),
            "updated_at": _now_iso(),
            "expires_at": "",
            "result_digest": result_digest,
            "terminal_reason": (terminal_reason or "")[:200],
        }
    else:
        existing["status"] = status
        existing["updated_at"] = _now_iso()
        existing["terminal_reason"] = (terminal_reason or "")[:200]
        if result_digest is not None:
            existing["result_digest"] = str(result_digest)[:64]
        if runtime_run_id:
            existing["runtime_run_id"] = str(runtime_run_id)[:64]
    ok, detail = _write(key, existing, DEFAULT_TTL_S, nx=False)
    if not ok and detail == "error":
        return ClaimResult(
            ok=False,
            reason_code="idempotency_commit_uncertain",
            store_unavailable=True,
            record=existing,
            redis_key=key,
        )
    return ClaimResult(ok=True, claimed=True, record=existing, redis_key=key, reason_code=status)


def release(
    agent_id: str,
    capability: str,
    idempotency_key: str,
    *,
    tenant_id: str | None = None,
) -> dict[str, Any]:
    """Drop in-progress claim (control-blocked / capability skip)."""
    key = idem_key(agent_id, capability, idempotency_key, tenant_id=tenant_id)
    if not key:
        return {"ok": False, "error": "malformed_idempotency_key"}
    existing, st = _read(key)
    if st == "unavailable":
        return {"ok": False, "reason_code": "idempotency_store_unavailable"}
    if existing and str(existing.get("status") or "") in TERMINAL:
        return {"ok": True, "released": False, "reason": "already_terminal"}
    cleared = _delete(key)
    return {"ok": True, "released": cleared, "key": key}


def get(
    agent_id: str,
    capability: str,
    idempotency_key: str,
    *,
    tenant_id: str | None = None,
) -> ClaimResult:
    key = idem_key(agent_id, capability, idempotency_key, tenant_id=tenant_id)
    if not key:
        return ClaimResult(ok=False, reason_code="malformed_idempotency_key")
    existing, st = _read(key)
    if st == "unavailable":
        return ClaimResult(
            ok=False, reason_code="idempotency_store_unavailable", store_unavailable=True
        )
    if st == "malformed":
        return ClaimResult(ok=False, reason_code="idempotency_record_malformed")
    if st == "expired" or not existing:
        return ClaimResult(ok=True, reason_code="not_found", redis_key=key)
    return ClaimResult(
        ok=True, record=existing, redis_key=key, reason_code=str(existing.get("status"))
    )


def reset_memory_for_tests() -> None:
    with _MEM_LOCK:
        _MEM.clear()
    _set_err(None)


__all__ = [
    "SCHEMA_VERSION",
    "KEY_PREFIX",
    "DEFAULT_TTL_S",
    "ClaimResult",
    "backend_status",
    "idem_key",
    "key_hash",
    "claim",
    "complete",
    "release",
    "get",
    "reset_memory_for_tests",
]
