"""Add prospective_memory table — durable L6 agent memory (claim/lease/idempotency).

Revision ID: 023_add_prospective_memory
Revises: 022_add_request_depth

Additive + idempotent (021 ka same pattern). Rollback drops the table if present.
Table is INERT until MEMORY_STACK_ENABLED is armed — creating it changes no
running behaviour.
"""

import sqlalchemy as sa

from alembic import op

revision = "023_add_prospective_memory"
down_revision = "022_add_request_depth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "prospective_memory" in inspector.get_table_names():
        return

    op.create_table(
        "prospective_memory",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("agent_id", sa.String(40), nullable=False),
        sa.Column("action", sa.String(500), nullable=False, server_default=""),
        sa.Column("note", sa.String(400), server_default=""),
        sa.Column("payload_json", sa.Text(), server_default="{}"),
        sa.Column("source", sa.String(40), server_default=""),
        sa.Column("due_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("idempotency_key", sa.String(120), nullable=False),
        sa.Column("claimed_by", sa.String(64), nullable=True),
        sa.Column("lease_until", sa.DateTime(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(500), server_default=""),
        sa.Column("dispatched_task_id", sa.String(36), nullable=True),
        sa.Column("checkout_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
        # UNIQUE = duplicate intent collapses to one row (retry-safe enqueue).
        # Declared INSIDE create_table on purpose: SQLite has no ALTER-ADD-CONSTRAINT,
        # so a separate op.create_unique_constraint() breaks every sqlite-backed
        # test/dev database (caught by the migration round-trip harness 2026-08-05).
        sa.UniqueConstraint("idempotency_key", name="uq_prospective_idempotency"),
    )
    op.create_index("ix_prospective_status_due", "prospective_memory", ["status", "due_at"])
    op.create_index("ix_prospective_tenant_agent", "prospective_memory", ["tenant_id", "agent_id"])
    op.create_index("ix_prospective_lease", "prospective_memory", ["status", "lease_until"])


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "prospective_memory" not in inspector.get_table_names():
        return
    op.drop_index("ix_prospective_lease", table_name="prospective_memory")
    op.drop_index("ix_prospective_tenant_agent", table_name="prospective_memory")
    op.drop_index("ix_prospective_status_due", table_name="prospective_memory")
    # the unique constraint lives inside the table definition, so dropping the
    # table removes it — no ALTER needed (portable to SQLite).
    op.drop_table("prospective_memory")
