"""Durable harness audit backend — authoritative single-write model, strict config,
status semantics, and guarded migration (unit level over a fake Redis).

Real-Redis / real-multiprocess durability runs in
tests/test_harness_audit_backend_integration.py (mandatory in CI). All harness
flags remain OFF; no executor runs here."""

from __future__ import annotations

import fnmatch
import json

import pytest

from app.agents.harness import audit, audit_backend, audit_migrate


# --------------------------------------------------------------------------- #
# Fake Redis supporting SET ... NX GET PX and the derived-index ops.
# Two instances sharing one `store` simulate two processes/containers.
# --------------------------------------------------------------------------- #
class FakeRedis:
    def __init__(self, store=None, crash=False, poison_metrics=False):
        self.store = (
            store
            if store is not None
            else {"kv": {}, "kv_ttl": {}, "streams": {}, "hashes": {}, "seq": [0]}
        )
        self.crash = crash
        self.poison_metrics = poison_metrics

    def _boom(self):
        if self.crash:
            raise ConnectionError("redis down")

    def set(self, name, value, nx=False, get=False, px=None):
        self._boom()
        kv = self.store["kv"]
        existed = name in kv
        old = kv.get(name)
        if nx and existed:
            return old if get else None  # not set; GET returns existing
        kv[name] = value
        if px:
            self.store["kv_ttl"][name] = px
        return (old if existed else None) if get else True

    def get(self, name):
        self._boom()
        return self.store["kv"].get(name)

    def delete(self, name):
        self.store["kv"].pop(name, None)
        self.store["hashes"].pop(name, None)
        return 1

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
        return [(sid.encode(), {k.encode(): v.encode() for k, v in f.items()}) for sid, f in s]

    def hincrby(self, name, field, amount=1):
        self._boom()
        if self.poison_metrics and name == audit_backend._METRICS_KEY:
            raise TypeError("WRONGTYPE metrics poisoned")
        h = self.store["hashes"].setdefault(name, {})
        h[field] = int(h.get(field, 0)) + amount
        return h[field]

    def hset(self, name, field, value):
        h = self.store["hashes"].setdefault(name, {})
        h[field] = value
        return 1

    def hgetall(self, name):
        self._boom()
        return {k.encode(): str(v).encode() for k, v in self.store["hashes"].get(name, {}).items()}

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


# ------------------------------ strict config ------------------------------ #
def test_config_resolution(monkeypatch):
    monkeypatch.delenv("HARNESS_AUDIT_BACKEND", raising=False)
    assert audit_backend.resolve_backend_config()["resolved_backend"] == "jsonl"
    monkeypatch.setenv("HARNESS_AUDIT_BACKEND", "jsonl")
    assert audit_backend.backend_name() == "jsonl"
    monkeypatch.setenv("HARNESS_AUDIT_BACKEND", "redis")
    assert audit_backend.backend_name() == "redis"
    for bad in ("redi", "redis ", "postgres", "REDISX"):
        monkeypatch.setenv("HARNESS_AUDIT_BACKEND", bad)
        c = audit_backend.resolve_backend_config()
        assert c["resolved_backend"] == "invalid" and c["configuration_valid"] is False


def test_invalid_backend_fails_closed_no_silent_jsonl(monkeypatch):
    monkeypatch.setenv("HARNESS_AUDIT_BACKEND", "postgres")
    be = audit_backend.get_backend()
    assert isinstance(be, audit_backend.InvalidBackend)
    r = audit_backend.write(_row(), backend=be)
    assert r["written"] is False and r["error"] and r["backend"] == "invalid"


# ---------------------- authoritative single-write model ------------------- #
def test_authoritative_create_and_duplicate():
    be = audit_backend.RedisBackend(FakeRedis())
    dk = audit_backend.derive_dedup_key(_row())
    r1 = be.record(_row(), dk)
    r2 = be.record(_row(), dk)
    assert r1["written"] and not r1["duplicate"] and r1["event_id"] == dk
    assert not r2["written"] and r2["duplicate"] and r2["event_id"] == dk


def test_record_value_shape():
    store = _store()
    be = audit_backend.RedisBackend(FakeRedis(store))
    dk = audit_backend.derive_dedup_key(_row())
    be.record(_row(), dk, source_app_version="878c1397")
    rec = json.loads(store["kv"][audit_backend._RECORD_PREFIX + dk])
    assert rec["event_id"] == dk
    assert rec["event"]["agent"] == "nikhil"
    assert rec["envelope"]["agent"] == "nikhil"
    assert rec["source_app_version"] == "878c1397"
    assert "created_at" in rec


