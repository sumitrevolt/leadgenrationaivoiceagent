"""Add request_depth column to agent_tasks (Paperclip org chart depth tracking).

Revision ID: 022_add_request_depth
Revises: 021_add_agent_tasks
"""

import sqlalchemy as sa

from alembic import op

revision = "022_add_request_depth"
down_revision = "021_add_agent_tasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent — skip if column already exists
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "agent_tasks" in inspector.get_table_names():
        columns = [c["name"] for c in inspector.get_columns("agent_tasks")]
        if "request_depth" not in columns:
            op.add_column(
                "agent_tasks", sa.Column("request_depth", sa.Integer(), server_default="0")
            )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "agent_tasks" in inspector.get_table_names():
        columns = [c["name"] for c in inspector.get_columns("agent_tasks")]
        if "request_depth" in columns:
            op.drop_column("agent_tasks", "request_depth")
