"""Add Product One Delivery OS fields to clients table (ADR-064, 2026-07-09).

Idempotent: skip columns that already exist.

Revision ID: 012_add_client_delivery_fields
Revises: 011_add_customer_deliverable
"""

import sqlalchemy as sa

from alembic import op

revision = "012_add_client_delivery_fields"
down_revision = "011_add_customer_deliverable"
branch_labels = None
depends_on = None

DELIVERY_COLUMNS = [
    ("delivery_stage", sa.String(50)),
    ("onboarding_status", sa.String(50)),
    ("social_setup_status", sa.String(50)),
    ("content_generation_status", sa.String(50)),
    ("approval_status", sa.String(50)),
    ("posting_status", sa.String(50)),
    ("report_status", sa.String(50)),
    ("last_delivery_at", sa.String(50)),
    ("next_action", sa.String(255)),
    ("blocking_reason", sa.String(255)),
    ("assigned_agent", sa.String(100)),
    ("automation_health", sa.String(50)),
    ("setup_completed_at", sa.String(50)),
]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_cols = {c["name"] for c in inspector.get_columns("clients")}

    for col_name, col_type in DELIVERY_COLUMNS:
        if col_name not in existing_cols:
            op.add_column("clients", sa.Column(col_name, col_type, nullable=True))


def downgrade() -> None:
    try:
        for col_name, _ in DELIVERY_COLUMNS:
            op.drop_column("clients", col_name)
    except Exception:
        pass
