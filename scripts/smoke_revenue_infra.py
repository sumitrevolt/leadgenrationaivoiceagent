#!/usr/bin/env python3
"""Post-deploy smoke — revenue+infra batch (2026-06-10).

Run IN CONTAINER:  docker exec leadgen_app python scripts/smoke_revenue_infra.py
Checks (no side-effects, no emails): module imports, flag states, warmup status,
invoice stats + FY numbering, usage-alert thresholds, packages annual fields.
"""

from __future__ import annotations

import json
import os


def main() -> int:
    ok = True

    flags = {
        k: os.environ.get(k, "")
        for k in ("AUTO_INVOICE", "EMAIL_WARMUP", "USAGE_ALERTS", "WARMUP_START_DATE")
    }
    print("FLAGS:", json.dumps(flags))

    try:
        from app.billing import gst_invoice

        st = gst_invoice.stats()
        nxt = gst_invoice.next_number()
        print("INVOICE:", json.dumps({"stats": st, "next_number": nxt}))
        assert nxt.startswith("INV/") and len(nxt) <= 16
    except Exception as e:
        ok = False
        print("INVOICE FAIL:", e)

    try:
        from app.platform import email_warmup

        ws = email_warmup.status()
        print("WARMUP:", json.dumps(ws))
        cap = email_warmup.effective_cap(25)
        print("WARMUP effective_cap(25):", cap)
        if ws.get("enabled") and ws.get("week", 0) >= 4 and cap != 25:
            ok = False
            print("WARMUP FAIL: wk4+ par cap base hona chahiye")
    except Exception as e:
        ok = False
        print("WARMUP FAIL:", e)

    try:
        from app.billing import usage_alerts

        m = usage_alerts.build_message(80, "Smoke Biz", 400, 500)
        assert "80%" in m["subject"]
        print("USAGE_ALERTS: build_message ok; recent:", len(usage_alerts.recent(5)))
    except Exception as e:
        ok = False
        print("USAGE_ALERTS FAIL:", e)

    try:
        from app.marketing.packages import PACKAGES

        annual = {p["key"]: p.get("price_inr_year") for p in PACKAGES}
        print("PACKAGES annual:", json.dumps(annual))
        assert all(v for v in annual.values())
    except Exception as e:
        ok = False
        print("PACKAGES FAIL:", e)

    # batch-2: pricing truth (checkout = packages prices, GST conditional, topup packs)
    try:
        from app.billing.subscription import PRICING_PLANS, BillingCycle, billing_manager
        from app.marketing.packages import get_topup_packs

        truth = {
            k: float(PRICING_PLANS[k].monthly_price)
            for k in ("starter", "growth", "advanced")
            if k in PRICING_PLANS
        }
        print("BILLING_TRUTH plans:", json.dumps(truth))
        assert truth == {"starter": 1199.0, "growth": 2999.0, "advanced": 6999.0}
        p = billing_manager.calculate_price("starter", BillingCycle.MONTHLY)
        py = billing_manager.calculate_price("starter", BillingCycle.YEARLY)
        gst_on = bool(os.environ.get("GST_GSTIN", "").strip())
        print(
            "BILLING_TRUTH starter monthly total:",
            float(p["total"]),
            "yearly:",
            float(py["total"]),
            "gst_registered:",
            gst_on,
        )
        if not gst_on:
            assert round(float(p["total"]), 2) == 1199.0 and round(float(py["total"]), 2) == 11990.0
        print("TOPUP packs:", json.dumps(get_topup_packs()))
    except Exception as e:
        ok = False
        print("BILLING_TRUTH FAIL:", e)

    print("SMOKE_RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
