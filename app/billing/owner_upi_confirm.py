"""Owner UPI Confirm — manual UPI → owner confirm → invoice flow (M3, P2).

WHY THIS EXISTS
---------------
ARCH §M3: Payment rail = MANUAL UPI ONLY. Stripe/Razorpay REMOVED (issue #243).
Owner is sole confirmer. This module implements the owner-confirmation flow:
1. Customer pays via UPI → pending payment recorded
2. Owner checks bank → confirms credit
3. Invoice auto-generated
4. Subscription activated

Design:
* Pending payments table (in-memory + JSONL for durability)
* Owner confirm → invoice generation → subscription activation
* Never raises — fails gracefully
* Evidence: bank screenshot URL / transaction ID

Evidence label: CODE-PRESENT (stub, needs wiring to billing/gst_invoice.py)
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Pending payments ledger
LEDGER_PATH = "data/pending_upi_payments.jsonl"
INVOICES_PATH = "data/invoices.jsonl"


class PendingPayment:
    """UPI payment pending owner confirmation."""

    def __init__(
        self,
        payment_id: str,
        client_id: str,
        amount_inr: float,
        upi_trx_id: str,
        payer_vpa: str,
        timestamp: str,
        status: str = "pending",  # pending | confirmed | rejected | expired
        evidence: str = "",
    ):
        self.payment_id = payment_id
        self.client_id = client_id
        self.amount_inr = amount_inr
        self.upi_trx_id = upi_trx_id
        self.payer_vpa = payer_vpa
        self.timestamp = timestamp
        self.status = status
        self.evidence = evidence
        self.confirmed_at: str | None = None
        self.invoice_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "payment_id": self.payment_id,
            "client_id": self.client_id,
            "amount_inr": self.amount_inr,
            "upi_trx_id": self.upi_trx_id,
            "payer_vpa": self.payer_vpa,
            "timestamp": self.timestamp,
            "status": self.status,
            "evidence": self.evidence,
            "confirmed_at": self.confirmed_at,
            "invoice_id": self.invoice_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PendingPayment:
        payment = cls(
            payment_id=data["payment_id"],
            client_id=data["client_id"],
            amount_inr=data["amount_inr"],
            upi_trx_id=data["upi_trx_id"],
            payer_vpa=data["payer_vpa"],
            timestamp=data["timestamp"],
            status=data.get("status", "pending"),
            evidence=data.get("evidence", ""),
        )
        payment.confirmed_at = data.get("confirmed_at")
        payment.invoice_id = data.get("invoice_id")
        return payment

    def confirm(self, evidence: str = ""):
        """Owner confirms payment — updates status + timestamp."""
        self.status = "confirmed"
        self.evidence = evidence
        self.confirmed_at = datetime.now(timezone.utc).isoformat()

    def reject(self, reason: str = ""):
        """Owner rejects payment."""
        self.status = "rejected"
        self.evidence = f"REJECTED: {reason}"
        self.confirmed_at = datetime.now(timezone.utc).isoformat()


class OwnerUpiConfirm:
    """Manages pending UPI payments + owner confirmation flow."""

    def __init__(self, ledger_path: str = LEDGER_PATH):
        self.ledger_path = ledger_path
        self.payments: dict[str, PendingPayment] = {}
        self._load()

    def _load(self):
        """Load existing pending payments."""
        if not os.path.exists(self.ledger_path):
            return
        try:
            with open(self.ledger_path) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            data = json.loads(line)
                            payment = PendingPayment.from_dict(data)
                            self.payments[payment.payment_id] = payment
                        except json.JSONDecodeError:
                            logger.warning(f"[owner_upi] Skipped malformed line: {line[:80]}")
        except Exception as e:
            logger.warning(f"[owner_upi] Failed to load ledger: {e}")

    def _save(self):
        """Persist all payments to ledger."""
        try:
            os.makedirs(os.path.dirname(self.ledger_path), exist_ok=True)
            with open(self.ledger_path, "w") as f:
                for payment in self.payments.values():
                    f.write(json.dumps(payment.to_dict()) + "\n")
        except Exception as e:
            logger.warning(f"[owner_upi] Failed to save ledger: {e}")

    def record_payment(
        self,
        client_id: str,
        amount_inr: float,
        upi_trx_id: str,
        payer_vpa: str,
    ) -> str:
        """Record a new pending UPI payment.

        Returns payment_id.
        """
        payment_id = f"pay_{uuid.uuid4().hex[:12]}"
        payment = PendingPayment(
            payment_id=payment_id,
            client_id=client_id,
            amount_inr=amount_inr,
            upi_trx_id=upi_trx_id,
            payer_vpa=payer_vpa,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        self.payments[payment_id] = payment
        self._save()
        logger.info(f"[owner_upi] Recorded: {payment_id} — ₹{amount_inr} from {payer_vpa}")
        return payment_id

    def confirm_payment(self, payment_id: str, evidence: str = "") -> bool:
        """Owner confirms payment → updates status + generates invoice.

        Returns True if successful, False if payment not found.
        """
        if payment_id not in self.payments:
            logger.warning(f"[owner_upi] Payment not found: {payment_id}")
            return False

        payment = self.payments[payment_id]
        if payment.status != "pending":
            logger.warning(f"[owner_upi] Payment not pending: {payment_id} (status={payment.status})")
            return False

        # Confirm
        payment.confirm(evidence)

        # Generate invoice (stub — wire to gst_invoice.py later)
        invoice_id = self._generate_invoice(payment)
        payment.invoice_id = invoice_id

        self._save()
        logger.info(f"[owner_upi] Confirmed: {payment_id} → invoice {invoice_id}")
        return True

    def reject_payment(self, payment_id: str, reason: str = "") -> bool:
        """Owner rejects payment.

        Returns True if successful, False if payment not found.
        """
        if payment_id not in self.payments:
            return False

        payment = self.payments[payment_id]
        payment.reject(reason)
        self._save()
        logger.info(f"[owner_upi] Rejected: {payment_id} — {reason}")
        return True

    def _generate_invoice(self, payment: PendingPayment) -> str:
        """Stub: generate invoice ID (wire to gst_invoice.py later).

        In production, this calls `app.billing.gst_invoice.create_invoice()`.
        """
        # For now, just return a stub invoice ID
        invoice_id = f"INV/{datetime.now().strftime('%Y-%Y')}/{uuid.uuid4().hex[:6].upper()}"
        logger.info(f"[owner_upi] Generated stub invoice: {invoice_id}")
        return invoice_id

    def get_pending(self, client_id: str | None = None) -> list[PendingPayment]:
        """Get pending payments (optionally filtered by client)."""
        payments = [p for p in self.payments.values() if p.status == "pending"]
        if client_id:
            payments = [p for p in payments if p.client_id == client_id]
        return payments

    def get_summary(self) -> dict[str, Any]:
        """Get summary counts."""
        pending = sum(1 for p in self.payments.values() if p.status == "pending")
        confirmed = sum(1 for p in self.payments.values() if p.status == "confirmed")
        rejected = sum(1 for p in self.payments.values() if p.status == "rejected")
        total_amount_pending = sum(p.amount_inr for p in self.payments.values() if p.status == "pending")
        return {
            "pending_count": pending,
            "confirmed_count": confirmed,
            "rejected_count": rejected,
            "total_amount_pending_inr": total_amount_pending,
        }

    def print_status(self):
        """Print human-readable status."""
        summary = self.get_summary()
        print(f"\n{'='*60}")
        print("  OWNER UPI CONFIRM STATUS")
        print(f"{'='*60}")
        print(f"  Pending:    {summary['pending_count']:3d} payments (₹{summary['total_amount_pending_inr']:,.0f})")
        print(f"  Confirmed:  {summary['confirmed_count']:3d} payments")
        print(f"  Rejected:   {summary['rejected_count']:3d} payments")
        print(f"{'='*60}\n")

        # Show pending details
        pending = self.get_pending()
        if pending:
            print("  PENDING PAYMENTS:")
            for p in pending[:10]:  # show first 10
                print(f"    {p.payment_id} — ₹{p.amount_inr:,.0f} from {p.payer_vpa} ({p.upi_trx_id})")
            if len(pending) > 10:
                print(f"    ... and {len(pending) - 10} more")
        print()


# Module-level singleton
_confirm: OwnerUpiConfirm | None = None


def get_confirm() -> OwnerUpiConfirm:
    """Get or create singleton OwnerUpiConfirm."""
    global _confirm
    if _confirm is None:
        _confirm = OwnerUpiConfirm()
    return _confirm


def record_payment(client_id: str, amount_inr: float, upi_trx_id: str, payer_vpa: str) -> str:
    """Convenience function to record a payment."""
    confirm = get_confirm()
    return confirm.record_payment(client_id, amount_inr, upi_trx_id, payer_vpa)


def confirm_payment(payment_id: str, evidence: str = "") -> bool:
    """Convenience function to confirm a payment."""
    confirm = get_confirm()
    return confirm.confirm_payment(payment_id, evidence)


def compute_and_print():
    """Convenience: print status."""
    confirm = get_confirm()
    confirm.print_status()
    return confirm.get_summary()


__all__ = [
    "PendingPayment",
    "OwnerUpiConfirm",
    "get_confirm",
    "record_payment",
    "confirm_payment",
    "compute_and_print",
]
