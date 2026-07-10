"""Add the canonical Claude-managed development task ledger (Phase 1)."""

import sqlalchemy as sa

from alembic import op

revision = "015_add_dev_tasks"
down_revision = "014_add_automation_log_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dev_tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("idempotency_key", sa.String(180), nullable=False),
        sa.Column("parent_objective", sa.String(4000), nullable=False),
        sa.Column("customer_id", sa.String(36), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(40), nullable=False),
        sa.Column("selected_provider", sa.String(60), nullable=True),
        sa.Column("selected_model", sa.String(180), nullable=True),
        sa.Column("fallback_models", sa.Text(), nullable=True),
        sa.Column("estimated_cost_usd", sa.Numeric(12, 6), nullable=True),
        sa.Column("actual_cost_usd", sa.Numeric(12, 6), nullable=True),
        sa.Column("estimated_input_tokens", sa.Integer(), nullable=True),
        sa.Column("estimated_output_tokens", sa.Integer(), nullable=True),
        sa.Column("actual_input_tokens", sa.Integer(), nullable=True),
        sa.Column("actual_output_tokens", sa.Integer(), nullable=True),
        sa.Column("worktree_path", sa.String(500), nullable=True),
        sa.Column("branch_name", sa.String(180), nullable=True),
        sa.Column("file_ownership", sa.Text(), nullable=True),
        sa.Column("dependencies", sa.Text(), nullable=True),
        sa.Column("acceptance_criteria", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("lease_owner", sa.String(120), nullable=True),
        sa.Column("lease_until", sa.DateTime(), nullable=True),
        sa.Column("test_evidence", sa.Text(), nullable=True),
        sa.Column("deployment_evidence", sa.Text(), nullable=True),
        sa.Column("delivery_evidence", sa.Text(), nullable=True),
        sa.Column("worker_report", sa.Text(), nullable=True),
        sa.Column("blocked_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("idempotency_key", name="uq_dev_tasks_idempotency_key"),
    )
    op.create_index("ix_dev_tasks_customer_id", "dev_tasks", ["customer_id"])
    op.create_index("ix_dev_tasks_priority", "dev_tasks", ["priority"])
    op.create_index("ix_dev_tasks_state", "dev_tasks", ["state"])
    op.create_index("ix_dev_tasks_created_at", "dev_tasks", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_dev_tasks_created_at", table_name="dev_tasks")
    op.drop_index("ix_dev_tasks_state", table_name="dev_tasks")
    op.drop_index("ix_dev_tasks_priority", table_name="dev_tasks")
    op.drop_index("ix_dev_tasks_customer_id", table_name="dev_tasks")
    op.drop_table("dev_tasks")
