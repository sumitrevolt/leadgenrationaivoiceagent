"""Tests — billing pricing-truth fix + top-up + recovery links (batch-2, 2026-06-10).

CRITICAL BUG FIXED: /pricing page ₹999 dikhata tha par checkout billing_manager ke
legacy Cloud-Run plans se ₹15,000+18% charge karta; 'advanced' checkout 404 deta;
unregistered hote hue GST collect hota tha. Yeh suite us truth ko lock karta hai.
"""

from __future__ import annotations

import asyncio
import os


# ----------------------- pricing truth sync ----------------------- #
def test_pricing_plans_synced_to_packages():
    from app.billing.subscription import PRICING_PLANS
    from app.marketing.packages import PACKAGES

    for pkg in PACKAGES:
        key = pkg["key"]
        assert key in PRICING_PLANS, f"{key} billing plans me hona chahiye (checkout 404 bug)"
        assert float(PRICING_PLANS[key].monthly_price) == float(pkg["price_inr_month"])
    # advanced (pehle missing tha) — 500 min metering ke saath
    assert float(PRICING_PLANS["advanced"].monthly_price) == 6999.0
    assert PRICING_PLANS["advanced"].calls_per_month == 500


def test_calculate_price_unregistered_flat(monkeypatch):
    """GST_GSTIN unset => advertised price hi total (koi illegal GST collection nahi)."""
    from app.billing.subscription import BillingCycle, billing_manager

    monkeypatch.delenv("GST_GSTIN", raising=False)
    p = billing_manager.calculate_price("starter", BillingCycle.MONTHLY)
    assert round(float(p["total"]), 2) == 1199.0 and float(p["tax"]) == 0.0
    # yearly = packages price_inr_year (2 mahine free)
    py = billing_manager.calculate_price("starter", BillingCycle.YEARLY)
    assert round(float(py["total"]), 2) == 11990.0
    pa = billing_manager.calculate_price("advanced", BillingCycle.YEARLY)
    assert round(float(pa["total"]), 2) == 69990.0


def test_calculate_price_registered_gst(monkeypatch):
    from app.billing.subscription import BillingCycle, billing_manager

    monkeypatch.setenv("GST_GSTIN", "27ABCDE1234F1Z5")
    p = billing_manager.calculate_price("starter", BillingCycle.MONTHLY)
    assert round(float(p["total"]), 2) == round(1199 * 1.18, 2)
    assert round(float(p["tax_rate"]), 0) == 18.0


# ----------------------- top-up packs ----------------------- #
def test_topup_pack_helpers():
    from app.marketing.packages import get_topup_packs, topup_pack

    packs = get_topup_packs()
    assert len(packs) >= 3 and all(p["key"].startswith("topup_") for p in packs)
    p100 = topup_pack("topup_100")
    assert p100["minutes"] == 100 and p100["price_inr"] > 0
    assert topup_pack("nope") == {}
    # effective rate included-rate (₹12/min) se upar (upsell math)
    assert p100["price_inr"] / p100["minutes"] >= 12.0


def test_usage_topup_guards():
    from app.billing import usage

    assert usage.add_topup_minutes("", 100) is False
    assert usage.add_topup_minutes("c1", 0) is False
    assert usage.topup_minutes("") == 0


# ----------------------- recovery links ----------------------- #
def test_payment_link_inert_without_creds(monkeypatch):
    """extra_notes param accepted; creds unset => graceful error (INERT)."""
    from app.billing import payment_links

    monkeypatch.setattr(payment_links, "_creds", lambda: ("", ""))
    res = asyncio.run(
        payment_links.create_payment_link(
            "c1", 999, "renewal", extra_notes={"plan_id": "starter"}
        )
    )
    assert res["ok"] is False and "creds" in res["error"].lower() or "razorpay" in res["error"].lower()


def test_dunning_link_helpers(tmp_path, monkeypatch):
    from app.billing import dunning

    assert dunning._with_link("body", "") == "body"
    out = dunning._with_link("body", "https://rzp.io/x")
    assert "https://rzp.io/x" in out and out.startswith("body")
    # unconfigured => "" (graceful), case cached link reuse
    import app.billing.payment_links as pl

    monkeypatch.setattr(pl, "is_configured", lambda: False)
    case = {"id": "x1", "client_id": "c1", "amount": 999}
    assert asyncio.run(dunning._ensure_pay_link(case)) == ""
    case["pay_link"] = "https://rzp.io/cached"
    assert asyncio.run(dunning._ensure_pay_link(case)) == "https://rzp.io/cached"
    # no amount => ""
    assert asyncio.run(dunning._ensure_pay_link({"id": "x2", "client_id": "c2"})) == ""


# ----------------------- public plans filter ----------------------- #
def test_public_plans_filter_keys():
    """/billing/plans ka filter source: packages keys subset of PRICING_PLANS."""
    from app.billing.subscription import PRICING_PLANS
    from app.marketing.packages import PACKAGES

    keys = [p["key"] for p in PACKAGES]
    assert keys == ["starter", "growth", "advanced"]
    assert all(k in PRICING_PLANS for k in keys)
