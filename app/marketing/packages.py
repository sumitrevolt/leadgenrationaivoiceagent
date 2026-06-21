"""
Marketing-first pricing packages — platform ke PUBLIC pricing ka source-of-truth.
==================================================================================

Positioning (June 2026, CLARIFIED): hum DO alag products banate hain —
  1. **AI Automated Marketing** (MAIN product, yeh pricing usi ki hai) — local
     businesses ke liye posts/GBP/festivals/posters/WhatsApp/reviews, sab
     /app/marketing me built. Advanced tier me **AI voice agent ek FEATURE**
     hai: inquiry auto-callback, lead qualification calls, missed-call follow-ups.
  2. **AI Voice Calling Agent** (ALAG standalone product) — full AI telecaller
     (outbound/DLT-gated); iski pricing **`voice_packages.py`** me (page /voice-agent),
     model = flat-monthly per niche-band A/B/C (ADR-009; updated 2026-06-12). Yahan NAHI.

Prices (research-revised 2026-06-11, ADR-009): Starter ₹1,199 · Growth ₹2,999 ·
Advanced ₹6,999 (anchors: Dhanda ₹7,999/yr, Predis Lite ~₹2,700/mo social-only,
agency retainer ₹10-25k/mo). Yearly = 10x monthly (2 mahine FREE).

USP (marketing product ka): koi bhi Indian marketing competitor (Dhanda
₹7,999/yr, AdBanao, Predis) AI voice-callback FEATURE nahi deta — isliye
"advanced" tier highlight hai. "Bundle/dono ek saath" framing MAT use karo.

Consumers:
  - GET /api/marketing/packages (PUBLIC — landing page JS fetch karta hai)
  - frontend/website/index.html pricing section (static fallback same data)

Pure-data module — koi heavy import nahi (import-safe, kabhi raise nahi karta).
"""

from __future__ import annotations

