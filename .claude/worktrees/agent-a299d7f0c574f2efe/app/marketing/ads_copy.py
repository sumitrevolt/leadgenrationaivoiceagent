"""
ads_copy.py — Google RSA + Meta ad copy pack (free stack).
===========================================================

  - ads_pack(business_name, niche, offer="", city="") -> dict:
      google: 15 headlines (HARD ≤30 chars har ek) + 4 descriptions (≤90 chars)
      meta:   3 primary texts (≤125 words) + 2 CTA button texts
      LLM 2 calls max (free_ai), deterministic Hinglish fallback sets —
      counts/limits HAMESHA enforce hote hain, LLM kuch bhi de.

Kabhi raise nahi karta, kabhi khali nahi deta.
"""

from __future__ import annotations

import re
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

try:
    from app.voice_agent import free_ai  # type: ignore
except Exception:  # pragma: no cover - free_ai khud import-safe hai
    free_ai = None  # type: ignore

try:
    # Paid-media specialist personas (agency-agents pack) ko prompt-grounding ke
    # liye on-demand search karte hain. Defensive — missing ho to no-op.
    from app.platform import skill_pack  # type: ignore
except Exception:  # pragma: no cover
    skill_pack = None  # type: ignore

try:
    from app.niches import NICHES  # type: ignore
except Exception:  # pragma: no cover
    NICHES = {}  # type: ignore

_H_MAX = 30  # Google RSA headline char limit
_D_MAX = 90  # Google RSA description char limit
_P_MAX_WORDS = 125  # Meta primary text word budget

_LINE_RE = re.compile(r"^\s*(?:[-*\d.()]+\s*)?(H|D|P|C)\s*[:.\-]\s*(.+)$", re.IGNORECASE)


def _label(niche: str) -> str:
    n = (niche or "").strip().replace("_", " ")
    return (n.title() if n and n.lower() != "general" else "Service")[:40]


def _clip_chars(s: str, n: int) -> str:
    """HARD char clip — word boundary pe kaato, guarantee len <= n."""
    s = re.sub(r"\s+", " ", (s or "")).strip().strip('"').strip()
    if len(s) <= n:
        return s
    cut = s[:n]
    if " " in cut:
        cut = cut[: cut.rfind(" ")]
    return cut.rstrip(" ,.;:-–—!|")[:n]


def _clip_words(s: str, n: int) -> str:
    words = (s or "").split()
    return " ".join(words[:n]) if len(words) > n else (s or "").strip()


def _dedupe_fill(cands: list[str], fillers: list[str], count: int, max_len: int) -> list[str]:
    """Clip → dedupe(case-insensitive) → exactly `count` items (fillers se pad)."""
    out: list[str] = []
    seen = set()
    for s in list(cands) + list(fillers):
        c = _clip_chars(s, max_len)
        if not c or c.lower() in seen:
            continue
        seen.add(c.lower())
        out.append(c)
        if len(out) >= count:
            break
    while len(out) < count:  # pragma: no cover - fillers kaafi hote hain
        filler = f"Aaj Hi Sampark Karein {len(out) + 1}"
        out.append(_clip_chars(filler, max_len))
    return out[:count]


def _fallback_headlines(name: str, label: str, offer: str, city: str) -> list[str]:
    c = (city or "").strip()
    cands = [name]
    if offer:
        cands.append(offer)
    if c:
        cands += [f"Best {label} — {c}", f"{c} Ka Bharosemand Naam"]
    cands += [f"{label} Experts", f"Top Rated {label}"]
    return cands


_H_FILLERS = [
    "Aaj Hi Call Karein",
    "Free Quote Paayein",
    "Trusted Local Business",
    "Quality Kaam, Sahi Daam",
    "Abhi Enquiry Karein",
    "5-Star Rated Service",
    "Jaldi Booking Karein",
    "Limited Time Offer",
    "Ghar Baithe Solution",
    "Expert Team, Asaan Process",
    "WhatsApp Pe Baat Karein",
    "100% Satisfaction",
    "Sahi Daam, Pakka Kaam",
    "Aaj Hi Shuru Karein",
    "Free Consultation Paayein",
    "Hazaron Khush Customers",
]


