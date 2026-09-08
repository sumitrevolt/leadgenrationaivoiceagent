"""Combo Product API — AI Growth Suite (Product 3) ka pricing surface.

GET /api/combo/packages   PUBLIC — pricing page JS fetch
GET /api/combo/niches     PUBLIC — combo-relevant niches (band info ke saath)
GET /api/combo/plans      admin  — plan IDs list (subscription sync ke liye)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.ratelimit import rate_limit

router = APIRouter(prefix="/combo", tags=["Combo Product"])


@router.get("/packages", dependencies=[Depends(rate_limit("combo_pkg", 30, 60))])
async def combo_packages():
    """AI Growth Suite (Marketing + Voice) ka full pricing payload."""
    from app.marketing.combo_packages import get_combo_packages

    return get_combo_packages()


@router.get("/niches", dependencies=[Depends(rate_limit("combo_niches", 30, 60))])
async def combo_niches():
    """Combo product ke relevant niches — band + pricing info ke saath."""
    try:
        from app.marketing.combo_packages import COMBO_TIERS
        from app.niches import NICHES

        # Band → combo tier mapping
        band_to_tier = {t["voice_band"]: t for t in COMBO_TIERS.values()}
        out = []
        for key, cfg in NICHES.items():
            band = cfg.get("lead_band", "A").upper()
            tier = band_to_tier.get(band)
            if not tier:
                continue
            out.append(
                {
                    "key": key,
                    "name": cfg.get("name", key),
                    "category": cfg.get("category"),
                    "band": band,
                    "combo_tier": tier["key"],
                    "combo_price_month": tier["price_month"],
                    "combo_plan_monthly": tier["plan_monthly"],
                }
            )
        return {"niches": sorted(out, key=lambda x: (x["band"], x["name"]))}
    except Exception:
        return {"niches": []}


@router.get("/plans")
async def combo_plans():
    """Combo plan IDs list — subscription._sync_combo_plans ke liye."""
    from app.marketing.combo_packages import COMBO_PILOT, COMBO_PLAN_IDS, COMBO_TIERS

    plans = []
    for t in COMBO_TIERS.values():
        plans.append(
            {
                "plan_id": t["plan_monthly"],
                "name": f"{t['name']} Monthly",
                "price_inr": t["price_month"],
                "billing": "monthly",
            }
        )
        plans.append(
            {
                "plan_id": t["plan_annual"],
                "name": f"{t['name']} Annual",
                "price_inr": t["price_year"],
                "billing": "annual",
            }
        )
    plans.append(
        {
            "plan_id": "combo_pilot",
            "name": COMBO_PILOT["name"],
            "price_inr": 0,
            "billing": "trial",
        }
    )
    return {"plans": plans, "all_ids": COMBO_PLAN_IDS}
