"""Tests for owner_upi_confirm.py â€” manual UPI confirmation flow (M3, P2).

Run: pytest tests/test_owner_upi_confirm.py -v
"""

import json
import os
import tempfile
from pathlib import Path

import pytest

from app.billing.owner_upi_confirm import OwnerUpiConfirm, PendingPayment, get_confirm, record_payment, confirm_payment


class TestPendingPayment:
    """Test PendingPayment dataclass."""

    def test_creation(self):
        """Test basic payment creation."""
        payment = PendingPayment(
            payment_id="pay_test123",
            client_id="client_456",
            amount_inr=1999.0,
            upi_trx_id="T123456789",
            payer_vpa="user@upi",
            timestamp="2026-09-17T00:00:00Z"
        )
        assert payment.payment_id == "pay_test123"
        assert payment.amount_inr == 1999.0
        assert payment.status == "pending"

    def test_confirm(self):
        """Test confirming a payment."""
        payment = PendingPayment(
            payment_id="pay_confirm",
            client_id="client_1",
            amount_inr=5999.0,
            upi_trx_id="T987654321",
            payer_vpa="user2@upi",
            timestamp="2026-09-17T00:00:00Z"
        )
        payment.confirm(evidence="bank_screenshot.jpg")

        assert payment.status == "confirmed"
        assert payment.evidence == "bank_screenshot.jpg"
        assert payment.confirmed_at is not None

    def test_reject(self):
        """Test rejecting a payment."""
        payment = PendingPayment(
            payment_id="pay_reject",
            client_id="client_2",
            amount_inr=1999.0,
            upi_trx_id="T111222333",
            payer_vpa="user3@upi",
            timestamp="2026-09-17T00:00:00Z"
        )
        payment.reject(reason="insufficient funds")

        assert payment.status == "rejected"
        assert "REJECTED" in payment.evidence
        assert payment.confirmed_at is not None

    def test_to_dict_from_dict(self):
        """Test serialization/deserialization."""
        payment = PendingPayment(
            payment_id="pay_serial",
            client_id="client_3",
            amount_inr=2999.0,
            upi_trx_id="T444555666",
            payer_vpa="user4@upi",
            timestamp="2026-09-17T00:00:00Z"
        )
        payment.confirm("evidence.txt")

        data = payment.to_dict()
        restored = PendingPayment.from_dict(data)

        assert restored.payment_id == payment.payment_id
        assert restored.status == "confirmed"
        assert restored.evidence == "evidence.txt"


class TestOwnerUpiConfirm:
    """Test OwnerUpiConfirm class."""

    @pytest.fixture
    def tmp_path(self, tmp_path):
        """Create temp ledger file."""
        ledger_file = tmp_path / "pending_upi_payments.jsonl"
        return str(ledger_file)

    def test_record_payment(self, tmp_path):
        """Test recording a new payment."""
        confirm = OwnerUpiConfirm(ledger_path=tmp_path)
        payment_id = confirm.record_payment(
            client_id="client_jiya",
            amount_inr=1999.0,
            upi_trx_id="T789012345",
            payer_vpa="jiya@ybl"
        )

        assert payment_id.startswith("pay_")
        assert payment_id in confirm.payments
        assert confirm.payments[payment_id].status == "pending"

    def test_confirm_payment(self, tmp_path):
        """Test confirming a payment generates invoice."""
        confirm = OwnerUpiConfirm(ledger_path=tmp_path)
        payment_id = confirm.record_payment(
            client_id="client_test",
            amount_inr=5999.0,
            upi_trx_id="T111000222",
            payer_vpa="test@upi"
        )

        # Confirm
        success = confirm.confirm_payment(payment_id, "bank_credit_seen")
        assert success is True

        # Verify
        payment = confirm.payments[payment_id]
        assert payment.status == "confirmed"
        assert payment.invoice_id is not None
        assert "INV" in payment.invoice_id

    def test_reject_payment(self, tmp_path):
        """Test rejecting a payment."""
        confirm = OwnerUpiConfirm(ledger_path=tmp_path)
        payment_id = confirm.record_payment(
            client_id="client_reject",
            amount_inr=1999.0,
            upi_trx_id="T333444555",
            payer_vpa="reject@upi"
        )

        success = confirm.reject_payment(payment_id, "wrong amount")
        assert success is True

        payment = confirm.payments[payment_id]
        assert payment.status == "rejected"

    def test_confirm_nonexistent(self, tmp_path):
        """Test confirming non-existent payment fails gracefully."""
        confirm = OwnerUpiConfirm(ledger_path=tmp_path)
        success = confirm.confirm_payment("pay_doesnotexist")
        assert success is False

    def test_get_pending(self, tmp_path):
        """Test querying pending payments."""
        confirm = OwnerUpiConfirm(ledger_path=tmp_path)

        # Record multiple payments
        id1 = confirm.record_payment("client1", 1999.0, "T1", "vpa1")
        id2 = confirm.record_payment("client2", 5999.0, "T2", "vpa2")
        confirm.confirm_payment(id1)

        # Query pending
        pending = confirm.get_pending()
        assert len(pending) == 1
        assert pending[0].payment_id == id2

        # Query by client
        pending_client = confirm.get_pending(client_id="client2")
        assert len(pending_client) == 1
        assert pending_client[0].payment_id == id2

    def test_get_summary(self, tmp_path):
        """Test summary computation."""
        confirm = OwnerUpiConfirm(ledger_path=tmp_path)

        id1 = confirm.record_payment("c1", 1999.0, "T1", "v1")
        id2 = confirm.record_payment("c2", 5999.0, "T2", "v2")
        id3 = confirm.record_payment("c3", 1999.0, "T3", "v3")
        confirm.confirm_payment(id1)
        confirm.reject_payment(id2, "wrong amount")

        summary = confirm.get_summary()
        assert summary["pending_count"] == 1
        assert summary["confirmed_count"] == 1
        assert summary["rejected_count"] == 1
        assert summary["total_amount_pending_inr"] == 1999.0

    def test_persistence(self, tmp_path):
        """Test persistence across instances."""
        # Create and save
        confirm1 = OwnerUpiConfirm(ledger_path=tmp_path)
        id1 = confirm1.record_payment("c1", 1999.0, "T1", "v1")
        confirm1.confirm_payment(id1)

        # Load in new instance
        confirm2 = OwnerUpiConfirm(ledger_path=tmp_path)
        assert id1 in confirm2.payments
        assert confirm2.payments[id1].status == "confirmed"

    def test_print_status(self, tmp_path, capsys):
        """Test status printing."""
        confirm = OwnerUpiConfirm(ledger_path=tmp_path)
        confirm.record_payment("c1", 1999.0, "T1", "v1")
        confirm.print_status()

        captured = capsys.readouterr()
        assert "OWNER UPI CONFIRM" in captured.out
        assert "Pending:" in captured.out


