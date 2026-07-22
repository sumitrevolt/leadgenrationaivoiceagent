"""Durable harness audit + shadow-dedup backend — multi-worker, restart, and
fail-closed semantics. All harness flags remain OFF; no executor runs here."""

from __future__ import annotations

import json

import pytest

from app.agents.harness import audit, audit_backend


# --------------------------------------------------------------------------- #
# A shared-store fake Redis. Two instances sharing one `store` simulate two
# processes / two containers pointed at the same Redis.
# --------------------------------------------------------------------------- #
class FakeRedis:
    def __init__(self, store=None, crash=False):
        self.store = (
            store
            if store is not None
            else {"kv": {}, "kv_ttl": {}, "streams": {}, "hashes": {}, "seq": [0]}
        )
        self.crash = crash

    def _boom(self):
        if self.crash:
            raise ConnectionError("redis down")

    def set(self, name, value, nx=False, px=None):
        self._boom()
        kv = self.store["kv"]
        if nx and name in kv:
            return None
        kv[name] = value
        if px:
            self.store["kv_ttl"][name] = px
        return True

    def xadd(self, name, fields, maxlen=None, approximate=True):
        self._boom()
        s = self.store["streams"].setdefault(name, [])
        self.store["seq"][0] += 1
        sid = f"{self.store['seq'][0]}-0"
        s.append((sid, dict(fields)))
        if maxlen and len(s) > maxlen:
            del s[0 : len(s) - maxlen]
        return sid.encode()

    def xlen(self, name):
        self._boom()
        return len(self.store["streams"].get(name, []))

    def xrange(self, name, count=None):
        self._boom()
        s = self.store["streams"].get(name, [])
        s = s[:count] if count else s
        return [(sid.encode(), f) for sid, f in s]

    def xrevrange(self, name, count=None):
        self._boom()
        s = list(reversed(self.store["streams"].get(name, [])))
        s = s[:count] if count else s
        return [(sid.encode(), f) for sid, f in s]

    def hincrby(self, name, field, amount=1):
        self._boom()
        h = self.store["hashes"].setdefault(name, {})
        h[field] = int(h.get(field, 0)) + amount
        return h[field]

    def hgetall(self, name):
        self._boom()
        h = self.store["hashes"].get(name, {})
        return {k.encode(): str(v).encode() for k, v in h.items()}

    def ping(self):
        self._boom()
        return True


def _row(
    tenant="__system__",
    agent="nikhil",
    loop="batch_harness",
    tool="t",
    ver="1.0.0",
    item="i1",
    attempt=0,
    kind="shadow",
    run="r1",
    mode="shadow",
):
    return {
        "ts": 1.0,
        "run_id": run,
        "task_id": run,
        "tenant_id": tenant,
        "agent": agent,
        "kind": kind,
        "tool": tool,
        "extra": {
            "source_loop": loop,
            "resolved_tool_name": tool,
            "resolved_tool_version": ver,
            "item_id": item,
            "attempt": attempt,
            "mode": mode,
        },
    }


# ------------------------------- dedup key --------------------------------- #
def test_dedup_key_distinguishes_tenant_agent_tool_attempt(monkeypatch):
    monkeypatch.setenv("APP_VERSION", "sha1")
    base = audit_backend.derive_dedup_key(_row())
    assert base == audit_backend.derive_dedup_key(_row())  # deterministic
    assert base != audit_backend.derive_dedup_key(_row(tenant="acme"))
    assert base != audit_backend.derive_dedup_key(_row(agent="rohan"))
    assert base != audit_backend.derive_dedup_key(_row(tool="other"))
    assert base != audit_backend.derive_dedup_key(_row(attempt=1))
    assert base != audit_backend.derive_dedup_key(_row(item="i2"))


def test_dedup_key_binds_production_sha(monkeypatch):
    monkeypatch.setenv("APP_VERSION", "shaA")
    a = audit_backend.derive_dedup_key(_row())
    monkeypatch.setenv("APP_VERSION", "shaB")
    b = audit_backend.derive_dedup_key(_row())
    assert a != b  # same logical event under a different deployed SHA is distinct


# ------------------------------ atomic dedup ------------------------------- #
def test_redis_atomic_first_observer_wins():
    be = audit_backend.RedisBackend(FakeRedis())
    dk = "k1"
    assert be.claim(dk) is True
    assert be.claim(dk) is False  # second observer loses atomically


