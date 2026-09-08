"""
gbp_audit.py — Dhanda-style Google Business Profile self-audit (NO Google API).
===============================================================================

Business owner 16 sawalon ke jawab deta hai (multiple-choice) → weighted
0-100 score + grade + per-area breakdown + top-5 concrete Hinglish fixes.

PURE LOGIC — koi LLM nahi, koi network nahi, kabhi raise nahi karta.
Missing/galat answers ko worst-case (score 0) maana jaata hai — audit
conservative rehta hai, owner motivated rehta hai.
"""

from __future__ import annotations

import re
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# ============================================================================ #
# 16 audit questions — {id, q (Hinglish), weight, options:[{label, score 0-1}]}
# weight: 3 = ranking-critical, 2 = strong signal, 1 = nice-to-have
# Options BEST → WORST order me hain (index 0 = best) — par score hi truth hai.
# ============================================================================ #

AUDIT_QUESTIONS: list[dict[str, Any]] = [
    {
        "id": "claimed",
        "q": "Kya aapne apna Google Business Profile claim + verify kiya hai?",
        "weight": 3,
        "options": [
            {"label": "Haan, claimed aur verified hai", "score": 1.0},
            {"label": "Claim kiya hai par verify pending hai", "score": 0.4},
            {"label": "Nahi / pata nahi", "score": 0.0},
        ],
    },
    {
        "id": "description",
        "q": "Business description kaisa hai? (750 characters tak likh sakte ho)",
        "weight": 2,
        "options": [
            {
                "label": "Poora 600-750 chars, local keywords (area + service) ke saath",
                "score": 1.0,
            },
            {"label": "Likha hai par chhota / bina keywords ke", "score": 0.5},
            {"label": "Khali hai ya 1-2 line hi hai", "score": 0.0},
        ],
    },
    {
        "id": "categories",
        "q": "Primary category bilkul sahi hai + 2-3 secondary categories lagi hain?",
        "weight": 3,
        "options": [
            {"label": "Haan, primary perfect + secondaries bhi hain", "score": 1.0},
            {"label": "Primary sahi hai par secondary nahi lagayi", "score": 0.6},
            {"label": "Pata nahi / shayad galat category hai", "score": 0.0},
        ],
    },
    {
        "id": "photos",
        "q": "Profile par kitne photos hain aur kitne fresh hain?",
        "weight": 3,
        "options": [
            {"label": "25+ photos, last 30 din me naye bhi dale", "score": 1.0},
            {"label": "10-25 photos, par kaafi purane", "score": 0.5},
            {"label": "10 se kam photos", "score": 0.2},
            {"label": "Sirf logo / koi photo nahi", "score": 0.0},
        ],
    },
    {
        "id": "posts",
        "q": "GBP posts (offers/updates) kitni baar daalte ho?",
        "weight": 2,
        "options": [
            {"label": "Har hafte kam-se-kam ek post", "score": 1.0},
            {"label": "Mahine me 1-2 baar", "score": 0.5},
            {"label": "Kabhi-kabhaar / kabhi nahi", "score": 0.0},
        ],
    },
    {
        "id": "reviews_count",
        "q": "Total kitne Google reviews hain?",
        "weight": 3,
        "options": [
            {"label": "50+ reviews", "score": 1.0},
            {"label": "20-50 reviews", "score": 0.7},
            {"label": "5-20 reviews", "score": 0.4},
            {"label": "5 se kam", "score": 0.0},
        ],
    },
    {
        "id": "rating",
        "q": "Average star rating kya hai?",
        "weight": 3,
        "options": [
            {"label": "4.5+ stars", "score": 1.0},
            {"label": "4.0-4.5 stars", "score": 0.7},
            {"label": "3.0-4.0 stars", "score": 0.3},
            {"label": "3.0 se neeche", "score": 0.0},
        ],
    },
    {
        "id": "review_replies",
        "q": "Reviews ka reply kitni jaldi aur kitne % ko dete ho?",
        "weight": 3,
        "options": [
            {"label": "Sab reviews ka reply 24 ghante me", "score": 1.0},
            {"label": "Zyada-tar ka reply, par der se", "score": 0.5},
            {"label": "Sirf negative ya kabhi-kabhi", "score": 0.2},
            {"label": "Reply karte hi nahi", "score": 0.0},
        ],
    },
    {
        "id": "qna",
        "q": "Q&A section me khud ke seeded sawal-jawab hain?",
        "weight": 1,
        "options": [
            {"label": "Haan, 5+ common Q&A khud daale hain", "score": 1.0},
            {"label": "1-2 hain", "score": 0.5},
            {"label": "Khali hai / random logon ke galat jawab pade hain", "score": 0.0},
        ],
    },
    {
        "id": "services",
        "q": "Products/Services section poora bhara hai (naam + price-range + photo)?",
        "weight": 2,
        "options": [
            {"label": "Haan, sab services photo + price ke saath", "score": 1.0},
            {"label": "Kuch services likhi hain, adhura", "score": 0.5},
            {"label": "Section khali hai", "score": 0.0},
        ],
    },
    {
        "id": "hours",
        "q": "Business hours sahi hain + holiday/special hours bhi set hain?",
        "weight": 2,
        "options": [
            {"label": "Haan, regular + holiday hours dono updated", "score": 1.0},
            {"label": "Regular hours hain, holiday hours nahi", "score": 0.6},
            {"label": "Hours galat/khali hain", "score": 0.0},
        ],
    },
    {
        "id": "contact",
        "q": "Phone number aur website link dono lage hain aur chalu hain?",
        "weight": 2,
        "options": [
            {"label": "Dono lage hain aur working", "score": 1.0},
            {"label": "Sirf phone hai, website nahi", "score": 0.5},
            {"label": "Dono missing/galat", "score": 0.0},
        ],
    },
    {
        "id": "booking",
        "q": "Booking/appointment link laga hai (Calendly/WhatsApp link bhi chalega)?",
        "weight": 1,
        "options": [
            {"label": "Haan, booking link live hai", "score": 1.0},
            {"label": "Nahi laga", "score": 0.0},
        ],
    },
    {
        "id": "geo_photos",
        "q": "Photos geo-tagged hain (location-on camera se khinchi hui)?",
        "weight": 1,
        "options": [
            {"label": "Haan, zyada-tar geo-tagged hain", "score": 1.0},
            {"label": "Pata nahi", "score": 0.3},
            {"label": "Nahi", "score": 0.0},
        ],
    },
    {
        "id": "nap",
        "q": "NAP consistency — Name/Address/Phone har jagah (website, JustDial, directories) SAME hai?",
        "weight": 3,
        "options": [
            {"label": "Haan, sab jagah bilkul same", "score": 1.0},
            {"label": "Thoda alag hai kahin-kahin", "score": 0.4},
            {"label": "Check hi nahi kiya / alag-alag hai", "score": 0.0},
        ],
    },
    {
        "id": "messaging",
        "q": "GBP messaging/chat on hai aur koi turant reply karta hai?",
        "weight": 1,
        "options": [
            {"label": "On hai, replies turant jaate hain", "score": 1.0},
            {"label": "On hai par reply late hota hai", "score": 0.5},
            {"label": "Off hai / pata nahi", "score": 0.0},
        ],
    },
]

