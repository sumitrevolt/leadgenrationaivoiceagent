"""Shared agent-runtime Owner OS control admission (pause/drain/stop-claims).

Proves the production gap: control records existed but submit ignored them.
All checks use the shared runtime path — not Pranav-only hardcoding.
"""

from __future__ import annotations

import pytest

from app.platform import agent_runtime as rt
from app.platform import owner_agent_execution as oae
from app.platform import owner_os
from app.platform import owner_os_store as store
from app.platform.agent_runtime import AgentCapability


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(rt, "_STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setattr(rt, "_USAGE_PATH", str(tmp_path / "usage.json"))
    monkeypatch.setattr(rt, "_DLQ_PATH", str(tmp_path / "dlq.jsonl"))
    monkeypatch.setattr(rt, "_BACKOFF_BASE_S", 0.0)
    monkeypatch.setattr(rt, "_kill_engaged", lambda key: False)
    monkeypatch.setattr(rt, "_approval_approved", lambda tenant, ref: False)

    monkeypatch.setenv("OWNER_OS_STORAGE", "jsonl")
    store.reset_storage_mode()
    monkeypatch.setattr(oae, "CONTROL_STORE", str(tmp_path / "agent_controls.jsonl"))
    monkeypatch.setattr(owner_os, "_CMD_STORE", str(tmp_path / "cmds.jsonl"))
    monkeypatch.setattr(owner_os, "_KILL_STORE", str(tmp_path / "kills.jsonl"))
    monkeypatch.setattr(owner_os, "_AUDIT_STORE", str(tmp_path / "audit.jsonl"))
    monkeypatch.setattr(store, "CMD_STORE", str(tmp_path / "cmds.jsonl"))
    monkeypatch.setattr(store, "KILL_STORE", str(tmp_path / "kills.jsonl"))
    monkeypatch.setattr(store, "AUDIT_STORE", str(tmp_path / "audit.jsonl"))
    from app.platform import agent_controls as ac

    monkeypatch.setattr(ac, "_STORE", str(tmp_path / "pause.jsonl"))

    caps_snapshot = dict(rt._CAPABILITIES)
    monkeypatch.setenv("AGENT_RUNTIME_CANCEL_BACKEND", "memory")
    monkeypatch.setenv("AGENT_RUNTIME_IDEM_BACKEND", "memory")
    from app.platform import agent_runtime_cancellation as crc
    from app.platform import agent_runtime_idempotency as arid

    crc.reset_memory_for_tests()
    arid.reset_memory_for_tests()
    rt._ACTIVE.clear()
    rt._ACTIVE_TASKS.clear()

    monkeypatch.setenv("AGENT_RUNTIME", "1")
    monkeypatch.setenv("OPS_HEALTH_AGENT", "1")
    monkeypatch.setenv("AFTERNOON_CONTENT", "1")
    monkeypatch.setenv("SRE_AGENT", "1")
    yield
    rt._CAPABILITIES.clear()
    rt._CAPABILITIES.update(caps_snapshot)
    crc.reset_memory_for_tests()
    arid.reset_memory_for_tests()
    rt._ACTIVE.clear()
    rt._ACTIVE_TASKS.clear()


def _register(agent_id: str, action: str, fn, **kw):
    rt.register_capability(AgentCapability(agent_id=agent_id, action=action, fn=fn, **kw))


async def _ok(ctx):
    ctx.add_usage(api_calls=1)
    return {"done": True}


# ---- pause ---------------------------------------------------------------- #


async def test_pause_blocks_submit_reason_and_no_engine():
    ran = {"n": 0}

    async def cap(ctx):
        ran["n"] += 1
        return {"done": True}

    _register("kavya", "ctrl_probe", cap)
    oae.set_control("kavya", by="t", reason="unit", manual_pause=True)
    res = await rt.submit("kavya", "ctrl_probe")
    assert res.status == "blocked"
    assert res.reason == "agent_paused"
    assert res.decision and res.decision["reason_code"] == "agent_paused"
    assert res.decision["control_source"] == "owner_os"
    assert ran["n"] == 0
    assert "leased" not in res.lifecycle


async def test_pause_resume_single_execution_no_flood():
    _register("kavya", "ctrl_probe", _ok)
    oae.set_control("kavya", by="t", reason="unit", manual_pause=True)
    blocked = await rt.submit("kavya", "ctrl_probe", idempotency_key="pause-idem-1")
    assert blocked.status == "blocked" and blocked.reason == "agent_paused"
    oae.resume("kavya", by="t", reason="done")
    ok = await rt.submit("kavya", "ctrl_probe", idempotency_key="pause-idem-1")
    assert ok.status == "succeeded"
    dup = await rt.submit("kavya", "ctrl_probe", idempotency_key="pause-idem-1")
    assert dup.status == "skipped" and dup.reason == "duplicate_suppressed"


# ---- drain / stop-claims -------------------------------------------------- #


async def test_drain_blocks_new_submit():
    _register("pranav", "ctrl_probe", _ok)
    oae.set_control("pranav", by="t", reason="drain", drain=True)
    res = await rt.submit("pranav", "ctrl_probe")
    assert res.status == "blocked"
    assert res.reason == "agent_draining"
    assert oae.runtime_admission_blocked("pranav")[1] == "agent_draining"


async def test_stop_claims_alone_reason(monkeypatch):
    _register("isha", "ctrl_probe", _ok)
    oae.set_control("isha", by="t", reason="sc", stop_claims=True)
    # Ensure drain not set (drain would win reason).
    ctrl = oae.get_control("isha")
    assert ctrl["stop_claims"] is True and ctrl["drain"] is False
    res = await rt.submit("isha", "ctrl_probe", tenant_id="t1")
    assert res.status == "blocked"
    assert res.reason == "agent_claims_stopped"


async def test_clear_drain_restores_execution():
    _register("pranav", "ctrl_probe", _ok)
    oae.set_control("pranav", by="t", drain=True, reason="x")
    assert (await rt.submit("pranav", "ctrl_probe")).status == "blocked"
    oae.resume("pranav", by="t")
    assert (await rt.submit("pranav", "ctrl_probe")).status == "succeeded"


# ---- kill / flags / cancel ------------------------------------------------ #


async def test_kill_still_blocks_with_structured_decision(monkeypatch):
    monkeypatch.setattr(rt, "_kill_engaged", lambda key: key == "owner_all_agents")
    _register("kavya", "ctrl_probe", _ok)
    res = await rt.submit("kavya", "ctrl_probe")
    assert res.status == "blocked"
    assert res.reason == "kill_switch_engaged:owner_all_agents"
    assert res.decision["reason_code"] == "kill_switch_active"


async def test_runtime_flag_blocks_before_claim(monkeypatch):
    monkeypatch.setenv("AGENT_RUNTIME", "0")
    ran = {"n": 0}

    async def cap(ctx):
        ran["n"] += 1
        return {}

    _register("kavya", "ctrl_probe", cap)
    res = await rt.submit("kavya", "ctrl_probe")
    assert res.status == "skipped"
    assert res.reason.startswith("runtime_flag_disabled")
    assert ran["n"] == 0


async def test_cancel_before_engine():
    ran = {"n": 0}

    async def cap(ctx):
        ran["n"] += 1
        return {}

    _register("kavya", "ctrl_probe", cap)
    task = rt.AgentTask(agent_id="kavya", action="ctrl_probe")
    rt.request_cancel_run("kavya", task.task_id)
    res = await rt.run_task(task)
    assert res.status == "cancelled" and res.reason == "cancel_requested"
    assert ran["n"] == 0


async def test_cancel_after_engine_classified_honestly(monkeypatch):
    """Non-cooperative: cancel flips during engine wait → honest reason."""

    async def cap(ctx):
        rt.request_cancel_run("kavya", ctx.task.task_id)
        return {"done": True}

    _register("kavya", "ctrl_probe", cap)
    res = await rt.submit("kavya", "ctrl_probe")
    assert res.status == "succeeded"
    assert res.reason == "cancel_requested_but_engine_completed"


async def test_agent_wide_cancel_no_running_is_ok():
    out = rt.request_cancel("kavya")
    assert out["ok"] is True
    assert out["status"] == "no_running_tasks"
    assert out["targeted_run_ids"] == []


# ---- races ---------------------------------------------------------------- #


async def test_control_between_policy_and_lease(monkeypatch):
    ran = {"n": 0}
    calls = {"n": 0}

    async def cap(ctx):
        ran["n"] += 1
        return {}

    def late(agent_id):
        calls["n"] += 1
        if calls["n"] <= 1:
            return False, ""
        return True, "agent_paused"

    monkeypatch.setattr(rt, "_owner_admission_blocked", late)
    _register("kavya", "ctrl_probe", cap)
    res = await rt.submit("kavya", "ctrl_probe")
    assert res.status == "blocked" and res.reason == "agent_paused"
    assert ran["n"] == 0
    assert "leased" not in res.lifecycle


async def test_control_between_lease_and_engine(monkeypatch):
    ran = {"n": 0}
    calls = {"n": 0}

    async def cap(ctx):
        ran["n"] += 1
        return {}

    def late(agent_id):
        calls["n"] += 1
        # policy + race1 + race2 allow; pre-engine blocks
        if calls["n"] < 4:
            return False, ""
        return True, "agent_draining"

    monkeypatch.setattr(rt, "_owner_admission_blocked", late)
    _register("kavya", "ctrl_probe", cap)
    res = await rt.submit("kavya", "ctrl_probe")
    assert res.status == "blocked" and res.reason == "agent_draining"
    assert ran["n"] == 0
    assert "leased" in res.lifecycle


# ---- multi-agent inheritance + claim_allowed parity ----------------------- #


async def test_controls_shared_across_two_pilots():
    for aid in ("kavya", "isha"):
        _register(aid, "ctrl_probe", _ok)
        oae.set_control(aid, by="t", manual_pause=True, reason="shared")
        res = await rt.submit(aid, "ctrl_probe", tenant_id="t1")
        assert res.reason == "agent_paused", aid
        oae.resume(aid, by="t")


def test_claim_allowed_still_ignores_manual_pause():
    """Scheduler contract: manual_pause does not flip claim_allowed."""
    oae.set_control("isha", by="t", manual_pause=True, reason="unit")
    assert oae.claim_allowed(agent_id="isha")[0] is True
    assert oae.runtime_admission_blocked("isha") == (True, "agent_paused")


# ---- Owner OS command_id normalize ---------------------------------------- #


def test_create_command_exposes_top_level_command_id():
    out = owner_os.create_command("Pending approvals dikhao", actor="t", idempotency_key="cid-1")
    assert out.get("command_id")
    assert out["command_id"] == out["command"]["command_id"]
    assert out.get("status") == out["command"]["status"]
    # legacy nested shape still present
    assert isinstance(out["command"], dict)
