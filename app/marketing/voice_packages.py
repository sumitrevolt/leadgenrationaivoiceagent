"""
AI Voice Calling Agent — STANDALONE product (Product 2) ka pricing source-of-truth.
====================================================================================

Yeh `packages.py` (Product 1: AI Automated Marketing) se ALAG product hai —
full Hinglish AI telecaller (qualification, appointments, follow-ups), India-legal
(TRAI disclosure built-in; cold-calling DLT-gated, tab tak consented/inbound/own-DB).

PRICING MODEL (ADR-009, user-approved 2026-06-11): **HYBRID, per-NICHE per-10-leads**
  - Billable unit = AI-QUALIFIED "interested" lead (call_qualifier verdict) — outcome-based.
  - PER-LEAD pricing system REMOVED (purana niches.py `pricing_inr` deleted) —
    sab kuch 10-lead UNITS me: monthly tier quota (1x/3x/6x packs) + top-up packs.
  - Har niche ek BAND me (A mass-local / B high-ticket / C premium-HNI) —
    band hi price decide karta hai (niches.py `lead_band` field).

Research anchors (June 2026): outcome pricing $3-25/qualified lead global;
human telecaller ₹55-85/resolved contact; humara COGS (free AI stack + Exotel
₹0.45-0.75/min) ≈ ₹30-50/qualified lead → healthy margin Band A pe bhi.

Consumers:
  - GET /api/voice/packages (PUBLIC — /voice-agent page fetch karta hai)
  - app/billing/subscription.py _sync_plans_from_packages (voice plan keys)
  - app/billing/lead_usage.py (quota per tier)

Pure-data module — koi heavy import nahi (import-safe, kabhi raise nahi karta).
"""

from __future__ import annotations

PACK_SIZE = 10  # leads per unit — "per 10 qualified leads" pricing ka atom

BANDS: dict[str, dict] = {
    "A": {
        "name": "Band A — Local Services",
        "desc": "Gyms, salons, tuition, repairs, clinics — mass local niches",
        "effective_per_lead_note": "₹300–450/qualified lead effective",
    },
    "B": {
        "name": "Band B — High-Ticket",
        "desc": "Real estate, study abroad, solar, interiors — bade ticket niches",
        "effective_per_lead_note": "₹900–1,200/qualified lead effective",
    },
    "C": {
        "name": "Band C — Premium / HNI",
        "desc": "Luxury real estate, wealth, fertility — premium niches",
        "effective_per_lead_note": "₹2,200–3,000/qualified lead effective",
    },
}

# Monthly tiers — quota = qualified leads/month (PACK_SIZE ke multiples).
# fair_use_minutes = abuse-guard cap (page footnote), quota khatam => top-up.
VOICE_TIERS: list[dict] = [
    {
        "key": "voice_starter",
        "name": "Voice Starter",
        "tagline": "AI telecaller shuru karo — mahine ke 10 qualified leads guaranteed pipeline me.",
        "leads_per_month": 10,
        "fair_use_minutes": 600,
        "price_inr_month": {"A": 3999, "B": 9999, "C": 24999},
        "features": [
            "Hinglish AI telecaller (insaan-jaisi awaaz, TRAI AI-disclosure built-in)",
            "10 AI-qualified leads har mahine (interested-verified)",
            "1 calling campaign (inbound/consented/own database)",
            "Sab call recordings + transcripts dashboard me",
            "Lead qualification report har call ki (budget, intent, timeline)",
            "WhatsApp follow-up drafts har qualified lead pe",
        ],
        "highlight": False,
        "badge": "",
    },
    {
        "key": "voice_growth",
        "name": "Voice Growth",
        "tagline": "Sales team jaisa output — 30 qualified leads/mahina, appointments AI khud book kare.",
        "leads_per_month": 30,
        "fair_use_minutes": 1800,
        "price_inr_month": {"A": 9999, "B": 26999, "C": 69999},
        "features": [
            "Voice Starter ke saare features included",
            "30 AI-qualified leads har mahine",
            "3 parallel campaigns + appointment booking AI khud karta hai",
            "Missed-call instant AI callback",
            "Old database reactivation calling (win-back)",
            "CRM/webhook integration (leads seedha aapke system me)",
        ],
        "highlight": True,
        "badge": "⭐ Sabse popular",
    },
    {
        "key": "voice_pro",
        "name": "Voice Pro",
        "tagline": "Full AI calling floor — 60 qualified leads/mahina, human telecaller cost ke fraction me.",
        "leads_per_month": 60,
        "fair_use_minutes": 3600,
        "price_inr_month": {"A": 17999, "B": 49999, "C": 129999},
        "features": [
            "Voice Growth ke saare features included",
            "60 AI-qualified leads har mahine",
            "Unlimited campaigns + priority calling window",
            "Human-transfer on hot lead (aapke number pe live connect)",
            "Dedicated success review call har mahine",
            "API access + white-label reports",
        ],
        "highlight": False,
        "badge": "",
    },
]

