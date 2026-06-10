"""payment_recon.py — Razorpay vs internal records daily reconciliation.

Finance truth: jo paisa Razorpay me aaya, kya uska invoice/billing record bana?
Webhook miss (downtime/secret-issue) = silent revenue-leak — yeh sweep pakdega.

- Razorpay Payments API (last N din ke `captured`) fetch — WAHI creds jo billing
  use karta hai (settings.razorpay_key_id/secret). Creds unset = graceful skip.
- Match: payment.id ↔ data/invoices.jsonl (gst_invoice notes me payment/order id)
  + amount-paisa match fallback. Unmatched = MISMATCH list.
- Alert email GATED `PAYMENT_RECON=1` (OFF = report-only via API, zero change).
- digest job me wired (try/except). Kabhi raise nahi karta. READ-only (koi
  refund/transfer/charge NAHI — sirf compare).
- Store last run: data/payment_recon_last.json.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_INVOICES = os.path.join("data", "invoices.jsonl")
_LAST = os.path.join("data", "payment_recon_last.json")
_RZP_PAYMENTS = "https://api.razorpay.com/v1/payments"


def _enabled() -> bool:
    return os.environ.get("PAYMENT_RECON", "0").strip().lower() in ("1", "true", "yes")


def _creds() -> tuple[str, str]:
    try:
        from app.config import settings

        return ((settings.razorpay_key_id or "").strip(), (settings.razorpay_key_secret or "").strip())
    except Exception:
        return ("", "")


def _load_invoices() -> list[dict]:
    try:
        if not os.path.exists(_INVOICES):
            return []
        with open(_INVOICES, encoding="utf-8") as f:
            return [json.loads(x) for x in f if x.strip()]
    except Exception:
        return []


def match_payments(payments: list[dict], invoices: list[dict]) -> dict[str, Any]:
    """Pure helper (testable, no network): captured payments ko invoices se match.

    Match keys: payment id / order id invoice ke kisi bhi string field me, ya
    exact amount-paisa + same-day match (fallback).
    """
    inv_blob = []
    for inv in invoices:
        try:
            inv_blob.append((json.dumps(inv, ensure_ascii=False), inv))
        except Exception:
            continue
    matched, unmatched = [], []
    for p in payments:
        pid = str(p.get("id") or "")
        oid = str(p.get("order_id") or "")
        amt = int(p.get("amount") or 0)  # paisa
        day = time.strftime("%Y-%m-%d", time.gmtime(int(p.get("created_at") or 0)))
        hit = None
        for blob, inv in inv_blob:
            if (pid and pid in blob) or (oid and oid in blob):
                hit = inv
                break
        if hit is None:
            for blob, inv in inv_blob:
                try:
                    inv_paisa = int(round(float(inv.get("gross_inr") or inv.get("total") or inv.get("total_inr") or 0) * 100))
                except Exception:
                    inv_paisa = -1
                if amt and inv_paisa == amt and str(inv.get("date", ""))[:10] == day:
                    hit = inv
                    break
        row = {"payment_id": pid, "amount_inr": round(amt / 100, 2), "day": day,
               "email": (p.get("email") or ""), "contact": str(p.get("contact") or "")}
        if hit is not None:
            row["invoice"] = hit.get("number") or hit.get("invoice_number") or "?"
            matched.append(row)
        else:
            unmatched.append(row)
    gross = round(sum(int(p.get("amount") or 0) for p in payments) / 100, 2)
    return {"total_payments": len(payments), "gross_inr": gross,
            "matched": len(matched), "unmatched": unmatched}


async def run(days: int = 3) -> dict[str, Any]:
    """Razorpay fetch + match + (gated) mismatch alert. READ-only."""
    kid, ksec = _creds()
    if not kid or not ksec:
        return {"ok": False, "skipped": "razorpay creds unset"}
    try:
        import httpx

        now = int(time.time())
        params = {"from": now - days * 86400, "to": now, "count": 100, "status": "captured"}
        async with httpx.AsyncClient(timeout=20, auth=(kid, ksec)) as cx:
            r = await cx.get(_RZP_PAYMENTS, params=params)
        if r.status_code != 200:
            return {"ok": False, "error": f"razorpay {r.status_code}: {r.text[:120]}"}
        payments = [p for p in (r.json().get("items") or []) if p.get("status") == "captured"]
        report = match_payments(payments, _load_invoices())
        report.update({"ok": True, "days": days, "ts": now})
        try:
            os.makedirs(os.path.dirname(_LAST) or ".", exist_ok=True)
            with open(_LAST, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False)
        except Exception:
            pass
        if report["unmatched"] and _enabled():
            try:
                from app.integrations.email_sender import email_sender

                notify = os.environ.get("NOTIFY_EMAIL", "").strip()
                if notify:
                    lines = "\n".join(
                        f"- {u['payment_id']} ₹{u['amount_inr']} ({u['day']}) {u['email']} {u['contact']}"
                        for u in report["unmatched"][:20]
                    )
                    await email_sender.send_email(
                        [notify],
                        f"⚠️ Payment recon: {len(report['unmatched'])} captured payment(s) bina invoice",
                        "Razorpay me paise aaye par invoice/record nahi mila (webhook miss?):\n\n"
                        + lines
                        + "\n\nCheck: Razorpay dashboard webhook delivery + /api/growth/revenue/invoices.",
                    )
            except Exception as e:
                logger.warning(f"[recon] alert fail: {e}")
        logger.info(f"[recon] {report['matched']}/{report['total_payments']} matched, "
                    f"{len(report['unmatched'])} unmatched")
        return report
    except Exception as e:
        logger.warning(f"[recon] run fail: {e}")
        return {"ok": False, "error": str(e)[:160]}


async def run_if_enabled(days: int = 3) -> dict[str, Any]:
    """Scheduler hook — sirf PAYMENT_RECON=1 pe chalti (default OFF = zero change)."""
    if not _enabled():
        return {"ok": False, "skipped": "PAYMENT_RECON off"}
    return await run(days)


def last_report() -> dict[str, Any]:
    try:
        if os.path.exists(_LAST):
            return json.load(open(_LAST, encoding="utf-8"))
    except Exception:
        pass
    return {"ok": False, "note": "abhi koi run nahi hua"}
