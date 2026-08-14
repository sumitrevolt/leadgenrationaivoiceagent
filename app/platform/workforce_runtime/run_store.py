"""Redis-backed DSH run/submission ledger with test-only memory mode."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable

logger = logging.getLogger(__name__)

RUN_PREFIX = "dsh:run:v1:"
SUBMISSION_PREFIX = "dsh:submission:v1:"
DEFAULT_TTL_S = 24 * 3600
_redis_factory: Any = None
_MEMORY: dict[str, tuple[str, float]] = {}
_LOCK = threading.Lock()


class RunStoreUnavailable(RuntimeError):
    """Durable run state is unavailable; callers must fail closed."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def now_iso() -> str:
    return _now_iso()


def _backend() -> str:
    return "memory" if (os.getenv("DSH_RUN_STORE_BACKEND") or "").lower() == "memory" else "redis"


def _redis():
    if _redis_factory is not None:
        return _redis_factory()
    import redis

    url = (os.getenv("REDIS_URL") or "").strip()
    if not url:
        from app.config import settings

        url = settings.redis_url
    return redis.Redis.from_url(url, socket_timeout=2, decode_responses=True)


def _identifier(value: str) -> str:
    clean = str(value or "").strip()
    if (
        not clean
        or len(clean) > 120
        or any(char in clean for char in ("/", "\\", "*", "?", "\n", "\r", "\x00", " "))
    ):
        raise ValueError("invalid ledger identifier")
    return clean


def _run_key(run_id: str) -> str:
    return RUN_PREFIX + _identifier(run_id)


def _submission_key(submission_id: str) -> str:
    return SUBMISSION_PREFIX + _identifier(submission_id)


def submission_id_for(run_id: str, capability: str) -> str:
    binding = f"{_identifier(run_id)}:{_identifier(capability)}"
    return "dsub_" + hashlib.sha256(binding.encode("utf-8")).hexdigest()[:20]


def submission_task_id_for(run_id: str, capability: str) -> str:
    binding = f"{_identifier(run_id)}:{_identifier(capability)}"
    digest = hashlib.sha256(binding.encode("utf-8")).hexdigest()
    return "dcap_" + digest[20:40]


