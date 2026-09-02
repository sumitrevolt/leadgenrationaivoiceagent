"""Batch-harness shadow adapter — record-only observation of each real batch item.

Wraps the item boundary in app/agents/batch_harness.py:run_batch/_run_one
(`res = await fn(item)`). Observes AFTER the real item completes; never invokes
the item fn, schedules items, changes concurrency/order/retries, alters the
checkpoint, or raises into the batch.

Concurrency: called from asyncio tasks (never threads). Harness.observe ->
audit.record is fully SYNCHRONOUS (no await), so asyncio cannot interleave two
writes — JSONL stays line-atomic without a lock. The dedup set is likewise
mutated synchronously. No global lock is held during item execution.

Resume: a skipped (already-checkpointed) item is a DIAGNOSTIC (RESUME_SKIPPED),
never an executed-action record. A duplicate callback for the same
(batch_run_id, item_id, attempt, operation) writes a shadow_dedup diagnostic.
"""

from __future__ import annotations

import collections
import hashlib
import json
from typing import Any, Optional

from app.agents.harness.adapters.shadow import shadow_loop_eligible
from app.agents.harness.contracts import SYSTEM_TENANT, RiskClass

try:
    from app.utils.logger import setup_logger

    logger = setup_logger(__name__)
except Exception:  # pragma: no cover
    import logging

    logger = logging.getLogger(__name__)

_SOURCE_LOOP = "batch_harness"
_SEEN: collections.OrderedDict[str, int] = collections.OrderedDict()
_SEEN_MAX = 4096

# Anonymous / non-stable operation identities -> MISSING_CONTEXT (never a guess).
_ANON = {"", "<lambda>", "lambda", "<anonymous>", "?"}


def _hash(obj: Any) -> str:
    try:
        return hashlib.sha1(
            json.dumps(obj, sort_keys=True, default=str).encode("utf-8"), usedforsecurity=False
        ).hexdigest()[:16]
    except Exception:
        return "unhashable"


def _seen(key: str) -> bool:
    if key in _SEEN:
        return True
    _SEEN[key] = 1
    if len(_SEEN) > _SEEN_MAX:
        _SEEN.popitem(last=False)
    return False


def _diag(agent: str, batch_run_id: str, kind: str, extra: dict) -> None:
    try:
        from app.agents.harness import audit
        from app.agents.harness.contracts import RunContext

        audit.record(
            RunContext(agent=agent, run_id=batch_run_id),
            None,
            None,
            kind=kind,
            extra={**extra, "source_loop": _SOURCE_LOOP},
        )
    except Exception:
        pass


def observe_batch_item(
    *,
    batch_run_id: str,
    batch_name: str,
    item_id: str,
    item_index: int,
    attempt: int,
    agent_id: str,
    tenant_id: str,
    operation_name: str,
    operation_arguments: dict | None = None,
    actual_executor: str = "",
    actual_result: Any = None,
    actual_error: Any = None,
    latency_ms: float = 0.0,
    checkpoint_state: str | None = None,
    resumed: bool = False,
    tool_name: str | None = None,
    tool_version: str | None = None,
    execution_metadata: dict | None = None,
) -> dict | None:
    """Observe one batch item attempt (or a resume-skip) in shadow. Returns the
    action record, or None (ineligible / resume-skip diagnostic / dedup / error).
    NEVER raises into the batch."""
    aid = (agent_id or "").strip().lower()
    if not shadow_loop_eligible(aid, _SOURCE_LOOP):
        return None

    # Resume-skip = diagnostic only, NEVER an executed-action observation.
    if resumed:
        _diag(
            aid,
            batch_run_id,
            "shadow_resume_skip",
            {
                "batch_run_id": batch_run_id,
                "item_id": item_id,
                "item_index": item_index,
                "attempt": attempt,
                "comparison_verdict": "RESUME_SKIPPED",
                "resumed": True,
            },
        )
        return None

    dedup_key = f"{_SOURCE_LOOP}:{batch_run_id}:{item_id}:{attempt}:{operation_name}"
    if _seen(dedup_key):
        _diag(
            aid,
            batch_run_id,
            "shadow_dedup",
            {
                "dedup_key": dedup_key,
                "item_id": item_id,
                "attempt": attempt,
                "comparison_verdict": "DUPLICATE_SUPPRESSED",
            },
        )
        return None

    try:
        from pydantic import BaseModel, ConfigDict

        from app.agents.harness import Harness, RunContext, ToolCall, ToolRegistry

        op = (operation_name or "").strip()
        stable = op not in _ANON
        if tool_name:  # explicit CANONICAL registry identity
            tool = tool_name
            tver = tool_version or "1.0.0"
        else:  # legacy = unregistered internal action
            tool = f"batch.execute.{op}" if stable else "batch.execute.__anonymous__"
            tver = "v1"
        args = operation_arguments or {}
        risk = RiskClass.READ  # internal batch item = read/compute
        shadow_ref = f"shadow:{batch_run_id}:{item_id}:{attempt}"

        class _AnyArgs(BaseModel):
            model_config = ConfigDict(extra="allow")

        async def _tripwire(**_: Any):
            raise AssertionError("batch shadow executor must never be invoked")

        reg = ToolRegistry(permission_fn=lambda a, t: True)
        reg.register(tool, _tripwire, _AnyArgs, risk)

        req = ToolCall(
            name=tool,
            args=args,
            reason="shadow observation of batch item",
            tool_version=tver,
            risk_class=risk,
            idempotency_key=shadow_ref,
            budget_scope="run",
            expected_effect=f"batch {batch_name} item {item_id}",
        )
        ctx = RunContext(
            run_id=batch_run_id,
            task_id=batch_run_id,
            tenant_id=(tenant_id or SYSTEM_TENANT),
            agent=aid,
            actor_id="batch_runner",
            shadow_run_id=shadow_ref,
            source_loop=_SOURCE_LOOP,
        )
        meta = dict(execution_metadata or {})
        # Anonymous operation identity -> MISSING_CONTEXT (never guessed).
        override = "MISSING_CONTEXT" if (not tool_name and not stable) else None
        meta.update(
            {
                "latency_ms": latency_ms,
                "legacy_tool": tool,
                "side_effect_class": "internal",
                "batch_run_id": batch_run_id,
                "batch_name": batch_name,
                "item_id": item_id,
                "item_index": item_index,
                "attempt": attempt,
                "operation_name": op or "<anonymous>",
                "actual_executor": actual_executor or op or "<anonymous>",
                "normalized_tool": tool,
                "normalized_arguments_hash": _hash(args),
                "actual_arguments_hash": _hash(args),
                "checkpoint_state": checkpoint_state,
                "resumed": False,
                "source_run_id": batch_run_id,
                "parent_action_id": f"{batch_run_id}:{item_id}",
                "tool_registry_status": (
                    "canonical_registered" if tool_name else "unregistered_internal_action"
                ),
            }
        )
        if override:
            meta["verdict_override"] = override
        return Harness(registry=reg).observe(
            ctx,
            req,
            actual_result=actual_result,
            actual_error=actual_error,
            execution_metadata=meta,
        )
    except Exception as e:
        logger.warning("harness.batch_shadow: observation failed (batch unaffected): %s", e)
        _diag(
            aid,
            batch_run_id,
            "shadow_error",
            {"error": str(e)[:200], "item_id": item_id, "item_index": item_index},
        )
        return None