class TestOwnerFlow:
    """Test the owner confirmation flow (business logic)."""

    def test_full_flow_record_confirm_invoice(self, tmp_path):
        """Test complete flow: record â†’ confirm â†’ invoice generated."""
        confirm = OwnerUpiConfirm(ledger_path=tmp_path)

        # Step 1: Customer pays via UPI
        payment_id = confirm.record_payment(
            client_id="client_jiya",
            amount_inr=1999.0,
            upi_trx_id="T_JIYA_001",
            payer_vpa="jiya@ybl"
        )

        # Step 2: Owner checks bank and confirms
        success = confirm.confirm_payment(
            payment_id,
            evidence="bank_statement_sept17.jpg"
        )
        assert success is True

        # Step 3: Verify invoice generated
        payment = confirm.payments[payment_id]
        assert payment.status == "confirmed"
        assert payment.invoice_id.startswith("INV/")
        assert payment.confirmed_at is not None

    def test_full_flow_record_reject(self, tmp_path):
        """Test complete flow: record â†’ reject."""
        confirm = OwnerUpiConfirm(ledger_path=tmp_path)

        # Step 1: Customer pays
        payment_id = confirm.record_payment(
            client_id="client_bad",
            amount_inr=1999.0,
            upi_trx_id="T_BAD_001",
            payer_vpa="bad@upi"
        )

        # Step 2: Owner rejects (wrong amount)
        success = confirm.reject_payment(payment_id, "amount mismatch")
        assert success is True

        # Step 3: Verify rejection
        payment = confirm.payments[payment_id]
        assert payment.status == "rejected"
        assert "REJECTED" in payment.evidence

    def test_double_confirm_prevented(self, tmp_path):
        """Test that double confirmation is prevented."""
        confirm = OwnerUpiConfirm(ledger_path=tmp_path)
        payment_id = confirm.record_payment("c1", 1999.0, "T1", "v1")

        # First confirm
        success1 = confirm.confirm_payment(payment_id)
        assert success1 is True

        # Second confirm should fail
        success2 = confirm.confirm_payment(payment_id)
        assert success2 is False

    def test_only_owner_can_confirm(self, tmp_path):
        """Test that only owner can confirm (stub â€” actual auth is separate)."""
        confirm = OwnerUpiConfirm(ledger_path=tmp_path)
        payment_id = confirm.record_payment("c1", 1999.0, "T1", "v1")

        # In production, this would check owner permissions
        # For now, just verify the flow works
        success = confirm.confirm_payment(payment_id, evidence="owner_check")
        assert success is True


class TestIntegration:
    """Integration tests."""

    def test_module_level_functions(self, tmp_path, monkeypatch):
        """Test module-level convenience functions."""
        monkeypatch.setattr("app.billing.owner_upi_confirm.get_confirm", lambda: OwnerUpiConfirm(tmp_path))

        # Record
        payment_id = record_payment("c1", 1999.0, "T1", "v1")
        assert payment_id.startswith("pay_")

        # Confirm
        success = confirm_payment(payment_id, "evidence")
        assert success is True

    def test_end_to_end_with_summary(self, tmp_path):
        """Test full workflow with summary tracking."""
        confirm = OwnerUpiConfirm(ledger_path=tmp_path)

        # Record 3 payments
        id1 = confirm.record_payment("c1", 1999.0, "T1", "v1")
        id2 = confirm.record_payment("c2", 5999.0, "T2", "v2")
        id3 = confirm.record_payment("c3", 1999.0, "T3", "v3")

        # Confirm 2, reject 1
        confirm.confirm_payment(id1, "bank_ok")
        confirm.confirm_payment(id2, "bank_ok")
        confirm.reject_payment(id3, "wrong_amount")

        # Get summary
        summary = confirm.get_summary()
        assert summary["pending_count"] == 0
        assert summary["confirmed_count"] == 2
        assert summary["rejected_count"] == 1
        assert summary["total_amount_pending_inr"] == 0

        # Verify total revenue
        total_confirmed = sum(
            p.amount_inr for p in confirm.payments.values()
            if p.status == "confirmed"
        )
        assert total_confirmed == 7998.0  # 1999 + 5999

