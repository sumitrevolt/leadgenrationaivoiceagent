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
    # advanced voice (500 min metering ke saath)
    assert float(PRICING_PLANS["advanced"].monthly_price) == 5999.0
    assert PRICING_PLANS["advanced"].calls_per_month == 500


# ----------------- MRR truth: plan selected != money received (ADR-101) ------------ #
def test_estimated_mrr_counts_only_clients_with_payment_evidence(monkeypatch):
    """Headline `Est. MRR` must not count a tenant that never paid.

    LIVE BUG (2026-07-15 admin audit): `/app/admin` showed `Est. MRR ₹8.0K` while the
    Revenue Analytics panel on the SAME page showed `₹2.0K / Active: 1`. Cause:
    `estimated_mrr` summed every client with `status == "active"` with no payment
    gate, so it counted the synthetic `Test Biz` (plan=growth, ZERO invoices — the
    very tenant ADR-095 flagged as synthetic) and `leadgenai-self` (the company's own
    internal tenant). Real MRR was ₹1,999 (Jiya only).

    This is the exact bug class ADR-095 already solved for the dead-man alert:
    a plan is SELECTED at signup before any money moves. Gate = `has_paid_evidence()`.
    """
    from app.api import admin_dashboard_builders as b

    paying = {"id": "jiya-makeover", "status": "active", "plan": "starter"}
    never_paid = {
        "id": "1f89031d621a",  # pragma: allowlist secret
        "name": "Test Biz",
        "status": "active",
        "plan": "growth",
    }
    self_brand = {"id": "leadgenai-self", "status": "active", "plan": "growth"}

    # Only the real customer has invoice evidence.
    monkeypatch.setattr(
        b, "_has_paid_evidence", lambda c: str(c.get("id")) == "jiya-makeover", raising=False
    )

    mrr = b._paid_mrr_total([paying, never_paid, self_brand])
    assert mrr == 1999, (
        f"Est. MRR must count ONLY invoice-backed clients, got ₹{mrr}. "
        "A never-invoiced or self-brand tenant must contribute ₹0."
    )


def test_collect_live_stats_estimated_mrr_excludes_unpaid_tenants(monkeypatch):
    """Covers the REAL production path (`_collect_live_stats`), not just the helper.

    Reproduces the exact live client set observed on /app/admin 2026-07-15:
    Jiya (real, invoiced) + Test Biz (synthetic, 0 invoices) + leadgenai-self (own
    tenant). Before the ADR-101 gate this produced ₹7,997 ("Est. MRR ₹8.0K").
    """
    from app.api import admin_dashboard_builders as b
    from app.marketing import clients_store

    live_set = [
        {"id": "jiya-makeover", "status": "active", "plan": "starter"},
        {
            "id": "1f89031d621a",  # pragma: allowlist secret
            "name": "Test Biz",
            "status": "active",
            "plan": "growth",
        },
        {"id": "leadgenai-self", "status": "active", "plan": "growth"},
    ]
    monkeypatch.setattr(
        clients_store,
        "list_clients",
        lambda status=None, **kw: (
            [c for c in live_set if c["status"] == status] if status else list(live_set)
        ),
        raising=False,
    )
    monkeypatch.setattr(
        b, "_has_paid_evidence", lambda c: str(c.get("id")) == "jiya-makeover", raising=False
    )

    stats = b._collect_live_stats()
    assert stats["estimated_mrr"] == 1999, (
        f"real dashboard path reported ₹{stats['estimated_mrr']} — must be ₹1,999 "
        "(only the invoice-backed client). ₹7,997 = the ADR-101 regression."
    )
    assert sum(stats["mrr_by_product"].values()) == stats["estimated_mrr"], (
        "lane breakdown must reconcile with the headline total"
    )


def test_estimated_mrr_fails_open_when_ledger_unknown(monkeypatch):
    """Ledger unreadable => keep the plan-based estimate, never report a false ₹0.

    Mirrors ADR-095's fail-OPEN: a broken invoice ledger must not make real revenue
    silently vanish from the founder's dashboard. `has_paid_evidence()` is already
    fail-OPEN (tri-state None -> True), so this pins that we did not invert it.
    """
    from app.api import admin_dashboard_builders as b

    paying = {"id": "jiya-makeover", "status": "active", "plan": "starter"}
    monkeypatch.setattr(b, "_has_paid_evidence", lambda c: True, raising=False)
    assert b._paid_mrr_total([paying]) == 1999


