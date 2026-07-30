"""Team access API — sub-admins + module-limited members (docs/ADMIN_RBAC_DESIGN.md).

EXISTING /api/admin/users/* (CRUD/status) ke UPAR thin layer: module grants
(rbac, preferences JSON), temp-password onboarding (must_change_password flag),
self change-password. Sab writes existing log_audit (AuditLog table) me.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth_deps import get_current_user, require_admin, require_super_admin
from app.api.ratelimit import rate_limit
from app.models.base import get_async_db
from app.models.user import User, UserRole, UserStatus
from app.platform import rbac
from app.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter(prefix="/team-access", tags=["Team Access"])

_MEMBER_ROLES = ("admin", "manager", "agent", "viewer")  # super_admin yahan se nahi banta


def _member_view(u: User) -> dict:
    return {
        "id": u.id,
        "email": u.email,
        "name": f"{u.first_name} {u.last_name}".strip(),
        "role": u.role.value if u.role else None,
        "status": u.status.value if u.status else None,
        "modules": rbac.get_user_modules(u),
        "must_change_password": rbac.must_change_password(u),
        "last_login": u.last_login.isoformat() if u.last_login else None,
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }


@router.get("/modules")
async def list_modules(_user: User = Depends(require_admin)):
    """Grantable modules catalog (UI checkboxes ke liye)."""
    return {"modules": [{"key": k, "prefixes": v} for k, v in rbac.MODULES.items()]}


@router.get("/members")
async def list_members(
    user: User = Depends(require_admin), db: AsyncSession = Depends(get_async_db)
):
    """Saare team members + unke module grants (merged view)."""
    rows = (
        (await db.execute(select(User).order_by(User.created_at.desc()).limit(200))).scalars().all()
    )
    return {"members": [_member_view(u) for u in rows], "your_role": user.role.value}


class MemberCreate(BaseModel):
    email: EmailStr
    first_name: str
    last_name: str = ""
    role: str = "manager"  # admin = sub-admin (sab); manager/agent/viewer = module-limited
    modules: list[str] = []
    temp_password: str = Field(min_length=8)


@router.post("/members")
async def create_member(
    body: MemberCreate,
    admin: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """Naya team member (super_admin only) — temp password + first-login change forced."""
    if body.role not in _MEMBER_ROLES:
        raise HTTPException(status_code=400, detail=f"role must be one of {_MEMBER_ROLES}")
    existing = (await db.execute(select(User).where(User.email == body.email))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    u = User(
        id=str(uuid.uuid4()),
        email=body.email,
        first_name=body.first_name or body.email.split("@")[0],
        last_name=body.last_name or "-",
        role=UserRole(body.role),
        status=UserStatus.ACTIVE,
        is_verified=True,
        created_at=datetime.utcnow(),
        created_by=admin.id,
    )
    u.set_password(body.temp_password)
    granted = rbac.set_user_modules(u, body.modules)
    rbac.set_must_change_password(u, True)
    db.add(u)
    await db.commit()
    await db.refresh(u)

    from app.api.admin import log_audit

    await log_audit(
        db,
        admin.id,
        "team.member_create",
        "user",
        u.id,
        new_value={"email": u.email, "role": body.role, "modules": granted},
    )
    return {
        "ok": True,
        "member": _member_view(u),
        "note": "temp password member ko alag se do; pehla login pe change forced",
    }


class ModulesIn(BaseModel):
    modules: list[str]


@router.patch("/members/{user_id}/modules")
async def set_modules(
    user_id: str,
    body: ModulesIn,
    admin: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """Member ke module grants update (super_admin only)."""
    u = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    if u.role == UserRole.SUPER_ADMIN:
        raise HTTPException(status_code=400, detail="super_admin needs no grants")
    old = rbac.get_user_modules(u)
    granted = rbac.set_user_modules(u, body.modules)
    u.updated_at = datetime.utcnow()
    await db.commit()

    from app.api.admin import log_audit

    await log_audit(
        db,
        admin.id,
        "team.modules_update",
        "user",
        u.id,
        old_value={"modules": old},
        new_value={"modules": granted},
    )
    return {"ok": True, "modules": granted}


class ResetIn(BaseModel):
    temp_password: str = Field(min_length=8)


@router.post("/members/{user_id}/reset-password")
async def reset_password(
    user_id: str,
    body: ResetIn,
    admin: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """Temp password set (super_admin only) — agla login pe change forced."""
    u = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    u.set_password(body.temp_password)
    rbac.set_must_change_password(u, True)
    u.failed_login_attempts = 0
    u.locked_until = None
    u.updated_at = datetime.utcnow()
    await db.commit()

    from app.api.admin import log_audit

    await log_audit(db, admin.id, "team.password_reset", "user", u.id, severity="warning")
    return {"ok": True, "note": "temp password member ko alag se do"}


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


# Defense-in-depth: password-verify write stays under route ``rate_limit``
# (same 5/300 budget as customer change-password) in addition to the global
# flat middleware — no prefix bypass.
@router.post(
    "/auth/change-password",
    dependencies=[Depends(rate_limit("team_pw_change", 5, 300))],
)
async def change_own_password(
    body: ChangePasswordIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Apna password change (koi bhi logged-in role) — must_change flag clear hota."""
    u = (await db.execute(select(User).where(User.id == user.id))).scalar_one_or_none()
    if not u or not u.verify_password(body.current_password):
        raise HTTPException(status_code=401, detail="Current password galat hai")
    if body.current_password == body.new_password:
        raise HTTPException(status_code=400, detail="Naya password alag hona chahiye")
    u.set_password(body.new_password)
    rbac.set_must_change_password(u, False)
    u.updated_at = datetime.utcnow()
    await db.commit()

    from app.api.admin import log_audit

    await log_audit(db, u.id, "team.password_changed", "user", u.id)
    return {"ok": True}


@router.get("/me")
async def my_access(request_user: User = Depends(get_current_user)):
    """Apna access view — role, modules, change-password flag (UI bootstrap)."""
    return {
        "email": request_user.email,
        "role": request_user.role.value if request_user.role else None,
        "is_admin": request_user.can_access_admin(),
        "modules": rbac.get_user_modules(request_user),
        "must_change_password": rbac.must_change_password(request_user),
    }
