"""Recipe engine — structured shot/scene plans (not unstructured prompt dumps)."""

from __future__ import annotations

from typing import Any

from app.marketing.creative_os.spec import SceneSpec

# Recipes that require verified source assets / quotes before use.
_BLOCKED_WITHOUT_SOURCE = frozenset({"before_after", "testimonial"})

RECIPES: dict[str, dict[str, Any]] = {
    "offer_announcement": {
        "roles": ["hook", "offer", "proof", "cta"],
        "default_duration_s": 4.0,
    },
    "problem_solution": {
        "roles": ["problem", "agitate", "solution", "cta"],
        "default_duration_s": 4.0,
    },
    "service_showcase": {
        "roles": ["intro", "service_1", "service_2", "cta"],
        "default_duration_s": 4.0,
    },
    "faq_reel": {
        "roles": ["question", "answer", "tip", "cta"],
        "default_duration_s": 3.5,
    },
    "festival_local": {
        "roles": ["greeting", "local_offer", "urgency", "cta"],
        "default_duration_s": 4.0,
    },
    "educational_tip": {
        "roles": ["hook_tip", "explain", "example", "cta"],
        "default_duration_s": 4.0,
    },
    "before_after": {
        "roles": ["before", "after", "proof", "cta"],
        "default_duration_s": 4.0,
        "requires_source_assets": True,
    },
    "testimonial": {
        "roles": ["quote", "attribution", "result", "cta"],
        "default_duration_s": 4.0,
        "requires_verified_quote": True,
    },
}


def list_recipes() -> list[str]:
    return sorted(RECIPES.keys())


# Copy variants per recipe. Index 0 is the "base" phrasing (the original,
# unchanged copy). Higher indices rotate the HOOK line among safe, non-factual
# alternatives so consecutive days read differently. Variant selection is
# deterministic (``build_scene_plan(variant=...)`` or ``dna["variant"]``).
COPY_VARIANTS: dict[str, list[str]] = {
    "offer_announcement": ["base", "question_hook", "benefit_hook"],
    "problem_solution": ["base", "cost_hook", "time_hook"],
    "service_showcase": ["base", "range_hook", "quality_hook"],
    "faq_reel": ["base", "pricing_q", "booking_q"],
    "festival_local": ["base", "countdown_hook", "blessing_hook"],
    "educational_tip": ["base", "myth_hook", "habit_hook"],
    "before_after": ["base", "transform_hook", "result_hook"],
    "testimonial": ["base", "outcome_hook", "trust_hook"],
}

# recipe -> variant name -> {"hi": template, "en": template}. Templates use
# {biz}/{offer}/{niche} only — they never introduce a price, metric or claim.
_VARIANT_HOOKS: dict[str, dict[str, dict[str, str]]] = {
    "offer_announcement": {
        "question_hook": {
            "hi": "{biz} ke paas kya naya hai? {offer}",
            "en": "What's new at {biz}? {offer}",
        },
        "benefit_hook": {
            "hi": "{biz} — {offer} se seedha fayda",
            "en": "{biz} — get more with {offer}",
        },
    },
    "problem_solution": {
        "cost_hook": {
            "hi": "{niche} me deri ka asli kharcha?",
            "en": "The real cost of waiting on {niche}?",
        },
        "time_hook": {
            "hi": "Time bachao — {biz} smart tareeke se",
            "en": "Save time — {biz} does it smarter",
        },
    },
    "service_showcase": {
        "range_hook": {
            "hi": "{biz} me {niche} ki poori range",
            "en": "The full {niche} range at {biz}",
        },
        "quality_hook": {
            "hi": "Quality pehle — {biz} ka vaada",
            "en": "Quality first — the {biz} promise",
        },
    },
    "faq_reel": {
        "pricing_q": {
            "hi": "{niche} ka price kaise tay hota hai?",
            "en": "How is {niche} pricing decided?",
        },
        "booking_q": {
            "hi": "{biz} par booking kaise karein?",
            "en": "How do I book with {biz}?",
        },
    },
    "festival_local": {
        "countdown_hook": {
            "hi": "Tyohar aa gaya — {biz} par slots bhar rahe hain",
            "en": "Festive season is here — slots at {biz} are filling",
        },
        "blessing_hook": {
            "hi": "Aapke ghar khushiyan — {biz} ki taraf se",
            "en": "Warm wishes to your home — from {biz}",
        },
    },
    "educational_tip": {
        "myth_hook": {
            "hi": "{niche} ka ek common myth",
            "en": "A common myth about {niche}",
        },
        "habit_hook": {
            "hi": "{niche} me ek chhoti aadat, bada farq",
            "en": "One small {niche} habit, a big difference",
        },
    },
    "before_after": {
        "transform_hook": {
            "hi": "Dekho — {biz} ka transformation",
            "en": "See the transformation — {biz}",
        },
        "result_hook": {
            "hi": "Pehle aur baad — {biz} ke saath",
            "en": "Before and after — with {biz}",
        },
    },
    "testimonial": {
        "outcome_hook": {
            "hi": "Ek customer ki baat — {biz}",
            "en": "A customer's words — {biz}",
        },
        "trust_hook": {
            "hi": "Bharosa — {biz} ke customers ki zubaani",
            "en": "Trust — in {biz} customers' own words",
        },
    },
}


