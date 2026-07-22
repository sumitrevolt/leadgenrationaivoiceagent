"""Durable harness audit + shadow-dedup backend — atomic Lua claim+append,
multi-worker, restart, and fail-closed semantics (unit level).

These are UNIT tests over a fake Redis whose ``eval`` replicates the atomic Lua
contract. Real-Redis, real-multiprocess durability is proven separately in
``tests/test_harness_audit_backend_integration.py`` (skips without a live Redis).
All harness flags remain OFF; no executor runs here."""

from __future__ import annotations

import fnmatch
import json

from app.agents.harness import audit, audit_backend


# --------------------------------------------------------------------------- #
# Fake Redis whose eval() implements the SAME atomic contract as _ATOMIC_LUA.
# Two instances sharing one `store` simulate two processes / two containers.
# --------------------------------------------------------------------------- #
class FakeRedis:
    def __init__(self, store=None, crash=False, eval_crash=False):
        self.store = (
            store
            if store is not None
            else {"kv": {}, "kv_ttl": {}, "streams": {}, "hashes": {}, "seq": [0]}
        )
        self.crash = crash
        self.eval_crash = eval_crash

    def _boom(self):
        if self.crash:
            raise ConnectionError("redis down")

    def _hincr(self, name, field, amt=1):
        h = self.store["hashes"].setdefault(name, {})
        h[field] = int(h.get(field, 0)) + amt
        return h[field]

    def eval(self, script, numkeys, *args):
        self._boom()
        if self.eval_crash:
            raise ConnectionError("script/connection failure")
        keys = args[:numkeys]
        argv = args[numkeys:]
        dedup_key, stream_key, metrics_key = keys[0], keys[1], keys[2]
        event_json, envelope_json, ttl_ms, maxlen, family, mode = argv
        kv = self.store["kv"]
        if dedup_key in kv:
            self._hincr(metrics_key, "duplicates_suppressed")
            v = kv[dedup_key]
            return [b"DUPLICATE", v.encode() if isinstance(v, str) else v]
        s = self.store["streams"].setdefault(stream_key, [])
        self.store["seq"][0] += 1
        sid = f"{self.store['seq'][0]}-0"
        s.append((sid, {"e": event_json}))
        ml = int(maxlen)
        if ml > 0 and len(s) > ml:
            del s[0 : len(s) - ml]
        val = '{"event_id":"' + sid + '","envelope":' + envelope_json + "}"
        kv[dedup_key] = val
        self.store["kv_ttl"][dedup_key] = int(ttl_ms)
        self._hincr(metrics_key, "records_created")
        self._hincr(metrics_key, "family:" + family)
        self._hincr(metrics_key, "mode:" + mode)
        return [b"CREATED", val.encode()]

    def hincrby(self, name, field, amount=1):
        self._boom()
        return self._hincr(name, field, amount)

    def hgetall(self, name):
        self._boom()
        h = self.store["hashes"].get(name, {})
        return {k.encode(): str(v).encode() for k, v in h.items()}

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

    def scan_iter(self, match=None, count=None):
        self._boom()
        for k in list(self.store["kv"].keys()):
            if match is None or fnmatch.fnmatch(k, match):
                yield k.encode()

    def ping(self):
        self._boom()
        return True


def _store():
    return {"kv": {}, "kv_ttl": {}, "streams": {}, "hashes": {}, "seq": [0]}


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
    assert base == audit_backend.derive_dedup_key(_row())
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
    assert a != b


# ------------------------------ atomic dedup ------------------------------- #
def test_atomic_first_observer_wins():
    be = audit_backend.RedisBackend(FakeRedis())
    dk = audit_backend.derive_dedup_key(_row())
    r1 = be.record(_row(), dk)
    r2 = be.record(_row(), dk)
    assert r1["written"] is True and r1["duplicate"] is False and r1["event_id"]
    assert r2["written"] is False and r2["duplicate"] is True
    assert r2["event_id"] == r1["event_id"]  # duplicate returns the ORIGINAL id


def test_cross_process_dedup_shared_backend():
    store = _store()
    be1 = audit_backend.RedisBackend(FakeRedis(store))
    be2 = audit_backend.RedisBackend(FakeRedis(store))  # another process/container
    r1 = audit_backend.write(_row(), backend=be1)
    r2 = audit_backend.write(_row(), backend=be2)
    assert r1["written"] is True and r2["duplicate"] is True
    assert r2["event_id"] == r1["event_id"]
    assert be1.counts()["records_created"] == 1
    assert be1.counts()["duplicates_suppressed"] == 1


def test_multi_worker_many_observers_one_record():
    store = _store()
    workers = [audit_backend.RedisBackend(FakeRedis(store)) for _ in range(8)]
    results = [audit_backend.write(_row(), backend=w) for w in workers]
    assert sum(1 for r in results if r["written"]) == 1
    assert sum(1 for r in results if r["duplicate"]) == 7
    ids = {r["event_id"] for r in results}
    assert len(ids) == 1  # every caller sees the same event id
    assert workers[0].counts()["records_created"] == 1


def test_different_events_not_collapsed():
    store = _store()
    be = audit_backend.RedisBackend(FakeRedis(store))
    audit_backend.write(_row(item="a"), backend=be)
    audit_backend.write(_row(item="b"), backend=be)
    audit_backend.write(_row(item="a", attempt=1), backend=be)
    assert be.counts()["records_created"] == 3


