"""
Professional Hinglish telecaller script dataset for the AI voice sales agent.

Yeh pure-data file hai — koi heavy import nahi (import-safe). Har niche ka
ek script-block hai jo END-CUSTOMER outbound call ke liye likha gaya hai
(LEADS agent client ke potential customers ko call karta hai). Lines real
Indian telecaller best-practices pe based hain (web-researched, June 2026):

  - Permission-based + pattern-interrupt opener (TRAI-friendly, brief)
  - Goal = appointment / site-visit / callback BOOK karna, phone pe close nahi
  - Objection handling = LAER (Listen-Acknowledge-Explore-Respond): pehle
    empathize, phir 1 value-line, phir aage badho
  - Har line phone-ready: 1 vakya, warm, confident, chhota Hinglish
  - [Company]/[Name]/[Project] placeholders runtime pe brain substitute karta

Niche-specific facts baked-in: solar = PM Surya Ghar subsidy (3kW pe ~Rs.78k,
300 unit free); home loan = balance-transfer EMI savings; insurance = term plan
~Rs.20-30/din; study-abroad/coaching/interior/dental = FREE consultation hook
+ no-cost EMI.

Consumers: TelecallerBrain (prompt grounding), knowledge_base (KB embedding via
kb_documents()), web-call demo. get_script() builtin/custom dono ke liye safe —
jo niche cover nahi, wo "general" fallback pe aata hai.
"""

from __future__ import annotations

from app.voice_agent.niche_scripts_data import (  # noqa: F401  (data extracted 2026-06-20)
    NICHE_SCRIPTS,
)

# Objection dict keys (sab niches me same — brain/KB consistent rehte hain):
#   mehenga      -> "price / too expensive / mehnga hai"
#   abhi_nahi    -> "timing / abhi nahi / baad me"
#   soch_ke      -> "soch ke batata hoon / need to think"
#   pehle_se_hai -> "already have it / pehle se laga/liya hai"
#   bharosa      -> "trust / bharosa nahi / genuine ho kya"


# ========================================================================== #
# Readable labels for KB strings (KB me niche/objection naam saaf dikhe)
# ========================================================================== #

_NICHE_LABELS: dict[str, str] = {
    "real_estate": "real estate (site visit)",
    "solar_residential": "residential solar",
    "solar_commercial": "commercial solar / C&I",
    "studying_abroad": "study abroad counselling",
    "insurance": "health/term insurance",
    "coaching": "coaching institute (NEET/JEE)",
    "home_loans": "home loan / balance transfer",
    "interior_designers": "interior design",
    "modular_kitchen": "modular kitchen",
    "dental_implants": "dental implants",
    "hair_transplant": "hair transplant clinic",
    "ivf_clinics": "IVF & fertility clinic",
    "immigration": "immigration / PR consultancy",
    "upskilling": "upskilling / edtech programs",
    "recruitment": "recruitment & staffing agency",
    "hvac_commercial": "commercial HVAC",
    "travel_packages": "international travel packages",
    "packers_movers": "packers & movers",
    "hotels_mice": "hotels & MICE events",
    "digital_marketing": "digital marketing agency",
    "ca_legal": "CA / legal / compliance",
    "restaurant_cafe": "restaurant / cafe",
    "automobile_service": "automobile service center",
    "photography_studio": "photography / videography studio",
    "pharmacy_medical": "pharmacy / medical store",
    "furniture_decor": "furniture & home decor",
    "kirana_supermarket": "kirana / supermarket",
    "travel_agency": "domestic travel agency",
    "gift_stationery": "gift shop / stationery",
    "hospital_appointments": "hospital / clinic appointments",
    "skin_dermatology": "skin & dermatology clinic",
    "finance_advisory": "financial advisory / wealth management",
    "edtech_creators": "edtech course creators",
    "cloud_kitchen": "cloud kitchen / tiffin service",
    "ayurveda_wellness": "Ayurveda & wellness center",
    "event_management": "event management",
    "hardware_paint": "hardware & paint store",
    "ai_marketing": "AI marketing services (B2B, business owners)",
    "general": "general sales call",
}

_OBJ_LABELS: dict[str, str] = {
    "mehenga": "price / too expensive",
    "abhi_nahi": "not now / timing",
    "soch_ke": "need to think about it",
    "pehle_se_hai": "already have it",
    "bharosa": "trust / credibility",
}


# ========================================================================== #
# Tiny helpers (pure, no side effects)
# ========================================================================== #


def get_script(niche_key: str) -> dict:
    """Return the script-block for a niche, ya 'general' fallback.

    Builtin priority niches ke liye custom script, baaki sab (incl. custom
    niches) ke liye general. Hamesha ek valid dict return karta hai.
    """
    if niche_key and niche_key in NICHE_SCRIPTS:
        return NICHE_SCRIPTS[niche_key]
    return NICHE_SCRIPTS["general"]


def kb_documents(niche_key: str) -> list[str]:
    """Niche script ko chhote standalone fact/example strings me flatten karo.

    Output KB embedding ke liye ready hai (har string self-contained sentence).
    Covered niche ka apna data; uncovered niche general script pe map hota hai.
    """
    script = get_script(niche_key)
    label = _NICHE_LABELS.get(niche_key, niche_key.replace("_", " ") if niche_key else "general")
    docs: list[str] = []

    opening = script.get("opening")
    if opening:
        docs.append(f"Opening line for {label}: {opening}")

    for q in script.get("discovery", []):
        docs.append(f"Qualification question for {label}: {q}")

    for obj_key, rebuttal in script.get("objections", {}).items():
        obj_label = _OBJ_LABELS.get(obj_key, obj_key)
        docs.append(f"Objection ({obj_label}) rebuttal for {label}: {rebuttal}")

    for line in script.get("value_lines", []):
        docs.append(f"Value point for {label}: {line}")

    closing = script.get("closing")
    if closing:
        docs.append(f"Closing line for {label}: {closing}")

    return docs


# --------------------------------------------------------------------------- #
# TRAI up-front AI-disclosure (TCCCPR) — legal gate, ALWAYS-ON
# --------------------------------------------------------------------------- #
_AI_DISCLOSURE_TOKENS = ("ai assistant", "ai voice", "automated", "artificial", "a.i.", "ai-")


def ensure_ai_disclosure(text: str, name: str = "Swara") -> str:
    """Guarantee the opener discloses up-front that the caller is an AI.

    TRAI TCCCPR mandates AI promotional calls open with an AI disclosure (not on
    user-ask). If the line already discloses (contains an AI token), it is left
    as-is; otherwise an up-front disclosure is injected naturally. Never raises —
    on any error the original text is returned (the static openers already name
    the company, so we fail toward speaking rather than silence).
    """
    try:
        t = (text or "").strip()
        if not t:
            return t
        low = t.lower()
        if any(tok in low for tok in _AI_DISCLOSURE_TOKENS):
            return t
        import re

        # Common case: "...main Swara bol rahi hoon..." -> insert ", ek AI assistant,".
        m = re.search(r"\bmain\s+" + re.escape(name), t, flags=re.IGNORECASE)
        if m:
            return t[: m.end()] + ", ek AI assistant," + t[m.end() :]
        # Fallback: prepend a short, clear disclosure sentence.
        return f"Main ek AI assistant hoon. {t}"
    except Exception:
        return text or ""


__all__ = ["NICHE_SCRIPTS", "get_script", "kb_documents", "ensure_ai_disclosure"]
