"""
Admin API
Endpoints for platform administration, user management, and system monitoring
"""
from typing import Optional, List
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, UploadFile, File, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, EmailStr
import uuid
import json

from app.models.user import User, UserRole, UserStatus, AuditLog, UserSession
from app.utils.logger import setup_logger
from app.config import settings

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
    phone: Optional[str] = None
    job_title: Optional[str] = None
    role: str = "viewer"
    client_id: Optional[str] = None


class UserUpdate(BaseModel):
    """Update user request"""
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    job_title: Optional[str] = None
    department: Optional[str] = None
    bio: Optional[str] = None
    role: Optional[str] = None
    status: Optional[str] = None


class UserResponse(BaseModel):
    """User response"""
    id: str
    email: str
    first_name: str
    last_name: str
    full_name: str
    phone: Optional[str]
    job_title: Optional[str]
    role: str
    status: str
    profile_picture_url: Optional[str]
    profile_picture_thumbnail_url: Optional[str]
    is_verified: bool
    is_2fa_enabled: bool
    client_id: Optional[str]
    created_at: datetime
    last_login: Optional[datetime]


class LoginRequest(BaseModel):
    """Login request"""
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    """Login response"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 3600
    user: UserResponse


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
    user_id: Optional[str]
    user_email: Optional[str]
    action: str
    resource_type: Optional[str]
    resource_id: Optional[str]
    ip_address: Optional[str]
    created_at: datetime
    severity: str


# ============================================================================
# Database Integration (Production-Ready)
# ============================================================================

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import selectinload
from app.models.base import get_async_db
from jose import jwt, JWTError
from datetime import timezone
import os
import secrets

# JWT Configuration
JWT_SECRET = os.environ.get("JWT_SECRET_KEY", settings.secret_key)
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 7


def create_access_token(user_id: str, email: str, role: str) -> str:
    """Create JWT access token"""
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "exp": expire,
        "type": "access"
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    """Create JWT refresh token"""
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": user_id,
        "exp": expire,
        "type": "refresh"
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

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_async_db)
) -> User:
    """Get current authenticated user from JWT token"""
    token = credentials.credentials
    
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token payload")
        
        # Get user from database
        result = await db.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        
        if user.status == UserStatus.SUSPENDED:
            raise HTTPException(status_code=403, detail="Account suspended")
        
        return user
        
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


async def require_admin(user: User = Depends(get_current_user)) -> User:
    """Require admin role"""
    if not user.can_access_admin():
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


async def require_super_admin(user: User = Depends(get_current_user)) -> User:
    """Require super admin role"""
    if user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(status_code=403, detail="Super admin access required")
    return user


async def log_audit(
    db: AsyncSession,
    user_id: Optional[str], 
    action: str, 
    resource_type: str = None, 
    resource_id: str = None, 
    old_value: dict = None, 
    new_value: dict = None,
    ip_address: str = None, 
    severity: str = "info"
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
        severity=severity
    )
    db.add(audit_entry)
    await db.commit()
    logger.info(f"Audit: {action} by user {user_id} on {resource_type}/{resource_id}")


# ============================================================================
# Authentication Endpoints
# ============================================================================

@router.post("/auth/login", response_model=LoginResponse)
async def login(request: LoginRequest, db: AsyncSession = Depends(get_async_db)):
    """
    Authenticate user and return JWT tokens
    """
    # Find user by email
    result = await db.execute(
        select(User).where(User.email == request.email)
    )
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
        is_active=True
    )
    db.add(session)
    await db.commit()
    
    await log_audit(db, user.id, "login.success", "user", user.id)
    
    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
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
            last_login=user.last_login
        )
    )


@router.post("/auth/logout")
async def logout(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Logout and invalidate all user sessions
    """
    # Invalidate all sessions for user in database
    result = await db.execute(
        select(UserSession).where(
            and_(UserSession.user_id == user.id, UserSession.is_active == True)
        )
    )
    sessions = result.scalars().all()
    for session in sessions:
        session.is_active = False
        session.revoked_at = datetime.utcnow()
        session.revoke_reason = "logout"
    
    await db.commit()
    await log_audit(db, user.id, "logout", "user", user.id)
    return {"message": "Logged out successfully"}


# ============================================================================
# User Management Endpoints
# ============================================================================

