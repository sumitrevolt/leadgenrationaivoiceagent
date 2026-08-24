"""Approval-notification Alembic migration contracts."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def _migration_module():
    path = (
        Path(__file__).resolve().parent.parent
        / "alembic"
        / "versions"
        / "018_add_approval_notifications.py"
    )
    spec = importlib.util.spec_from_file_location("approval_notification_migration", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_approval_notification_migration_upgrade_idempotent_and_downgrade(monkeypatch):
    migration = _migration_module()
    assert migration.down_revision == "017_add_lead_pipeline_tables"
    engine = sa.create_engine("sqlite://")

    with engine.begin() as connection:
        operations = Operations(MigrationContext.configure(connection))
        monkeypatch.setattr(migration, "op", operations)

        migration.upgrade()
        migration.upgrade()

        inspector = sa.inspect(connection)
        columns = {column["name"] for column in inspector.get_columns("approval_notifications")}
        assert columns == {
            "id",
            "client_id",
            "approval_id",
            "approval_version",
            "channel",
            "idempotency_key",
            "status",
            "failure_category",
            "provider_message_id",
            "attempts",
            "attempted_at",
            "completed_at",
            "meta_json",
        }
        indexes = {
            index["name"]: index for index in inspector.get_indexes("approval_notifications")
        }
        assert indexes["ix_approval_notifications_idempotency_key"]["unique"] == 1
        assert {
            "ix_approval_notifications_client_id",
            "ix_approval_notifications_approval_id",
            "ix_approval_notifications_status",
            "ix_approval_notifications_attempted_at",
        }.issubset(indexes)

        migration.downgrade()
        assert "approval_notifications" not in sa.inspect(connection).get_table_names()