PACKAGES: list[dict] = [
    {
        "key": "starter",
        "name": "Marketing Starter",
        "tagline": "Roz ka content + Google presence — sab AI se, aapka time zero. 100% marketing-only plan.",
        "price_inr_month": 1199,
        "price_inr_year": 11990,  # 10x monthly = 2 mahine FREE (research: 16.7% standard, churn ~27% kam)
        "annual_note": "Saal bhar ka ek saath: ₹11,990 (2 mahine FREE)",
        "price_note": "100% marketing-only — koi calling charge nahi · roz ke ₹40 se kam me poora marketing setup",
        "marketing_only": True,
        "features": [
            "Roz AI social posts — Hinglish caption + hashtags (39 niches, aapki industry ke hisaab se)",
            "Branded post frames — aapka logo + business naam har post pe",
            "Customer portal — 1-click copy + WhatsApp/Insta share (roz subah ~7 baje content ready)",
            "Festival calendar auto — Diwali, Holi, Rakhi, Independence Day sab covered",
            "Tyohar/offer posts — sale day ke liye ready creatives + captions",
            "Google Business Profile audit (0–100 score) + top 5 fix suggestions",
            "Google reviews ke Hinglish reply drafts — copy-paste, rating bachao",
            "4 branded posters/mo — naam, phone, offer ke saath (SVG, print-ready)",
            "WhatsApp content pack — broadcast messages + status updates ready",
            "UPI Scan & Pay QR card — counter/display ke liye branded",
            "Hashtag suggestions har post ke saath",
            "Post approval workflow — publish se pehle aapki OK (portal me)",
            "Onboarding checklist + customer dashboard (leads, content, bills)",
            "GST invoice download portal se",
            "100% marketing-only — koi calling charge / minute limit nahi",
        ],
        "highlight": False,
        "badge": "",
    },
    {
        "key": "growth",
        "name": "Growth",
        "tagline": "Poora marketing engine — content, competitor aur leads sab automatic. 100% marketing-only plan.",
        "price_inr_month": 2999,
        "price_inr_year": 29990,  # 2 mahine FREE
        "annual_note": "Saal bhar ka ek saath: ₹29,990 (2 mahine FREE)",
        "price_note": "100% marketing-only — koi calling charge nahi · sab kuch Starter ka + growth tools",
        "marketing_only": True,
        "features": [
            "Starter ke saare features included",
            "Unlimited posters + festival creatives — jitne chahiye utne",
            "AI image generation + Complete Post one-shot (caption + hashtags + image)",
            "Post variations A/B — ek idea se 2–4 alag versions",
            "Content calendar + scheduler — mahine bhar ka plan + festival auto-schedule",
            "Competitor analysis — unki posts/strengths dekho, gaps exploit karo",
            "Mini-site `/b/aapka-slug` — bio link + digital card + booking page",
            "Website enquiry widget — 1-line script, form seedha dashboard me",
            "AI website chatbot — FAQ + lead capture (widget mode)",
            "Database reactivation — purane customers ke liye win-back campaigns",
            "WhatsApp drip nurture — naye leads ko spaced follow-up messages",
            "Review kit — khush customer ko Google review, unhappy ko private feedback",
            "Team lead routing — 2–5 members round-robin + WhatsApp handoff",
            "CRM sync (Zoho/HubSpot) + programmable webhooks (lead/call events)",
            "Ads copy pack + Reels script drafts + sentiment/hashtag research",
            "Catalog + UPI payment links + referral program tools",
            "Monthly marketing report — kya chala, kya nahi, agla mahina kya karein",
            "Customer 2FA + hot leads dashboard",
        ],
        "highlight": False,
        "badge": "",
    },
    {
        "key": "advanced",
        "name": "Advanced AI Agent",
        "tagline": "Growth ka poora marketing + AI Voice Agent feature — har inquiry ko AI khud call kare. India me sirf yahan.",
        "price_inr_month": 6999,
        "price_inr_year": 69990,  # 2 mahine FREE
        "annual_note": "Saal bhar ka ek saath: ₹69,990 (2 mahine FREE)",
        "price_note": "telephony usage included up to 500 min/mo",
        "marketing_only": False,
        "features": [
            "Growth ke saare features included",
            "AI Voice Agent — har website/GBP inquiry ko ~2-minute me AI call (insaan jaisi Hindi awaaz)",
            "Lead qualification — budget, timeline, interest score AI capture karta hai",
            "Appointment booking — AI calendar slots offer + confirm karta hai",
            "Missed-call auto-callback (DID active hone par) — koi enquiry miss nahi",
            "500 calling minutes/mo included — top-up packs (100/250/500 min) available",
            "Weekly 50 follow-up calls — purani leads garam rakho",
            "Sab call transcripts + AI summary aapke dashboard me",
            "Post-call AI qualification — interest score + next-action draft",
            "Speed-to-lead SLA badge — kitni der me pehli call hui, track karo",
            "Multi-lingual — Hindi, Hinglish, English (aur regional jahan script ho)",
            "TRAI-compliant AI disclosure greeting har call pe",
            "Calls + leads ek hi portal — marketing content bhi, voice bhi",
            "Minute usage tracker — kitna use hua, kitna bacha, renewal date",
        ],
        "highlight": True,
        "badge": "🚀 India me sirf hamare paas",
    },
]


def get_packages(include_trial: bool = False) -> list:
    """Public pricing packages (list of dicts) — landing page + API ke liye.

    Default (include_trial=False) = pehle jaisa EXACT 3 paid packages (backward
    compatible — existing consumers untouched). include_trial=True pe FREE trial
    package list ke aage add hota hai (additive only).
    """
    if include_trial:
        return [dict(TRIAL_PACKAGE)] + PACKAGES
    return PACKAGES


# --------------------------------------------------------------------------- #
# FREE TRIAL (₹0, 7 din, marketing-lite) — funnel-leak fix: paid-only signup
# se hesitant SMBs nikal jaate the. Trial = ZERO payment, limited features.
# --------------------------------------------------------------------------- #
TRIAL_DAYS = 7

