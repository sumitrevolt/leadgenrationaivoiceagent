"""
Per-niche knowledge + objection playbook for all builtin niches.

`niches.py` me har niche ka TARGETING + PRICING config hai. Yeh module uska
*conversation* counterpart hai — har niche ke liye:

  - facts:      grounded, end-customer-facing knowledge (jo agent SACH-SACH bol
                sakta hai). DATA agent inhe client ke KB me seed karta hai aur
                LEADS agent inse grounded jawab deta hai (hallucination se bachne
                ke liye — natural_dialog ka anti-hallucination design).
  - benefits:   end customer ko kyun farak padta hai (3-5 short points).
  - objections: objection_key -> Hinglish rebuttal (LEADS agent ke liye).

Frame: LEADS agent client ke END CUSTOMER ko call karta hai (niche ka
`target_type`/`end_customer` dekho). Isliye facts/objections end-customer ki
bhasha me likhe hain, factual rakhe hain — jahan exact number/scheme vary karti
hai wahan "team exact detail confirm karwa degi" pe defer karte hain.

Keys EXACTLY app.niches.NICHES jaise hain. Naya niche add karte waqt yahan bhi
ek pack add karo; lookups `.get()` + generic fallback se safe hain.

Usage:
    from app.niche_knowledge import knowledge_facts, objection_response
    facts = knowledge_facts("solar_residential")
    rebut = objection_response("solar_residential", "too_expensive")
"""

from __future__ import annotations

from typing import Any

# Common objection rebuttals jo har niche pe kaam aate hain (per-niche pack inhe
# override kar sakta hai). End-customer ke saath warm, non-pushy tone.
# NOTE: ye canonical CATEGORY keys hain — har category ka ek generic fallback hai
# taaki koi bhi niche bina apne specific rebuttal ke bhi kuch sahi bol sake.
_GENERIC_OBJECTIONS: dict[str, str] = {
    "not_interested": "Bilkul samajhti hoon. Bas ek chhoti si baat — agar yeh aapke kaam ka na ho to main 1 minute me phone rakh deti hoon, par sun lijiye?",
    "busy": "Koi baat nahi, aap busy hain. Main aapko kis time call karoon jo aapke liye sahi rahe?",
    "send_details": "Zaroor, main WhatsApp pe detail bhej deti hoon. Bas 30 second me ek main baat bata doon taaki aapko pata ho kya bhej rahi hoon?",
    "think_about_it": "Bilkul, sochna chahiye. Main koi pressure nahi de rahi — ek choti detail bhej deti hoon, aap aaram se dekh lena.",
    "too_expensive": "Samajhti hoon. Aap apna budget batayein to main usi me best option nikaal deti hoon — aur EMI/flexible options bhi aksar hote hain.",
    "already_have": "Achhi baat hai! Ek baar free compare/review kar lijiye — ho sakta hai behtar option ya thodi bachat mil jaaye, koi commitment nahi.",
    "just_browsing": "Bilkul, abhi dekh-dekh rahe hain — samajh gayi. Main 1-2 options bhej deti hoon, jab man kare tab aage badhna, koi jaldi nahi.",
}

# Canonical category -> niche pack me jo synonym keys ho sakti hain (preference
# order). match_objection/objection_response pehle niche-specific wording dhoondte
# hain, phir generic fallback.
_OBJECTION_SYNONYMS: dict[str, list[str]] = {
    "too_expensive": [
        "too_expensive",
        "expensive",
        "expensive_abroad",
        "expensive_amc",
        "price",
        "price_high",
        "price_negotiable",
        "rate_high",
        "high_capex",
        "fees",
        "fees_high",
        "budget",
        "budget_issue",
    ],
    "already_have": [
        "already_have",
        "already_have_broker",
        "already_coaching",
        "already_applying",
        "have_vendor",
        "have_supplier",
        "have_ca",
        "have_team",
        "have_loan",
        "existing_partner",
        "local_carpenter",
        "carpenter_cheaper",
    ],
    "just_browsing": [
        "just_browsing",
        "just_looking",
        "just_planning",
        "comparing",
    ],
    "think_about_it": [
        "think_about_it",
        "think",
        "need_to_discuss",
        "need_time",
        "not_decided",
        "not_sure",
        "later",
        "not_now",
    ],
    "busy": ["busy", "no_time", "later", "not_now"],
    "send_details": ["send_details", "send_quote", "send_proposal"],
    "not_interested": ["not_interested"],
}


from app.niche_knowledge_data import NICHE_KNOWLEDGE  # noqa: F401  (data extracted 2026-06-20)

# Generic pack — unknown niche ya missing fields ke liye safe fallback.
_GENERIC_PACK: dict[str, Any] = {
    "facts": [
        "Hum aapke business ke potential customers ko AI voice agent se call karke qualified leads laate hain.",
        "Aap sirf qualified result ke paise dete ho — koi bada fixed setup nahi.",
        "Demo free hai; 15 minute me dikha dete hain system kaise kaam karta hai.",
    ],
    "benefits": [
        "Qualified leads, kam mehnat",
        "Pay-per-result pricing",
        "Free demo",
    ],
    "objections": dict(_GENERIC_OBJECTIONS),
}


