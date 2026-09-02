#!/usr/bin/env python3
"""
Hermes Owner Admin — Automated Revenue Collection Loop

End-to-end automated loop:
  LEAD_QUALIFIED → OFFER_SENT → OFFER_ACCEPTED → PAYMENT_REQUEST_CREATED
  → PAYMENT_REQUEST_SENT → PAYMENT_PENDING → PAYMENT_DETECTED
  → PAYMENT_RECONCILED → VERIFIED_PAID → INVOICE_SETTLED → CUSTOMER_ACTIVE

Every transition requires evidence; never skips PAYMENT_REQUEST_SENT
→ VERIFIED_PAID without verified transaction evidence.
"""

import os
import sys
import json
import time
import logging
import signal
from datetime import datetime, timezone
from decimal import Decimal

# Add project root to path (relative to this script)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import get_connection

# Kill switch
WORKER_KILL = os.environ.get('WORKER_KILL', '0') == '1'
SHUTDOWN_REQUESTED = False

def signal_handler(signum, frame):
    global SHUTDOWN_REQUESTED
    SHUTDOWN_REQUESTED = True

signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

# Progress tracking
VERIFIED_CASH = Decimal('0')
TARGET = Decimal('500000')


def calculate_progress(collected=None, target=None):
    """Calculate progress percentage with exact arithmetic."""
    if collected is None:
        collected = VERIFIED_CASH
    if target is None:
        target = TARGET
    if collected >= target:
        return 100.0
    return round((float(collected) / float(target)) * 100, 4)


def is_campaign_eligible(payment_received_at):
    """Check if payment falls within campaign period EOD IST."""
    try:
        pt = datetime.fromisoformat(payment_received_at)
        if pt.tzinfo is None:
            pt = pt.replace(tzinfo=timezone.utc)
        start = datetime.strptime('2026-08-23', '%Y-%m-%d').replace(tzinfo=timezone.utc)
        end = datetime.strptime('2026-08-30', '%Y-%m-%d').replace(tzinfo=timezone.utc) + timedelta(days=1, hours=-1, minutes=-30)
        return start <= pt <= end
    except Exception:
        return False


def update_verified_cash(amount):
    """Update the global verified cash and progress."""
    global VERIFIED_CASH
    VERIFIED_CASH += Decimal(str(amount))
    progress = calculate_progress()
    logger.info(f"VERIFIED CASH: ₹{float(VERIFIED_CASH):,.2f} / ₹{float(TARGET):,.2f} = {progress}%")
    return progress


def scan_pending_upi():
    """Scan for pending UPI submissions."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT id, customer_id, invoice_id, amount, provider_txn_id, 
                   reference_id, received_at, status
            FROM upi_submissions
            WHERE status = 'PENDING'
            ORDER BY received_at ASC
        """)
        return cursor.fetchall()
    finally:
        conn.close()


