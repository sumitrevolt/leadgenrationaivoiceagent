"""Lead status-history audit table (F-DB3, production audit 2026-07-01).

Idempotent: skip if table already exists (create_all on live DB).
Forward-only — no backfill of pre-existing status changes.
Revision ID: 007_add_lead_status_history
Revises: 006_flywheel_enterprise
"""

import sqlalchemy as sa

from alembic import op

revision = "007_add_lead_status_history"
down_revision = "006_flywheel_enterprise"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())

    if "lead_status_history" not in existing:
        op.create_table(
            "lead_status_history",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "lead_id", sa.String(36), sa.ForeignKey("leads.id"), nullable=False, index=True
            ),
            sa.Column("old_status", sa.String(30), nullable=True),
            sa.Column("new_status", sa.String(30), nullable=False),
            sa.Column("changed_by", sa.String(100), nullable=True),
            sa.Column("changed_at", sa.DateTime()),
        )
        op.create_index(
            "ix_lead_status_history_changed_at", "lead_status_history", ["changed_at"]
        )


def downgrade() -> None:
    try:
        op.drop_table("lead_status_history")
    except Exception:
        pass
