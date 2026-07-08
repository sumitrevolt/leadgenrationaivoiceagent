"""Add customer_deliverables table (F-DB5, production audit 2026-07-08).

Idempotent: skip if table already exists.

Revision ID: 011_add_customer_deliverable
Revises: 010_enum_columns_to_varchar
"""

import sqlalchemy as sa

from alembic import op

revision = "011_add_customer_deliverable"
down_revision = "010_enum_columns_to_varchar"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())

    if "customer_deliverables" not in existing:
        op.create_table(
            "customer_deliverables",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("client_id", sa.String(36), sa.ForeignKey("clients.id"), nullable=False),
            sa.Column("plan_code", sa.String(50)),
            sa.Column("billing_cycle_month", sa.String(7)),
            sa.Column("deliverable_type", sa.String(100)),
            sa.Column("title", sa.String(255)),
            sa.Column("description", sa.Text()),
            sa.Column("status", sa.String(50), nullable=False, server_default="not_started"),
            sa.Column("channel", sa.String(50), nullable=False, server_default="dashboard"),
            sa.Column("due_date", sa.DateTime()),
            sa.Column("delivered_at", sa.DateTime()),
            sa.Column("evidence_url", sa.String(500)),
            sa.Column("evidence_payload", sa.Text()),
            sa.Column("approval_id", sa.String(36)),
            sa.Column("automation_run_id", sa.String(36)),
            sa.Column("error_message", sa.Text()),
            sa.Column("next_action", sa.Text()),
            sa.Column("owner", sa.String(50)),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_customer_deliverables_client", "customer_deliverables", ["client_id"])
        op.create_index("ix_customer_deliverables_status", "customer_deliverables", ["status"])
        op.create_index("ix_customer_deliverables_cycle", "customer_deliverables", ["client_id", "billing_cycle_month"])


def downgrade() -> None:
    try:
        op.drop_table("customer_deliverables")
    except Exception:
        pass
