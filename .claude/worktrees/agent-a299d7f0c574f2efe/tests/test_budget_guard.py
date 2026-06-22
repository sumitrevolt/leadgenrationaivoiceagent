"""Unit tests for app/llm/budget_guard.py — fake redis, no real infra/LLM."""

import pytest

from app.llm import budget_guard as bg


# --- fake redis (dict-backed) -------------------------------------------------
class FakePipe:
    def __init__(self, r):
        self.r = r
        self.ops = []

    def incrby(self, k, amt):
        self.ops.append(("incrby", k, amt))
        return self

    def expire(self, k, ttl):
        self.ops.append(("expire", k, ttl))
        return self

    async def execute(self):
        out = []
        for op in self.ops:
            if op[0] == "incrby":
                self.r.kv[op[1]] = int(self.r.kv.get(op[1], 0)) + op[2]
                out.append(self.r.kv[op[1]])
            else:
                out.append(True)
        self.ops = []
        return out


class FakeRedis:
    def __init__(self):
        self.kv = {}

    async def get(self, k):
        return self.kv.get(k)

    async def incrby(self, k, amt):
        self.kv[k] = int(self.kv.get(k, 0)) + amt
        return self.kv[k]

    def pipeline(self):
        return FakePipe(self)


class InMemLike:
    """Mimics app.cache InMemoryCache fallback — get/set/expire/incr but NO pipeline/incrby."""

    def __init__(self):
        self.kv = {}

    async def get(self, k):
        return self.kv.get(k)

    async def set(self, k, v, **kw):
        self.kv[k] = v
        return True

    async def expire(self, k, ttl):
        return True

    async def incr(self, k):
        self.kv[k] = int(self.kv.get(k, 0)) + 1
        return self.kv[k]


@pytest.fixture
def fake_redis(monkeypatch):
    r = FakeRedis()

    async def _r():
        return r

    monkeypatch.setattr(bg, "_redis", _r)
    bg.reset_local()
    return r


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in (
        "LLM_BUDGET_GUARD",
        "LLM_BUDGET_HARD_KILL",
        "LLM_BUDGET_DAILY_CALLS",
        "LLM_BUDGET_DAILY_TOKENS",
        "LLM_BUDGET_GLOBAL_DAILY_CALLS",
    ):
        monkeypatch.delenv(k, raising=False)
    yield


@pytest.mark.asyncio
async def test_disabled_always_allows(fake_redis):
    # flag unset => allow True, reason disabled, zero redis I/O
    ok, info = await bg.allow("anyscope")
    assert ok is True
    assert info["reason"] == "disabled"


@pytest.mark.asyncio
async def test_hard_kill_blocks_all(monkeypatch, fake_redis):
    monkeypatch.setenv("LLM_BUDGET_GUARD", "1")
    monkeypatch.setenv("LLM_BUDGET_HARD_KILL", "1")
    ok, info = await bg.allow("x")
    assert ok is False
    assert info["reason"] == "hard_kill"


@pytest.mark.asyncio
async def test_scope_call_cap_blocks_after_limit(monkeypatch, fake_redis):
    monkeypatch.setenv("LLM_BUDGET_GUARD", "1")
    monkeypatch.setenv("LLM_BUDGET_DAILY_CALLS", "2")
    monkeypatch.setenv("LLM_BUDGET_DAILY_TOKENS", "0")  # token cap off
    monkeypatch.setenv("LLM_BUDGET_GLOBAL_DAILY_CALLS", "0")  # global off

    assert (await bg.allow("a"))[0] is True
    await bg.record("a", calls=1)
    assert (await bg.allow("a"))[0] is True
    await bg.record("a", calls=1)
    ok, info = await bg.allow("a")
    assert ok is False
    assert info["reason"] == "scope_calls"


