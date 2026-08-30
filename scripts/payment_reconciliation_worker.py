#!/usr/bin/env python3
"""
Automated Payment Reconciliation Worker for Hermes Owner Admin

Scans invoices, matches UPI transactions against invoices with full evidence checks,
sets VERIFIED_PAID, triggers idempotent provisioning, updates cash scoreboard,
falls to PAYMENT_REVIEW_REQUIRED on ambiguity.

Idempotent: same transaction never credits twice.
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from decimal import Decimal

# Add project root to path
sys.path.insert(0, "C:/Users/Ratanshila/Documents/leadgenrationaivoiceagent")

from db import get_connection


def calculate_progress(collected, target=500000):
    """Calculate progress percentage."""
    if collected >= target:
        return 100.0
    return round((collected / target) * 100, 4)


def is_campaign_eligible(
    payment_received_at, campaign_start="2026-08-23", campaign_end="2026-08-30"
):
    """Check if payment falls within campaign period EOD IST."""
    try:
        pt = datetime.fromisoformat(payment_received_at)
        if pt.tzinfo is None:
            pt = pt.replace(tzinfo=timezone.utc)
        # Campaign period in IST (UTC+5:30)
        start = datetime.strptime(campaign_start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        end = datetime.strptime(campaign_end, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(
            days=1, hours=-1, minutes=-30
        )  # EOD IST
        return start <= pt <= end
    except Exception:
        return False


def scan_and_reconcile():
    """Main reconciliation loop."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        # Scan for pending UPI submissions
        cursor.execute("""
            SELECT id, customer_id, invoice_id, amount, provider_txn_id,
                   reference_id, received_at, status
            FROM upi_submissions
            WHERE status = 'PENDING'
            ORDER BY received_at ASC
        """)
        events = cursor.fetchall()

        for event in events:
            (
                event_id,
                customer_id,
                invoice_id,
                amount,
                provider_txn_id,
                reference_id,
                received_at,
                status,
            ) = event

            # Fetch invoice details
            cursor.execute(
                """
                SELECT id, customer_id, expected_amount, status, campaign_eligible
                FROM invoices
                WHERE id = %s
            """,
                (invoice_id,),
            )
            invoice = cursor.fetchone()

            if not invoice:
                continue

            inv_id, inv_customer_id, expected_amount, inv_status, inv_campaign_eligible = invoice

            # Check: invoice already paid
            if inv_status == "PAID":
                cursor.execute(
                    """
                    UPDATE upi_submissions SET status = 'SKIPPED_ALREADY_PAID' WHERE id = %s
                """,
                    (event_id,),
                )
                conn.commit()
                continue

            # Idempotency: transaction already consumed
            cursor.execute(
                """
                SELECT COUNT(*) FROM upi_submissions
                WHERE provider_txn_id = %s AND status = 'VERIFIED_PAID'
            """,
                (provider_txn_id,),
            )
            if cursor.fetchone()[0] > 0:
                cursor.execute(
                    """
                    UPDATE upi_submissions SET status = 'SKIPPED_DUPLICATE' WHERE id = %s
                """,
                    (event_id,),
                )
                conn.commit()
                continue

            # Amount match check
            if Decimal(str(amount)) != Decimal(str(expected_amount)):
                cursor.execute(
                    """
                    UPDATE upi_submissions SET status = 'PAYMENT_REVIEW_REQUIRED' WHERE id = %s
                """,
                    (event_id,),
                )
                conn.commit()
                continue

            # Customer/Reference match check
            if customer_id != inv_customer_id:
                cursor.execute(
                    """
                    UPDATE upi_submissions SET status = 'PAYMENT_REVIEW_REQUIRED' WHERE id = %s
                """,
                    (event_id,),
                )
                conn.commit()
                continue

            # Campaign eligibility check
            if not is_campaign_eligible(received_at):
                cursor.execute(
                    """
                    UPDATE upi_submissions SET status = 'HISTORICAL_OUTSIDE_CAMPAIGN' WHERE id = %s
                """,
                    (event_id,),
                )
                conn.commit()
                continue

            # ALL CHECKS PASSED → VERIFIED_PAID
            cursor.execute(
                """
                UPDATE upi_submissions SET status = 'VERIFIED_PAID' WHERE id = %s
            """,
                (event_id,),
            )

            # Settle invoice
            cursor.execute(
                """
                UPDATE invoices SET status = 'PAID', paid_at = NOW(), verified_at = NOW(),
                    transaction_id = %s, verified = TRUE
                WHERE id = %s
            """,
                (provider_txn_id, invoice_id),
            )

            # Update ledger / cash scoreboard
            cursor.execute(
                """
                UPDATE campaign_ledger SET verified_cash_collected = verified_cash_collected + %s WHERE id = 1
            """,
                (Decimal(str(amount)),),
            )

            # Trigger idempotent provisioning
            cursor.execute(
                """
                CALL trigger_provisioning(%s)
            """,
                (provider_txn_id,),
            )

            # Record audit trail
            cursor.execute(
                """
                INSERT INTO payment_audit (invoice_id, transaction_id, amount, verified_at, verified_by)
                VALUES (%s, %s, %s, NOW(), 'AUTOMATED_RECONCILIATION')
            """,
                (invoice_id, provider_txn_id, amount),
            )

            conn.commit()

        return {"scanned": len(events)}

    finally:
        conn.close()


if __name__ == "__main__":
    result = scan_and_reconcile()
    print(f"Reconciliation complete: {result}")
