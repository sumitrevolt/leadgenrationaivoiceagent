"""Voice Product API — AI Voice Calling Agent (Product 2, ADR-009) ka ALAG surface.

Marketing product (/api/marketing/*) se separate handling:
  - GET  /api/voice/packages        PUBLIC — /voice-agent page pricing fetch (band/niche resolved)
  - GET  /api/voice/niches          PUBLIC — voice-product niches (category leadgen/both)
  - GET  /api/voice/quota           admin  — client ka qualified-lead quota status
  - POST /api/voice/record-lead     admin  — manual qualified-lead record (dispute-fix/override)
  - POST /api/voice/topup-link      admin  — 10-lead pack price (manual UPI collect)

Pricing model: per-NICHE per-10-qualified-leads (voice_packages.py) — PER-LEAD system removed.
Sab handlers defensive (kabhi 500 nahi on data issues), public endpoints rate-limited.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.auth_deps import require_admin
from app.api.ratelimit import rate_limit
from app.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter(prefix="/voice", tags=["Voice Product"])


# ----------------------------- PUBLIC pricing ----------------------------- #
@router.get("/agents", dependencies=[Depends(rate_limit("voice_agents", 30, 60))])
async def voice_agents():
    """Voice product personas — telecaller, booking agent, receptionist."""
    from app.voice_agent.voice_roles import list_voice_agents

    return {"product": "voice_agent", "agents": list_voice_agents(), "count": 3}


@router.get("/packages", dependencies=[Depends(rate_limit("voice_pkg", 30, 60))])
async def voice_packages(band: str | None = None, niche: str | None = None):
    """Voice product tiers + 10-lead top-up pack — band ya niche se prices resolve."""
    from app.marketing.voice_packages import get_voice_packages

    return get_voice_packages(band=band, niche=niche)


@router.get("/niches", dependencies=[Depends(rate_limit("voice_niches", 30, 60))])
async def voice_niches():
    """Voice product ke niches (marketing product se ALAG set) + band/pricing info."""
    from app.marketing.voice_packages import BANDS, lead_topup_price
    from app.niches import niches_for_product

    out = []
    for key, cfg in niches_for_product("voice").items():
        band = str(cfg.get("lead_band") or "A").upper()
        out.append(
            {
                "id": key,
                "name": cfg.get("name", key),
                "tier": cfg.get("tier"),
                "lead_band": band,
                "band_name": (BANDS.get(band) or {}).get("name", ""),
                "topup_pack_inr": lead_topup_price(band),
                "pitch_hook": cfg.get("pitch_hook", ""),
            }
        )
    return {"product": "voice_agent", "niches": out, "count": len(out)}


# ----------------------------- Quota / metering ----------------------------- #
@router.get("/quota")
async def voice_quota(client_id: str, plan: str | None = None, _user=Depends(require_admin)):
    """Client ka qualified-lead quota status (period = calendar month)."""
    from app.billing import lead_usage

    return lead_usage.usage_summary(client_id, plan)


class RecordLeadIn(BaseModel):
    client_id: str
    ref: str = ""
    plan: str | None = None


@router.post("/record-lead")
async def record_lead(body: RecordLeadIn, _user=Depends(require_admin)):
    """Manual qualified-lead record (normally call_qualifier hook se auto hota)."""
    from app.billing import lead_usage

    ok = lead_usage.record_qualified_lead(body.client_id, ref=body.ref, plan=body.plan)
    return {"ok": ok, "summary": lead_usage.usage_summary(body.client_id, body.plan)}


class TopupLinkIn(BaseModel):
    client_id: str
    band: str = "A"
    niche: str | None = None


@router.post("/topup-link")
async def lead_topup_link(body: TopupLinkIn, _user=Depends(require_admin)):
    """10-lead top-up pack info (Band-priced).

    Razorpay removed 2026-06-18 — automated payment links gone. Returns the pack
    price so the operator can collect via manual UPI and credit leads manually.
    """
    from app.marketing.voice_packages import lead_topup_price, niche_band, normalize_band

    band = normalize_band(body.band) if body.band else niche_band(body.niche)
    price = lead_topup_price(band)
    return {
        "ok": False,
        "error": "Online payment links band — manual UPI se collect karo, phir leads credit karo.",
        "band": band,
        "price_inr": price,
    }