@pytest.mark.asyncio
async def test_scope_isolation(monkeypatch, fake_redis):
    monkeypatch.setenv("LLM_BUDGET_GUARD", "1")
    monkeypatch.setenv("LLM_BUDGET_DAILY_CALLS", "1")
    monkeypatch.setenv("LLM_BUDGET_DAILY_TOKENS", "0")
    monkeypatch.setenv("LLM_BUDGET_GLOBAL_DAILY_CALLS", "0")

    await bg.record("a", calls=1)
    assert (await bg.allow("a"))[0] is False  # a exhausted
    assert (await bg.allow("b"))[0] is True  # b untouched


@pytest.mark.asyncio
async def test_token_cap(monkeypatch, fake_redis):
    monkeypatch.setenv("LLM_BUDGET_GUARD", "1")
    monkeypatch.setenv("LLM_BUDGET_DAILY_CALLS", "0")
    monkeypatch.setenv("LLM_BUDGET_DAILY_TOKENS", "100")
    monkeypatch.setenv("LLM_BUDGET_GLOBAL_DAILY_CALLS", "0")

    await bg.record("a", calls=1, prompt_tokens=60, completion_tokens=50)  # 110 > 100
    ok, info = await bg.allow("a")
    assert ok is False
    assert info["reason"] == "scope_tokens"


@pytest.mark.asyncio
async def test_global_cap(monkeypatch, fake_redis):
    monkeypatch.setenv("LLM_BUDGET_GUARD", "1")
    monkeypatch.setenv("LLM_BUDGET_DAILY_CALLS", "0")
    monkeypatch.setenv("LLM_BUDGET_DAILY_TOKENS", "0")
    monkeypatch.setenv("LLM_BUDGET_GLOBAL_DAILY_CALLS", "2")

    await bg.record("a", calls=1)
    await bg.record("b", calls=1)
    ok, info = await bg.allow("c")  # global=2 >= 2
    assert ok is False
    assert info["reason"] == "global_calls"


@pytest.mark.asyncio
async def test_fail_open_on_redis_error(monkeypatch):
    monkeypatch.setenv("LLM_BUDGET_GUARD", "1")
    monkeypatch.setenv("LLM_BUDGET_DAILY_CALLS", "1")

    async def _boom():
        raise RuntimeError("redis down")

    monkeypatch.setattr(bg, "_redis", _boom)
    bg.reset_local()
    ok, info = await bg.allow("a")
    assert ok is True  # FAIL-OPEN
    assert info["reason"] == "error_failopen"


@pytest.mark.asyncio
async def test_hard_kill_alone_blocks_even_with_guard_off(monkeypatch, fake_redis):
    """Review finding #1: ONLY the emergency kill flag (guard OFF) must still block."""
    monkeypatch.delenv("LLM_BUDGET_GUARD", raising=False)
    monkeypatch.setenv("LLM_BUDGET_HARD_KILL", "1")
    assert bg.active() is True
    ok, info = await bg.allow("x")
    assert ok is False
    assert info["reason"] == "hard_kill"


@pytest.mark.asyncio
async def test_record_counts_on_inmemory_fallback(monkeypatch):
    """Review finding #2: InMemoryCache (no pipeline/incrby) pe bhi record() count kare."""
    mem = InMemLike()

    async def _r():
        return mem

    monkeypatch.setattr(bg, "_redis", _r)
    bg.reset_local()
    monkeypatch.setenv("LLM_BUDGET_GUARD", "1")
    monkeypatch.setenv("LLM_BUDGET_DAILY_CALLS", "1")
    monkeypatch.setenv("LLM_BUDGET_DAILY_TOKENS", "0")
    monkeypatch.setenv("LLM_BUDGET_GLOBAL_DAILY_CALLS", "0")

    await bg.record("a", calls=1)  # get+set fallback (no pipeline/incrby on InMemLike)
    ok, info = await bg.allow("a")
    assert ok is False  # counter actually incremented => cap trips
    assert info["reason"] == "scope_calls"
