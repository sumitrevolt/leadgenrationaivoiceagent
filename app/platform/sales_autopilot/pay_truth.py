"""Sales Autopilot pay-truth — converted ≠ paid without ledger proof.

Joins autopilot ``converted`` / ``awaiting_payment`` prospects to invoices + UPI
rows by ``converted_client_id``. Never fabricates payment, never auto-activates.
Chase = handoff + best-effort ntfy. Never raises.
"""

from __future__ import annotations

from typing import Any

from app.platform.sales_autopilot import handoff as _handoff
from app.platform.sales_autopilot import store as _store
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def has_payment_proof(client_id: str) -> dict[str, Any]:
    """True iff a non-void invoice OR approved/activated UPI row exists for client_id."""
    cid = str(client_id or "").strip()
    out: dict[str, Any] = {
        "client_id": cid,
        "paid": False,
        "via": None,
        "invoice": None,
        "upi": None,
    }
    if not cid:
        return out
    try:
        from app.billing import gst_invoice

        for inv in gst_invoice.list_invoices(limit=500):
            if inv.get("voided"):
                continue
            if str(inv.get("client_id") or "").strip() != cid:
                continue
            # Live invoice row = ledger proof (amount may be 0 for credit notes — still real)
            out["paid"] = True
            out["via"] = "invoice"
            out["invoice"] = {
                "number": inv.get("number") or inv.get("invoice_no"),
                "gross_inr": inv.get("gross_inr"),
                "status": inv.get("status"),
            }
            return out
    except Exception as e:
        logger.debug("[pay_truth] invoice scan skip: %s", e)
    try:
        from app.platform import upi_payments

        for p in upi_payments.list_payments():
            if str(p.get("client_id") or "").strip() != cid:
                continue
            st = str(p.get("status") or "").lower()
            if (
                st in ("approved", "auto_activated")
                or p.get("activated")
                or p.get("auto_activated")
            ):
                out["paid"] = True
                out["via"] = "upi"
                out["upi"] = {
                    "id": p.get("id"),
                    "status": p.get("status"),
                    "amount": p.get("amount"),
                }
                return out
    except Exception as e:
        logger.debug("[pay_truth] upi scan skip: %s", e)
    return out


def enrich_prospect(rec: dict[str, Any]) -> dict[str, Any]:
    """Attach pay_truth fields to a prospect dict (non-mutating copy)."""
    row = dict(rec or {})
    cid = str(row.get("converted_client_id") or "").strip()
    proof = has_payment_proof(cid) if cid else {"paid": False, "via": None, "client_id": ""}
    row["payment_verified"] = bool(proof.get("paid"))
    row["payment_via"] = proof.get("via")
    st = str(row.get("status") or "")
    if st == _store.STATUS_CONVERTED and cid and not proof.get("paid"):
        row["revenue_status"] = "awaiting_payment"
    elif st == _store.STATUS_AWAITING_PAYMENT:
        row["revenue_status"] = "awaiting_payment"
    elif st == _store.STATUS_CONVERTED and proof.get("paid"):
        row["revenue_status"] = "paid"
    else:
        row["revenue_status"] = st or "unknown"
    return row


_CHASE_DONE_STEP = "hq_chase_done"
_CHASE_PARK_STEP = "hq_chase_admin"


def reconcile_pay_truth(*, chase: bool = True) -> dict[str, Any]:
    """Demote unpaid converted → awaiting_payment; restore proofed awaiting → converted.

    Never marks paid without ledger. Optional chase records payment_reminder + ntfy.
    """
    summary: dict[str, Any] = {
        "scanned": 0,
        "demoted": 0,
        "restored": 0,
        "chased": 0,
        "items": [],
    }
    try:
        for rec in _store.list_prospects(limit=2000):
            st = str(rec.get("status") or "")
            if st not in (_store.STATUS_CONVERTED, _store.STATUS_AWAITING_PAYMENT):
                continue
            summary["scanned"] += 1
            pid = str(rec.get("id") or "")
            cid = str(rec.get("converted_client_id") or "").strip()
            proof = has_payment_proof(cid) if cid else {"paid": False}
            if st == _store.STATUS_CONVERTED and (not cid or not proof.get("paid")):
                _store.mark_status(
                    pid,
                    _store.STATUS_AWAITING_PAYMENT,
                    payment_verified=False,
                    pay_truth_note="converted_without_ledger",
                )
                summary["demoted"] += 1
                summary["items"].append({"id": pid, "action": "demoted", "client_id": cid})
                if chase:
                    steps = list(rec.get("steps_done") or [])
                    if _CHASE_DONE_STEP not in steps and _CHASE_PARK_STEP not in steps:
                        _chase_unpaid(pid, rec)
                        summary["chased"] += 1
            elif st == _store.STATUS_AWAITING_PAYMENT and cid and proof.get("paid"):
                _store.mark_status(
                    pid,
                    _store.STATUS_CONVERTED,
                    payment_verified=True,
                    payment_via=proof.get("via"),
                    pay_truth_note="ledger_proof_found",
                )
                summary["restored"] += 1
                summary["items"].append(
                    {"id": pid, "action": "restored", "client_id": cid, "via": proof.get("via")}
                )
            elif st == _store.STATUS_AWAITING_PAYMENT and chase:
                steps = list(rec.get("steps_done") or [])
                # Hot Queue Done/Park must also silence scheduler ntfy chase.
                if _CHASE_DONE_STEP in steps or _CHASE_PARK_STEP in steps:
                    continue
                _chase_unpaid(pid, rec)
                summary["chased"] += 1
                summary["items"].append({"id": pid, "action": "chased", "client_id": cid})
        return summary
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("[pay_truth] reconcile failed: %s", e)
        summary["error"] = str(e)[:160]
        return summary