def _encode(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _decode(raw: Any) -> dict[str, Any] | None:
    if raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    value = json.loads(raw)
    return value if isinstance(value, dict) else None


def _set_new(key: str, value: dict[str, Any], ttl_s: int = DEFAULT_TTL_S) -> bool:
    ttl = max(60, min(int(ttl_s), 7 * 24 * 3600))
    payload = _encode(value)
    try:
        if _backend() == "memory":
            now = time.time()
            with _LOCK:
                current = _MEMORY.get(key)
                if current and current[1] > now:
                    return False
                _MEMORY[key] = (payload, now + ttl)
            return True
        return bool(_redis().set(key, payload, ex=ttl, nx=True))
    except Exception as exc:
        logger.warning("[dsh_run_store] create failed: %s", type(exc).__name__)
        raise RunStoreUnavailable("run store unavailable") from exc


def _get(key: str) -> dict[str, Any] | None:
    try:
        if _backend() == "memory":
            with _LOCK:
                row = _MEMORY.get(key)
            if row is None:
                return None
            if row[1] <= time.time():
                with _LOCK:
                    _MEMORY.pop(key, None)
                return None
            return _decode(row[0])
        return _decode(_redis().get(key))
    except Exception as exc:
        logger.warning("[dsh_run_store] read failed: %s", type(exc).__name__)
        raise RunStoreUnavailable("run store unavailable") from exc


def _update(key: str, mutate: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    try:
        if _backend() == "memory":
            with _LOCK:
                row = _MEMORY.get(key)
                if row is None or row[1] <= time.time():
                    raise KeyError("record_not_found")
                record = _decode(row[0]) or {}
                mutate(record)
                record["updated_at"] = _now_iso()
                _MEMORY[key] = (_encode(record), row[1])
            return record
        client = _redis()
        import redis

        for _attempt in range(3):
            with client.pipeline() as pipe:
                try:
                    pipe.watch(key)
                    raw = pipe.get(key)
                    record = _decode(raw)
                    if record is None:
                        raise KeyError("record_not_found")
                    ttl = max(60, int(pipe.ttl(key) or DEFAULT_TTL_S))
                    mutate(record)
                    record["updated_at"] = _now_iso()
                    pipe.multi()
                    pipe.set(key, _encode(record), ex=ttl)
                    pipe.execute()
                    return record
                except redis.WatchError:
                    continue
        raise RunStoreUnavailable("run store update contention")
    except (KeyError, RunStoreUnavailable):
        raise
    except Exception as exc:
        logger.warning("[dsh_run_store] update failed: %s", type(exc).__name__)
        raise RunStoreUnavailable("run store unavailable") from exc


def create_run(
    *,
    run_id: str,
    agent_id: str,
    tenant_id: str,
    action: str,
    idempotency_key: str,
    approval_ref: str,
    trigger: str,
    timeout_s: float | None,
    provider: str,
    shadow: bool,
    deadline: float,
    input_payload: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    now = _now_iso()
    immutable = {
        "agent_id": str(agent_id or "").strip().lower(),
        "tenant_id": str(tenant_id or "").strip(),
        "action": str(action or "").strip(),
        "idempotency_key": str(idempotency_key or "").strip()[:128],
        "approval_ref": str(approval_ref or "").strip()[:160],
        "trigger": str(trigger or "on_demand").strip()[:80],
        "provider": str(provider or "").strip(),
        "shadow": bool(shadow),
        "input_payload": dict(input_payload or {}),
    }
    request_hash = hashlib.sha256(_encode(immutable).encode("utf-8")).hexdigest()
    row = {
        "schema_version": 1,
        "run_id": _identifier(run_id),
        **immutable,
        "timeout_s": float(timeout_s) if timeout_s else None,
        "status": "queued",
        "reason": "",
        "request_hash": request_hash,
        "deadline": float(deadline),
        "heartbeat_at": now,
        "created_at": now,
        "updated_at": now,
        # Private server-side input. public_run() always strips this field.
        "result": None,
        "audit_seq": 0,
        "audit_hash": "",
        "audit_events": [],
    }
    if not _set_new(_run_key(run_id), row):
        existing = get_run(run_id, include_private=True)
        if existing is None:
            raise RunStoreUnavailable("run create conflict without readable record")
        if str(existing.get("request_hash") or "") != request_hash:
            raise ValueError("run_immutable_collision")
        return existing, False
    return row, True


def get_run(run_id: str, *, include_private: bool = False) -> dict[str, Any] | None:
    row = _get(_run_key(run_id))
    if row is None:
        return None
    if not include_private:
        row.pop("input_payload", None)
        row.pop("idempotency_key", None)
        row.pop("approval_ref", None)
    return row


def update_run(run_id: str, **fields: Any) -> dict[str, Any]:
    allowed = {
        "status",
        "reason",
        "heartbeat_at",
        "result",
        "runtime_version",
        "pid",
        "queue_task_id",
    }
    unexpected = set(fields) - allowed
    if unexpected:
        raise ValueError(f"unsupported run fields: {sorted(unexpected)}")

    def mutate(row: dict[str, Any]) -> None:
        row.update(fields)

    return _update(_run_key(run_id), mutate)


def heartbeat(run_id: str) -> dict[str, Any]:
    return update_run(run_id, heartbeat_at=_now_iso())


def _older_than(value: Any, seconds: float) -> bool:
    try:
        stamp = datetime.fromisoformat(str(value or ""))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - stamp).total_seconds() > seconds
    except Exception:
        return True


def claim_run(run_id: str, *, stale_after_s: float = 600.0) -> tuple[dict[str, Any], bool]:
    claimed = [False]

    def mutate(row: dict[str, Any]) -> None:
        status = str(row.get("status") or "")
        reclaim = status == "running" and _older_than(row.get("heartbeat_at"), stale_after_s)
        if status == "queued" or reclaim:
            row["status"] = "running"
            row["heartbeat_at"] = _now_iso()
            row["reason"] = ""
            claimed[0] = True

    row = _update(_run_key(run_id), mutate)
    return row, claimed[0]


def append_event(run_id: str, event: str, detail: dict[str, Any] | None = None) -> dict[str, Any]:
    """Atomically append a bounded hash-chained, payload-minimized run event."""
    emitted: dict[str, Any] = {}

    def mutate(row: dict[str, Any]) -> None:
        seq = int(row.get("audit_seq") or 0) + 1
        previous = str(row.get("audit_hash") or "")
        base = {
            "run_id": row.get("run_id"),
            "seq": seq,
            "prev_hash": previous,
            "event": str(event or "")[:80],
            "detail": dict(detail or {}),
            "at": _now_iso(),
        }
        canonical = json.dumps(base, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
        base["event_hash"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        events = list(row.get("audit_events") or [])
        events.append(base)
        row["audit_events"] = events[-200:]
        row["audit_seq"] = seq
        row["audit_hash"] = base["event_hash"]
        emitted.clear()
        emitted.update(base)

    _update(_run_key(run_id), mutate)
    return emitted


def create_submission(
    *,
    submission_id: str,
    run_id: str,
    capability: str,
    task_id: str,
) -> tuple[dict[str, Any], bool]:
    now = _now_iso()
    row = {
        "schema_version": 1,
        "submission_id": _identifier(submission_id),
        "run_id": _identifier(run_id),
        "capability": str(capability or "").strip(),
        "task_id": str(task_id or "").strip(),
        "status": "queued",
        "reason": "",
        "result_digest": "",
        "heartbeat_at": now,
        "created_at": now,
        "updated_at": now,
    }
    created = _set_new(_submission_key(submission_id), row)
    return (row if created else get_submission(submission_id) or row), created


def get_submission(submission_id: str) -> dict[str, Any] | None:
    return _get(_submission_key(submission_id))


def update_submission(submission_id: str, **fields: Any) -> dict[str, Any]:
    allowed = {
        "status",
        "reason",
        "result_digest",
        "queue_task_id",
        "approval_id",
        "heartbeat_at",
    }
    unexpected = set(fields) - allowed
    if unexpected:
        raise ValueError(f"unsupported submission fields: {sorted(unexpected)}")

    def mutate(row: dict[str, Any]) -> None:
        row.update(fields)

    return _update(_submission_key(submission_id), mutate)


def claim_submission(
    submission_id: str,
    *,
    stale_after_s: float = 600.0,
) -> tuple[dict[str, Any], bool]:
    claimed = [False]

    def mutate(row: dict[str, Any]) -> None:
        status = str(row.get("status") or "")
        reclaim = status == "running" and _older_than(row.get("heartbeat_at"), stale_after_s)
        if status == "queued" or reclaim:
            row["status"] = "running"
            row["heartbeat_at"] = _now_iso()
            row["reason"] = ""
            claimed[0] = True

    row = _update(_submission_key(submission_id), mutate)
    return row, claimed[0]


def reset_memory_for_tests() -> None:
    with _LOCK:
        _MEMORY.clear()


__all__ = [
    "RUN_PREFIX",
    "SUBMISSION_PREFIX",
    "RunStoreUnavailable",
    "claim_run",
    "claim_submission",
    "create_run",
    "create_submission",
    "append_event",
    "get_run",
    "get_submission",
    "heartbeat",
    "now_iso",
    "reset_memory_for_tests",
    "submission_id_for",
    "submission_task_id_for",
    "update_run",
    "update_submission",
]
