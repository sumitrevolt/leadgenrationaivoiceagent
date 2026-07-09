"""Add automation_logs table (ADR-064, 2026-07-09).

Idempotent: skip if table already exists.

Revision ID: 013_add_automation_logs
Revises: 012_add_client_delivery_fields
"""

import sqlalchemy as sa

from alembic import op

revision = "013_add_automation_logs"
down_revision = "012_add_client_delivery_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())

    if "automation_logs" not in existing:
        op.create_table(
            "automation_logs",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("client_id", sa.String(36), nullable=True),
            sa.Column("job_type", sa.String(100), nullable=False),
            sa.Column("status", sa.String(20), nullable=False),
            sa.Column("started_at", sa.String(50)),
            sa.Column("finished_at", sa.String(50)),
            sa.Column("duration_ms", sa.Integer()),
            sa.Column("input_summary", sa.Text()),
            sa.Column("output_summary", sa.Text()),
            sa.Column("error_message", sa.Text()),
            sa.Column("retry_count", sa.Integer()),
            sa.Column("next_retry_at", sa.String(50)),
            sa.Column("triggered_by", sa.String(50)),
            sa.Column("meta_json", sa.Text()),
            sa.Column("created_at", sa.DateTime()),
        )
        op.create_index("ix_automation_logs_client_id", "automation_logs", ["client_id"])
        op.create_index("ix_automation_logs_job_type", "automation_logs", ["job_type"])
        op.create_index("ix_automation_logs_status", "automation_logs", ["status"])
        op.create_index("ix_automation_logs_created_at", "automation_logs", ["created_at"])


def downgrade() -> None:
    try:
        op.drop_table("automation_logs")
    except Exception:
        pass