# Concrete Hinglish fix-action per area (lowest scorers me se top-5 dikhte hain)
_FIXES: dict[str, str] = {
    "claimed": "Sabse pehle business.google.com par jaake profile claim karo aur postcard/phone se verify karwao — bina iske kuch bhi rank nahi hoga.",
    "description": "Aaj hi 600-750 characters ka description likho — apna area + service keywords daalo (jaise 'Andheri me rooftop solar installation').",
    "categories": "Google par apne top competitor ka profile kholo, unki primary category dekho, apni wahi sahi karo + 2-3 secondary categories add karo.",
    "photos": "Is hafte 5 naye photos dalo (kaam karte hue, team, before/after) — phir har hafte 2-3 ka routine banao.",
    "posts": "Har Somvaar ek GBP post daalo — offer ya kaam ka update, photo ke saath. 10 minute ka kaam hai, freshness signal milta hai.",
    "reviews_count": "Counter/bill par review QR-code rakho aur har khush customer se turant Google review maango — target: har hafte 3 naye reviews.",
    "rating": "Naraz customers ko pehle personally call karke solve karo, phir review update karne ki request karo — naye 5-star reviews se average upar khinch jaayega.",
    "review_replies": "Aaj hi SAB purane reviews ka reply likho (negative ka sabse pehle), aur aage 24-ghante-reply ka rule banao.",
    "qna": "Q&A me khud 5-6 common sawal poochho aur jawab do (price-range, timing, area-coverage) — objections pehle hi cut ho jaate hain.",
    "services": "Products/Services section me har service ka naam + price-range + ek photo dalo — ye search results me directly dikhta hai.",
    "hours": "Hours abhi check karke sahi karo + agle 3 mahine ke holidays ke special hours set karo — 'galat hours' wali negative review free me aati hai.",
    "contact": "Working phone number + website (ya Instagram/WhatsApp link) profile par lagao — bina iske lead jaane ka rasta hi nahi.",
    "booking": "Free Calendly ya WhatsApp wa.me link ko booking-link me lagao — call chhoot bhi jaaye to lead capture hota hai.",
    "geo_photos": "Phone camera me location ON karke shop/site ki naye photos kheencho aur wahi upload karo — free local-relevance signal hai.",
    "nap": "Apna Name/Address/Phone website, JustDial, IndiaMart, Facebook — har jagah ek jaisa karo (spelling tak same). Mismatch se Google ka trust girta hai.",
    "messaging": "GBP messaging ON karo aur phone par notifications laga lo — chat se aaya customer sabse garam lead hota hai.",
}

