"""Admin API — owner-inbox one-shot email canary (super_admin only).

Never enables ``AUTO_EMAIL_OUTREACH``. Recipient is accepted from the authenticated
UI POST body and is never echoed back in cleartext (masked only).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.auth_deps import require_super_admin
from app.platform import owner_email_canary as _canary

router = APIRouter(prefix="/api/admin/owner-email-canary", tags=["Owner Email Canary"])


class CanarySendIn(BaseModel):
    to_email: str = Field(..., min_length=3, max_length=254)
    idempotency_key: str = Field(..., min_length=8, max_length=128)
    confirm: bool = False
    confirm_owner_inbox: bool = False


@router.get("/preflight")
async def owner_email_canary_preflight(_user=Depends(require_super_admin)) -> dict[str, Any]:
    return _canary.preflight()


@router.post("/send")
async def owner_email_canary_send(
    body: CanarySendIn,
    user=Depends(require_super_admin),
) -> dict[str, Any]:
    if not body.confirm or not body.confirm_owner_inbox:
        return {
            "ok": False,
            "outcome": _canary.BLOCKED,
            "reason": "confirm_and_owner_inbox_required",
            "provider_called": False,
        }
    return await _canary.send_canary(
        to_email=body.to_email,
        idempotency_key=body.idempotency_key,
        confirm=True,
        actor_id=str(getattr(user, "id", "") or ""),
    )


@router.get("/last")
async def owner_email_canary_last(_user=Depends(require_super_admin)) -> dict[str, Any]:
    """Expose last attempt OR failed preflight/authority truth (never fake ok)."""
    pf = _canary.preflight()
    if not pf.get("ok"):
        return {
            "ok": False,
            "outcome": pf.get("outcome") or _canary.BLOCKED,
            "reason": pf.get("reason") or "preflight_failed",
            "error_type": pf.get("error_type"),
            "last_attempt": pf.get("last_attempt"),
            "attempt_count": pf.get("attempt_count"),
        }
    return {
        "ok": True,
        "last_attempt": pf.get("last_attempt"),
        "attempt_count": pf.get("attempt_count"),
    }
