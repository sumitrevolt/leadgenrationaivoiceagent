#!/usr/bin/env python3
"""
Campaign Attribution Module

Classifies every payment as CAMPAIGN_REVENUE or HISTORICAL/OUTSIDE_CAMPAIGN.

Authoritative rule: Only payments received during the exact 7-day campaign window
(2026-08-23 to 2026-08-30 EOD IST) count toward the ₹5,00,000 target.

All other payments are classified as HISTORICAL/OUTSIDE_CAMPAIGN and must NEVER
increment real campaign cash, regardless of amount or source.
"""

import os
import sys
import json
from datetime import datetime, timezone
from decimal import Decimal

# Add project root to path (relative to this script)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Campaign period constants
CAMPAIGN_START = '2026-08-23'
CAMPAIGN_END = '2026-08-30'


def classify_payment(payment_received_at, provider_txn_id=None, customer_id=None, amount=None):
    """
    Classify a payment as CAMPAIGN_REVENUE or HISTORICAL/OUTSIDE_CAMPAIGN.
    
    Authoritative rule: Only payments received during the exact 7-day campaign window
    (2026-08-23 to 2026-08-30 EOD IST) count toward the ₹5,00,000 target.
    
    Returns: ('CAMPAIGN_REVENUE', True) or ('HISTORICAL_OUTSIDE_CAMPAIGN', False)
    """
    try:
        pt = datetime.fromisoformat(payment_received_at)
        if pt.tzinfo is None:
            pt = pt.replace(tzinfo=timezone.utc)
        
        # Campaign period: 2026-08-23 00:00 IST to 2026-08-30 EOD IST (23:59:59)
        start = datetime.strptime(CAMPAIGN_START, '%Y-%m-%d').replace(tzinfo=timezone.utc)
        # EOD IST = end of 2026-08-30 in IST timezone
        # IST = UTC+5:30, so 23:59:59 IST = 18:29:59 UTC on 2026-08-30
        end = datetime.strptime(CAMPAIGN_END, '%Y-%m-%d').replace(tzinfo=timezone.utc) + timedelta(
            hours=18, minutes=29, seconds=59)
        
        if start <= pt <= end:
            return 'CAMPAIGN_REVENUE', True
        else:
            return 'HISTORICAL_OUTSIDE_CAMPAIGN', False
            
    except Exception:
        return 'UNKNOWN', False


def is_campaign_eligible(payment_received_at):
    """Simplified check: was this payment in the campaign window?"""
    try:
        pt = datetime.fromisoformat(payment_received_at)
        if pt.tzinfo is None:
            pt = pt.replace(tzinfo=timezone.utc)
        start = datetime.strptime(CAMPAIGN_START, '%Y-%m-%d').replace(tzinfo=timezone.utc)
        end = datetime.strptime(CAMPAIGN_END, '%Y-%m-%d').replace(tzinfo=timezone.utc) + timedelta(
            hours=18, minutes=29, seconds=59)
        return start <= pt <= end
    except Exception:
        return False


def verify_payment_attribution(ref_id, client_id=None, invoice_id=None, amount=None, received_at=None):
    """
    Full attribution verification for a payment reference.
    
    Returns dict with classification and all checks:
    - campaign_eligible: True if in 7-day window
    - classification: CAMPAIGN_REVENUE or HISTORICAL
    - amounts_match: if amount provided, check against expected
    - client_matches: if client_id provided, check against record
    """
    from db import get_connection
    
    result = {
        'campaign_eligible': False,
        'classification': 'UNKNOWN',
        'amounts_match': None,
        'client_matches': None,
        'invoice_found': False,
    }
    
    try:
        # First check campaign eligibility
        result['campaign_eligible'] = is_campaign_eligible(received_at or '')
        
        if result['campaign_eligible']:
            result['classification'] = 'CAMPAIGN_REVENUE'
        else:
            result['classification'] = 'HISTORICAL_OUTSIDE_CAMPAIGN'
        
        # Check amount match if amount provided
        if amount is not None:
            # Look up the record to get expected amount
            conn = get_connection()
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    SELECT expected_amount, customer_id, invoice_id 
                    FROM upi_submissions 
                    WHERE reference_id = %s OR provider_txn_id = %s
                """, (ref_id, ref_id))
                record = cursor.fetchone()
                conn.close()
                
                if record:
                    expected_amount = Decimal(str(record[0]))
                    received_amount = Decimal(str(amount))
                    result['amounts_match'] = expected_amount == received_amount
                    result['invoice_found'] = True
            except Exception:
                conn.close()
        
        # Check client match if client_id provided
        if client_id is not None:
            conn = get_connection()
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    SELECT customer_id 
                    FROM upi_submissions 
                    WHERE reference_id = %s OR provider_txn_id = %s
                """, (ref_id, ref_id))
                record = cursor.fetchone()
                conn.close()
                
                if record:
                    result['client_matches'] = record[0] == client_id
            except Exception:
                conn.close()
    
    except Exception as e:
        logger.warning(f"Attribution verification error: {e}")
    
    return result


# Simple logger
import logging
logger = logging.getLogger('campaign_attribution')


def main():
    """Entry point — test classification."""
    import argparse
    parser = argparse.ArgumentParser(description='Campaign Attribution Classifier')
    parser.add_argument('--received-at', required=True, help='Payment received timestamp (ISO format)')
    parser.add_argument('--ref-id', help='Payment reference ID')
    parser.add_argument('--client-id', help='Client ID for match check')
    parser.add_argument('--amount', type=float, help='Amount for match check')
    args = parser.parse_args()
    
    classification, is_campaign = classify_payment(args.received_at)
    
    print(f"Payment received at: {args.received_at}")
    print(f"Campaign eligible: {is_campaign}")
    print(f"Classification: {classification}")
    
    # Verify full attribution
    if args.ref_id:
        attribution = verify_payment_attribution(args.ref_id, 
                                                 client_id=args.client_id,
                                                 amount=args.amount,
                                                 received_at=args.received_at)
        print(f"\nFull attribution report:")
        print(f"  campaign_eligible: {attribution['campaign_eligible']}")
        print(f"  classification: {attribution['classification']}")
        print(f"  amounts_match: {attribution['amounts_match']}")
        print(f"  client_matches: {attribution['client_matches']}")
        print(f"  invoice_found: {attribution['invoice_found']}")


if __name__ == '__main__':
    main()