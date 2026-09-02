"""Add automation_logs.evidence_url (ADR-068, 2026-07-09).

Proof artifact URL/path for an automation run (report HTML, published post URL).
Idempotent: skip if the column already exists. Additive, nullable — safe on a
live Postgres (instant metadata-only ADD COLUMN) and on SQLite.

Revision ID: 014_add_automation_log_evidence
Revises: 013_add_automation_logs
"""

import sqlalchemy as sa

from alembic import op

revision = "014_add_automation_log_evidence"
down_revision = "013_add_automation_logs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "automation_logs" not in set(insp.get_table_names()):
        return
    cols = {c["name"] for c in insp.get_columns("automation_logs")}
    if "evidence_url" not in cols:
        op.add_column(
            "automation_logs",
            sa.Column("evidence_url", sa.String(500), nullable=True),
        )


def downgrade() -> None:
    try:
        op.drop_column("automation_logs", "evidence_url")
    except Exception:
        pass
