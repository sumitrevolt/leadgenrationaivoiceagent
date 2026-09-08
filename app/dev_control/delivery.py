"""Product-One delivery evidence + draft customer notification (Phase 6).

Closes the loop from an approved dev-task to a customer-visible delivery record.
Two ban-safety / attribution rules hold here:
  * The customer notification is a DRAFT only. Nothing is auto-sent (WhatsApp bulk
    auto-send = number ban; §5). A human sends it via the existing 1-click surface.
  * If the task carries a customer_id, a per-customer AutomationLog row is written
    (via the canonical automation_log_service) so the admin cockpit's customer
    filter attributes the work — mirroring ADR-065/066.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Callable

from app.dev_control.service import TaskState

_DELIVER_FROM = {TaskState.PRODUCTION_DEPLOYED.value, TaskState.DELIVERY_VERIFICATION.value}


def build_delivery_notification_draft(objective: str, customer_id: str | None) -> dict[str, Any]:
    """Pure, ban-safe notification DRAFT. auto_send is always False."""
    obj = (objective or "").strip()
    return {
        "channel": "manual_review",
        "to_customer_id": customer_id or None,
        "subject": "Your requested update is ready",
        "body": (
            "Namaste! Aapke account par ek update complete ho gaya hai: "
            + (obj[:200] if obj else "requested change")
            + ". Team review ke baad aapko confirm karegi."
        ),
        "auto_send": False,
        "note": "DRAFT only — a human sends this via the 1-click surface (ban-safe).",
    }


async def finalize_delivery(
    db,
    task_id: str,
    *,
    verified_by: str = "claude-manager",
    log_fn: Callable[..., str] | None = None,
) -> dict[str, Any]:
    """Move an approved task to COMPLETED with delivery evidence + attribution."""
    from app.models.dev_task import DevTask

    task = await db.get(DevTask, task_id)
    if task is None:
        return {"ok": False, "reason": "task_not_found"}
    if task.state not in _DELIVER_FROM:
        return {"ok": False, "reason": "illegal_state", "state": task.state}

    if task.state == TaskState.PRODUCTION_DEPLOYED.value:
        task.state = TaskState.DELIVERY_VERIFICATION.value  # legal hop

    draft = build_delivery_notification_draft(task.parent_objective, task.customer_id)
    now = datetime.utcnow()
    task.delivery_evidence = json.dumps(
        {
            "verified_by": verified_by,
            "verified_at": now.isoformat(),
            "customer_id": task.customer_id,
            "notification_draft": draft,
            "auto_sent": False,
            "note": "delivery recorded; customer notification is a human-sent draft",
        }
    )[:8000]
    task.state = TaskState.COMPLETED.value  # DELIVERY_VERIFICATION -> COMPLETED (legal)
    task.updated_at = now

    attribution_log_id = ""
    if task.customer_id:
        emit = log_fn
        if emit is None:
            try:
                from app.platform.automation_log_service import log_event as emit  # type: ignore
            except Exception:
                emit = None
        if emit is not None:
            try:
                attribution_log_id = (
                    emit(
                        client_id=task.customer_id,
                        job_type="dev_task_delivery",
                        status="success",
                        output_summary=(task.parent_objective or "")[:200],
                        evidence_url=(task.worker_report or "")[:400],
                        triggered_by="dev_orchestrator",
                        meta_json={"task_id": task_id, "state": task.state},
                    )
                    or ""
                )
            except Exception:
                attribution_log_id = ""

    await db.commit()
    return {
        "ok": True,
        "state": task.state,
        "notification_draft": draft,
        "auto_sent": False,
        "attribution_log_id": attribution_log_id,
    }
