"""
Marketing-first pricing packages — platform ke PUBLIC pricing ka source-of-truth.
==================================================================================

Positioning (June 2026, merged marketing plan):
  1. **AI Marketing Automation** (MAIN product, starter + growth ko merge karke)
     — local businesses ke liye posts/GBP/festivals/posters/WhatsApp/reviews,
     lead capture, reactivation, CRM sync, aur automation. Public pricing me yahi
     single marketing plan dikhata hai.
  2. **AI Voice Calling Agent** (ALAG standalone product) — full AI telecaller
     (outbound/DLT-gated); iski pricing **`voice_packages.py`** me (page /voice-agent),
     model = flat-monthly per niche-band A/B/C (ADR-009; updated 2026-06-12). Yahan NAHI.

Prices (research-revised 2026-06-25): Marketing Automation ₹1,999 · Growth
(legacy/internal hidden) ₹2,999 · Advanced Voice Agent ₹5,999 (anchors: local SMB
budget sweet spot, voice as premium upsell). Yearly = 10x monthly (2 mahine FREE).

USP (marketing product ka): koi bhi Indian marketing competitor (Dhanda
₹7,999/yr, AdBanao, Predis) AI voice-callback FEATURE nahi deta — isliye
"advanced" tier highlight hai. "Bundle/dono ek saath" framing MAT use karo.

Consumers:
  - GET /api/marketing/packages (PUBLIC — landing page JS fetch karta hai)
  - frontend/website/index.html pricing section (static fallback same data)

Pure-data module — koi heavy import nahi (import-safe, kabhi raise nahi karta).
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Main plan (AI Marketing Automation) feature CATALOG — grouped for the pricing
# page's collapsible display. Flat `features` list isi se DERIVE hoti hai
# (single source-of-truth → koi drift nahi). HAR bullet customer portal me ek
# LIVE self-serve tool se backed hai (app/api/customer_marketing_studio.py
# `_TOOLS` — live route + UI card) — koi fabricated/undelivered claim nahi.
# --------------------------------------------------------------------------- #
_STARTER_CORE: list[str] = [
    "Roz AI social posts — Hinglish caption + hashtags (39 niches); portal me draft ready, aap approve karke share",
    "Branded post frames — aapka logo + business naam har post pe",
    "Customer portal — 1-click copy + WhatsApp/Insta share (subah drafts target; aap control me)",
    "Festival calendar auto — Diwali, Holi, Rakhi, Independence Day sab covered",
    "Tyohar/offer posts — sale day ke liye ready creatives + captions",
    "Google Business Profile audit (0–100 score) + top 5 fix suggestions",
    "Google reviews ke Hinglish reply drafts — copy-paste, rating bachao",
    "4 branded posters/mo — naam, phone, offer ke saath (SVG, print-ready)",
    "WhatsApp content pack — broadcast messages + status updates ready (1-click send)",
    "Lead capture widget — 1-line script, form seedha dashboard me",
    "AI website chatbot — FAQ + lead capture (widget mode)",
    "CRM sync (Zoho/HubSpot) + webhooks — aapke credentials connect karne ke baad",
    "WhatsApp drip nurture — spaced follow-up DRAFTS (1-click send; bulk auto-send OFF, ban-safe)",
    "Database reactivation — purane customers ke liye win-back campaign DRAFTS",
    "Competitor analysis + monthly marketing report — kya chala, kya nahi",
    "Referral tools + Ads copy pack (headlines/creatives DRAFT — Meta/Google ads management nahi) + Reels script drafts",
    "UPI Scan & Pay QR card — counter/display ke liye branded",
    "Mini-site `/b/aapka-slug` — bio link + digital visiting card + booking page (ek link sab kuch)",
    "Appointment booking page — customer khud calendar slot book kare, aapko auto-confirmation",
    "AI image generation + Complete Post one-shot — caption + hashtags + AI image ek click me",
    "AI video ads (Reels/Shorts) — free stack pe generate; ready + approve ke baad 1-click share (koi extra charge nahi)",
    "Har post pe 1-click WhatsApp/copy share — approve karke seedha bhejo (aap control me; auto-post/bulk-send nahi, ban-safe)",
    "Content calendar + scheduler — mahine bhar ka plan + festival auto-schedule",
    "Post variations A/B — ek idea se 2–4 alag versions, jo chale wo chuno",
    "Review kit — khush customer ko Google review, naraz ko private feedback (rating bachao)",
    "Team lead routing — members round-robin + WhatsApp handoff (team setup ke baad)",
    "Product/service catalog + UPI payment links — share karo, customer wahi se pay kare",
    "Hot leads dashboard — score ke hisaab se priority leads upar, pehle kisko follow-up karein",
    "Per-client blog page — programmatic SEO, Google pe organic reach badhao",
    "Sentiment + hashtag research — kya trend kar raha, kaunsa tone chal raha",
    "Customer 2FA (TOTP) login security — account safe rakho",
    "Post approval workflow — publish se pehle aapki OK (portal me)",
    "GST invoice download portal se",
]

# 40 NAYE features (2026-06-29) — sab pehle se customer portal me LIVE (Studio _TOOLS).
_STARTER_FEATURE_GROUPS: list[dict] = [
    {
        "title": "Core Marketing Automation",
        "icon": "⚙️",
        "items": _STARTER_CORE,
    },
    {
        "title": "Content & Creative",
        "icon": "🎨",
        "items": [
            "Carousel maker — Instagram multi-slide carousel posts (SVG ready)",
            "Meme generator — niche-relevant Hinglish memes, viral-ready",
            "Testimonial poster — customer review → branded poster + caption",
            "Content repurpose — 1 topic/blog → 7 alag formats (post/reel/thread…)",
            "Reel/Ad voiceover script — Hinglish VO record karne ke liye ready",
            "YouTube metadata — title + tags + description optimized",
            "Instagram 9-grid planner — cohesive feed layout",
            "Story highlights planner — categories + cover ideas",
            "Regional language post — caption Hindi/Marathi/Tamil/Telugu… me convert",
            "Evergreen post ideas — kabhi bhi repost-able content bank",
        ],
    },
    {
        "title": "Local SEO & AI Discovery",
        "icon": "📍",
        "items": [
            "Get-Found-by-AI (AEO) — ChatGPT/Gemini/Perplexity pe dikhne ka checklist",
            "Schema markup generator — LocalBusiness JSON-LD (Google rich results)",
            "FAQ page builder — website ke liye ready Q&A",
            "'Service in city' SEO pages — local search ke liye landing pages",
            "Listings / NAP consistency check — directories pe naam/phone/address audit",
            "DIY rank-check guide — Google ranking khud track karne ka tareeka",
            "Conversion tracking setup — GA4 / Meta pixel / UTM checklist",
        ],
    },
    {
        "title": "Leads & Conversion",
        "icon": "🧲",
        "items": [
            "AI Inbox — saari inquiries intent + urgency ke hisaab se sorted",
            "Lead magnet builder — free guide/checklist se leads capture",
            "Speed-to-lead instant reply — naya lead aate hi ready message",
            "Ad budget planner — niche + goal ke hisaab se daily ad spend SUGGESTION (spend/campaign management plan me nahi)",
            "Lost-lead reasons + fix — kyu convert nahi hua, kaise sudhaarein",
            "Newsletter builder — monthly email newsletter ka plan + content outline",
            "Quote / estimate draft — inquiry se professional price quote",
            "ROI calculator — spend vs revenue estimate dikhaao",
        ],
    },
    {
        "title": "Reviews & Reputation",
        "icon": "⭐",
        "items": [
            "Bad-review rescue — naraz review ka polite damage-control reply",
            "Reviews widget — website pe Google reviews showcase",
            "Case study generator — customer success story (social-proof content)",
            "NPS / CSAT survey builder — customer feedback survey ready",
        ],
    },
    {
        "title": "Sales & Retention",
        "icon": "🤝",
        "items": [
            "Objection handler — 'mehenga hai / sochta hoon' ka best reply",
            "Loyalty program design — points + rewards gamified plan",
            "Coupon generator — code + expiry + WhatsApp text",
            "Customer reminders — appointment/renewal/payment ke auto messages",
            "Complaint recovery flow — angry customer ko wapas khush karna",
            "UGC request kit — customers se photo/video testimonials maango (influencer outreach / creator management plan me nahi)",
        ],
    },
    {
        "title": "Planning & Coaching",
        "icon": "🚀",
        "items": [
            "AI Growth Coach — har hafte 3 high-impact action suggestions",
            "Next-Best-Action — aaj kya karna hai, priority task list",
            "Daily Owner Brief — business ka ek-nazar daily summary",
            "Customer avatar — ideal buyer profile + targeting guidance",
            "Best time to post/call/message — niche-wise optimal timing",
        ],
    },
    {
        # Hands-free: background me AUTO-DRAFT (scheduler/event-driven). Outbound
        # send ban-safe OFF — customer/admin 1-click se bhejta. Surface, fabricate nahi.
        "title": "Hands-Free Automations",
        "icon": "🤖",
        "items": [
            "Appointment/booking reminders — booking se pehle auto WhatsApp/SMS reminder DRAFT (no-show kam)",
            "Repeat-service due reminders — 'aapki service due hai' auto recurring nudge DRAFT",
            "Naye Google review pe auto AI reply-draft — review aate hi ready jawab",
            "Brand & review mention monitoring (weekly) — net pe aapke naam ka zikr + reply drafts",
            "Local Google rank tracking (weekly) — aapki keywords ki ranking auto-track + report",
            "Birthday/anniversary auto-wishes — customers ko personalized wish DRAFT",
            "Monthly customer newsletter — har mahine email newsletter auto-DRAFT",
            "Cold-lead auto win-back — thande pade leads ko wapas laane ke DRAFTS",
            "Multi-channel follow-up cadence — WhatsApp+email+SMS sequenced auto-DRAFT advance",
            "Lifecycle nurture journeys — inquiry→engaged→loyal event-based auto-DRAFTS",
            "Hot-lead instant alert — naya high-intent lead aate hi turant aapko notify",
            "Sales deal auto next-action — har deal ka agla step auto-suggest",
            "Signup→paid nurture — naye signup ko paying customer banane ki auto-sequence DRAFT",
            "Email deliverability auto-watch — aapki emails spam me na jaayein (SPF/DMARC/blacklist auto-check)",
            "Har inquiry auto-log + source attribution — kaunsa lead kahan se aaya, timeline auto-record",
            "Weekly AI-staff work report — 'is hafte aapki AI team ne kya kiya' auto-summary",
            "Evergreen content auto-repost — purane top posts auto-freshen + re-queue DRAFT",
            "NPS/CSAT auto-survey — customer satisfaction survey periodic auto-DRAFT",
            "Stale-inquiry auto-followup — 24h koi reply nahi → auto nudge DRAFT",
            "Roz-subah Owner Brief auto-tayar — naye leads + ready content + aaj ke kaam, bina click",
        ],
    },
]

# Flat list (backward-compat: landing page, billing sync, tests) = groups se derive.
_STARTER_FEATURES: list[str] = [it for g in _STARTER_FEATURE_GROUPS for it in g["items"]]

PACKAGES: list[dict] = [
    {
        "key": "starter",
        "name": "AI Marketing Automation",
        "tagline": "Content, leads, reviews aur automation — sab ek plan me. 100% marketing-only.",
        "price_inr_month": 1999,
        "price_inr_year": 19990,  # 10x monthly = 2 mahine FREE
        "annual_note": "Saal bhar ka ek saath: ₹19,990 (2 mahine FREE)",
        "price_note": "100% marketing automation — koi calling charge nahi · content + leads + CRM sab ek saath",
        "marketing_only": True,
        "feature_groups": _STARTER_FEATURE_GROUPS,
        "features": _STARTER_FEATURES,
        "highlight": True,
        "badge": "POPULAR",
    },
    {
        "key": "growth",
        "name": "Growth",
        "tagline": "Legacy/internal only — hidden from public pricing, backward compatibility ke liye.",
        "price_inr_month": 2999,
        "price_inr_year": 29990,  # 2 mahine FREE
        "annual_note": "Saal bhar ka ek saath: ₹29,990 (2 mahine FREE)",
        "price_note": "Legacy/internal plan — public pricing me show nahi hota",
        "marketing_only": True,
        "public": False,
        "features": [
            "Legacy Growth plan — starter automation ka older split",
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
        # Product-truth (ADR-009): this is Marketing Product-1 Advanced with an
        # AI-callback FEATURE — NOT a "two products bundled" USP. Standalone Voice
        # Agent pricing lives in voice_packages.py (/voice-agent).
        "name": "Advanced Marketing",
        "tagline": "Poora marketing + AI inquiry-callback FEATURE (500 min/mo). Standalone Voice Agent alag product hai.",
        "price_inr_month": 5999,
        "price_inr_year": 59990,  # 2 mahine FREE
        "annual_note": "Saal bhar ka ek saath: ₹59,990 (2 mahine FREE)",
        "price_note": "Main plan ka poora marketing + 500 callback min/mo included (top-up packs available)",
        "marketing_only": False,
        "features": [
            "Main plan (₹1,999) ke SAARE marketing features included — content, GBP, reviews, leads, CRM, mini-site, sab",
            "AI inquiry callback FEATURE — website/GBP inquiry ko ~2-minute me AI call (Hindi awaaz)",
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
            "Minute usage tracker — kitna use hua, kitna bacha, renewal date",
        ],
        "highlight": True,
        "badge": "ADVANCED",
    },
]


def get_packages(include_trial: bool = False) -> list:
    """Public pricing packages (list of dicts) — landing page + API ke liye.

    Default (include_trial=False) = pehle jaisa EXACT 3 paid packages (backward
    compatible — existing consumers untouched). Public endpoints ke liye
    `get_public_packages()` use karo. include_trial=True pe FREE trial package
    list ke aage add hota hai (additive only).
    """
    if include_trial:
        return [dict(TRIAL_PACKAGE)] + PACKAGES
    return PACKAGES


def get_public_packages(include_trial: bool = False) -> list:
    """Public-facing pricing packages.

    Starter (merged marketing automation) + Advanced voice plan return hote hain.
    Legacy/internal Growth split hidden rehta hai taaki backward compatibility
    retain ho aur public pricing simple rahe.
    """
    out = []
    if include_trial:
        out.append(dict(TRIAL_PACKAGE))
    out.extend(dict(p) for p in PACKAGES if p.get("public", True))
    return out


def get_starter_price_inr() -> int:
    """Starter plan ka monthly ₹ — single source (₹1,999). Hardcoded 1999
    fallbacks kahin bhi use mat karo — isi ko call karo (2026-08-01 audit fix:
    admin/customer dashboard builders me scattered literals thhe)."""
    try:
        for p in PACKAGES:
            if str(p.get("key") or "").strip().lower() == "starter":
                price = int(p.get("price_inr_month") or 0)
                if price > 0:
                    return price
    except Exception:
        pass
    return 1999


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
    "price_note": "₹0 — 7 din ka free trial, koi card/payment nahi. Pasand aaye to AI Marketing Automation ₹1,999/mo se shuru karo.",
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
        "Koi card/payment nahi — pasand aaye to AI Marketing Automation ₹1,999/mo se shuru",
        "Voice calling nahi (Advanced Voice Agent me AI callback milta hai)",
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
