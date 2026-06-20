"""
test_semantic_cache.py — unit tests for app/cache/semantic_cache.py.

Fake backend use karte hain (deterministic vectors + real cosine) — koi Redis /
Qdrant / fastembed / LLM key nahi chahiye. CI me `-m "not network"` ke saath
safely chalega (network marker nahi lagaya).
"""

import math

import pytest

from app.cache import semantic_cache as sc


# --- deterministic fake backend ---------------------------------------------
def _cos(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


class FakeBackend:
    """In-memory L1 + vector list. embed() ek vecmap se controlled vectors deta."""

    def __init__(self, vecmap=None, embed_raises=False):
        self.l1 = {}
        self.vecs = []  # (vec, scope, response, ts)
        self.vecmap = vecmap or {}
        self.embed_raises = embed_raises
        self.embed_calls = 0

    async def l1_get(self, key):
        return self.l1.get(key)

    async def l1_set(self, key, value, ttl):
        self.l1[key] = value

    def embed(self, text):
        self.embed_calls += 1
        if self.embed_raises:
            raise RuntimeError("embed model not ready")
        # normalized text -> vector; unknown = far-away unit vector.
        return self.vecmap.get(text, [0.0, 0.0, 1.0])

    def vsearch(self, vec, scope):
        best = None
        for v, s, resp, ts in self.vecs:
            if s != scope:
                continue
            score = _cos(v, vec)
            if best is None or score > best["score"]:
                best = {"response": resp, "score": score, "ts": ts}
        return best

    def vupsert(self, vec, scope, key_text, response, ts):
        self.vecs.append((vec, scope, response, ts))


# normalized (lowercased) keys -> unit vectors. price phrasings ~0.99 cosine.
VECMAP = {
    "what is your pricing": [1.0, 0.0, 0.0],
    "what's your price": [0.99, 0.141, 0.0],  # cos ~0.99 vs above
    "tell me a joke": [0.0, 1.0, 0.0],  # cos 0 vs price
}


@pytest.fixture(autouse=True)
def _reset():
    sc.reset_stats()
    yield


@pytest.mark.asyncio
async def test_disabled_bypass(monkeypatch):
    monkeypatch.delenv("SEMANTIC_CACHE", raising=False)
    be = FakeBackend(VECMAP)
    calls = {"n": 0}

    async def factory():
        calls["n"] += 1
        return "LIVE"

    val, info = await sc.semantic_complete("what is your pricing", factory, scope="t", backend=be)
    assert val == "LIVE"
    assert info["cache"] == "disabled"
    assert calls["n"] == 1
    assert be.embed_calls == 0  # disabled = embedding bhi nahi


@pytest.mark.asyncio
async def test_exact_hit(monkeypatch):
    monkeypatch.setenv("SEMANTIC_CACHE", "1")
    be = FakeBackend(VECMAP)
    calls = {"n": 0}

    async def factory():
        calls["n"] += 1
        return "ANSWER_PRICE"

    v1, i1 = await sc.semantic_complete("What is your pricing", factory, scope="t", backend=be)
    v2, i2 = await sc.semantic_complete("what is   your PRICING", factory, scope="t", backend=be)
    assert v1 == v2 == "ANSWER_PRICE"
    assert i1["cache"] == "miss"
    assert i2["cache"] == "exact"  # normalize -> same L1 key
    assert calls["n"] == 1  # factory once


@pytest.mark.asyncio
async def test_semantic_hit(monkeypatch):
    monkeypatch.setenv("SEMANTIC_CACHE", "1")
    be = FakeBackend(VECMAP)
    calls = {"n": 0}

    async def factory():
        calls["n"] += 1
        return "ANSWER_PRICE"

    await sc.semantic_complete(
        "what is your pricing", factory, scope="t", min_similarity=0.97, backend=be
    )
    val, info = await sc.semantic_complete(
        "what's your price", factory, scope="t", min_similarity=0.97, backend=be
    )
    assert val == "ANSWER_PRICE"
    assert info["cache"] == "semantic"
    assert info["score"] >= 0.97
    assert calls["n"] == 1  # 2nd served from semantic cache


@pytest.mark.asyncio
async def test_semantic_miss_below_threshold(monkeypatch):
    monkeypatch.setenv("SEMANTIC_CACHE", "1")
    be = FakeBackend(VECMAP)
    calls = {"n": 0}

    async def factory():
        calls["n"] += 1
        return f"R{calls['n']}"

    await sc.semantic_complete(
        "what is your pricing", factory, scope="t", min_similarity=0.97, backend=be
    )
    val, info = await sc.semantic_complete(
        "tell me a joke", factory, scope="t", min_similarity=0.97, backend=be
    )
    assert info["cache"] == "miss"
    assert val == "R2"
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_scope_isolation(monkeypatch):
    monkeypatch.setenv("SEMANTIC_CACHE", "1")
    be = FakeBackend(VECMAP)

    async def f_a():
        return "A"

    async def f_b():
        return "B"

    await sc.semantic_complete(
        "what is your pricing", f_a, scope="nicheA", min_similarity=0.97, backend=be
    )
    # same text, different scope -> must NOT serve nicheA's answer
    val, info = await sc.semantic_complete(
        "what is your pricing", f_b, scope="nicheB", min_similarity=0.97, backend=be
    )
    assert val == "B"
    assert info["cache"] == "miss"


@pytest.mark.asyncio
async def test_failopen_on_embed_error(monkeypatch):
    monkeypatch.setenv("SEMANTIC_CACHE", "1")
    be = FakeBackend(VECMAP, embed_raises=True)
    calls = {"n": 0}

    async def factory():
        calls["n"] += 1
        return "LIVE_OK"

    val, info = await sc.semantic_complete("what is your pricing", factory, scope="t", backend=be)
    assert val == "LIVE_OK"  # embed gira par response mila (fail-open)
    assert info["cache"] == "miss"
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_sync_factory_supported(monkeypatch):
    monkeypatch.setenv("SEMANTIC_CACHE", "1")
    be = FakeBackend(VECMAP)
    val, info = await sc.semantic_complete(
        "tell me a joke", lambda: "SYNC_VAL", scope="t", backend=be
    )
    assert val == "SYNC_VAL"
