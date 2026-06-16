"""Customer-facing webhooks API — register, list, delete, test, deliveries.

Mounted under /api/customer/webhooks. Each route requires a customer JWT
(role=customer); the client_id is derived from the token, never accepted
from query/body (defends against the same IDOR class as the C1 billing fix).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.customer_auth import require_customer
from app.platform import customer_webhooks as cw

router = APIRouter(prefix="/api/customer/webhooks", tags=["Customer Webhooks"])


class WebhookCreateIn(BaseModel):
    url: str = Field(..., min_length=8, max_length=500)
    events: list[str] = Field(..., min_length=1, max_length=20)
    description: str = Field("", max_length=120)


@router.get("/_meta")
async def meta() -> dict[str, Any]:
    """Public meta: enabled state + supported event list. No auth (so SDKs can
    discover what's available without a token). No customer data leaks here."""
    return {
        "enabled": cw.enabled(),
        "supported_events": list(cw.SUPPORTED_EVENTS),
    }


@router.post("")
async def create(body: WebhookCreateIn, client_id: str = Depends(require_customer)) -> dict:
    """Create a webhook. Returns the FULL row including secret — this is the
    ONLY time the secret is visible. Save it customer-side immediately."""
    out = cw.register(
        client_id=client_id,
        url=body.url,
        events=body.events,
        description=body.description,
    )
    if not out.get("ok"):
        raise HTTPException(status_code=422, detail=out.get("error", "validation failed"))
    return out


@router.get("")
async def list_(client_id: str = Depends(require_customer)) -> dict:
    """List webhooks owned by the caller (secrets redacted to preview)."""
    items = cw.list_for(client_id)
    return {"count": len(items), "webhooks": items}


@router.delete("/{webhook_id}")
async def delete(webhook_id: str, client_id: str = Depends(require_customer)) -> dict:
    """Delete a webhook. 404 if not owned or not found."""
    ok = cw.remove(webhook_id, client_id)
    if not ok:
        raise HTTPException(status_code=404, detail="webhook not found")
    return {"deleted": True}


@router.post("/{webhook_id}/test")
async def test_fire(webhook_id: str, client_id: str = Depends(require_customer)) -> dict:
    """Send one synchronous test event (no retries) and return the outcome."""
    return await cw.fire_test(webhook_id, client_id)


@router.get("/{webhook_id}/deliveries")
async def deliveries(
    webhook_id: str,
    limit: int = 50,
    client_id: str = Depends(require_customer),
) -> dict:
    """Recent delivery attempts (success + failure)."""
    items = cw.recent_deliveries(webhook_id, client_id, limit=max(1, min(int(limit), 200)))
    return {"webhook_id": webhook_id, "count": len(items), "deliveries": items}


__all__ = ["router"]
