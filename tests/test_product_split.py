"""Tests — ADR-009 two-product split (2026-06-11).

Locks: (1) voice product catalog (per-niche per-10-leads, hybrid tiers+packs),
(2) niches lead_band + per-product sets (per-lead pricing REMOVED),
(3) qualified-lead quota metering (fail-open), (4) AI staff product split,
(5) billing plans sync (marketing new prices + 9 voice plans, legacy per_lead gone).
"""

from __future__ import annotations

import importlib


# ----------------------- voice catalog ----------------------- #
# PRICING MODEL (2026-06-12): FLAT MONTHLY per band (per-10-lead system REMOVED).
# Band A=₹4,999 · B=₹9,999 · C=₹19,999 /mo; annual = 10× (2 mahine free); pilot free.
def test_voice_packages_catalog():
    from app.marketing import voice_packages as vp

    # S = Starter Voice ₹1,999 (100 min) · F = Freemium ₹0 (10 calls/mo) — added 2026-08
    assert set(vp.BANDS) == {"S", "F", "A", "B", "C"}
    # flat monthly prices, band ladder A < B < C
    pa, pb, pc = (vp.BANDS[b]["price_month"] for b in ("A", "B", "C"))
    assert pa < pb < pc and pa > 0
    # annual = 10× monthly (2 mahine free) for every band
    for b in ("A", "B", "C"):
        assert vp.BANDS[b]["price_year"] == vp.BANDS[b]["price_month"] * 10
    # plan-id registry: 3 monthly + 3 annual + starter/freemium + free pilot
    assert set(vp.VOICE_PLAN_IDS) == {
        "voice_a_monthly",
        "voice_b_monthly",
        "voice_c_monthly",
        "voice_a_annual",
        "voice_b_annual",
        "voice_c_annual",
        "voice_starter_monthly",
        "voice_starter_annual",
        "voice_freemium",
        "voice_freemium_annual",
        "voice_pilot",
    }
    # flat plans = unlimited quota signal; pilot = fair-use call cap
    assert vp.plan_lead_quota("voice_a_monthly") == vp.UNLIMITED_QUOTA
    assert vp.plan_lead_quota("voice_pilot") == vp.PILOT_CALL_CAP


def test_voice_packages_resolution_helpers():
    from app.marketing import voice_packages as vp

    pkg = vp.get_voice_packages(band="b")
    # tiers = freemium + starter + pilot + band monthly + band annual
    assert pkg["band"] == "B" and len(pkg["tiers"]) == 5
    assert pkg["pricing_model"] == "flat_monthly"
    plan_ids = [t["plan_id"] for t in pkg["tiers"]]
    assert plan_ids == [
        "voice_freemium",
        "voice_starter_monthly",
        "voice_pilot",
        "voice_b_monthly",
        "voice_b_annual",
    ]
    assert vp.voice_plan_parts("voice_b_monthly") == ("voice_b_monthly", "B")
    assert vp.voice_plan_parts("starter") == ("", "A")  # marketing plan != voice
    assert vp.is_voice_plan("voice_c_monthly") and not vp.is_voice_plan("growth")
    assert vp.plan_lead_quota("voice_b_monthly") == vp.UNLIMITED_QUOTA
    assert vp.plan_lead_quota("advanced") == 0  # non-voice plan
    assert vp.normalize_band("junk") == "A"
    # niche -> band resolution (niches.py lead_band se)
    assert vp.niche_band("ivf_clinics") == "C"


# ----------------------- niches split ----------------------- #
def test_niches_lead_band_and_no_per_lead_pricing():
    from app import niches as n

    builtins = {k: v for k, v in n.NICHES.items() if not v.get("custom")}
    # curated builtin set + wizard catalog extension 2026-08 (12 SMB niches,
    # real_estate folded into real_estate_luxury as builtin) — 39 + 12 = 51
    assert len(builtins) == 51
    for k, cfg in builtins.items():
        assert "pricing_inr" not in cfg, f"per-lead pricing leftover in {k}"
        assert cfg.get("lead_band") in ("A", "B", "C"), k
    assert n.lead_band("ivf_clinics") == "C"  # premium band niche
    assert n.lead_band("nope_unknown") == "A"


