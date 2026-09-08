"""Revenue automation (dunning / client-health / lifecycle / digest) + GST invoicing
(Rule-46 sequential FY numbering) + usage upsell alerts endpoints.

Extracted from app/api/growth.py (2026-06-20 refactor) to shrink the god-router.
Mounted via growth.router.include_router(); paths unchanged (/api/growth/revenue/*).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.auth_deps import require_admin

router = APIRouter(tags=["Growth"])


# ------------------- Revenue automation (dunning/health/lifecycle/digest) ------------------- #
class DunningCaseIn(BaseModel):
    client_id: str
    amount: float | None = None
    gateway: str | None = ""
    reason: str | None = ""


@router.post("/revenue/dunning/case")
async def dunning_open_case(body: DunningCaseIn, _user=Depends(require_admin)):
    """Manual dunning case (webhook ke bahar se) — recovery sequence shuru."""
    from app.billing import dunning

    return await dunning.on_payment_failed(
        body.client_id, body.amount, body.gateway or "", body.reason or ""
    )


@router.post("/revenue/dunning/run")
async def dunning_run(_user=Depends(require_admin)):
    """Dunning sweep abhi chalao (gated DUNNING_ENGINE — off = no-op)."""
    from app.billing import dunning

    return await dunning.run_due()


@router.get("/revenue/dunning")
async def dunning_overview(_user=Depends(require_admin)):
    """Dunning stats + open cases."""
    from app.billing import dunning

    return dunning.stats()


@router.get("/revenue/health/clients")
async def client_health_report(_user=Depends(require_admin)):
    """Saare clients ka churn-risk health score (red pehle)."""
    from app.platform import client_health

    return await client_health.health_report()


@router.post("/revenue/health/run")
async def client_health_run(_user=Depends(require_admin)):
    """Health check + (gated CLIENT_HEALTH_ALERTS) red-client email alert."""
    from app.platform import client_health

    return await client_health.run_check()


class LifecycleEnrollIn(BaseModel):
    email: str
    business_name: str | None = ""
    client_id: str | None = ""
    plan: str | None = "starter"


@router.post("/revenue/lifecycle/enroll")
async def lifecycle_enroll(body: LifecycleEnrollIn, _user=Depends(require_admin)):
    """Manually kisi signup ko nurture sequence me daalo."""
    from app.marketing import lifecycle_nurture

    return lifecycle_nurture.enroll(
        body.email, body.business_name or "", body.client_id or "", body.plan or "starter"
    )


@router.post("/revenue/lifecycle/run")
async def lifecycle_run(_user=Depends(require_admin)):
    """Nurture sweep abhi chalao (gated LIFECYCLE_NURTURE — off = no-op)."""
    from app.marketing import lifecycle_nurture

    return await lifecycle_nurture.run_due()


@router.get("/revenue/lifecycle")
async def lifecycle_overview(_user=Depends(require_admin)):
    """Nurture funnel stats."""
    from app.marketing import lifecycle_nurture

    return lifecycle_nurture.stats()


@router.post("/revenue/digest/run")
async def revenue_digest_run(_user=Depends(require_admin)):
    """Revenue digest abhi banao+bhejo (force — gate/dedupe skip)."""
    from app.platform import revenue_digest

    return await revenue_digest.run(force=True)


# ------------- GST invoicing (gst_invoice.py — Rule 46, sequential FY numbering) ------------- #
@router.get("/revenue/invoices")
async def revenue_invoices(limit: int = 50, _user=Depends(require_admin)):
    """Invoice list + FY stats (latest first)."""
    from app.billing import gst_invoice

    return {"stats": gst_invoice.stats(), "invoices": gst_invoice.list_invoices(limit)}


@router.post("/revenue/invoice")
async def revenue_invoice_create(payload: dict, _user=Depends(require_admin)):
    """Manual invoice banao: {client_id, plan, amount_inr?, payment_ref?, gateway?}."""
    from app.billing import gst_invoice

    inv = await gst_invoice.on_payment_success(
        str(payload.get("client_id") or ""),
        str(payload.get("plan") or ""),
        payment_ref=str(payload.get("payment_ref") or ""),
        gateway=str(payload.get("gateway") or ""),
        amount_inr=payload.get("amount_inr"),
    )
    return inv or {"error": "invoice nahi bana — client_id/plan/amount check karo"}


@router.post("/revenue/invoice-void")
async def revenue_invoice_void(payload: dict, _user=Depends(require_admin)):
    """Accountant-safe invoice VOID: {number, reason?}. Record delete NAHI hota —
    append-only void marker (Rule-46 sequence intact, gross reporting se excluded).
    2026-07-18 billing containment: synthetic test invoices ka correction path."""
    from app.billing import gst_invoice

    number = str(payload.get("number") or "").strip()
    if not number:
        return {"ok": False, "error": "number chahiye (e.g. INV/2026-27/0003)"}
    by = str(getattr(_user, "email", "") or "admin")
    return gst_invoice.void_invoice(number, reason=str(payload.get("reason") or ""), by=by)


@router.get("/revenue/invoices.csv")
async def revenue_invoices_csv(fy: str = "", _user=Depends(require_admin)):
    """GSTR-friendly CSV export (?fy=2026-27 optional filter) — accounting/CA ke liye."""
    import csv
    import io

    from fastapi.responses import PlainTextResponse

    from app.billing import gst_invoice

    rows = gst_invoice.list_invoices(5000)
    if fy.strip():
        rows = [r for r in rows if r.get("fy") == fy.strip()]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        [
            "number",
            "date",
            "fy",
            "client_id",
            "recipient",
            "recipient_gstin",
            "plan",
            "description",
            "sac_code",
            "taxable_value",
            "cgst",
            "sgst",
            "igst",
            "gross_inr",
            "place_of_supply",
            "tax_mode",
            "payment_ref",
            "gateway",
            "status",
        ]
    )
    for r in rows:
        rec = r.get("recipient", {}) or {}
        w.writerow(
            [
                r.get("number"),
                r.get("date"),
                r.get("fy"),
                r.get("client_id"),
                rec.get("name"),
                rec.get("gstin"),
                r.get("plan"),
                r.get("description"),
                r.get("sac_code"),
                r.get("taxable_value"),
                r.get("cgst"),
                r.get("sgst"),
                r.get("igst"),
                r.get("gross_inr"),
                r.get("place_of_supply"),
                r.get("tax_mode"),
                r.get("payment_ref"),
                r.get("gateway"),
                "voided" if r.get("voided") else "",
            ]
        )
    return PlainTextResponse(buf.getvalue(), media_type="text/csv")


@router.post("/revenue/topup-link")
async def revenue_topup_link(payload: dict, _user=Depends(require_admin)):
    """Voice-minute top-up pack info: {client_id, pack: topup_100|topup_250|topup_500}.

    Razorpay removed 2026-06-18 — automated payment links gone. Returns the pack
    details so the operator can collect via manual UPI and credit minutes manually.
    """
    from app.marketing.packages import get_topup_packs, topup_pack

    cid = str(payload.get("client_id") or "").strip()
    pack = topup_pack(str(payload.get("pack") or "topup_100"))
    if not cid or not pack:
        return {"ok": False, "error": "client_id + valid pack chahiye", "packs": get_topup_packs()}
    return {
        "ok": False,
        "error": "Online payment links band — manual UPI se collect karo, phir minutes credit karo.",
        "pack": pack,
    }


@router.get("/revenue/topup-packs")
async def revenue_topup_packs(_user=Depends(require_admin)):
    from app.marketing.packages import get_topup_packs

    return {"packs": get_topup_packs()}


@router.get("/revenue/invoice-html")
async def revenue_invoice_html(number: str, _user=Depends(require_admin)):
    """Printable HTML invoice (?number=INV/2026-27/0001 — number me '/' isliye query param)."""
    from fastapi.responses import HTMLResponse

    from app.billing import gst_invoice

    inv = gst_invoice.get_by_number(number)
    if not inv:
        return {"error": "invoice not found"}
    return HTMLResponse(gst_invoice.invoice_html(inv))


# ------------- Usage upsell alerts (usage_alerts.py — 80%/100% minute triggers) ------------- #
@router.post("/revenue/usage-alerts/run")
async def usage_alerts_run(_user=Depends(require_admin)):
    """Usage-threshold sweep abhi chalao (send gated USAGE_ALERTS=1; record hamesha)."""
    from app.billing import usage_alerts

    return await usage_alerts.run_check()


@router.get("/revenue/usage-alerts")
async def usage_alerts_recent(limit: int = 50, _user=Depends(require_admin)):
    """Recent usage alerts (latest first)."""
    from app.billing import usage_alerts

    return {"alerts": usage_alerts.recent(limit)}
