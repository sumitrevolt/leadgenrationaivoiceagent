#!/usr/bin/env bash
set -u
echo "=== admin_tasks.db exists? ==="
ls -la /opt/leadgen/data/admin_tasks.db 2>&1
echo
echo "=== where is the task ledger in code? ==="
grep -rn "admin_tasks" /opt/leadgen/app/admin/services/task_ledger.py 2>/dev/null | head -5
grep -rln "ADMIN_TASKS_DB\|admin_tasks.db" /opt/leadgen/app /opt/leadgen/config 2>/dev/null | head -5
echo
echo "=== Postgres is canonical task store — query via pgbouncer ==="
docker exec leadgen_app python - <<'PY' 2>&1 | head -20
import os, json, asyncio
from app.utils.logger import setup_logger
try:
    from sqlalchemy import text
    from app.db.session import get_engine
    eng = get_engine()
    with eng.connect() as conn:
        rows = conn.execute(text("SELECT id, status, updated_at FROM admin_tasks WHERE id LIKE 'PLT-113%' LIMIT 5")).fetchall()
        for r in rows:
            print(r)
        if not rows:
            tables = conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public'")).fetchall()
            print("PLT-113 not found in admin_tasks. public tables:", [t[0] for t in tables])
except Exception as e:
    print("ERR", type(e).__name__, e)
PY
