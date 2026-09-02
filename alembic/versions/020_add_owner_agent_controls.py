"""Add Owner OS per-agent execution controls (V1.1 Isha slice).

Revision ID: 020_add_owner_agent_controls
Revises: 019_add_owner_os_tables

Additive + idempotent. Rollback drops owner_agent_controls if present.
"""

import sqlalchemy as sa

from alembic import op

revision = "020_add_owner_agent_controls"
down_revision = "019_add_owner_os_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "owner_agent_controls" in tables:
        return
    op.create_table(
        "owner_agent_controls",
        sa.Column("agent_id", sa.String(40), primary_key=True),
        sa.Column("manual_pause", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("scheduled_pause", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("stop_claims", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("drain", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("drain_state", sa.String(20), nullable=False, server_default="idle"),
        sa.Column("reason", sa.String(200)),
        sa.Column("changed_by", sa.String(120)),
        sa.Column("changed_at", sa.DateTime()),
        sa.Column("expiry", sa.DateTime()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("meta_json", sa.Text()),
    )
    op.create_index("ix_owner_agent_controls_drain_state", "owner_agent_controls", ["drain_state"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "owner_agent_controls" in tables:
        op.drop_table("owner_agent_controls")
