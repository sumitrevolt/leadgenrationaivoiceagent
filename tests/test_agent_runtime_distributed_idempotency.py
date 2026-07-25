"""Distributed idempotency race + runtime integration (memory backend)."""

from __future__ import annotations

import pytest

from app.platform import agent_runtime as rt
from app.platform import agent_runtime_idempotency as arid
from app.platform.agent_runtime import AgentCapability


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    monkeypatch.setattr(rt, "_STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setattr(rt, "_USAGE_PATH", str(tmp_path / "usage.json"))
    monkeypatch.setattr(rt, "_DLQ_PATH", str(tmp_path / "dlq.jsonl"))
    monkeypatch.setattr(rt, "_BACKOFF_BASE_S", 0.0)
    monkeypatch.setattr(rt, "_kill_engaged", lambda key: False)
    monkeypatch.setattr(rt, "_approval_approved", lambda tenant, ref: False)
    monkeypatch.setattr(rt, "_owner_admission_blocked", lambda aid: (False, ""))
    monkeypatch.setenv("AGENT_RUNTIME_IDEM_BACKEND", "memory")
    monkeypatch.setenv("AGENT_RUNTIME_CANCEL_BACKEND", "memory")
    from app.platform import agent_runtime_cancellation as crc

    crc.reset_memory_for_tests()
    arid.reset_memory_for_tests()
    rt._ACTIVE.clear()
    rt._ACTIVE_TASKS.clear()
    caps = dict(rt._CAPABILITIES)
    monkeypatch.setenv("AGENT_RUNTIME", "1")
    monkeypatch.setenv("SRE_AGENT", "1")
    monkeypatch.setenv("DELIVERY_ASSURANCE_AGENT", "1")
    monkeypatch.setenv("OPS_HEALTH_AGENT", "1")
    yield
    rt._CAPABILITIES.clear()
    rt._CAPABILITIES.update(caps)
    arid.reset_memory_for_tests()
    crc.reset_memory_for_tests()


def _reg(agent, action, fn):
    rt.register_capability(AgentCapability(agent_id=agent, action=action, fn=fn))


async def test_pranav_duplicate_one_engine():
    n = {"c": 0}

    async def cap(ctx):
        n["c"] += 1
        return {"ok": True}

    _reg("pranav", "idem_probe", cap)
    a = await rt.submit("pranav", "idem_probe", idempotency_key="p-dup-1")
    b = await rt.submit("pranav", "idem_probe", idempotency_key="p-dup-1")
    assert a.status == "succeeded"
    assert b.status == "skipped" and b.reason == "duplicate_suppressed"
    assert n["c"] == 1
    assert b.output.get("original_run_id") == a.task_id


async def test_nikhil_duplicate_shared_store():
    n = {"c": 0}

    async def cap(ctx):
        n["c"] += 1
        return {"ok": True}

    _reg("nikhil", "idem_probe", cap)
    a = await rt.submit("nikhil", "idem_probe", idempotency_key="n-dup-1")
    b = await rt.submit("nikhil", "idem_probe", idempotency_key="n-dup-1")
    assert a.status == "succeeded" and b.reason == "duplicate_suppressed"
    assert n["c"] == 1


async def test_store_unavailable_blocks_before_engine(monkeypatch):
    n = {"c": 0}

    async def cap(ctx):
        n["c"] += 1
        return {}

    _reg("pranav", "idem_probe", cap)
    monkeypatch.setenv("AGENT_RUNTIME_IDEM_BACKEND", "redis")
    monkeypatch.setattr(arid, "_sync_redis", lambda: (_ for _ in ()).throw(OSError("down")))
    res = await rt.submit("pranav", "idem_probe", idempotency_key="unavail-1")
    assert res.status == "blocked"
    assert res.reason == "idempotency_store_unavailable"
    assert n["c"] == 0


async def test_cancel_terminal_then_duplicate(monkeypatch):
    async def cap(ctx):
        return {"should_not": True}

    async def open_then_cancel(task):
        rt.request_cancel_run(task.agent_id, task.task_id)
        return None

    monkeypatch.setattr(rt, "_durable_open", open_then_cancel)
    _reg("pranav", "idem_probe", cap)
    r1 = await rt.submit("pranav", "idem_probe", idempotency_key="cxl-1")
    assert r1.status == "cancelled"

    async def _noop_open(task):
        return None

    monkeypatch.setattr(rt, "_durable_open", _noop_open)
    r2 = await rt.submit("pranav", "idem_probe", idempotency_key="cxl-1")
    assert r2.status == "skipped"
    assert r2.reason == "duplicate_suppressed"


async def test_blocked_control_releases_key():
    # Control-blocked / release path: drop in-progress claim, then succeed
    arid.claim("pranav", "idem_probe", "blk-1", runtime_run_id="art_blk00000001")
    arid.release("pranav", "idem_probe", "blk-1")

    async def cap(ctx):
        return {"ran": True}

    _reg("pranav", "idem_probe", cap)
    res = await rt.submit("pranav", "idem_probe", idempotency_key="blk-1")
    assert res.status == "succeeded"


async def test_new_key_after_failure():
    async def boom(ctx):
        raise RuntimeError("x")

    _reg("pranav", "idem_probe", boom)
    r1 = await rt.submit("pranav", "idem_probe", idempotency_key="fail-1")
    assert r1.status == "failed"
    r2 = await rt.submit("pranav", "idem_probe", idempotency_key="fail-1")
    assert r2.reason == "duplicate_suppressed"

    async def ok(ctx):
        return {"ok": 1}

    _reg("pranav", "idem_probe", ok)
    r3 = await rt.submit("pranav", "idem_probe", idempotency_key="fail-1-new")
    assert r3.status == "succeeded"
