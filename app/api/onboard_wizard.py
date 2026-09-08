"""Onboarding wizard API — business-type templates + auto-setup.

GET  /api/onboard-wizard/business-types     → wizard UI ke liye business-type list
GET  /api/onboard-wizard/preview/{type}     → niche + auto-setup preview (kya milega)
POST /api/onboard-wizard/apply              → client pe niche auto-setup lagao (admin)

Auth: require_admin (Bearer JWT from /app/admin-login). Apply is flag-gated
ONBOARD_WIZARD_APPLY (default OFF) — read-only previews always available.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.auth_deps import require_admin

router = APIRouter(prefix="/api/onboard-wizard", tags=["Onboarding Wizard"])


class WizardApplyIn(BaseModel):
    client_id: str = Field(..., min_length=1, max_length=100)
    business_type: str = Field(..., min_length=1, max_length=60)
    niche_override: str = Field("", max_length=80)
    business_name: str = Field("", max_length=200)
    services: str = Field("", max_length=1000)
    offer: str = Field("", max_length=500)
    opening_line: str = Field("", max_length=1000)


class WizardPreviewIn(BaseModel):
    business_type: str = Field(..., min_length=1, max_length=60)
    business_name: str = Field("", max_length=200)
    services: str = Field("", max_length=1000)
    offer: str = Field("", max_length=500)


@router.get("/business-types")
async def list_business_types(_admin: dict = Depends(require_admin)) -> dict[str, Any]:
    """Wizard UI ke liye saare business types + niche resolve."""
    from app.marketing import onboard_wizard

    try:
        return {
            "ok": True,
            "business_types": onboard_wizard.get_business_types(),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"wizard catalog error: {exc}"[:200])


@router.get("/preview/{business_type}")
async def preview_template(
    business_type: str, _admin: dict = Depends(require_admin)
) -> dict[str, Any]:
    """Ek business type ka template preview — niche + auto-setup fields + asset flags."""
    from app.marketing import onboard_wizard

    try:
        p = onboard_wizard.get_template_preview(business_type)
        return {"ok": True, "template": p}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"wizard preview error: {exc}"[:200])


@router.post("/script-preview")
async def preview_script(
    body: WizardPreviewIn, _admin: dict = Depends(require_admin)
) -> dict[str, Any]:
    """Voice script preview — niche opening + services/offer se suggested opening."""
    from app.marketing import onboard_wizard

    try:
        p = onboard_wizard.get_script_preview(
            body.business_type,
            business_name=body.business_name,
            services=body.services,
            offer=body.offer,
        )
        return p
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"script preview error: {exc}"[:200])


@router.post("/apply")
async def apply_wizard_setup(
    body: WizardApplyIn, _admin: dict = Depends(require_admin)
) -> dict[str, Any]:
    """Client pe business-type niche auto-setup lagao (snapshot + knowledge seed)."""
    from app.marketing import onboard_wizard

    try:
        res = onboard_wizard.apply_auto_setup(
            body.client_id,
            body.business_type,
            niche_override=body.niche_override,
            business_name=body.business_name,
            services=body.services,
            offer=body.offer,
            opening_line=body.opening_line,
        )
        if not res.get("ok") and "disabled" in str(res.get("error") or ""):
            raise HTTPException(
                status_code=423,
                detail="ONBOARD_WIZARD_APPLY disabled — .env me ONBOARD_WIZARD_APPLY=1 set karo",
            )
        return res
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"wizard apply error: {exc}"[:200])