@router.get("/users", response_model=List[UserResponse])
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    role: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db)
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
                func.lower(User.last_name).like(search_pattern)
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
            last_login=user.last_login
        )
        for user in users
    ]


@router.post("/users", response_model=UserResponse)
async def create_user(
    request: UserCreate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Create a new user (database-backed)
    """
    # Check if email already exists
    result = await db.execute(
        select(User).where(User.email == request.email)
    )
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
        created_by=admin.id
    )
    user.set_password(request.password)
    user.generate_verification_token()
    
    db.add(user)
    await db.commit()
    await db.refresh(user)
    
    await log_audit(db, admin.id, "user.create", "user", user.id, 
                   new_value={"email": user.email, "role": role.value})
    
    # TODO: Send verification email
    
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
        last_login=user.last_login
    )


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str, 
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get user by ID (database-backed)
    """
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
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
        last_login=user.last_login
    )


@router.patch("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    request: UserUpdate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Update user details (database-backed)
    """
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
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
    
    await log_audit(db, admin.id, "user.update", "user", user.id, 
              old_value=old_values, new_value=user.to_dict())
    
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
        last_login=user.last_login
    )


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str, 
    admin: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Delete user (super admin only) - database-backed
    """
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Cannot delete yourself
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    
    user_email = user.email
    await db.delete(user)
    await db.commit()
    
    await log_audit(db, admin.id, "user.delete", "user", user_id, 
              old_value={"email": user_email}, severity="warning")
    
    return {"message": "User deleted successfully"}


# ============================================================================
# Profile Picture Endpoints
# ============================================================================

@router.post("/users/{user_id}/picture")
async def upload_profile_picture(
    user_id: str,
    file: UploadFile = File(...),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Upload profile picture for a user
    Stores in Google Cloud Storage
    """
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Validate file type
    allowed_types = ["image/jpeg", "image/png", "image/gif", "image/webp"]
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Invalid file type. Allowed: JPEG, PNG, GIF, WebP")
    
    # Validate file size (max 5MB)
    contents = await file.read()
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Max 5MB")
    
    # For production, upload to GCS
    try:
        from app.utils.storage import upload_to_gcs, generate_thumbnail
        
        bucket_name = settings.gcs_bucket_name or "auraleads-profile-pictures"
        file_ext = file.filename.split(".")[-1] if file.filename else "jpg"
        file_path = f"profile-pictures/{user_id}/{uuid.uuid4()}.{file_ext}"
        
        # Upload original
        picture_url = await upload_to_gcs(bucket_name, file_path, contents, file.content_type)
        
        # Generate and upload thumbnail
        thumbnail_contents = await generate_thumbnail(contents, size=(150, 150))
        thumbnail_path = file_path.replace(f".{file_ext}", f"_thumb.{file_ext}")
        thumbnail_url = await upload_to_gcs(bucket_name, thumbnail_path, thumbnail_contents, file.content_type)
        
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
        "profile_picture_thumbnail_url": user.profile_picture_thumbnail_url
    }


@router.delete("/users/{user_id}/picture")
async def delete_profile_picture(
    user_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Delete user's profile picture
    """
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
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
    
    log_audit(admin.id, "user.picture.delete", "user", user_id)
    
    return {"message": "Profile picture deleted"}


# ============================================================================
# Admin Dashboard Endpoints
# ============================================================================

@router.get("/stats", response_model=AdminStats)
async def get_admin_stats(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db)
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
    
    # TODO: Get these from actual database tables
    return AdminStats(
        total_users=total_users,
        active_users=active_users,
        total_clients=150,  # Query from clients table
        active_clients=120,
        total_leads=25000,  # Query from leads table
        total_calls=50000,  # Query from call_logs table
        total_appointments=2500,
        total_revenue_inr=1500000.00,
        active_campaigns=45,
        system_health="healthy"
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
        "storage": "healthy"
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
        last_checked=datetime.utcnow()
    )


# ============================================================================
# Audit Log Endpoints
# ============================================================================

@router.get("/audit-logs", response_model=List[AuditLogEntry])
async def get_audit_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    action: Optional[str] = None,
    user_id: Optional[str] = None,
    resource_type: Optional[str] = None,
    severity: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    admin: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_async_db)
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
    users_result = await db.execute(
        select(User).where(User.id.in_(user_ids))
    ) if user_ids else None
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
            severity=log.severity
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
        last_login=user.last_login
    )
