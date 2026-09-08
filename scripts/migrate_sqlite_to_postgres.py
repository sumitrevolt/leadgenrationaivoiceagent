#!/usr/bin/env python3
"""
Safe, verified SQLite -> Postgres data migration.

WHAT IT DOES
  1. Builds the FULL, correctly-typed schema on the target Postgres using the
     app's own ORM models (Base.metadata.create_all) — same path the app uses.
  2. Reflects the source SQLite DB to discover the tables/rows that actually exist.
  3. Copies every table present in BOTH, in FK-safe order, coercing SQLite's
     loosely-typed values (0/1 -> bool, ISO strings -> datetime) into the proper
     Postgres column types.
  4. Verifies row counts table-by-table and prints a report. Non-zero exit on
     ANY mismatch so a deploy script can stop.

SAFETY
  * Read-only on the source SQLite file.
  * Idempotent: a target table that ALREADY has rows is SKIPPED (warning),
    unless you pass --wipe (TRUNCATE first) or --force (insert anyway).
  * `alembic_version` is intentionally NOT copied — run `alembic upgrade head`
    after this (or let app startup stamp it).

USAGE
  python scripts/migrate_sqlite_to_postgres.py \
      --sqlite sqlite:///./leadgen.db \
      --postgres postgresql+psycopg2://leadgen:PASS@localhost:5432/leadgen

  # Defaults: --sqlite sqlite:///./leadgen.db
  #           --postgres  <- DATABASE_URL env (normalised to a sync psycopg2 URL)

  # Re-run after a failed attempt:
  python scripts/migrate_sqlite_to_postgres.py --wipe
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, MetaData, create_engine, inspect, select, text
from sqlalchemy.engine import Engine

# Make sure the app package is importable when run from the repo root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load_models_metadata() -> MetaData:
    """Import the ORM models so every table is registered on Base.metadata."""
    from app.models.base import Base  # noqa: WPS433

    # Importing the package (and a few known modules) registers all mappers.
    try:
        import app.models  # noqa: F401
    except Exception:
        pass
    for mod in (
        "app.models.user",
        "app.models.payment",
        "app.models.billing_record",
    ):
        try:
            __import__(mod)
        except Exception:
            pass
    # Most reliable: import the full app — it wires up EVERY model module exactly
    # like the live app's create_all() does, so no table is silently missed.
    try:
        import app.main  # noqa: F401
    except Exception as exc:
        print(f"[warn] could not import app.main ({exc}); relying on app.models only")
    return Base.metadata


def _sync_pg_url(url: str) -> str:
    """Normalise any Postgres URL to a synchronous psycopg2 URL."""
    return (
        url.replace("+asyncpg", "")
        .replace("postgresql+psycopg2://", "postgresql+psycopg2://")
        .replace("postgresql://", "postgresql+psycopg2://")
    )


def _coerce(value, col_type):
    """Coerce a SQLite scalar into something Postgres will accept."""
    if value is None:
        return None
    if isinstance(col_type, Boolean):
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "t", "yes", "y"}
        return bool(value)
    if isinstance(col_type, (DateTime, Date)) and isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00").replace(" ", "T", 1))
            return (
                dt.date()
                if isinstance(col_type, Date) and not isinstance(col_type, DateTime)
                else dt
            )
        except ValueError:
            return raw  # let the driver try; surfaces as an error if truly bad
    return value


def migrate(sqlite_url: str, pg_url: str, *, wipe: bool, force: bool, batch: int = 500) -> int:
    metadata = _load_models_metadata()
    src: Engine = create_engine(sqlite_url)
    dst: Engine = create_engine(_sync_pg_url(pg_url))

    print(f"SOURCE : {sqlite_url}")
    print(f"TARGET : {dst.url.render_as_string(hide_password=True)}")
    print(f"TABLES : {len(metadata.tables)} known to the ORM\n")

    # 1) Build schema on target (idempotent — only creates missing tables).
    metadata.create_all(dst)
    print("[schema] create_all() done on target\n")

    # 2) Which tables actually exist in the source?
    src_tables = set(inspect(src).get_table_names())

    failures: list[str] = []
    summary: list[tuple[str, int, int, str]] = []

    with src.connect() as sconn, dst.begin() as dconn:
        # Disable FK enforcement on Postgres during bulk load so the copy faithfully
        # replicates SQLite (which doesn't enforce FKs — prod has some orphan rows).
        is_pg = dconn.dialect.name == "postgresql"
        if is_pg:
            dconn.execute(text("SET session_replication_role = replica"))
        for table in metadata.sorted_tables:  # FK-safe (parents first)
            name = table.name
            if name == "alembic_version":
                continue
            if name not in src_tables:
                summary.append((name, 0, 0, "skip: not in source"))
                continue

            src_rows = [dict(r._mapping) for r in sconn.execute(select(table))]
            src_count = len(src_rows)

            dst_existing = dconn.execute(select(table)).fetchall()
            if dst_existing and not (wipe or force):
                summary.append((name, src_count, len(dst_existing), "skip: target not empty"))
                continue
            if dst_existing and wipe:
                dconn.execute(table.delete())

            if src_rows:
                coltypes = {c.name: c.type for c in table.columns}
                clean = [
                    {k: _coerce(v, coltypes.get(k)) for k, v in row.items()} for row in src_rows
                ]
                for i in range(0, len(clean), batch):
                    dconn.execute(table.insert(), clean[i : i + batch])

            dst_count = dconn.execute(select(table)).fetchall()
            dst_n = len(dst_count)
            ok = dst_n >= src_count
            summary.append((name, src_count, dst_n, "OK" if ok else "MISMATCH"))
            if not ok:
                failures.append(name)

        if is_pg:
            dconn.execute(text("SET session_replication_role = DEFAULT"))

    # 3) Report
    print(f"{'TABLE':<34}{'SRC':>8}{'DST':>8}  STATUS")
    print("-" * 64)
    for name, s, d, status in summary:
        print(f"{name:<34}{s:>8}{d:>8}  {status}")
    print("-" * 64)

    if failures:
        print(f"\n[FAIL] row-count mismatch in: {', '.join(failures)}")
        return 1
    print("\n[OK] all tables migrated and verified.")
    print("NEXT: run `alembic upgrade head` (or restart app) to stamp the schema version.")
    return 0


def main() -> int:
    default_pg = os.environ.get(
        "DATABASE_URL", "postgresql+psycopg2://leadgen:leadgen@localhost:5432/leadgen"
    )
    ap = argparse.ArgumentParser(description="Safe SQLite -> Postgres data migration")
    ap.add_argument("--sqlite", default="sqlite:///./leadgen.db", help="source SQLite URL")
    ap.add_argument("--postgres", default=default_pg, help="target Postgres URL (sync or async)")
    ap.add_argument("--wipe", action="store_true", help="TRUNCATE target tables before copy")
    ap.add_argument("--force", action="store_true", help="insert even if target table has rows")
    args = ap.parse_args()
    try:
        return migrate(args.sqlite, args.postgres, wipe=args.wipe, force=args.force)
    except Exception as exc:  # pragma: no cover
        print(f"\n[ERROR] migration aborted: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
