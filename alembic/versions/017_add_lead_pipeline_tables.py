# alembic/versions/017_add_lead_pipeline_tables.py
"""lead_pipeline_batches / lead_pipeline_stage_runs / lead_pipeline_quality_issues
tables + leads.score_reason / leads.source_batch_id columns (2026-07-08, lead-gen
pipeline automation vertical slice — see
docs/superpowers/specs/2026-07-08-lead-gen-pipeline-automation-design.md).

Idempotent: skip if a table/column already exists — same pattern as
008_add_agents_agent_events.py / 016_add_dev_task_usage.py. Never ALTERs
an existing table's existing columns, only adds genuinely new tables/columns.

Revision ID: 017_add_lead_pipeline_tables
Revises: 016_add_dev_task_usage
"""

import sqlalchemy as sa

from alembic import op

revision = "017_add_lead_pipeline_tables"
down_revision = "016_add_dev_task_usage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())

    if "lead_pipeline_batches" not in existing:
        op.create_table(
            "lead_pipeline_batches",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("source", sa.String(30), nullable=False, server_default="prospector"),
            sa.Column("niche", sa.String(50)),
            sa.Column("city", sa.String(100)),
            sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
            sa.Column("total_raw", sa.Integer(), server_default="0"),
            sa.Column("total_duplicate", sa.Integer(), server_default="0"),
            sa.Column("total_invalid", sa.Integer(), server_default="0"),
            sa.Column("total_valid", sa.Integer(), server_default="0"),
            sa.Column("total_scored", sa.Integer(), server_default="0"),
            sa.Column("total_eligible", sa.Integer(), server_default="0"),
            sa.Column("total_outreach_created", sa.Integer(), server_default="0"),
            sa.Column("error_count", sa.Integer(), server_default="0"),
            sa.Column("started_at", sa.DateTime()),
            sa.Column("completed_at", sa.DateTime()),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_pipeline_batches_source_time", "lead_pipeline_batches", ["source", "created_at"])
        op.create_index("ix_pipeline_batches_status_time", "lead_pipeline_batches", ["status", "created_at"])

    if "lead_pipeline_stage_runs" not in existing:
        op.create_table(
            "lead_pipeline_stage_runs",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("batch_id", sa.String(36), sa.ForeignKey("lead_pipeline_batches.id"), nullable=False),
            sa.Column("stage_name", sa.String(30), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
            sa.Column("input_count", sa.Integer(), server_default="0"),
            sa.Column("output_count", sa.Integer(), server_default="0"),
            sa.Column("rejected_count", sa.Integer(), server_default="0"),
            sa.Column("error_message", sa.Text()),
            sa.Column("started_at", sa.DateTime()),
            sa.Column("completed_at", sa.DateTime()),
        )
        op.create_index("ix_pipeline_stage_runs_batch", "lead_pipeline_stage_runs", ["batch_id", "stage_name"])
        # FK column itself also gets its own index (matches Column(..., index=True)
        # in app/models/lead_pipeline.py — SQLAlchemy's default auto-generated name).
        op.create_index("ix_lead_pipeline_stage_runs_batch_id", "lead_pipeline_stage_runs", ["batch_id"])

    if "lead_pipeline_quality_issues" not in existing:
        op.create_table(
            "lead_pipeline_quality_issues",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("batch_id", sa.String(36), sa.ForeignKey("lead_pipeline_batches.id"), nullable=False),
            sa.Column("stage_name", sa.String(30), nullable=False),
            sa.Column("issue_type", sa.String(40), nullable=False),
            sa.Column("severity", sa.String(10), nullable=False, server_default="warning"),
            sa.Column("message", sa.Text()),
            sa.Column("resolved", sa.Boolean(), server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_pipeline_issues_batch", "lead_pipeline_quality_issues", ["batch_id", "created_at"])
        op.create_index("ix_pipeline_issues_resolved", "lead_pipeline_quality_issues", ["resolved", "severity"])
        # batch_id and resolved both also declare index=True on the Column itself
        # (app/models/lead_pipeline.py) in addition to the composite Index()s above
        # — create_all() emits both; mirror here so alembic-managed DBs match.
        op.create_index("ix_lead_pipeline_quality_issues_batch_id", "lead_pipeline_quality_issues", ["batch_id"])
        op.create_index("ix_lead_pipeline_quality_issues_resolved", "lead_pipeline_quality_issues", ["resolved"])

    lead_cols = {c["name"] for c in inspector.get_columns("leads")}
    if "score_reason" not in lead_cols:
        op.add_column("leads", sa.Column("score_reason", sa.Text()))
    if "source_batch_id" not in lead_cols:
        # Raw SQL, not op.add_column(Column(..., ForeignKey(...))): Alembic's
        # add_column, when the Column carries a ForeignKey, emits ADD COLUMN
        # then a SEPARATE ADD CONSTRAINT statement — SQLite's dialect has no
        # support for the latter (NotImplementedError: "No support for ALTER
        # of constraints in SQLite dialect", verified locally). Wrapping in
        # batch_alter_table (its documented workaround) then trips on the
        # leads table's OTHER pre-existing unnamed FKs (assigned_to/
        # campaign_id) during its copy-and-move recreate: "ValueError:
        # Constraint must have a name" (also verified locally). A single raw
        # ALTER ... ADD COLUMN ... REFERENCES is valid SQL in ONE statement on
        # both SQLite (3.35+) and Postgres — the same raw-SQL escape hatch
        # already used by 009_leads_phone_unique_if_clean.py/
        # 010_enum_columns_to_varchar.py for similar cross-dialect gaps, and
        # it doesn't touch the rest of the table at all.
        bind.execute(
            sa.text(
                "ALTER TABLE leads ADD COLUMN source_batch_id VARCHAR(36) "
                "REFERENCES lead_pipeline_batches(id)"
            )
        )
        # Model declares source_batch_id with index=True (app/models/lead.py) —
        # create_all()-based test DBs get this index for free; an alembic-managed
        # DB needs it explicit or the two schema-provisioning paths silently drift.
        op.create_index("ix_leads_source_batch_id", "leads", ["source_batch_id"])


def downgrade() -> None:
    # Drop leads.source_batch_id BEFORE dropping lead_pipeline_batches — it FKs
    # into that table, so on Postgres dropping the table first would fail with
    # a dependency error.
    try:
        op.drop_index("ix_leads_source_batch_id", table_name="leads")
    except Exception:
        pass
    try:
        op.drop_column("leads", "source_batch_id")
    except Exception:
        pass
    try:
        op.drop_column("leads", "score_reason")
    except Exception:
        pass
    for tbl in ("lead_pipeline_quality_issues", "lead_pipeline_stage_runs", "lead_pipeline_batches"):
        try:
            op.drop_table(tbl)
        except Exception:
            pass
