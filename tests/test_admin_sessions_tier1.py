"""Tier-1 Slice C — regression tests for admin JWT session revocation.

Covers single-token (jti) revocation, revoke-all-for-user via the iat<epoch epoch bump,
the fail-closed (admin-tier) vs fail-open (lower-tier) Redis-failure policy, and iat
normalization. Uses an in-memory fake async Redis; no live Redis needed.
"""

import asyncio
import time
from datetime import datetime

import pytest
from fastapi import HTTPException

from app.platform import admin_sessions as sess


class _FakeAsyncRedis:
    def __init__(self):
        self.store = {}

    async def setex(self, k, ttl, v):
        self.store[k] = str(v)

    async def get(self, k):
        return self.store.get(k)

    async def exists(self, k):
        return 1 if k in self.store else 0


def _use(monkeypatch, fake):
    async def _f():
        return fake

    monkeypatch.setattr(sess, "_redis", _f, raising=True)


def _down(monkeypatch):
    async def _f():
        raise RuntimeError("redis down")

    monkeypatch.setattr(sess, "_redis", _f, raising=True)


# ---- iat normalization --------------------------------------------------------


def test_iat_ts_handles_int_datetime_none():
    assert sess._iat_ts(1_700_000_000) == 1_700_000_000
    assert sess._iat_ts(None) is None
    dt = datetime.utcfromtimestamp(1_700_000_000)
    assert abs(sess._iat_ts(dt) - 1_700_000_000) <= 1


# ---- single-token (jti) revocation --------------------------------------------


def test_fresh_token_not_revoked(monkeypatch):
    _use(monkeypatch, _FakeAsyncRedis())
    payload = {"jti": "j1", "sub": "u1", "iat": int(time.time())}
    assert asyncio.run(sess.is_revoked(payload)) is False


def test_revoke_jti_then_revoked(monkeypatch):
    fake = _FakeAsyncRedis()
    _use(monkeypatch, fake)
    asyncio.run(sess.revoke_jti("j1"))
    payload = {"jti": "j1", "sub": "u1", "iat": int(time.time())}
    assert asyncio.run(sess.is_revoked(payload)) is True
    # a DIFFERENT token (different jti) for the same user is unaffected
    other = {"jti": "j2", "sub": "u1", "iat": int(time.time())}
    assert asyncio.run(sess.is_revoked(other)) is False


# ---- revoke-all-for-user (epoch bump) -----------------------------------------


def test_revoke_all_kills_old_tokens_but_not_new_logins(monkeypatch):
    fake = _FakeAsyncRedis()
    _use(monkeypatch, fake)
    asyncio.run(sess.revoke_all_for_user("u1", reason="password_reset"))
    now = int(time.time())
    old_token = {"jti": "old", "sub": "u1", "iat": now - 1000}  # issued before revoke
    new_token = {"jti": "new", "sub": "u1", "iat": now + 1000}  # re-login after revoke
    assert asyncio.run(sess.is_revoked(old_token)) is True
    assert asyncio.run(sess.is_revoked(new_token)) is False
    # a different user is unaffected
    other_user = {"jti": "x", "sub": "u2", "iat": now - 1000}
    assert asyncio.run(sess.is_revoked(other_user)) is False


# ---- documented Redis-failure policy ------------------------------------------


def test_redis_down_fail_open_returns_false(monkeypatch):
    _down(monkeypatch)
    payload = {"jti": "j", "sub": "u", "iat": int(time.time())}
    # lower-tier / default → fail-open (availability): not treated as revoked
    assert asyncio.run(sess.is_revoked(payload, fail_closed=False)) is False


def test_redis_down_fail_closed_raises_503(monkeypatch):
    _down(monkeypatch)
    payload = {"jti": "j", "sub": "u", "iat": int(time.time())}
    with pytest.raises(HTTPException) as ei:
        asyncio.run(sess.is_revoked(payload, fail_closed=True))
    assert ei.value.status_code == 503


# ---- revoke helpers never raise on redis failure ------------------------------


def test_revoke_helpers_swallow_redis_errors(monkeypatch):
    _down(monkeypatch)
    assert asyncio.run(sess.revoke_jti("j")) is False
    assert asyncio.run(sess.revoke_all_for_user("u")) is False


def test_revoke_noop_on_empty_ids(monkeypatch):
    _use(monkeypatch, _FakeAsyncRedis())
    assert asyncio.run(sess.revoke_jti(None)) is False
    assert asyncio.run(sess.revoke_all_for_user(None)) is False