def test_calculate_price_unregistered_flat(monkeypatch):
    """GST_GSTIN unset => advertised price hi total (koi illegal GST collection nahi)."""
    from app.billing.subscription import BillingCycle, billing_manager

    monkeypatch.delenv("GST_GSTIN", raising=False)
    p = billing_manager.calculate_price("starter", BillingCycle.MONTHLY)
    assert round(float(p["total"]), 2) == 1999.0 and float(p["tax"]) == 0.0
    # yearly = packages price_inr_year (2 mahine free)
    py = billing_manager.calculate_price("starter", BillingCycle.YEARLY)
    assert round(float(py["total"]), 2) == 19990.0
    pa = billing_manager.calculate_price("advanced", BillingCycle.YEARLY)
    assert round(float(pa["total"]), 2) == 59990.0


def test_calculate_price_registered_gst(monkeypatch):
    from app.billing.subscription import BillingCycle, billing_manager

    monkeypatch.setenv("GST_GSTIN", "27ABCDE1234F1Z5")
    p = billing_manager.calculate_price("starter", BillingCycle.MONTHLY)
    assert round(float(p["total"]), 2) == round(1999 * 1.18, 2)
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
    # LITERAL pins (audit 2026-07-04): pehle sirf ≥₹12/min tha — ek silent
    # price edit CI pe pass ho jata. Change = packages.py + yahan SAATH.
    by_key = {p["key"]: p for p in packs}
    assert by_key["topup_100"]["price_inr"] == 1499
    assert by_key["topup_250"]["price_inr"] == 3499
    assert by_key["topup_500"]["price_inr"] == 5999


def test_combo_tier_price_literals():
    """Combo billing-sync ab bhi active hai (router gated hai, module nahi) —
    tier prices pin karo taaki silent edit CI pe pakda jaye (audit 2026-07-04)."""
    from app.marketing.combo_packages import COMBO_TIERS, combo_plan_price

    assert COMBO_TIERS["starter"]["price_month"] == 4999
    assert COMBO_TIERS["growth"]["price_month"] == 9999
    assert COMBO_TIERS["pro"]["price_month"] == 21999
    for t in COMBO_TIERS.values():
        assert t["price_year"] == t["price_month"] * 10  # 2 mahine free
    assert combo_plan_price("combo_pro_monthly") == 21999
    assert combo_plan_price("combo_pilot") == 0
    assert combo_plan_price("unknown_plan") == 0


def test_usage_topup_guards():
    from app.billing import usage

    assert usage.add_topup_minutes("", 100) is False
    assert usage.add_topup_minutes("c1", 0) is False
    assert usage.topup_minutes("") == 0


def test_dunning_link_helpers(tmp_path, monkeypatch):
    from app.billing import dunning

    assert dunning._with_link("body", "") == "body"
    out = dunning._with_link("body", "https://rzp.io/x")
    assert "https://rzp.io/x" in out and out.startswith("body")
    # Razorpay removed 2026-06-18 — UPI path; UPI not configured in test env
    # => falls back to PRICING_URL (never empty).  Cached link reuse still works.
    case = {"id": "x1", "client_id": "c1", "amount": 999}
    result = asyncio.run(dunning._ensure_pay_link(case))
    assert result  # never empty — at minimum PRICING_URL
    case["pay_link"] = "https://rzp.io/cached"
    assert asyncio.run(dunning._ensure_pay_link(case)) == "https://rzp.io/cached"
    # no amount + no VPA => PRICING_URL fallback
    no_amt = asyncio.run(dunning._ensure_pay_link({"id": "x2", "client_id": "c2"}))
    assert no_amt == dunning.PRICING_URL


# ----------------------- public plans filter ----------------------- #
def test_public_plans_filter_keys():
    """/billing/plans ka filter source: packages keys subset of PRICING_PLANS."""
    from app.billing.subscription import PRICING_PLANS
    from app.marketing.packages import get_public_packages

    keys = [p["key"] for p in get_public_packages()]
    assert keys == ["starter", "advanced"]
    assert all(k in PRICING_PLANS for k in keys)