def _fallback_descriptions(name: str, label: str, offer: str, city: str) -> list[str]:
    c = city.strip() or "aapke sheher"
    out = [
        f"{name}: {label} ke liye trusted naam. Aaj hi call karein, free quote paayein.",
        "Hazaron khush customers. Quality kaam, sahi daam, time pe delivery. Abhi baat karein.",
        f"{c} me ghar baithe {label} — WhatsApp pe enquiry karein, turant jawab milega.",
    ]
    out.append(
        f"{offer} — offer limited hai, aaj hi book karein!"
        if offer
        else "Free consultation + transparent pricing. Pehle baat karein, phir decide karein."
    )
    return out


def _fallback_primaries(name: str, label: str, offer: str, city: str) -> list[str]:
    c = city.strip() or "aapke area"
    offer_line = f" Abhi chal raha hai: {offer}." if offer else ""
    return [
        (
            f"Kya aap {c} me bharosemand {label} dhundh rahe hain? 🤔 {name} ne "
            f"hazaron customers ka kaam time par, sahi daam me poora kiya hai."
            f"{offer_line} Quality ki guarantee, transparent pricing aur friendly "
            "team — sab ek jagah. Aaj hi WhatsApp pe message karein aur FREE "
            "consultation paayein. Der mat kijiye, slot limited hain! 📲"
        ),
        (
            f"⭐⭐⭐⭐⭐ '{name} ne kaam itna accha kiya ki maine 3 dost refer kar "
            f"diye!' — aise reviews hi hamari pehchan hain. {label} me {c} ka "
            f"trusted naam.{offer_line} Pehle baat karein, estimate lein, phir "
            "decide karein — koi pressure nahi. Abhi call ya message karein. 📞"
        ),
        (
            f"STOP scrolling! 🛑 Agar {label.lower()} ki zarurat hai to ye post "
            f"aapke liye hai. {name} — {c} me quality + speed + sahi daam ka "
            f"perfect combo.{offer_line} Sirf is hafte ke liye special slots "
            "khule hain. Comment ya DM karein 'INFO' aur hum turant details "
            "bhejenge. 🚀"
        ),
    ]


_FALLBACK_CTAS = ["WhatsApp Karein 📲", "Abhi Call Karein 📞"]


def _parse_marked(text: str) -> dict[str, list[str]]:
    """'H:/D:/P:/C:' prefixed lines parse karo -> {h:[],d:[],p:[],c:[]}."""
    out: dict[str, list[str]] = {"h": [], "d": [], "p": [], "c": []}
    for ln in (text or "").splitlines():
        m = _LINE_RE.match(ln)
        if m:
            out[m.group(1).lower()].append(m.group(2).strip())
    return out


def _persona(topic: str, max_chars: int = 460) -> tuple[str, str]:
    """Paid-media persona pack se (name, system-prompt grounding prefix).

    skill_pack.find/snippet_for use karta — ppc/paid-social/creative/tracking
    personas ko surface karke LLM ko expert guidance deta. Defensive: kuch na
    mile (ya skill_pack missing) to ('', '')."""
    if skill_pack is None:
        return "", ""
    try:
        hits = skill_pack.find(topic, k=1)
        if not hits:
            return "", ""
        name = hits[0].get("name", "") or ""
        snip = skill_pack.snippet_for(topic, max_chars=max_chars) or ""
        if not snip:
            return name, ""
        prefix = (
            "Neeche ek senior paid-media strategist ka internal guidance hai. "
            "Ise apne jawab me APPLY kar (raw text copy mat kar):\n"
            f"{snip}\n\n"
        )
        return name, prefix
    except Exception:  # pragma: no cover - never break ad copy
        return "", ""


def _niche_keywords(niche: str) -> list[str]:
    """niches.py se is niche ke seed keywords (custom-safe). Empty on miss."""
    try:
        cfg = NICHES.get((niche or "").strip(), {}) or {}
        return [str(k).strip() for k in (cfg.get("keywords") or []) if str(k).strip()][:6]
    except Exception:  # pragma: no cover
        return []


