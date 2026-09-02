"""
AI Growth Suite — Combo Product (Product 3) pricing source-of-truth.
=====================================================================

Product 3 = AI Automated Marketing + AI Voice Calling Agent — ek subscription me dono.

PRICING MODEL:
  - Combo Starter : Mktg Starter  + Voice Band A = ₹6,998 alag-alag → ₹4,999/mo  (save ₹1,999)
  - Combo Growth  : Mktg Growth   + Voice Band B = ₹12,998 alag-alag → ₹9,999/mo  (save ₹2,999)
  - Combo Pro     : Mktg Advanced + Voice Band C = ₹25,998 alag-alag → ₹21,999/mo (save ₹3,999)
  - Annual        : 10× monthly (2 mahine FREE)
  - Free Pilot    : 7 din / 50 voice calls (marketing features full, zero payment)

USP: India me koi aur competitor yeh bundle nahi deta.
     Marketing content warm audience banata hai; AI voice us audience ko convert karta hai.
     Alag-alag lene se ~₹2,000–4,000/mo zyada lagta hai.

Plan IDs:
  combo_starter_monthly / combo_starter_annual
  combo_growth_monthly  / combo_growth_annual
  combo_pro_monthly     / combo_pro_annual
  combo_pilot           (₹0, 7 din, 50 calls, marketing-lite)

Consumers:
  - GET /api/combo/packages (PUBLIC — pricing page)
  - app/billing/subscription.py _sync_combo_plans
  - app/billing/lead_usage.py (UNLIMITED_QUOTA = flat plan signal)

Pure-data module — koi heavy import nahi. Kabhi raise nahi karta.
"""

from __future__ import annotations

PILOT_DAYS: int = 7
PILOT_CALL_CAP: int = 50
UNLIMITED_QUOTA: int = 9_999  # lead_usage "unlimited" signal (voice_packages se same)

# --------------------------------------------------------------------------- #
# Combo tier definitions
# --------------------------------------------------------------------------- #
COMBO_TIERS: dict[str, dict] = {
    "starter": {
        "key": "combo_starter",
        "name": "Combo Starter",
        "tagline": "Apni brand banao + AI voice se leads convert karo — ek flat monthly subscription.",
        "voice_band": "A",
        "marketing_plan": "starter",
        "marketing_price_month": 1_999,
        "voice_price_month": 4_999,
        "price_separately": 6_998,  # if bought independently
        "price_month": 4_999,  # COMBO price (marketing almost FREE)
        "price_year": 49_990,  # 10× (2 mahine free)
        "savings_month": 1_999,
        "savings_year": 23_988,  # 12 × savings_month
        "plan_monthly": "combo_starter_monthly",
        "plan_annual": "combo_starter_annual",
        "niches_note": "Band A niches: Insurance, Coaching, Solar, Hospital Appointments, Upskilling, Travel",
        "highlight": False,
        "badge": "",
        "features": [
            # Marketing features (Starter)
            "AI social posts + festival calendar — roz ready content",
            "Google Business Profile audit + top fixes (0-100 score)",
            "4 branded festival posters har mahine",
            "WhatsApp content pack — broadcast + status messages",
            "Website lead-capture form / chat widget",
            # Voice features (Band A)
            "AI Voice Caller — Band A niches (insurance, coaching, solar, hospital, travel…)",
            "Unlimited AI calls — koi lead counting nahi",
            "Live call dashboard — recordings + Hinglish transcripts",
            "AI call qualification report — intent, budget, timeline",
            "Missed-call instant callback + WhatsApp follow-up drafts",
            "TRAI AI-disclosure built-in",
        ],
    },
    "growth": {
        "key": "combo_growth",
        "name": "Combo Growth",
        "tagline": "Poora marketing engine + AI voice — complete lead-to-conversion pipeline.",
        "voice_band": "B",
        "marketing_plan": "growth",
        "marketing_price_month": 2_999,
        "voice_price_month": 9_999,
        "price_separately": 12_998,
        "price_month": 9_999,
        "price_year": 99_990,
        "savings_month": 2_999,
        "savings_year": 35_988,
        "plan_monthly": "combo_growth_monthly",
        "plan_annual": "combo_growth_annual",
        "niches_note": "Band B niches: Home Loans, Study Abroad, Dental, Finance Advisory, CA & Legal",
        "highlight": True,
        "badge": "Best seller",
        "features": [
            # Marketing features (Growth)
            "Starter ke saare marketing features included",
            "Unlimited AI posters — jitne chahiye",
            "Content calendar auto — mahine bhar ka plan ready",
            "Competitor analysis + database reactivation (win-back)",
            "WhatsApp drip nurture sequences",
            "Monthly marketing performance report",
            # Voice features (Band B)
            "AI Voice Caller — Band B niches (home loans, study abroad, dental…)",
            "Unlimited AI calls — flat monthly, zero disputes",
            "Live call dashboard + transcripts + AI qualification",
            "CRM / webhook integration — leads seedha aapke system me",
            "Missed-call instant callback + WhatsApp follow-up drafts",
        ],
    },
    "pro": {
        "key": "combo_pro",
        "name": "Combo Pro",
        "tagline": "Premium marketing + AI voice for high-ticket niches — maximum ROI per client.",
        "voice_band": "C",
        "marketing_plan": "advanced",
        "marketing_price_month": 5_999,
        "voice_price_month": 19_999,
        "price_separately": 25_998,
        "price_month": 21_999,
        "price_year": 2_19_990,
        "savings_month": 3_999,
        "savings_year": 47_988,
        "plan_monthly": "combo_pro_monthly",
        "plan_annual": "combo_pro_annual",
        "niches_note": "Band C niches: IVF Clinics, Immigration, Commercial Solar/HVAC, Hair Transplant",
        "highlight": False,
        "badge": "Maximum savings",
        "features": [
            # Marketing features (Advanced)
            "Growth ke saare marketing features included",
            "AI Voice Agent FEATURE in marketing (inquiry auto-callback, 500 min/mo)",
            "Lead qualification + appointment booking — AI khud karta hai",
            "Priority support + dedicated monthly review call",
            # Voice features (Band C)
            "AI Voice Caller — Band C premium niches (IVF, immigration, hair transplant…)",
            "Unlimited AI calls — highest-ticket niche support",
            "Live call dashboard + transcripts + AI qualification",
            "Full CRM sync (Zoho / HubSpot) — qualified leads auto-push",
            "Missed-call instant callback + WhatsApp follow-up drafts",
            "Dedicated voice strategy session (setup + script tuning)",
        ],
    },
}