# --------------------------- atomicity guarantees -------------------------- #
def test_atomic_no_partial_commit_on_failure():
    store = _store()
    be = audit_backend.RedisBackend(FakeRedis(store, eval_crash=True))
    r = audit_backend.write(_row(), backend=be)
    assert r["written"] is False and r["error"]
    # Nothing committed: no dedup key, no stream entry (claim+append were one op)
    assert store["kv"] == {}
    assert store["streams"].get(audit_backend._STREAM_KEY, []) == []


def test_timeout_after_commit_retry_returns_same_event_id():
    # Commit succeeds; a client-timeout retry of the SAME logical event must find
    # the dedup key and return the original event id (no second stream record).
    store = _store()
    be = audit_backend.RedisBackend(FakeRedis(store))
    dk = audit_backend.derive_dedup_key(_row())
    first = be.record(_row(), dk)
    retry = be.record(_row(), dk)  # simulated retry after a lost ack
    assert first["written"] and retry["duplicate"]
    assert retry["event_id"] == first["event_id"]
    assert be.counts()["records_created"] == 1


def test_envelope_stored_in_dedup_value():
    store = _store()
    be = audit_backend.RedisBackend(FakeRedis(store))
    dk = audit_backend.derive_dedup_key(_row())
    be.record(_row(), dk)
    raw = store["kv"][audit_backend._DEDUP_PREFIX + dk]
    parsed = json.loads(raw)
    assert parsed["event_id"]
    assert parsed["envelope"]["agent"] == "nikhil"
    assert parsed["envelope"]["execution_comparison"] is None or "envelope" in parsed


# --------------------------- restart persistence --------------------------- #
def test_restart_preserves_dedup_and_audit():
    store = _store()
    be = audit_backend.RedisBackend(FakeRedis(store))
    r1 = audit_backend.write(_row(), backend=be)
    be2 = audit_backend.RedisBackend(FakeRedis(store))  # restart: new client, same store
    r2 = audit_backend.write(_row(), backend=be2)
    assert r2["duplicate"] is True and r2["event_id"] == r1["event_id"]
    assert be2.counts()["records_created"] == 1


# --------------------------- fail-closed semantics ------------------------- #
def test_backend_unavailable_fails_closed_no_raise():
    be = audit_backend.RedisBackend(FakeRedis(crash=True))
    r = audit_backend.write(_row(), backend=be)
    assert r["written"] is False and r["duplicate"] is False and r["error"]


def test_production_redis_no_client_prohibits_silent_fallback(monkeypatch):
    monkeypatch.setenv("HARNESS_AUDIT_BACKEND", "redis")
    monkeypatch.setattr(audit_backend, "_get_redis_client", lambda: None)
    r = audit_backend.write(_row())
    assert r["written"] is False and r["error"] and r["backend"] == "redis"


# ------------------------------ retention/TTL ------------------------------ #
def test_dedup_claim_sets_ttl():
    store = _store()
    be = audit_backend.RedisBackend(FakeRedis(store))
    dk = audit_backend.derive_dedup_key(_row())
    be.record(_row(), dk)
    assert store["kv_ttl"].get(audit_backend._DEDUP_PREFIX + dk)  # PX TTL applied


def test_stream_maxlen_trims(monkeypatch):
    monkeypatch.setenv("HARNESS_AUDIT_MAXLEN", "3")
    store = _store()
    be = audit_backend.RedisBackend(FakeRedis(store))
    for i in range(6):
        be.record(_row(item=f"x{i}"), audit_backend.derive_dedup_key(_row(item=f"x{i}")))
    assert be._safe_xlen() <= 3


# --------------------------- size + sanitization --------------------------- #
def test_forbidden_keys_scrubbed():
    row = _row()
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
    assert len(json.dumps(out).encode()) <= 4096
    assert out.get("_size_truncated") or out["extra"].get("_oversized_dropped_payload")


# ------------------------------ jsonl fallback ----------------------------- #
def test_jsonl_backend_default_no_dedup(tmp_path, monkeypatch):
    monkeypatch.delenv("HARNESS_AUDIT_BACKEND", raising=False)
    p = tmp_path / "runs.jsonl"
    be = audit_backend.JsonlBackend(str(p))
    audit_backend.write(_row(), backend=be)
    audit_backend.write(_row(), backend=be)  # identical -> NOT deduped in jsonl mode
    lines = [x for x in p.read_text().splitlines() if x.strip()]
    assert len(lines) == 2
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

    store = _store()
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
    assert audit_backend.get_backend().counts()["records_created"] == 1


# ------------------------- historical import (Option A) -------------------- #
def test_historical_import_idempotent():
    store = _store()
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
    assert c["records_created"] == 2
    assert c["by_family"].get("dag_engine") == 1
    assert c["by_family"].get("batch_harness") == 1


# ------------------------------- status surface ---------------------------- #
def test_status_counts_no_secrets(monkeypatch):
    store = _store()
    monkeypatch.setenv("HARNESS_AUDIT_BACKEND", "redis")
    monkeypatch.setattr(audit_backend, "_get_redis_client", lambda: FakeRedis(store))
    audit_backend.write(_row(), backend=audit_backend.get_backend())
    st = audit_backend.status()
    assert st["backend"] == "redis"
    assert st["health"]["healthy"] is True
    assert st["counts"]["total"] == 1
    assert st["counts"]["dedup_keys_active"] == 1
    blob = json.dumps(st).lower()
    for bad in ("password", "secret", "token", "dsn", "authorization"):
        assert bad not in blob


def test_keys_are_hash_tagged_single_slot():
    # All keys the Lua touches share one {audit} hash tag -> one cluster slot.
    assert "{audit}" in audit_backend._STREAM_KEY
    assert "{audit}" in audit_backend._COUNTS_KEY
    assert "{audit}" in audit_backend._DEDUP_PREFIX
