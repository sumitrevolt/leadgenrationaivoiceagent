"""
semantic_cache.py — free LLM response cache (L1 exact + L2 semantic).

KYUN: greeting-audio + 60s API cache pehle se hai; "general LLM response cache"
audit me free-to-add GAP tha (latency↓ + free-tier token/TPD burn↓). Yeh wahi
bharta — koi naya paid dep nahi, tera maujooda fastembed + Qdrant + Redis reuse.

DESIGN (teri prod-rules ke according):
  - FLAG-GATED: env `SEMANTIC_CACHE` (OFF default) — unset = ZERO behaviour change
    aur ZERO extra Redis/embed overhead (disabled branch turant lautta).
  - FAIL-OPEN: koi bhi error/timeout = seedha factory() call (cache miss jaisa),
    request kabhi raise/ block nahi hoti.
  - OFF-LOOP + HARD-DEADLINE: embedding `asyncio.to_thread` + `wait_for` me chalti
    (public-path pe ML kabhi event-loop block na kare — 3 prod-downs ka sabak).
  - SHARED METRICS: hit/miss counters Redis me (multi-worker-correct — tera in-process
    counter "unreliable" decision ke according). /metrics inhe expose karta hai.
  - DECOUPLED + TESTABLE: core ek duck-typed `backend` pe chalta; default prod
    backend lazily fastembed/Qdrant/Redis use karta. Tests fake backend dete hain.

USAGE (caller opt-in karta, koi auto-wiring nahi):
    from app.cache.semantic_cache import semantic_complete
    reply, info = await semantic_complete(
        user_text, lambda: free_ai.chat(system=sys, messages=msgs), scope=niche
    )
    # info = {"cache": "exact"|"semantic"|"miss"|"disabled", "score": float, ...}

Top-level imports SIRF stdlib — `app.*` sab lazy taaki yeh module bina poore app
ke bhi import/test ho sake.
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import logging
import os
import time
import uuid
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger(__name__)

# --- stats ---------------------------------------------------------------------
# in-memory (per-process, quick local debug) + Redis (shared, /metrics-correct).
_STATS: dict[str, int] = {"exact": 0, "semantic": 0, "miss": 0, "error": 0, "disabled": 0}
_REDIS_PREFIX = "semcache"


def stats() -> dict[str, int]:
    """Per-process in-memory counters (quick debug). /metrics ke liye redis_stats()."""
    return dict(_STATS)


def reset_stats() -> None:
    for k in _STATS:
        _STATS[k] = 0


async def _bump(kind: str) -> None:
    """Shared Redis counter (multi-worker-correct). Best-effort — fail-open."""
    try:
        from app.cache import get_cache_redis_client

        r = await get_cache_redis_client()
        await r.incr(f"{_REDIS_PREFIX}:{kind}")
    except Exception:
        pass


async def _record(kind: str) -> None:
    """Ek cache-event count karo: in-memory + shared Redis (best-effort)."""
    _STATS[kind] = _STATS.get(kind, 0) + 1
    await _bump(kind)


async def redis_stats() -> dict[str, int]:
    """Shared (Redis) counters — multi-worker-correct, /metrics ke liye. Fail = zeros."""
    out = {"exact": 0, "semantic": 0, "miss": 0, "error": 0, "disabled": 0}
    try:
        from app.cache import get_cache_redis_client

        r = await get_cache_redis_client()
        for k in list(out):
            v = await r.get(f"{_REDIS_PREFIX}:{k}")
            out[k] = int(v or 0)
    except Exception:
        pass
    return out


# --- config (env, runtime-toggle-able) ----------------------------------------
def is_enabled() -> bool:
    return (os.getenv("SEMANTIC_CACHE", "") or "").strip().lower() in ("1", "true", "yes", "on")


def _ttl() -> int:
    try:
        return int(os.getenv("SEMANTIC_CACHE_TTL_S", "21600") or 21600)  # 6h
    except Exception:
        return 21600


def _min_sim() -> float:
    try:
        return float(os.getenv("SEMANTIC_CACHE_MIN_SIM", "0.97") or 0.97)
    except Exception:
        return 0.97


def _embed_timeout() -> float:
    try:
        return float(os.getenv("SEMANTIC_CACHE_EMBED_TIMEOUT_S", "2.0") or 2.0)
    except Exception:
        return 2.0


def _store_timeout() -> float:
    try:
        return float(os.getenv("SEMANTIC_CACHE_STORE_TIMEOUT_S", "1.5") or 1.5)
    except Exception:
        return 1.5


# --- helpers ------------------------------------------------------------------
def _normalize(text: str) -> str:
    """Whitespace collapse + lower — exact-match hit-rate badhane ke liye."""
    return " ".join((text or "").split()).lower()


def _l1_key(scope: str, norm: str) -> str:
    h = hashlib.sha256(f"{scope}|{norm}".encode()).hexdigest()[:32]
    return f"sem:{h}"


async def _call_factory(factory: Callable[[], Any] | Awaitable[Any]) -> Any:
    """factory zero-arg callable (value ya awaitable de) ya seedha awaitable ho."""
    res = factory() if callable(factory) else factory
    if inspect.isawaitable(res):
        res = await res
    return res


async def _safe_embed(backend: Any, text: str) -> list[float] | None:
    """Off-loop embed with hard timeout. Fail = None (semantic skip, fail-open)."""
    try:
        return await asyncio.wait_for(asyncio.to_thread(backend.embed, text), _embed_timeout())
    except Exception as e:  # timeout / dep-missing / model-not-ready
        await _record("error")
        logger.debug("semantic_cache embed skipped: %s", e)
        return None


async def _safe_thread(fn: Callable[..., Any], *args: Any, timeout: float) -> Any:
    try:
        return await asyncio.wait_for(asyncio.to_thread(fn, *args), timeout)
    except Exception as e:
        logger.debug("semantic_cache backend op skipped: %s", e)
        return None


# --- default production backend (lazy app.* imports) --------------------------
class _ProdBackend:
    """fastembed (query embedding) + Qdrant (dedicated cache collection) + Redis
    (L1 exact, evictable cache instance). Sab lazy + best-effort."""

    def __init__(self) -> None:
        self.collection = (
            os.getenv("SEMANTIC_CACHE_COLLECTION", "") or "llm_semantic_cache"
        ).strip()
        self._l1 = None

    # -- L1 exact (Redis evictable cache; fail-soft already) -- #
    def _cache(self):
        if self._l1 is None:
            from app.cache import Cache  # lazy — top-level light rakha

            self._l1 = Cache(prefix="llmsem", default_ttl=_ttl())
        return self._l1

    async def l1_get(self, key: str) -> str | None:
        val = await self._cache().get(key)
        return val if isinstance(val, str) else (None if val is None else str(val))

    async def l1_set(self, key: str, value: str, ttl: int) -> None:
        await self._cache().set(key, value, ttl=ttl)

    # -- embedding (reuse the KB's fastembed model — same vector space) -- #
    def embed(self, text: str) -> list[float]:
        from app.voice_agent.knowledge_base import _get_qdrant_embedder

        emb = _get_qdrant_embedder()
        vec = next(iter(emb.embed([f"query: {text}"])))  # symmetric (query↔query match)
        return [float(x) for x in vec]

    # -- Qdrant (dedicated collection; KB ke kb_main ko pollute nahi karta) -- #
    def _client(self):
        from app.voice_agent.knowledge_base import _get_qdrant_client

        return _get_qdrant_client()  # live singleton (kb_main ensure side-effect harmless)

    def _ensure(self, client, dim: int) -> None:
        from qdrant_client import models as qm

        if not client.collection_exists(self.collection):
            client.create_collection(
                collection_name=self.collection,
                vectors_config=qm.VectorParams(size=dim, distance=qm.Distance.COSINE),
            )
            try:
                client.create_payload_index(
                    collection_name=self.collection,
                    field_name="scope",
                    field_schema=qm.PayloadSchemaType.KEYWORD,
                )
            except Exception:
                pass

    def vsearch(self, vec: list[float], scope: str) -> dict[str, Any] | None:
        from qdrant_client import models as qm

        client = self._client()
        if not client.collection_exists(self.collection):
            return None
        res = client.query_points(
            collection_name=self.collection,
            query=vec,
            query_filter=qm.Filter(
                must=[qm.FieldCondition(key="scope", match=qm.MatchValue(value=scope))]
            ),
            limit=1,
            with_payload=True,
        )
        pts = getattr(res, "points", None) or []
        if not pts:
            return None
        p = pts[0]
        pl = getattr(p, "payload", None) or {}
        return {
            "response": pl.get("response"),
            "score": float(getattr(p, "score", 0.0) or 0.0),
            "ts": float(pl.get("ts", 0.0) or 0.0),
        }

    def vupsert(
        self, vec: list[float], scope: str, key_text: str, response: str, ts: float
    ) -> None:
        from qdrant_client import models as qm

        client = self._client()
        self._ensure(client, len(vec))
        client.upsert(
            collection_name=self.collection,
            points=[
                qm.PointStruct(
                    id=str(uuid.uuid4()),
                    vector=vec,
                    payload={"scope": scope, "key": key_text[:512], "response": response, "ts": ts},
                )
            ],
        )


_DEFAULT_BACKEND: _ProdBackend | None = None


def _default_backend() -> _ProdBackend:
    global _DEFAULT_BACKEND
    if _DEFAULT_BACKEND is None:
        _DEFAULT_BACKEND = _ProdBackend()
    return _DEFAULT_BACKEND


# --- public API ---------------------------------------------------------------
async def semantic_complete(
    key_text: str,
    factory: Callable[[], Any] | Awaitable[Any],
    *,
    scope: str = "global",
    ttl: int | None = None,
    min_similarity: float | None = None,
    backend: Any = None,
) -> tuple[Any, dict[str, Any]]:
    """LLM response ko semantically cache karo.

    key_text     : jis text pe match karna (e.g. user message / prompt).
    factory      : zero-arg callable jo asli LLM response (str) banata (await-able OK).
    scope        : niche/client isolation (alag scope cross-serve nahi karega).
    Returns      : (response, info). info["cache"] = exact|semantic|miss|disabled.

    FAIL-OPEN: cache layer ka koi bhi error = factory() chalega; response kabhi
    block/raise nahi hoga.
    """
    info: dict[str, Any] = {"cache": "miss", "score": 0.0, "scope": scope}

    if not is_enabled():
        _STATS["disabled"] += 1  # disabled = ZERO extra I/O (no redis bump)
        info["cache"] = "disabled"
        return await _call_factory(factory), info

    norm = _normalize(key_text)
    if not norm:
        return await _call_factory(factory), info

    be = backend or _default_backend()
    ttl_v = int(ttl if ttl is not None else _ttl())
    min_sim = float(min_similarity if min_similarity is not None else _min_sim())
    now = time.time()
    l1key = _l1_key(scope, norm)

    # L1: exact match (no embedding cost) — templated/repeat prompts yahin pakde jate.
    try:
        hit = await be.l1_get(l1key)
    except Exception:
        hit = None
    if hit:
        await _record("exact")
        info["cache"] = "exact"
        return hit, info

    # L2: semantic — embed off-loop + Qdrant top-1 cosine.
    vec = await _safe_embed(be, norm)
    if vec is not None:
        found = await _safe_thread(be.vsearch, vec, scope, timeout=_store_timeout())
        if found and found.get("response") is not None:
            score = float(found.get("score") or 0.0)
            ts = float(found.get("ts") or 0.0)
            fresh = ts == 0.0 or (now - ts) <= ttl_v
            if score >= min_sim and fresh:
                await _record("semantic")
                info.update(cache="semantic", score=round(score, 4))
                try:
                    await be.l1_set(l1key, found["response"], ttl_v)  # warm L1
                except Exception:
                    pass
                return found["response"], info

    # MISS → compute once, then store best-effort (never blocks the response).
    await _record("miss")
    value = await _call_factory(factory)
    try:
        if isinstance(value, str) and value.strip():
            await be.l1_set(l1key, value, ttl_v)
            if vec is not None:
                await _safe_thread(
                    be.vupsert, vec, scope, norm, value, now, timeout=_store_timeout()
                )
    except Exception:
        pass
    return value, info
