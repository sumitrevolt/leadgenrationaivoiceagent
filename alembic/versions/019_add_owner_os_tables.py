"""Add Owner OS durable tables (commands, kill switches, audit).

Revision ID: 019_add_owner_os_tables
Revises: 018_add_approval_notifications

Additive + idempotent. Production uses Alembic-only schema management
(`DB_CREATE_ALL=0`). Rollback drops the three tables if present.
"""

import sqlalchemy as sa

from alembic import op

revision = "019_add_owner_os_tables"
down_revision = "018_add_approval_notifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "owner_commands" not in tables:
        op.create_table(
            "owner_commands",
            sa.Column("command_id", sa.String(40), primary_key=True),
            sa.Column("actor_id", sa.String(120), nullable=False),
            sa.Column("actor_role", sa.String(40)),
            sa.Column("original_instruction", sa.Text(), nullable=False),
            sa.Column("normalized_intent", sa.String(64), nullable=False),
            sa.Column("tenant_id", sa.String(64)),
            sa.Column("assigned_agent_id", sa.String(40)),
            sa.Column("risk_level", sa.String(20), nullable=False, server_default="low"),
            sa.Column("approval_state", sa.String(40), nullable=False, server_default="none"),
            sa.Column("execution_state", sa.String(40), nullable=False, server_default="DRAFT"),
            sa.Column("idempotency_key", sa.String(80), nullable=False),
            sa.Column("parameters_json", sa.Text()),
            sa.Column("publish_allowed", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column(
                "customer_notify_allowed",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
            sa.Column("created_at", sa.DateTime()),
            sa.Column("updated_at", sa.DateTime()),
            sa.Column("completed_at", sa.DateTime()),
            sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("error_code", sa.String(64)),
            sa.Column("sanitized_error", sa.Text()),
            sa.Column("evidence_summary_json", sa.Text()),
            sa.Column("correlation_id", sa.String(64)),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("preview_summary", sa.Text()),
            sa.UniqueConstraint("idempotency_key", name="uq_owner_commands_idempotency"),
        )
        op.create_index(
            "ix_owner_commands_normalized_intent", "owner_commands", ["normalized_intent"]
        )
        op.create_index("ix_owner_commands_tenant_id", "owner_commands", ["tenant_id"])
        op.create_index(
            "ix_owner_commands_assigned_agent_id", "owner_commands", ["assigned_agent_id"]
        )
        op.create_index("ix_owner_commands_execution_state", "owner_commands", ["execution_state"])
        op.create_index("ix_owner_commands_created_at", "owner_commands", ["created_at"])
        op.create_index("ix_owner_commands_correlation_id", "owner_commands", ["correlation_id"])

    if "owner_kill_switches" not in tables:
        op.create_table(
            "owner_kill_switches",
            sa.Column("switch_name", sa.String(64), primary_key=True),
            sa.Column("engaged", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("scope", sa.String(40), nullable=False, server_default="global"),
            sa.Column("reason", sa.String(200)),
            sa.Column("changed_by", sa.String(120)),
            sa.Column("changed_at", sa.DateTime()),
            sa.Column("expiry", sa.DateTime()),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        )

    if "owner_os_audit_events" not in tables:
        op.create_table(
            "owner_os_audit_events",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("at", sa.DateTime()),
            sa.Column("actor", sa.String(120), nullable=False),
            sa.Column("action", sa.String(80), nullable=False),
            sa.Column("target", sa.String(120)),
            sa.Column("tenant_id", sa.String(64)),
            sa.Column("correlation_id", sa.String(64)),
            sa.Column("before_summary", sa.Text()),
            sa.Column("after_summary", sa.Text()),
            sa.Column("meta_json", sa.Text()),
        )
        op.create_index("ix_owner_os_audit_events_at", "owner_os_audit_events", ["at"])
        op.create_index("ix_owner_os_audit_events_action", "owner_os_audit_events", ["action"])
        op.create_index(
            "ix_owner_os_audit_events_tenant_id", "owner_os_audit_events", ["tenant_id"]
        )
        op.create_index(
            "ix_owner_os_audit_events_correlation_id",
            "owner_os_audit_events",
            ["correlation_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "owner_os_audit_events" in tables:
        op.drop_table("owner_os_audit_events")
    if "owner_kill_switches" in tables:
        op.drop_table("owner_kill_switches")
    if "owner_commands" in tables:
        op.drop_table("owner_commands")
