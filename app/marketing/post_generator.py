"""
post_generator.py — Dhanda.app-style FREE AI marketing module.
===============================================================

Chhote businesses ke liye social-media posts + Google Business Profile (GBP)
tips + 7-din content calendar — sab 100% FREE stack par:

  LLM:      app.voice_agent.free_ai.chat() (Cerebras/Groq/OpenRouter chain).
            free_ai ("","") de sakta hai (zero keys / quota / timeout) —
            ISLIYE har function ka TEMPLATE fallback hai. KABHI empty nahi.
  Niches:   app.niches.NICHES se display name + pitch_hook (sab .get safe).

Import-safe: free_ai/NICHES na milein to bhi module load hota hai aur
templates se kaam chalta hai. Koi function raise nahi karta.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# --- free LLM chain (import-safe; None => sirf templates) --- #
try:
    from app.voice_agent import free_ai  # type: ignore
except Exception:  # pragma: no cover - free_ai khud import-safe hai
    free_ai = None  # type: ignore

try:
    # Marketing persona pack (agency-agents) — content/social/copywriting guidance.
    from app.platform import skill_pack  # type: ignore
except Exception:  # pragma: no cover
    skill_pack = None  # type: ignore


def _persona_prefix(topic: str, max_chars: int = 300) -> str:
    """Marketing persona ka short guidance prefix (skill_pack). Hot path =
    chhota cap (~300). Defensive: skill_pack missing/empty -> ''."""
    if skill_pack is None or not topic:
        return ""
    try:
        snip = skill_pack.snippet_for(topic, max_chars=max_chars) or ""
        return (
            (f"Expert social-media strategist guidance (APPLY, copy mat kar): {snip}\n\n")
            if snip
            else ""
        )
    except Exception:
        return ""


# --- niche registry (import-safe; {} => generic flavor) --- #
try:
    from app.niches import NICHES  # type: ignore
except Exception:  # pragma: no cover
    NICHES = {}  # type: ignore


# ============================================================================ #
# Niche helpers (sab .get fallbacks — unknown/custom niche par bhi chalega)
# ============================================================================ #


def _niche_cfg(niche: str) -> dict[str, Any]:
    try:
        return NICHES.get((niche or "").strip().lower(), {}) or {}
    except Exception:
        return {}


def _niche_name(niche: str) -> str:
    """Display name, warna key ko hi title-case kar do."""
    cfg = _niche_cfg(niche)
    name = str(cfg.get("name") or "").strip()
    if name:
        return name
    key = (niche or "general").strip() or "general"
    return key.replace("_", " ").title()


def _niche_pitch(niche: str) -> str:
    """NICHES pitch_hook (1-line flavor), warna generic Hinglish line."""
    cfg = _niche_cfg(niche)
    pitch = str(cfg.get("pitch_hook") or "").strip()
    return pitch or "Quality service, sahi daam, 100% bharosa."


def _stable_idx(seed: str, n: int) -> int:
    """Deterministic pick (same business+niche => same template, variety across)."""
    if n <= 0:
        return 0
    digest = hashlib.md5((seed or "x").encode("utf-8", "ignore")).hexdigest()
    return int(digest, 16) % n


# ============================================================================ #
# Hashtag sets (per-niche + general base) — fallback aur LLM top-up dono ke liye
# ============================================================================ #

_GENERAL_HASHTAGS: list[str] = [
    "#LocalBusiness",
    "#SmallBusinessIndia",
    "#SupportLocal",
    "#Vocal4Local",
    "#India",
    "#SpecialOffer",
    "#BestService",
    "#Trending",
]

_NICHE_HASHTAGS: dict[str, list[str]] = {
    "real_estate": [
        "#RealEstate",
        "#PropertyForSale",
        "#DreamHome",
        "#RealEstateIndia",
        "#HomeBuying",
        "#SiteVisit",
        "#NewLaunch",
        "#PropertyInvestment",
    ],
    "real_estate_luxury": [
        "#LuxuryRealEstate",
        "#LuxuryHomes",
        "#PremiumProperty",
        "#HNI",
        "#LuxuryLiving",
        "#PenthouseLife",
        "#RealEstateIndia",
        "#DreamHome",
    ],
    "studying_abroad": [
        "#StudyAbroad",
        "#OverseasEducation",
        "#StudentVisa",
        "#IELTS",
        "#StudyInCanada",
        "#StudyInUK",
        "#AbroadDreams",
        "#EducationConsultant",
    ],
    "home_loans": [
        "#HomeLoan",
        "#LoanAgainstProperty",
        "#EMI",
        "#HousingFinance",
        "#BalanceTransfer",
        "#HomeLoanIndia",
        "#DreamHomeLoan",
        "#FinanceTips",
    ],
    "solar_residential": [
        "#SolarEnergy",
        "#RooftopSolar",
        "#SolarPanels",
        "#GoSolar",
        "#SolarIndia",
        "#CleanEnergy",
        "#BijliBachat",
        "#SolarSubsidy",
    ],
    "solar_commercial": [
        "#CommercialSolar",
        "#SolarForBusiness",
        "#SolarEPC",
        "#GoSolar",
        "#SolarIndia",
        "#EnergySavings",
        "#GreenBusiness",
        "#NetMetering",
    ],
    "insurance": [
        "#Insurance",
        "#LifeInsurance",
        "#HealthInsurance",
        "#TermPlan",
        "#FamilyFirst",
        "#FinancialPlanning",
        "#InsuranceIndia",
        "#SecureFuture",
    ],
    "coaching": [
        "#Coaching",
        "#CoachingClasses",
        "#ExamPrep",
        "#StudyTips",
        "#NEET",
        "#JEE",
        "#Toppers",
        "#EducationIndia",
    ],
    "interior_designers": [
        "#InteriorDesign",
        "#HomeDecor",
        "#InteriorDesigner",
        "#HomeInteriors",
        "#ModularKitchen",
        "#HomeMakeover",
        "#DecorGoals",
        "#DesignIndia",
    ],
    "dental_implants": [
        "#DentalCare",
        "#DentalImplants",
        "#SmileMakeover",
        "#Dentist",
        "#OralHealth",
        "#TeethWhitening",
        "#HealthySmile",
        "#DentalClinic",
    ],
    "general": list(_GENERAL_HASHTAGS),
}


def _hashtags_for(niche: str, seed_tags: list[str] | None = None) -> list[str]:
    """8-12 hashtags — LLM ke tags (agar mile) + niche set + general, deduped."""
    out: list[str] = []
    seen = set()

    def _add(tag: str) -> None:
        t = (tag or "").strip()
        if not t:
            return
        if not t.startswith("#"):
            t = "#" + re.sub(r"\s+", "", t)
        low = t.lower()
        # len>=3 => '#' + kam-se-kam 2 chars (truncated "#H" jaise tags drop).
        if low not in seen and len(t) >= 3:
            seen.add(low)
            out.append(t)

    for t in seed_tags or []:
        _add(t)

    key = (niche or "general").strip().lower()
    for t in _NICHE_HASHTAGS.get(key, []):
        _add(t)
    # Unknown/custom niche => key se ek tag bana do (#EvCharging style)
    if key not in _NICHE_HASHTAGS and key not in ("", "general"):
        _add("#" + "".join(p.capitalize() for p in re.split(r"[_\s]+", key) if p))
    for t in _GENERAL_HASHTAGS:
        if len(out) >= 12:
            break
        _add(t)
    return out[:12]


# ============================================================================ #
# Caption templates (LLM-fail fallback) — {business_name}/{offer} placeholders
# ============================================================================ #

_GENERIC_TEMPLATES: list[dict[str, str]] = [
    {
        "caption": (
            "✨ {business_name} me aapka swagat hai!\n"
            "💼 {niche_line}\n"
            "{offer_line}📞 Aaj hi contact karein — DM ya call!"
        ),
        "image_idea": "Shopfront/office ki bright photo, smiling team ke saath",
    },
    {
        "caption": (
            "🚀 {business_name} ke saath kaam banao aasaan!\n"
            "⭐ {niche_line}\n"
            "{offer_line}📍 Visit karein ya WhatsApp karein abhi!"
        ),
        "image_idea": "Service-in-action ki candid photo with logo overlay",
    },
    {
        "caption": (
            "🌟 Sapne bade, service best — {business_name}!\n"
            "💡 {niche_line}\n"
            "{offer_line}💬 Free consultation ke liye aaj hi baat karein!"
        ),
        "image_idea": "Happy customer + team handshake, natural light me",
    },
    {
        "caption": (
            "👇 Sahi jagah aaye hain — {business_name} hai na!\n"
            "✅ {niche_line}\n"
            "{offer_line}⏰ Limited slots — abhi book karein!"
        ),
        "image_idea": "Before/after ya product close-up collage",
    },
    {
        "caption": (
            "💯 {business_name}: kaam jo bole quality!\n"
            "🏆 {niche_line}\n"
            "{offer_line}📲 Details ke liye DM karein!"
        ),
        "image_idea": "5-star review screenshot ka clean graphic card",
    },
]

_FESTIVAL_TEMPLATES: list[dict[str, str]] = [
    {
        "caption": (
            "🪔 {business_name} ki taraf se {occasion} ki hardik shubhkamnayein! ✨\n"
            "{offer_line}🎊 Is shubh avsar par humse judiye — {niche_line}\n"
            "📞 Abhi contact karein!"
        ),
        "image_idea": "Festive decoration ke saath shop/team photo, diye/lights theme",
    },
    {
        "caption": (
            "🎉 {occasion} mubarak ho! {business_name} laya hai khushiyon ka tohfa.\n"
            "{offer_line}💫 {niche_line}\n"
            "📲 DM karein aaj hi!"
        ),
        "image_idea": "Festival-theme creative with brand colors + greeting text",
    },
]


def _template_post(business_name: str, niche: str, occasion: str, offer: str) -> dict[str, Any]:
    """Deterministic, never-empty template post (LLM bilkul na chale tab bhi)."""
    offer_line = f"🎁 Offer: {offer}\n" if (offer or "").strip() else ""
    niche_line = _niche_pitch(niche)
    occ = (occasion or "").strip()

    pool = _FESTIVAL_TEMPLATES if occ else _GENERIC_TEMPLATES
    tpl = pool[_stable_idx(f"{business_name}|{niche}|{occ}", len(pool))]

    caption = (
        tpl["caption"]
        .format(
            business_name=business_name,
            offer_line=offer_line,
            niche_line=niche_line,
            occasion=occ or "is khaas mauke",
        )
        .strip()
    )
    hashtags = _hashtags_for(niche)
    image_idea = tpl["image_idea"]
    return {
        "caption": caption,
        "hashtags": hashtags,
        "image_idea": image_idea,
        "post_text": caption + "\n\n" + " ".join(hashtags),
        "provider": "template",
    }


# ============================================================================ #
# LLM output parsing (lenient — free models format bhatka dete hain)
# ============================================================================ #

# Tag must have >=2 chars after '#' (total len>=3) — kills truncated "#H" leaks.
_TAG_RE = r"#[\wऀ-ॿ]{2,}"

# Markdown decoration (`**`, `_`, `#`) LLMs keyword ke aas-paas daal dete hain
# (e.g. "**HASHTAGS:**") — markers tolerant + caption/image edges se * _ " strip.
_DECOR = r"[*_#\s]*"
_EDGE_STRIP = re.compile(r'^[\s*_"]+|[\s*_"]+$')


def _parse_llm_post(text: str) -> tuple[str, list[str], str]:
    """CAPTION:/HASHTAGS:/IMAGE: markers parse karo; na milein to lenient mode.

    Markdown-bold markers (`**HASHTAGS:**`) bhi handle hote hain — warna caption
    lookahead fail ho ke poora hashtag-block caption me leak karta (real bug)."""
    caption, hashtags, image_idea = "", [], ""
    try:
        m = re.search(
            rf"CAPTION{_DECOR}:\s*(.+?)(?=\n\s*{_DECOR}(?:HASHTAGS?|IMAGE){_DECOR}:|\Z)",
            text,
            re.S | re.I,
        )
        if m:
            caption = _EDGE_STRIP.sub("", m.group(1).strip())
        m = re.search(
            rf"HASHTAGS?{_DECOR}:\s*(.+?)(?=\n\s*{_DECOR}IMAGE{_DECOR}:|\Z)",
            text,
            re.S | re.I,
        )
        if m:
            hashtags = re.findall(_TAG_RE, m.group(1))
        m = re.search(rf"IMAGE{_DECOR}:\s*(.+)", text, re.I)
        if m:
            image_idea = _EDGE_STRIP.sub("", m.group(1).strip().splitlines()[0].strip())

        if not caption:
            # Markers nahi mile — hashtags hata ke bacha text hi caption hai.
            body = re.sub(_TAG_RE, "", text).strip()
            caption = body[:400].strip()
            if not hashtags:
                hashtags = re.findall(_TAG_RE, text)
    except Exception:  # pragma: no cover - regex kabhi raise nahi karta normally
        pass
    return caption, hashtags[:12], image_idea


# ============================================================================ #
# 1) generate_post — social post (LLM-first, template-guaranteed)
# ============================================================================ #


async def generate_post(
    business_name: str,
    niche: str = "general",
    occasion: str = "",
    offer: str = "",
    language: str = "hinglish",
    context: str = "",
) -> dict[str, Any]:
    """Ready-to-copy social post banao. KABHI empty return nahi karta.

    Returns: {"caption", "hashtags"(8-12), "image_idea", "post_text", "provider"}.
    """
    business_name = (business_name or "").strip() or "Aapka Business"
    niche = (niche or "general").strip().lower() or "general"
    occasion = (occasion or "").strip()
    offer = (offer or "").strip()
    language = (language or "hinglish").strip().lower() or "hinglish"

    caption, hashtags, image_idea, provider = "", [], "", ""

    # Optional: typed/validated output via Instructor (USE_STRUCTURED_CONTENT=1).
    # No fragile text-parsing; falls through to the free_ai + template path below.
    try:
        import os

        if os.getenv("USE_STRUCTURED_CONTENT", "").strip().lower() in {"1", "true", "yes", "on"}:
            from pydantic import BaseModel

            from app.llm.structured import aextract

            class _Post(BaseModel):
                caption: str
                hashtags: list[str]
                image_idea: str

            _sys = (
                f"Tu ek expert Indian social-media marketer hai jo chhote local businesses ke liye "
                f"catchy {language} promotional posts likhta hai."
            )
            _usr = (
                f"Business: {business_name}\nCategory: {_niche_name(niche)}\n"
                f"USP/angle: {_niche_pitch(niche)}\nOccasion: {occasion or 'koi nahi'}\n"
                f"Offer: {offer or 'koi nahi'}\n"
                + (f"{context}\n" if context else "")
                + "Fields: caption (2-3 chhoti lines + emojis), hashtags (8-12, har ek '#' ke saath), "
                "image_idea (1-line creative)."
            )
            _obj = await aextract(_Post, _sys, _usr, max_tokens=400)
            if _obj is not None and (_obj.caption or "").strip():
                caption = _obj.caption.strip()
                hashtags = [h for h in (_obj.hashtags or []) if h]
                image_idea = (_obj.image_idea or "").strip()
                provider = "instructor"
    except Exception as e:  # never let the optional path break generation
        logger.warning(f"generate_post structured step skipped: {e}")

    if not caption.strip() and free_ai is not None:
        try:
            # Inject content_feedback best_themes — learn from past performance
            _theme_hint = ""
            try:
                from app.marketing.content_feedback import best_themes as _best_themes

                _top = _best_themes(niche=niche, n=3)  # list[str] — past winners
                if _top:
                    _theme_hint = (
                        "\nTop-performing themes for this niche (past feedback): "
                        + ", ".join(_top)
                        + " — prefer these angles."
                    )
            except Exception:
                pass

            system = (
                _persona_prefix("social media marketing content viral caption hook copywriting")
                + "Tu ek expert Indian social-media marketer hai jo chhote local "
                f"businesses ke liye catchy {language} posts likhta hai. "
                "Output EXACTLY is format me de, koi extra commentary nahi:\n"
                "CAPTION: <2-3 chhoti lines, emojis ke saath>\n"
                "HASHTAGS: <8-12 relevant hashtags, space-separated, # ke saath>\n"
                "IMAGE: <1-line photo/creative idea>" + _theme_hint
            )
            user = (
                f"Business: {business_name}\n"
                f"Category: {_niche_name(niche)}\n"
                f"USP/angle: {_niche_pitch(niche)}\n"
                f"Occasion: {occasion or 'koi nahi'}\n"
                f"Offer: {offer or 'koi nahi'}\n"
                + (f"{context}\n" if context else "")
                + "Ek Instagram/WhatsApp-ready promotional post banao."
            )
            text, provider = await free_ai.chat(
                system,
                [{"role": "user", "content": user}],
                max_tokens=500,  # 350->500: truncation ("CAP") kam karo
                temperature=0.85,
            )
            if text and text.strip():
                caption, hashtags, image_idea = _parse_llm_post(text)
        except Exception as e:  # free_ai.chat khud nahi raise karta, par safety
            logger.warning(f"generate_post LLM step failed, using template: {e}")

    # Truncated fragment ("CAP") = usable caption nahi — template pe fall back.
    if len(caption.strip()) < 20:
        return _template_post(business_name, niche, occasion, offer)

    # LLM chala — missing pieces template stock se top-up karo.
    hashtags = _hashtags_for(niche, seed_tags=hashtags)
    if not image_idea.strip():
        image_idea = (
            f"{business_name} ki festive-theme creative photo"
            if occasion
            else f"{business_name} ke product/service ki clean, well-lit photo"
        )
    return {
        "caption": caption,
        "hashtags": hashtags,
        "image_idea": image_idea,
        "post_text": caption + "\n\n" + " ".join(hashtags),
        "provider": provider or "llm",
    }


# ============================================================================ #
# 2) gbp_tips — STATIC Google Business Profile checklist (no LLM)
# ============================================================================ #

_GBP_UNIVERSAL: list[dict[str, str]] = [
    {
        "tip": "Profile 100% complete karo — har field (hours, website, phone, attributes) bhara ho",
        "why": "Complete profiles ko Google 2.7x zyada 'reputable' maanta hai aur ranking me upar rakhta hai",
        "impact": "high",
    },
    {
        "tip": "Har hafte 2-3 naye photos upload karo (kaam, team, results)",
        "why": "Photos wale profiles ko 42% zyada direction-requests aur 35% zyada website-clicks milte hain",
        "impact": "high",
    },
    {
        "tip": "Har 7 din me ek GBP post daalo (offer/update/event)",
        "why": "Active posting Google ko 'business zinda hai' signal deta hai — local pack me freshness boost",
        "impact": "med",
    },
    {
        "tip": "Har review ka reply 24 ghante ke andar do (negative ka sabse pehle)",
        "why": "Review-response rate ranking factor hai aur 89% log replies padh ke business chunte hain",
        "impact": "high",
    },
    {
        "tip": "Q&A section khud seed karo — 5-6 common sawal khud poochho aur jawab do",
        "why": "Warna random log galat jawab daal dete hain; seeded Q&A objection pehle hi kaat deta hai",
        "impact": "med",
    },
    {
        "tip": "Primary category bilkul sahi chuno + 2-3 secondary categories add karo",
        "why": "Category sabse bada local-ranking factor hai — galat category = galat searches me dikhna",
        "impact": "high",
    },
    {
        "tip": "NAP consistency rakho — Name/Address/Phone har jagah (website, directories) SAME ho",
        "why": "Mismatched NAP se Google ka trust girta hai aur duplicate listings ban jaati hain",
        "impact": "high",
    },
    {
        "tip": "Business description me local keywords daalo (area + service, e.g. 'Andheri me ...')",
        "why": "'Near me' aur '<area> + service' searches me match hone ka direct signal hai",
        "impact": "med",
    },
    {
        "tip": "Products/Services section poora bharo — naam, price-range, photo, description",
        "why": "Ye items search results me directly dikhte hain aur profile ka conversion badhate hain",
        "impact": "med",
    },
    {
        "tip": "Booking/appointment link lagao (Calendly/WhatsApp link bhi chalega)",
        "why": "Profile se seedha booking = zero friction; call chhootne par bhi lead capture hota hai",
        "impact": "med",
    },
    {
        "tip": "Geo-tagged photos use karo (location-on camera se khinchi hui)",
        "why": "Photo metadata local relevance ka extra signal deta hai — free me milta hai, lo",
        "impact": "med",
    },
]

_GBP_NICHE: dict[str, list[dict[str, str]]] = {
    "real_estate": [
        {
            "tip": "Har naye project/listing ka GBP post banao photos + price-range ke saath",
            "why": "'2BHK in <area>' jaise searches me listing-posts seedha dikhte hain — free portal exposure",
            "impact": "high",
        },
    ],
    "real_estate_luxury": [
        {
            "tip": "Premium photoshoot wale interiors/amenities photos hi daalo, phone-clicks nahi",
            "why": "HNI buyer 5 second me profile ki quality se brand judge kar leta hai",
            "impact": "med",
        },
    ],
    "solar_residential": [
        {
            "tip": "Har installation ke baad rooftop ki before/after photo + savings figure post karo",
            "why": "'Solar panel installer near me' me proof-photos wale profile par hi calls aate hain",
            "impact": "high",
        },
    ],
    "solar_commercial": [
        {
            "tip": "Commercial site case-studies (kW size + payback) services section me daalo",
            "why": "B2B buyer capacity aur ROI dekh ke hi enquiry karta hai",
            "impact": "med",
        },
    ],
    "studying_abroad": [
        {
            "tip": "Visa-success student photos (consent ke saath) + university logos posts me daalo",
            "why": "Parents bharosa reviews + success-proof se hi karte hain — enquiry se pehle yahi dekhte hain",
            "impact": "high",
        },
    ],
    "home_loans": [
        {
            "tip": "'Loan approved' success posts + EMI calculator link lagao profile par",
            "why": "Borrower eligibility-doubt me hota hai — calculator click = warm lead",
            "impact": "med",
        },
    ],
    "insurance": [
        {
            "tip": "Claim-settled stories (bina naam ke) post karo — premium nahi, bharosa becho",
            "why": "Insurance me sabse bada objection 'claim milega ya nahi' hota hai",
            "impact": "high",
        },
    ],
    "coaching": [
        {
            "tip": "Toppers/results ke selection-list photos har result-season me post karo",
            "why": "Parents 'results' search karte hain — proof wala profile hi shortlist hota hai",
            "impact": "high",
        },
    ],
    "interior_designers": [
        {
            "tip": "Har completed project ka before/after album banao (room-wise photos)",
            "why": "Interior clients portfolio dekh ke hi call karte hain — GBP hi free portfolio hai",
            "impact": "high",
        },
    ],
    "dental_implants": [
        {
            "tip": "Smile-makeover before/after (consent ke saath) + doctor intro video daalo",
            "why": "Dental me dar sabse bada blocker hai — friendly doctor face trust banata hai",
            "impact": "high",
        },
    ],
}

_GBP_NICHE_DEFAULT: list[dict[str, str]] = [
    {
        "tip": "Apne kaam ki before/after ya result photos regular post karo",
        "why": "Har niche me proof-of-work hi sabse bada trust-builder hai — text claims nahi",
        "impact": "med",
    },
]


def gbp_tips(niche: str = "general") -> list[dict[str, str]]:
    """STATIC researched GBP checklist (no LLM): 11 universal + 1-2 niche-specific."""
    key = (niche or "general").strip().lower()
    tips = [dict(t) for t in _GBP_UNIVERSAL]
    extra = _GBP_NICHE.get(key)
    if extra is None and key not in ("", "general"):
        extra = _GBP_NICHE_DEFAULT
    for t in extra or []:
        tips.append(dict(t))
    return tips


# ============================================================================ #
# 3) content_calendar — 7-din (ya N-din) plan (1 LLM call, template fallback)
# ============================================================================ #

_CAL_FALLBACK: list[tuple[str, str, str]] = [
    ("Monday", "Tip / Gyaan", "💡 Pro tip from {business_name}: {tip_line}"),
    (
        "Tuesday",
        "Offer / Deal",
        "🎉 Sirf is hafte! {business_name} par special offer — DM ya call karein!",
    ),
    (
        "Wednesday",
        "Testimonial",
        "⭐ Hamare khush customer ki kahani — '{business_name} ne kaam aasaan kar diya!'",
    ),
    (
        "Thursday",
        "Behind the Scenes",
        "🎬 Parde ke peeche: dekhiye {business_name} ki team kaise kaam karti hai!",
    ),
    (
        "Friday",
        "Festival / Fun",
        "😄 Weekend mood on! {business_name} ki taraf se fun fact — comment me batao apna take!",
    ),
    (
        "Saturday",
        "Product / Service Spotlight",
        "🔦 Spotlight: {business_name} ki sabse popular service — jaaniye log ise kyun pasand karte hain.",
    ),
    (
        "Sunday",
        "Engagement Question",
        "🤔 Aapka kya khayal hai? Comment me bataiye — {business_name} ke saath Sunday baat-cheet!",
    ),
]


def _template_calendar(business_name: str, niche: str, days: int) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    tip_line = _niche_pitch(niche)
    for i in range(days):
        weekday, theme, cap = _CAL_FALLBACK[i % 7]
        out.append(
            {
                "day": f"Day {i + 1} ({weekday})",
                "theme": theme,
                "caption_short": cap.format(business_name=business_name, tip_line=tip_line),
            }
        )
    return out


def _parse_calendar(text: str, days: int) -> list[dict[str, str]]:
    """'Day 1 | theme | caption' lines parse karo; poore `days` na milein to []"""
    entries: list[dict[str, str]] = []
    try:
        for line in (text or "").splitlines():
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 3 and parts[-2] and parts[-1]:
                day = re.sub(r"^[\-\*\.\)\s]+", "", parts[0]).strip()
                entries.append(
                    {
                        "day": day or f"Day {len(entries) + 1}",
                        "theme": parts[-2],
                        "caption_short": parts[-1],
                    }
                )
            if len(entries) >= days:
                break
    except Exception:  # pragma: no cover
        return []
    return entries if len(entries) == days else []


async def content_calendar(business_name: str, niche: str, days: int = 7) -> list[dict[str, str]]:
    """N-din ka content calendar: [{"day","theme","caption_short"}, ...].

    Ek free_ai.chat call; fail/short par deterministic template (length == days).
    """
    business_name = (business_name or "").strip() or "Aapka Business"
    niche = (niche or "general").strip().lower() or "general"
    try:
        days = max(1, min(int(days), 30))
    except Exception:
        days = 7

    if free_ai is not None:
        try:
            system = (
                "Tu Indian small businesses ka social-media content planner hai. "
                f"EXACTLY {days} lines de, har line is format me (koi extra text nahi):\n"
                "Day <n> | <theme> | <1-line Hinglish caption with 1 emoji>"
            )
            user = (
                f"Business: {business_name} (category: {_niche_name(niche)}, "
                f"angle: {_niche_pitch(niche)}). {days}-din ka content calendar banao."
            )
            text, _provider = await free_ai.chat(
                system,
                [{"role": "user", "content": user}],
                max_tokens=600,
                temperature=0.7,
            )
            if text and text.strip():
                parsed = _parse_calendar(text, days)
                if parsed:
                    return parsed
        except Exception as e:
            logger.warning(f"content_calendar LLM step failed, using template: {e}")

    return _template_calendar(business_name, niche, days)
