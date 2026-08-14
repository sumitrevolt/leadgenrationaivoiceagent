"""
Run audit + correlation (OB-01 / OB-02).

The audit found three disjoint stores with no shared join key: Langfuse/Tempo
traces, `data/eval_history.jsonl` eval scores, and
`architecture/execution/task-ledger.json` run/approval state. You cannot replay
a run end-to-end.

This module mints ONE ``run_id`` and threads it everywhere:
* stamps it as an OTel/Langfuse span attribute (``gen_ai.run.id``) via the
  existing ``observability_llm`` when present (OB-01);
* appends an append-only correlation record per step to a run log so a later
  ``replay(run_id)`` can reconstruct trace -> action -> observation -> eval ->
  approval (OB-02).

Append-only JSONL keeps it simple and durable; swap the sink for your DB later.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Optional

from . import session
from .contracts import RunContext, ToolCall, ToolResult

try:
    from app.utils.logger import setup_logger  # type: ignore

    logger = setup_logger(__name__)
except Exception:  # pragma: no cover
    import logging

    logger = logging.getLogger(__name__)

_RUN_LOG = os.getenv("HARNESS_RUN_LOG", "data/harness_runs.jsonl")


def _emit_span_attr(ctx: RunContext, **attrs: Any) -> None:
    """Attach run_id (and extras) to the current LLM/OTel span if the app's
    observability layer is available. Best-effort; never raises."""
    try:
        from app import observability_llm as obs  # type: ignore

        setter = getattr(obs, "set_current_attributes", None) or getattr(obs, "annotate", None)
        if callable(setter):
            setter(**{"gen_ai.run.id": ctx.run_id, **attrs})
    except Exception:
        pass


def record(
    ctx: RunContext,
    call: ToolCall | None,
    result: ToolResult | None,
    kind: str,
    extra: dict[str, Any] | None = None,
) -> None:
    """Append one correlation event. ``kind`` in {step, approval, eval, stop}."""
    row = {
        "ts": round(time.time(), 3),
        "run_id": ctx.run_id,
        "task_id": ctx.task_id,
        "tenant_id": ctx.tenant_id,
        "agent": ctx.agent,
        "iteration": ctx.iterations,
        "kind": kind,
        "tool": call.name if call else None,
        "call_id": call.call_id if call else None,
        "reason": (call.reason[:200] if call else None),
        "ok": (result.ok if result else None),
        "cost_usd": (result.cost_usd if result else None),
        "control_trail": (result.control_trail if result else None),
        "extra": extra or {},
    }
    # ADR-180: typed session event + hash-chain. OFF = historical keys only.
    if session.session_events_enabled():
        ev = session.event_for_kind(kind, extra)
        if ev:
            row["session_event"] = ev
        session.stamp(row)
    _emit_span_attr(ctx, tool=row["tool"], kind=kind)
    # Durable backend is INERT by default: with HARNESS_AUDIT_BACKEND=jsonl (the
    # default) this is byte-identical to the historical append-only file sink and
    # production is unchanged. A durable backend (redis) is used only when an
    # operator explicitly selects it; in that mode the write is atomically deduped,
    # durably appended, and FAILS CLOSED (dropped observation + operational error)
    # rather than silently reverting to the process-local file.
    try:
        from . import audit_backend
    except Exception:  # pragma: no cover - import safety
        audit_backend = None  # type: ignore

    if audit_backend is None or audit_backend.backend_name() == "jsonl":
        try:
            os.makedirs(os.path.dirname(_RUN_LOG) or ".", exist_ok=True)
            with open(_RUN_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        except Exception as e:  # never break the loop on an audit write
            logger.warning("harness.audit: run-log write failed: %s", e)
    else:
        res = audit_backend.write(row)
        if not res.get("written") and not res.get("duplicate"):
            logger.error(
                "harness.audit: durable observation dropped (fail-closed) via %s: %s",
                res.get("backend"),
                res.get("error"),
            )


def replay(run_id: str) -> list:
    """Reconstruct the ordered event chain for a run (OB-02)."""
    events = []
    try:
        with open(_RUN_LOG, encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if row.get("run_id") == run_id:
                    events.append(row)
    except FileNotFoundError:
        return []
    events.sort(key=lambda r: r.get("ts", 0))
    return events


def counts() -> dict:
    """Read-only durable-audit counts for the harness status surface. Never raises."""
    try:
        from . import audit_backend

        return audit_backend.get_backend().counts()
    except Exception as e:  # pragma: no cover - status must never break callers
        try:
            from . import audit_backend

            return {"backend": audit_backend.backend_name(), "error": str(e)[:160]}
        except Exception:
            return {"backend": "unknown", "error": str(e)[:160]}


def backend_status() -> dict:
    """Read-only backend health + config snapshot (no secrets). Never raises."""
    try:
        from . import audit_backend

        return audit_backend.status()
    except Exception as e:  # pragma: no cover
        return {"backend": "unknown", "error": str(e)[:160]}
