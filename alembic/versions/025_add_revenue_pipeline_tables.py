"""add revenue pipeline tables

Revision ID: 025
Revises: 024
Create Date: 2026-08-31 16:45:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "025"
down_revision = "024_add_agent_goals"
branch_labels = None
depends_on = None


def upgrade():
    # 1. Create revenue_lead_records table
    op.create_table(
        "revenue_lead_records",
        sa.Column("lead_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=64), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column("niche", sa.String(length=128), nullable=False),
        sa.Column("score", sa.Integer(), nullable=True, default=0),
        sa.Column("kanban_state", sa.String(length=64), nullable=False, default="DISCOVERED"),
        sa.Column("outreach_channel", sa.String(length=64), nullable=True, default="email"),
        sa.Column("outreach_draft", sa.Text(), nullable=True),
        sa.Column("provider_action_id", sa.String(length=128), nullable=True),
        sa.Column("provider_response_payload", sa.JSON(), nullable=True),
        sa.Column("payment_evidence", sa.JSON(), nullable=True),
        sa.Column("suppression_status", sa.String(length=64), nullable=True, default="CLEARED"),
        sa.Column("task_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.Float(), nullable=True),
        sa.Column("updated_at", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("lead_id"),
    )
    op.create_index("ix_revenue_lead_records_lead_id", "revenue_lead_records", ["lead_id"], unique=False)
    op.create_index("ix_revenue_lead_records_tenant_id", "revenue_lead_records", ["tenant_id"], unique=False)
    op.create_index("ix_revenue_lead_records_phone", "revenue_lead_records", ["phone"], unique=False)
    op.create_index("ix_revenue_lead_records_email", "revenue_lead_records", ["email"], unique=False)
    op.create_index("ix_revenue_lead_records_domain", "revenue_lead_records", ["domain"], unique=False)
    op.create_index("ix_revenue_lead_records_niche", "revenue_lead_records", ["niche"], unique=False)
    op.create_index("ix_revenue_lead_records_kanban_state", "revenue_lead_records", ["kanban_state"], unique=False)
    op.create_index("ix_revenue_lead_records_provider_action_id", "revenue_lead_records", ["provider_action_id"], unique=False)

    # 2. Create revenue_audit_logs table
    op.create_table(
        "revenue_audit_logs",
        sa.Column("audit_id", sa.String(length=64), nullable=False),
        sa.Column("lead_id", sa.String(length=64), nullable=False),
        sa.Column("actor_bot", sa.String(length=64), nullable=False),
        sa.Column("previous_state", sa.String(length=64), nullable=False),
        sa.Column("next_state", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("task_id", sa.String(length=128), nullable=True),
        sa.Column("evidence_id", sa.String(length=128), nullable=True),
        sa.Column("timestamp", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("audit_id"),
    )
    op.create_index("ix_revenue_audit_logs_audit_id", "revenue_audit_logs", ["audit_id"], unique=False)
    op.create_index("ix_revenue_audit_logs_lead_id", "revenue_audit_logs", ["lead_id"], unique=False)
    op.create_index("ix_revenue_audit_logs_actor_bot", "revenue_audit_logs", ["actor_bot"], unique=False)
    op.create_index("ix_revenue_audit_logs_timestamp", "revenue_audit_logs", ["timestamp"], unique=False)


def downgrade():
    op.drop_table("revenue_audit_logs")
    op.drop_table("revenue_lead_records")
