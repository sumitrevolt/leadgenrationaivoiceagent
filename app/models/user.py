"""
User Model
Database model for users with authentication, roles, and profile pictures
"""
from datetime import datetime
from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text, Enum, ForeignKey, LargeBinary
from sqlalchemy.orm import relationship
import enum
import uuid
import secrets
import bcrypt

from app.models.base import Base


class UserRole(enum.Enum):
    """User role enum"""
    SUPER_ADMIN = "super_admin"  # Platform owner
    ADMIN = "admin"  # Company admin
    MANAGER = "manager"  # Team manager
    AGENT = "agent"  # Voice agent operator
    VIEWER = "viewer"  # Read-only access


class UserStatus(enum.Enum):
    """User status enum"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    PENDING = "pending"  # Email verification pending


class User(Base):
    """User database model with profile picture support"""
    __tablename__ = "users"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Authentication
    email = Column(String(255), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)
    password_salt = Column(String(64), nullable=False)
    
    # Profile information
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    display_name = Column(String(200))
    phone = Column(String(20))
    job_title = Column(String(100))
    department = Column(String(100))
    bio = Column(Text)
    
    # Profile picture - stored in Cloud Storage, reference here
    profile_picture_url = Column(String(500))
    profile_picture_thumbnail_url = Column(String(500))
    profile_picture_bucket = Column(String(255))  # GCS bucket name
    profile_picture_path = Column(String(500))  # Path in bucket
    
    # Role and permissions - use values_callable to match PostgreSQL lowercase enum
    role = Column(
        Enum(UserRole, values_callable=lambda x: [e.value for e in x]),
        default=UserRole.VIEWER,
        nullable=False
    )
    status = Column(
        Enum(UserStatus, values_callable=lambda x: [e.value for e in x]),
        default=UserStatus.PENDING,
        nullable=False
    )
    is_verified = Column(Boolean, default=False)
    is_2fa_enabled = Column(Boolean, default=False)
    two_fa_secret = Column(String(32))  # TOTP secret
    
    # Client association (for multi-tenant)
    client_id = Column(String(36), ForeignKey("clients.id"), nullable=True)
    
    # Session management
    refresh_token = Column(String(255))
    token_expires_at = Column(DateTime)
    last_login = Column(DateTime)
    last_login_ip = Column(String(45))  # IPv6 support
    failed_login_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime)
    
    # Preferences (JSON)
    preferences = Column(Text)  # JSON: theme, notifications, timezone, etc.
    notification_settings = Column(Text)  # JSON: email, sms, push settings
    
    # Activity tracking
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(String(36))
    last_active_at = Column(DateTime)
    
    # Email verification
    email_verification_token = Column(String(64))
    email_verified_at = Column(DateTime)
    
    # Password reset
    password_reset_token = Column(String(64))
    password_reset_expires = Column(DateTime)
    
    # Relationships
    # client = relationship("Client", back_populates="users")
    
    @property
    def full_name(self) -> str:
        """Get user's full name"""
        return f"{self.first_name} {self.last_name}"
    
    @staticmethod
    def hash_password(password: str) -> str:
        """Hash password using bcrypt (production-ready)"""
        password_bytes = password.encode('utf-8')
        salt = bcrypt.gensalt(rounds=12)
        hashed = bcrypt.hashpw(password_bytes, salt)
        return hashed.decode('utf-8')
    
    def set_password(self, password: str):
        """Set user password with bcrypt hashing"""
        self.password_hash = self.hash_password(password)
        self.password_salt = ""  # Not needed with bcrypt, but keeping for backward compatibility
    
    def verify_password(self, password: str) -> bool:
        """Verify password against bcrypt hash"""
        try:
            password_bytes = password.encode('utf-8')
            hash_bytes = self.password_hash.encode('utf-8')
            return bcrypt.checkpw(password_bytes, hash_bytes)
        except Exception:
            return False
    
    def generate_verification_token(self) -> str:
        """Generate email verification token"""
        self.email_verification_token = secrets.token_urlsafe(32)
        return self.email_verification_token
    
    def generate_password_reset_token(self) -> str:
        """Generate password reset token"""
        self.password_reset_token = secrets.token_urlsafe(32)
        from datetime import timedelta
        self.password_reset_expires = datetime.utcnow() + timedelta(hours=24)
        return self.password_reset_token
    
    def can_access_admin(self) -> bool:
        """Check if user has admin access"""
        return self.role in [UserRole.SUPER_ADMIN, UserRole.ADMIN]
    
    def has_permission(self, permission: str) -> bool:
        """Check if user has a specific permission"""
        # Permission hierarchy
        permissions_map = {
            UserRole.SUPER_ADMIN: ["*"],  # All permissions
            UserRole.ADMIN: ["manage_users", "manage_campaigns", "view_analytics", "manage_settings", "manage_agents"],
            UserRole.MANAGER: ["manage_campaigns", "view_analytics", "manage_agents"],
            UserRole.AGENT: ["view_campaigns", "make_calls", "view_leads"],
            UserRole.VIEWER: ["view_campaigns", "view_leads", "view_analytics"],
        }
        
        role_permissions = permissions_map.get(self.role, [])
        return "*" in role_permissions or permission in role_permissions
    
    def to_dict(self, include_sensitive: bool = False) -> dict:
        """Convert user to dictionary"""
        data = {
            "id": self.id,
            "email": self.email,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "full_name": self.full_name,
            "display_name": self.display_name or self.full_name,
            "phone": self.phone,
            "job_title": self.job_title,
            "department": self.department,
            "bio": self.bio,
            "profile_picture_url": self.profile_picture_url,
            "profile_picture_thumbnail_url": self.profile_picture_thumbnail_url,
            "role": self.role.value if self.role else None,
            "status": self.status.value if self.status else None,
            "is_verified": self.is_verified,
            "is_2fa_enabled": self.is_2fa_enabled,
            "client_id": self.client_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_login": self.last_login.isoformat() if self.last_login else None,
            "last_active_at": self.last_active_at.isoformat() if self.last_active_at else None,
        }
        
        if include_sensitive:
            data.update({
                "last_login_ip": self.last_login_ip,
                "failed_login_attempts": self.failed_login_attempts,
                "locked_until": self.locked_until.isoformat() if self.locked_until else None,
            })
        
        return data


class UserSession(Base):
    """Track user sessions for security"""
    __tablename__ = "user_sessions"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    
    # Session info
    access_token_hash = Column(String(64), nullable=False)
    refresh_token_hash = Column(String(64), nullable=False)
    device_info = Column(Text)  # User agent, device type
    ip_address = Column(String(45))
    location = Column(String(200))  # City, Country from IP
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    last_used_at = Column(DateTime, default=datetime.utcnow)
    revoked_at = Column(DateTime)
    
    # Status
    is_active = Column(Boolean, default=True)
    revoke_reason = Column(String(100))  # logout, password_change, admin_revoke


class AuditLog(Base):
    """Audit trail for admin actions"""
    __tablename__ = "audit_logs"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    
    # Action details
    action = Column(String(100), nullable=False, index=True)  # e.g., user.create, campaign.delete
    resource_type = Column(String(50))  # user, campaign, client, etc.
    resource_id = Column(String(36))
    
    # What changed
    old_value = Column(Text)  # JSON
    new_value = Column(Text)  # JSON
    
    # Context
    ip_address = Column(String(45))
    user_agent = Column(Text)
    request_id = Column(String(36))  # For tracing
    
    # Timestamp
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Severity
    severity = Column(String(20), default="info")  # info, warning, critical