def test_niches_for_product_sets_differ():
    from app import niches as n

    mkt = n.niches_for_product("marketing")
    voice = n.niches_for_product("voice")
    assert mkt and voice
    # dono products ke niche sets ALAG (marketing-only + leadgen-only dono exist)
    assert set(mkt) != set(voice)
    only_mkt = set(mkt) - set(voice)
    only_voice = set(voice) - set(mkt)
    assert only_mkt, "category=marketing niches missing"
    assert only_voice, "category=leadgen niches missing"
    assert n.niche_products({"category": "marketing"}) == ["marketing"]
    assert n.niche_products({"category": "leadgen"}) == ["voice"]
    assert n.niche_products({}) == ["marketing", "voice"]


# ----------------------- lead usage metering ----------------------- #
def test_lead_usage_guards_and_flow(tmp_path, monkeypatch):
    from app.billing import lead_usage as lu
    from app.marketing.voice_packages import UNLIMITED_QUOTA

    monkeypatch.setattr(lu, "_STORE", tmp_path / "lead_usage.jsonl")
    assert lu.record_qualified_lead("") is False
    assert lu.add_topup_leads("c1", 0) is False
    # fail-open: no client / non-voice plan
    assert lu.has_lead_quota("", "voice_a_monthly") is True
    assert lu.has_lead_quota("c1", "advanced") is True
    # flat monthly plan: usage METERED (reporting) par quota UNLIMITED -> gate hamesha open
    assert lu.record_qualified_lead("c1", ref="call_x", plan="voice_a_monthly")
    s = lu.usage_summary("c1", "voice_a_monthly")
    assert s["used_leads"] == 1 and s["quota_leads"] == UNLIMITED_QUOTA
    for i in range(9):
        lu.record_qualified_lead("c1", ref=f"c{i}", plan="voice_a_monthly")
    assert lu.leads_used_this_period("c1") == 10
    # unlimited flat plan -> has_lead_quota hamesha True
    assert lu.has_lead_quota("c1", "voice_a_monthly") is True
    # top-up still records additively (reporting)
    assert lu.add_topup_leads("c1", 10, ref="pay_1")
    assert lu.topup_leads_this_period("c1") == 10


# ----------------------- team split ----------------------- #
def test_staff_product_split():
    from app.platform import team

    assert len(team.STAFF) >= 12
    for k, v in team.STAFF.items():
        assert v.get("product") in ("marketing", "voice", "platform"), k
    mkt = team.staff_for_product("marketing")
    voice = team.staff_for_product("voice")
    assert "isha" in mkt and "swara" not in mkt
    assert "swara" in voice and "isha" not in voice
    # shared platform staff dono me
    assert "manager" in mkt and "manager" in voice
    assert set(team.staff_for_product("")) == set(team.STAFF)


# ----------------------- billing plans sync ----------------------- #
def test_billing_plans_two_products():
    import app.billing.subscription as sub

    importlib.reload(sub)  # ensure sync ran with current packages
    # marketing (Product 1) — merged marketing automation price
    assert float(sub.PRICING_PLANS["starter"].monthly_price) == 1999.0
    assert float(sub.PRICING_PLANS["growth"].monthly_price) == 2999.0
    assert float(sub.PRICING_PLANS["advanced"].monthly_price) == 5999.0
    # voice (Product 2) — flat per-band plans (monthly + annual) + free pilot
    from app.marketing.voice_packages import BANDS, UNLIMITED_QUOTA, VOICE_PLAN_IDS

    for pid in VOICE_PLAN_IDS:
        plan = sub.PRICING_PLANS.get(pid)
        assert plan is not None, pid
    # band monthly prices synced from voice_packages source-of-truth
    for b in ("A", "B", "C"):
        mp = sub.PRICING_PLANS[BANDS[b]["plan_monthly"]]
        assert float(mp.monthly_price) == float(BANDS[b]["price_month"])
        assert mp.leads_per_month == UNLIMITED_QUOTA  # flat = unlimited
    # free pilot plan
    assert float(sub.PRICING_PLANS["voice_pilot"].monthly_price) == 0.0
    # legacy PER-LEAD plans hata diye (per-lead system removed)
    assert "per_lead" not in sub.PRICING_PLANS
    assert "hybrid_starter" not in sub.PRICING_PLANS


def test_packages_marketing_prices():
    from app.marketing.packages import PACKAGES

    truth = {p["key"]: (p["price_inr_month"], p["price_inr_year"]) for p in PACKAGES}
    assert truth == {
        "starter": (1999, 19990),
        "growth": (2999, 29990),
        "advanced": (5999, 59990),
    }