def test_partial_commit_impossible_metrics_poison():
    # Poison metrics so the DERIVED index hincrby raises. The authoritative record
    # must still be created and reported written=True (all-or-nothing decoupled).
    store = _store()
    be = audit_backend.RedisBackend(FakeRedis(store, poison_metrics=True))
    dk = audit_backend.derive_dedup_key(_row())
    r = be.record(_row(), dk)
    assert r["written"] is True and r["duplicate"] is False
    assert audit_backend._RECORD_PREFIX + dk in store["kv"]  # record durable


def test_record_write_failure_leaves_nothing():
    store = _store()

    class FailSet(FakeRedis):
        def set(self, *a, **k):
            raise ConnectionError("down")

    be = audit_backend.RedisBackend(FailSet(store))
    r = audit_backend.write(_row(), backend=be)
    assert r["written"] is False and r["error"]
    assert store["kv"] == {}  # nothing created


def test_retention_at_least_90_days(monkeypatch):
    monkeypatch.delenv("HARNESS_AUDIT_RETENTION_S", raising=False)
    assert audit_backend.audit_retention_s() >= 90 * 24 * 3600
    store = _store()
    be = audit_backend.RedisBackend(FakeRedis(store))
    dk = audit_backend.derive_dedup_key(_row())
    be.record(_row(), dk)
    assert store["kv_ttl"][audit_backend._RECORD_PREFIX + dk] >= 90 * 24 * 3600 * 1000


# --------------------------- multi-worker / restart ------------------------ #
def test_cross_process_one_record():
    store = _store()
    ws = [audit_backend.RedisBackend(FakeRedis(store)) for _ in range(8)]
    res = [audit_backend.write(_row(), backend=w) for w in ws]
    assert sum(1 for r in res if r["written"]) == 1
    assert sum(1 for r in res if r["duplicate"]) == 7
    assert len({r["event_id"] for r in res}) == 1
    assert ws[0].counts()["authoritative_records"] == 1


def test_restart_preserves_record():
    store = _store()
    be = audit_backend.RedisBackend(FakeRedis(store))
    r1 = audit_backend.write(_row(), backend=be)
    be2 = audit_backend.RedisBackend(FakeRedis(store))
    r2 = audit_backend.write(_row(), backend=be2)
    assert r2["duplicate"] and r2["event_id"] == r1["event_id"]
    assert be2.counts()["authoritative_records"] == 1


def test_distinct_events_distinct_records():
    store = _store()
    be = audit_backend.RedisBackend(FakeRedis(store))
    for i in range(5):
        audit_backend.write(_row(item=f"x{i}"), backend=be)
    assert be.counts()["authoritative_records"] == 5


# ------------------------------- reconciler -------------------------------- #
def test_reconcile_rebuilds_index():
    store = _store()
    r = FakeRedis(store)
    be = audit_backend.RedisBackend(r)
    for i in range(3):
        be.record(_row(item=f"x{i}"), audit_backend.derive_dedup_key(_row(item=f"x{i}")))
    store["streams"][audit_backend._STREAM_KEY] = []  # simulate lost/lagged index
    store["hashes"].pop(audit_backend._METRICS_KEY, None)
    dry = be.reconcile(dry_run=True)
    assert dry["authoritative_records"] == 3 and dry["missing_stream_entries"] == 3
    live = be.reconcile(dry_run=False)
    assert live["missing_stream_entries"] == 3
    assert be._safe_xlen() == 3
    assert be.counts()["by_family"].get("batch_harness") == 3


# ---------------------------- status semantics ----------------------------- #
def test_status_semantics_jsonl(monkeypatch, tmp_path):
    monkeypatch.setenv("HARNESS_AUDIT_BACKEND", "jsonl")
    monkeypatch.setenv("HARNESS_RUN_LOG", str(tmp_path / "h.jsonl"))
    st = audit_backend.status()
    h = st["health"]
    assert st["backend"] == "jsonl" and st["configuration_valid"] is True
    assert h["selected_intentionally"] and h["fallback_active"] is False
    assert h["durable"] is False and h["multi_worker_safe"] is False


