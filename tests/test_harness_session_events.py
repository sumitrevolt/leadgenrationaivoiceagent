"""ADR-180: typed SessionEvent + hash-chain. Flag OFF = historical JSONL keys."""

from __future__ import annotations

import asyncio
import json

from pydantic import BaseModel

from app.agents.harness import (
    Harness,
    RiskClass,
    RunContext,
    StopReason,
    ToolCall,
    ToolRegistry,
    audit,
    session,
)
from app.api.automation_flags import AUTOMATION_FLAGS
from app.platform.automation_flag_manifest import FlagGovernance, describe_flag

_HISTORICAL_KEYS = {
    "ts",
    "run_id",
    "task_id",
    "tenant_id",
    "agent",
    "iteration",
    "kind",
    "tool",
    "call_id",
    "reason",
    "ok",
    "cost_usd",
    "control_trail",
    "extra",
}


class _EchoArgs(BaseModel):
    text: str


async def _echo(text: str):
    return f"echo:{text}"


def _harness(**kw) -> Harness:
    r = ToolRegistry(permission_fn=lambda agent, tool: True)
    r.register("echo", _echo, _EchoArgs, RiskClass.READ)
    return Harness(registry=r, **kw)


def _bind_log(monkeypatch, tmp_path):
    path = tmp_path / "harness_runs.jsonl"
    monkeypatch.setattr(audit, "_RUN_LOG", str(path))
    session.reset_chain()
    return path


def _rows(path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def test_flag_registered_canary_only_off_default(monkeypatch):
    monkeypatch.delenv("HARNESS_SESSION_EVENTS", raising=False)
    assert "HARNESS_SESSION_EVENTS" in AUTOMATION_FLAGS
    meta = describe_flag("HARNESS_SESSION_EVENTS")
    assert meta.governance == FlagGovernance.CANARY_ONLY
    assert meta.default_hint == "0"
    assert session.session_events_enabled() is False


def test_flag_off_row_keeps_historical_keys(monkeypatch, tmp_path):
    monkeypatch.setenv("HARNESS_SESSION_EVENTS", "0")
    path = _bind_log(monkeypatch, tmp_path)
    audit.record(RunContext(agent="tester", run_id="r-off"), None, None, kind="step")
    row = _rows(path)[0]
    assert set(row.keys()) == _HISTORICAL_KEYS
    assert "seq" not in row and "event_hash" not in row and "session_event" not in row


def test_hash_chain_stamp_and_tamper_detect():
    session.reset_chain("chain-1")
    a = {"run_id": "chain-1", "kind": "session", "n": 1}
    b = {"run_id": "chain-1", "kind": "session", "n": 2}
    session.stamp(a)
    session.stamp(b)
    ok, why = session.verify_chain([a, b])
    assert ok, why
    b["n"] = 99
    bad, reason = session.verify_chain([a, b])
    assert not bad and "event_hash mismatch" in reason


def test_run_emits_turn_envelope_when_flag_on(monkeypatch, tmp_path):
    monkeypatch.setenv("HARNESS_SESSION_EVENTS", "1")
    path = _bind_log(monkeypatch, tmp_path)
    h = _harness()
    ctx = RunContext(agent="tester", run_id="r-on")
    calls = [ToolCall(name="echo", args={"text": "a"}), None]

    async def propose(_ctx):
        return calls.pop(0)

    reason = asyncio.run(h.run(ctx, propose, profile="headless"))
    assert reason == StopReason.GOAL_MET
    rows = _rows(path)
    events = [r.get("session_event") for r in rows]
    assert events[0] == "turn_start"
    assert "tool_result" in events
    assert events[-1] == "turn_end"
    assert all("event_hash" in r and "seq" in r for r in rows)
    ok, why = session.verify_chain(rows)
    assert ok, why
    assert rows[0]["extra"].get("profile") == "headless"


def test_pre_step_reject_is_denied_and_logged(monkeypatch, tmp_path):
    monkeypatch.setenv("HARNESS_SESSION_EVENTS", "1")
    path = _bind_log(monkeypatch, tmp_path)

    async def refuse(_ctx):
        return False

    h = _harness(pre_step=refuse)
    ctx = RunContext(agent="tester", run_id="r-rej")

    async def propose(_ctx):
        raise AssertionError("propose must not run after pre_step reject")

    reason = asyncio.run(h.run(ctx, propose))
    assert reason == StopReason.DENIED
    rows = _rows(path)
    assert any(r.get("session_event") == "pre_step_reject" for r in rows)
    assert any(r.get("session_event") == "turn_start" for r in rows)
    ok, why = session.verify_chain(rows)
    assert ok, why


def test_flag_off_run_does_not_write_session_kind(monkeypatch, tmp_path):
    monkeypatch.setenv("HARNESS_SESSION_EVENTS", "0")
    path = _bind_log(monkeypatch, tmp_path)
    h = _harness()
    ctx = RunContext(agent="tester", run_id="r-compat")
    calls = [None]

    async def propose(_ctx):
        return calls.pop(0)

    reason = asyncio.run(h.run(ctx, propose))
    assert reason == StopReason.GOAL_MET
    assert _rows(path) == []
