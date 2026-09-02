"""DB-enforced lead-phone uniqueness (F-DB2, production audit 2026-07-01).

Business rule (decided in-code, matching the ALREADY-established app-level
convention independently used by app/platform/prospector.py and
app/tasks/sync.py — both look up `Lead.phone` globally before inserting):
phone is the platform-wide dedup key. app/api/public_site.py::_save_lead_db
was the one write path missing this check (fixed alongside this migration).

Non-destructive by design: this migration NEVER deletes or merges rows. It
inspects the live `leads` table for phone values with more than one row; if
any exist, it logs a warning (visible in migration output / deploy logs) and
SKIPS creating the hard constraint — a broken app-level dedup bug elsewhere
must not turn an `alembic upgrade head` into a data-loss event. Once the
warning-listed duplicates are reviewed and cleaned up by an operator, running
`alembic downgrade -1 && alembic upgrade head` re-attempts constraint creation.

Idempotent: skip if the index already exists.
Revision ID: 009_leads_phone_unique_if_clean
Revises: 008_add_agents_agent_events
"""

import sqlalchemy as sa

from alembic import op

revision = "009_leads_phone_unique_if_clean"
down_revision = "008_add_agents_agent_events"
branch_labels = None
depends_on = None

_INDEX_NAME = "uq_leads_phone"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "leads" not in inspector.get_table_names():
        return  # fresh DB with no leads table yet — nothing to enforce

    existing_indexes = {ix["name"] for ix in inspector.get_indexes("leads")}
    existing_uniques = {uc["name"] for uc in inspector.get_unique_constraints("leads")}
    if _INDEX_NAME in existing_indexes or _INDEX_NAME in existing_uniques:
        return  # already enforced

    dupes = bind.execute(
        sa.text(
            "SELECT phone, COUNT(*) AS n FROM leads "
            "WHERE phone IS NOT NULL AND phone != '' "
            "GROUP BY phone HAVING COUNT(*) > 1"
        )
    ).fetchall()

    if dupes:
        preview = ", ".join(f"{row[0]} (x{row[1]})" for row in dupes[:10])
        more = f" and {len(dupes) - 10} more" if len(dupes) > 10 else ""
        print(
            f"[009_leads_phone_unique_if_clean] SKIPPING unique index — "
            f"{len(dupes)} phone(s) already have duplicate leads: {preview}{more}. "
            f"App-level dedup (public_site.py/prospector.py/tasks/sync.py) now "
            f"prevents new duplicates; clean up existing ones then re-run "
            f"'alembic downgrade -1 && alembic upgrade head' to enforce at the DB level."
        )
        return

    op.create_index(_INDEX_NAME, "leads", ["phone"], unique=True)


def downgrade() -> None:
    try:
        op.drop_index(_INDEX_NAME, table_name="leads")
    except Exception:
        pass
