"""Self-serve UPI payment submissions — kill manual WhatsApp-screenshot friction.

Customer pays via UPI, then submits "maine pay kiya" (ref + plan) from the site.
Record lands in a pending queue (``data/upi_payments.json``). Admin approves/rejects,
OR — when ``UPI_AUTO_ACTIVATE=1`` — the plan auto-activates instantly on submit.

Patterned on ``app.platform.upi_config`` (json data-file store, never raises).
ADDITIVE + defensive: every function wraps work in try/except and returns a safe
default; nothing here ever lets an exception escape into a request path.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_STORE = os.path.join("data", "upi_payments.json")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_store() -> list[dict]:
    """Read the payment records list. Never raises — bad/missing file → []."""
    try:
        if os.path.isfile(_STORE):
            with open(_STORE, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception as e:
        logger.debug("upi_payments read failed: %s", e)
    return []


def _write_store(rows: list[dict]) -> bool:
    """Persist the records list. Never raises — returns False on failure."""
    try:
        os.makedirs(os.path.dirname(_STORE) or ".", exist_ok=True)
        with open(_STORE, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.warning("upi_payments write failed: %s", e)
        return False


def _make_id(existing: list[dict], upi_ref: str) -> str:
    """Deterministic-ish id: counter + short hash of upi_ref (no uuid/random)."""
    try:
        h = hashlib.sha1((upi_ref or "").encode("utf-8")).hexdigest()[:8]
    except Exception:
        h = "00000000"
    return f"upi_{len(existing) + 1}_{h}"


def _notify_admin(record: dict) -> None:
    """Best-effort ntfy push to admin. Never blocks / never raises."""
    try:
        from app.platform import ops_alerts

        msg = (
            f"Plan: {record.get('plan')} · Ref: {record.get('upi_ref')} · "
            f"Client: {record.get('client_id') or '-'} · "
            f"Naam: {record.get('payer_name') or '-'} · Amt: {record.get('amount')}"
        )
        ops_alerts._ntfy("New UPI payment", msg)
    except Exception as e:
        logger.debug("upi_payments admin notify skipped: %s", e)


def _try_activate(client_id: str, plan: str) -> bool:
    """Best-effort plan activation. Never raises — returns activation success bool."""
    cid = (client_id or "").strip()
    if not cid:
        return False
    try:
        from app.billing import usage

        return bool(usage.activate_plan(cid, plan))
    except Exception as e:
        logger.debug("upi_payments activate skipped: %s", e)
        return False


def submit_payment(
    client_id: str,
    plan: str,
    upi_ref: str,
    amount: float = 0,
    payer_name: str = "",
    payer_contact: str = "",
) -> dict:
    """Customer self-serve "maine pay kiya" submission.

    Validates plan + upi_ref non-empty, appends a pending record, notifies admin,
    and (when ``UPI_AUTO_ACTIVATE=1`` + client_id) tries instant activation.
    Never raises — returns ``{"ok": False, "error": ...}`` on validation failure.
    """
    try:
        plan_s = (plan or "").strip()
        ref_s = (upi_ref or "").strip()
        if not plan_s:
            return {"ok": False, "error": "Plan zaroori hai"}
        if not ref_s:
            return {"ok": False, "error": "UPI reference / transaction id zaroori hai"}

        cid = (client_id or "").strip()
        rows = _read_store()
        record = {
            "id": _make_id(rows, ref_s),
            "client_id": cid,
            "plan": plan_s,
            "upi_ref": ref_s,
            "amount": amount,
            "payer_name": (payer_name or "").strip(),
            "payer_contact": (payer_contact or "").strip(),
            "status": "pending",
            "auto_activated": False,
            "created_at": _now_iso(),
            "decided_at": None,
            "decided_by": None,
        }
        rows.append(record)
        _write_store(rows)

        # Best-effort admin notify (after persist so the record is durable first).
        _notify_admin(record)

        # Optional instant activation (flag-gated, default OFF).
        if os.environ.get("UPI_AUTO_ACTIVATE") == "1" and cid:
            if _try_activate(cid, plan_s):
                record["status"] = "auto_activated"
                record["auto_activated"] = True
                record["decided_at"] = _now_iso()
                record["decided_by"] = "auto"
                # Persist the updated status (record is the same object in rows).
                _write_store(rows)

        return {"ok": True, **record}
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("submit_payment failed: %s", e)
        return {"ok": False, "error": "Submit fail — thodi der baad try karo"}


def list_payments(status: str | None = None) -> list[dict]:
    """All payment records, optionally filtered by status. Never raises."""
    try:
        rows = _read_store()
        if status:
            return [r for r in rows if r.get("status") == status]
        return rows
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("list_payments failed: %s", e)
        return []


def decide(payment_id: str, approve: bool, decided_by: str = "admin") -> dict:
    """Admin approve/reject a pending submission.

    On approve (and not already auto-activated) + client_id → activate the plan.
    Returns the updated record, or ``{"ok": False, "error": "not_found"}``.
    Never raises.
    """
    try:
        pid = (payment_id or "").strip()
        rows = _read_store()
        record = None
        for r in rows:
            if r.get("id") == pid:
                record = r
                break
        if record is None:
            return {"ok": False, "error": "not_found"}

        record["status"] = "approved" if approve else "rejected"
        record["decided_at"] = _now_iso()
        record["decided_by"] = (decided_by or "admin")[:80]

        if approve and not record.get("auto_activated") and record.get("client_id"):
            _try_activate(record.get("client_id", ""), record.get("plan", ""))

        _write_store(rows)
        return record
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("decide failed: %s", e)
        return {"ok": False, "error": "decide_failed"}
