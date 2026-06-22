"""Enterprise flywheel tables — accounts, contacts, interactions, campaign_variants.

Idempotent: skip if tables already exist (create_all on live DB).
Revision ID: 006_flywheel_enterprise
Revises: 005_add_billing_records
"""

import sqlalchemy as sa

from alembic import op

revision = "006_flywheel_enterprise"
down_revision = "005_add_billing_records"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())

    if "accounts" not in existing:
        op.create_table(
            "accounts",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("client_id", sa.String(36), index=True),
            sa.Column("company_name", sa.String(255), nullable=False, index=True),
            sa.Column("domain", sa.String(255), index=True),
            sa.Column("industry", sa.String(100)),
            sa.Column("employee_band", sa.String(50)),
            sa.Column("niche", sa.String(100), index=True),
            sa.Column("city", sa.String(100)),
            sa.Column("created_at", sa.DateTime()),
            sa.Column("updated_at", sa.DateTime()),
        )
        op.create_index("ix_accounts_client_domain", "accounts", ["client_id", "domain"])
        op.create_index("ix_accounts_client_niche", "accounts", ["client_id", "niche"])

    if "contacts" not in existing:
        op.create_table(
            "contacts",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("client_id", sa.String(36), index=True),
            sa.Column("account_id", sa.String(36), sa.ForeignKey("accounts.id"), index=True),
            sa.Column("name", sa.String(255)),
            sa.Column("phone_e164", sa.String(20), index=True),
            sa.Column("email", sa.String(255), index=True),
            sa.Column("role", sa.String(100)),
            sa.Column("lead_id", sa.String(36), index=True),
            sa.Column("enriched_at", sa.DateTime()),
            sa.Column("created_at", sa.DateTime()),
            sa.Column("updated_at", sa.DateTime()),
        )
        op.create_index("ix_contacts_client_phone", "contacts", ["client_id", "phone_e164"])

    if "interactions" not in existing:
        op.create_table(
            "interactions",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("client_id", sa.String(36), index=True),
            sa.Column("contact_id", sa.String(36), sa.ForeignKey("contacts.id"), index=True),
            sa.Column("lead_id", sa.String(36), index=True),
            sa.Column("channel", sa.String(30), nullable=False),
            sa.Column("direction", sa.String(10)),
            sa.Column("body_summary", sa.Text()),
            sa.Column("outcome", sa.String(50)),
            sa.Column("campaign_variant_id", sa.String(36), index=True),
            sa.Column("meta_json", sa.Text()),
            sa.Column("occurred_at", sa.DateTime(), index=True),
            sa.Column("created_at", sa.DateTime()),
        )
        op.create_index("ix_interactions_contact_at", "interactions", ["contact_id", "occurred_at"])
        op.create_index("ix_interactions_channel", "interactions", ["channel", "direction"])

    if "campaign_variants" not in existing:
        op.create_table(
            "campaign_variants",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("client_id", sa.String(36), index=True),
            sa.Column("script_id", sa.String(100), nullable=False, index=True),
            sa.Column("variant_key", sa.String(50), nullable=False),
            sa.Column("niche", sa.String(100), index=True),
            sa.Column("channel", sa.String(30)),
            sa.Column("content", sa.Text()),
            sa.Column("impressions", sa.Integer(), server_default="0"),
            sa.Column("replies", sa.Integer(), server_default="0"),
            sa.Column("meetings", sa.Integer(), server_default="0"),
            sa.Column("meeting_rate", sa.Float(), server_default="0"),
            sa.Column("status", sa.String(20), server_default="challenger"),
            sa.Column("created_at", sa.DateTime()),
            sa.Column("promoted_at", sa.DateTime()),
        )
        op.create_index("ix_cv_script_status", "campaign_variants", ["script_id", "status"])


def downgrade() -> None:
    for tbl in ("campaign_variants", "interactions", "contacts", "accounts"):
        try:
            op.drop_table(tbl)
        except Exception:
            pass