def _chase_unpaid(prospect_id: str, rec: dict[str, Any]) -> None:
    try:
        _handoff.payment_reminder(prospect_id)
    except Exception:
        pass
    try:
        from app.integrations import ntfy

        name = rec.get("name") or prospect_id
        cid = rec.get("converted_client_id") or "-"
        ntfy.push_bg(
            "💰 Unpaid converted — chase",
            f"{name} client={cid} — ledger me payment nahi. /start → Billing ₹1999. "
            f"Kabhi manual mark-paid mat karo.",
            priority="high",
            tags=["moneybag", "warning"],
        )
    except Exception:
        pass


def _paychase_awaiting_id(hq_id: str) -> str:
    """Return prospect_id only when hq_id is paychase:<id> and status is awaiting_payment."""
    raw = (hq_id or "").strip()
    if not raw.startswith("paychase:"):
        return ""
    pid = raw.split(":", 1)[1].strip()
    if not pid:
        return ""
    rec = _store.get_prospect(pid)
    if not rec or rec.get("status") != _store.STATUS_AWAITING_PAYMENT:
        return ""
    return pid


def mark_paychase_done(hq_id: str) -> bool:
    """Clear a synthetic pay-chase Hot Queue card (hq_id = paychase:<prospect_id>)."""
    pid = _paychase_awaiting_id(hq_id)
    if not pid:
        return False
    try:
        _store.add_step_done(pid, _CHASE_DONE_STEP)
        return True
    except Exception as e:
        logger.debug("[pay_truth] mark_paychase_done skip: %s", e)
        return False


def mark_paychase_parked(hq_id: str) -> bool:
    """Park a synthetic pay-chase card out of the operator queue."""
    pid = _paychase_awaiting_id(hq_id)
    if not pid:
        return False
    try:
        _store.add_step_done(pid, _CHASE_PARK_STEP)
        return True
    except Exception as e:
        logger.debug("[pay_truth] mark_paychase_parked skip: %s", e)
        return False


def unpaid_chase_cards(limit: int = 50) -> list[dict[str, Any]]:
    """Hot-Queue-shaped cards for awaiting_payment prospects (owner chase)."""
    out: list[dict[str, Any]] = []
    try:
        for rec in _store.list_prospects(limit=500):
            if rec.get("status") != _store.STATUS_AWAITING_PAYMENT:
                continue
            steps = list(rec.get("steps_done") or [])
            if _CHASE_DONE_STEP in steps or _CHASE_PARK_STEP in steps:
                continue
            phone = str(rec.get("phone") or "")
            digits = "".join(c for c in phone if c.isdigit())
            wa = ""
            if len(digits) >= 10:
                from urllib.parse import quote

                msg = (
                    f"Namaste {rec.get('name') or ''}! Aapka LeadGen AI account ready hai — "
                    f"Billing se ₹1,999 UPI complete karein: https://leadsgenai.in/start"
                )
                wa = f"https://wa.me/91{digits[-10:]}?text={quote(msg.strip())}"
            out.append(
                {
                    "hq_id": f"paychase:{rec.get('id')}",
                    "channel": "payment_chase",
                    "intent": "interested",
                    "from": rec.get("email") or phone,
                    "phone": phone,
                    "business_name": rec.get("name") or "",
                    "text": f"awaiting_payment client_id={rec.get('converted_client_id') or '-'}",
                    "draft": (
                        "Payment pending — owner: password reset → Billing ₹1999 → reply PAID. "
                        "Do not mark-paid without ledger."
                    ),
                    "wa_link": wa,
                    "hq_source": "pay_truth",
                    "at": rec.get("updated_at") or rec.get("created_at") or "",
                    "prospect_id": rec.get("id"),
                    "converted_client_id": rec.get("converted_client_id"),
                }
            )
            if len(out) >= max(1, int(limit)):
                break
    except Exception as e:
        logger.debug("[pay_truth] chase cards skip: %s", e)
    return out


__all__ = [
    "has_payment_proof",
    "enrich_prospect",
    "reconcile_pay_truth",
    "unpaid_chase_cards",
    "mark_paychase_done",
    "mark_paychase_parked",
]
