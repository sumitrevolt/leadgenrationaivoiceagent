"""Owner Revenue Kit — one-screen revenue + one-click UPI confirm (M3, T04).

WHY THIS EXISTS
---------------
PRD §2c: the owner is the sole human operator and must run the business in ~15-30
min/day. This module is the **owner-facing surface** that:
  * shows pending UPI payments (money in-flight),
  * shows the honest collected ₹ (via `gst_invoice.stats()`),
  * shows the capacity bottleneck (via `capacity_ledger`), and
  * lets the owner confirm a bank credit with **ONE click** → real invoice
    (via `app.billing.owner_upi_confirm`) — the ONLY manual money step.

Routes are **genuinely gated** by `require_admin`. NO payment gateway is exposed.

FastAPI gotcha respected (ARCH §M5): signature-level `Depends(...)` lands in
``route.dependant.dependencies``, NOT ``route.dependencies``. Gated routes below
use a real signature `Depends(require_admin)`.

Evidence label: CODE-PRESENT (new module, pinned by tests/test_capacity_ledger.py
+ tests/test_owner_upi_confirm.py).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends

from app.api.auth_deps import require_admin

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Owner Revenue Kit"])


def _revenue_stats() -> dict[str, Any]:
    """Real collected-₹ truth from the GST invoice ledger. Never raises."""
    try:
        from app.billing import gst_invoice

        return gst_invoice.stats()
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("[owner_revenue_kit] stats failed: %s", e)
        return {}


def _capacity() -> dict[str, Any]:
    """Honest capacity snapshot. Never raises."""
    try:
        from app.platform import capacity_ledger

        snap = capacity_ledger.read_snapshot()
        return snap or capacity_ledger.build_snapshot()
    except Exception:
        return {}


@router.get("/app/revenue-kit/summary")
async def revenue_kit_summary(_admin=Depends(require_admin)) -> dict[str, Any]:
    """One-screen owner summary: collected ₹, pending queue, capacity gap. Gated."""
    pending: list[dict[str, Any]] = []
    try:
        from app.billing import owner_upi_confirm

        pending = owner_upi_confirm.list_pending_confirmations()
    except Exception:
        pending = []
    stats = _revenue_stats()
    cap = _capacity()
    return {
        "collected_fy_gross_inr": stats.get("fy_gross_inr", 0),
        "fy": stats.get("fy", ""),
        "pending_confirmations": len(pending),
        "pending": pending[:50],
        "capacity": cap,
        "payment_method": "owner_confirmed_upi",
        "gateway": None,  # explicit: NO gateway
    }


@router.get("/app/revenue-kit/pending")
async def revenue_kit_pending(_admin=Depends(require_admin)) -> dict[str, Any]:
    """Pending UPI submissions awaiting the one-click bank-credit confirm. Gated."""
    try:
        from app.billing import owner_upi_confirm

        rows = owner_upi_confirm.list_pending_confirmations()
    except Exception:
        rows = []
    return {"pending": rows, "count": len(rows)}


@router.post("/app/revenue-kit/confirm/{payment_id}")
async def revenue_kit_confirm(
    payment_id: str,
    _admin=Depends(require_admin),
) -> dict[str, Any]:
    """ONE-CLICK owner confirmation → real invoice. Gated. Never raises.

    Produces a real invoice via `app.billing.gst_invoice`; sets
    `payment_verification_method = owner_confirmed_upi`. NO gateway.
    """
    try:
        from app.billing import owner_upi_confirm

        result = owner_upi_confirm.confirm_payment(payment_id, confirmed_by="owner")
        return result
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("[owner_revenue_kit] confirm failed: %s", e)
        return {"ok": False, "payment_id": payment_id, "error": str(e)[:200]}


__all__ = ["router", "revenue_kit_summary", "revenue_kit_pending", "revenue_kit_confirm"]
