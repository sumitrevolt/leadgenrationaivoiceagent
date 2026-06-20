"""Deliverability / bookings / reviews / webhook-register endpoints.

Extracted from app/api/growth.py (2026-06-20 refactor) to shrink the god-router.
Mounted via growth.router.include_router(); paths unchanged (/api/growth/...).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.auth_deps import require_admin

router = APIRouter(tags=["Growth"])


# ---------------- Deliverability / bookings / reviews / webhooks ---------------- #
@router.get("/deliverability")
async def deliverability_check(_user=Depends(require_admin)):
    """SPF/DMARC + IP blacklist check abhi chalao (Smartlead-pattern)."""
    from app.platform import deliverability_monitor

    return await deliverability_monitor.run_check()


@router.get("/deliverability/summary")
async def deliverability_summary(_user=Depends(require_admin)):
    """DNS + warmup + complaint gate — admin cockpit (2026 deliverability)."""
    from app.platform import eval_hub

    return await eval_hub.deliverability_summary()


@router.post("/infra/rag-retrieval-ab")
async def infra_rag_retrieval_ab(_user=Depends(require_admin)):
    """Run offline RAG A/B gate (baseline vs rerank/hybrid/full) — prove before flip."""
    from app.platform import eval_hub

    return await eval_hub.run_rag_ab_gate(timeout_s=120.0)


@router.get("/bookings/upcoming")
async def bookings_upcoming(all: bool = False, _user=Depends(require_admin)):
    from app.platform import booking_reminders

    if all:
        return booking_reminders.list_all(50)
    return booking_reminders.upcoming(30)


@router.post("/bookings/remind-run")
async def bookings_remind_run(_user=Depends(require_admin)):
    """Booking reminders sweep (gated BOOKING_REMINDERS)."""
    from app.platform import booking_reminders

    return await booking_reminders.run_due()


class BookingNoShowIn(BaseModel):
    booking_id: str


@router.post("/bookings/no-show")
async def bookings_no_show(body: BookingNoShowIn, _user=Depends(require_admin)):
    """Appointment no-show mark + journey drafts (gated JOURNEY_ENGINE)."""
    from app.platform import booking_reminders

    return await booking_reminders.mark_no_show(body.booking_id.strip())


@router.post("/reviews/monitor-run")
async def reviews_monitor_run(_user=Depends(require_admin)):
    """Naye Google reviews check + AI reply drafts (gated REVIEW_MONITOR)."""
    from app.marketing import review_monitor

    return await review_monitor.run_check()


@router.get("/reviews/drafts")
async def reviews_drafts(_user=Depends(require_admin)):
    from app.marketing import review_monitor

    return review_monitor.recent_drafts(30)


class WebhookIn(BaseModel):
    url: str
    events: list[str] | None = None
    client_id: str | None = ""
    secret: str | None = ""


@router.post("/webhooks/register")
async def webhooks_register(body: WebhookIn, _user=Depends(require_admin)):
    """Zapier-style outbound webhook register (https only, HMAC-signed)."""
    from app.platform import outbound_webhooks

    return outbound_webhooks.register(
        body.url, body.events, body.client_id or "", body.secret or ""
    )


@router.get("/webhooks")
async def webhooks_list(_user=Depends(require_admin)):
    from app.platform import outbound_webhooks

    return {
        "webhooks": outbound_webhooks.list_webhooks(),
        "deliveries": outbound_webhooks.recent_deliveries(20),
    }


@router.delete("/webhooks/{webhook_id}")
async def webhooks_remove(webhook_id: str, _user=Depends(require_admin)):
    from app.platform import outbound_webhooks

    return {"removed": outbound_webhooks.remove(webhook_id)}
