"""
Admin API
Endpoints for platform administration, user management, and system monitoring
"""

import json
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, Field

from app.api.ratelimit import rate_limit
from app.config import settings
from app.models.user import AuditLog, User, UserRole, UserSession, UserStatus
from app.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter(prefix="/admin", tags=["Admin"])
security = HTTPBearer()


# ============================================================================
# Pydantic Models
# ============================================================================


class UserCreate(BaseModel):
    """Create user request"""

    email: EmailStr
    password: str = Field(min_length=8)
    first_name: str
    last_name: str
    phone: str | None = None
    job_title: str | None = None
    role: str = "viewer"
    client_id: str | None = None


class UserUpdate(BaseModel):
    """Update user request"""

    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    job_title: str | None = None
    department: str | None = None
    bio: str | None = None
    role: str | None = None
    status: str | None = None


class UserResponse(BaseModel):
    """User response"""

    id: str
    email: str
    first_name: str
    last_name: str
    full_name: str
    phone: str | None
    job_title: str | None
    role: str
    status: str
    profile_picture_url: str | None
    profile_picture_thumbnail_url: str | None
    is_verified: bool
    is_2fa_enabled: bool
    client_id: str | None
    created_at: datetime
    last_login: datetime | None


class LoginRequest(BaseModel):
    """Login request"""

    email: EmailStr
    password: str
    totp: str = ""  # 2FA code (sirf ADMIN_TOTP_SECRET env set hone par required)


class LoginResponse(BaseModel):
    """Login response"""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 3600
    user: UserResponse
    must_change_password: bool = False  # temp-password onboarding (rbac flag)
    must_setup_2fa: bool = False  # Tier-1 Slice D: policy requires 2FA enrollment


class AdminStats(BaseModel):
    """Admin dashboard statistics"""

    total_users: int
    active_users: int
    total_clients: int
    active_clients: int
    total_leads: int
    total_calls: int
    total_appointments: int
    total_revenue_inr: float
    active_campaigns: int
    system_health: str  # healthy, degraded, critical


class SystemHealth(BaseModel):
    """System health status"""

    overall: str
    database: str
    redis: str
    vertex_ai: str
    telephony: str
    storage: str
    last_checked: datetime


class AuditLogEntry(BaseModel):
    """Audit log entry"""

    id: str
    user_id: str | None
    user_email: str | None
    action: str
    resource_type: str | None
    resource_id: str | None
    ip_address: str | None
    created_at: datetime
    severity: str


# ============================================================================
# Database Integration (Production-Ready)
# ============================================================================

import secrets
from datetime import timezone

from jose import JWTError, jwt
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import get_async_db

# JWT Configuration
# settings.jwt_secret_key is loaded from env/.env by pydantic-settings —
# os.environ.get() would miss values that only exist in the .env file.
# Must match app.api.auth_deps.JWT_SECRET (token issue + verify).
JWT_SECRET = settings.jwt_secret_key
JWT_ALGORITHM = settings.jwt_algorithm
ACCESS_TOKEN_EXPIRE_MINUTES = settings.jwt_access_token_expire_minutes
REFRESH_TOKEN_EXPIRE_DAYS = settings.jwt_refresh_token_expire_days