def campaign_plan(
    name: str, label: str, offer: str = "", city: str = "", niche: str = ""
) -> dict[str, Any]:
    """Deterministic paid-media campaign plan — ppc + paid-social + tracking
    persona best-practices ka structured Hinglish form. LLM-free (quota-safe),
    kabhi khali/raise nahi."""
    c = (city or "").strip()
    loc = c or "aapke sheher"
    low = (label or "Service").lower()
    seeds = _niche_keywords(niche) or [low, f"{low} services", f"best {low}"]
    keywords: list[str] = []
    seen: set[str] = set()
    for k in seeds:
        for variant in (k, f"{k} {c}".strip(), f"{low} near me"):
            v = re.sub(r"\s+", " ", variant).strip().lower()
            if v and v not in seen:
                seen.add(v)
                keywords.append(v)
    # SEM keyword matrix (advertools via seo_tools) — additive + defensive. advertools
    # VPS pe opt-in installed; missing/locally => [] (naive `keywords` list upar already
    # deta). Closes the seo_tools orphan (docs/Automation_Marketing_Repos.md). Never-raise.
    keyword_matrix: list[dict[str, Any]] = []
    try:
        from app.marketing import seo_tools

        _mods = [m for m in [c, "near me", "best", "price"] if m] or ["near me", "best"]
        keyword_matrix = seo_tools.generate_keywords(seeds[:6], _mods)[:60]
    except Exception:  # pragma: no cover - never break the plan
        keyword_matrix = []
    return {
        "budget_split": {
            "google_pct": 60,
            "meta_pct": 40,
            "note": (
                f"Local {low} me search-intent zyada hota hai → Google pe ~60%. "
                "₹300-500/din se start karein; 10-14 din data ke baad jo channel "
                "sasta lead de, usme budget shift karein."
            ),
        },
        "targeting": [
            f"📍 Location: {loc} + 10-15 km radius (local service business).",
            "👥 Age 25-55, mobile-first (zyadatar leads mobile se aati hain).",
            f"🎯 Meta interests: {label} + ghar/property owners + local-area pages.",
            "🔁 Retargeting: 7-din ke website/widget visitors par (sabse sasti conversion).",
            "👀 Lookalike: enquiry/call kar chuke logon ka 1% lookalike (Meta).",
        ],
        "keywords": keywords[:10],
        "keyword_matrix": keyword_matrix,
        "negative_keywords": ["free", "sasta", "jobs", "salary", "vacancy", "diy", "kaise kare"],
        "measurement": [
            "🔗 Har ad-link par UTM lagayein (utm_source=google/meta) — lead ka source pata chale.",
            "📞 Call-tracking + WhatsApp-click ko conversion mark karein (sirf clicks nahi).",
            "🎯 KPI: cost-per-lead (CPL). Pehle 2 hafte target ₹100-300/lead (niche pe depend).",
            "📅 Hafte me ek baar search-terms report dekhein, fizool keywords negative me daalein.",
        ],
        "pro_tip": (
            f"{name or 'Aapka business'}: pehle ₹3,000-5,000 ka 2-hafte test budget chalayein, "
            "winner ad + winner keyword nikalein, phir scale karein. Ek saath 3-4 creative "
            "variants test karein (creative-strategist rule)."
            + (f" Offer highlight: {offer.strip()}." if (offer or "").strip() else "")
        ),
    }


