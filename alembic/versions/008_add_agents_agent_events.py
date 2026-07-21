"""agents / agent_events tables (F-DB1, production audit 2026-07-01).

Both tables previously existed only via SQLAlchemy create_all() fallback, with
no Alembic migration — a latent gap that would 500 the Team dashboard + worker
pool the day DB_CREATE_ALL is flipped to 0 (Alembic-only mode, see
app/models/base.py init_async_db docstring).

Idempotent: skip if a table already exists (create_all on live DB) — this is a
pure no-op there, matching the pattern in 006_flywheel_enterprise.py and
007_add_lead_status_history.py. Only creates the tables on an environment where
they're genuinely absent (fresh DB / disaster-recovery restore), so there is no
column-drift risk against the live VPS: it never ALTERs an existing table.

Columns mirror app/models/agent.py::Agent and app/models/agent_event.py::AgentEvent
exactly, including the `role` column that base.py's _apply_schema_upgrades()
ALTERs onto pre-existing `agents` tables — a fresh table created by this
migration already has it, so no post-create ALTER is needed for a new DB.

Revision ID: 008_add_agents_agent_events
Revises: 007_add_lead_status_history
"""

import sqlalchemy as sa

from alembic import op

revision = "008_add_agents_agent_events"
down_revision = "007_add_lead_status_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())

    if "agents" not in existing:
        op.create_table(
            "agents",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("name", sa.String(100), nullable=False),
            sa.Column("agent_code", sa.String(20), index=True),
            sa.Column("current_client_id", sa.String(36), sa.ForeignKey("clients.id")),
            sa.Column("current_client_name", sa.String(255)),
            sa.Column("current_campaign_id", sa.String(36), sa.ForeignKey("campaigns.id")),
            sa.Column(
                "status",
                sa.Enum(
                    "IDLE",
                    "CALLING",
                    "SCRAPING",
                    "PAUSED",
                    "ERROR",
                    "OFFLINE",
                    name="agentstatus",
                ),
                server_default="IDLE",
            ),
            sa.Column("role", sa.String(20), server_default="leads", index=True),
            sa.Column("niche", sa.String(50)),
            sa.Column("voice", sa.String(50), server_default="EdgeTTS"),
            sa.Column("language", sa.String(20), server_default="hinglish"),
            sa.Column("max_concurrent_calls", sa.Integer(), server_default="1"),
            sa.Column("calls_made", sa.Integer(), server_default="0"),
            sa.Column("leads_found", sa.Integer(), server_default="0"),
            sa.Column("appointments_booked", sa.Integer(), server_default="0"),
            sa.Column("talk_time_seconds", sa.Integer(), server_default="0"),
            sa.Column("last_error", sa.Text()),
            sa.Column("error_count", sa.Integer(), server_default="0"),
            sa.Column("created_at", sa.DateTime()),
            sa.Column("updated_at", sa.DateTime()),
            sa.Column("last_active_at", sa.DateTime()),
        )
        op.create_index("ix_agents_status", "agents", ["status"])
        op.create_index("ix_agents_client", "agents", ["current_client_id"])

    if "agent_events" not in existing:
        op.create_table(
            "agent_events",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("member", sa.String(40), nullable=False, server_default="system"),
            sa.Column("action", sa.String(60), nullable=False, server_default="event"),
            sa.Column("detail", sa.String(500), server_default=""),
            sa.Column("status", sa.String(10), server_default="ok"),
            sa.Column("meta_json", sa.Text(), server_default="{}"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_agent_events_member_time", "agent_events", ["member", "created_at"])
        op.create_index("ix_agent_events_time", "agent_events", ["created_at"])


def downgrade() -> None:
    for tbl in ("agent_events", "agents"):
        try:
            op.drop_table(tbl)
        except Exception:
            pass
    # sa.Enum(name="agentstatus") on agents.status implicitly CREATEs a Postgres
    # TYPE on upgrade, but op.drop_table does NOT drop that TYPE. Without removing
    # it here, a downgrade -> upgrade round-trip fails with
    # "type agentstatus already exists" (the CI Postgres round-trip gate).
    # The only dependent (agents.status) is dropped above, so the TYPE has no
    # remaining dependents at this point. IF EXISTS matches this migration's
    # already-idempotent contract (guarded upgrade, try/except downgrade), and is
    # NOT a substitute for ordering — the drop is correctly sequenced after the
    # dependent tables. Guarded to Postgres: SQLite maps Enum to VARCHAR+CHECK and
    # has no TYPE object, so DROP TYPE is invalid there.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TYPE IF EXISTS agentstatus")