def recipe_allowed(
    recipe: str, *, source_asset_ids: list[str] | None = None, verified_quote: str = ""
) -> dict[str, Any]:
    """Return {ok:True} or {ok:False, error:...}. before_after/testimonial blocked without proof."""
    name = (recipe or "").strip().lower()
    if name not in RECIPES:
        return {"ok": False, "error": f"unknown_recipe:{name}"}
    meta = RECIPES[name]
    if name in _BLOCKED_WITHOUT_SOURCE:
        if meta.get("requires_source_assets") and not (source_asset_ids or []):
            return {"ok": False, "error": "before_after_requires_source_assets"}
        if meta.get("requires_verified_quote") and not (verified_quote or "").strip():
            return {"ok": False, "error": "testimonial_requires_verified_quote"}
    return {"ok": True, "recipe": name}


def build_scene_plan(
    recipe: str,
    *,
    business_name: str,
    offer: str = "",
    niche: str = "general",
    language: str = "hinglish",
    cta: str = "",
    festival: str = "",
    tip: str = "",
    faq_q: str = "",
    faq_a: str = "",
    dna: dict[str, Any] | None = None,
    variant: int = 0,
) -> list[SceneSpec]:
    """Deterministic structured scenes for a recipe. Never returns free-form blob only.

    ``dna`` (a ``SocialProfile.to_dna()`` dict) and ``variant`` additively vary
    the HOOK line only — the offer, business name and CTA facts are unchanged.
    With no ``dna``/``variant`` this is byte-for-byte the original behaviour.
    """
    name = (recipe or "").strip().lower()
    if name not in RECIPES:
        name = "offer_announcement"
    meta = RECIPES[name]
    dur = float(meta.get("default_duration_s") or 4.0)
    biz = (business_name or "Business").strip()
    dna = dict(dna or {})
    variants = COPY_VARIANTS.get(name) or ["base"]
    dna_variant = dna.get("variant")
    if isinstance(dna_variant, int) and not isinstance(dna_variant, bool):
        v_idx = dna_variant % len(variants)
    else:
        v_idx = int(variant or 0) % len(variants)
    variant_name = variants[v_idx]
    lang = str(dna.get("language_hint") or language or "hinglish").strip()
    hook_variant = str(dna.get("hook_variant") or "").strip()
    off = (offer or "").strip() or f"{niche} services"
    call = (cta or "").strip() or "Call ya WhatsApp karo — aaj hi"
    texts = _texts_for(
        name,
        biz=biz,
        offer=off,
        niche=niche,
        language=lang,
        cta=call,
        festival=festival,
        tip=tip,
        faq_q=faq_q,
        faq_a=faq_a,
        variant_name=variant_name,
    )
    # Frame the hook with the tenant's tone — non-factual opener only.
    if texts and dna:
        try:
            from app.marketing.creative_os.social_profile import apply_to_copy

            texts[0] = apply_to_copy(dna, texts[0], role="hook", language=lang)
        except Exception:  # pragma: no cover - defensive
            pass
    _ = hook_variant  # recorded on the spec by the caller; copy is variant-driven
    roles = list(meta["roles"])
    scenes: list[SceneSpec] = []
    for i, role in enumerate(roles):
        scenes.append(
            SceneSpec(
                index=i,
                role=role,
                text=texts[i] if i < len(texts) else call,
                duration_s=dur,
            )
        )
    return scenes