async def ads_pack(
    business_name: str, niche: str, offer: str = "", city: str = ""
) -> dict[str, Any]:
    """Google RSA + Meta ad pack. LLM-first (2 calls), Hinglish fallback.

    Limits HARD-enforced: 15 headlines ≤30 chars, 4 descriptions ≤90 chars,
    3 primaries ≤125 words, 2 CTAs. Kabhi raise/khali nahi.
    """
    name = (business_name or "").strip()[:120] or "Aapka Business"
    label = _label(niche)
    offer_c = (offer or "").strip()[:200]
    city_c = (city or "").strip()[:80]
    provider = "template"
    g_name, g_ground = _persona("google search ads ppc headlines keywords conversion quality score")
    m_name, m_ground = _persona("facebook instagram meta paid social ad creative hook targeting")
    grounded_by = [n for n in dict.fromkeys([g_name, m_name]) if n]

    llm_h: list[str] = []
    llm_d: list[str] = []
    llm_p: list[str] = []
    llm_c: list[str] = []

    if free_ai is not None:
        brief = (
            f"Business: {name}. Category: {label}."
            + (f" City: {city_c}." if city_c else "")
            + (f" Offer: {offer_c}." if offer_c else "")
        )
        try:
            g_sys = (
                "Tu Google Ads expert hai. Hinglish (Roman script) me likh: "
                "15 ad headlines (har ek MAX 30 characters — STRICT) aur "
                "4 ad descriptions (har ek MAX 90 characters). Format: har "
                "headline 'H: ...' line par, har description 'D: ...' line "
                "par. Sirf ye lines, koi commentary nahi."
            )
            if g_ground:
                g_sys = g_ground + g_sys
            text, p = await free_ai.chat(
                g_sys,
                [{"role": "user", "content": brief}],
                max_tokens=520,
                temperature=0.7,
            )
            parsed = _parse_marked(text)
            llm_h, llm_d = parsed["h"], parsed["d"]
            if (llm_h or llm_d) and p:
                provider = p
        except Exception as e:
            logger.warning(f"ads_pack google LLM failed: {e}")
        try:
            m_sys = (
                "Tu Facebook/Instagram ads copywriter hai. Hinglish me likh: "
                "3 ad primary texts (50-90 shabd har ek, emoji ke saath, hook "
                "se shuru) aur 2 chhote CTA button texts (2-3 shabd). Format: "
                "har primary EK line par 'P: ...', har CTA 'C: ...'. Sirf ye "
                "lines, koi commentary nahi."
            )
            if m_ground:
                m_sys = m_ground + m_sys
            text2, p2 = await free_ai.chat(
                m_sys,
                [{"role": "user", "content": brief}],
                max_tokens=600,
                temperature=0.75,
            )
            parsed2 = _parse_marked(text2)
            llm_p, llm_c = parsed2["p"], parsed2["c"]
            if llm_p and p2 and provider == "template":
                provider = p2
        except Exception as e:
            logger.warning(f"ads_pack meta LLM failed: {e}")

    headlines = _dedupe_fill(
        llm_h + _fallback_headlines(name, label, offer_c, city_c),
        _H_FILLERS,
        15,
        _H_MAX,
    )
    descriptions = _dedupe_fill(
        llm_d + _fallback_descriptions(name, label, offer_c, city_c),
        _fallback_descriptions(name, label, offer_c, city_c),
        4,
        _D_MAX,
    )
    primaries = [
        _clip_words(s, _P_MAX_WORDS)
        for s in (llm_p + _fallback_primaries(name, label, offer_c, city_c))
        if s and s.strip()
    ][:3]
    while len(primaries) < 3:  # pragma: no cover - fallback 3 deta hi hai
        primaries.append(_fallback_primaries(name, label, offer_c, city_c)[len(primaries) % 3])
    ctas = [_clip_chars(s, 25) for s in (llm_c + _FALLBACK_CTAS) if s and s.strip()][:2]
    while len(ctas) < 2:  # pragma: no cover
        ctas.append(_FALLBACK_CTAS[len(ctas)])

    return {
        "business_name": name,
        "niche": label,
        "google": {"headlines": headlines, "descriptions": descriptions},
        "meta": {"primaries": primaries, "ctas": ctas},
        "plan": campaign_plan(name, label, offer_c, city_c, niche),
        "grounded_by": grounded_by,
        "provider": provider,
        "tip": "Google RSA me sab 15 headlines paste karo — Google khud best "
        "combos test karta hai. Meta pe 3 primaries A/B test karo.",
    }
