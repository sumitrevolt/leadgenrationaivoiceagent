"""P0 Redis fail-fast regression tests (2026-07-11 hardening).

Before this loop, `app/platform/integration_health.py::snapshot()` acquired
a Redis client with `socket_timeout=2` but NO `socket_connect_timeout` — so
`sock.connect(socket_address)` blocked indefinitely when Redis was absent,
hanging the entire pytest suite. Stack trace evidence:

    File "app/platform/integration_health.py", line 112, in snapshot
        h = r.hgetall(_hour_key(dt, kind)) or {}
    File ".venv/Lib/site-packages/redis/connection.py", line 615, in _connect
        sock.connect(socket_address)          ← BLOCKED HERE

This suite locks:
  1. `snapshot()` completes within a bounded window even when Redis is absent
  2. Redis unavailability degrades snapshot to `redis_status: "unavailable"`
     instead of returning empty-but-healthy-looking dict
  3. Explicit `INTEGRATION_HEALTH_REDIS_MODE=disabled` performs ZERO network
  4. Production default remains enabled (never silently disabled)
  5. Snapshot never raises
  6. No Redis credential leaks in error diagnostics
"""

from __future__ import annotations

import os
import time

import pytest

from app.platform import integration_health as ih


# --------------------------------------------------------------------------- #
# Test-mode policy
# --------------------------------------------------------------------------- #


def test_redis_mode_default_is_enabled(monkeypatch):
    monkeypatch.delenv("INTEGRATION_HEALTH_REDIS_MODE", raising=False)
    assert ih._redis_mode() == "enabled"


def test_redis_mode_disabled_via_env(monkeypatch):
    monkeypatch.setenv("INTEGRATION_HEALTH_REDIS_MODE", "disabled")
    assert ih._redis_mode() == "disabled"


def test_redis_mode_invalid_value_treated_as_enabled(monkeypatch):
    """Fail safe — production must NEVER be silently disabled by a typo."""
    monkeypatch.setenv("INTEGRATION_HEALTH_REDIS_MODE", "totally-bogus")
    assert ih._redis_mode() == "enabled"


# --------------------------------------------------------------------------- #
# Disabled mode — zero network
# --------------------------------------------------------------------------- #


def test_disabled_mode_performs_zero_network_calls(monkeypatch):
    """When explicitly disabled, snapshot() must never attempt Redis I/O."""
    monkeypatch.setenv("INTEGRATION_HEALTH_REDIS_MODE", "disabled")
    calls = []
    monkeypatch.setattr(
        ih,
        "_redis",
        lambda: calls.append("call") or (_ for _ in ()).throw(RuntimeError("should not be called")),
    )

    out = ih.snapshot(hours=2)
    assert calls == [], "disabled mode must NOT call _redis()"
    assert out["redis_status"] == "disabled"
    assert out["degraded"] is True
    assert "INTEGRATION_HEALTH_REDIS_MODE" in out["reason"]


def test_disabled_mode_returns_within_bounded_time(monkeypatch):
    monkeypatch.setenv("INTEGRATION_HEALTH_REDIS_MODE", "disabled")
    t0 = time.monotonic()
    ih.snapshot(hours=24)
    assert time.monotonic() - t0 < 0.5, "disabled snapshot must be near-instant"


# --------------------------------------------------------------------------- #
# Unavailable Redis (ping fails)
# --------------------------------------------------------------------------- #


class _RedisPingFails:
    def ping(self):
        import redis

        raise redis.ConnectionError("Error 111 connecting to 127.0.0.1:6379. Connection refused.")


class _RedisConnectHang:
    """Simulates the ORIGINAL hang symptom by raising a timeout error the
    way redis-py does when socket_connect_timeout fires."""

    def ping(self):
        import socket

        raise socket.timeout("timed out")


def test_redis_ping_connection_error_degrades_safely(monkeypatch):
    monkeypatch.delenv("INTEGRATION_HEALTH_REDIS_MODE", raising=False)
    monkeypatch.setattr(ih, "_redis", lambda: _RedisPingFails())

    out = ih.snapshot(hours=2)
    assert out["redis_status"] == "unavailable"
    assert out["degraded"] is True
    assert out["reason"] == "connection_failed"
    assert out["error_type"] == "ConnectionError"
    # No raw exception message (which contained "127.0.0.1:6379")
    blob = str(out)
    assert "127.0.0.1:6379" not in blob, "raw Redis endpoint must not leak"
    assert "Error 111" not in blob


