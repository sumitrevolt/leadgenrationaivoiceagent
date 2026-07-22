"""Real-Redis, real-multiprocess durability proof for the harness audit backend.

Skips automatically when no live Redis is reachable, so it is safe in any CI that
lacks a Redis service. Point it at a throwaway Redis DB via HARNESS_TEST_REDIS_URL
(default redis://localhost:6379/15); the DB is flushed around each test.

Unlike the fake-Redis unit tests, this exercises the ACTUAL Lua script on a real
Redis server across real OS processes.
"""

from __future__ import annotations

import multiprocessing
import os

import pytest

redis = pytest.importorskip("redis")

from app.agents.harness import audit_backend  # noqa: E402

REDIS_URL = (
    os.getenv("HARNESS_TEST_REDIS_URL") or os.getenv("REDIS_URL") or "redis://localhost:6379/15"
)


def _client():
    return redis.Redis.from_url(REDIS_URL)


def _redis_available() -> bool:
    try:
        _client().ping()
        return True
    except Exception:
        return False


# In required mode (CI) a missing/unhealthy Redis is a HARD FAILURE, never a skip.
_REQUIRE_REDIS = (os.getenv("HARNESS_REQUIRE_REDIS") or "").strip() == "1"
_REDIS_UP = _redis_available()

pytestmark = pytest.mark.skipif(
    not _REDIS_UP and not _REQUIRE_REDIS,
    reason="no live Redis (set HARNESS_TEST_REDIS_URL); skipping only when not required",
)


def test_required_redis_must_be_reachable():
    """When HARNESS_REQUIRE_REDIS=1 (mandatory CI), the suite must NOT skip: a
    missing or unhealthy Redis fails here so a skipped real-Redis suite can never
    masquerade as success."""
    if _REQUIRE_REDIS:
        assert _REDIS_UP, f"HARNESS_REQUIRE_REDIS=1 but Redis unreachable at {REDIS_URL}"
        # AOF durability must be active for a durable-audit claim.
        cfg = _client().config_get("appendonly")
        assert cfg.get("appendonly") == "yes", f"Redis AOF not enabled: {cfg}"


@pytest.fixture(autouse=True)
def _clean_db():
    c = _client()
    c.flushdb()
    yield
    c.flushdb()


def _row(item="i1", attempt=0):
    return {
        "ts": 1.0,
        "run_id": "r1",
        "task_id": "r1",
        "tenant_id": "__system__",
        "agent": "nikhil",
        "kind": "shadow",
        "tool": "batch.internal.safe_calculation",
        "extra": {
            "source_loop": "batch_harness",
            "resolved_tool_name": "batch.internal.safe_calculation",
            "resolved_tool_version": "1.0.0",
            "item_id": item,
            "attempt": attempt,
            "mode": "shadow",
        },
    }


# Module-level worker so it is picklable under spawn (Windows/macOS).
def _proc_worker(row, dedup_key, url, q):
    import redis as _redis

    from app.agents.harness import audit_backend as ab

    be = ab.RedisBackend(_redis.Redis.from_url(url))
    q.put(be.record(row, dedup_key))


def test_real_redis_atomic_and_duplicate():
    be = audit_backend.RedisBackend(_client())
    dk = audit_backend.derive_dedup_key(_row())
    r1 = be.record(_row(), dk)
    r2 = be.record(_row(), dk)
    assert r1["written"] and r2["duplicate"]
    assert r1["event_id"] and r2["event_id"] == r1["event_id"]
    assert be._safe_xlen() == 1


def test_real_redis_multiprocess_one_record():
    row, dk = _row(), audit_backend.derive_dedup_key(_row())
    ctx = multiprocessing.get_context("spawn")
    q = ctx.Queue()
    procs = [ctx.Process(target=_proc_worker, args=(row, dk, REDIS_URL, q)) for _ in range(8)]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=30)
    results = [q.get(timeout=5) for _ in range(8)]
    assert sum(1 for r in results if r["written"]) == 1
    assert sum(1 for r in results if r["duplicate"]) == 7
    assert len({r["event_id"] for r in results}) == 1  # all callers agree on the id
    assert audit_backend.RedisBackend(_client())._safe_xlen() == 1


def test_real_redis_new_process_after_restart_recognizes_dedup():
    be = audit_backend.RedisBackend(_client())
    dk = audit_backend.derive_dedup_key(_row())
    be.record(_row(), dk)
    # brand-new client (simulates a restarted worker; data persists server-side)
    be2 = audit_backend.RedisBackend(_client())
    assert be2.record(_row(), dk)["duplicate"] is True
    assert be2._safe_xlen() == 1


def test_real_redis_distinct_events_distinct_records():
    be = audit_backend.RedisBackend(_client())
    for i in range(5):
        be.record(_row(item=f"x{i}"), audit_backend.derive_dedup_key(_row(item=f"x{i}")))
    assert be._safe_xlen() == 5
    assert be.counts()["records_created"] == 5


def test_real_redis_backend_unavailable_explicit_failure():
    bad = redis.Redis.from_url("redis://localhost:6390/0", socket_connect_timeout=1)
    be = audit_backend.RedisBackend(bad)
    r = audit_backend.write(_row(), backend=be)
    assert r["written"] is False and r["error"]


def test_real_redis_status_counts():
    be = audit_backend.RedisBackend(_client())
    be.record(_row(), audit_backend.derive_dedup_key(_row()))
    c = be.counts()
    assert c["records_created"] == 1
    assert c["dedup_keys_active"] == 1
    assert c["stream_length"] == 1
