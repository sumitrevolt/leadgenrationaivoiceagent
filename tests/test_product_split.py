"""Tests — ADR-009 two-product split (2026-06-11).

Locks: (1) voice product catalog (per-niche per-10-leads, hybrid tiers+packs),
(2) niches lead_band + per-product sets (per-lead pricing REMOVED),
(3) qualified-lead quota metering (fail-open), (4) AI staff product split,
(5) billing plans sync (marketing new prices + 9 voice plans, legacy per_lead gone).
"""

from __future__ import annotations

import importlib


# ----------------------- voice catalog ----------------------- #
def test_voice_packages_catalog():
    from app.marketing import voice_packages as vp

    assert vp.PACK_SIZE == 10
    assert set(vp.BANDS) == {"A", "B", "C"}
    keys = [t["key"] for t in vp.VOICE_TIERS]
    assert keys == ["voice_starter", "voice_growth", "voice_pro"]
    for t in vp.VOICE_TIERS:
        assert t["leads_per_month"] % vp.PACK_SIZE == 0  # quota = 10-lead units
        for b in ("A", "B", "C"):
            assert t["price_inr_month"][b] > 0
        # band ladder: A < B < C
        assert t["price_inr_month"]["A"] < t["price_inr_month"]["B"] < t["price_inr_month"]["C"]
    # top-up rate tier-effective-rate se UPAR (upsell lever)
    st = next(t for t in vp.VOICE_TIERS if t["key"] == "voice_starter")
    for b in ("A", "B", "C"):
        per_lead_tier = st["price_inr_month"][b] / st["leads_per_month"]
        assert vp.lead_topup_price(b) / vp.PACK_SIZE >= per_lead_tier


def test_voice_packages_resolution_helpers():
    from app.marketing import voice_packages as vp

    pkg = vp.get_voice_packages(band="b")
    assert pkg["band"] == "B" and len(pkg["tiers"]) == 3
    assert pkg["tiers"][0]["plan_id"] == "voice_starter_b"
    assert pkg["topup_pack"]["price_inr"] == vp.lead_topup_price("B")
    assert vp.voice_plan_parts("voice_growth_c") == ("voice_growth", "C")
    assert vp.voice_plan_parts("starter") == ("", "A")  # marketing plan != voice
    assert vp.is_voice_plan("voice_pro_a") and not vp.is_voice_plan("growth")
    assert vp.plan_lead_quota("voice_growth_b") == 30
    assert vp.plan_lead_quota("advanced") == 0
    assert vp.normalize_band("junk") == "A"


# ----------------------- niches split ----------------------- #
def test_niches_lead_band_and_no_per_lead_pricing():
    from app import niches as n

    builtins = {k: v for k, v in n.NICHES.items() if not v.get("custom")}
    assert len(builtins) >= 40
    for k, cfg in builtins.items():
        assert "pricing_inr" not in cfg, f"per-lead pricing leftover in {k}"
        assert cfg.get("lead_band") in ("A", "B", "C"), k
    assert n.lead_band("real_estate_luxury") == "C"
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

    monkeypatch.setattr(lu, "_STORE", tmp_path / "lead_usage.jsonl")
    assert lu.record_qualified_lead("") is False
    assert lu.add_topup_leads("c1", 0) is False
    # fail-open: no client / non-voice plan
    assert lu.has_lead_quota("", "voice_starter_a") is True
    assert lu.has_lead_quota("c1", "advanced") is True
    # voice plan flow: quota 10 -> consume -> topup
    assert lu.record_qualified_lead("c1", ref="call_x", plan="voice_starter_a")
    s = lu.usage_summary("c1", "voice_starter_a")
    assert s["used_leads"] == 1 and s["quota_leads"] == 10 and s["remaining_leads"] == 9
    for i in range(9):
        lu.record_qualified_lead("c1", ref=f"c{i}", plan="voice_starter_a")
    assert lu.has_lead_quota("c1", "voice_starter_a") is False
    assert lu.add_topup_leads("c1", 10, ref="pay_1")
    assert lu.has_lead_quota("c1", "voice_starter_a") is True
    assert lu.leads_remaining("c1", "voice_starter_a") == 10


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
    # marketing (Product 1) — naye research prices
    assert float(sub.PRICING_PLANS["starter"].monthly_price) == 1199.0
    assert float(sub.PRICING_PLANS["growth"].monthly_price) == 2999.0
    assert float(sub.PRICING_PLANS["advanced"].monthly_price) == 6999.0
    # voice (Product 2) — 9 band plans, quota in leads_per_month
    from app.marketing.voice_packages import BANDS, VOICE_TIERS

    for t in VOICE_TIERS:
        for b in BANDS:
            pid = f"{t['key']}_{b.lower()}"
            plan = sub.PRICING_PLANS.get(pid)
            assert plan is not None, pid
            assert float(plan.monthly_price) == float(t["price_inr_month"][b])
            assert plan.leads_per_month == t["leads_per_month"]
    # legacy PER-LEAD plans hata diye (per-lead system removed)
    assert "per_lead" not in sub.PRICING_PLANS
    assert "hybrid_starter" not in sub.PRICING_PLANS


def test_packages_marketing_prices():
    from app.marketing.packages import PACKAGES

    truth = {p["key"]: (p["price_inr_month"], p["price_inr_year"]) for p in PACKAGES}
    assert truth == {
        "starter": (1199, 11990),
        "growth": (2999, 29990),
        "advanced": (6999, 69990),
    }
