"""Agent Runtime (Phase-B) contract-enforcement tests.

Prompt-mandated 15 cases: GREEN success · flag skip · kill block · prohibited
reject · timeout · retry→DLQ · idempotent dedupe · concurrency · budget ·
tenant isolation · AMBER approval · RED hard-off · heartbeat vs useful-work ·
event-only healthy-idle · registry stays green.

Isolated: state/usage/DLQ files → tmp_path; kill/idempotency/approval seams
monkeypatched; no Redis/DB/network required (durable bridge is best-effort).
"""

from __future__ import annotations

import asyncio
import json
import os

import pytest

from app.platform import agent_registry as ar
from app.platform import agent_runtime as rt
from app.platform.agent_runtime import AgentCapability, SkipTask


@pytest.fixture(autouse=True)
def isolated_runtime(tmp_path, monkeypatch):
    """Isolated stores + deterministic seams + pilot flags ON."""
    monkeypatch.setattr(rt, "_STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setattr(rt, "_USAGE_PATH", str(tmp_path / "usage.json"))
    monkeypatch.setattr(rt, "_DLQ_PATH", str(tmp_path / "dlq.jsonl"))
    monkeypatch.setattr(rt, "_BACKOFF_BASE_S", 0.0)
    monkeypatch.setattr(rt, "_kill_engaged", lambda key: False)
    monkeypatch.setattr(rt, "_approval_approved", lambda tenant, ref: False)

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
    monkeypatch.setenv("SOCIAL_ENGINE", "1")
    yield rt
    rt._CAPABILITIES.clear()
    rt._CAPABILITIES.update(caps_snapshot)
    crc.reset_memory_for_tests()
    arid.reset_memory_for_tests()
    rt._ACTIVE.clear()
    rt._ACTIVE_TASKS.clear()


def _register(agent_id: str, action: str, fn, **kw):
    rt.register_capability(AgentCapability(agent_id=agent_id, action=action, fn=fn, **kw))


async def _ok_cap(ctx):
    ctx.add_usage(api_calls=1)
    return {"done": True}


# ---------------------------------------------------------------------- #
# 1. Valid GREEN task success
# ---------------------------------------------------------------------- #
async def test_green_task_success():
    _register("kavya", "unit_probe", _ok_cap)
    res = await rt.submit("kavya", "unit_probe")
    assert res.status == "succeeded"
    assert res.lane == "GREEN"
    assert res.attempts == 1
    assert res.lifecycle[0] == "queued" and res.lifecycle[-1] == "succeeded"
    assert "leased" in res.lifecycle and "running" in res.lifecycle
    assert res.usage["api_calls"] == 1


# ---------------------------------------------------------------------- #
# 2. Disabled flag skip (primary_flag + master flag dono)
# ---------------------------------------------------------------------- #
async def test_disabled_primary_flag_skips(monkeypatch):
    monkeypatch.setenv("OPS_HEALTH_AGENT", "0")
    _register("kavya", "unit_probe", _ok_cap)
    res = await rt.submit("kavya", "unit_probe")
    assert res.status == "skipped"
    assert res.reason == "flag_disabled:OPS_HEALTH_AGENT"


async def test_disabled_master_flag_skips_everything(monkeypatch):
    monkeypatch.setenv("AGENT_RUNTIME", "0")
    _register("kavya", "unit_probe", _ok_cap)
    res = await rt.submit("kavya", "unit_probe")
    assert res.status == "skipped"
    assert res.reason.startswith("runtime_flag_disabled")


# ---------------------------------------------------------------------- #
# 3. Kill-switch block (global owner_all_agents = every agent stops)
# ---------------------------------------------------------------------- #
async def test_global_kill_switch_blocks(monkeypatch):
    monkeypatch.setattr(rt, "_kill_engaged", lambda key: key == "owner_all_agents")
    for agent, flag_action in (("kavya", "unit_probe"), ("isha", "unit_probe2")):
        _register(agent, flag_action, _ok_cap)
        res = await rt.submit(agent, flag_action, tenant_id="t1")
        assert res.status == "blocked", agent
        assert res.reason == "kill_switch_engaged:owner_all_agents", agent


async def test_kill_check_error_fails_closed(monkeypatch):
    monkeypatch.setattr(rt, "_kill_engaged", lambda key: None)  # store errored
    _register("kavya", "unit_probe", _ok_cap)
    res = await rt.submit("kavya", "unit_probe")
    assert res.status == "blocked"
    assert res.reason.startswith("kill_switch_check_error:owner_")


# ---------------------------------------------------------------------- #
# 4. Prohibited action reject (contract data = enforcement)
# ---------------------------------------------------------------------- #
async def test_prohibited_action_rejected():
    _register("kavya", "mutate_infra", _ok_cap)  # registered ho ke bhi block
    res = await rt.submit("kavya", "mutate_infra")
    assert res.status == "blocked"
    assert res.reason == "prohibited_action:mutate_infra"


# ---------------------------------------------------------------------- #
# 5. Timeout (per-attempt wait_for)
# ---------------------------------------------------------------------- #
async def test_timeout_fails_with_structured_error():
    async def slow(ctx):
        await asyncio.sleep(3)
        return {}

    _register("kavya", "slow_probe", slow)
    res = await rt.submit("kavya", "slow_probe", timeout_s=0.2)
    assert res.status == "failed"
    assert res.error_class == "TimeoutError"
    assert res.attempts == 1  # kavya retry_policy = skip-on-fail
    assert res.escalation == "hermes"


# ---------------------------------------------------------------------- #
# 6. Retry then DLQ (zara retry_policy = "DLQ + backoff")
# ---------------------------------------------------------------------- #
async def test_retry_then_dlq():
    calls = {"n": 0}

    async def flaky(ctx):
        calls["n"] += 1
        raise RuntimeError("provider 500")

    _register("zara", "internal_flaky", flaky, side_effect="internal")
    res = await rt.submit("zara", "internal_flaky")
    assert res.status == "failed"
    assert res.attempts == 3 == calls["n"]
    assert res.dlq is True
    assert res.reason == "retry_exhausted"
    recs = rt.runtime_dlq()
    assert recs and recs[0]["agent_id"] == "zara"
    assert recs[0]["error_class"] == "RuntimeError"
    assert recs[0]["error_message"]  # failure reason recorded


# ---------------------------------------------------------------------- #
# 7. Idempotent duplicate suppression
# ---------------------------------------------------------------------- #
async def test_idempotent_duplicate_suppressed():
    _register("kavya", "unit_probe", _ok_cap)
    first = await rt.submit("kavya", "unit_probe", idempotency_key="k1")
    dup = await rt.submit("kavya", "unit_probe", idempotency_key="k1")
    assert first.status == "succeeded"
    assert dup.status == "skipped"
    assert dup.reason == "duplicate_suppressed"


async def test_failed_run_retains_key_blocks_same_key_retry():
    """Terminal failure is durable — same key must not re-execute (need new key)."""

    async def boom(ctx):
        raise ValueError("x")

    _register("kavya", "boomer", boom)
    r1 = await rt.submit("kavya", "boomer", idempotency_key="k2")
    assert r1.status == "failed"
    _register("kavya", "boomer", _ok_cap)  # fixed now
    r2 = await rt.submit("kavya", "boomer", idempotency_key="k2")
    assert r2.status == "skipped"
    assert r2.reason == "duplicate_suppressed"
    r3 = await rt.submit("kavya", "boomer", idempotency_key="k2-retry")
    assert r3.status == "succeeded"


# ---------------------------------------------------------------------- #
# 8. Concurrency limit (kavya max_concurrency = 1)
# ---------------------------------------------------------------------- #
async def test_concurrency_limit():
    gate = asyncio.Event()

    async def waiter(ctx):
        await gate.wait()
        return {"done": True}

    _register("kavya", "gated_probe", waiter)
    t1 = asyncio.create_task(rt.submit("kavya", "gated_probe"))
    await asyncio.sleep(0.05)  # t1 slot le chuka
    blocked = await rt.submit("kavya", "gated_probe")
    assert blocked.status == "blocked"
    assert blocked.reason == "concurrency_limit"
    gate.set()
    done = await t1
    assert done.status == "succeeded"


# ---------------------------------------------------------------------- #
# 9. Budget exhaustion (daily api-call cap, fail-CLOSED)
# ---------------------------------------------------------------------- #
async def test_budget_exhaustion():
    day = rt._now_iso()[:10]
    os.makedirs(os.path.dirname(rt._USAGE_PATH) or ".", exist_ok=True)
    with open(rt._USAGE_PATH, "w", encoding="utf-8") as f:
        json.dump({day: {"kavya": {"api_calls": 50, "cost_inr": 0, "contacts": 0, "runs": 50}}}, f)
    _register("kavya", "unit_probe", _ok_cap)
    res = await rt.submit("kavya", "unit_probe")
    assert res.status == "blocked"
    assert res.reason == "budget_exhausted:api_calls"


# ---------------------------------------------------------------------- #
# 10. Tenant isolation
# ---------------------------------------------------------------------- #
async def test_tenant_isolation():
    _register("isha", "tenant_probe", _ok_cap, tenant_scoped=True)
    no_tenant = await rt.submit("isha", "tenant_probe")
    assert no_tenant.status == "blocked" and no_tenant.reason == "tenant_required"
    mismatch = await rt.submit(
        "isha", "tenant_probe", {"client_id": "other-client"}, tenant_id="jiya-makeover"
    )
    assert mismatch.status == "blocked" and mismatch.reason == "tenant_mismatch"
    ok = await rt.submit(
        "isha", "tenant_probe", {"client_id": "jiya-makeover"}, tenant_id="jiya-makeover"
    )
    assert ok.status == "succeeded"


# ---------------------------------------------------------------------- #
# 11. AMBER approval requirement (customer side-effect)
# ---------------------------------------------------------------------- #
async def test_amber_customer_action_requires_approval(monkeypatch):
    _register("zara", "customer_probe", _ok_cap, side_effect="customer", tenant_scoped=True)
    no_ref = await rt.submit("zara", "customer_probe", tenant_id="t1")
    assert no_ref.status == "blocked" and no_ref.reason == "approval_required"

    not_approved = await rt.submit("zara", "customer_probe", tenant_id="t1", approval_ref="ap1")
    assert not_approved.status == "blocked" and not_approved.reason == "approval_not_approved"

    monkeypatch.setattr(rt, "_approval_approved", lambda tenant, ref: ref == "ap1")
    approved = await rt.submit("zara", "customer_probe", tenant_id="t1", approval_ref="ap1")
    assert approved.status == "succeeded"


# ---------------------------------------------------------------------- #
# 12. RED action remains hard-off (no env flip can enable)
# ---------------------------------------------------------------------- #
async def test_red_lane_remains_hard_off(monkeypatch):
    monkeypatch.setenv("PLATFORM_DIAL_DAILY", "1")  # env flip attempt — must NOT matter
    _register("swara", "place_call", _ok_cap)
    for agent in ("swara", "ananya"):
        res = await rt.submit(agent, "place_call")
        assert res.status == "blocked", agent
        assert res.reason == "red_lane_hard_off_mandate_required", agent


async def test_non_pilot_agent_blocked():
    # Wave-B put manager in pilots; AMBER hold (rohan) stays allowlist-blocked.
    _register("rohan", "unit_probe", _ok_cap)
    res = await rt.submit("rohan", "unit_probe")
    assert res.status == "blocked"
    assert res.reason == "not_in_pilot_rollout"


# ---------------------------------------------------------------------- #
# 13. Heartbeat vs useful-work status (alag-alag signals)
# ---------------------------------------------------------------------- #
async def test_heartbeat_vs_useful_work(monkeypatch):
    monkeypatch.setenv("OPS_HEALTH_AGENT", "0")
    _register("kavya", "unit_probe", _ok_cap)
    skipped = await rt.submit("kavya", "unit_probe")
    assert skipped.status == "skipped"
    state = rt._read_json(rt._STATE_PATH)
    assert state["kavya"]["process_hb"]  # process alive
    assert not state["kavya"].get("useful_work")  # par useful kaam NAHI hua

    monkeypatch.setenv("OPS_HEALTH_AGENT", "1")
    ok = await rt.submit("kavya", "unit_probe")
    assert ok.status == "succeeded"
    state = rt._read_json(rt._STATE_PATH)
    assert state["kavya"]["useful_work"]  # ab useful-work heartbeat bhi


# ---------------------------------------------------------------------- #
# 14. Event-only agent reports healthy-idle (offline NAHI)
# ---------------------------------------------------------------------- #
def test_event_only_agent_healthy_idle():
    status = rt.runtime_status()
    assert status["ok"] is True
    by_id = {a["agent_id"]: a for a in status["agents"]}
    assert by_id["riya"]["event_or_ondemand_only"] is True
    assert by_id["riya"]["health"] == "healthy_idle"
    assert all(a["health"] != "offline" for a in status["agents"])
    # pilots wired par abhi dispatch nahi hue = pilot_ready (incident nahi)
    assert by_id["kavya"]["health"] in ("pilot_ready", "healthy", "healthy_idle")
    assert by_id["kavya"]["pilot"] is True
    assert by_id["swara"]["lane"] == "RED" and by_id["swara"]["pilot"] is False


# ---------------------------------------------------------------------- #
# 15. Existing 31-agent registry validation remains green
# ---------------------------------------------------------------------- #
def test_registry_still_green_and_pilots_canonical():
    assert ar.validate_registry() == []
    reg = ar.build_registry()
    assert len(reg) == 31
    for pilot in rt.PILOT_AGENTS:
        assert pilot in reg
    # pilot lane sanity — Phase-B risk envelope
    assert reg["kavya"].lane == "GREEN"
    assert reg["isha"].lane == "GREEN" and reg["isha"].reasoning is True
    assert reg["zara"].lane == "AMBER" and reg["zara"].default_mode != "live"


# ---------------------------------------------------------------------- #
# Extras: cancellation, capability self-skip, pilot registration, status surface
# ---------------------------------------------------------------------- #
async def test_cancellation_blocks_specific_run():
    _register("kavya", "unit_probe", _ok_cap)
    task = rt.AgentTask(agent_id="kavya", action="unit_probe")
    out = rt.request_cancel_run("kavya", task.task_id, reason="unit")
    assert out.get("ok") is True
    res = await rt.run_task(task)
    assert res.status == "cancelled" and res.reason == "cancel_requested"
    # Unrelated future run is NOT cancelled
    res2 = await rt.submit("kavya", "unit_probe")
    assert res2.status == "succeeded"


async def test_capability_self_skip_is_honest():
    async def skipper(ctx):
        raise SkipTask("downstream_engine_off")

    _register("kavya", "skippy", skipper)
    res = await rt.submit("kavya", "skippy")
    assert res.status == "skipped"
    assert res.reason == "capability_skip:downstream_engine_off"


async def test_unregistered_capability_fails_closed():
    res = await rt.submit("kavya", "no_such_action")
    assert res.status == "blocked"
    assert res.reason == "capability_not_registered:no_such_action"


def test_pilot_capabilities_register_idempotently():
    from app.platform import agent_runtime_pilots as pilots

    pilots.ensure_pilots_registered()
    pilots.ensure_pilots_registered()
    assert "ops_health_check" in rt.capabilities_for("kavya")
    assert "draft_content_brief" in rt.capabilities_for("isha")
    assert "publish_approved_content" in rt.capabilities_for("zara")
    zcap = rt.get_capability("zara", "publish_approved_content")
    assert zcap.requires_approval is True and zcap.tenant_scoped is True


async def test_isha_pilot_draft_is_proposal_only():
    from app.platform import agent_runtime_pilots as pilots

    pilots.ensure_pilots_registered()
    res = await rt.submit(
        "isha",
        "draft_content_brief",
        {"client_id": "jiya-makeover", "topic": "monsoon offer"},
        tenant_id="jiya-makeover",
    )
    assert res.status == "succeeded"
    out = res.output
    assert out["requires_human_review"] is True
    assert out["published"] is False and out["customer_contacted"] is False
    assert out["proposal"]["generator"] == "deterministic_template"  # LLM flag off


def test_runtime_status_never_raises_and_shows_budgets():
    status = rt.runtime_status()
    assert status["canonical_count"] == 31
    assert sorted(status["pilots"]) == sorted(rt.PILOT_AGENTS)
    row = next(a for a in status["agents"] if a["agent_id"] == "kavya")
    assert row["budget"]["api_calls"]["cap"] == 50
    assert "owner_all_agents" in row["kill_switches"]
