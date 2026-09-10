"""add dev_workers (24x7 worker identity + liveness registry)

Revision ID: 027_add_dev_workers
Revises: 026_add_dev_task_events
Create Date: 2026-09-10 15:35:00.000000

``dev_tasks`` answers WHAT must be done; nothing in the schema answered WHO is
doing it and whether they are still alive. Owner Command Center question Q4
("kaunsa bot/agent stuck hai") therefore had no row source and could only be
answered from in-memory dicts or ``data/workforce_live_status.json`` — which is
self-refuting and banned by the truth gate in ``AGENTS.md``.

This table is the first honest source for that question. Schema follows
``docs/architecture/24X7_ARCHITECTURE_RECORD.md`` §3: heartbeat 60 s, lease TTL
600 s (lockstep with ``app/dev_control/claims.py`` DEFAULT_LEASE_SECONDS),
staleness at 10 missed beats.

Deliberately contains **no credential, token or env column** — everything here
is safe to render to the owner as-is.

Additive + idempotent (same guarded pattern as 021/024/026): every step is
protected by an inspector check so re-running against a create_all-built DB is
a no-op that never raises. ROLLBACK IS IMPLEMENTED.

Chains onto 026 — do NOT renumber; 026 is already taken by another worker and
two heads would break the Alembic chain.
"""

import sqlalchemy as sa

from alembic import op

revision = "027_add_dev_workers"
down_revision = "026_add_dev_task_events"
branch_labels = None
depends_on = None

TABLE = "dev_workers"

INDEXES = (
    ("ix_dev_workers_kind", ["kind"]),
    ("ix_dev_workers_supervisor_bot", ["supervisor_bot"]),
    ("ix_dev_workers_heartbeat_ts", ["heartbeat_ts"]),
    ("ix_dev_workers_current_task_id", ["current_task_id"]),
    ("ix_dev_workers_combo_id", ["combo_id"]),
    ("ix_dev_workers_health", ["health"]),
    ("ix_dev_workers_created_at", ["created_at"]),
)


def _existing_indexes(inspector, table: str) -> set[str]:
    try:
        return {str(ix.get("name")) for ix in inspector.get_indexes(table)}
    except Exception:
        return set()


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if TABLE in set(inspector.get_table_names()):
        # Table already present (create_all path). Only backfill missing indexes.
        existing = _existing_indexes(inspector, TABLE)
        for name, cols in INDEXES:
            if name not in existing:
                op.create_index(name, TABLE, cols, unique=False)
        return

    op.create_table(
        TABLE,
        sa.Column("worker_id", sa.String(length=120), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("supervisor_bot", sa.String(length=80), nullable=True),
        sa.Column("capabilities", sa.Text(), nullable=True),
        sa.Column("version", sa.String(length=60), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("heartbeat_ts", sa.DateTime(), nullable=True),
        sa.Column("lease_id", sa.String(length=120), nullable=True),
        sa.Column("current_task_id", sa.String(length=36), nullable=True),
        sa.Column("queue_depth", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("combo_id", sa.String(length=60), nullable=True),
        sa.Column("health", sa.String(length=20), nullable=False),
        sa.Column("pid_host", sa.String(length=255), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("worker_id"),
    )
    for name, cols in INDEXES:
        op.create_index(name, TABLE, cols, unique=False)


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if TABLE not in set(inspector.get_table_names()):
        return
    existing = _existing_indexes(inspector, TABLE)
    with op.batch_alter_table(TABLE) as batch_op:
        for name, _cols in reversed(INDEXES):
            if name in existing:
                batch_op.drop_index(name)
    op.drop_table(TABLE)