# --------------------------------------------------------------------------- #
# Public helpers
# --------------------------------------------------------------------------- #
def get_knowledge_pack(niche_key: str | None) -> dict[str, Any]:
    """Return the full pack for a niche (generic fallback for unknown keys)."""
    if not niche_key:
        return _GENERIC_PACK
    return NICHE_KNOWLEDGE.get(niche_key, _GENERIC_PACK)


def knowledge_facts(niche_key: str | None) -> list[str]:
    """Grounded facts for a niche — DATA agent KB seed + LEADS agent grounding."""
    return list(get_knowledge_pack(niche_key).get("facts", []))


def niche_benefits(niche_key: str | None) -> list[str]:
    """End-customer benefits for a niche."""
    return list(get_knowledge_pack(niche_key).get("benefits", []))


def objection_response(niche_key: str | None, objection_key: str) -> str | None:
    """
    Objection rebuttal for a niche. Resolution order:
      1. niche pack me exact key ya uske synonyms (niche-specific wording).
      2. generic category fallback.
    Returns None only if category bilkul unknown ho.
    """
    pack = get_knowledge_pack(niche_key)
    obj = pack.get("objections", {})
    for syn in _OBJECTION_SYNONYMS.get(objection_key, [objection_key]):
        if syn in obj:
            return obj[syn]
    if objection_key in obj:
        return obj[objection_key]
    return _GENERIC_OBJECTIONS.get(objection_key)


# Free-form utterance keyword -> canonical objection category. Hindi + English
# dono cover karte hain taaki LEADS agent ka rule-based fallback richer ho.
_OBJECTION_KEYWORDS = [
    (
        (
            "mehenga",
            "mehengi",
            "expensive",
            "costly",
            "zyada paisa",
            "zyada paise",
            "budget nahi",
            "afford",
            "paise nahi",
            "kitne ka",
            "kitna lagega",
        ),
        "too_expensive",
    ),
    (
        (
            "dekh raha",
            "dekh rahi",
            "bas dekh",
            "sirf dekh",
            "browse",
            "browsing",
            "just looking",
            "abhi sirf",
            "compare",
            "compar",
        ),
        "just_browsing",
    ),
    (
        (
            "already",
            "pehle se",
            "humara already",
            "existing",
            "already have",
            "ek aur",
            "lagaya hua",
            "pehle se hai",
        ),
        "already_have",
    ),
    (("busy", "abhi nahi", "baad me", "call later", "time nahi", "kaam me"), "busy"),
    (
        (
            "soch",
            "think",
            "dekhungi",
            "dekhunga",
            "discuss",
            "ghar me baat",
            "family se",
            "samay",
            "time chahiye",
        ),
        "think_about_it",
    ),
    (("whatsapp", "email", "detail bhej", "bhej do", "send", "message kar"), "send_details"),
    (("not interested", "nahi chahiye", "interested nahi", "mat karo"), "not_interested"),
]


def match_objection(niche_key: str | None, utterance: str) -> str | None:
    """
    Free-form utterance se best niche objection rebuttal nikaalo. Pehle niche ke
    apne objection key ka direct token match, phir keyword->category->synonym
    resolution (niche-specific wording > generic). None = no clear match.
    """
    if not utterance:
        return None
    low = utterance.lower()
    pack = get_knowledge_pack(niche_key)
    niche_obj = pack.get("objections", {})

    # 1) niche ki apni objection keys ka direct token match (e.g. "just looking")
    for key in niche_obj:
        token = key.replace("_", " ")
        if token in low:
            return niche_obj[key]

    # 2) keyword -> category -> niche synonym / generic fallback
    for words, category in _OBJECTION_KEYWORDS:
        if any(w in low for w in words):
            hit = objection_response(niche_key, category)
            if hit:
                return hit
    return None


__all__ = [
    "NICHE_KNOWLEDGE",
    "get_knowledge_pack",
    "knowledge_facts",
    "niche_benefits",
    "objection_response",
    "match_objection",
]


# --- depth overlay merge (2026-06-14) ---------------------------------------- #
# niche_knowledge_extra.EXTRA ko base packs me APPEND-only merge karo:
# facts/benefits dedupe-append, objections update. Base packs hamesha kaam karte;
# overlay sirf depth badhata. try/except = overlay optional, import kabhi nahi todta.
try:
    from app.niche_knowledge_extra import EXTRA as _EXTRA

    for _k, _v in _EXTRA.items():
        _p = NICHE_KNOWLEDGE.setdefault(_k, {"facts": [], "benefits": [], "objections": {}})
        for _fld in ("facts", "benefits"):
            _dst = _p.setdefault(_fld, [])
            for _item in _v.get(_fld, []):
                if _item not in _dst:
                    _dst.append(_item)
        _p.setdefault("objections", {}).update(_v.get("objections", {}))
except Exception:  # pragma: no cover — overlay optional
    pass
