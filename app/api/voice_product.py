"""Voice Product API — AI Voice Calling Agent (Product 2, ADR-009) ka ALAG surface.

Marketing product (/api/marketing/*) se separate handling:
  - GET  /api/voice/packages        PUBLIC — /voice-agent page pricing fetch (band/niche resolved)
  - GET  /api/voice/niches          PUBLIC — voice-product niches (category leadgen/both)
  - GET  /api/voice/quota           admin  — client ka lead quota status (flat plans = unlimited)
  - POST /api/voice/record-lead     admin  — manual qualified-lead record (dispute-fix/override)
  - POST /api/voice/topup-link      admin  — RETIRED, band ka flat monthly fee batata hai

Pricing model: **FLAT MONTHLY per niche-band** (voice_packages.py = single source):
Band A ₹4,999 / B ₹9,999 / C ₹19,999 per month, unlimited AI calls, koi lead-counting
nahi. Purana per-10-qualified-leads / per-lead top-up system 2026-06-12 ko retire hua.
Sab handlers defensive (kabhi 500 nahi on data issues), public endpoints rate-limited.

⚠️ 2026-07-14: is module ne 7 din prod me 500 diya kyunki ye retired
`lead_topup_price()` import kar raha tha. Pricing helper hatate waqt uske SAARE
callers grep karo — module-level nahi, function-level import tha isliye startup pe
nahi phata, sirf request pe. Contract: `tests/test_voice_product_contract.py`.
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
    """Voice product ke niches (marketing product se ALAG set) + band/pricing info.

    PRICING NOTE (2026-07-14): pehle yahan `lead_topup_price(band)` se
    `topup_pack_inr` nikalta tha. Wo function 2026-06-12 ke flat per-band pricing
    switch me retire ho gaya ("Koi lead-counting nahi" — voice_packages.py), par
    import yahan reh gaya -> har request pe ImportError -> **7 din tak prod 500**.
    Ab band ka FLAT monthly price hi truth hai (§5: voice_packages = single source).
    """
    from app.marketing.voice_packages import BANDS, normalize_band
    from app.niches import niches_for_product

    out = []
    for key, cfg in niches_for_product("voice").items():
        band = normalize_band(cfg.get("lead_band"))
        band_info = BANDS.get(band) or {}
        out.append(
            {
                "id": key,
                "name": cfg.get("name", key),
                "tier": cfg.get("tier"),
                "lead_band": band,
                "band_name": band_info.get("name", ""),
                "band_price_month_inr": band_info.get("price_month"),
                "band_price_year_inr": band_info.get("price_year"),
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
    """RETIRED (2026-07-14) — flat per-band pricing me lead top-up hota hi nahi.

    History: ye 10-lead top-up pack ka price deta tha. 2026-06-12 ko voice pricing
    lead-counting se FLAT per-niche-band ho gayi (unlimited calls), aur tab
    `lead_topup_price()` hata diya gaya — par yahan import reh gaya, jo har call pe
    ImportError deta tha. Route ko delete karne ke bajaye retain kiya (koi purana
    caller 404 na khaye) par ab wo band ka SACH bolta hai: flat monthly fee.
    """
    from app.marketing.voice_packages import BANDS, niche_band, normalize_band

    band = normalize_band(body.band) if body.band else niche_band(body.niche)
    band_info = BANDS.get(band) or {}
    return {
        "ok": False,
        "error": (
            "Lead top-up retire ho chuka — voice plans FLAT per-band monthly hain "
            "(unlimited calls). Band ka monthly fee manual UPI se collect karo."
        ),
        "band": band,
        "band_price_month_inr": band_info.get("price_month"),
        "band_price_year_inr": band_info.get("price_year"),
    }