def create_access_token(user_id: str, email: str, role: str) -> str:
    """Create JWT access token.

    ``jti`` + ``iat`` are required for ``admin_sessions`` revocation (logout /
    password-reset epoch bump). Tokens without them cannot be killed server-side
    before natural expiry — that gap made deploy-window 401 handling the only
    real "logout" path for many sessions.
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "exp": expire,
        "iat": int(now.timestamp()),
        "jti": str(uuid.uuid4()),
        "type": "access",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    """Create JWT refresh token (also carries jti/iat for revocation parity)."""
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": user_id,
        "exp": expire,
        "iat": int(now.timestamp()),
        "jti": str(uuid.uuid4()),
        "type": "refresh",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and validate JWT token"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")


# ============================================================================
# Helper Functions
# ============================================================================


# ── Canonical auth (ADMIN-001 council fix 2026-06-26) ───────────────────────
# These three deps previously had LOCAL copies here that had drifted WEAKER than
# the canonical app.api.auth_deps versions: the local get_current_user blocked
# only SUSPENDED (not INACTIVE → a deprovisioned admin could still authenticate)
# and the local require_admin skipped the RBAC module-grant path. Delegate to the
# single canonical implementation so behaviour can no longer diverge. Other
# modules importing `require_admin` from here (e.g. assessment.py) auto-inherit
# the stronger version. auth_deps imports no app.api.* module → no import cycle.
from app.api.auth_deps import get_current_user, require_admin, require_super_admin  # noqa: E402


async def log_audit(
    db: AsyncSession,
    user_id: str | None,
    action: str,
    resource_type: str = None,
    resource_id: str = None,
    old_value: dict = None,
    new_value: dict = None,
    ip_address: str = None,
    severity: str = "info",
):
    """Log admin action to database for audit trail"""
    audit_entry = AuditLog(
        id=str(uuid.uuid4()),
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        old_value=json.dumps(old_value) if old_value else None,
        new_value=json.dumps(new_value) if new_value else None,
        ip_address=ip_address,
        created_at=datetime.utcnow(),
        severity=severity,
    )
    db.add(audit_entry)
    await db.commit()
    logger.info(f"Audit: {action} by user {user_id} on {resource_type}/{resource_id}")


# ============================================================================
# Authentication Endpoints
# ============================================================================


@router.post(
    "/auth/login",
    response_model=LoginResponse,
    dependencies=[Depends(rate_limit("admin_login", 8, 60))],
)
async def login(request: LoginRequest, db: AsyncSession = Depends(get_async_db)):
    """
    Authenticate user and return JWT tokens
    """
    # Find user by email
    result = await db.execute(select(User).where(User.email == request.email))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Check account status
    if user.status == UserStatus.SUSPENDED:
        raise HTTPException(status_code=403, detail="Account suspended")

    if user.locked_until and user.locked_until > datetime.utcnow():
        raise HTTPException(status_code=403, detail="Account temporarily locked")

    # Verify password
    if not user.verify_password(request.password):
        user.failed_login_attempts = (user.failed_login_attempts or 0) + 1

        # Lock after 5 failed attempts
        if user.failed_login_attempts >= 5:
            user.locked_until = datetime.utcnow() + timedelta(minutes=30)

        await db.commit()
        await log_audit(db, None, "login.failed", "user", user.id, severity="warning")
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # 2FA step-up (Tier-1 Slice D): per-user TOTP takes precedence. The shared
    # ADMIN_TOTP_SECRET remains ONLY as a bootstrap / break-glass fallback for users who
    # have not yet enrolled — so the owner can never be permanently locked out.
    from app.platform import admin_2fa

    if admin_2fa.is_enabled(user):
        if not await admin_2fa.verify_login_code(user, request.totp):
            user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
            if user.failed_login_attempts >= 5:
                user.locked_until = datetime.utcnow() + timedelta(minutes=30)
            await db.commit()
            await log_audit(db, user.id, "login.totp_failed", "user", user.id, severity="warning")
            raise HTTPException(status_code=401, detail="2FA code required/invalid")
    else:
        import os as _os

        _totp_secret = (_os.getenv("ADMIN_TOTP_SECRET") or "").strip()
        if _totp_secret:
            from app.utils.totp import verify_totp

            if not verify_totp(_totp_secret, request.totp):
                await log_audit(
                    db, user.id, "login.totp_failed", "user", user.id, severity="warning"
                )
                raise HTTPException(status_code=401, detail="2FA code required/invalid")

    # Reset failed attempts on success
    user.failed_login_attempts = 0
    user.last_login = datetime.utcnow()
    await db.commit()

    # Generate JWT tokens
    access_token = create_access_token(user.id, user.email, user.role.value)
    refresh_token = create_refresh_token(user.id)

    # Create session in database
    session = UserSession(
        id=str(uuid.uuid4()),
        user_id=user.id,
        access_token_hash=secrets.token_hex(32),  # Store hash, not actual token
        refresh_token_hash=secrets.token_hex(32),
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(hours=1),
        is_active=True,
    )
    db.add(session)
    await db.commit()

    await log_audit(db, user.id, "login.success", "user", user.id)

    try:
        from app.platform import rbac as _rbac

        _must_change = _rbac.must_change_password(user)
    except Exception:
        _must_change = False

    try:
        from app.platform import admin_2fa as _a2fa

        _must_setup_2fa = _a2fa.must_setup(user)
    except Exception:
        _must_setup_2fa = False

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        must_change_password=_must_change,
        must_setup_2fa=_must_setup_2fa,
        user=UserResponse(
            id=user.id,
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            full_name=user.full_name,
            phone=user.phone,
            job_title=user.job_title,
            role=user.role.value,
            status=user.status.value,
            profile_picture_url=user.profile_picture_url,
            profile_picture_thumbnail_url=user.profile_picture_thumbnail_url,
            is_verified=user.is_verified,
            is_2fa_enabled=user.is_2fa_enabled,
            client_id=user.client_id,
            created_at=user.created_at,
            last_login=user.last_login,
        ),
    )


@router.post("/auth/logout")
async def logout(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Logout and invalidate all user sessions (DB session rows + real JWT revocation).
    """
    # Invalidate all sessions for user in database
    result = await db.execute(
        select(UserSession).where(and_(UserSession.user_id == user.id, UserSession.is_active))
    )
    sessions = result.scalars().all()
    for session in sessions:
        session.is_active = False
        session.revoked_at = datetime.utcnow()
        session.revoke_reason = "logout"

    await db.commit()

    # Tier-1 Slice C: the DB rows above were never checked on requests — the JWT itself
    # stayed valid after logout. Actually revoke it now: blacklist this token's jti AND
    # epoch-bump the user (matches this endpoint's "invalidate ALL sessions" intent).
    from app.platform import admin_sessions

    try:
        auth = request.headers.get("authorization") or ""
        if auth.lower().startswith("bearer "):
            payload = decode_token(auth.split(" ", 1)[1])
            ttl = None
            exp = payload.get("exp")
            if exp:
                import time as _t

                ttl = max(1, int(exp) - int(_t.time()))
            await admin_sessions.revoke_jti(payload.get("jti"), ttl=ttl)
    except Exception:
        pass
    await admin_sessions.revoke_all_for_user(user.id, reason="logout")

    await log_audit(db, user.id, "logout", "user", user.id)
    return {"message": "Logged out successfully"}


