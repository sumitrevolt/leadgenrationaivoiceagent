"""Add agent_tasks table — Paperclip-inspired per-agent work queue.

Revision ID: 021_add_agent_tasks
Revises: 020_add_owner_agent_controls

Additive + idempotent. Rollback drops agent_tasks if present.
"""

import sqlalchemy as sa

from alembic import op

revision = "021_add_agent_tasks"
down_revision = "020_add_owner_agent_controls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "agent_tasks" in inspector.get_table_names():
        return

    op.create_table(
        "agent_tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("agent_id", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("goal", sa.String(500), nullable=False, server_default=""),
        sa.Column("result_summary", sa.Text(), server_default=""),
        sa.Column("client_id", sa.String(36), nullable=True),
        sa.Column("campaign_id", sa.String(36), nullable=True),
        sa.Column("goal_text", sa.String(500), server_default=""),
        sa.Column("parent_task_id", sa.String(36), nullable=True),
        sa.Column("delegated_by", sa.String(40), nullable=True),
        sa.Column("delegated_to", sa.String(40), nullable=True),
        sa.Column("cost_tokens_in", sa.Integer(), server_default="0"),
        sa.Column("cost_tokens_out", sa.Integer(), server_default="0"),
        sa.Column("cost_usd", sa.Float(), server_default="0.0"),
        sa.Column("provider", sa.String(40), server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("claimed_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("checkout_version", sa.Integer(), server_default="0"),
    )
    op.create_index("ix_agent_tasks_agent_status", "agent_tasks", ["agent_id", "status"])
    op.create_index("ix_agent_tasks_status", "agent_tasks", ["status"])
    op.create_index("ix_agent_tasks_client", "agent_tasks", ["client_id"])
    op.create_index("ix_agent_tasks_created", "agent_tasks", ["created_at"])


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "agent_tasks" not in inspector.get_table_names():
        return
    op.drop_index("ix_agent_tasks_created", table_name="agent_tasks")
    op.drop_index("ix_agent_tasks_client", table_name="agent_tasks")
    op.drop_index("ix_agent_tasks_status", table_name="agent_tasks")
    op.drop_index("ix_agent_tasks_agent_status", table_name="agent_tasks")
    op.drop_table("agent_tasks")
