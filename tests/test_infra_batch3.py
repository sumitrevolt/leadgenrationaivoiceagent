"""Tests: infra batch-3 — dlq_retry, integration_health, file_lock, heavy-queue routing.

Hermetic (no real Redis/network) — fake redis object inject/monkeypatch.
"""

from __future__ import annotations

import asyncio
import json
import os

import pytest


# ---------------------------------------------------------------- fake redis
class FakeRedis:
    def __init__(self):
        self.lists: dict[str, list] = {}
        self.hashes: dict[str, dict] = {}
        self.kv: dict[str, str] = {}

    def rpop(self, k):
        lst = self.lists.get(k) or []
        return lst.pop() if lst else None

    def lpush(self, k, v):
        self.lists.setdefault(k, []).insert(0, v)

    def ltrim(self, k, a, b):
        if k in self.lists:
            self.lists[k] = self.lists[k][a : b + 1]

    def llen(self, k):
        return len(self.lists.get(k) or [])

    def lrange(self, k, a, b):
        return (self.lists.get(k) or [])[a : b + 1]

    def hincrby(self, k, f, n=1):
        h = self.hashes.setdefault(k, {})
        h[f] = int(h.get(f, 0)) + n
        return h[f]

    def incr(self, k):
        self.kv[k] = str(int(self.kv.get(k) or 0) + 1)
        return int(self.kv[k])

    def hgetall(self, k):
        return dict(self.hashes.get(k) or {})

    def ping(self):
        return True

    def expire(self, k, ttl):
        self.kv.setdefault(f"__ttl__{k}", ttl)
        return True

    def get(self, k):
        return self.kv.get(k)

    def set(self, k, v, nx=False, ex=None):
        if nx and k in self.kv:
            return None
        self.kv[k] = v
        return True

    def setex(self, k, ttl, v):
        self.kv[k] = v
        return True

    def delete(self, k):
        self.lists.pop(k, None)
        self.hashes.pop(k, None)
        self.kv.pop(k, None)


# ---------------------------------------------------------------- dlq_retry
def test_dlq_parse_staff_job():
    from app.platform import dlq_retry

    assert dlq_retry.parse_staff_job({"args": "('content',)"}) == "content"
    assert dlq_retry.parse_staff_job({"args": '["qa"]'}) == "qa"
    assert dlq_retry.parse_staff_job({"args": "('not_a_job',)"}) is None
    assert dlq_retry.parse_staff_job({"args": ""}) is None


def test_dlq_sweep_flag_off_noop():
    from app.platform import dlq_retry

    os.environ.pop("DLQ_AUTO_RETRY", None)
    out = asyncio.run(dlq_retry.run_sweep(r=FakeRedis()))
    assert out["enabled"] is False
    assert out["retried"] == [] and out["dead"] == []


def test_dlq_sweep_retries_then_dead(monkeypatch):
    from app.platform import dlq_retry

    monkeypatch.setenv("DLQ_AUTO_RETRY", "1")
    monkeypatch.setenv("RUN_IN_PROCESS_SCHEDULER", "1")  # in-process dispatch path

    dispatched = []

    async def fake_run_job(job):
        dispatched.append(job)

    from app.platform import team_scheduler

    monkeypatch.setattr(team_scheduler, "_run_job", fake_run_job)

    r = FakeRedis()
    rec = {"task_id": "t1", "error": "boom", "args": "('content',)", "kwargs": "{}"}
    # attempt 1 + 2 = retry; attempt 3 = dead
    for _ in range(3):
        r.lpush(dlq_retry.DLQ_KEY, json.dumps(rec))
        out = asyncio.run(dlq_retry.run_sweep(r=r))
    assert dispatched == ["content", "content"]  # 2 retries
    assert out["dead"] == ["content"]
    assert r.llen(dlq_retry.DEAD_KEY) == 1


def test_dlq_sweep_unknown_task_goes_dead(monkeypatch):
    from app.platform import dlq_retry

    monkeypatch.setenv("DLQ_AUTO_RETRY", "1")
    r = FakeRedis()
    r.lpush(dlq_retry.DLQ_KEY, json.dumps({"task_id": "x", "args": "('legacy_call_task',)"}))
    out = asyncio.run(dlq_retry.run_sweep(r=r))
    assert out["skipped"] == 1
    assert r.llen(dlq_retry.DEAD_KEY) == 1  # blind retry NAHI — side-effect safe


