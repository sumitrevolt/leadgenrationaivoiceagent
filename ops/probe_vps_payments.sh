#!/usr/bin/env bash
set -u
cd /opt/leadgen
echo "=== Postgres payment truth (read-only) ==="
docker exec leadgen_app python - <<'PY' 2>&1 | tail -8
import asyncio
from sqlalchemy import text
from app.db.session import get_engine

async def main():
    eng = get_engine()
    with eng.connect() as c:
        n = c.execute(text("SELECT COUNT(*) FROM payments")).scalar()
        total = c.execute(text("SELECT COALESCE(SUM(amount_inr),0) FROM payments WHERE status='paid'")).scalar()
        print(f"payments rows={n} verified_paid_total_inr={total}")
        for r in c.execute(text("SELECT id, client_id, amount_inr, status, verified_at FROM payments ORDER BY id DESC LIMIT 3")):
            print(dict(r._mapping))
        for r in c.execute(text("SELECT c.id, c.name, s.status, p.plan_key FROM clients c LEFT JOIN subscriptions s ON s.client_id=c.id LEFT JOIN plans p ON p.id=s.plan_id LIMIT 5")):
            print(dict(r._mapping))

asyncio.run(main())
PY
