"""
AI Voice Calling Agent — STANDALONE product (Product 2) pricing source-of-truth.
==================================================================================

PRICING MODEL (updated 2026-06-12): **FLAT MONTHLY per niche-band**
  - Ek band = ek flat monthly fee. Koi lead-counting nahi, koi disputes nahi.
  - Client pay karta hai aur hum unlimited AI calls karte hain us niche ke liye.
  - Band A (volume niches)   : ₹4,999/mo
  - Band B (mid-premium)     : ₹9,999/mo
  - Band C (premium/HNI)     : ₹19,999/mo
  - Annual                   : 10× monthly (2 mahine free)
  - Free pilot               : 7 din / 50 calls (zero payment)

  Niche → band mapping: niches.py `lead_band` field.
  Band → plan ID       : voice_a_monthly / voice_b_monthly / voice_c_monthly
                         voice_a_annual  / voice_b_annual  / voice_c_annual
                         voice_pilot     (free, 7 days)

Backward-compat helpers retained:
  - voice_plan_price(), is_voice_plan(), plan_lead_quota() (returns UNLIMITED_QUOTA)
  - get_voice_packages() — same shape as before (tiers list, band_info)

Consumers:
  - GET /api/voice/packages (PUBLIC — /voice-agent page)
  - app/billing/subscription.py _sync_voice_plans (plan key list)
  - app/billing/lead_usage.py (quota check — unlimited for flat plans)

Pure-data module — koi heavy import nahi. Kabhi raise nahi karta.
"""

from __future__ import annotations

PILOT_DAYS: int = 7
PILOT_CALL_CAP: int = 50  # fair-use pilot cap
UNLIMITED_QUOTA: int = 9_999  # lead_usage.py me "unlimited" signal

# Band metadata
BANDS: dict[str, dict] = {
    "S": {
        "name": "Starter Voice — 100 min",
        "desc": "Perfect for freelancers and small setups testing AI voice.",
        "niches_sample": "Any Niche (100 min cap)",
        "price_month": 1999,
        "price_year": 19990,
        "plan_monthly": "voice_starter_monthly",
        "plan_annual": "voice_starter_annual",
    },
    "F": {
        "name": "Freemium — 10 calls/mo",
        "desc": "Viral free tier forever. 10 calls per month.",
        "niches_sample": "Any Niche (10 calls/mo cap)",
        "price_month": 0,
        "price_year": 0,
        "plan_monthly": "voice_freemium",
        "plan_annual": "voice_freemium_annual",
    },
    "A": {
        "name": "Band A — Volume niches",
        "desc": "Insurance, coaching, solar, hospital, upskilling, travel, events — mass market",
        "niches_sample": "Insurance · Coaching · Solar · Hospital Appointments · Upskilling · Travel",
        "price_month": 4_999,
        "price_year": 49_990,
        "plan_monthly": "voice_a_monthly",
        "plan_annual": "voice_a_annual",
    },
    "B": {
        "name": "Band B — Mid-premium niches",
        "desc": "Home loans, study abroad, dental, modular kitchen, finance advisory, CA",
        "niches_sample": "Home Loans · Study Abroad · Dental · Finance Advisory · CA & Legal",
        "price_month": 9_999,
        "price_year": 99_990,
        "plan_monthly": "voice_b_monthly",
        "plan_annual": "voice_b_annual",
    },
    "C": {
        "name": "Band C — Premium niches",
        "desc": "IVF, immigration, commercial solar, commercial HVAC, hair transplant",
        "niches_sample": "IVF Clinics · Immigration · Commercial Solar · HVAC · Hair Transplant",
        "price_month": 19_999,
        "price_year": 1_99_990,
        "plan_monthly": "voice_c_monthly",
        "plan_annual": "voice_c_annual",
    },
}

# All valid plan IDs (used by subscription._sync_voice_plans)
VOICE_PLAN_IDS: list[str] = (
    [BANDS[b]["plan_monthly"] for b in BANDS]
    + [BANDS[b]["plan_annual"] for b in BANDS]
    + ["voice_pilot"]
)

