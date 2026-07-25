"""Real-Redis, real-multiprocess durability proof for the authoritative
single-write harness audit backend.

Mandatory in CI (see .github/workflows/ci.yml harness-redis-integration): with
HARNESS_REQUIRE_REDIS=1 a missing/unhealthy Redis is a HARD FAILURE, never a skip.
Locally it skips when no Redis is reachable. Point it at a throwaway DB via
HARNESS_TEST_REDIS_URL (default redis://localhost:6379/15); flushed around each test.
"""

from __future__ import annotations

import hashlib
import json
import multiprocessing
import os

import pytest

redis = pytest.importorskip("redis")

from app.agents.harness import audit_backend, audit_migrate  # noqa: E402

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


_REQUIRE_REDIS = (os.getenv("HARNESS_REQUIRE_REDIS") or "").strip() == "1"
_REDIS_UP = _redis_available()

pytestmark = pytest.mark.skipif(
    not _REDIS_UP and not _REQUIRE_REDIS,
    reason="no live Redis (set HARNESS_TEST_REDIS_URL); skipping only when not required",
)


def test_required_redis_must_be_reachable():
    """Mandatory-CI guard: with HARNESS_REQUIRE_REDIS=1 the suite must not skip; a
    missing/unhealthy Redis (or AOF off) fails here."""
    if _REQUIRE_REDIS:
        assert _REDIS_UP, f"HARNESS_REQUIRE_REDIS=1 but Redis unreachable at {REDIS_URL}"
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


def _proc_worker(row, dedup_key, url, q):
    import redis as _redis

    from app.agents.harness import audit_backend as ab

    be = ab.RedisBackend(_redis.Redis.from_url(url))
    q.put(be.record(row, dedup_key))


def test_real_authoritative_create_and_duplicate():
    be = audit_backend.RedisBackend(_client())
    dk = audit_backend.derive_dedup_key(_row())
    r1 = be.record(_row(), dk)
    r2 = be.record(_row(), dk)
    assert r1["written"] and r2["duplicate"] and r2["event_id"] == r1["event_id"]
    assert be.counts()["authoritative_records"] == 1


def test_real_multiprocess_one_record():
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
    assert len({r["event_id"] for r in results}) == 1
    assert audit_backend.RedisBackend(_client()).counts()["authoritative_records"] == 1


def test_real_partial_commit_impossible_wrongtype_metrics():
    c = _client()
    c.set(audit_backend._METRICS_KEY, "not-a-hash")  # poison derived metrics -> hincrby WRONGTYPE
    be = audit_backend.RedisBackend(_client())
    dk = audit_backend.derive_dedup_key(_row())
    r = be.record(_row(), dk)
    assert r["written"] is True  # authoritative record created despite index failure
    assert c.exists(audit_backend._RECORD_PREFIX + dk) == 1


def test_real_record_write_failure_leaves_nothing():
    bad = redis.Redis.from_url("redis://localhost:6390/0", socket_connect_timeout=1)
    be = audit_backend.RedisBackend(bad)
    r = audit_backend.write(_row(), backend=be)
    assert r["written"] is False and r["error"]
    assert audit_backend.RedisBackend(_client()).counts()["authoritative_records"] == 0


def test_real_restart_and_distinct():
    be = audit_backend.RedisBackend(_client())
    dk = audit_backend.derive_dedup_key(_row())
    be.record(_row(), dk)
    assert audit_backend.RedisBackend(_client()).record(_row(), dk)["duplicate"] is True
    for i in range(4):
        be.record(_row(item=f"x{i}"), audit_backend.derive_dedup_key(_row(item=f"x{i}")))
    assert be.counts()["authoritative_records"] == 5


def test_real_reconcile_rebuilds_index():
    be = audit_backend.RedisBackend(_client())
    for i in range(3):
        be.record(_row(item=f"y{i}"), audit_backend.derive_dedup_key(_row(item=f"y{i}")))
    _client().delete(audit_backend._STREAM_KEY, audit_backend._METRICS_KEY)  # lose index
    dry = be.reconcile(dry_run=True)
    assert dry["authoritative_records"] == 3 and dry["missing_stream_entries"] == 3
    be.reconcile(dry_run=False)
    assert be._safe_xlen() == 3
    assert be.counts()["by_family"].get("batch_harness") == 3


def test_real_retention_expiry_becomes_new(monkeypatch):
    # A very short retention makes the record expire; a later replay is a NEW obs.
    import time

    monkeypatch.setenv("HARNESS_AUDIT_RETENTION_S", "1")
    be = audit_backend.RedisBackend(_client())
    dk = audit_backend.derive_dedup_key(_row())
    assert be.record(_row(), dk)["written"] is True
    time.sleep(1.3)
    assert be.record(_row(), dk)["written"] is True  # expired -> treated as new


def test_real_migration_idempotent_and_provenance(tmp_path):
    dag = {
        "ts": 1.0,
        "run_id": "canary-dag-shadow-0001",
        "tenant_id": "__system__",
        "agent": "manager",
        "kind": "shadow",
        "tool": "workflow.dag.internal_calculation",
        "extra": {
            "source_loop": "dag_engine",
            "node_id": "calc",
            "attempt": 0,
            "mode": "shadow",
            "resolved_tool_name": "workflow.dag.internal_calculation",
            "resolved_tool_version": "1.0.0",
        },
    }
    batch = {
        "ts": 2.0,
        "run_id": "canary_batch_shadow_0001",
        "tenant_id": "__system__",
        "agent": "nikhil",
        "kind": "shadow",
        "tool": "batch.internal.safe_calculation",
        "extra": {
            "source_loop": "batch_harness",
            "item_id": "canary-batch-1",
            "attempt": 0,
            "mode": "shadow",
            "resolved_tool_name": "batch.internal.safe_calculation",
            "resolved_tool_version": "1.0.0",
        },
    }
    body = (json.dumps(dag) + "\n" + json.dumps(batch) + "\n").encode()
    src = tmp_path / "harness_runs.jsonl"
    src.write_bytes(body)
    chk = hashlib.sha256(body).hexdigest()
    sav = "8" * 40
    be = audit_backend.RedisBackend(_client())
    # dry-run: zero writes
    pv = audit_migrate.preview(str(src), sav, backend=be)
    assert pv["would_create"] == 2 and pv["already_existing"] == 0
    assert be.counts()["authoritative_records"] == 0
    # apply: 2 created
    r1 = audit_migrate.apply(str(src), "tok", chk, sav, backend=be)
    assert r1["records_created"] == 2
    # re-apply: idempotent
    r2 = audit_migrate.apply(str(src), "tok", chk, sav, backend=be)
    assert r2["records_created"] == 0 and r2["already_existing"] == 2
    # provenance: keys derived under SOURCE sha
    dag_key = audit_backend.derive_dedup_key(dag, source_app_version=sav)
    assert _client().exists(audit_backend._RECORD_PREFIX + dag_key) == 1
