"""Ledger-backed daily Product-1 (Marketing) paid activations — IST day.

WHY (docs/gtm/PRODUCT1_50_PAID_DAY_90D.md): us plan ka north-star KPI "new paid
Marketing activations / day" hai aur Phase 1 ka exit criteria uska ledger-backed
admin number maangta hai. Ab tak iske liye koi count tha hi nahi — sirf MRR
snapshot delta (``revenue_snapshots``) tha, jo price change / plan edit / churn se
bhi hilta hai, isliye wo paid activation ka PROOF nahi hai.

TRUTH SOURCES (dono pehle se maujood ledgers — koi naya store nahi):
  - ``app.billing.gst_invoice``   → non-void invoice rows (``created_at``, ``plan``)
  - ``app.platform.upi_payments`` → approved / auto_activated rows (``decided_at``)

Manual UPI hi canonical rail hai: yeh module sirf PADHTA hai — kabhi approve /
activate / invoice create nahi karta, aur owner-confirm gate ko kabhi bypass nahi
karta. Kabhi raise nahi karta (partial/zero data = 0, fabricate kabhi nahi).

Honest definitions (dono alag hain, isliye dono report hote hain):
  - ``paid_today``        = aaj (IST) jitne DISTINCT marketing clients ka koi
    paid ledger event mila — naya ya renewal, dono.
  - ``activations_today`` = unme se woh clients jinka SABSE PEHLA paid event bhi
    aaj hi hai → yehi "new paid activation" KPI hai.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_IST = "Asia/Kolkata"

# "Owner ne bank credit confirm kar diya" — wahi set jo pay_truth.has_payment_proof()
# ledger-proof maanta hai. Yahan naya/alag payment semantics invent nahi kar rahe.
_PAID_UPI_STATUSES = ("approved", "auto_activated")

# gst_invoice.list_invoices() khud 500 pe hard-cap karta hai — lookback isi window
# tak bounded hai, aur wahi baat ``scan`` me honestly report hoti hai.
_INVOICE_WINDOW = 500


def _ist_day(raw: Any) -> str:
    """ISO/date string → ``YYYY-MM-DD`` in IST. Blank/garbage → ``""``.

    Ledger timestamps UTC me likhe jaate hain; IST day boundary 05:30 UTC pe
    shift hota hai, isliye din ka faisla convert karke hi lena hai (raw string
    slice galat din de dega raat ke invoices pe).
    """
    s = str(raw or "").strip()
    if not s:
        return ""
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    try:
        from zoneinfo import ZoneInfo

        return dt.astimezone(ZoneInfo(_IST)).strftime("%Y-%m-%d")
    except Exception:  # pragma: no cover - tzdata missing
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%d")


def today_ist() -> str:
    """Aaj ka IST din label."""
    return _ist_day(datetime.now(timezone.utc).isoformat())


def marketing_plan_keys() -> set[str]:
    """Paid Product-1 plan keys — ``packages.py`` hi single source of truth hai.

    Trial / ₹0 excluded (free ≠ paid). Voice-band aur combo plan ids ``PACKAGES``
    me hote hi nahi, phir bhi unhe explicitly subtract kiya jaata hai taaki koi
    future catalogue merge chupke se Marketing KPI ko inflate na kar de.

    Fail-CLOSED: packages padha hi na jaye to empty set → count 0. Ek metric ke
    liye under-report safe hai; guess karke paid count banana NAHI.
    """
    keys: set[str] = set()
    try:
        from app.marketing.packages import PACKAGES

        for p in PACKAGES or []:
            k = str((p or {}).get("key") or "").strip().lower()
            try:
                price = int((p or {}).get("price_inr_month") or 0)
            except Exception:
                price = 0
            if k and price > 0:
                keys.add(k)
    except Exception as e:
        logger.debug("[paid_activations] packages read failed: %s", e)
        return set()
    try:
        from app.marketing.voice_packages import VOICE_PLAN_IDS

        keys -= {str(k).strip().lower() for k in (VOICE_PLAN_IDS or []) if k}
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("[paid_activations] voice ids skipped: %s", e)
    try:
        from app.marketing.combo_packages import COMBO_PLAN_IDS

        keys -= {str(k).strip().lower() for k in (COMBO_PLAN_IDS or []) if k}
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("[paid_activations] combo ids skipped: %s", e)
    return keys


def _paid_events(
    plans: set[str], invoice_limit: int
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Har visible Marketing paid ledger event → ``{client_id, day, source, gross_inr}``.

    ``gross_inr`` sirf invoice se aata hai: UPI submissions ``amount: 0`` record
    karte hain (frontend me amount field hai hi nahi — upi_payments me documented),
    aur approve karte hi wahi payment ek GST invoice bhi fire karta hai, to UPI ka
    amount jodna double-count hota.
    """
    events: list[dict[str, Any]] = []
    scan: dict[str, Any] = {"invoices": 0, "invoice_window_saturated": False, "upi_rows": 0}
    try:
        from app.billing import gst_invoice

        rows = gst_invoice.list_invoices(invoice_limit) or []
        scan["invoices"] = len(rows)
        scan["invoice_window_saturated"] = len(rows) >= min(max(1, int(invoice_limit)), 500)
        for r in rows:
            if r.get("kind") == "void" or r.get("voided"):
                continue
            if str(r.get("plan") or "").strip().lower() not in plans:
                continue
            cid = str(r.get("client_id") or "").strip()
            day = _ist_day(r.get("created_at") or r.get("date"))
            if not cid or not day:
                continue
            try:
                gross = float(r.get("gross_inr") or 0)
            except Exception:
                gross = 0.0
            events.append({"client_id": cid, "day": day, "source": "invoice", "gross_inr": gross})
    except Exception as e:
        logger.debug("[paid_activations] invoice scan skip: %s", e)
    try:
        from app.platform import upi_payments

        rows = upi_payments.list_payments() or []
        scan["upi_rows"] = len(rows)
        for p in rows:
            st = str(p.get("status") or "").strip().lower()
            # Rejected pehle: ek baar activate hone ke baad reject hua record
            # `activated=True` rakhta hai, to sirf flags dekhne se wo paid gina jata.
            if st == "rejected":
                continue
            if (
                st not in _PAID_UPI_STATUSES
                and not p.get("activated")
                and not p.get("auto_activated")
            ):
                continue
            if str(p.get("plan") or "").strip().lower() not in plans:
                continue
            cid = str(p.get("client_id") or "").strip()
            day = _ist_day(p.get("decided_at"))
            if not cid or not day:
                continue
            events.append({"client_id": cid, "day": day, "source": "upi", "gross_inr": 0.0})
    except Exception as e:
        logger.debug("[paid_activations] upi scan skip: %s", e)
    return events, scan