_GRADES = [(85, "A"), (70, "B"), (50, "C")]  # else "D"


def _grade(score: int) -> str:
    for cutoff, g in _GRADES:
        if score >= cutoff:
            return g
    return "D"


def score_audit(answers: dict[str, Any]) -> dict[str, Any]:
    """Weighted 0-100 GBP score + grade + breakdown + top-5 Hinglish fixes.

    `answers` = {question_id: option_index}. Missing/invalid => worst (0).
    Pure logic — kabhi raise nahi karta, hamesha complete dict deta hai.
    """
    answers = answers if isinstance(answers, dict) else {}
    total_weight = sum(q["weight"] for q in AUDIT_QUESTIONS) or 1
    earned = 0.0
    answered = 0
    breakdown: list[dict[str, Any]] = []
    losses: list[dict[str, Any]] = []  # weighted loss per area (fix ranking)

    for q in AUDIT_QUESTIONS:
        qid = q["id"]
        options = q["options"]
        raw = answers.get(qid, answers.get(str(qid)))
        opt_score, label = 0.0, "no answer"
        try:
            idx = int(raw)  # type: ignore[arg-type]
            if 0 <= idx < len(options):
                opt_score = float(options[idx].get("score", 0.0))
                label = str(options[idx].get("label", ""))
                answered += 1
        except (TypeError, ValueError):
            pass

        weight = q["weight"]
        earned += opt_score * weight
        breakdown.append(
            {
                "id": qid,
                "question": q["q"],
                "weight": weight,
                "answer_label": label,
                "score_pct": round(opt_score * 100),
            }
        )
        loss = (1.0 - opt_score) * weight
        if loss > 0.001:
            losses.append({"id": qid, "loss": loss})

    score = round(100.0 * earned / total_weight)
    score = max(0, min(100, score))

    # Top-5 fixes: sabse zyada weighted-loss wale areas, concrete action ke saath
    losses.sort(key=lambda x: x["loss"], reverse=True)
    top_fixes: list[str] = []
    recoverable = 0.0
    for item in losses[:5]:
        fix = _FIXES.get(item["id"])
        if fix:
            top_fixes.append(fix)
        recoverable += item["loss"]

    potential = min(100, score + round(100.0 * recoverable / total_weight))
    if score >= 90:
        impact = (
            f"Zabardast! {score}/100 — profile top shape me hai. "
            "Bas weekly photos + posts ka routine banaye rakho."
        )
    else:
        impact = (
            f"Abhi {score}/100 — sirf top-5 fixes karne se score ~{potential} tak jaa "
            "sakta hai. Google data: complete profiles ko ~2.7x zyada calls/direction "
            "requests milti hain — ye free leads hain."
        )

    return {
        "score": score,
        "grade": _grade(score),
        "answered": answered,
        "total_questions": len(AUDIT_QUESTIONS),
        "breakdown": breakdown,
        "top_fixes": top_fixes,
        "impact": impact,
    }


