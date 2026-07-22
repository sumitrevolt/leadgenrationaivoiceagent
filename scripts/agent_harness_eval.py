"""
Golden-Task Evaluation Suite — Agent Harness Standard Verification.
====================================================================

WHY (2026-07-22, Agent Harness Engineering Standard M6):
Provides automated regression testing and quality evaluation of the Agent Harness
against core standard requirements (M1-M5: Loop Engine, Tool Schemas, Policy Gates,
Context Compaction, Checkpoints).

Run:
  .venv\\Scripts\\python.exe scripts/agent_harness_eval.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Any

# Ensure app is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.platform import agent_registry as ar
from app.platform import agent_runtime as art
from app.platform.agent_loop import AgentLoopEngine, LoopTerminationReason
from app.platform.tool_registry import validate_tool_payload
from app.platform.context_governance import ContextWindow, sanitize_prompt_text
from app.platform.agent_checkpoint import save_checkpoint, load_latest_checkpoint
from app.utils.logger import setup_logger

logger = setup_logger("agent_harness_eval")


async def run_eval_suite() -> bool:
    print("=" * 70)
    print("Agent Harness Engineering Standard — Golden-Task Evaluation Suite")
    print("=" * 70)

    passed_count = 0
    total_tests = 6

    # Test 1: Policy Gate Safety (RED lane strictly fail-closed)
    print("\n[Eval 1/6] Policy Gate Safety — RED Lane Invariant")
    orig_flag = os.environ.get("AGENT_RUNTIME")
    os.environ["AGENT_RUNTIME"] = "1"
    try:
        swara_task = art.AgentTask(
            task_id="eval_swara_001",
            agent_id="swara",
            action="inbound_callback",
            tenant_id="eval_tenant",
            payload={},
        )
        contract, cap, refusal = art.evaluate_policy(swara_task)
        if refusal and refusal.status == art.TaskStatus.BLOCKED.value and "red_lane" in refusal.reason:
            print("  ✅ PASSED: Swara RED lane dispatch blocked fail-closed")
            passed_count += 1
        else:
            print(f"  ❌ FAILED: Swara RED lane check failed! Refusal: {refusal}")
    finally:
        if orig_flag is None:
            os.environ.pop("AGENT_RUNTIME", None)
        else:
            os.environ["AGENT_RUNTIME"] = orig_flag

    # Test 2: Tool Registry JSON Schema Validation
    print("\n[Eval 2/6] Tool Registry JSON Schema Validation")
    valid, err = validate_tool_payload("whatsapp_send", {"message_text": "hello"})
    valid_ok, _ = validate_tool_payload("whatsapp_send", {"recipient_phone": "+919876543210", "message_text": "hello"})
    if not valid and "Missing required field" in err and valid_ok:
        print("  ✅ PASSED: Invalid tool payload blocked, valid payload passed")
        passed_count += 1
    else:
        print(f"  ❌ FAILED: Tool payload validation check failed! err: {err}")

    # Test 3: Context Governance & Secret Redaction
    print("\n[Eval 3/6] Context Governance & Secret Redaction")
    raw_prompt = "User API key is sk-123456789012345678901234567890 and Gemini key AIzaSyA1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6"
    sanitized = sanitize_prompt_text(raw_prompt)
    if "sk-12345" not in sanitized and "[REDACTED_API_KEY]" in sanitized and "[REDACTED_GEMINI_KEY]" in sanitized:
        print("  ✅ PASSED: API keys successfully redacted from context prompt")
        passed_count += 1
    else:
        print(f"  ❌ FAILED: Secret redaction failed! Result: {sanitized}")

    # Test 4: Context Window Compaction
    print("\n[Eval 4/6] Context Window Compaction")
    cw = ContextWindow(
        system_prompt="System Prompt",
        tenant_id="tenant_1",
        messages=[{"role": "user", "content": "msg " * 500} for _ in range(5)],
        max_tokens=200,
    )
    compacted = cw.compact()
    if len(compacted) < 5 and "[Context Compacted" in compacted[0]["content"]:
        print("  ✅ PASSED: Context compacted above token threshold retaining recency")
        passed_count += 1
    else:
        print(f"  ❌ FAILED: Context compaction failed! Compacted count: {len(compacted)}")

    # Test 5: Durable State Turn Checkpoint Persistence
    print("\n[Eval 5/6] Durable State Turn Checkpoint Persistence")
    test_task_id = "eval_ckpt_task_001"
    save_checkpoint(test_task_id, 1, {"status": "ok", "step": 1})
    loaded = load_latest_checkpoint(test_task_id)
    if loaded and loaded.get("task_id") == test_task_id and loaded.get("state_data", {}).get("status") == "ok":
        print("  ✅ PASSED: Turn checkpoint persisted and reloaded successfully")
        passed_count += 1
    else:
        print(f"  ❌ FAILED: Checkpoint load failed! Loaded: {loaded}")

    # Test 6: Agent Loop Engine Budget & Turn Bounds
    print("\n[Eval 6/6] Agent Loop Engine Budget Bounds")
    engine = AgentLoopEngine(max_turns=2, max_tokens=1000)

    async def dummy_step(state: Any, input_data: dict[str, Any]) -> dict[str, Any]:
        return {"done": False, "action": "loop_step", "tokens_used": 100}

    loop_state = await engine.run_loop({"start": True}, dummy_step)
    if loop_state.termination_reason == LoopTerminationReason.MAX_TURNS_EXCEEDED:
        print("  ✅ PASSED: Loop engine stopped cleanly at max turns limit")
        passed_count += 1
    else:
        print(f"  ❌ FAILED: Loop engine termination failed! Reason: {loop_state.termination_reason}")

    print("\n" + "=" * 70)
    print(f"EVALUATION RESULT: {passed_count}/{total_tests} PASSED")
    print("=" * 70)
    return passed_count == total_tests


if __name__ == "__main__":
    success = asyncio.run(run_eval_suite())
    sys.exit(0 if success else 1)
