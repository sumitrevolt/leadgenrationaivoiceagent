"""revenue_sprint.py — 7-day ₹5L sprint conversion APIs (2026-08-23).

Research-driven batch jo EXISTING dormant engines ko wire karta hai:
* ``offers.issue_offer`` ka pehla ROUTE caller — WhatsApp close ke liye hosted
  pay-link with amount-prefilled UPI intent + QR (upi-pg pattern).
* ``promo_codes`` platform coupon engine — LAUNCH offer honest deadline ke saath
  (Lago-style definitions + applied ledger; original offer immutable rehta hai,
  discount = superseding offer).
* DFY setup fee jaise custom quotes ``offers.issue_custom_offer`` se.

Auth PER-ROUTE (upi_payments.py convention): admin issue/create = require_admin;
public read/apply = rate-limited, fail-closed on unknown/expired refs. Router ko
``prefix="/api"`` ke saath mount kiya jata hai.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.auth_deps import require_admin
from app.api.ratelimit import rate_limit

logger = logging.getLogger(__name__)

router = APIRouter(tags=["revenue-sprint"])


class OfferIssueIn(BaseModel):
    """Admin offer issuance — package-priced ya explicit custom amount."""

    deal_id: str
    package_code: str
    mode: str = "package"  # package | custom
    amount_inr: int = 0  # mode=custom only
    label: str = ""
    client_id: str = ""
    prospect_id: str = ""
    ttl_days: int = 30


class PromoCreateIn(BaseModel):
    code: str
    kind: str = "fixed_inr"  # fixed_inr | pct
    value: float = Field(gt=0)
    plan_ids: list[str] = Field(default_factory=list)
    once_per_customer: bool = True
    max_redemptions: int = 0
    expires_at: str = ""
    label: str = ""
    tags: list[str] = Field(default_factory=list)


class PromoApplyIn(BaseModel):
    code: str
    contact: str = ""


def _pay_payload(order_ref: str, off: dict) -> dict:
    """Offer → customer-facing pay payload (UPI intent am+tn prefilled + QR).

    tn me order_ref jata hai taaki bank-statement reconciliation trivial ho
    (upi-pg pattern). VPA unset ho to link/QR khali — page phir bhi dikhata hai.
    """
    try:
        from app.marketing.upi_kit import payment_kit
        from app.platform import upi_config

        vpa = upi_config.get_vpa()
        if not vpa:
            return {"armed": False, "upi_link": "", "qr_svg": "", "vpa": ""}
        note = f"LeadGenAI {order_ref}"[:80]
        kit = payment_kit("LeadGen AI", vpa, off.get("quoted_amount"), note)
        return {
            "armed": True,
            "vpa": vpa,
            "upi_link": kit.get("upi_link") or "",
            "qr_svg": kit.get("qr_svg") or "",
        }
    except Exception as e:
        logger.warning("[revenue_sprint] pay payload failed: %s", e)
        return {"armed": False, "upi_link": "", "qr_svg": "", "vpa": ""}


def _offer_public_view(off: dict) -> dict:
    return {
        "order_ref": off.get("order_ref"),
        "package_code": off.get("package_code"),
        "label": off.get("label") or "",
        "amount_inr": off.get("quoted_amount"),
        "currency": off.get("currency") or "INR",
        "expires_at": off.get("expires_at"),
        "status": off.get("status"),
        "promo_code": off.get("promo_code") or "",
        "promo_discount_inr": off.get("promo_discount_inr") or 0,
    }


@router.post(
    "/admin/revenue/offers/issue",
    summary="Admin: payable offer issue karo → hosted pay-link (WhatsApp close)",
)
async def admin_issue_offer(body: OfferIssueIn, _user=Depends(require_admin)):
    try:
        deal_id = (body.deal_id or "").strip()
        pkg = (body.package_code or "").strip()
        if not deal_id or not pkg:
            return {"ok": False, "error": "deal_id aur package_code required"}

        def _issue() -> dict | None:
            from app.marketing import offers

            if body.mode == "custom":
                return offers.issue_custom_offer(
                    deal_id,
                    pkg,
                    body.amount_inr,
                    label=body.label,
                    client_id=body.client_id,
                    prospect_id=body.prospect_id,
                    ttl_days=body.ttl_days,
                )
            return offers.issue_offer(
                deal_id,
                pkg,
                client_id=body.client_id,
                prospect_id=body.prospect_id,
                ttl_days=body.ttl_days,
            )

        off = await asyncio.to_thread(_issue)
        if not off:
            return {
                "ok": False,
                "error": (
                    "Offer issue nahi hua — unknown/unpriced package ya amount "
                    "bounds (₹99..₹10L) ke bahar"
                ),
            }
        ref = str(off.get("order_ref") or "")
        out = {"ok": True, **_offer_public_view(off), "pay_url": f"/pay/{ref}"}
        out.update(_pay_payload(ref, off))
        return out
    except Exception as e:
        logger.warning("admin_issue_offer failed: %s", e)
        return {"ok": False, "error": "internal"}


@router.get(
    "/admin/revenue/offers",
    summary="Admin: recent offers (issued/paid/superseded)",
)
async def admin_list_offers(deal_id: str = "", _user=Depends(require_admin)):
    try:
        from app.marketing import offers

        rows = await asyncio.to_thread(offers.list_offers, (deal_id or "").strip(), 100)
        return {"ok": True, "offers": [_offer_public_view(o) for o in rows]}
    except Exception as e:
        logger.warning("admin_list_offers failed: %s", e)
        return {"ok": False, "offers": []}


@router.post(
    "/admin/promo/create",
    summary="Admin: promo code define karo (launch offer, discount)",
)
async def admin_create_promo(body: PromoCreateIn, _user=Depends(require_admin)):
    try:
        from app.billing import promo_codes

        res = await asyncio.to_thread(
            promo_codes.create_code,
            body.code,
            body.kind,
            body.value,
            plan_ids=body.plan_ids,
            once_per_customer=body.once_per_customer,
            max_redemptions=body.max_redemptions,
            expires_at=body.expires_at,
            label=body.label,
            tags=body.tags,
        )
        return res
    except Exception as e:
        logger.warning("admin_create_promo failed: %s", e)
        return {"ok": False, "reason": "internal"}


@router.get("/admin/promo/list", summary="Admin: promo definitions + applied ledger")
async def admin_list_promo(_user=Depends(require_admin)):
    try:
        from app.billing import promo_codes

        defs = await asyncio.to_thread(promo_codes.list_definitions)
        applied = await asyncio.to_thread(promo_codes.list_applied, 200)
        return {"ok": True, "definitions": defs, "applied": applied}
    except Exception as e:
        logger.warning("admin_list_promo failed: %s", e)
        return {"ok": False, "definitions": [], "applied": []}


@router.get(
    "/public/offers/{order_ref}",
    summary="Public: order resolve → UPI pay-kit (amount-prefilled intent + QR)",
    dependencies=[Depends(rate_limit("offer_view", 60, 60))],
)
async def public_offer(order_ref: str):
    try:
        from app.marketing import offers

        ref = (order_ref or "").strip()
        off, reason = await asyncio.to_thread(offers.resolve_payable, ref)
        if not off:
            # Fail-closed: koi guessable-ref probing par data leak nahi.
            return {"ok": False, "reason": reason}
        out = {"ok": True, **_offer_public_view(off)}
        out.update(_pay_payload(ref, off))
        return out
    except Exception as e:
        logger.warning("public_offer failed: %s", e)
        return {"ok": False, "reason": "unavailable"}


@router.post(
    "/public/offers/{order_ref}/promo",
    summary="Public: order par promo code lagao → discounted supersede offer",
    dependencies=[Depends(rate_limit("offer_promo", 10, 60))],
)
async def public_apply_promo(order_ref: str, body: PromoApplyIn):
    try:
        from app.billing import promo_codes

        res = await asyncio.to_thread(
            promo_codes.apply_promo_to_order,
            (order_ref or "").strip(),
            body.code,
            customer_contact=body.contact,
        )
        if not res.get("ok"):
            return res
        new_ref = str(res.get("order_ref") or "")
        out = dict(res)
        out["pay_url"] = f"/pay/{new_ref}"
        return out
    except Exception as e:
        logger.warning("public_apply_promo failed: %s", e)
        return {"ok": False, "reason": "internal"}


@router.get(
    "/public/launch-offer",
    summary="Public: active launch offer (pricing-page countdown ka server-side deadline)",
)
async def public_launch_offer():
    try:
        from app.billing import promo_codes

        active = await asyncio.to_thread(promo_codes.active_launch_offer)
        if not active:
            return {"ok": False}
        return {
            "ok": True,
            "code": active.get("code"),
            "kind": active.get("kind"),
            "value": active.get("value"),
            "label": active.get("label") or "",
            "expires_at": active.get("expires_at") or "",
        }
    except Exception as e:
        logger.warning("public_launch_offer failed: %s", e)
        return {"ok": False}
