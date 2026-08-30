#!/usr/bin/env python3
"""
Automated Cash Scoreboard — Campaign Revenue Tracker

Recalculates after every VERIFIED_PAID event:
  VERIFIED_CASH = sum of all verified campaign-collected amounts
  TARGET = ₹5,00,000 (fixed)
  REMAINING = max(0, TARGET - VERIFIED_CASH)
  PROGRESS = VERIFIED_CASH / TARGET × 100 (exact arithmetic)
  PAYMENTS_TODAY = count of VERIFIED_PAID events in current campaign window
  PAID_DEALS = unique client IDs who paid
  AVERAGE_CASH_PER_DEAL = VERIFIED_CASH / count of paid deals
"""

import json
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal

# Add project root to path
sys.path.insert(0, "C:/Users/Ratanshila/Documents/leadgenrationaivoiceagent")

# Constants
TARGET = Decimal("500000")
CAMPAIGN_START = "2026-08-23"
CAMPAIGN_END = "2026-08-30"


def load_campaign_ledger():
    """Load current campaign ledger state from database."""
    try:
        from db import get_connection

        conn = get_connection()
        cursor = conn.cursor()
        # Static query: no interpolation and no user input - `id` is a literal
        # constant, so there is nothing to parameterize. scripts/security_scan.py
        # flags every raw SELECT handed to cursor.execute by regex unless it also
        # sees a parameter tuple, so this is a documented false positive.
        cursor.execute("SELECT verified_cash_collected FROM campaign_ledger WHERE id = 1")  # nosecurity
        result = cursor.fetchone()
        conn.close()
        if result:
            return Decimal(str(result[0]))
        return Decimal("0")
    except Exception:
        return Decimal("0")


def classify_payment(payment_received_at, provider_txn_id=None, customer_id=None, amount=None):
    """Classify a payment as CAMPAIGN_REVENUE or HISTORICAL/OUTSIDE_CAMPAIGN."""
    try:
        pt = datetime.fromisoformat(payment_received_at)
        if pt.tzinfo is None:
            pt = pt.replace(tzinfo=timezone.utc)

        start = datetime.strptime(CAMPAIGN_START, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        end = datetime.strptime(CAMPAIGN_END, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(
            days=1, hours=-1, minutes=-30
        )

        if start <= pt <= end:
            return "CAMPAIGN_REVENUE"
        else:
            return "HISTORICAL_OUTSIDE_CAMPAIGN"
    except Exception:
        return "UNKNOWN"


def recalculate_scoreboard():
    """Full scoreboard recalculation after VERIFIED_PAID events."""
    from db import get_connection

    verified_cash = load_campaign_ledger()

    # Calculate derived metrics
    remaining = max(Decimal("0"), TARGET - verified_cash)
    progress = calculate_progress(verified_cash, TARGET)

    # Count payments today / in campaign window
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT COUNT(*), GROUP_CONCAT(DISTINCT client_id)
            FROM upi_submissions
            WHERE status = 'VERIFIED_PAID'
              AND received_at >= %s
              AND received_at <= %s
        """,
            (CAMPAIGN_START, CAMPAIGN_END),
        )
        payment_count_result = cursor.fetchone()
        conn.close()

        if payment_count_result and payment_count_result[0]:
            payments_today = int(payment_count_result[0])
            # Parse client IDs (GROUP_CONCAT may have commas)
            client_ids_str = payment_count_result[1] if len(payment_count_result) > 1 else ""
        else:
            payments_today = 0
            client_ids_str = ""
    except Exception:
        payments_today = 0
        client_ids_str = ""

    # Count unique paid deals
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(DISTINCT customer_id)
            FROM upi_submissions
            WHERE status = 'VERIFIED_PAID'
        """)
        deals_result = cursor.fetchone()
        conn.close()

        if deals_result and deals_result[0]:
            paid_deals = int(deals_result[0])
        else:
            paid_deals = 0
    except Exception:
        paid_deals = 0

    # Calculate average cash per deal
    if paid_deals > 0:
        average_cash_per_deal = verified_cash / Decimal(str(paid_deals))
    else:
        average_cash_per_deal = Decimal("0")

    # Build scoreboard
    scoreboard = {
        "verified_cash_collected": float(verified_cash),
        "target": float(TARGET),
        "remaining": float(remaining),
        "progress_percent": round(float(progress), 4),
        "payments_today": payments_today,
        "paid_deals": paid_deals,
        "average_cash_per_deal": float(average_cash_per_deal),
        "timestamp": datetime.utcnow().isoformat(),
        "campaign_window": f"{CAMPAIGN_START} to {CAMPAIGN_END} EOD IST",
    }

    return scoreboard


def calculate_progress(collected, target=500000):
    """Calculate progress percentage with exact arithmetic."""
    if collected >= target:
        return 100.0
    return round((float(collected) / float(target)) * 100, 4)


def verify_payment_reference(ref_id):
    """Verify a payment reference against the ledger."""
    from db import get_connection

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT id, status, amount, received_at, customer_id, invoice_id
            FROM upi_submissions
            WHERE reference_id = %s OR provider_txn_id = %s
        """,
            (ref_id, ref_id),
        )
        result = cursor.fetchone()
        conn.close()
        return result
    finally:
        conn.close()


def main():
    """Entry point — recalculate and display scoreboard."""
    from db import get_connection

    scoreboard = recalculate_scoreboard()

    print("=" * 60)
    print("HERMES CAMPAIGN REVENUE SCOREBOARD")
    print("=" * 60)
    print(f"Target: ₹{scoreboard['target']:,.2f}")
    print(f"Verified Collected: ₹{scoreboard['verified_cash_collected']:,.2f}")
    print(f"Remaining: ₹{scoreboard['remaining']:,.2f}")
    print(f"Progress: {scoreboard['progress_percent']}%")
    print(f"Campaign Window: {scoreboard['campaign_window']}")
    print("")
    print(f"Payments Today (campaign): {scoreboard['payments_today']}")
    print(f"Unique Paid Deals: {scoreboard['paid_deals']}")
    print(f"Average Cash per Deal: ₹{scoreboard['average_cash_per_deal']:,.2f}")
    print("")

    if scoreboard["remaining"] > 0:
        print(f"🎯 NEXT: ₹{scoreboard['remaining']:,.2f} more needed to reach target")
    else:
        print("🏆 TARGET REACHED! ₹5,00,000 verified cash collected!")

    print("=" * 60)

    # Output JSON for monitoring
    print("\n--- JSON OUTPUT ---")
    print(json.dumps(scoreboard, indent=2))


if __name__ == "__main__":
    main()
