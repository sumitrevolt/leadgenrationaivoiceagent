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


class WebhookToggleIn(BaseModel):
    enabled: bool


@router.get("/_meta")
async def meta() -> dict[str, Any]:
    """Public meta: enabled state + supported event list. No auth (so SDKs can
    discover what's available without a token). No customer data leaks here."""
    return {
        "enabled": cw.enabled(),
        "supported_events": list(cw.SUPPORTED_EVENTS),
        "verifier_doc": "/api/customer/webhooks/_verifier-examples",
    }


_VERIFIER_PY = '''# Python — verify a LeadsGenAI webhook (Flask/FastAPI/Django)
import hmac, hashlib

WEBHOOK_SECRET = b"whsec_xxxxxxxx"   # value shown ONCE at registration

def verify(body: bytes, signature_header: str) -> bool:
    """signature_header is the literal value of X-LeadGen-Signature, e.g.
    'sha256=ab12cd34...'. body is the raw HTTP body bytes (NOT json.loads'd)."""
    if not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(WEBHOOK_SECRET, body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature_header[7:], expected)

# Flask:
# @app.post("/hook")
# def hook():
#     if not verify(request.get_data(), request.headers.get("X-LeadGen-Signature", "")):
#         return ("bad signature", 401)
#     payload = request.get_json()
#     ...
'''

_VERIFIER_NODE = """// Node.js (Express) — verify a LeadsGenAI webhook
const crypto = require("crypto");
const WEBHOOK_SECRET = "whsec_xxxxxxxx";   // value shown ONCE at registration

function verify(rawBody, signatureHeader) {
  if (!signatureHeader || !signatureHeader.startsWith("sha256=")) return false;
  const expected = crypto.createHmac("sha256", WEBHOOK_SECRET)
                         .update(rawBody)
                         .digest("hex");
  // constant-time compare
  return crypto.timingSafeEqual(
    Buffer.from(signatureHeader.slice(7), "hex"),
    Buffer.from(expected, "hex"),
  );
}

// app.post("/hook", express.raw({type: "application/json"}), (req, res) => {
//   if (!verify(req.body, req.headers["x-leadgen-signature"])) {
//     return res.status(401).send("bad signature");
//   }
//   const payload = JSON.parse(req.body.toString());
//   ...
// });
"""


@router.get("/_verifier-examples")
async def verifier_examples() -> dict[str, Any]:
    """Public — drop-in HMAC verifier code for Python + Node. Customer SDK
    builders read this to integrate without reverse-engineering our headers."""
    return {
        "scheme": "HMAC-SHA256",
        "headers": {
            "signature": "X-LeadGen-Signature  (format: sha256=<hex>)",
            "event": "X-LeadGen-Event  (e.g. lead.qualified, call.completed, call.report.ready)",
            "delivery": "X-LeadGen-Delivery  (unique per attempt — use for idempotency)",
        },
        "important": [
            "Sign the RAW body bytes — not the json.loads'd payload.",
            "Use constant-time compare (hmac.compare_digest / crypto.timingSafeEqual).",
            "Be idempotent — respond 200 even if you already processed the X-LeadGen-Delivery ID.",
            "Respond within 10s — we treat anything else as a failure and retry.",
            "Reject signatures older than your tolerance window (LeadGenAI does not currently send a timestamp; use delivery ID dedup).",
        ],
        "python_example": _VERIFIER_PY,
        "node_example": _VERIFIER_NODE,
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


@router.patch("/{webhook_id}")
async def update(
    webhook_id: str,
    body: WebhookToggleIn,
    client_id: str = Depends(require_customer),
) -> dict:
    """L.1: pause/resume a webhook. enabled=False stops emit() from firing it;
    delivery history + secret + subscriptions preserved."""
    out = cw.set_enabled(webhook_id, client_id, body.enabled)
    if not out.get("ok"):
        raise HTTPException(status_code=404, detail=out.get("error", "update failed"))
    return out


@router.post("/{webhook_id}/rotate-secret")
async def rotate_secret(webhook_id: str, client_id: str = Depends(require_customer)) -> dict:
    """K.3: rotate the signing secret in-place. Returns new secret ONCE."""
    out = cw.rotate_secret(webhook_id, client_id)
    if not out.get("ok"):
        raise HTTPException(status_code=404, detail=out.get("error", "rotate failed"))
    return out


@router.post("/{webhook_id}/deliveries/{delivery_id}/retry")
async def retry_delivery(
    webhook_id: str,
    delivery_id: str,
    client_id: str = Depends(require_customer),
) -> dict:
    """K.2: re-fire a prior failed delivery. The new attempt is logged with a
    fresh delivery_id; the original failure record stays intact for audit."""
    out = await cw.retry_delivery(webhook_id, client_id, delivery_id)
    if not out.get("delivered") and out.get("error") in (
        "webhook_not_found",
        "delivery_not_found",
        "delivery_already_succeeded",
    ):
        raise HTTPException(status_code=404, detail=out["error"])
    return out


__all__ = ["router"]
