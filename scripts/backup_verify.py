#!/usr/bin/env python3
"""Backup verify — create + test restore (Playbook zero-tolerance gate).

Usage:
    python scripts/backup_verify.py          # full test
    python scripts/backup_verify.py --quick # backup only, no restore

Exit 0 = backup + restore OK. Exit 1 = failure.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKUP_DIR = Path(os.environ.get("BACKUP_DIR", "/opt/leadgen/data/backups"))
DB_URL = os.environ.get("DATABASE_URL", "postgresql://leadgen:password@pgbouncer:6432/leadgen")


def run(cmd: list[str], timeout: int = 60) -> tuple[int, str, str]:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout, r.stderr


def pg_backup() -> Path | None:
    """Create a pg_dump backup. Returns path or None."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    dump_path = BACKUP_DIR / f"leadgen_backup_{ts}.sql"

    # Extract DB host/port from env or use defaults
    host = os.environ.get("PGHOST", "pgbouncer")
    port = os.environ.get("PGPORT", "6432")
    user = os.environ.get("PGUSER", "leadgen")
    db = os.environ.get("PGDATABASE", "leadgen")

    cmd = ["pg_dump", "-h", host, "-p", port, "-U", user, "-d", db, "-f", str(dump_path)]
    rc, out, err = run(cmd, timeout=120)
    if rc != 0:
        print(f"[BACKUP FAIL] pg_dump exit={rc}\n{err[:500]}")
        return None

    size = dump_path.stat().st_size
    print(f"[BACKUP OK] {dump_path} ({size} bytes)")
    return dump_path


def pg_restore_test(dump_path: Path) -> bool:
    """Test restore to a temporary database."""
    test_db = "leadgen_restore_test"
    host = os.environ.get("PGHOST", "pgbouncer")
    port = os.environ.get("PGPORT", "6432")
    user = os.environ.get("PGUSER", "leadgen")

    # Create test DB
    rc, _, err = run(["dropdb", "-h", host, "-p", port, "-U", user, "--if-exists", test_db])
    rc, _, err = run(["createdb", "-h", host, "-p", port, "-U", user, test_db])
    if rc != 0:
        print(f"[RESTORE FAIL] createdb failed: {err[:500]}")
        return False

    # Restore
    rc, out, err = run(
        ["psql", "-h", host, "-p", port, "-U", user, "-d", test_db, "-f", str(dump_path)],
        timeout=120,
    )
    if rc != 0:
        print(f"[RESTORE FAIL] psql exit={rc}\n{err[:500]}")
        return False

    # Verify: count tables
    rc, out, err = run(
        [
            "psql",
            "-h",
            host,
            "-p",
            port,
            "-U",
            user,
            "-d",
            test_db,
            "-c",
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public';",
        ]
    )
    if rc != 0:
        print(f"[RESTORE VERIFY FAIL] table count failed: {err[:500]}")
        return False

    # Parse psql output: extract number from lines like " count \n-------\n    42\n(1 row)"
    table_count = 0
    for line in out.strip().splitlines():
        stripped = line.strip()
        if stripped.isdigit():
            table_count = int(stripped)
            break

    print(f"[RESTORE OK] {table_count} tables restored successfully")

    # Cleanup
    run(["dropdb", "-h", host, "-p", port, "-U", user, "--if-exists", test_db])
    return table_count > 0


def main() -> int:
    args = sys.argv[1:]
    quick = "--quick" in args

    print("[backup_verify] Starting backup test...")
    print(f"  BACKUP_DIR={BACKUP_DIR}")
    print("  DB_URL (host:port)=127.0.0.1:6432")
    print("=" * 60)

    # 1. Backup
    dump = pg_backup()
    if not dump:
        print("[FAIL] Backup creation failed")
        return 1

    if quick:
        print("[OK] Quick mode — backup created, restore skipped")
        return 0

    # 2. Restore
    if not pg_restore_test(dump):
        print("[FAIL] Restore test failed")
        return 1

    print("\n[OK] Backup + Restore test passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
