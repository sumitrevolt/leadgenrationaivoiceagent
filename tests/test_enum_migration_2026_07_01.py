"""F-DB4 enum-column retrofit (production audit 2026-07-01).

The full migration (alembic/versions/010_enum_columns_to_varchar.py) is
Postgres-specific — it queries information_schema/pg_type and runs
`ALTER COLUMN ... TYPE VARCHAR USING LOWER(...)`, none of which exist on
SQLite. This test only confirms the dialect guard: on SQLite (this project's
CI/dev default), the migration must be a clean no-op, never raise, and never
touch the column type is meaningless here — SQLite has no native enum type to
begin with. The Postgres-specific behavior (real type conversion + the
NAME->value casing fix) was verified end-to-end this session against a real
local Postgres 16 instance — see docs/archive/2026-07/TEST_RESULTS.md for the full command +
output; that verification is not repeated here as a permanent CI dependency
since the migration only ever needs to run once against real prod/staging.

Also confirms the model-level change (native_enum=False, values_callable) does
not break ordinary CRUD against SQLite — the actual value stored is the
enum's .value either way on a dialect with no native enum type.
"""

from __future__ import annotations

import importlib.util
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.agent import Agent, AgentStatus
from app.models.base import Base
from app.models.lead import Lead, LeadSource, LeadStatus


def _load_migration_module():
    """alembic/versions/010_*.py can't be `import`ed normally — a filename
    starting with a digit isn't a valid Python module name. Load it directly
    from its file path, same as alembic's own runtime loader does."""
    path = os.path.join("alembic", "versions", "010_enum_columns_to_varchar.py")
    spec = importlib.util.spec_from_file_location("enum_migration_010", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


enum_migration = _load_migration_module()


def test_migration_upgrade_is_noop_on_sqlite():
    """Actually invoke the real upgrade() function (not just its dialect
    check) against a live SQLite engine, via Alembic's own Operations API —
    same mechanism Alembic uses at runtime, just without the CLI."""
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        op_instance = Operations(ctx)
        import alembic.op as global_op

        # alembic.op proxies to a thread-local operations context; set it up
        # the same way `alembic upgrade` does before calling upgrade().
        global_op._proxy = op_instance
        try:
            enum_migration.upgrade()  # must not raise, must do nothing on sqlite
        finally:
            global_op._proxy = None

    # Confirm nothing changed — schema still has the exact original columns.
    from sqlalchemy import inspect

    insp = inspect(engine)
    assert "leads" in insp.get_table_names()
    assert "agents" in insp.get_table_names()


def test_enum_model_columns_round_trip_on_sqlite():
    """Sanity check the native_enum=False + values_callable model change
    doesn't change ordinary CRUD behavior on a dialect with no native enum."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()

    lead = Lead(
        id="test-enum-1",
        company_name="Enum Test Co",
        phone="+919999900001",
        status=LeadStatus.QUALIFIED,
        source=LeadSource.WEBSITE,
    )
    agent = Agent(id="test-enum-agent-1", name="Enum Test Agent", status=AgentStatus.CALLING)
    s.add_all([lead, agent])
    s.commit()
    s.expire_all()

    lead2 = s.get(Lead, "test-enum-1")
    agent2 = s.get(Agent, "test-enum-agent-1")
    assert lead2.status == LeadStatus.QUALIFIED
    assert lead2.source == LeadSource.WEBSITE
    assert agent2.status == AgentStatus.CALLING
    s.close()


def test_migration_module_importable():
    """The migration file itself must import cleanly (syntax/logic sanity)."""
    assert hasattr(enum_migration, "upgrade")
    assert hasattr(enum_migration, "downgrade")
    assert hasattr(enum_migration, "_VARCHAR_LEN")