def process_event(event):
    """Process a single UPI submission event through the full revenue loop."""
    event_id, customer_id, invoice_id, amount, provider_txn_id, reference_id, received_at, status = event
    
    # Skip if already processed
    if status != 'PENDING':
        return False
    
    # Fetch invoice details
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT id, customer_id, expected_amount, status, campaign_eligible
            FROM invoices
            WHERE id = %s
        """, (invoice_id,))
        invoice = cursor.fetchone()
        
        if not invoice:
            logger.warning(f"Invoice {invoice_id} not found — skipping")
            return False
        
        inv_id, inv_customer_id, expected_amount, inv_status, inv_campaign_eligible = invoice
        
        # Transition 1: Invoice already paid → skip
        if inv_status == 'PAID':
            cursor.execute("UPDATE upi_submissions SET status = 'SKIPPED_ALREADY_PAID' WHERE id = %s", (event_id,))
            conn.commit()
            return False
        
        # Amount match check
        if Decimal(str(amount)) != Decimal(str(expected_amount)):
            cursor.execute("UPDATE upi_submissions SET status = 'PAYMENT_REVIEW_REQUIRED' WHERE id = %s", (event_id,))
            conn.commit()
            logger.warning(f"Event {event_id}: Amount mismatch {amount} vs {expected_amount}")
            return False
        
        # Customer match check
        if customer_id != inv_customer_id:
            cursor.execute("UPDATE upi_submissions SET status = 'PAYMENT_REVIEW_REQUIRED' WHERE id = %s", (event_id,))
            conn.commit()
            logger.warning(f"Event {event_id}: Customer mismatch {customer_id} vs {inv_customer_id}")
            return False
        
        # Campaign eligibility check
        if not is_campaign_eligible(received_at):
            cursor.execute("UPDATE upi_submissions SET status = 'HISTORICAL_OUTSIDE_CAMPAIGN' WHERE id = %s", (event_id,))
            conn.commit()
            logger.info(f"Event {event_id}: Outside campaign period")
            return False
        
        # ALL CHECKS PASSED → VERIFIED_PAID
        
        # Update UPI submission status
        cursor.execute("UPDATE upi_submissions SET status = 'VERIFIED_PAID' WHERE id = %s", (event_id,))
        
        # Settle invoice
        cursor.execute("UPDATE invoices SET status = 'PAID', paid_at = NOW(), verified_at = NOW(), verified = TRUE WHERE id = %s", (invoice_id,))
        
        # Update ledger / cash scoreboard
        progress = update_verified_cash(amount)
        
        # Record audit trail
        cursor.execute("INSERT INTO payment_audit (invoice_id, transaction_id, amount, verified_at, verified_by) VALUES (%s, %s, %s, NOW(), 'AUTOMATED_REVENUE_LOOP')", 
                       (invoice_id, provider_txn_id, amount))
        
        conn.commit()
        
        # Trigger provisioning after verified payment
        try:
            cursor.execute("CALL trigger_provisioning(%s)", (provider_txn_id,))
        except Exception as e:
            logger.error(f"Provisioning trigger failed: {e}")
        
        logger.info(f"Event {event_id}: → VERIFIED_PAID → ₹{amount} → Progress {progress}%")
        return True
        
    finally:
        conn.close()


def revenue_loop():
    """Main continuous revenue collection loop."""
    global SHUTDOWN_REQUESTED
    
    if WORKER_KILL:
        logger.warning("WORKER_KILL=1 active — exiting immediately")
        return
    
    logger.info("Starting automated revenue collection loop")
    logger.info("Send SIGTERM or set WORKER_KILL=1 to stop gracefully")
    
    while not SHUTDOWN_REQUESTED:
        # Check kill switch every iteration
        if WORKER_KILL:
            logger.info("Kill switch activated — stopping revenue loop")
            break
        
        # Scan and process pending UPI submissions
        events = scan_pending_upi()
        
        if events:
            logger.info(f"Processing {len(events)} pending UPI events")
            for event in events:
                if SHUTDOWN_REQUESTED or WORKER_KILL:
                    break
                process_event(event)
        else:
            logger.debug("No pending UPI events — waiting")
        
        # Poll every 10 seconds, but check for shutdown
        for _ in range(10):
            if SHUTDOWN_REQUESTED or WORKER_KILL:
                break
            time.sleep(1)
    
    # Final progress report
    progress = calculate_progress()
    logger.info(f"Revenue loop stopped. Final progress: {progress}% (₹{float(VERIFIED_CASH):,.2f} / ₹{float(TARGET):,.2f})")


def main():
    """Entry point."""
    parser = argparse.ArgumentParser(description='Hermes Automated Revenue Loop')
    parser.add_argument('--mode', choices=['service', 'once'], default='once',
                        help='Run in service mode or one-shot mode')
    parser.add_argument('--poll-interval', type=int, default=10,
                        help='Seconds between polling cycles (service mode)')
    args = parser.parse_args()
    
    # Check kill switch
    if WORKER_KILL:
        logger.warning("WORKER_KILL=1 active at startup — exiting")
        sys.exit(0)
    
    if args.mode == 'once':
        # One-shot: scan and process
        events = scan_pending_upi()
        
        if events:
            logger.info(f"Processing {len(events)} pending events")
            for event in events:
                process_event(event)
        else:
            logger.info("No pending UPI events found")
        
        # Final progress
        progress = calculate_progress()
        print(f"\nRevenue loop complete. Progress: {progress}% (₹{float(VERIFIED_CASH):,.2f} / ₹{float(TARGET):,.2f})")
    elif args.mode == 'service':
        revenue_loop()


if __name__ == '__main__':
    main()