# Extra 10-lead TOP-UP pack (quota khatam hone pe; period-end pe EXPIRE).
# Rate tier-effective-rate se UPAR — upgrade/renew sasta lage (minute-topup pattern).
LEAD_TOPUP_PACK: dict = {
    "key": "lead_pack_10",
    "leads": PACK_SIZE,
    "label": "10 extra qualified leads",
    "price_inr": {"A": 4499, "B": 11999, "C": 29999},
}

# Quota lookup — lead_usage.py metering ke liye (plan key -> leads/month).
PLAN_LEADS: dict[str, int] = {t["key"]: int(t["leads_per_month"]) for t in VOICE_TIERS}


def normalize_band(band: str | None) -> str:
    """'a'/'A'/junk -> valid band letter (default 'A'). Kabhi raise nahi."""
    b = (band or "").strip().upper()
    return b if b in BANDS else "A"


def niche_band(niche_key: str | None) -> str:
    """Niche key -> band letter (niches.py `lead_band` se; unknown => 'A')."""
    try:
        from app.niches import NICHES

        cfg = NICHES.get((niche_key or "").strip().lower()) or {}
        return normalize_band(cfg.get("lead_band"))
    except Exception:
        return "A"


def get_voice_packages(band: str | None = None, niche: str | None = None) -> dict:
    """Voice product ka public pricing payload — band ya niche se resolve.

    Returns {band, band_info, pack_size, tiers:[{...price_inr_month:int}], topup_pack}.
    Tier prices band-resolved INT hote hain (page ko matrix nahi dikhana padta).
    Kabhi raise nahi karta.
    """
    b = normalize_band(band) if band else niche_band(niche)
    tiers = []
    for t in VOICE_TIERS:
        tt = {k: v for k, v in t.items() if k != "price_inr_month"}
        tt["price_inr_month"] = int(t["price_inr_month"].get(b, 0))
        tt["plan_id"] = f"{t['key']}_{b.lower()}"
        tiers.append(tt)
    pack = {k: v for k, v in LEAD_TOPUP_PACK.items() if k != "price_inr"}
    pack["price_inr"] = int(LEAD_TOPUP_PACK["price_inr"].get(b, 0))
    return {
        "product": "voice_agent",
        "band": b,
        "band_info": dict(BANDS.get(b) or {}),
        "pack_size": PACK_SIZE,
        "tiers": tiers,
        "topup_pack": pack,
        "compliance_note": "TRAI AI-disclosure har call pe; cold outbound DLT ke baad — tab tak inbound/consented/own-database calling.",
    }


def voice_plan_parts(plan_id: str | None) -> tuple[str, str]:
    """'voice_growth_b' -> ('voice_growth', 'B'). Invalid => ('', 'A')."""
    p = (plan_id or "").strip().lower()
    for t in VOICE_TIERS:
        for b in BANDS:
            if p == f"{t['key']}_{b.lower()}":
                return t["key"], b
        if p == t["key"]:
            return t["key"], "A"
    return "", "A"


def is_voice_plan(plan_id: str | None) -> bool:
    return bool(voice_plan_parts(plan_id)[0])


def voice_plan_price(plan_id: str | None) -> int:
    """Band-resolved monthly price for 'voice_<tier>_<band>' (0 if unknown)."""
    key, band = voice_plan_parts(plan_id)
    for t in VOICE_TIERS:
        if t["key"] == key:
            return int(t["price_inr_month"].get(band, 0))
    return 0


def lead_topup_price(band: str | None) -> int:
    return int(LEAD_TOPUP_PACK["price_inr"].get(normalize_band(band), 0))


def plan_lead_quota(plan_id: str | None) -> int:
    """Plan (with ya without band suffix) -> leads/month quota (0 = not voice plan)."""
    key, _ = voice_plan_parts(plan_id)
    return PLAN_LEADS.get(key, 0)
