"""Add the per-attempt dev-task usage/cost ledger (Phase 2)."""

import sqlalchemy as sa

from alembic import op

revision = "016_add_dev_task_usage"
down_revision = "015_add_dev_tasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dev_task_usage",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("task_id", sa.String(36), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(60), nullable=False),
        sa.Column("model", sa.String(180), nullable=True),
        sa.Column("outcome", sa.String(40), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=True),
        sa.Column("estimated", sa.Boolean(), nullable=False),
        sa.Column("scope", sa.String(160), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_dev_task_usage_task_id", "dev_task_usage", ["task_id"])
    op.create_index("ix_dev_task_usage_outcome", "dev_task_usage", ["outcome"])
    op.create_index("ix_dev_task_usage_created_at", "dev_task_usage", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_dev_task_usage_created_at", table_name="dev_task_usage")
    op.drop_index("ix_dev_task_usage_outcome", table_name="dev_task_usage")
    op.drop_index("ix_dev_task_usage_task_id", table_name="dev_task_usage")
    op.drop_table("dev_task_usage")
