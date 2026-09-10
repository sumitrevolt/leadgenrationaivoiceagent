"""add dev_task_events + dev_tasks parent_id/next_eligible_at

Revision ID: 026_add_dev_task_events
Revises: 025
Create Date: 2026-09-11 00:00:00.000000

Makes DevTask safe as the single canonical 24x7 task ledger:
  * ``dev_task_events``  — append-only, hash-chained audit trail
                           (prev_hash -> event_hash, genesis "0"*64).
  * ``dev_tasks.parent_id``        — nullable self-FK; parent/child tasks.
  * ``dev_tasks.next_eligible_at`` — nullable; claim backoff gate honoured by
                           ``app.dev_control.claims.claim_next``.

Additive + idempotent (024/021 ka same pattern): every step is guarded by an
inspector check, so re-running on a create_all-built DB is a no-op and never
raises. ROLLBACK IS IMPLEMENTED — downgrade drops the indexes, the two columns
and the table (batch_alter_table so SQLite, which cannot DROP COLUMN in place,
is handled too).
"""

import sqlalchemy as sa

from alembic import op

revision = "026_add_dev_task_events"
down_revision = "025"
branch_labels = None
depends_on = None


def _existing_indexes(inspector, table: str) -> set[str]:
    try:
        return {str(ix.get("name")) for ix in inspector.get_indexes(table)}
    except Exception:
        return set()


def _existing_columns(inspector, table: str) -> set[str]:
    try:
        return {str(col.get("name")) for col in inspector.get_columns(table)}
    except Exception:
        return set()


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names())

    # 1. Hash-chained audit trail.
    if "dev_task_events" not in tables:
        op.create_table(
            "dev_task_events",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("task_id", sa.String(length=36), nullable=False),
            sa.Column("seq", sa.Integer(), nullable=False, default=0),
            sa.Column("prev_hash", sa.String(length=64), nullable=False),
            sa.Column("event_hash", sa.String(length=64), nullable=False),
            sa.Column("actor", sa.String(length=120), nullable=True),
            sa.Column("from_state", sa.String(length=40), nullable=True),
            sa.Column("to_state", sa.String(length=40), nullable=True),
            sa.Column("payload", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["task_id"], ["dev_tasks.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_dev_task_events_task_id", "dev_task_events", ["task_id"], unique=False
        )
        op.create_index(
            "ix_dev_task_events_created_at", "dev_task_events", ["created_at"], unique=False
        )

    # 2. dev_tasks: parent_id + next_eligible_at (both nullable + indexed).
    if "dev_tasks" in tables:
        columns = _existing_columns(inspector, "dev_tasks")
        indexes = _existing_indexes(inspector, "dev_tasks")
        if "parent_id" not in columns:
            op.add_column("dev_tasks", sa.Column("parent_id", sa.String(length=36), nullable=True))
        if "next_eligible_at" not in columns:
            op.add_column("dev_tasks", sa.Column("next_eligible_at", sa.DateTime(), nullable=True))
        if "ix_dev_tasks_parent_id" not in indexes:
            op.create_index("ix_dev_tasks_parent_id", "dev_tasks", ["parent_id"], unique=False)
        if "ix_dev_tasks_next_eligible_at" not in indexes:
            op.create_index(
                "ix_dev_tasks_next_eligible_at", "dev_tasks", ["next_eligible_at"], unique=False
            )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names())

    if "dev_tasks" in tables:
        indexes = _existing_indexes(inspector, "dev_tasks")
        columns = _existing_columns(inspector, "dev_tasks")
        # batch_alter_table: SQLite needs a table rebuild to drop a column.
        with op.batch_alter_table("dev_tasks") as batch_op:
            if "ix_dev_tasks_next_eligible_at" in indexes:
                batch_op.drop_index("ix_dev_tasks_next_eligible_at")
            if "ix_dev_tasks_parent_id" in indexes:
                batch_op.drop_index("ix_dev_tasks_parent_id")
            if "next_eligible_at" in columns:
                batch_op.drop_column("next_eligible_at")
            if "parent_id" in columns:
                batch_op.drop_column("parent_id")

    if "dev_task_events" in tables:
        op.drop_table("dev_task_events")
