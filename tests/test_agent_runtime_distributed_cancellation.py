"""Race-boundary + shared-runtime distributed cancellation tests (memory backend)."""

from __future__ import annotations

import asyncio

import pytest

from app.platform import agent_runtime as rt
from app.platform import agent_runtime_cancellation as crc
from app.platform.agent_runtime import AgentCapability, AgentTask


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    monkeypatch.setattr(rt, "_STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setattr(rt, "_USAGE_PATH", str(tmp_path / "usage.json"))
    monkeypatch.setattr(rt, "_DLQ_PATH", str(tmp_path / "dlq.jsonl"))
    monkeypatch.setattr(rt, "_BACKOFF_BASE_S", 0.0)
    monkeypatch.setattr(rt, "_kill_engaged", lambda key: False)
    monkeypatch.setattr(rt, "_approval_approved", lambda tenant, ref: False)
    monkeypatch.setattr(rt, "_owner_admission_blocked", lambda aid: (False, ""))
    monkeypatch.setenv("AGENT_RUNTIME_CANCEL_BACKEND", "memory")
    monkeypatch.setenv("AGENT_RUNTIME_IDEM_BACKEND", "memory")
    from app.platform import agent_runtime_idempotency as arid

    crc.reset_memory_for_tests()
    arid.reset_memory_for_tests()
    rt._ACTIVE.clear()
    rt._ACTIVE_TASKS.clear()
    caps = dict(rt._CAPABILITIES)
    monkeypatch.setenv("AGENT_RUNTIME", "1")
    monkeypatch.setenv("OPS_HEALTH_AGENT", "1")
    monkeypatch.setenv("SRE_AGENT", "1")
    monkeypatch.setenv("DELIVERY_ASSURANCE_AGENT", "1")
    yield
    rt._CAPABILITIES.clear()
    rt._CAPABILITIES.update(caps)
    crc.reset_memory_for_tests()
    arid.reset_memory_for_tests()
    rt._ACTIVE.clear()
    rt._ACTIVE_TASKS.clear()


def _reg(agent: str, action: str, fn):
    rt.register_capability(AgentCapability(agent_id=agent, action=action, fn=fn))


async def test_cancel_before_lease_no_engine():
    ran = {"n": 0}

    async def cap(ctx):
        ran["n"] += 1
        return {}

    _reg("pranav", "cancel_probe", cap)
    task = AgentTask(agent_id="pranav", action="cancel_probe")
    rt.request_cancel_run("pranav", task.task_id)
    res = await rt.run_task(task)
    assert res.status == "cancelled"
    assert ran["n"] == 0
    assert "leased" not in (res.lifecycle or [])


async def test_cancel_after_slot_before_engine(monkeypatch):
    ran = {"n": 0}
    checks = {"n": 0}
    real = crc.is_requested

    def delayed(agent_id, runtime_run_id):
        checks["n"] += 1
        # Allow policy + pre-slot; block on post-slot / pre-engine checks
        if checks["n"] < 3:
            return crc.CancelCheck(status="not_requested")
        return real(agent_id, runtime_run_id)

    async def cap(ctx):
        ran["n"] += 1
        return {}

    _reg("pranav", "cancel_probe", cap)
    task = AgentTask(agent_id="pranav", action="cancel_probe")
    # Seed cancel so delayed checks eventually see it
    crc.request("pranav", task.task_id)
    monkeypatch.setattr(crc, "is_requested", delayed)
    res = await rt.run_task(task)
    assert res.status == "cancelled"
    assert ran["n"] == 0


async def test_cancel_immediately_before_engine(monkeypatch):
    ran = {"n": 0}
    real_blocked = rt._owner_admission_blocked

    async def cap(ctx):
        ran["n"] += 1
        return {}

    # Inject cancel after lease by hooking durable open
    async def open_then_cancel(task):
        rt.request_cancel_run(task.agent_id, task.task_id)
        return None

    monkeypatch.setattr(rt, "_durable_open", open_then_cancel)
    monkeypatch.setattr(rt, "_owner_admission_blocked", lambda aid: (False, ""))
    _reg("nikhil", "cancel_probe", cap)
    task = AgentTask(agent_id="nikhil", action="cancel_probe")
    res = await rt.run_task(task)
    assert res.status == "cancelled"
    assert ran["n"] == 0
    _ = real_blocked


async def test_cooperative_engine_checkpoint():
    async def cap(ctx):
        ctx.raise_if_cancelled()
        return {"should_not": True}

    _reg("pranav", "cancel_probe", cap)
    task = AgentTask(agent_id="pranav", action="cancel_probe")
    rt.request_cancel_run("pranav", task.task_id)
    # Cancel observed at policy — never reaches engine. Use mid-flight path:
    crc.clear("pranav", task.task_id)

    async def coop(ctx):
        rt.request_cancel_run(ctx.task.agent_id, ctx.task.task_id)
        ctx.raise_if_cancelled()
        return {}

    _reg("pranav", "coop_probe", coop)
    res = await rt.submit("pranav", "coop_probe")
    assert res.status == "cancelled"
    assert res.reason == "cancel_requested"


async def test_non_cooperative_completion_classified():
    async def cap(ctx):
        rt.request_cancel_run(ctx.task.agent_id, ctx.task.task_id)
        return {"done": 1}

    _reg("nikhil", "cancel_probe", cap)
    res = await rt.submit("nikhil", "cancel_probe")
    assert res.status == "succeeded"
    assert res.reason == "cancel_requested_but_engine_completed"


async def test_cancelled_run_does_not_retry_as_transient():
    attempts = {"n": 0}

    async def cap(ctx):
        attempts["n"] += 1
        raise RuntimeError("should not run")

    _reg("pranav", "cancel_probe", cap)
    task = AgentTask(agent_id="pranav", action="cancel_probe")
    rt.request_cancel_run("pranav", task.task_id)
    res = await rt.run_task(task)
    assert res.status == "cancelled"
    assert attempts["n"] == 0
    # New unrelated run identity still works
    res2 = await rt.submit("pranav", "cancel_probe")
    assert res2.status in ("failed", "succeeded", "blocked")  # engine may fail — but ran
    assert attempts["n"] >= 1


async def test_future_run_not_cancelled_by_prior_record():
    async def cap(ctx):
        return {"ok": True}

    _reg("pranav", "cancel_probe", cap)
    old = AgentTask(agent_id="pranav", action="cancel_probe")
    rt.request_cancel_run("pranav", old.task_id)
    res = await rt.submit("pranav", "cancel_probe")
    assert res.status == "succeeded"
    assert res.task_id != old.task_id


async def test_store_unavailable_blocks_before_engine(monkeypatch):
    async def cap(ctx):
        return {}

    _reg("pranav", "cancel_probe", cap)
    monkeypatch.setenv("AGENT_RUNTIME_CANCEL_BACKEND", "redis")
    monkeypatch.setattr(crc, "_sync_redis", lambda: (_ for _ in ()).throw(OSError("down")))
    task = AgentTask(agent_id="pranav", action="cancel_probe")
    res = await rt.run_task(task)
    assert res.status == "blocked"
    assert res.reason == "cancellation_store_unavailable"


def test_idempotency_backend_status_truthful():
    from app.platform import agent_runtime_idempotency as arid

    st = arid.backend_status()
    assert st["key_prefix"].startswith("agentrt:idem:")
    assert st.get("fail_open_on_redis_error") is False
    assert st["idempotency_backend"] in ("redis", "memory", "file")


async def test_owner_os_art_cancel_shape(monkeypatch):
    from app.platform import owner_agent_execution as oae

    monkeypatch.setenv("AGENT_RUNTIME_CANCEL_BACKEND", "memory")
    out = oae.request_cancel_running("pranav", "art_owner_os_01", by="owner", reason="unit")
    assert out["ok"] is True
    assert out["command_id"]
    assert out["targeted_run_ids"] == ["art_owner_os_01"]
    assert out["cancellation_backend"] == "memory"
    assert crc.is_requested("pranav", "art_owner_os_01").requested
