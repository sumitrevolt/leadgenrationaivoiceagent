"""InMemoryCache must accept the nx/xx kwargs that redis.asyncio.set() supports,
so voice_launch.session_idem_claim (which passes nx=True, ex=ttl) does NOT
fail-CLOSED when the app falls back to the in-memory cache. Without this, every
dial is treated as 'already dispatched this session' and no call is ever placed.
See PLT-156 root-cause (call_loop.log 2026-09-15)."""

import pytest
from app.cache import InMemoryCache


@pytest.mark.asyncio
async def test_inmemory_set_basic():
    c = InMemoryCache()
    assert await c.set("a", "1") == "OK"
    assert await c.get("a") == "1"
    assert await c.set("b", "2", ex=60) == "OK"
    assert await c.get("b") == "2"


@pytest.mark.asyncio
async def test_inmemory_set_returns_none_and_ok():
    # redis.asyncio.set() returns None on no-op and "OK" on write; mirror that.
    c = InMemoryCache()
    assert await c.set("k", "v") == "OK"


@pytest.mark.asyncio
async def test_inmemory_set_nx_only_if_absent():
    c = InMemoryCache()
    assert await c.set("k", "first", nx=True) == "OK"
    assert await c.get("k") == "first"
    # second nx set on existing key -> no-op, original value kept
    assert await c.set("k", "second", nx=True) is None
    assert await c.get("k") == "first"


@pytest.mark.asyncio
async def test_inmemory_set_xx_only_if_present():
    c = InMemoryCache()
    assert await c.set("k", "v", xx=True) is None  # absent -> no-op
    await c.set("k", "v")
    assert await c.set("k", "v2", xx=True) == "OK"  # present -> overwrite
    assert await c.get("k") == "v2"


@pytest.mark.asyncio
async def test_inmemory_set_expired_counts_as_absent():
    c = InMemoryCache()
    await c.set("k", "v", ex=120)
    # force the key to be expired (past timestamp) -> counts as absent
    import time
    c._expiry["k"] = time.time() - 5
    assert await c.set("k", "w", nx=True) == "OK"
    assert await c.get("k") == "w"


@pytest.mark.asyncio
async def test_session_idem_claim_does_not_fail_closed_on_inmemory():
    """session_idem_claim(key, nx=True) must return True on first claim, False on
    duplicate — NOT silently fail-CLOSED (False for everything) when the Redis
    client falls back to InMemoryCache."""
    import app.cache as cache_mod
    from app.telephony import voice_launch as vl

    mem = InMemoryCache()
    async def fake_redis():
        return mem

    # monkeypatch the module-level _redis and current_session_id
    vl._redis = fake_redis
    async def fake_sid():
        return "sess-1"

    vl.current_session_id = fake_sid

    first = await vl.session_idem_claim("sess-1", "lead:+9199999")
    dup = await vl.session_idem_claim("sess-1", "lead:+9199999")
    other = await vl.session_idem_claim("sess-1", "lead:+9188888")
    assert first is True
    assert dup is False
    assert other is True