def daily_paid_activations(
    day: str = "", *, invoice_limit: int = _INVOICE_WINDOW
) -> dict[str, Any]:
    """Aaj (ya diye gaye IST ``day``) ke Product-1 paid activations — ledger se.

    Dedupe ``client_id`` + din pe hota hai: ek hi UPI approve ek invoice bhi fire
    karta hai, aur dono ledger me alag row banti hai — bina dedupe ke ek customer
    do baar ginta. Never raises; kuch bhi tootne pe zeroes.
    """
    target = str(day or "").strip() or today_ist()
    out: dict[str, Any] = {
        "day": target,
        "tz": _IST,
        "paid_today": 0,
        "activations_today": 0,
        "gross_inr_today": 0.0,
        "clients": [],
        "events_by_source": {"invoice": 0, "upi": 0},
        "scan": {"invoices": 0, "invoice_window_saturated": False, "upi_rows": 0},
    }
    try:
        plans = marketing_plan_keys()
        if not plans:
            logger.debug("[paid_activations] no marketing plan keys resolved — reporting 0")
            return out
        events, scan = _paid_events(plans, invoice_limit)
        out["scan"] = scan
        first_day: dict[str, str] = {}
        today_rows: dict[str, dict[str, Any]] = {}
        for ev in events:
            cid = ev["client_id"]
            d = ev["day"]
            prev = first_day.get(cid)
            if not prev or d < prev:
                first_day[cid] = d
            if d != target:
                continue
            row = today_rows.setdefault(
                cid, {"client_id": cid, "sources": [], "gross_inr": 0.0, "new": False}
            )
            if ev["source"] not in row["sources"]:
                row["sources"].append(ev["source"])
            row["gross_inr"] = round(float(row["gross_inr"]) + float(ev.get("gross_inr") or 0), 2)
            out["events_by_source"][ev["source"]] = (
                int(out["events_by_source"].get(ev["source"]) or 0) + 1
            )
        for cid, row in today_rows.items():
            row["new"] = first_day.get(cid) == target
        out["paid_today"] = len(today_rows)
        out["activations_today"] = sum(1 for r in today_rows.values() if r["new"])
        out["gross_inr_today"] = round(sum(float(r["gross_inr"]) for r in today_rows.values()), 2)
        out["clients"] = sorted(today_rows.values(), key=lambda r: str(r["client_id"]))[:50]
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("[paid_activations] daily count failed: %s", e)
    return out


__all__ = ["daily_paid_activations", "marketing_plan_keys", "today_ist"]