# ============================================================================
# Per-user 2FA (TOTP) — Tier-1 Slice D
# ============================================================================


class TwoFAPasswordIn(BaseModel):
    password: str


class TwoFAActivateIn(BaseModel):
    code: str


class TwoFADisableIn(BaseModel):
    password: str
    code: str = ""


@router.get("/2fa/status")
async def twofa_status(user: User = Depends(get_current_user)):
    """Current user's 2FA state + enrollment policy."""
    from app.platform import admin_2fa

    return admin_2fa.status(user)


@router.post("/2fa/setup", dependencies=[Depends(rate_limit("admin_2fa", 10, 300))])
async def twofa_setup(
    body: TwoFAPasswordIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Begin enrollment: password re-auth → returns otpauth URI + raw secret + recovery
    codes ONCE (never persisted in plaintext, never logged). 2FA is not enabled until
    /2fa/activate confirms a code."""
    if not user.verify_password(body.password):
        await log_audit(db, user.id, "2fa.setup_denied", "user", user.id, severity="warning")
        raise HTTPException(status_code=401, detail="Password re-authentication failed")
    from app.platform import admin_2fa

    enroll = admin_2fa.generate_enrollment(user)
    await db.commit()
    await log_audit(db, user.id, "2fa.setup_begin", "user", user.id)
    return {
        "ok": True,
        "otpauth_uri": enroll["otpauth_uri"],
        "secret": enroll["secret"],
        "recovery_codes": enroll["recovery_codes"],
    }


@router.post("/2fa/activate", dependencies=[Depends(rate_limit("admin_2fa", 10, 300))])
async def twofa_activate(
    body: TwoFAActivateIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Confirm the pending enrollment with a TOTP code → enable 2FA."""
    from app.platform import admin_2fa

    if not admin_2fa.activate(user, body.code):
        await log_audit(db, user.id, "2fa.activate_failed", "user", user.id, severity="warning")
        raise HTTPException(status_code=400, detail="Invalid or expired 2FA code")
    await db.commit()
    await log_audit(db, user.id, "2fa.activated", "user", user.id)
    return {"ok": True, "enabled": True}


@router.post("/2fa/disable", dependencies=[Depends(rate_limit("admin_2fa", 10, 300))])
async def twofa_disable(
    body: TwoFADisableIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Disable 2FA: password re-auth + a current TOTP/recovery code → revoke all sessions."""
    from app.platform import admin_2fa, admin_sessions

    if not user.verify_password(body.password):
        raise HTTPException(status_code=401, detail="Password re-authentication failed")
    if admin_2fa.is_enabled(user) and not await admin_2fa.verify_login_code(user, body.code):
        await log_audit(db, user.id, "2fa.disable_denied", "user", user.id, severity="warning")
        raise HTTPException(status_code=401, detail="Current 2FA code required")
    admin_2fa.disable(user)
    await db.commit()
    await admin_sessions.revoke_all_for_user(user.id, reason="2fa_disabled")
    await log_audit(db, user.id, "2fa.disabled", "user", user.id, severity="warning")
    return {"ok": True, "enabled": False}


@router.post("/2fa/recovery/regenerate", dependencies=[Depends(rate_limit("admin_2fa", 5, 300))])
async def twofa_recovery_regen(
    body: TwoFADisableIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Issue a fresh set of recovery codes (invalidates old). Requires password + a code."""
    from app.platform import admin_2fa

    if not user.verify_password(body.password):
        raise HTTPException(status_code=401, detail="Password re-authentication failed")
    if not admin_2fa.is_enabled(user):
        raise HTTPException(status_code=400, detail="2FA not enabled")
    if not await admin_2fa.verify_login_code(user, body.code):
        raise HTTPException(status_code=401, detail="Current 2FA code required")
    codes = admin_2fa.regenerate_recovery(user)
    await db.commit()
    await log_audit(db, user.id, "2fa.recovery_regenerated", "user", user.id, severity="warning")
    return {"ok": True, "recovery_codes": codes}


# ============================================================================
# User Management Endpoints
# ============================================================================


@router.get("/users", response_model=list[UserResponse])
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    role: str | None = None,
    status: str | None = None,
    search: str | None = None,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """
    List all users with filtering and pagination (database-backed)
    """
    # Build query
    query = select(User)
    filters = []

    # Filter by role
    if role:
        try:
            filters.append(User.role == UserRole(role))
        except ValueError:
            pass

    # Filter by status
    if status:
        try:
            filters.append(User.status == UserStatus(status))
        except ValueError:
            pass

    # Search in name/email
    if search:
        search_pattern = f"%{search.lower()}%"
        filters.append(
            or_(
                func.lower(User.email).like(search_pattern),
                func.lower(User.first_name).like(search_pattern),
                func.lower(User.last_name).like(search_pattern),
            )
        )

    # Non-super admins can only see users from their client
    if admin.role != UserRole.SUPER_ADMIN and admin.client_id:
        filters.append(User.client_id == admin.client_id)

    if filters:
        query = query.where(and_(*filters))

    query = query.offset(skip).limit(limit).order_by(User.created_at.desc())

    result = await db.execute(query)
    users = result.scalars().all()

    return [
        UserResponse(
            id=user.id,
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            full_name=user.full_name,
            phone=user.phone,
            job_title=user.job_title,
            role=user.role.value,
            status=user.status.value,
            profile_picture_url=user.profile_picture_url,
            profile_picture_thumbnail_url=user.profile_picture_thumbnail_url,
            is_verified=user.is_verified,
            is_2fa_enabled=user.is_2fa_enabled,
            client_id=user.client_id,
            created_at=user.created_at,
            last_login=user.last_login,
        )
        for user in users
    ]


@router.post("/users", response_model=UserResponse)
async def create_user(
    request: UserCreate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Create a new user (database-backed)
    """
    # Check if email already exists
    result = await db.execute(select(User).where(User.email == request.email))
    existing_user = result.scalar_one_or_none()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    # Validate role
    try:
        role = UserRole(request.role)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid role: {request.role}")

    # Only super admin can create other super admins
    if role == UserRole.SUPER_ADMIN and admin.role != UserRole.SUPER_ADMIN:
        raise HTTPException(status_code=403, detail="Only super admin can create super admin users")

    # Create user
    user = User(
        id=str(uuid.uuid4()),
        email=request.email,
        first_name=request.first_name,
        last_name=request.last_name,
        phone=request.phone,
        job_title=request.job_title,
        role=role,
        status=UserStatus.PENDING,
        client_id=request.client_id or admin.client_id,
        created_at=datetime.utcnow(),
        created_by=admin.id,
    )
    user.set_password(request.password)
    user.generate_verification_token()

    db.add(user)
    await db.commit()
    await db.refresh(user)

    await log_audit(
        db,
        admin.id,
        "user.create",
        "user",
        user.id,
        new_value={"email": user.email, "role": role.value},
    )

    # Send verification email (best-effort, never block create)
    try:
        from app.platform.auto_outreach import EmailSender as _ES

        _es = _ES()
        _es.send(
            to=user.email,
            subject="Aapka LeadsGenAI account ban gaya ✅",
            body=(
                f"Namaste {user.first_name},\n\n"
                f"Aapka account create ho gaya hai.\n"
                f"Login: https://leadsgenai.in/app/admin-login\n"
                f"Email: {user.email}\n\n"
                f"Agar aapne yeh account request nahi kiya, please ignore karein.\n\n"
                f"Team LeadsGenAI"
            ),
        )
    except Exception as _ve:
        logger.debug(f"[user.create] verification email skip: {_ve}")

    return UserResponse(
        id=user.id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        full_name=user.full_name,
        phone=user.phone,
        job_title=user.job_title,
        role=user.role.value,
        status=user.status.value,
        profile_picture_url=user.profile_picture_url,
        profile_picture_thumbnail_url=user.profile_picture_thumbnail_url,
        is_verified=user.is_verified,
        is_2fa_enabled=user.is_2fa_enabled,
        client_id=user.client_id,
        created_at=user.created_at,
        last_login=user.last_login,
    )


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_async_db)
):
    """
    Get user by ID (database-backed)
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Check permission
    if admin.role != UserRole.SUPER_ADMIN and user.client_id != admin.client_id:
        raise HTTPException(status_code=403, detail="Access denied")

    return UserResponse(
        id=user.id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        full_name=user.full_name,
        phone=user.phone,
        job_title=user.job_title,
        role=user.role.value,
        status=user.status.value,
        profile_picture_url=user.profile_picture_url,
        profile_picture_thumbnail_url=user.profile_picture_thumbnail_url,
        is_verified=user.is_verified,
        is_2fa_enabled=user.is_2fa_enabled,
        client_id=user.client_id,
        created_at=user.created_at,
        last_login=user.last_login,
    )


@router.patch("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    request: UserUpdate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Update user details (database-backed)
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    old_values = user.to_dict()

    # Check permission
    if admin.role != UserRole.SUPER_ADMIN and user.client_id != admin.client_id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Update fields
    if request.first_name:
        user.first_name = request.first_name
    if request.last_name:
        user.last_name = request.last_name
    if request.phone:
        user.phone = request.phone
    if request.job_title:
        user.job_title = request.job_title
    if request.department:
        user.department = request.department
    if request.bio:
        user.bio = request.bio

    # Role changes require proper permission
    if request.role:
        new_role = UserRole(request.role)
        if new_role == UserRole.SUPER_ADMIN and admin.role != UserRole.SUPER_ADMIN:
            raise HTTPException(status_code=403, detail="Cannot promote to super admin")
        user.role = new_role

    if request.status:
        user.status = UserStatus(request.status)

    user.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(user)

    # Tier-1 Slice C: a role or status change must invalidate the target's existing tokens
    # so a stale higher-privilege / still-active session cannot be reused after downgrade,
    # suspension or deactivation.
    if request.role or request.status:
        from app.platform import admin_sessions

        await admin_sessions.revoke_all_for_user(
            user.id,
            reason=f"user.update role={request.role or '-'} status={request.status or '-'}",
        )

    await log_audit(
        db, admin.id, "user.update", "user", user.id, old_value=old_values, new_value=user.to_dict()
    )

    return UserResponse(
        id=user.id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        full_name=user.full_name,
        phone=user.phone,
        job_title=user.job_title,
        role=user.role.value,
        status=user.status.value,
        profile_picture_url=user.profile_picture_url,
        profile_picture_thumbnail_url=user.profile_picture_thumbnail_url,
        is_verified=user.is_verified,
        is_2fa_enabled=user.is_2fa_enabled,
        client_id=user.client_id,
        created_at=user.created_at,
        last_login=user.last_login,
    )


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    admin: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Delete user (super admin only) - database-backed
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Cannot delete yourself
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")

    user_email = user.email
    await db.delete(user)
    await db.commit()

    # Tier-1 Slice C: kill any live tokens of the deleted user immediately.
    from app.platform import admin_sessions

    await admin_sessions.revoke_all_for_user(user_id, reason="user.delete")

    await log_audit(
        db,
        admin.id,
        "user.delete",
        "user",
        user_id,
        old_value={"email": user_email},
        severity="warning",
    )

    return {"message": "User deleted successfully"}


# ============================================================================
# Profile Picture Endpoints
# ============================================================================


@router.post("/users/{user_id}/picture")
async def upload_profile_picture(
    user_id: str,
    file: UploadFile = File(...),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Upload profile picture for a user
    Stores in Google Cloud Storage
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Validate file type
    allowed_types = ["image/jpeg", "image/png", "image/gif", "image/webp"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400, detail="Invalid file type. Allowed: JPEG, PNG, GIF, WebP"
        )

    # Validate file size (max 5MB)
    contents = await file.read()
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Max 5MB")

    # For production, upload to GCS
    try:
        from app.utils.storage import generate_thumbnail, upload_to_gcs

        bucket_name = settings.gcs_bucket_name or "auraleads-profile-pictures"
        file_ext = file.filename.split(".")[-1] if file.filename else "jpg"
        file_path = f"profile-pictures/{user_id}/{uuid.uuid4()}.{file_ext}"

        # Upload original
        picture_url = await upload_to_gcs(bucket_name, file_path, contents, file.content_type)

        # Generate and upload thumbnail
        thumbnail_contents = await generate_thumbnail(contents, size=(150, 150))
        thumbnail_path = file_path.replace(f".{file_ext}", f"_thumb.{file_ext}")
        thumbnail_url = await upload_to_gcs(
            bucket_name, thumbnail_path, thumbnail_contents, file.content_type
        )

        user.profile_picture_url = picture_url
        user.profile_picture_thumbnail_url = thumbnail_url
        user.profile_picture_bucket = bucket_name
        user.profile_picture_path = file_path

    except Exception as e:
        logger.warning(f"GCS upload failed, using placeholder: {e}")
        # Fallback to placeholder
        user.profile_picture_url = f"https://ui-avatars.com/api/?name={user.first_name}+{user.last_name}&size=200&background=3b82f6&color=fff"
        user.profile_picture_thumbnail_url = f"https://ui-avatars.com/api/?name={user.first_name}+{user.last_name}&size=50&background=3b82f6&color=fff"

    await db.commit()
    await log_audit(db, admin.id, "user.picture.upload", "user", user_id)

    return {
        "message": "Profile picture uploaded",
        "profile_picture_url": user.profile_picture_url,
        "profile_picture_thumbnail_url": user.profile_picture_thumbnail_url,
    }


@router.delete("/users/{user_id}/picture")
async def delete_profile_picture(
    user_id: str, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_async_db)
):
    """
    Delete user's profile picture
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Delete from GCS if exists
    if user.profile_picture_bucket and user.profile_picture_path:
        try:
            from app.utils.storage import delete_from_gcs

            await delete_from_gcs(user.profile_picture_bucket, user.profile_picture_path)
        except Exception as e:
            logger.warning(f"GCS delete failed: {e}")

    user.profile_picture_url = None
    user.profile_picture_thumbnail_url = None
    user.profile_picture_bucket = None
    user.profile_picture_path = None

    await db.commit()
    await log_audit(db, admin.id, "user.picture.delete", "user", user_id)

    return {"message": "Profile picture deleted"}


# ============================================================================
# Admin Dashboard Endpoints
# ============================================================================


@router.get("/stats", response_model=AdminStats)
async def get_admin_stats(
    admin: User = Depends(require_admin), db: AsyncSession = Depends(get_async_db)
):
    """
    Get admin dashboard statistics (database-backed)
    """
    # Get user counts from database
    total_users_result = await db.execute(select(func.count(User.id)))
    total_users = total_users_result.scalar() or 0

    active_users_result = await db.execute(
        select(func.count(User.id)).where(User.status == UserStatus.ACTIVE)
    )
    active_users = active_users_result.scalar() or 0

    # Real DB queries — models import lazy to avoid circular
    try:
        from sqlalchemy import func as _func

        from app.models.billing_record import BillingRecord
        from app.models.call_log import CallLog
        from app.models.client import Client
        from app.models.lead import Lead

        _tc_r = await db.execute(select(_func.count(Client.id)))
        total_clients = _tc_r.scalar() or 0

        from app.models.client import ClientStatus as _CS

        _ac_r = await db.execute(
            select(_func.count(Client.id)).where(Client.status.in_([_CS.ACTIVE, _CS.TRIAL]))
        )
        active_clients = _ac_r.scalar() or 0

        _tl_r = await db.execute(select(_func.count(Lead.id)))
        total_leads = _tl_r.scalar() or 0

        _calls_r = await db.execute(select(_func.count(CallLog.id)))
        total_calls = _calls_r.scalar() or 0

        from app.models.billing_record import BillingRecordStatus as _BRS
        from app.models.call_log import CallOutcome as _CO

        _appt_r = await db.execute(
            select(_func.count(CallLog.id)).where(CallLog.outcome == _CO.APPOINTMENT)
        )
        total_appointments = _appt_r.scalar() or 0

        _rev_r = await db.execute(
            select(_func.sum(BillingRecord.amount)).where(BillingRecord.status == _BRS.PAID)
        )
        # amount stored in paise → convert to INR
        total_revenue_inr = float((_rev_r.scalar() or 0) / 100.0)
    except Exception as _e:
        logger.warning(f"[admin_stats] DB query failed, using defaults: {_e}")
        total_clients = active_clients = 0
        total_leads = total_calls = total_appointments = 0
        total_revenue_inr = 0.0

    return AdminStats(
        total_users=total_users,
        active_users=active_users,
        total_clients=total_clients,
        active_clients=active_clients,
        total_leads=total_leads,
        total_calls=total_calls,
        total_appointments=total_appointments,
        total_revenue_inr=total_revenue_inr,
        active_campaigns=0,
        system_health="healthy",
    )


@router.get("/health", response_model=SystemHealth)
async def get_system_health(admin: User = Depends(require_admin)):
    """
    Get system health status
    """
    health = {
        "database": "healthy",
        "redis": "healthy",
        "vertex_ai": "healthy",
        "telephony": "healthy",
        "storage": "healthy",
    }

    # Check database
    try:
        from app.models.base import get_async_session

        async with get_async_session() as session:
            await session.execute("SELECT 1")
    except:
        health["database"] = "unhealthy"

    # Check Redis
    try:
        from app.cache import get_redis_client

        redis = await get_redis_client()
        await redis.ping()
    except:
        health["redis"] = "degraded"

    # Check Vertex AI
    try:
        from app.llm import get_vertex_client

        client = get_vertex_client()
        if client:
            health["vertex_ai"] = "healthy"
    except:
        health["vertex_ai"] = "degraded"

    # Determine overall health
    unhealthy_count = sum(1 for v in health.values() if v == "unhealthy")
    degraded_count = sum(1 for v in health.values() if v == "degraded")

    if unhealthy_count > 0:
        overall = "critical"
    elif degraded_count > 0:
        overall = "degraded"
    else:
        overall = "healthy"

    return SystemHealth(
        overall=overall,
        database=health["database"],
        redis=health["redis"],
        vertex_ai=health["vertex_ai"],
        telephony=health["telephony"],
        storage=health["storage"],
        last_checked=datetime.utcnow(),
    )


# ============================================================================
# Audit Log Endpoints
# ============================================================================


@router.get("/audit-logs", response_model=list[AuditLogEntry])
async def get_audit_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    action: str | None = None,
    user_id: str | None = None,
    resource_type: str | None = None,
    severity: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    admin: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Get audit logs from database (super admin only)
    """
    # Build query with filters
    query = select(AuditLog)
    filters = []

    if action:
        filters.append(AuditLog.action.contains(action))
    if user_id:
        filters.append(AuditLog.user_id == user_id)
    if resource_type:
        filters.append(AuditLog.resource_type == resource_type)
    if severity:
        filters.append(AuditLog.severity == severity)
    if start_date:
        filters.append(AuditLog.created_at >= start_date)
    if end_date:
        filters.append(AuditLog.created_at <= end_date)

    if filters:
        query = query.where(and_(*filters))

    query = query.order_by(AuditLog.created_at.desc()).offset(skip).limit(limit)

    result = await db.execute(query)
    logs = result.scalars().all()

    # Get user emails for the logs
    user_ids = [log.user_id for log in logs if log.user_id]
    users_result = await db.execute(select(User).where(User.id.in_(user_ids))) if user_ids else None
    user_map = {u.id: u.email for u in users_result.scalars().all()} if users_result else {}

    return [
        AuditLogEntry(
            id=log.id,
            user_id=log.user_id,
            user_email=user_map.get(log.user_id),
            action=log.action,
            resource_type=log.resource_type,
            resource_id=log.resource_id,
            ip_address=log.ip_address,
            created_at=log.created_at,
            severity=log.severity,
        )
        for log in logs
    ]


# ============================================================================
# Settings Endpoints
# ============================================================================


@router.get("/settings")
async def get_platform_settings(admin: User = Depends(require_super_admin)):
    """
    Get platform settings (super admin only)
    """
    return {
        "app_name": settings.app_name,
        "app_env": settings.app_env,
        "default_llm": settings.default_llm,
        "default_tts": settings.default_tts,
        "default_stt": settings.default_stt,
        "default_telephony": settings.default_telephony,
        "max_concurrent_calls": settings.max_concurrent_calls,
        "working_hours_start": settings.working_hours_start,
        "working_hours_end": settings.working_hours_end,
        "timezone": settings.timezone,
        "enable_dnd_check": settings.enable_dnd_check,
        "auto_start_platform": settings.auto_start_platform,
    }


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(user: User = Depends(get_current_user)):
    """
    Get current logged in user info
    """
    return UserResponse(
        id=user.id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        full_name=user.full_name,
        phone=user.phone,
        job_title=user.job_title,
        role=user.role.value,
        status=user.status.value,
        profile_picture_url=user.profile_picture_url,
        profile_picture_thumbnail_url=user.profile_picture_thumbnail_url,
        is_verified=user.is_verified,
        is_2fa_enabled=user.is_2fa_enabled,
        client_id=user.client_id,
        created_at=user.created_at,
        last_login=user.last_login,
    )
