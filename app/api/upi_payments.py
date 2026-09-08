"""Self-serve UPI payment API — "maine pay kiya" submission + admin review.

Public POST ``/upi/submit`` lets a customer report a UPI payment (ref + plan)
without waiting for a WhatsApp-screenshot + manual admin activation. Admins
review the pending queue and approve/reject. With ``UPI_AUTO_ACTIVATE=1`` the
plan auto-activates instantly on submit.

NO prefix here — the main app mounts this at ``/api`` (so routes become
``/api/upi/...``). Auth is enforced PER-ROUTE. Defensive:
import never fails, handlers never 500.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.auth_deps import require_admin
from app.api.customer_auth import optional_customer
from app.api.ratelimit import rate_limit

logger = logging.getLogger(__name__)

router = APIRouter(tags=["upi-payments"])


class UpiSubmitIn(BaseModel):
    plan: str
    upi_ref: str
    amount: float = 0
    payer_name: str = ""
    payer_contact: str = ""
    # client_id is derived from the customer's JWT — client CANNOT submit for someone else.
    client_id: str = ""
    # #240 reconciliation anchor. Accepted but NEVER trusted as submitted:
    # submit_payment re-resolves it against the offer store and refuses unknown,
    # expired, superseded, already-paid or plan-mismatched references.
    order_ref: str = ""


class UpiBindIn(BaseModel):
    """Admin-only bind payload — client_id for an unbound (guest) submission."""

    client_id: str = ""


@router.post(
    "/upi/submit",
    summary="Customer self-serve: maine pay kiya (UPI ref submit)",
    dependencies=[Depends(rate_limit("upi_submit", 10, 60))],
)
async def upi_submit(body: UpiSubmitIn, client_id: str = Depends(optional_customer)):
    """Customer (ya guest) apna UPI payment report karta hai. Never 500.

    client_id is derived from the customer's JWT when logged in — a client CANNOT
    submit for someone else's account. Guests (no token) submit a pending record
    keyed by payer_contact; admin reaches out + activates (frontend home-page pay
    modal path). Guests NEVER auto-activate: submit_payment only auto-activates
    when client_id is non-empty AND on the UPI_AUTO_ACTIVATE_CLIENTS allowlist.
    """
    try:
        from app.platform import upi_payments

        res = await asyncio.to_thread(
            upi_payments.submit_payment,
            client_id=client_id,
            plan=body.plan,
            upi_ref=body.upi_ref,
            amount=body.amount,
            payer_name=body.payer_name,
            payer_contact=body.payer_contact,
            order_ref=body.order_ref,
        )
        if not res.get("ok"):
            return {
                "ok": False,
                "error": res.get("error") or "Submit fail",
                "message": res.get("error") or "Submit fail — dobara try karo",
            }
        status = res.get("status", "pending")
        if status == "auto_activated":
            message = "Plan activate ho gaya — dhanyavaad!"
        else:
            message = "Mil gaya! Verify ho raha hai, jaldi activate."
        return {
            "ok": True,
            "status": status,
            "id": res.get("id"),
            "message": message,
        }
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("upi_submit failed: %s", e)
        return {
            "ok": False,
            "error": "internal",
            "message": "Kuch gadbad — thodi der baad try karo.",
        }


@router.get("/upi/pending", summary="Admin: pending UPI submissions queue")
async def upi_pending_list(_user=Depends(require_admin)):
    """Admin-only — pending plus approved-but-unactivated submissions."""
    try:
        from app.platform import upi_payments

        pending = await asyncio.to_thread(
            upi_payments.list_actionable
        )  # calls list_actionable() off-loop
        return {"ok": True, "pending": pending}
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("upi_pending_list failed: %s", e)
        return {"ok": False, "pending": []}


@router.post("/upi/pending/{pid}/approve", summary="Admin: approve a UPI submission")
async def upi_approve(pid: str, _user=Depends(require_admin)):
    """Admin-only — approve + activate plan (if client_id present)."""
    try:
        from app.platform import upi_payments

        rec = await asyncio.to_thread(upi_payments.decide, pid, True, decided_by="admin")
        return {"ok": rec.get("ok", True), "record": rec}
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("upi_approve failed: %s", e)
        return {"ok": False, "error": "internal"}


@router.post("/upi/pending/{pid}/bind", summary="Admin: bind a client to an unbound UPI submission")
async def upi_bind(pid: str, body: UpiBindIn, _user=Depends(require_admin)):
    """Admin-only — resolve a guest (unbound) submission (#304).

    Guest "maine pay kiya" submissions carry no client_id; approving one fails
    closed with ``approved_but_unbound``. This operator queue action binds the
    verified marketing client (fail-closed: unknown client / cross-tenant
    re-point refused), then Approve activates — the owner's Approve stays the
    single activation gate.
    """
    try:
        from app.platform import upi_payments

        rec = await asyncio.to_thread(
            upi_payments.bind_client, pid, (body.client_id or "").strip(), decided_by="admin"
        )
        return {"ok": rec.get("ok", True), "record": rec}
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("upi_bind failed: %s", e)
        return {"ok": False, "error": "internal"}


@router.post("/upi/pending/{pid}/reject", summary="Admin: reject a UPI submission")
async def upi_reject(pid: str, _user=Depends(require_admin)):
    """Admin-only — reject submission (no activation)."""
    try:
        from app.platform import upi_payments

        rec = await asyncio.to_thread(upi_payments.decide, pid, False, decided_by="admin")
        return {"ok": rec.get("ok", True), "record": rec}
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("upi_reject failed: %s", e)
        return {"ok": False, "error": "internal"}
