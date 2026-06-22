"""add user tables

Revision ID: 002_add_users
Create Date: 2026-01-03

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = '002_add_users'
down_revision = '001_initial'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create users table
    op.create_table(
        'users',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('email', sa.String(255), nullable=False, unique=True, index=True),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('password_salt', sa.String(64), nullable=False),
        
        # Profile
        sa.Column('first_name', sa.String(100), nullable=False),
        sa.Column('last_name', sa.String(100), nullable=False),
        sa.Column('display_name', sa.String(200)),
        sa.Column('phone', sa.String(20)),
        sa.Column('job_title', sa.String(100)),
        sa.Column('department', sa.String(100)),
        sa.Column('bio', sa.Text),
        
        # Profile picture
        sa.Column('profile_picture_url', sa.String(500)),
        sa.Column('profile_picture_thumbnail_url', sa.String(500)),
        sa.Column('profile_picture_bucket', sa.String(255)),
        sa.Column('profile_picture_path', sa.String(500)),
        
        # Role and status
        sa.Column('role', sa.Enum('super_admin', 'admin', 'manager', 'agent', 'viewer', name='userrole'), 
                  default='viewer', nullable=False),
        sa.Column('status', sa.Enum('active', 'inactive', 'suspended', 'pending', name='userstatus'),
                  default='pending', nullable=False),
        sa.Column('is_verified', sa.Boolean, default=False),
        sa.Column('is_2fa_enabled', sa.Boolean, default=False),
        sa.Column('two_fa_secret', sa.String(32)),
        
        # Client association
        sa.Column('client_id', sa.String(36), sa.ForeignKey('clients.id'), nullable=True),
        
        # Session management
        sa.Column('refresh_token', sa.String(255)),
        sa.Column('token_expires_at', sa.DateTime),
        sa.Column('last_login', sa.DateTime),
        sa.Column('last_login_ip', sa.String(45)),
        sa.Column('failed_login_attempts', sa.Integer, default=0),
        sa.Column('locked_until', sa.DateTime),
        
        # Preferences (JSON)
        sa.Column('preferences', sa.Text),
        sa.Column('notification_settings', sa.Text),
        
        # Timestamps
        sa.Column('created_at', sa.DateTime, default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column('created_by', sa.String(36)),
        sa.Column('last_active_at', sa.DateTime),
        
        # Email verification
        sa.Column('email_verification_token', sa.String(64)),
        sa.Column('email_verified_at', sa.DateTime),
        
        # Password reset
        sa.Column('password_reset_token', sa.String(64)),
        sa.Column('password_reset_expires', sa.DateTime),
    )
    
    # Create user_sessions table
    op.create_table(
        'user_sessions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False, index=True),
        
        # Session info
        sa.Column('access_token_hash', sa.String(64), nullable=False),
        sa.Column('refresh_token_hash', sa.String(64), nullable=False),
        sa.Column('device_info', sa.Text),
        sa.Column('ip_address', sa.String(45)),
        sa.Column('location', sa.String(200)),
        
        # Timestamps
        sa.Column('created_at', sa.DateTime, default=sa.func.now()),
        sa.Column('expires_at', sa.DateTime, nullable=False),
        sa.Column('last_used_at', sa.DateTime, default=sa.func.now()),
        sa.Column('revoked_at', sa.DateTime),
        
        # Status
        sa.Column('is_active', sa.Boolean, default=True),
        sa.Column('revoke_reason', sa.String(100)),
    )
    
    # Create audit_logs table
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=True, index=True),
        
        # Action details
        sa.Column('action', sa.String(100), nullable=False, index=True),
        sa.Column('resource_type', sa.String(50)),
        sa.Column('resource_id', sa.String(36)),
        
        # What changed
        sa.Column('old_value', sa.Text),
        sa.Column('new_value', sa.Text),
        
        # Context
        sa.Column('ip_address', sa.String(45)),
        sa.Column('user_agent', sa.Text),
        sa.Column('request_id', sa.String(36)),
        
        # Timestamp
        sa.Column('created_at', sa.DateTime, default=sa.func.now(), index=True),
        
        # Severity
        sa.Column('severity', sa.String(20), default='info'),
    )
    
    # Create indexes for performance
    op.create_index('ix_users_client_id', 'users', ['client_id'])
    op.create_index('ix_users_role', 'users', ['role'])
    op.create_index('ix_users_status', 'users', ['status'])
    op.create_index('ix_audit_logs_resource', 'audit_logs', ['resource_type', 'resource_id'])


def downgrade() -> None:
    op.drop_index('ix_audit_logs_resource')
    op.drop_index('ix_users_status')
    op.drop_index('ix_users_role')
    op.drop_index('ix_users_client_id')
    op.drop_table('audit_logs')
    op.drop_table('user_sessions')
    op.drop_table('users')
    op.execute('DROP TYPE IF EXISTS userrole')
    op.execute('DROP TYPE IF EXISTS userstatus')