# All valid combo plan IDs
COMBO_PLAN_IDS: list[str] = (
    [COMBO_TIERS[t]["plan_monthly"] for t in COMBO_TIERS]
    + [COMBO_TIERS[t]["plan_annual"] for t in COMBO_TIERS]
    + ["combo_pilot"]
)

# Pilot package (₹0)
COMBO_PILOT: dict = {
    "key": "combo_pilot",
    "name": "Combo Pilot — Free 7 Days",
    "tagline": "Marketing + Voice dono try karo — 7 din mein dekho ROI, koi payment nahi.",
    "billing": "one-time",
    "price_month": 0,
    "price_year": None,
    "plan_id": "combo_pilot",
    "pilot_days": PILOT_DAYS,
    "pilot_call_cap": PILOT_CALL_CAP,
    "highlight": False,
    "badge": "Zero risk",
    "features": [
        "Marketing: 5 AI posts + 1 GBP audit + WhatsApp pack",
        f"Voice: {PILOT_CALL_CAP} AI calls on your niche database",
        "Live dashboard — recordings + transcripts",
        "Koi card ya payment nahi chahiye",
    ],
}


# --------------------------------------------------------------------------- #
# Public API helpers
# --------------------------------------------------------------------------- #


def get_combo_packages() -> dict:
    """Combo product ka full pricing payload — /api/combo/packages ke liye.

    Shape:
      {product, pricing_model, pilot, tiers:[starter,growth,pro+annual], comparison, savings_table}
    Kabhi raise nahi karta.
    """
    tiers_out = []
    for tier_key, t in COMBO_TIERS.items():
        tiers_out.append(
            {
                "key": t["key"],
                "name": t["name"],
                "tagline": t["tagline"],
                "voice_band": t["voice_band"],
                "marketing_plan": t["marketing_plan"],
                "price_month": t["price_month"],
                "price_year": t["price_year"],
                "price_separately": t["price_separately"],
                "savings_month": t["savings_month"],
                "savings_year": t["savings_year"],
                "plan_monthly": t["plan_monthly"],
                "plan_annual": t["plan_annual"],
                "niches_note": t["niches_note"],
                "features": t["features"],
                "highlight": t["highlight"],
                "badge": t["badge"],
                "billing_monthly": {
                    "price": t["price_month"],
                    "plan_id": t["plan_monthly"],
                },
                "billing_annual": {
                    "price": t["price_year"],
                    "price_monthly_equiv": t["price_month"],
                    "plan_id": t["plan_annual"],
                    "note": "2 mahine FREE (10× monthly rate)",
                },
            }
        )

    return {
        "product": "combo",
        "product_name": "AI Growth Suite",
        "tagline": "Marketing attract kare, AI Voice convert kare — ek subscription, poora pipeline.",
        "pricing_model": "flat_monthly",
        "usp": "India me koi competitor yeh bundle nahi deta.",
        "pilot": COMBO_PILOT,
        "tiers": tiers_out,
        "comparison": {
            "starter": {
                "separately": 6_998,
                "combo": 4_999,
                "savings_pct": round((1_999 / 6_998) * 100),
            },
            "growth": {
                "separately": 12_998,
                "combo": 9_999,
                "savings_pct": round((2_999 / 12_998) * 100),
            },
            "pro": {
                "separately": 25_998,
                "combo": 21_999,
                "savings_pct": round((3_999 / 25_998) * 100),
            },
        },
    }


def is_combo_plan(plan_id: str | None) -> bool:
    """True agar plan_id koi bhi combo plan hai."""
    return (plan_id or "").strip().lower() in {p.lower() for p in COMBO_PLAN_IDS}


def combo_plan_quota(plan_id: str | None) -> int:
    """Combo plans = unlimited voice calls (UNLIMITED_QUOTA). Pilot = PILOT_CALL_CAP."""
    p = (plan_id or "").strip().lower()
    if p == "combo_pilot":
        return PILOT_CALL_CAP
    if p in {x.lower() for x in COMBO_PLAN_IDS}:
        return UNLIMITED_QUOTA
    return 0


def combo_plan_price(plan_id: str | None) -> int:
    """Plan ID se monthly equivalent price (annual plan pe bhi monthly rate). Pilot = 0."""
    p = (plan_id or "").strip().lower()
    if p == "combo_pilot":
        return 0
    for t in COMBO_TIERS.values():
        if p in (t["plan_monthly"].lower(), t["plan_annual"].lower()):
            return t["price_month"]
    return 0


__all__ = [
    "COMBO_TIERS",
    "COMBO_PLAN_IDS",
    "COMBO_PILOT",
    "PILOT_DAYS",
    "PILOT_CALL_CAP",
    "UNLIMITED_QUOTA",
    "get_combo_packages",
    "is_combo_plan",
    "combo_plan_quota",
    "combo_plan_price",
]
