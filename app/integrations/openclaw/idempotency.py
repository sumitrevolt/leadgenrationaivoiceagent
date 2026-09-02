"""OpenClaw idempotency store — Stage A uses in-process cache for GREEN reads only.

Durable (Redis) storage is Stage B preparation for AMBER. Production must not
enable AMBER until durable_idempotency_available() is True.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Protocol

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_PREFIX = "openclaw:idem:"
_DEFAULT_TTL_S = 300


class OpenClawIdempotencyStore(Protocol):
    def get(self, key: str) -> dict[str, Any] | None: ...

    def put(self, key: str, result: dict[str, Any], ttl_seconds: int) -> None: ...


class MemoryIdempotencyStore:
    """In-process cache — GREEN read optimization / local tests only. Not durable."""

    def __init__(self, max_entries: int = 500) -> None:
        self._data: dict[str, tuple[float, dict[str, Any]]] = {}
        self._max = max_entries

    def get(self, key: str) -> dict[str, Any] | None:
        if not key:
            return None
        row = self._data.get(key)
        if not row:
            return None
        exp, value = row
        if exp < time.time():
            self._data.pop(key, None)
            return None
        return value

    def put(self, key: str, result: dict[str, Any], ttl_seconds: int) -> None:
        if not key:
            return
        if len(self._data) > self._max:
            for k in list(self._data.keys())[:100]:
                self._data.pop(k, None)
        self._data[key] = (time.time() + max(1, int(ttl_seconds)), result)

    def clear(self) -> None:
        self._data.clear()


class RedisIdempotencyStore:
    """Redis-backed store for Stage B AMBER durability. Sync client, best-effort."""

    def get(self, key: str) -> dict[str, Any] | None:
        if not key:
            return None
        r = _sync_redis()
        if r is None:
            return None
        try:
            raw = r.get(_PREFIX + key)
            if not raw:
                return None
            data = json.loads(raw)
            return data if isinstance(data, dict) else None
        except Exception as exc:
            logger.warning("openclaw idem redis get failed: %s", type(exc).__name__)
            return None

    def put(self, key: str, result: dict[str, Any], ttl_seconds: int) -> None:
        if not key:
            return
        r = _sync_redis()
        if r is None:
            return
        try:
            r.setex(_PREFIX + key, max(1, int(ttl_seconds)), json.dumps(result, default=str))
        except Exception as exc:
            logger.warning("openclaw idem redis put failed: %s", type(exc).__name__)


def _sync_redis():
    try:
        import redis as _redis

        url = os.environ.get("REDIS_URL", "redis://localhost:6379")
        return _redis.from_url(url, decode_responses=True, socket_connect_timeout=0.5)
    except Exception:
        return None


def durable_idempotency_available() -> bool:
    """True only when Redis responds. In-process memory alone is NOT durable."""
    r = _sync_redis()
    if r is None:
        return False
    try:
        return bool(r.ping())
    except Exception:
        return False


# Process-local default store (GREEN optimization). Tests clear via .clear().
MEMORY_STORE = MemoryIdempotencyStore()


def get_store(*, prefer_durable: bool = False) -> OpenClawIdempotencyStore:
    if prefer_durable and durable_idempotency_available():
        return RedisIdempotencyStore()
    return MEMORY_STORE