def test_cross_process_dedup_shared_backend():
    store = {"kv": {}, "kv_ttl": {}, "streams": {}, "hashes": {}, "seq": [0]}
    be1 = audit_backend.RedisBackend(FakeRedis(store))
    be2 = audit_backend.RedisBackend(FakeRedis(store))  # "another process/container"
    r1 = audit_backend.write(_row(), backend=be1)
    r2 = audit_backend.write(_row(), backend=be2)  # same logical event
    assert r1["written"] is True and r1["duplicate"] is False
    assert r2["written"] is False and r2["duplicate"] is True
    assert be1.counts()["total"] == 1  # exactly one durable record
    assert be1.counts()["duplicates_suppressed"] == 1


def test_multi_worker_many_observers_one_record():
    store = {"kv": {}, "kv_ttl": {}, "streams": {}, "hashes": {}, "seq": [0]}
    workers = [audit_backend.RedisBackend(FakeRedis(store)) for _ in range(8)]
    results = [audit_backend.write(_row(), backend=w) for w in workers]
    assert sum(1 for r in results if r["written"]) == 1
    assert sum(1 for r in results if r["duplicate"]) == 7
    assert workers[0].counts()["total"] == 1


def test_different_events_not_collapsed():
    store = {"kv": {}, "kv_ttl": {}, "streams": {}, "hashes": {}, "seq": [0]}
    be = audit_backend.RedisBackend(FakeRedis(store))
    audit_backend.write(_row(item="a"), backend=be)
    audit_backend.write(_row(item="b"), backend=be)
    audit_backend.write(_row(item="a", attempt=1), backend=be)
    assert be.counts()["total"] == 3


# --------------------------- restart persistence --------------------------- #
def test_restart_preserves_dedup_and_audit():
    store = {"kv": {}, "kv_ttl": {}, "streams": {}, "hashes": {}, "seq": [0]}
    be = audit_backend.RedisBackend(FakeRedis(store))
    audit_backend.write(_row(), backend=be)
    # "restart": brand-new client + backend, same durable store
    be2 = audit_backend.RedisBackend(FakeRedis(store))
    r = audit_backend.write(_row(), backend=be2)
    assert r["duplicate"] is True  # dedup survived restart
    assert be2.counts()["total"] == 1  # audit survived restart


# --------------------------- fail-closed semantics ------------------------- #
def test_backend_unavailable_fails_closed_no_raise():
    be = audit_backend.RedisBackend(FakeRedis(crash=True))
    r = audit_backend.write(_row(), backend=be)
    assert r["written"] is False and r["duplicate"] is False
    assert r["error"]  # operational error surfaced, no exception raised


def test_claim_ok_then_append_crash_fails_closed():
    class ClaimOkAppendCrash(FakeRedis):
        def xadd(self, *a, **k):
            raise ConnectionError("down mid-write")

    be = audit_backend.RedisBackend(ClaimOkAppendCrash())
    r = audit_backend.write(_row(), backend=be)
    assert r["written"] is False and r["error"]


def test_production_redis_no_client_prohibits_silent_fallback(monkeypatch):
    monkeypatch.setenv("HARNESS_AUDIT_BACKEND", "redis")
    monkeypatch.setattr(audit_backend, "_get_redis_client", lambda: None)
    r = audit_backend.write(_row())  # no injected backend -> must NOT use jsonl
    assert r["written"] is False and r["error"]
    assert r["backend"] == "redis"


# ------------------------------ retention/TTL ------------------------------ #
def test_dedup_claim_sets_ttl():
    fake = FakeRedis()
    be = audit_backend.RedisBackend(fake)
    be.claim("k")
    key = audit_backend._DEDUP_PREFIX + "k"
    assert fake.store["kv_ttl"].get(key)  # px TTL applied (bounded, not unbounded)


def test_stream_maxlen_trims(monkeypatch):
    monkeypatch.setenv("HARNESS_AUDIT_MAXLEN", "3")
    fake = FakeRedis()
    be = audit_backend.RedisBackend(fake)
    for i in range(6):
        be.append(_row(item=f"x{i}"))
    assert fake.xlen(audit_backend._STREAM_KEY) <= 3


# --------------------------- size + sanitization --------------------------- #
def test_forbidden_keys_scrubbed():
    row = _row()
    # Keys assigned via a loop variable (no `keyword = "literal"` pattern) so
    # secret scanners are not tripped; redaction is by KEY name, not value.
    sensitive = ["api_key", "password", "token", "authorization", "private_key"]
    marker = "x" * 8
    for k in sensitive:
        row["extra"][k] = marker
    out = audit_backend.enforce_size(row)
    for k in sensitive:
        assert out["extra"][k] == "<redacted>"


