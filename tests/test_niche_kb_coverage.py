"""
Niche knowledge-base coverage guarantee.
=========================================
Har ACTIVE niche (app.niches.NICHES) ka ek conversation KB pack
(app.niche_knowledge.NICHE_KNOWLEDGE, overlay-merged) hona CHAHIYE, taaki voice
+ marketing agents us niche me grounded baat kar sakein (hallucination se bachne
ke liye).

Naya niche add karte waqt agar uska KB pack na ho (ya bahut shallow ho) to ye
test FAIL karega — /verify me turant pakda jayega. "Har niche ka KB" permanent
guarantee.

Floor (current packs isse upar hain): >=3 facts, >=2 objection rebuttals, >=2 benefits.
"""

from __future__ import annotations

from app.niche_knowledge import NICHE_KNOWLEDGE
from app.niches import NICHES

MIN_FACTS = 3
MIN_OBJECTIONS = 2
MIN_BENEFITS = 2


def test_every_niche_has_kb_pack():
    """Har niche ka pack maujood ho."""
    missing = sorted(n for n in NICHES if n not in NICHE_KNOWLEDGE)
    assert not missing, (
        f"In niches ka KB pack MISSING hai (niche_knowledge.py ya "
        f"niche_knowledge_extra.py me add karo): {missing}"
    )


def test_every_niche_pack_min_depth():
    """Har pack me kaafi facts/objections/benefits hon (sirf generic fallback nahi)."""
    thin = []
    for n in NICHES:
        p = NICHE_KNOWLEDGE.get(n, {})
        nf = len(p.get("facts", []) or [])
        no = len(p.get("objections", {}) or {})
        nb = len(p.get("benefits", []) or [])
        if nf < MIN_FACTS or no < MIN_OBJECTIONS or nb < MIN_BENEFITS:
            thin.append({"niche": n, "facts": nf, "objections": no, "benefits": nb})
    assert not thin, (
        f"In niches ka KB pack shallow hai (floor {MIN_FACTS}f/{MIN_OBJECTIONS}o/"
        f"{MIN_BENEFITS}b se kam) — depth add karo: {thin}"
    )


def test_overlay_enrichment_applied():
    """Depth overlay (niche_knowledge_extra) base packs me merge hua ho."""
    # ayurveda_wellness overlay me >=4 facts add karte hain → merged pack richer hona chahiye
    p = NICHE_KNOWLEDGE.get("ayurveda_wellness", {})
    assert len(p.get("facts", [])) >= 5, (
        "Depth overlay merge nahi hua (ayurveda_wellness facts kam)"
    )
