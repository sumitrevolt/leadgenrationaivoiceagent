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
) -> list[SceneSpec]:
    """Deterministic structured scenes for a recipe. Never returns free-form blob only."""
    name = (recipe or "").strip().lower()
    if name not in RECIPES:
        name = "offer_announcement"
    meta = RECIPES[name]
    dur = float(meta.get("default_duration_s") or 4.0)
    biz = (business_name or "Business").strip()
    off = (offer or "").strip() or f"{niche} services"
    call = (cta or "").strip() or "Call ya WhatsApp karo — aaj hi"
    texts = _texts_for(
        name,
        biz=biz,
        offer=off,
        niche=niche,
        language=language,
        cta=call,
        festival=festival,
        tip=tip,
        faq_q=faq_q,
        faq_a=faq_a,
    )
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


__all__ = [
    "RECIPES",
    "build_scene_plan",
    "list_recipes",
    "recipe_allowed",
]
