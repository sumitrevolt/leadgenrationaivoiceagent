"""Per-tenant runtime feature-flags endpoints (Redis-backed, master FEATURE_FLAGS).

Extracted from app/api/growth.py (2026-06-20 refactor) to shrink the god-router.
Mounted via growth.router.include_router(); paths unchanged (/api/growth/infra/feature-flags*).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.auth_deps import require_admin, require_super_admin

router = APIRouter(tags=["Growth"])


# ------------- Per-tenant Feature Flags (Phase 1 SaaS infra upgrade) ------------- #
# Redis-backed runtime flags — per-tenant / percentage rollout (A/B + progressive
# launch + kill-switch) bina redeploy. Master gate = env FEATURE_FLAGS (default OFF).
# Service: app/infrastructure/feature_flags.py. Reads=admin, writes=super_admin.
class FeatureFlagIn(BaseModel):
    key: str
    state: str = "disabled"  # disabled | enabled_all | enabled_percentage | enabled_tenants
    description: str = ""
    percentage: int = 0  # 0-100 (sirf enabled_percentage)
    enabled_tenants: list[str] = Field(default_factory=list)  # sirf enabled_tenants
    metadata: dict = Field(default_factory=dict)


@router.get("/infra/feature-flags")
async def list_feature_flags(_user=Depends(require_admin)):
    """Saare runtime feature-flags + master-gate status."""
    import os as _os

    from app.infrastructure.feature_flags import feature_flags

    flags = await feature_flags.get_all_flags()
    return {
        "system_active": _os.environ.get("FEATURE_FLAGS", "0").strip().lower()
        in ("1", "true", "yes"),
        "count": len(flags),
        "flags": [f.to_dict() for f in flags],
    }


@router.post("/infra/feature-flags")
async def upsert_feature_flag(body: FeatureFlagIn, _user=Depends(require_super_admin)):
    """Create/update ek flag (idempotent upsert). created_at preserve hota."""
    from app.infrastructure.feature_flags import FeatureFlag, FeatureState, feature_flags

    key = (body.key or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="key required")
    valid = {s.value for s in FeatureState}
    if body.state not in valid:
        raise HTTPException(status_code=400, detail=f"state must be one of {sorted(valid)}")
    pct = max(0, min(100, int(body.percentage or 0)))
    flag = FeatureFlag(
        key=key,
        state=FeatureState.coerce(body.state),
        description=body.description or "",
        percentage=pct,
        enabled_tenants=[str(t).strip() for t in (body.enabled_tenants or []) if str(t).strip()],
        metadata=body.metadata or {},
    )
    # Audit trail (audit 2026-07-04): a super-admin action that changes runtime
    # behavior previously left ZERO who/when/old-state trail (Redis-only write).
    old = None
    try:
        prev = await feature_flags.get_flag(key)
        old = prev.to_dict() if prev else None
    except Exception:
        pass
    if not await feature_flags.set_flag(flag):
        raise HTTPException(status_code=503, detail="could not persist flag (storage unavailable)")
    try:
        from app.platform.team import log_event

        log_event(
            "kavya",
            "feature_flag_upsert",
            f"Runtime flag '{key}' -> {body.state}"
            + (f" (was {old.get('state')})" if old else " (new)"),
            meta={"key": key, "old": old, "new": flag.to_dict()},
        )
    except Exception:
        pass
    return {"status": "saved", "flag": flag.to_dict()}


@router.get("/infra/feature-flags/{key}/check")
async def check_feature_flag(
    key: str, tenant_id: str = "", user_id: str = "", _user=Depends(require_admin)
):
    """Eval helper — is flag is tenant/user ke liye on hai? (master-gate respect karta)."""
    from app.infrastructure.feature_flags import feature_flags

    enabled = await feature_flags.is_enabled(key, tenant_id or None, user_id or None)
    return {
        "key": key,
        "tenant_id": tenant_id or None,
        "user_id": user_id or None,
        "enabled": enabled,
    }


@router.get("/infra/feature-flags/{key}")
async def get_feature_flag(key: str, _user=Depends(require_admin)):
    from app.infrastructure.feature_flags import feature_flags

    f = await feature_flags.get_flag(key)
    if not f:
        raise HTTPException(status_code=404, detail="flag not found")
    return f.to_dict()


@router.delete("/infra/feature-flags/{key}")
async def delete_feature_flag(key: str, _user=Depends(require_super_admin)):
    from app.infrastructure.feature_flags import feature_flags

    old = None
    try:
        prev = await feature_flags.get_flag(key)
        old = prev.to_dict() if prev else None
    except Exception:
        pass
    if not await feature_flags.delete_flag(key):
        raise HTTPException(status_code=404, detail="flag not found or storage unavailable")
    try:
        from app.platform.team import log_event

        log_event(
            "kavya",
            "feature_flag_delete",
            f"Runtime flag '{key}' deleted",
            meta={"key": key, "old": old},
        )
    except Exception:
        pass
    return {"status": "deleted", "key": key}


# Growth feature endpoints (marketing-AI/loyalty/reports/keys/NPS/IndexNow) extracted to
# app/api/growth_features.py (2026-06-20); included below so paths stay unchanged.
from app.api.growth_features import router as _features_router  # noqa: E402

router.include_router(_features_router)