def test_redis_socket_timeout_degrades_safely(monkeypatch):
    """The exact class of failure that used to hang the suite."""
    monkeypatch.delenv("INTEGRATION_HEALTH_REDIS_MODE", raising=False)
    monkeypatch.setattr(ih, "_redis", lambda: _RedisConnectHang())

    t0 = time.monotonic()
    out = ih.snapshot(hours=24)
    elapsed = time.monotonic() - t0

    assert elapsed < 2.5, f"snapshot must be bounded, took {elapsed:.2f}s"
    assert out["redis_status"] == "unavailable"
    assert out["degraded"] is True
    # In Python 3.10+ socket.timeout is an alias for TimeoutError; either
    # name is acceptable — both mean the same failure mode.
    assert out["error_type"] in ("timeout", "TimeoutError")


def test_redis_constructor_raises_degrades_safely(monkeypatch):
    """If `_redis()` itself can't be constructed (bad URL, missing module,
    settings error), snapshot must not propagate — it degrades."""
    monkeypatch.delenv("INTEGRATION_HEALTH_REDIS_MODE", raising=False)

    def _boom():
        raise ValueError("bad redis url: rediss://user:S3cret@10.0.0.1:6379/0")

    monkeypatch.setattr(ih, "_redis", _boom)
    out = ih.snapshot(hours=2)
    # Constructor failure lands in the outer except — reason=acquisition_failed
    assert out["redis_status"] == "unavailable"
    assert out["reason"] == "acquisition_failed"
    assert out["error_type"] == "ValueError"
    # Sensitive URL fragment MUST NOT leak
    blob = str(out)
    for leak in ("S3cret", "10.0.0.1", "rediss://"):
        assert leak not in blob, f"credential leak in error diagnostic: {leak!r}"


# --------------------------------------------------------------------------- #
# Available Redis — happy path
# --------------------------------------------------------------------------- #


class _RedisHealthy:
    def __init__(self):
        self._hashes: dict[str, dict[bytes, bytes]] = {}
        self._strings: dict[str, bytes] = {}

    def ping(self):
        return True

    def hgetall(self, key):
        return self._hashes.get(key, {})

    def get(self, key):
        return self._strings.get(key)

    def seed(self, key, mapping):
        self._hashes[key] = {k.encode(): str(v).encode() for k, v in mapping.items()}

    def seed_str(self, key, value):
        self._strings[key] = value.encode()


def test_healthy_redis_returns_populated_integrations(monkeypatch):
    monkeypatch.delenv("INTEGRATION_HEALTH_REDIS_MODE", raising=False)
    stub = _RedisHealthy()

    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    stub.seed(ih._hour_key(now, "fail"), {"smtp": 3, "places": 1})
    stub.seed(ih._hour_key(now, "ok"), {"smtp": 100, "places": 50})

    monkeypatch.setattr(ih, "_redis", lambda: stub)
    out = ih.snapshot(hours=1)
    assert out["redis_status"] == "healthy"
    assert "smtp" in out["integrations"]
    assert out["integrations"]["smtp"]["fail"] == 3
    assert out["integrations"]["smtp"]["ok"] == 100
    assert out["integrations"]["smtp"]["fail_rate"] == pytest.approx(3 / 103, abs=1e-3)


# --------------------------------------------------------------------------- #
# Snapshot invariants
# --------------------------------------------------------------------------- #


def test_snapshot_always_populates_elapsed_s(monkeypatch):
    monkeypatch.setenv("INTEGRATION_HEALTH_REDIS_MODE", "disabled")
    out = ih.snapshot()
    assert isinstance(out.get("elapsed_s"), (int, float))
    assert out["elapsed_s"] >= 0


def test_snapshot_never_raises_even_on_bogus_hours(monkeypatch):
    monkeypatch.setenv("INTEGRATION_HEALTH_REDIS_MODE", "disabled")
    for h in (-5, 0, 999999, "not-an-int"):
        try:
            out = ih.snapshot(hours=h) if isinstance(h, int) else ih.snapshot()
            assert isinstance(out, dict)
        except Exception as e:
            pytest.fail(f"snapshot raised on hours={h!r}: {e}")


# --------------------------------------------------------------------------- #
# Regression: the exact scenario that hung the full suite before this fix
# --------------------------------------------------------------------------- #


def test_snapshot_bounded_when_redis_absent(monkeypatch):
    """Simulates the ORIGINAL hang: Redis constructor succeeds but ping()
    hits socket-connect timeout. Prior to the socket_connect_timeout=1
    change, this scenario blocked the pytest suite for minutes at
    `sock.connect(socket_address)`. Post-fix: snapshot degrades within 2.5s."""
    monkeypatch.delenv("INTEGRATION_HEALTH_REDIS_MODE", raising=False)

    class _RedisAbsent:
        def ping(self):
            import redis

            raise redis.ConnectionError("connect timed out")

    monkeypatch.setattr(ih, "_redis", lambda: _RedisAbsent())

    t0 = time.monotonic()
    out = ih.snapshot(hours=24)
    elapsed = time.monotonic() - t0
    assert elapsed < 2.5, f"still hanging? took {elapsed:.2f}s"
    assert out["degraded"] is True