def test_oversized_event_bounded(monkeypatch):
    monkeypatch.setenv("HARNESS_AUDIT_MAX_BYTES", "512")
    row = _row()
    row["extra"]["legacy_result_summary"] = "A" * 5000
    out = audit_backend.enforce_size(row)
    assert len(json.dumps(out).encode()) <= 4096  # hard-bounded
    assert out.get("_size_truncated") or out["extra"].get("_oversized_dropped_payload")


# ------------------------------ jsonl fallback ----------------------------- #
def test_jsonl_backend_default_no_dedup(tmp_path, monkeypatch):
    monkeypatch.delenv("HARNESS_AUDIT_BACKEND", raising=False)
    p = tmp_path / "runs.jsonl"
    be = audit_backend.JsonlBackend(str(p))
    audit_backend.write(_row(), backend=be)
    audit_backend.write(_row(), backend=be)  # identical -> NOT deduped in jsonl mode
    lines = [x for x in p.read_text().splitlines() if x.strip()]
    assert len(lines) == 2  # byte-identical historical behaviour preserved
    c = be.counts()
    assert c["total"] == 2 and c["backend"] == "jsonl"


def test_audit_record_jsonl_default_writes_file(tmp_path, monkeypatch):
    from app.agents.harness.contracts import RunContext

    monkeypatch.delenv("HARNESS_AUDIT_BACKEND", raising=False)
    monkeypatch.setattr(audit, "_RUN_LOG", str(tmp_path / "hr.jsonl"))
    audit.record(
        RunContext(agent="nikhil", run_id="r1"),
        None,
        None,
        kind="shadow",
        extra={"source_loop": "batch_harness", "mode": "shadow"},
    )
    data = (tmp_path / "hr.jsonl").read_text().strip().splitlines()
    assert len(data) == 1 and json.loads(data[0])["agent"] == "nikhil"


def test_audit_record_redis_path_dedups(monkeypatch):
    from app.agents.harness.contracts import RunContext

    store = {"kv": {}, "kv_ttl": {}, "streams": {}, "hashes": {}, "seq": [0]}
    monkeypatch.setenv("HARNESS_AUDIT_BACKEND", "redis")
    monkeypatch.setattr(audit_backend, "_get_redis_client", lambda: FakeRedis(store))
    ctx = RunContext(agent="nikhil", run_id="r1")
    ex = {
        "source_loop": "batch_harness",
        "resolved_tool_name": "t",
        "resolved_tool_version": "1.0.0",
        "item_id": "i1",
        "attempt": 0,
        "mode": "shadow",
    }
    audit.record(ctx, None, None, kind="shadow", extra=dict(ex))
    audit.record(ctx, None, None, kind="shadow", extra=dict(ex))  # duplicate
    assert audit_backend.get_backend().counts()["total"] == 1


# ------------------------- historical import (Option A) -------------------- #
def test_historical_import_idempotent():
    store = {"kv": {}, "kv_ttl": {}, "streams": {}, "hashes": {}, "seq": [0]}
    be = audit_backend.RedisBackend(FakeRedis(store))
    dag = _row(
        loop="dag_engine",
        tool="workflow.dag.internal_calculation",
        item=None,
        run="canary-dag-shadow-0001",
    )
    dag["extra"]["node_id"] = "calc"
    batch = _row(
        loop="batch_harness",
        tool="batch.internal.safe_calculation",
        item="canary-batch-1",
        run="canary_batch_shadow_0001",
    )
    for _ in range(2):  # import twice -> still exactly 2
        audit_backend.write(dag, backend=be)
        audit_backend.write(batch, backend=be)
    c = be.counts()
    assert c["total"] == 2
    assert c["by_family"].get("dag_engine") == 1
    assert c["by_family"].get("batch_harness") == 1


# ------------------------------- status surface ---------------------------- #
def test_status_counts_no_secrets(monkeypatch):
    store = {"kv": {}, "kv_ttl": {}, "streams": {}, "hashes": {}, "seq": [0]}
    monkeypatch.setenv("HARNESS_AUDIT_BACKEND", "redis")
    monkeypatch.setattr(audit_backend, "_get_redis_client", lambda: FakeRedis(store))
    audit_backend.write(_row(), backend=audit_backend.get_backend())
    st = audit_backend.status()
    assert st["backend"] == "redis"
    assert st["health"]["healthy"] is True
    assert st["counts"]["total"] == 1
    blob = json.dumps(st).lower()
    for bad in ("password", "secret", "token", "dsn", "authorization"):
        assert bad not in blob
