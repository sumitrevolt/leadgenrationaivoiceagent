"""
Marketing-first pricing packages — platform ke PUBLIC pricing ka source-of-truth.
==================================================================================

Positioning (June 2026 pivot): product = "AI Automated Marketing" for local
businesses (Dhanda-style posts/GBP/festivals/posters/WhatsApp/reviews — sab
/app/marketing me built hai). AI voice agent ab marketing ka KILLER helper hai:
website/GBP inquiry auto-callback, lead qualification calls, missed-call
follow-ups.

USP: koi bhi Indian competitor (Dhanda ₹7,999/yr, AdBanao, Predis) voice-calling
+ marketing EK package me nahi deta — isliye "advanced" tier highlight hai.

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
        "price_inr_month": 999,
        "price_note": "100% marketing-only — koi calling charge nahi · roz ke ₹33 me poora setup (billed annually or ₹1,299/mo)",
        "marketing_only": True,
        "features": [
            "AI social media posts + festival calendar (Diwali, Holi, sab covered)",
            "Google Business Profile audit + top fixes (0-100 score)",
            "Reviews ke ready Hinglish replies — copy-paste karo",
            "4 festival/offer posters har mahine (aapke naam + number ke saath)",
            "WhatsApp content pack — broadcast + status messages ready",
            "UPI 'Scan & Pay' QR Card generator for counter",
        ],
        "highlight": False,
        "badge": "",
    },
    {
        "key": "growth",
        "name": "Growth",
        "tagline": "Poora marketing engine — content, competitor aur leads sab automatic. 100% marketing-only plan.",
        "price_inr_month": 2499,
        "price_note": "100% marketing-only — koi calling charge nahi · sab kuch Starter ka + growth tools",
        "marketing_only": True,
        "features": [
            "Starter ke saare features included",
            "Unlimited posters — jitne chahiye utne banao",
            "Content calendar auto — mahine bhar ka plan ready",
            "Competitor analysis — unki strengths copy, gaps exploit",
            "Website lead-capture form setup (inquiries seedha dashboard me)",
            "Database reactivation (win-back campaigns for old customers)",
            "WhatsApp drip nurture sequences for new leads",
            "Monthly marketing report — kya chala, kya nahi",
        ],
        "highlight": False,
        "badge": "",
    },
    {
        "key": "advanced",
        "name": "Advanced AI Agent",
        "tagline": "Marketing + ek AI jo aapke har inquiry ko KHUD call kare — India me sirf yahan.",
        "price_inr_month": 5999,
        "price_note": "telephony usage included up to 500 min/mo",
        "marketing_only": False,
        "features": [
            "Growth ke saare features included",
            "AI Voice Agent — har website/GBP inquiry ko 2-minute me AI call (Hindi, insaan jaisi awaaz)",
            "Lead qualification + appointment booking — AI khud karta hai",
            "Missed-call auto-callback + WhatsApp auto-reply — koi customer chhoot-ta nahi",
            "Weekly 50 follow-up calls — purani leads bhi garam rehti hain",
            "Sab call transcripts aapke dashboard me",
            "Multi-lingual calling supports (Hindi, Hinglish, English, etc.)",
        ],
        "highlight": True,
        "badge": "🚀 India me sirf hamare paas",
    },
]


def get_packages() -> list:
    """Public pricing packages (list of dicts) — landing page + API ke liye."""
    return PACKAGES
