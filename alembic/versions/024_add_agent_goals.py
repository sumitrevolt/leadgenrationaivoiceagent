"""Add agent_goals table — Goal Hierarchy (Paperclip ADOPT #1, 2026-08-19).

Revision ID: 024_add_agent_goals
Revises: 023_add_prospective_memory

Additive + idempotent (023/021 ka same pattern). Rollback drops the table if
present. Table is INERT until goals are created via /api/goals — creating it
changes no running behaviour. Column set mirrors app/models/agent_goal.py
(create_all for DB_CREATE_ALL=1 envs; this migration serves Alembic-only envs).
"""

import sqlalchemy as sa

from alembic import op

revision = "024_add_agent_goals"
down_revision = "023_add_prospective_memory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "agent_goals" in inspector.get_table_names():
        return

    op.create_table(
        "agent_goals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text(), server_default=""),
        sa.Column("level", sa.String(20), nullable=False, server_default="company"),
        sa.Column("status", sa.String(20), nullable=False, server_default="planned"),
        sa.Column("parent_goal_id", sa.String(36), nullable=True),
        sa.Column("owner_agent_id", sa.String(40), nullable=True),
        sa.Column("client_id", sa.String(64), nullable=True),
        sa.Column("campaign_id", sa.String(64), nullable=True),
        sa.Column("target_metric", sa.String(300), server_default=""),
        sa.Column("progress_notes", sa.Text(), server_default="[]"),
        sa.Column("linked_task_ids", sa.Text(), server_default="[]"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("achieved_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_agent_goals_level_status", "agent_goals", ["level", "status"])
    op.create_index("ix_agent_goals_parent", "agent_goals", ["parent_goal_id"])
    op.create_index("ix_agent_goals_client", "agent_goals", ["client_id"])
    op.create_index("ix_agent_goals_created", "agent_goals", ["created_at"])


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "agent_goals" not in inspector.get_table_names():
        return
    op.drop_index("ix_agent_goals_created", table_name="agent_goals")
    op.drop_index("ix_agent_goals_client", table_name="agent_goals")
    op.drop_index("ix_agent_goals_parent", table_name="agent_goals")
    op.drop_index("ix_agent_goals_level_status", table_name="agent_goals")
    op.drop_table("agent_goals")