def _worst_idx(qid: str) -> int:
    """Unknown → sabse conservative (last) option."""
    for q in AUDIT_QUESTIONS:
        if q["id"] == qid:
            return max(0, len(q["options"]) - 1)
    return 0


def _clamp_idx(qid: str, idx: int) -> int:
    for q in AUDIT_QUESTIONS:
        if q["id"] == qid:
            n = len(q["options"])
            try:
                i = int(idx)
            except (TypeError, ValueError):
                return _worst_idx(qid)
            return max(0, min(n - 1, i))
    return 0


def heuristic_suggest(client: dict[str, Any] | None) -> dict[str, Any]:
    """Profile se CONSERVATIVE answer suggestions. Score SAVE nahi karta.

    Unknown facts → worst/pata-nahi option. Sirf clear signals pe mid/better.
    """
    c = client if isinstance(client, dict) else {}
    socials = c.get("socials") if isinstance(c.get("socials"), dict) else {}
    gbp = str(c.get("gbp") or socials.get("gbp") or "").strip()
    phone = str(c.get("phone") or c.get("whatsapp_phone") or "").strip()
    website = str(c.get("website") or c.get("site_url") or "").strip()
    services = c.get("services")
    has_services = bool(
        (isinstance(services, str) and services.strip())
        or (isinstance(services, list | tuple) and len(services) > 0)
    )
    city = str(c.get("city") or c.get("target_area") or "").strip()
    niche = str(c.get("niche") or c.get("industry") or "").strip()
    wa = bool(str(c.get("whatsapp_phone") or "").strip())

    answers: dict[str, int] = {q["id"]: _worst_idx(q["id"]) for q in AUDIT_QUESTIONS}
    sources: dict[str, str] = {}

    if gbp:
        answers["claimed"] = 1  # claimed? verify unknown — mid, not best
        sources["claimed"] = "gbp_link_present"
    if phone and website:
        answers["contact"] = 0
        sources["contact"] = "phone+website_in_profile"
    elif phone:
        answers["contact"] = 1
        sources["contact"] = "phone_only"
    if has_services:
        answers["services"] = 1
        sources["services"] = "services_in_profile"
    if city and niche:
        answers["description"] = 1
        sources["description"] = "city+niche_known_not_gbp_text"
    if wa:
        answers["booking"] = 0
        sources["booking"] = "whatsapp_can_be_booking_link"
        answers["messaging"] = 2  # still unknown if GBP chat on
        sources["messaging"] = "wa_exists_gbp_chat_unknown"

    # Photos/reviews/hours/posts/qna/nap/geo — live GBP bina invent nahi
    for qid in (
        "photos",
        "posts",
        "reviews_count",
        "rating",
        "review_replies",
        "qna",
        "hours",
        "geo_photos",
        "nap",
        "categories",
    ):
        sources.setdefault(qid, "unknown_conservative")

    return {
        "ok": True,
        "answers": answers,
        "sources": sources,
        "mode": "heuristic",
        "note_hi": (
            "Profile se conservative suggestions. Photos/reviews/hours jaise facts "
            "GBP pe dekh ke boss confirm kare — Score tabhi save hoga."
        ),
    }


def parse_council_gbp_answers(text: str) -> dict[str, int]:
    """Chairman text se `Q_<id>: <index>` lines. Invalid skip."""
    out: dict[str, int] = {}
    raw = str(text or "")
    for q in AUDIT_QUESTIONS:
        qid = q["id"]
        m = re.search(rf"(?im)^\s*Q_{re.escape(qid)}\s*:\s*(\d+)\s*$", raw)
        if not m:
            continue
        out[qid] = _clamp_idx(qid, int(m.group(1)))
    return out
