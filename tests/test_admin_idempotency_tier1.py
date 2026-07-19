"""Tier-1 governance — regression tests for admin Idempotency-Key protection.

Covers the spec scenarios: double-click (replay), concurrent duplicate (in-progress
reject), key reuse with a different payload (fail-safe conflict), expired key
(re-execute), and the documented Redis-failure policy (fail-open default vs
fail-closed flag). Uses an in-memory fake Redis; no live Redis needed.
"""

import pytest
from fastapi import HTTPException

from app.platform import admin_idempotency as idem


class _FakeHeaders(dict):
    def get(self, k, default=None):
        return super().get(k.lower(), default)


class _FakeRequest:
    def __init__(self, headers=None):
        self.headers = _FakeHeaders(headers or {})


class _FakeRedis:
    """Minimal Redis stub: SET NX, GET, DELETE. TTL ignored (expiry simulated via drop())."""

    def __init__(self):
        self.store = {}

    def set(self, k, v, nx=False, ex=None):
        if nx and k in self.store:
            return None
        self.store[k] = v
        return True

    def get(self, k):
        return self.store.get(k)

    def drop(self, k):
        self.store.pop(k, None)


def _use(monkeypatch, fake):
    monkeypatch.setattr(idem, "_redis", lambda: fake, raising=True)


def _req(key="idem-1"):
    return _FakeRequest({"idempotency-key": key} if key else {})


# ---- payload hashing / key extraction -----------------------------------------


def test_phash_is_order_independent():
    assert idem._phash({"a": 1, "b": 2}) == idem._phash({"b": 2, "a": 1})


def test_phash_differs_on_value_change():
    assert idem._phash({"a": 1}) != idem._phash({"a": 2})


def test_no_key_returns_none(monkeypatch):
    _use(monkeypatch, _FakeRedis())
    assert idem.begin(request=_req(key=None), actor_id="u1", scope="s", payload={}) is None


# ---- double-click → execute once, then replay ---------------------------------


def test_double_click_executes_once_then_replays(monkeypatch):
    fake = _FakeRedis()
    _use(monkeypatch, fake)
    p = {"client_id": "c1", "confirm": True}

    first = idem.begin(request=_req(), actor_id="u1", scope="client.delete", payload=p)
    assert isinstance(first, idem._Owner)  # we own execution
    idem.store(first, {"ok": True, "deleted": True})

    second = idem.begin(request=_req(), actor_id="u1", scope="client.delete", payload=p)
    assert isinstance(second, idem.Replay)
    assert second.response == {"ok": True, "deleted": True}


# ---- concurrent duplicate (in-progress, not yet stored) → 409 -----------------


def test_concurrent_duplicate_rejected_while_in_progress(monkeypatch):
    fake = _FakeRedis()
    _use(monkeypatch, fake)
    p = {"client_id": "c1", "confirm": True}

    first = idem.begin(request=_req(), actor_id="u1", scope="client.delete", payload=p)
    assert isinstance(first, idem._Owner)
    # second arrives before first stores its result
    with pytest.raises(HTTPException) as ei:
        idem.begin(request=_req(), actor_id="u1", scope="client.delete", payload=p)
    assert ei.value.status_code == 409
    assert "in progress" in str(ei.value.detail).lower()


# ---- key reuse with a different payload → fail-safe 409 -----------------------


def test_key_reuse_different_payload_conflicts(monkeypatch):
    fake = _FakeRedis()
    _use(monkeypatch, fake)

    first = idem.begin(
        request=_req(), actor_id="u1", scope="client.delete", payload={"client_id": "c1"}
    )
    idem.store(first, {"ok": True})
    with pytest.raises(HTTPException) as ei:
        idem.begin(
            request=_req(), actor_id="u1", scope="client.delete", payload={"client_id": "c2"}
        )
    assert ei.value.status_code == 409
    assert "different payload" in str(ei.value.detail).lower()


# ---- expired key (dropped from store) → re-execute ----------------------------


def test_expired_key_reexecutes(monkeypatch):
    fake = _FakeRedis()
    _use(monkeypatch, fake)
    p = {"client_id": "c1", "confirm": True}

    first = idem.begin(request=_req(), actor_id="u1", scope="client.delete", payload=p)
    idem.store(first, {"ok": True})
    # simulate TTL expiry
    fake.drop("idem:admin:u1:client.delete:idem-1")
    again = idem.begin(request=_req(), actor_id="u1", scope="client.delete", payload=p)
    assert isinstance(again, idem._Owner)  # free to execute again


# ---- different actor with same key is isolated --------------------------------


def test_key_is_scoped_per_actor(monkeypatch):
    fake = _FakeRedis()
    _use(monkeypatch, fake)
    p = {"client_id": "c1"}
    a = idem.begin(request=_req(), actor_id="userA", scope="client.delete", payload=p)
    idem.store(a, {"ok": "A"})
    b = idem.begin(request=_req(), actor_id="userB", scope="client.delete", payload=p)
    assert isinstance(b, idem._Owner)  # different actor → not deduped against userA


# ---- documented Redis-failure policy ------------------------------------------


def _raise_redis():
    raise RuntimeError("redis down")


def test_redis_down_fail_open_by_default(monkeypatch):
    monkeypatch.delenv("ADMIN_IDEMPOTENCY_FAIL_CLOSED", raising=False)
    monkeypatch.setattr(idem, "_redis", _raise_redis, raising=True)
    # default policy = fail-open: proceed without dedup (returns None → caller executes)
    assert idem.begin(request=_req(), actor_id="u1", scope="s", payload={}) is None


def test_redis_down_fail_closed_when_flagged(monkeypatch):
    monkeypatch.setenv("ADMIN_IDEMPOTENCY_FAIL_CLOSED", "1")
    monkeypatch.setattr(idem, "_redis", _raise_redis, raising=True)
    with pytest.raises(HTTPException) as ei:
        idem.begin(request=_req(), actor_id="u1", scope="s", payload={})
    assert ei.value.status_code == 503


def test_store_is_noop_for_non_owner(monkeypatch):
    _use(monkeypatch, _FakeRedis())
    # passing None (no-key path) or a Replay must not raise
    idem.store(None, {"ok": True})
    idem.store(idem.Replay({"x": 1}), {"ok": True})
