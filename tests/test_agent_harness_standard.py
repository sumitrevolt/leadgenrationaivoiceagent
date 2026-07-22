"""
Contract & Conformance Unit Tests for Agent Harness Standard (M1-M5).
======================================================================
"""

from __future__ import annotations

import pytest
import asyncio
from app.platform.agent_loop import AgentLoopEngine, LoopTerminationReason, AgentTurnState
from app.platform.tool_registry import validate_tool_payload, get_tool_schema
from app.platform.context_governance import ContextWindow, sanitize_prompt_text, estimate_tokens
from app.platform.agent_checkpoint import save_checkpoint, load_latest_checkpoint


def test_tool_registry_validation():
    valid, err = validate_tool_payload("whatsapp_send", {"recipient_phone": "+919876543210", "message_text": "Test"})
    assert valid is True
    assert err == ""

    invalid, err_reason = validate_tool_payload("whatsapp_send", {"message_text": "Test"})
    assert invalid is False
    assert "Missing required field 'recipient_phone'" in err_reason


def test_context_sanitization():
    raw = "My secret key is sk-123456789012345678901234567890"
    sanitized = sanitize_prompt_text(raw)
    assert "sk-12345" not in sanitized
    assert "[REDACTED_API_KEY]" in sanitized


def test_context_compaction():
    cw = ContextWindow(
        system_prompt="System Prompt",
        tenant_id="tenant_123",
        messages=[{"role": "user", "content": f"Turn {i} " + ("word " * 100)} for i in range(10)],
        max_tokens=300,
    )
    compacted = cw.compact()
    assert len(compacted) < 10
    assert "[Context Compacted" in compacted[0]["content"]


def test_turn_checkpoint_roundtrip(tmp_path):
    task_id = "test_task_checkpoint_123"
    filepath = save_checkpoint(task_id, 1, {"turn": 1, "status": "in_progress"})
    assert filepath is not None

    loaded = load_latest_checkpoint(task_id)
    assert loaded is not None
    assert loaded["task_id"] == task_id
    assert loaded["state_data"]["turn"] == 1


@pytest.mark.asyncio
async def test_agent_loop_engine_budget_limit():
    engine = AgentLoopEngine(max_turns=5, max_tokens=150)

    async def step(state: AgentTurnState, inp: dict):
        return {"done": False, "action": "loop", "tokens_used": 200}

    loop_state = await engine.run_loop({}, step)
    assert loop_state.termination_reason == LoopTerminationReason.BUDGET_EXHAUSTED
    assert loop_state.tokens_used >= 150
