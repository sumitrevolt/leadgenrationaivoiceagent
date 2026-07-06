"""delivery_events table (customer-facing delivery ledger, sub-project 1 of
Customer Delivery OS, 2026-07-06).

Mirrors 008_add_agents_agent_events.py's idempotent pattern: only creates the
table when genuinely absent (fresh DB / DR restore), never ALTERs an existing
table — zero column-drift risk against the live VPS.

Revision ID: 011_add_delivery_events
Revises: 010_enum_columns_to_varchar
"""

import sqlalchemy as sa

from alembic import op

revision = "011_add_delivery_events"
down_revision = "010_enum_columns_to_varchar"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())

    if "delivery_events" not in existing:
        op.create_table(
            "delivery_events",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("client_id", sa.String(40), nullable=False),
            sa.Column("event_type", sa.String(40), nullable=False, server_default="event"),
            sa.Column("detail", sa.String(500), server_default=""),
            sa.Column("status", sa.String(10), server_default="ok"),
            sa.Column("meta_json", sa.Text(), server_default="{}"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index(
            "ix_delivery_events_client_time", "delivery_events", ["client_id", "created_at"]
        )
        op.create_index("ix_delivery_events_time", "delivery_events", ["created_at"])


def downgrade() -> None:
    try:
        op.drop_table("delivery_events")
    except Exception:
        pass
