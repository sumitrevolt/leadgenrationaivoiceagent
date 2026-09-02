"""add billing_records ledger table (BillingRecord model)

The minute-metering / MRR ledger (app/models/billing_record.py) had no migration —
it only got created at runtime by create_all(). This adds it to the Alembic history so
fresh, migration-driven setups get the table too. IDEMPOTENT: if the table already
exists (create_all built it on the live SQLite DB), upgrade is a no-op — safe to run
on the existing production database without "table already exists" errors.

Revision ID: 005_add_billing_records
Revises: 004_add_data_credits
Create Date: 2026-06-09
"""

import sqlalchemy as sa

from alembic import op

revision = "005_add_billing_records"
down_revision = "004_add_data_credits"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "billing_records" in sa.inspect(bind).get_table_names():
        return  # already present (create_all) — idempotent no-op

    op.create_table(
        "billing_records",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "client_id", sa.String(length=36), sa.ForeignKey("clients.id"), nullable=False
        ),
        sa.Column("client_name", sa.String(length=255)),
        sa.Column("campaign_id", sa.String(length=36), sa.ForeignKey("campaigns.id")),
        # record_type / status are SQLAlchemy Enums on the model. They are persisted as
        # short strings; we declare them as String here so the column is portable across
        # SQLite/Postgres and never conflicts with what the ORM writes (no strict CHECK).
        sa.Column("record_type", sa.String(length=20)),
        sa.Column("status", sa.String(length=20)),
        sa.Column("period_year", sa.Integer()),
        sa.Column("period_month", sa.Integer()),
        sa.Column("amount", sa.Integer(), server_default="0"),
        sa.Column("cost", sa.Integer(), server_default="0"),
        sa.Column("quantity", sa.Integer(), server_default="1"),
        sa.Column("currency", sa.String(length=10), server_default="INR"),
        sa.Column("description", sa.String(length=500)),
        sa.Column("reference_id", sa.String(length=100)),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("updated_at", sa.DateTime()),
        sa.Column("billed_at", sa.DateTime()),
        sa.Column("paid_at", sa.DateTime()),
    )
    op.create_index("ix_billing_client", "billing_records", ["client_id"])
    op.create_index("ix_billing_period", "billing_records", ["period_year", "period_month"])
    op.create_index("ix_billing_type_status", "billing_records", ["record_type", "status"])


def downgrade() -> None:
    bind = op.get_bind()
    if "billing_records" not in sa.inspect(bind).get_table_names():
        return
    for ix in ("ix_billing_type_status", "ix_billing_period", "ix_billing_client"):
        try:
            op.drop_index(ix, table_name="billing_records")
        except Exception:
            pass
    op.drop_table("billing_records")