def test_status_semantics_invalid(monkeypatch):
    monkeypatch.setenv("HARNESS_AUDIT_BACKEND", "postgres")
    st = audit_backend.status()
    assert st["backend"] == "invalid" and st["configuration_valid"] is False
    assert st["health"]["healthy"] is False


def test_status_semantics_redis(monkeypatch):
    store = _store()
    monkeypatch.setenv("HARNESS_AUDIT_BACKEND", "redis")
    monkeypatch.setattr(audit_backend, "_get_redis_client", lambda: FakeRedis(store))
    audit_backend.write(_row(), backend=audit_backend.get_backend())
    st = audit_backend.status()
    assert st["backend"] == "redis"
    assert st["health"]["durable"] is True and st["health"]["multi_worker_safe"] is True
    assert st["counts"]["authoritative_records"] == 1


# ------------------------- provenance / dedup identity --------------------- #
def test_dedup_uses_source_app_version_for_migration(monkeypatch):
    monkeypatch.setenv("APP_VERSION", "67a18b0_runtime")
    live = audit_backend.derive_dedup_key(_row())
    hist = audit_backend.derive_dedup_key(_row(), source_app_version="878c1397_source")
    assert live != hist  # migration identity uses ORIGINAL provenance, not runtime


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
    assert len(data) == 1


# ------------------------------- migration CLI ----------------------------- #
_DAG = {
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
_BATCH = {
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
_SRC_SHA = "0" * 40


def _write_src(tmp_path):
    import hashlib

    p = tmp_path / "harness_runs.jsonl"
    body = (json.dumps(_DAG) + "\n" + json.dumps(_BATCH) + "\n").encode()
    p.write_bytes(body)
    return str(p), hashlib.sha256(body).hexdigest()


def test_migration_dry_run_zero_writes(tmp_path):
    src, chk = _write_src(tmp_path)
    store = _store()
    be = audit_backend.RedisBackend(FakeRedis(store))
    pv = audit_migrate.preview(src, _SRC_SHA, backend=be)
    assert pv["source_count"] == 2 and pv["source_checksum"] == chk
    assert pv["source_family_breakdown"] == {"dag_engine": 1, "batch_harness": 1}
    assert len(pv["derived_record_keys"]) == 2
    assert store["kv"] == {}  # ZERO writes on preview


def test_migration_apply_idempotent(tmp_path):
    src, chk = _write_src(tmp_path)
    store = _store()
    be = audit_backend.RedisBackend(FakeRedis(store))
    r1 = audit_migrate.apply(src, "tok", chk, _SRC_SHA, backend=be)
    assert r1["records_created"] == 2 and r1["already_existing"] == 0
    r2 = audit_migrate.apply(src, "tok", chk, _SRC_SHA, backend=be)
    assert r2["records_created"] == 0 and r2["already_existing"] == 2  # idempotent


def test_migration_refuses_wrong_checksum(tmp_path):
    src, _chk = _write_src(tmp_path)
    be = audit_backend.RedisBackend(FakeRedis(_store()))
    with pytest.raises(SystemExit):
        audit_migrate.apply(src, "tok", "deadbeef" * 8, _SRC_SHA, backend=be)


def test_migration_refuses_missing_guards(tmp_path):
    src, chk = _write_src(tmp_path)
    be = audit_backend.RedisBackend(FakeRedis(_store()))
    with pytest.raises(SystemExit):
        audit_migrate.apply(src, "", chk, _SRC_SHA, backend=be)  # no token
    with pytest.raises(SystemExit):
        audit_migrate.apply(src, "tok", chk, "short", backend=be)  # bad source sha


def test_migration_uses_source_provenance(tmp_path):
    src, chk = _write_src(tmp_path)
    store = _store()
    be = audit_backend.RedisBackend(FakeRedis(store))
    audit_migrate.apply(src, "tok", chk, _SRC_SHA, backend=be)
    # keys must be derived under the SOURCE sha, not the runtime sha
    dag_key = audit_backend.derive_dedup_key(_DAG, source_app_version=_SRC_SHA)
    assert audit_backend._RECORD_PREFIX + dag_key in store["kv"]


def test_keys_hash_tagged_single_slot():
    for k in (
        audit_backend._RECORD_PREFIX,
        audit_backend._STREAM_KEY,
        audit_backend._METRICS_KEY,
        audit_backend._MIGRATION_PREFIX,
    ):
        assert "{audit}" in k
