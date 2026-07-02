"""Local SEO API — GEO visibility (AI-search) + 3×3 grid rank + listings presence.

  POST /api/localseo/geo-check          (PUBLIC, 5/60s)  AI-search visibility report (lead magnet #3)
  GET  /api/localseo/geo-checks         (admin)          recent geo checks
  POST /api/localseo/grid-rank          (admin)          3×3 grid rank check (9 lookups, 3 runs/day cap)
  GET  /api/localseo/grid-runs          (admin)          recent grid runs
  GET  /api/localseo/listings-checklist (admin)          India directories + manual deep-links (NO scraping)
  POST /api/localseo/listings-status    (admin)          self-reported present-map save → score+tips
  GET  /api/localseo/listings-status    (admin)          latest status + live score (?client_id=)

Mount (main session):
    from app.api.localseo import router as localseo_router
    app.include_router(localseo_router, prefix="/api")   # /api/localseo/*

Patterns (engage.py/seoops.py jaisa): lazy imports, modules never-raise
(error dicts), LLM/network endpoints `asyncio.wait_for` wrapped (prod-down
lesson — event loop kabhi block nahi). Koi naya env flag NAHI (manual/on-demand
endpoints). Listings me koi directory HTTP fetch NAHI (ToS policy).
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.api.auth_deps import require_admin
from app.api.ratelimit import rate_limit
from app.security.turnstile import verify_turnstile
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter(prefix="/localseo", tags=["Local-SEO"])


# --------------------------------------------------------------------------- #
# F1 — GEO / AI-search visibility (PUBLIC lead magnet)
# --------------------------------------------------------------------------- #
class GeoCheckIn(BaseModel):
    business_name: str = Field(..., min_length=2, max_length=120)
    niche: str = Field("", max_length=60)
    city: str = Field(..., min_length=2, max_length=60)


@router.post(
    "/geo-check",
    dependencies=[Depends(rate_limit("geo", 5, 60)), Depends(verify_turnstile)],
)
async def geo_check(body: GeoCheckIn):
    """PUBLIC: 'AI search me aapka business dikh raha hai?' — score+verdict+tips.

    Cache-first (1 hr); LLM probes hard 20s timeout me (event loop safe). Turnstile-
    gated (2026-07-01) — this fans out multiple free-LLM calls per request, same
    abuse class as /api/public/ai-demo; INERT when TURNSTILE_SECRET_KEY unset."""
    from app.marketing import geo_visibility

    try:
        return await asyncio.wait_for(
            geo_visibility.check(body.business_name, body.niche, body.city),
            timeout=20,
        )
    except asyncio.TimeoutError:
        return {
            "ok": False,
            "error": "timeout",
            "message": "AI check me time lag raha hai — thodi der baad try karo.",
        }
    except Exception as e:  # pragma: no cover - module khud never-raise hai
        logger.warning(f"[localseo] geo-check failed: {e}")
        return {"ok": False, "error": str(e)}


@router.get("/geo-checks")
async def geo_checks(limit: int = Query(20, ge=1, le=200), _user=Depends(require_admin)):
    """Recent geo-checks (admin) — kaun lead-magnet use kar raha hai."""
    from app.marketing import geo_visibility

    return {"checks": geo_visibility.recent(limit)}


# --------------------------------------------------------------------------- #
# F2 — 3×3 local grid rank (admin — Places quota costs)
# --------------------------------------------------------------------------- #
class GridRankIn(BaseModel):
    keyword: str = Field(..., min_length=2, max_length=120)
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)
    business_name: str = Field(..., min_length=2, max_length=120)
    radius_km: float = Field(2.0, ge=0.5, le=10)
    phone: str = Field("", max_length=20)


@router.post("/grid-rank")
async def grid_rank_check(body: GridRankIn, _user=Depends(require_admin)):
    """3×3 grid rank — 9 parallel Places lookups (10s each), max 3 runs/day."""
    from app.platform import grid_rank

    try:
        return await asyncio.wait_for(
            grid_rank.grid_check(
                body.keyword, body.lat, body.lng, body.business_name, body.radius_km, body.phone
            ),
            timeout=25,
        )
    except asyncio.TimeoutError:
        return {
            "ok": False,
            "error": "timeout",
            "message": "Grid check slow chal raha — dobara try karo.",
        }
    except Exception as e:  # pragma: no cover - module khud never-raise hai
        logger.warning(f"[localseo] grid-rank failed: {e}")
        return {"ok": False, "error": str(e)}


@router.get("/grid-runs")
async def grid_runs(limit: int = Query(20, ge=1, le=100), _user=Depends(require_admin)):
    """Recent grid runs newest-first + aaj ka daily-cap usage."""
    from app.platform import grid_rank

    return {"runs": grid_rank.recent_runs(limit), "runs_today": grid_rank.runs_today()}


# --------------------------------------------------------------------------- #
# F3 — India listings presence (NO scraping — manual deep-links + self-report)
# --------------------------------------------------------------------------- #
class ListingsStatusIn(BaseModel):
    client_id: str = Field(..., min_length=1, max_length=64)
    present: dict[str, bool] = Field(default_factory=dict)


@router.get("/listings-checklist")
async def listings_checklist(
    business_name: str = Query(..., min_length=2, max_length=120),
    city: str = Query("", max_length=60),
    niche: str = Query("", max_length=60),
    _user=Depends(require_admin),
):
    """Curated India directories + manual search deep-links (LINK only, NO fetch)."""
    from app.marketing import listings_presence

    return listings_presence.checklist(business_name, city, niche)


@router.post("/listings-status")
async def listings_status_save(body: ListingsStatusIn, _user=Depends(require_admin)):
    """Self-reported present-map save karo → 0-100 score + Hinglish gap tips."""
    from app.marketing import listings_presence

    return listings_presence.save_status(body.client_id, body.present)


@router.get("/listings-status")
async def listings_status_get(
    client_id: str = Query(..., min_length=1, max_length=64), _user=Depends(require_admin)
):
    """Client ka latest listings status + live score."""
    from app.marketing import listings_presence

    return listings_presence.get_status(client_id)


__all__ = ["router"]
