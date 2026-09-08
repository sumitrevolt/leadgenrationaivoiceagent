"""Retrofit native Postgres ENUM columns to VARCHAR (F-DB4, production audit
2026-07-01, closed after gaining real-Postgres access this session).

WHY: `payment.py` already uses `Enum(..., native_enum=False, values_callable=...)`
(VARCHAR-backed, no native Postgres ENUM type) — the safer pattern, because
adding a new enum value to a native type later needs `ALTER TYPE ... ADD VALUE`,
which cannot run inside the same transaction as other DDL on some Postgres
versions. Every other model with an enum column used the bare `Enum(...)` form
(native_enum defaults True), so on a `create_all()`-bootstrapped DB (this
project's actual default, `DB_CREATE_ALL=1`) they render as native Postgres
ENUM types.

DISCOVERY (verified against real Postgres, not guessed): the actual list is
bigger than it looks from reading model files alone. `create_all()` produces
native ENUM types on 16 columns across 8 tables — including `billing_records`
and `campaigns`, which are easy to miss by hand. Meanwhile, several
Alembic-authored migrations (001_initial.py's `leads`/`clients`/`call_logs`,
004_add_data_credits.py's `credit_transactions`/`api_usage_logs`) already
define these same columns as plain `sa.String(...)`, NOT a native enum — so
whether a given live database actually has native-enum columns here depends on
which bootstrap path originally built it, which this migration cannot know in
advance.

DESIGN: dynamically discover every native-enum column via `information_schema`
+ `pg_type` (not a hardcoded list) and convert only what's actually found. This
is correct regardless of the database's bootstrap history, and a genuine no-op
on any column that's already VARCHAR. No-op entirely on non-Postgres dialects
(SQLite has no native enum type). Never drops the underlying enum TYPE
(orphaned but harmless) — dropping risks a dependency error if anything else
still references it, and there's no correctness reason to remove it.

CRITICAL DATA DETAIL (found by testing against real Postgres, not assumed):
a bare `Column(Enum(SomeEnum), ...)` with no `values_callable` makes SQLAlchemy
store the Python enum member's **NAME** in the native Postgres type (e.g.
"QUALIFIED"), not its `.value` ("qualified") — confirmed via `pg_enum` on a
`create_all()`-bootstrapped DB. Only `UserRole`/`UserStatus` already store
lowercase values (user.py explicitly sets `values_callable`); the other 13
enum classes across `leads`/`clients`/`agents`/`call_logs`/`campaigns`/
`billing_records`/`credit_transactions`/`api_usage_logs` do not, so their
columns hold uppercase names today. A migration that only changed the column
TYPE (e.g. `USING col::text`) without ALSO fixing this casing would leave
"QUALIFIED" in the database while every other part of this fix (see the model
changes in the same commit) switches the app to reading/writing `.value`
("qualified") — a silent mismatch that breaks every read of these columns.
Verified every one of the 13 name-storing enum classes follows a consistent
`MEMBER_NAME.lower() == member.value` convention (read all 13 class bodies,
no exceptions) — so `LOWER(col::text)` is a correct, safe transformation for
all 16 columns: for the 13 that store names, it produces the exact `.value`;
for the 2 that already store lowercase values, it's a no-op.

Verified end-to-end against real Postgres (16.2), twice — once on a DB
bootstrapped via `alembic upgrade head` alone (3 native-enum columns:
`agents.status`, `users.role/status`) and once via `Base.metadata.create_all()`
(this project's actual `DB_CREATE_ALL=1` default — 16 native-enum columns
across 8 tables). Seeded real rows with real enum values before migrating,
confirmed both the column type AND the stored value are correct afterward,
and confirmed the ORM can still read the row back as the correct Python enum
member post-migration. See docs/archive/2026-07/TEST_RESULTS.md for the full command + output.

Downgrade: intentionally a no-op. Reconstructing the exact original enum type
+ its full set of allowed values from live column data alone isn't reliably
derivable (a value that's never occurred in any row wouldn't be inferred), so
this migration is treated as forward-only rather than fabricating an
incomplete reversal.

Revision ID: 010_enum_columns_to_varchar
Revises: 009_leads_phone_unique_if_clean
"""

import sqlalchemy as sa

from alembic import op

revision = "010_enum_columns_to_varchar"
down_revision = "009_leads_phone_unique_if_clean"
branch_labels = None
depends_on = None

_VARCHAR_LEN = 64  # generous — every enum value seen in this codebase is well under this


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return  # SQLite/others have no native enum type — nothing to retrofit

    rows = bind.execute(
        sa.text(
            """
            SELECT c.table_name, c.column_name, c.udt_name
            FROM information_schema.columns c
            JOIN pg_type t ON t.typname = c.udt_name
            WHERE t.typtype = 'e'
              AND c.table_schema = 'public'
            ORDER BY c.table_name, c.column_name
            """
        )
    ).fetchall()

    for table_name, column_name, enum_type in rows:
        print(
            f"[010_enum_columns_to_varchar] converting {table_name}.{column_name} "
            f"({enum_type} -> varchar({_VARCHAR_LEN}))"
        )
        bind.execute(
            sa.text(
                f'ALTER TABLE "{table_name}" ALTER COLUMN "{column_name}" '
                f'TYPE VARCHAR({_VARCHAR_LEN}) USING LOWER("{column_name}"::text)'
            )
        )

    if not rows:
        print("[010_enum_columns_to_varchar] no native-enum columns found — nothing to do")


def downgrade() -> None:
    print(
        "[010_enum_columns_to_varchar] downgrade is a no-op by design — the original "
        "enum type + its full value set cannot be reliably reconstructed from live "
        "column data alone (a value that never occurred wouldn't be inferred)."
    )