# ----------------------- annual-cycle undercharge guard (2026-06-26) ----------------------- #
def test_annual_plan_never_undercharged_by_cycle_arg(monkeypatch):
    """REGRESSION: *_annual plans encode price as monthly_price + yearly_discount.
    A checkout defaulting billing_cycle='monthly' for an annual plan once charged 1x
    the monthly figure (10x undercharge). calculate_price now forces the cycle from
    the plan-id suffix, so an annual plan is ALWAYS billed at the yearly (10x) amount,
    and a monthly plan is never accidentally yearly-discounted."""
    from app.billing.subscription import BillingCycle, billing_manager
    from app.marketing.voice_packages import BANDS

    monkeypatch.delenv("GST_GSTIN", raising=False)
    for band, info in BANDS.items():
        pm = float(info["price_month"])
        monthly = billing_manager.calculate_price(info["plan_monthly"], BillingCycle.MONTHLY)
        # annual queried with the WRONG (monthly) cycle — the bug scenario
        annual_buggy = billing_manager.calculate_price(info["plan_annual"], BillingCycle.MONTHLY)
        annual_yr = billing_manager.calculate_price(info["plan_annual"], BillingCycle.YEARLY)
        assert round(float(monthly["total"]), 2) == round(pm, 2)
        # annual is forced to yearly regardless of the cycle arg, and is ~10x monthly
        assert round(float(annual_buggy["total"]), 2) == round(float(annual_yr["total"]), 2)
        assert round(float(annual_yr["total"]), 2) == round(pm * 10, 2), band
        # a monthly plan must NOT pick up the yearly discount even if asked for yearly
        monthly_as_yr = billing_manager.calculate_price(info["plan_monthly"], BillingCycle.YEARLY)
        assert round(float(monthly_as_yr["total"]), 2) == round(pm, 2)


# ----------------------- voice band literal price pins (2026-07-02) ----------------------- #
def test_voice_band_literal_prices():
    """The other voice tests only assert INTERNAL consistency vs BANDS, so an
    accidental BANDS edit would pass silently. Pin the LITERAL ₹ figures from
    voice_packages.py (source-of-truth): A 4999 / B 9999 / C 19999 monthly,
    annual = 10x (2 months free) = 49990 / 99990 / 199990."""
    from app.marketing.voice_packages import BANDS

    assert BANDS["A"]["price_month"] == 4999, "Band A monthly must stay ₹4,999"
    assert BANDS["B"]["price_month"] == 9999, "Band B monthly must stay ₹9,999"
    assert BANDS["C"]["price_month"] == 19999, "Band C monthly must stay ₹19,999"
    assert BANDS["A"]["price_year"] == 49990, "Band A annual must stay ₹49,990 (10x)"
    assert BANDS["B"]["price_year"] == 99990, "Band B annual must stay ₹99,990 (10x)"
    assert BANDS["C"]["price_year"] == 199990, "Band C annual must stay ₹1,99,990 (10x)"


# ----------------------- starter feature catalog (2026-06-29: +40 features) ----------------------- #
def test_starter_feature_groups_invariant():
    """Main plan +40 features (33 core + 40 naye = 73). feature_groups grouped view,
    flat `features` usi se DERIVE (single source — koi drift nahi)."""
    from app.marketing.packages import PACKAGES

    starter = next(p for p in PACKAGES if p["key"] == "starter")
    groups = starter.get("feature_groups") or []
    flat = starter.get("features") or []

    assert len(groups) >= 6, "kam se kam 6 categories honi chahiye"
    for g in groups:
        assert g.get("title") and isinstance(g.get("items"), list) and g["items"], g
    # flat == flatten(groups) — drift guard (yahi single-source invariant)
    flattened = [it for g in groups for it in g["items"]]
    assert flat == flattened, "features flat list groups se derive honi chahiye (drift)"
    assert len(flat) >= 70, f"33 core + 40 naye expected, mila {len(flat)}"
    assert len(flat) == len(set(flat)), "duplicate feature line nahi honi chahiye"


def test_starter_feature_groups_synced_to_billing_plan():
    """packages.py feature_groups -> PRICING_PLANS['starter'].feature_groups (sync)."""
    from app.billing.subscription import PRICING_PLANS
    from app.marketing.packages import PACKAGES

    starter_pkg = next(p for p in PACKAGES if p["key"] == "starter")
    plan = PRICING_PLANS["starter"]
    assert getattr(plan, "feature_groups", None), "billing plan me feature_groups sync hone chahiye"
    assert len(plan.feature_groups) == len(starter_pkg["feature_groups"])