# Features shared across all paid plans
_BASE_FEATURES: list[str] = [
    "8+ Indian languages (Hindi, Tamil, Telugu, Marathi, Gujarati, Bengali, etc) — human-like voice, TRAI AI-disclosure built-in",
    "Unlimited AI calls aapke niche database pe",
    "Live call dashboard — recordings + Hinglish transcripts",
    "Har call ka AI qualification report (intent, budget, timeline)",
    "Missed-call instant AI callback",
    "WhatsApp follow-up drafts har interested lead ke liye",
    "CRM / webhook integration (leads seedha aapke system me)",
]


# Tier-display list for the /voice-agent page (3 cards, band-resolved)
def _make_tiers(band: str) -> list[dict]:
    b = BANDS[band]
    return [
        {
            "key": "voice_freemium",
            "name": "Freemium",
            "tagline": "Duniya ko AI power dikhane ke liye — 10 free calls/mo hamesha.",
            "billing": "monthly",
            "price_inr_month": 0,
            "price_inr_year": None,
            "calls_included": "10 calls / mahina",
            "features": _BASE_FEATURES + ["Hamesha ke liye free", "Basic support"],
            "highlight": False,
            "badge": "Viral",
            "plan_id": "voice_freemium",
        },
        {
            "key": "voice_starter_monthly",
            "name": "Starter Voice",
            "tagline": "Chhote business/freelancers ke liye perfect shuruwat.",
            "billing": "monthly",
            "price_inr_month": 1999,
            "price_inr_year": 19990,
            "calls_included": "100 min / mahina",
            "features": _BASE_FEATURES + ["Sabse sasta AI Voice in India"],
            "highlight": False,
            "badge": "New Entry",
            "plan_id": "voice_starter_monthly",
        },
        {
            "key": "voice_pilot",
            "name": "Free Pilot",
            "tagline": f"7 din mein dekho AI agent kaisa kaam karta hai — {PILOT_CALL_CAP} calls free.",
            "billing": "one-time",
            "price_inr_month": 0,
            "price_inr_year": None,
            "calls_included": f"{PILOT_CALL_CAP} calls (7 din)",
            "features": [
                "AI telecaller live on your niche",
                f"{PILOT_CALL_CAP} real calls aapke database pe",
                "Live dashboard + transcripts",
                "No credit card required",
            ],
            "highlight": False,
            "badge": "Zero risk",
            "plan_id": "voice_pilot",
        },
        {
            "key": b["plan_monthly"],
            "name": f"Monthly — {band} band",
            "tagline": "Flat monthly. Koi lead-counting nahi, koi surprise invoice nahi.",
            "billing": "monthly",
            "price_inr_month": b["price_month"],
            "price_inr_year": None,
            "calls_included": "Unlimited calls",
            "features": _BASE_FEATURES + ["Cancel anytime — koi lock-in nahi"],
            "highlight": True,
            "badge": "Most popular",
            "plan_id": b["plan_monthly"],
        },
        {
            "key": b["plan_annual"],
            "name": f"Annual — {band} band",
            "tagline": "2 mahine free — ek baar pay karo, saal bhar tension nahi.",
            "billing": "annual",
            "price_inr_month": b["price_month"],  # shown as "per month equivalent"
            "price_inr_year": b["price_year"],
            "calls_included": "Unlimited calls",
            "features": _BASE_FEATURES
            + [
                "2 mahine free (vs monthly billing)",
                "Priority support + dedicated review call",
            ],
            "highlight": False,
            "badge": "Best value",
            "plan_id": b["plan_annual"],
        },
    ]


def normalize_band(band: str | None) -> str:
    """'a'/'A'/junk -> valid band letter (default 'A'). Kabhi raise nahi."""
    b = (band or "").strip().upper()
    return b if b in BANDS else "A"


