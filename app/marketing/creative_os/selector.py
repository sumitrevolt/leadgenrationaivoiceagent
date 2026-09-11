"""Deterministic, tenant-seeded creative selector.

REPLACES the fixed env default as the sole recipe authority (design OI-5). The
`DAILY_VIDEO_RECIPE` env value becomes the COLD-START default for tenants with
fewer than 2 lineage entries — it is no longer a hard override.

DETERMINISM
  ``seed = sha256(f"{tenant_id}|{day}|{rotation_index}")`` → ``random.Random``.
  The same (tenant, day, rotation) always yields the same
  ``(recipe, template_id, hook_variant)`` — reproducible, testable, and no
  shared global state. ``rotation_index`` advances the pick so the novelty gate
  can ask for "the next distinct candidate".

BIAS (advisory only)
  * cold start (fewer than 2 lineage entries) → the env cold-start recipe.
  * otherwise → the tenant's learned ``prefer_recipe`` when it is an allowed
    recipe, else a deterministic pick. Learning never *forces* a recipe and never
    mutates prompts.
  * blocked recipes (``before_after`` / ``testimonial``) are excluded unless the
    caller supplies the verified source assets / quote that ``recipe_allowed``
    requires — the compliance gate is untouched.
"""

from __future__ import annotations

import hashlib
import os
import random
from typing import Any

from app.marketing.creative_os.recipes import list_recipes, recipe_allowed
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

#: Hook registers the selector may pick from. Names only — the copy engine maps
#: them to actual phrasing; this adds no new state-machine vocabulary.
HOOK_VARIANTS: tuple[str, ...] = ("question", "statement", "urgency", "social_proof")

#: niche keyword → HyperFrames template id (must exist in TEMPLATE_REGISTRY).
#: Scanned IN ORDER, first match wins, so the rows are ordered
#: MOST-SPECIFIC-FIRST. The three tenant-niche rows (P1-2) MUST precede the
#: generic `beauty` row: otherwise a niche like "bridal makeup salon" matches
#: `beauty`/`makeup` and silently falls through to the generic beauty template,
#: and the new compositions never run.
_NICHE_TEMPLATE_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("makeover", "makeover_before_after_v1"),
    ("bridal", "bridal_package_v1"),
    ("salon", "salon_service_v1"),
    ("beauty", "beauty_luxury_offer_v1"),
    ("makeup", "beauty_luxury_offer_v1"),
    ("spa", "beauty_luxury_offer_v1"),
    ("hair", "beauty_luxury_offer_v1"),
    ("skin", "beauty_luxury_offer_v1"),
    ("agency", "agency_product_launch_v1"),
    ("saas", "agency_product_launch_v1"),
    ("software", "agency_product_launch_v1"),
    ("product", "agency_product_launch_v1"),
    ("startup", "agency_product_launch_v1"),
)

_DEFAULT_TEMPLATE = "local_service_promo_v1"


def _seed_for(tenant_id: str, day: str, rotation_index: int) -> int:
    raw = f"{tenant_id}|{day}|{int(rotation_index)}".encode("utf-8")
    return int(hashlib.sha256(raw).hexdigest()[:12], 16)


def _template_for(niche: str, recipe: str) -> str:
    """Map a niche (and recipe) to an allowlisted template id."""
    text = f"{niche or ''} {recipe or ''}".lower()
    for keyword, template_id in _NICHE_TEMPLATE_KEYWORDS:
        if keyword in text:
            return template_id
    return _DEFAULT_TEMPLATE


def _allowed_recipes(
    *, source_asset_ids: list[str] | None, verified_quote: str
) -> list[str]:
    out: list[str] = []
    for name in list_recipes():
        gate = recipe_allowed(
            name,
            source_asset_ids=source_asset_ids or [],
            verified_quote=verified_quote or "",
        )
        if gate.get("ok"):
            out.append(name)
    return out


def select_creative(
    *,
    tenant_id: str,
    day: str,
    recipe_hint: str = "",
    learning_stats: dict[str, Any] | None = None,
    profile: Any = None,
    rotation_index: int = 0,
    source_asset_ids: list[str] | None = None,
    verified_quote: str = "",
    niche: str = "general",
    cold_start_recipe: str = "",
    lookback: int = 2,
) -> dict[str, Any]:
    """Return ``{recipe, template_id, hook_variant, seed, reason}``. Never raises."""
    try:
        tid = str(tenant_id or "").strip()
        d = str(day or "").strip()
        rot = max(0, int(rotation_index or 0))
        candidates = _allowed_recipes(
            source_asset_ids=source_asset_ids, verified_quote=verified_quote
        )
        if not candidates:
            return {"ok": False, "error": "no_allowed_recipes"}

        # Rotation base is drawn from a rotation-INDEPENDENT seed (rot=0) and only
        # THEN advanced by `rot`. Seeding this draw with `rot` as well (the old
        # behaviour) made `start` an independent random draw per rotation, so
        # ``(start + rot) % n`` re-collided with probability ~1/n and consecutive
        # rotations emitted the SAME recipe — the exact repetition bug reported.
        base_rng = random.Random(_seed_for(tid, d, 0))
        stats = learning_stats or {}
        prefer = str(stats.get("prefer_recipe") or "").strip()
        cold = _lineage_count(tid) < max(1, int(lookback or 2))
        cold_recipe = (
            str(cold_start_recipe or "").strip()
            or os.getenv("DAILY_VIDEO_RECIPE", "offer_announcement").strip()
            or "offer_announcement"
        )
        hint = str(recipe_hint or "").strip()

        reason = ""
        if rot == 0 and hint and hint in candidates:
            recipe = hint
            reason = "caller_hint"
        elif rot == 0 and cold and cold_recipe in candidates:
            recipe = cold_recipe
            reason = "cold_start_default"
        elif rot == 0 and prefer and prefer in candidates:
            recipe = prefer
            reason = "learned_preference"
        else:
            start = base_rng.randrange(len(candidates))
            recipe = candidates[(start + rot) % len(candidates)]
            reason = "rotation" if rot else "deterministic_pick"

        template_id = _template_for(niche, recipe)
        hook_variant = HOOK_VARIANTS[
            (base_rng.randrange(len(HOOK_VARIANTS)) + rot) % len(HOOK_VARIANTS)
        ]
        seed = _seed_for(tid, d, rot)
        return {
            "ok": True,
            "recipe": recipe,
            "template_id": template_id,
            "hook_variant": hook_variant,
            "seed": seed,
            "rotation_index": rot,
            "cold_start": cold,
            "reason": reason,
        }
    except Exception as exc:
        logger.warning("[selector] select_creative failed: %s", exc)
        return {"ok": False, "error": str(exc)[:160]}


def _lineage_count(tenant_id: str) -> int:
    """How many accepted lineage entries the tenant has, capped at 2 (0 on doubt).

    Only the cold-start boundary (<2) matters here, so we read the last 2 lines
    rather than the whole ledger.
    """
    try:
        from app.marketing.creative_os import novelty

        return len(novelty.recent_lineage(tenant_id, n=2))
    except Exception:
        return 0


__all__ = [
    "HOOK_VARIANTS",
    "select_creative",
]
