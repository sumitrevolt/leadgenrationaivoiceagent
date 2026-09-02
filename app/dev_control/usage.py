"""Usage/cost ledger service for the engineering control plane (Phase 2).

``build_usage_rows`` is pure (no DB, no imports beyond stdlib) so it is trivially
unit-testable. ``persist_usage`` writes the itemised rows and rolls the actual
token/cost totals up onto the owning DevTask. Nothing here calls a provider or
mutates a worktree.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

_BUDGET_REASONS = {"task_budget_exceeded", "daily_budget_exceeded"}


def build_usage_rows(task_id: str, result: dict[str, Any]) -> list[dict[str, Any]]:
    """Translate one ``gateway.invoke`` result into immutable ledger rows."""
    rows: list[dict[str, Any]] = []
    n = 0
    for att in result.get("attempted", []) or []:
        n += 1
        if att.get("skipped"):
            outcome = "skipped_unconfigured" if att.get("skipped") == "unconfigured" else "skipped"
            detail = str(att.get("skipped"))[:500]
        elif att.get("error"):
            outcome = "empty_response" if att.get("error") == "empty_response" else "provider_error"
            detail = str(att.get("error"))[:500]
        else:
            outcome, detail = "attempt", None
        rows.append(
            {
                "attempt_no": n,
                "provider": str(att.get("provider") or "")[:60],
                "model": None,
                "outcome": outcome,
                "input_tokens": None,
                "output_tokens": None,
                "cost_usd": None,
                "estimated": True,
                "detail": detail,
            }
        )

    if result.get("ok"):
        n += 1
        usage = result.get("usage") or {}
        rows.append(
            {
                "attempt_no": n,
                "provider": str(result.get("provider") or "")[:60],
                "model": result.get("model"),
                "outcome": "success",
                "input_tokens": int(usage.get("prompt_tokens") or 0),
                "output_tokens": int(usage.get("completion_tokens") or 0),
                "cost_usd": Decimal(str(usage.get("actual_cost_usd") or "0")),
                "estimated": bool(usage.get("estimated", False)),
                "detail": None,
            }
        )
    elif result.get("reason") in _BUDGET_REASONS:
        n += 1
        usage = result.get("usage") or {}
        rows.append(
            {
                "attempt_no": n,
                "provider": str(result.get("selected_provider") or "")[:60],
                "model": None,
                "outcome": "budget_denied",
                "input_tokens": None,
                "output_tokens": None,
                "cost_usd": Decimal(str(usage.get("estimated_cost_usd") or "0")),
                "estimated": True,
                "detail": str(result.get("reason"))[:500],
            }
        )
    return rows


async def persist_usage(
    db, task_id: str, rows: list[dict[str, Any]], scope: str | None = None
) -> dict[str, Any]:
    """Insert ledger rows and aggregate the real cost/tokens onto the DevTask."""
    from app.models.dev_task import DevTask
    from app.models.dev_usage import DevTaskUsage

    now = datetime.utcnow()
    total_cost = Decimal("0")
    in_tok = out_tok = 0
    for r in rows:
        db.add(
            DevTaskUsage(
                id=str(uuid.uuid4()),
                task_id=task_id,
                scope=(scope or None),
                created_at=now,
                attempt_no=r["attempt_no"],
                provider=r["provider"],
                model=r.get("model"),
                outcome=r["outcome"],
                input_tokens=r.get("input_tokens"),
                output_tokens=r.get("output_tokens"),
                cost_usd=r.get("cost_usd"),
                estimated=bool(r.get("estimated", True)),
                detail=r.get("detail"),
            )
        )
        if r["outcome"] == "success":
            total_cost += Decimal(str(r.get("cost_usd") or "0"))
            in_tok += int(r.get("input_tokens") or 0)
            out_tok += int(r.get("output_tokens") or 0)

    task = await db.get(DevTask, task_id)
    if task is not None:
        task.actual_input_tokens = (task.actual_input_tokens or 0) + in_tok
        task.actual_output_tokens = (task.actual_output_tokens or 0) + out_tok
        task.actual_cost_usd = Decimal(str(task.actual_cost_usd or "0")) + total_cost
        task.updated_at = now
    await db.commit()
    return {
        "rows_written": len(rows),
        "success_cost_usd": str(total_cost),
        "input_tokens": in_tok,
        "output_tokens": out_tok,
    }


async def record_gateway_result(
    db, task_id: str, result: dict[str, Any], scope: str | None = None
) -> dict[str, Any]:
    return await persist_usage(db, task_id, build_usage_rows(task_id, result), scope=scope)