def _variant_hook(recipe: str, variant_name: str, *, hi: bool, biz: str, offer: str, niche: str) -> str:
    """Return the variant hook line, or "" when the variant has no override."""
    spec = (_VARIANT_HOOKS.get(recipe) or {}).get(variant_name)
    if not spec:
        return ""
    template = spec.get("hi") if hi else spec.get("en")
    if not template:
        return ""
    return template.format(biz=biz, offer=offer, niche=niche)


def _base_texts(
    recipe: str,
    *,
    biz: str,
    offer: str,
    niche: str,
    language: str,
    cta: str,
    festival: str,
    tip: str,
    faq_q: str,
    faq_a: str,
) -> list[str]:
    hi = language in ("hinglish", "hi")
    if recipe == "problem_solution":
        return [
            (
                f"{niche} me delay? Customers wait nahi karte"
                if hi
                else f"Still losing {niche} customers?"
            ),
            (
                "Manual follow-up se leads freeze ho jaate hain"
                if hi
                else "Manual follow-up freezes your pipeline"
            ),
            (
                f"{biz} automated marketing se response turant"
                if hi
                else f"{biz} responds instantly with automation"
            ),
            cta,
        ]
    if recipe == "service_showcase":
        return [
            f"{biz} — aapke area ka trusted {niche}" if hi else f"{biz} — trusted local {niche}",
            f"Service highlight: {offer}",
            f"Quality + speed — {biz} style" if hi else f"Quality and speed — the {biz} way",
            cta,
        ]
    if recipe == "faq_reel":
        q = faq_q or (f"{niche} kitna time leta hai?" if hi else f"How long does {niche} take?")
        a = faq_a or (
            f"{biz} clear timeline + transparent pricing deta hai"
            if hi
            else f"{biz} gives clear timelines and pricing"
        )
        return [
            q,
            a,
            "Pro tip: pehle consultation book karo" if hi else "Pro tip: book a consultation first",
            cta,
        ]
    if recipe == "festival_local":
        fest = festival or ("Festive season" if not hi else "Tyohar special")
        return [
            f"{fest} ki shubhkamnayen — {biz}" if hi else f"{fest} greetings from {biz}",
            f"Local offer: {offer}",
            "Limited slots — aaj confirm karo" if hi else "Limited slots — confirm today",
            cta,
        ]
    if recipe == "educational_tip":
        t = tip or (f"{niche} ke liye 1 practical tip" if hi else f"One practical {niche} tip")
        return [
            t,
            (
                f"{biz} recommend karta hai: consistency > one-time push"
                if hi
                else f"{biz} recommends consistency over one-offs"
            ),
            "Example: weekly offer + clear CTA",
            cta,
        ]
    # offer_announcement (default) + any unknown falls here
    return [
        f"{biz} ki nayi offer" if hi else f"New offer from {biz}",
        offer,
        f"Verified local {niche} — {biz}",
        cta,
    ]


def _texts_for(
    recipe: str,
    *,
    biz: str,
    offer: str,
    niche: str,
    language: str,
    cta: str,
    festival: str,
    tip: str,
    faq_q: str,
    faq_a: str,
    variant_name: str = "base",
) -> list[str]:
    """Base copy for a recipe, with an optional variant override on the HOOK line.

    The override only ever replaces scene[0]; the offer / business / CTA facts in
    the remaining scenes are untouched.
    """
    texts = _base_texts(
        recipe,
        biz=biz,
        offer=offer,
        niche=niche,
        language=language,
        cta=cta,
        festival=festival,
        tip=tip,
        faq_q=faq_q,
        faq_a=faq_a,
    )
    if variant_name and variant_name != "base" and texts:
        hi = language in ("hinglish", "hi")
        override = _variant_hook(
            recipe, variant_name, hi=hi, biz=biz, offer=offer, niche=niche
        )
        if override:
            texts = list(texts)
            texts[0] = override
    return texts


__all__ = [
    "COPY_VARIANTS",
    "RECIPES",
    "build_scene_plan",
    "list_recipes",
    "recipe_allowed",
]