TRIAL_PACKAGE: dict = {
    "key": "trial",
    "name": "7-Din FREE Trial",
    "tagline": "Bina paise diye AI marketing try karo — card bhi nahi chahiye.",
    "price_inr_month": 0,
    "price_note": "₹0 — 7 din ka free trial, koi card/payment nahi. Pasand aaye to Starter se shuru karo.",
    "marketing_only": True,
    "trial": True,
    "trial_days": TRIAL_DAYS,
    "features": [
        "5 AI social posts — Hinglish caption + hashtags, copy/share ready",
        "1 Google Business Profile audit (0–100 score + fix list)",
        "Website lead-capture widget — enquiry form (+ optional AI chat mode)",
        "Mini-site preview link (`/b/aapka-slug`) + bio link",
        "Branded post frame sample — logo + business naam",
        "Customer login portal — 7 din full dashboard access",
        "WhatsApp content — basic broadcast/status pack",
        "Onboarding checklist — setup steps portal me",
        "1-click copy + WhatsApp share har post pe",
        "Koi card/payment nahi — pasand aaye to Starter ₹1,199/mo se shuru",
        "Voice calling nahi (Advanced tier me AI callback milta hai)",
    ],
    "highlight": False,
    "badge": "🎁 FREE",
}


# --------------------------------------------------------------------------- #
# VOICE-MINUTE TOP-UP PACKS (Advanced tier ke liye; period-end pe EXPIRE — research:
# rollover rare, revenue-recognition+usage reasons). Effective rate included-minute
# (₹12/min @500) se UPAR, taaki heavy users ko upgrade/renew sasta lage (upsell lever).
# NOTE: prices research-pattern se set (₹15-18/min) — user adjust kar sakta hai.
# --------------------------------------------------------------------------- #
TOPUP_PACKS: list[dict] = [
    {"key": "topup_100", "minutes": 100, "price_inr": 1499, "label": "100 min Top-up"},
    {"key": "topup_250", "minutes": 250, "price_inr": 3499, "label": "250 min Top-up"},
    {"key": "topup_500", "minutes": 500, "price_inr": 5999, "label": "500 min Top-up"},
]


def get_topup_packs() -> list[dict]:
    return [dict(p) for p in TOPUP_PACKS]


def topup_pack(key: str) -> dict:
    """Pack by key ('topup_100') — {} if unknown. Kabhi raise nahi."""
    k = (key or "").strip().lower()
    for p in TOPUP_PACKS:
        if p["key"] == k:
            return dict(p)
    return {}


def get_trial_package() -> dict:
    """Trial package ka copy (mutation-safe)."""
    return dict(TRIAL_PACKAGE)


def trial_expiry_iso(days: int = TRIAL_DAYS) -> str:
    """Aaj se `days` din baad ka ISO timestamp (UTC) — client record ke liye."""
    try:
        from datetime import datetime, timedelta, timezone

        return (datetime.now(timezone.utc) + timedelta(days=max(1, int(days)))).isoformat()
    except Exception:
        return ""


def trial_status(client: dict | None) -> dict:
    """Client record se trial state — {trial, active, expired, days_left, expires_at}.

    Pure helper (no DB/middleware) — customer portal + admin UI ke liye.
    Kabhi raise nahi karta.
    """
    out = {"trial": False, "active": False, "expired": False, "days_left": 0, "expires_at": None}
    try:
        c = client or {}
        if not c.get("trial"):
            return out
        out["trial"] = True
        exp_raw = str(c.get("trial_expires") or "").strip()
        out["expires_at"] = exp_raw or None
        if not exp_raw:
            return out
        from datetime import datetime, timezone

        exp_s = exp_raw[:-1] + "+00:00" if exp_raw.endswith("Z") else exp_raw
        exp = datetime.fromisoformat(exp_s)
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        delta = exp - now
        if delta.total_seconds() > 0:
            out["active"] = True
            out["days_left"] = max(1, delta.days + (1 if delta.seconds > 0 else 0))
        else:
            out["expired"] = True
    except Exception:
        pass
    return out
