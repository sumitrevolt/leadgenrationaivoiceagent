"""Customer-login account lockout (2026-08-01 enterprise-audit fix).

Per-account brute-force lockout: 5 failed attempts -> 15min lock (Redis-backed),
mirroring admin.py's 5-fail -> 30min lock. Per-IP rate limit (10/60) is a
separate control. Fail-open on Redis error (metering-class, not compliance).

Hermetic: `get_redis_client` monkeypatch'd to a fake redis — no real Redis.
"""

import asyncio

import pytest

from app.api import customer_auth as CA


class FakeRedis:
    """Mimics the async subset of redis the lockout helpers use."""

    def __init__(self):
        self.kv: dict[str, str] = {}
        self.ttl: dict[str, int] = {}

    async def exists(self, k):
        return 1 if k in self.kv else 0

    async def incr(self, k):
        n = int(self.kv.get(k, 0)) + 1
        self.kv[k] = str(n)
        return n

    async def expire(self, k, ttl):
        self.ttl[k] = ttl
        return True

    async def set(self, k, v, ex=None):
        self.kv[k] = v
        if ex is not None:
            self.ttl[k] = ex
        return True

    async def delete(self, *keys):
        gone = 0
        for k in keys:
            if k in self.kv:
                del self.kv[k]
                gone += 1
        return gone


class _Await:
    """So `await get_redis_client()` returns the fake."""

    def __init__(self, fr):
        self.fr = fr

    def __await__(self):
        async def _g():
            return self.fr

        return _g().__await__()


@pytest.fixture
def fake_redis(monkeypatch):
    fr = FakeRedis()
    monkeypatch.setattr("app.cache.get_redis_client", lambda: _Await(fr))
    return fr


def _record(emails=("a@b.com",), n=1):
    async def _go():
        for _ in range(n):
            for e in emails:
                await CA._record_login_failure(e)

    asyncio.run(_go())


def _locked(email):
    return asyncio.run(CA._account_locked(email))


def test_fail_then_lock_at_five(fake_redis):
    _record(n=5)
    assert _locked("a@b.com") is True, "5 failures must lock the account"
    assert _locked("other@x.com") is False, "unrelated account unaffected"


def test_lock_key_is_case_normalized(fake_redis):
    _record(emails=("MiXeD@Case.COM",))
    assert "customer:login:fail:mixed@case.com" in fake_redis.kv
    assert "MiXeD@Case.COM" not in fake_redis.kv


def test_success_clears_failures_and_lock(fake_redis):
    _record(n=2)
    assert "customer:login:fail:a@b.com" in fake_redis.kv
    asyncio.run(CA._clear_login_failures("a@b.com"))
    assert fake_redis.kv == {}, "clear must drop both fail counter and lock"
    assert _locked("a@b.com") is False


def test_fewer_than_five_does_not_lock(fake_redis):
    _record(n=3)
    assert _locked("a@b.com") is False


def test_lock_ttl_is_900s(fake_redis):
    _record(n=5)
    assert fake_redis.ttl.get("customer:login:lock:a@b.com") == CA._LOCKOUT_WINDOW_S


def test_fail_open_when_redis_errors(monkeypatch):
    """Redis error must NOT lock everyone out (fail-open metering class)."""

    async def _boom():
        raise RuntimeError("redis down")

    monkeypatch.setattr("app.cache.get_redis_client", lambda: _boom())
    assert _locked("a@b.com") is False


def test_clear_fail_open_when_redis_errors(monkeypatch):
    async def _boom():
        raise RuntimeError("redis down")

    monkeypatch.setattr("app.cache.get_redis_client", lambda: _boom())
    asyncio.run(CA._clear_login_failures("a@b.com"))  # must not raise


def test_record_fail_open_when_redis_errors(monkeypatch):
    async def _boom():
        raise RuntimeError("redis down")

    monkeypatch.setattr("app.cache.get_redis_client", lambda: _boom())
    _record()  # must not raise
