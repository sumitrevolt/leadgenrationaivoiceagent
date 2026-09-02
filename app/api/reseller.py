"""Reseller / Agency program API.

Public apply + program-info endpoints (rate-limited, no auth) and admin
review endpoints (``require_admin``). Defensive: import + handlers never 500.

Mounted by main.py at ``prefix="/api"`` → public routes live under
``/api/reseller/*``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.auth_deps import require_admin
from app.api.ratelimit import rate_limit
from app.platform import reseller
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter(tags=["Reseller"])


# --------------------------------------------------------------------------- #
# Request models
# --------------------------------------------------------------------------- #
class ApplyIn(BaseModel):
    name: str
    agency: str = ""
    email: str
    phone: str = ""
    city: str = ""
    clients_estimate: int = 0
    message: str = ""


# --------------------------------------------------------------------------- #
# Public — apply (rate-limited, no auth)
# --------------------------------------------------------------------------- #
@router.post(
    "/reseller/apply",
    dependencies=[Depends(rate_limit("reseller_apply", 10, 60))],
)
async def reseller_apply(body: ApplyIn):
    """Agency reseller application — NO AUTH, rate-limited. Never-raise."""
    try:
        res = reseller.submit_application(
            name=body.name,
            agency=body.agency,
            email=body.email,
            phone=body.phone,
            city=body.city,
            clients_estimate=body.clients_estimate,
            message=body.message,
        )
    except Exception as e:  # pragma: no cover - defensive (module is never-raise)
        logger.warning("reseller_apply failed: %s", e)
        return {"ok": False, "message": "Kuch galat ho gaya — thodi der baad try karo."}

    if not res.get("ok"):
        return {
            "ok": False,
            "message": res.get("error") or "Application save nahi ho payi.",
        }
    return {
        "ok": True,
        "id": res.get("id"),
        "message": "Application mil gayi — 24 ghante me contact karenge.",
    }


# --------------------------------------------------------------------------- #
# Public — program info (no auth)
# --------------------------------------------------------------------------- #
@router.get("/reseller/info")
async def reseller_info():
    """Static reseller program description (commission tiers + what's included)."""
    try:
        return reseller.program_info()
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("reseller_info failed: %s", e)
        return {"name": "LeadGen AI Reseller Program", "commission_tiers": []}


# --------------------------------------------------------------------------- #
# Admin — review applications
# --------------------------------------------------------------------------- #
@router.get("/reseller/applications")
async def reseller_applications(_user=Depends(require_admin)):
    """List pending reseller applications (admin)."""
    try:
        return {"ok": True, "applications": reseller.list_applications(status="pending")}
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("reseller_applications failed: %s", e)
        return {"ok": True, "applications": []}


@router.post("/reseller/applications/{aid}/approve")
async def reseller_approve(aid: str, _user=Depends(require_admin)):
    """Approve a reseller application (admin)."""
    try:
        return reseller.decide(aid, approve=True, decided_by="admin")
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("reseller_approve failed: %s", e)
        return {"ok": False, "error": "not_found"}


@router.post("/reseller/applications/{aid}/reject")
async def reseller_reject(aid: str, _user=Depends(require_admin)):
    """Reject a reseller application (admin)."""
    try:
        return reseller.decide(aid, approve=False, decided_by="admin")
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("reseller_reject failed: %s", e)
        return {"ok": False, "error": "not_found"}