def niche_band(niche_key: str | None) -> str:
    """Niche key -> band letter (niches.py lead_band se; unknown => 'A')."""
    try:
        from app.niches import NICHES

        cfg = NICHES.get((niche_key or "").strip().lower()) or {}
        return normalize_band(cfg.get("lead_band"))
    except Exception:
        return "A"


def get_voice_packages(band: str | None = None, niche: str | None = None) -> dict:
    """Voice product ka public pricing payload — band ya niche se resolve.

    Returns {band, band_info, tiers:[pilot, monthly, annual], compliance_note}.
    Same outer shape as before — /voice-agent page compatible.
    Kabhi raise nahi karta.
    """
    b = normalize_band(band) if band else niche_band(niche)
    return {
        "product": "voice_agent",
        "pricing_model": "flat_monthly",
        "band": b,
        "band_info": dict(BANDS[b].items()),
        "pilot_days": PILOT_DAYS,
        "pilot_call_cap": PILOT_CALL_CAP,
        "tiers": _make_tiers(b),
        "compliance_note": (
            "TRAI AI-disclosure har call pe built-in. "
            "Cold outbound DLT approval ke baad; tab tak inbound / consented / own-database calling."
        ),
    }


# ---------------------------------------------------------------------------
# Backward-compat helpers (lead_usage.py / subscription.py ke liye)
# ---------------------------------------------------------------------------


def voice_plan_parts(plan_id: str | None) -> tuple[str, str]:
    """plan_id -> (base_key, band). e.g. 'voice_b_monthly' -> ('voice_b_monthly','B').
    Invalid / unknown -> ('', 'A').
    """
    p = (plan_id or "").strip().lower()
    for band, info in BANDS.items():
        if p == info["plan_monthly"]:
            return info["plan_monthly"], band
        if p == info["plan_annual"]:
            return info["plan_annual"], band
    if p == "voice_pilot":
        return "voice_pilot", "A"
    # Legacy plan IDs (old per-10-lead system) — treat as Band A monthly
    legacy_prefixes = ("voice_starter", "voice_growth", "voice_pro")
    for pfx in legacy_prefixes:
        if p.startswith(pfx):
            band_suffix = p.replace(pfx + "_", "").upper()
            b = band_suffix if band_suffix in BANDS else "A"
            return "voice_a_monthly", b
    return "", "A"


def is_voice_plan(plan_id: str | None) -> bool:
    """True agar plan_id koi bhi voice plan hai (flat ya legacy)."""
    return bool(voice_plan_parts(plan_id)[0])


def voice_plan_price(plan_id: str | None) -> int:
    """Band-resolved monthly price (annual plan pe bhi monthly equivalent deta hai).
    Pilot plan => 0.
    """
    key, band = voice_plan_parts(plan_id)
    if key == "voice_pilot":
        return 0
    # voice_plan_parts() returns ('', 'A') for UNKNOWN ids — band alone is
    # always truthy, so without the key-check every unknown string priced as
    # Band-A ₹4,999 (audit 2026-07-04: broke UPI floor lookups for combo ids).
    if not key or not band or band not in BANDS:
        return 0
    return BANDS[band]["price_month"]


def plan_lead_quota(plan_id: str | None) -> int:
    """Flat model me 'unlimited' quota — lead_usage.py ke liye UNLIMITED_QUOTA signal.
    Pilot me PILOT_CALL_CAP, baaki sab UNLIMITED_QUOTA.
    """
    key, _ = voice_plan_parts(plan_id)
    if key == "voice_pilot":
        return PILOT_CALL_CAP
    if key:
        return UNLIMITED_QUOTA
    return 0


# Legacy aliases — koi bhi old import toot na jaye
PACK_SIZE = 1  # no longer meaningful; kept for import compat
PLAN_LEADS: dict[str, int] = (
    {info["plan_monthly"]: UNLIMITED_QUOTA for info in BANDS.values()}
    | {info["plan_annual"]: UNLIMITED_QUOTA for info in BANDS.values()}
    | {"voice_pilot": PILOT_CALL_CAP}
)
