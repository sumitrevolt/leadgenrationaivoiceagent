"""Per-niche COMPLETE marketing pack — content_focus driven (free-stack).

Har niche ke `content_focus` themes (e.g. "festival posters", "property posts",
"reels") use karke posts banao — `post_generator.generate_post` reuse karke —
+ niche hashtags (`hashtags.research` reuse) + ek offer/CTA line (niche ke
`pricing_inr`/`pitch_hook`/`avg_ticket_inr` se derive). Ek call me poora
ready-to-post pack. Platform self-marketing AUR client content templates ke liye.

REUSE only (rebuild nahi): generate_post + hashtags + NICHES. Import-safe,
kabhi raise nahi karta. LLM na ho to generate_post khud template-fallback deta.
"""

from __future__ import annotations

from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def _niche_cfg(niche_key: str) -> dict[str, Any]:
    try:
        from app.niches import NICHES

        return NICHES.get((niche_key or "").strip().lower(), {}) or {}
    except Exception:
        return {}


def _derive_offer(cfg: dict[str, Any]) -> str:
    """Niche pricing/pitch se ek short offer/value line (Hinglish)."""
    hook = str(cfg.get("pitch_hook") or "").strip()
    if hook:
        return hook[:160]
    return "Aaj hi shuru karo — pehle hafte me naye leads."


def _cta(cfg: dict[str, Any]) -> str:
    tgt = str(cfg.get("end_customer") or cfg.get("target_type") or "customers")
    return f"DM 'START' — {tgt} tak pahunchna shuru karein."


async def build_pack(
    niche_key: str, business_name: str | None = None, city: str = "", count: int = 2
) -> dict[str, Any]:
    """Ek niche ka poora marketing pack. count = kitne content_focus themes (posts)."""
    cfg = _niche_cfg(niche_key)
    name = str(cfg.get("name") or (niche_key or "business").replace("_", " ").title())
    biz = (business_name or name).strip()
    focuses = [str(x) for x in (cfg.get("content_focus") or []) if str(x).strip()]
    if not focuses:
        focuses = ["social post", "offer post", "customer testimonial", "festival greeting"]
    offer = _derive_offer(cfg)

    posts: list[dict[str, Any]] = []
    try:
        import asyncio

        from app.marketing.post_generator import generate_post

        themes = focuses[: max(1, min(int(count), 6))]

        async def _one(theme: str) -> dict[str, Any]:
            # 2026-07-19: per-post 10s timeout — ek slow free-LLM call poora pack ko
            # 45s+ hang na kare (generate_post ka apna template-fallback bhi hai).
            p = await asyncio.wait_for(
                generate_post(biz, niche_key, occasion=theme, offer=offer), timeout=10
            )
            return {
                "theme": theme,
                "caption": p.get("caption") or p.get("post_text") or "",
                "hashtags": p.get("hashtags") or [],
                "image_idea": p.get("image_idea") or "",
                "provider": p.get("provider") or "",
            }

        # 2026-07-19: SEQUENTIAL (concurrency 1) — free-tier LLM concurrent calls
        # 429-backoff dete (single call ~1.2s fast, 4-concurrent 40s+). count=2
        # default + sequential + per-post timeout = reliably <20s, kabhi hang nahi.
        for theme in themes:
            try:
                posts.append(await _one(theme))
            except Exception as e:
                logger.warning(f"[niche_pack] theme '{theme}' skipped: {e}")
    except Exception as e:
        logger.warning(f"[niche_pack] post gen failed: {e}")

    # Niche hashtags (research reuse; defensive on shape)
    tags: list[str] = []
    try:
        from app.marketing import hashtags

        h = await hashtags.research(niche_key, city)
        if isinstance(h, dict):
            tags = h.get("hashtags") or h.get("tags") or h.get("trending") or []
        elif isinstance(h, list):
            tags = h
    except Exception as e:
        logger.debug(f"[niche_pack] hashtags skip: {e}")
    if not tags and posts:
        tags = posts[0].get("hashtags") or []

    return {
        "ok": True,
        "niche": niche_key,
        "name": name,
        "tier": cfg.get("tier"),
        "category": cfg.get("category"),
        "target": cfg.get("end_customer") or cfg.get("target_type"),
        "content_focus": focuses,
        "offer": offer,
        "cta": _cta(cfg),
        "posts": posts,
        "hashtags": [str(t) for t in tags][:15],
    }


async def build_all(tier: str | None = None, limit: int = 6) -> dict[str, Any]:
    """Multiple niches ke packs (LLM-heavy → default limit 6). Tier filter optional."""
    try:
        from app.niches import NICHES
    except Exception:
        return {"ok": False, "reason": "NICHES unavailable", "packs": []}
    keys = [
        k
        for k, c in NICHES.items()
        if isinstance(c, dict) and (not tier or str(c.get("tier", "")).upper() == tier.upper())
    ]
    keys = keys[: max(1, min(int(limit), 42))]
    packs = []
    for k in keys:
        try:
            packs.append(await build_pack(k, count=2))
        except Exception as e:
            logger.debug(f"[niche_pack] {k} skip: {e}")
    return {"ok": True, "count": len(packs), "packs": packs}


__all__ = ["build_pack", "build_all"]
