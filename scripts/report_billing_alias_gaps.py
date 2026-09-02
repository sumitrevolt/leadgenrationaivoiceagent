#!/usr/bin/env python3
"""READ-ONLY dry-run: find invoice owner ids that do not resolve to a marketing client.

Does NOT mutate data. Match confidence is email-only (never display-name guessing).
Usage:
  python scripts/report_billing_alias_gaps.py
  python scripts/report_billing_alias_gaps.py --json
"""

from __future__ import annotations

import argparse
import json
import sys


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="Emit JSON lines")
    args = ap.parse_args()

    from app.billing import gst_invoice
    from app.marketing import clients_store

    clients = clients_store.list_clients() or []
    email_index: dict[str, list[str]] = {}
    for c in clients:
        em = str(c.get("email") or c.get("contact_email") or "").strip().lower()
        cid = str(c.get("id") or "").strip()
        if em and cid:
            email_index.setdefault(em, []).append(cid)

    rows = gst_invoice.list_invoices(2000) or []
    gaps = []
    for inv in rows:
        if inv.get("voided"):
            continue
        bid = str(inv.get("client_id") or "").strip()
        if not bid:
            continue
        if clients_store.resolve_client(bid):
            continue  # already linked or is a marketing id
        email = str((inv.get("recipient") or {}).get("email") or "").strip().lower()
        matches = email_index.get(email) or []
        gaps.append(
            {
                "billing_id": bid,
                "invoice": inv.get("number"),
                "recipient_email_present": bool(email),
                "email_match_count": len(matches),
                "suggested_marketing_id": matches[0] if len(matches) == 1 else None,
                "confidence": "email_unique" if len(matches) == 1 else "unmatched",
            }
        )

    if args.json:
        for g in gaps:
            print(json.dumps(g, ensure_ascii=False))
    else:
        print(f"orphan_billing_ids={len(gaps)}")
        for g in gaps[:50]:
            print(
                f"  billing={g['billing_id']} invoice={g['invoice']} "
                f"confidence={g['confidence']} suggest={g['suggested_marketing_id']}"
            )
        if len(gaps) > 50:
            print(f"  ... +{len(gaps) - 50} more")
        print(
            "DRY_RUN only — no mutations. To link a unique email match, use "
            "clients_store.link_billing_alias(marketing_id, billing_id) or "
            "POST /api/admin/upi/activate with billing_client_id=..."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
