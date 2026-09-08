"""
Smoke tests for app.agents.harness — run WITHOUT the full app (all app.* imports
are optional in the package). Proves the ordered controls actually fire.

    pytest tests/test_harness_smoke.py -q
"""

import asyncio
import os

import pytest
from pydantic import BaseModel, field_validator

from app.agents.harness import (
    Budget,
    Harness,
    RiskClass,
    RunContext,
    StopReason,
    ToolCall,
    ToolRegistry,
)
from app.agents.harness.stop import StopController


# ---- sample tools ----------------------------------------------------
class EchoArgs(BaseModel):
    text: str

    @field_validator("text")
    @classmethod
    def _bounded(cls, v: str) -> str:
        if len(v) > 100:  # VA-02 argument bound
            raise ValueError("text too long")
        return v


class SendArgs(BaseModel):
    to: str
    body: str


async def _echo(text: str):
    return f"echo:{text}"


async def _send(to: str, body: str):
    return {"sent_to": to}


def _fresh_registry() -> ToolRegistry:
    # Simulate a configured permissions matrix that grants these tools.
    r = ToolRegistry(permission_fn=lambda agent, tool: True)
    r.register("echo", _echo, EchoArgs, RiskClass.READ)
    r.register("send_whatsapp", _send, SendArgs, RiskClass.EXTERNAL_SEND)
    return r


def _harness(**kw) -> Harness:
    return Harness(registry=_fresh_registry(), **kw)


# ---- tests -----------------------------------------------------------
def test_valid_read_tool_executes():
    h = _harness()
    ctx = RunContext(agent="tester")
    res = asyncio.run(h.step(ctx, ToolCall(name="echo", args={"text": "hi"})))
    assert res.ok and res.output == "echo:hi"
    assert "VA-01/02:valid" in res.control_trail and "exec:done" in res.control_trail


def test_bounds_reject():
    h = _harness()
    ctx = RunContext(agent="tester")
    res = asyncio.run(h.step(ctx, ToolCall(name="echo", args={"text": "x" * 200})))
    assert not res.ok and "VA-01/02:reject" in res.control_trail


def test_unknown_tool_denied():
    h = _harness()
    ctx = RunContext(agent="tester")
    res = asyncio.run(h.step(ctx, ToolCall(name="nope", args={})))
    assert not res.ok


def test_dangerous_requires_approval_default_deny():
    # No app.risk_approve available -> fail-closed hold.
    h = _harness()
    ctx = RunContext(agent="tester")
    res = asyncio.run(
        h.step(
            ctx,
            ToolCall(
                name="send_whatsapp", idempotency_key="k1", args={"to": "+91", "body": "hello"}
            ),
        )
    )
    assert not res.ok and "PM-03:hold" in res.control_trail


def test_dangerous_approved_then_checkpoint_and_egress():
    async def approve(ctx, call, risk):
        return True

    h = _harness(approval=approve)
    ctx = RunContext(agent="tester")
    res = asyncio.run(
        h.step(
            ctx,
            ToolCall(name="send_whatsapp", idempotency_key="k2", args={"to": "+91", "body": "hi"}),
        )
    )
    assert res.ok
    assert "PM-03:approved" in res.control_trail
    assert "SB-04:checkpoint" in res.control_trail
    assert "DL-01:clean" in res.control_trail


def test_dl01_blocks_secret_payload():
    async def approve(ctx, call, risk):
        return True

    h = _harness(approval=approve)
    ctx = RunContext(agent="tester")
    res = asyncio.run(
        h.step(
            ctx,
            ToolCall(
                name="send_whatsapp",
                idempotency_key="k3",
                args={"to": "+91", "body": "key=sk_live_123"},
            ),
        )
    )
    assert not res.ok and "DL-01:block" in res.control_trail


def test_budget_iteration_stop():
    sc = StopController(Budget(max_iterations=2))
    ctx = RunContext(agent="tester")
    ctx.iterations = 2
    cont, reason = sc.check(ctx)
    assert not cont and reason == StopReason.MAX_ITERATIONS


def test_no_progress_detection():
    sc = StopController(Budget(no_progress_window=3))
    ctx = RunContext(agent="tester")
    for _ in range(3):
        sc.record_progress(ctx, {"same": "obs"})
    cont, reason = sc.check(ctx)
    assert not cont and reason == StopReason.NO_PROGRESS


def test_run_driver_reaches_goal():
    async def approve(ctx, call, risk):
        return True

    h = _harness(approval=approve)
    ctx = RunContext(agent="tester")
    calls = [
        ToolCall(name="echo", args={"text": "a"}),
        ToolCall(name="echo", args={"text": "b"}),
        None,
    ]

    async def propose(ctx):
        return calls.pop(0)

    reason = asyncio.run(h.run(ctx, propose))
    assert reason == StopReason.GOAL_MET
    assert ctx.tool_calls == 2


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-q"]))


def test_mutating_requires_idempotency_key():
    async def approve(ctx, call, risk):
        return True

    h = _harness(approval=approve)
    ctx = RunContext(agent="tester")
    # send_whatsapp is MUTATING (EXTERNAL_SEND) with NO idempotency_key -> reject
    res = asyncio.run(h.step(ctx, ToolCall(name="send_whatsapp", args={"to": "+91", "body": "hi"})))
    assert not res.ok and "VA-02:no-idempotency" in res.control_trail