def test_dlq_retry_counts_are_per_job(monkeypatch):
    """Per-job Redis keys: one job's incr must not share / reset another's TTL bucket."""
    from app.platform import dlq_retry

    monkeypatch.setenv("DLQ_AUTO_RETRY", "1")
    monkeypatch.setenv("RUN_IN_PROCESS_SCHEDULER", "1")

    async def fake_run_job(_job):
        return True

    from app.platform import team_scheduler

    monkeypatch.setattr(team_scheduler, "_run_job", fake_run_job)

    r = FakeRedis()
    r.lpush(dlq_retry.DLQ_KEY, json.dumps({"args": "('content',)", "error": "a"}))
    r.lpush(dlq_retry.DLQ_KEY, json.dumps({"args": "('qa',)", "error": "b"}))
    out = asyncio.run(dlq_retry.run_sweep(r=r, max_items=10))
    assert {x["job"] for x in out["retried"]} == {"content", "qa"}
    assert r.get(f"{dlq_retry.COUNT_KEY_PREFIX}content") == "1"
    assert r.get(f"{dlq_retry.COUNT_KEY_PREFIX}qa") == "1"
    # shared hash must NOT be the write path anymore
    assert r.hgetall(dlq_retry.COUNTS_KEY) == {}


# ---------------------------------------------------------- integration_health
def test_integration_health_counters(monkeypatch):
    from app.platform import integration_health as ih

    fake = FakeRedis()
    monkeypatch.setattr(ih, "_redis", lambda: fake)
    ih.record_failure("smtp", "auth failed")
    ih.record_failure("smtp")
    ih.record_success("smtp")
    snap = ih.snapshot(hours=2)
    s = snap["integrations"]["smtp"]
    assert s["fail"] == 2 and s["ok"] == 1
    assert s["last_error"] == "auth failed"


def test_integration_health_watch_alerts_gated(monkeypatch):
    from app.platform import integration_health as ih

    fake = FakeRedis()
    monkeypatch.setattr(ih, "_redis", lambda: fake)
    monkeypatch.delenv("INTEGRATION_ALERTS", raising=False)
    for _ in range(6):
        ih.record_failure("exotel", "500")
    out = asyncio.run(ih.run_watch())
    # flag OFF = koi alert nahi, par fails visible
    assert out["enabled"] is False
    assert out["recent_fails"].get("exotel", 0) >= 5
    assert out["alerted"] == []


def test_integration_health_never_raises_without_redis(monkeypatch):
    from app.platform import integration_health as ih

    def boom():
        raise ConnectionError("no redis")

    monkeypatch.setattr(ih, "_redis", boom)
    ih.record_failure("smtp")  # no raise
    ih.record_success("smtp")  # no raise
    snap = ih.snapshot()
    assert snap["redis_status"] == "unavailable"
    assert snap["degraded"] is True
    assert snap["reason"] == "acquisition_failed"
    assert snap["error_type"] == "ConnectionError"
    assert "error" not in snap  # exception messages may contain Redis credentials


# ---------------------------------------------------------------- file_lock
def test_locked_append_and_rewrite(tmp_path):
    from app.utils.file_lock import locked_append, locked_rewrite

    p = str(tmp_path / "store.jsonl")
    assert locked_append(p, json.dumps({"a": 1}))
    assert locked_append(p, json.dumps({"a": 2}))
    lines = open(p, encoding="utf-8").read().splitlines()
    assert len(lines) == 2
    assert locked_rewrite(p, json.dumps({"only": True}) + "\n")
    lines = open(p, encoding="utf-8").read().splitlines()
    assert lines == [json.dumps({"only": True})]
    # atomic rewrite ke baad koi .tmp leftovers nahi
    assert not [f for f in os.listdir(tmp_path) if ".tmp." in f]


def test_file_lock_context(tmp_path):
    from app.utils.file_lock import file_lock

    p = str(tmp_path / "x.json")
    with file_lock(p) as locked:
        # platform pe lock primitive ho to locked True hona chahiye
        assert locked in (True, False)
    # lock file ban gayi par store untouched
    assert not os.path.exists(p)


# ------------------------------------------------------------- heavy routing
def test_heavy_queue_routing_flag(monkeypatch):
    from app import worker

    name = "app.tasks.staff_jobs.run_staff_job"
    # flag OFF (default) = None (default queue)
    monkeypatch.delenv("CELERY_HEAVY_QUEUE", raising=False)
    assert worker._route_staff_task(name, ("qa",), {}, {}) is None
    # flag ON: heavy job → heavy queue; light job → default
    monkeypatch.setenv("CELERY_HEAVY_QUEUE", "1")
    assert worker._route_staff_task(name, ("qa",), {}, {}) == {"queue": "heavy"}
    assert worker._route_staff_task(name, ("content",), {}, {}) == {"queue": "heavy"}
    assert worker._route_staff_task(name, ("watchdog",), {}, {}) is None
    # non-staff task kabhi route nahi hota
    assert worker._route_staff_task("app.tasks.calling.make_call", ("qa",), {}, {}) is None


def test_sales_pipeline_locked_write(tmp_path, monkeypatch):
    """_write_all ab locked_rewrite use karta — file valid jsonl rehni chahiye."""
    from app.marketing import sales_pipeline as sp

    p = str(tmp_path / "deals.jsonl")
    rows = [{"id": "d1", "stage": "new"}, {"id": "d2", "stage": "won"}]
    sp._write_all(p, rows)
    got = [json.loads(line) for line in open(p, encoding="utf-8") if line.strip()]
    assert got == rows
