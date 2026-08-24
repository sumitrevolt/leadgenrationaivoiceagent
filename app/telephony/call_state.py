"""Distributed call state for CallManager — Redis when available, in-memory fallback.

Why: with >1 uvicorn/dialer worker, a local `dict` + `asyncio.PriorityQueue` are
per-process, so workers can't share the call queue or see each other's active calls.
This store keeps the **priority call queue** and a **serializable active-call registry**
in Redis so workers scale statelessly.

IMPORTANT: live `VoiceAgent` CallContext objects are NOT stored here — they can't be
serialized and must stay in the worker that's running the call. This store only holds
the queued `CallRequest` payloads (plain dicts) and lightweight active-call snapshots.

Falls back to a local `asyncio.PriorityQueue` + dict when Redis is unavailable, so a
single-worker / dev deploy behaves exactly as before. Never raises.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_QUEUE_KEY = "telephony:call_queue"
_ACTIVE_KEY = "telephony:active_calls"
_SID_KEY = "telephony:sid_to_call_id"  # reverse-lookup: Vobiz CallSid → our internal call_id


class RedisCallStore:
    """Shared queue + active-call registry. Redis-backed with local fallback."""

    def __init__(self) -> None:
        self._local_queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._local_active: dict[str, dict] = {}
        self._client: Any = None
        self._is_redis = False
        self._checked = False
        # redis.asyncio clients bind their connection pool to the event loop
        # that first uses them.  Keep the loop object itself (not its id): loop
        # ids can be reused after a loop is closed.
        self._client_loop: asyncio.AbstractEventLoop | None = None

    async def _redis(self) -> Any:
        """Return a real Redis client (with sorted-set ops) or None for local fallback."""
        current_loop = asyncio.get_running_loop()
        if self._is_redis and self._client_loop is not current_loop:
            self._client = None
            self._is_redis = False
            self._checked = False
        if self._checked and self._client_loop is current_loop:
            return self._client if self._is_redis else None
        self._checked = True
        self._client_loop = current_loop
        try:
            import redis.asyncio as aioredis

            from app.config import settings

            client = aioredis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
                max_connections=8,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            await client.ping()
            # A real redis client exposes zadd/zpopmin; the InMemoryCache fallback
            # in app/cache.py does not — in that case we stay fully local.
            if client is not None and hasattr(client, "zadd") and hasattr(client, "zpopmin"):
                self._client = client
                self._is_redis = True
                logger.info("📞 RedisCallStore: Redis-backed distributed call state active")
            else:
                logger.info("📞 RedisCallStore: Redis unavailable — local in-memory call state")
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(f"RedisCallStore init failed ({e}); using local state.")
        return self._client if self._is_redis else None

    # ------------------------------ queue ------------------------------ #
    async def enqueue(self, priority: int, call_id: str, payload: dict) -> None:
        """Add a call to the priority queue (lower priority value = dialed first)."""
        item = {"call_id": call_id, "payload": payload, "ts": time.time()}
        r = await self._redis()
        if r is not None:
            try:
                # score = priority * 1e12 + epoch -> priority first, then FIFO within.
                score = float(priority) * 1e12 + time.time()
                await r.zadd(_QUEUE_KEY, {json.dumps(item, default=str): score})
                return
            except Exception as e:
                logger.warning(f"call_queue zadd failed ({e}); local fallback.")
        await self._local_queue.put((priority, item["ts"], call_id, payload))

    async def dequeue(self) -> tuple[int, str, dict] | None:
        """Pop the highest-priority item, or None if the queue is empty (non-blocking)."""
        r = await self._redis()
        if r is not None:
            try:
                popped = await r.zpopmin(_QUEUE_KEY, 1)
                if not popped:
                    return None
                member, score = popped[0]
                if isinstance(member, (bytes, bytearray)):
                    member = member.decode()
                item = json.loads(member)
                priority = int(float(score) // 1e12)
                return priority, item["call_id"], item["payload"]
            except Exception as e:
                logger.warning(f"call_queue zpopmin failed ({e}); local fallback.")
        if self._local_queue.empty():
            return None
        try:
            priority, _ts, call_id, payload = self._local_queue.get_nowait()
            return priority, call_id, payload
        except asyncio.QueueEmpty:
            return None

    async def qsize(self) -> int:
        r = await self._redis()
        if r is not None:
            try:
                return int(await r.zcard(_QUEUE_KEY))
            except Exception:
                pass
        return self._local_queue.qsize()

    # ------------------------------ active ----------------------------- #
    async def register(self, call_id: str, meta: dict) -> None:
        """Record a serializable snapshot of an active call (cross-worker visibility)."""
        r = await self._redis()
        if r is not None:
            try:
                await r.hset(_ACTIVE_KEY, call_id, json.dumps(meta, default=str))
                return
            except Exception as e:
                logger.warning(f"active hset failed ({e}); local fallback.")
        self._local_active[call_id] = meta

    async def unregister(self, call_id: str) -> None:
        r = await self._redis()
        if r is not None:
            try:
                await r.hdel(_ACTIVE_KEY, call_id)
                return
            except Exception as e:
                logger.warning(f"active hdel failed ({e}); local fallback.")
        self._local_active.pop(call_id, None)

    # -- sid ↔ call_id reverse mapping (2026-07-10: Vobiz status webhook fix) -- #

    async def _sid_map_set(self, sid: str, call_id: str) -> None:
        """Map Vobiz CallSid → our internal call_id (so status webhooks resolve)."""
        if not sid or not call_id:
            return
        r = await self._redis()
        if r is not None:
            try:
                await r.hset(_SID_KEY, sid, call_id)
                return
            except Exception as e:
                logger.warning(f"sid_map hset failed ({e}); local fallback.")
        self._local_sid_map = getattr(self, "_local_sid_map", {}) or {}
        self._local_sid_map[sid] = call_id

    async def _sid_map_get(self, sid: str) -> str | None:
        """Look up our internal call_id from a Vobiz CallSid."""
        if not sid:
            return None
        r = await self._redis()
        if r is not None:
            try:
                val = await r.hget(_SID_KEY, sid)
                return (
                    val.decode()
                    if isinstance(val, (bytes, bytearray))
                    else str(val)
                    if val
                    else None
                )
            except Exception as e:
                logger.warning(f"sid_map hget failed ({e}); local fallback.")
        lm = getattr(self, "_local_sid_map", {}) or {}
        return lm.get(sid)

    async def _sid_map_del(self, sid: str) -> None:
        if not sid:
            return
        r = await self._redis()
        if r is not None:
            try:
                await r.hdel(_SID_KEY, sid)
                return
            except Exception as e:
                logger.warning(f"sid_map hdel failed ({e}); local fallback.")
        lm = getattr(self, "_local_sid_map", {}) or {}
        lm.pop(sid, None)

    async def active_count(self) -> int:
        r = await self._redis()
        if r is not None:
            try:
                return int(await r.hlen(_ACTIVE_KEY))
            except Exception:
                pass
        return len(self._local_active)

    def local_qsize(self) -> int:
        """Sync best-effort local queue size (for non-async stats callers)."""
        return self._local_queue.qsize()


_store: RedisCallStore | None = None


def get_call_store() -> RedisCallStore:
    """Process-wide RedisCallStore singleton (lazy)."""
    global _store
    if _store is None:
        _store = RedisCallStore()
    return _store


__all__ = ["RedisCallStore", "get_call_store"]
