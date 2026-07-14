"""Add approval notification audit table.

Revision ID: 018_add_approval_notifications
Revises: 017_add_lead_pipeline_tables

Additive and idempotent: production uses Alembic-only schema management
(`DB_CREATE_ALL=0`), so the model added in 2026-07-12 must have an explicit
migration before approval reminders can be enabled safely.
"""

import sqlalchemy as sa

from alembic import op

revision = "018_add_approval_notifications"
down_revision = "017_add_lead_pipeline_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "approval_notifications" in set(inspector.get_table_names()):
        return

    op.create_table(
        "approval_notifications",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("client_id", sa.String(64)),
        sa.Column("approval_id", sa.String(64), nullable=False),
        sa.Column("approval_version", sa.String(64)),
        sa.Column("channel", sa.String(20), nullable=False, server_default="email"),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="attempted"),
        sa.Column("failure_category", sa.String(50)),
        sa.Column("provider_message_id", sa.String(255)),
        sa.Column("attempts", sa.Integer(), server_default="1"),
        sa.Column("attempted_at", sa.DateTime()),
        sa.Column("completed_at", sa.DateTime()),
        sa.Column("meta_json", sa.Text()),
    )
    op.create_index(
        "ix_approval_notifications_idempotency_key",
        "approval_notifications",
        ["idempotency_key"],
        unique=True,
    )
    op.create_index(
        "ix_approval_notifications_client_id",
        "approval_notifications",
        ["client_id"],
    )
    op.create_index(
        "ix_approval_notifications_approval_id",
        "approval_notifications",
        ["approval_id"],
    )
    op.create_index(
        "ix_approval_notifications_status",
        "approval_notifications",
        ["status"],
    )
    op.create_index(
        "ix_approval_notifications_attempted_at",
        "approval_notifications",
        ["attempted_at"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "approval_notifications" in set(inspector.get_table_names()):
        op.drop_table("approval_notifications")
