#!/usr/bin/env bash
set -u
cd /opt/leadgen
echo "=== Postgres payment + subscription truth (read-only) ==="
docker exec leadgen_app python - <<'PY' 2>&1
import asyncio
from sqlalchemy import text
from app.db.session import get_engine

async def main():
    eng = get_engine()
    with eng.connect() as c:
        n = c.execute(text("SELECT COUNT(*) FROM payments")).scalar()
        total = c.execute(text("SELECT COALESCE(SUM(amount_inr),0) FROM payments WHERE status='paid'")).scalar()
        print(f"payments_total_rows={n} verified_paid_total_inr={total}")
        for r in c.execute(text("SELECT id, client_id, amount_inr, status FROM payments ORDER BY id DESC LIMIT 4")):
            print("payment:", dict(r._mapping))
        for r in c.execute(text("SELECT c.name, s.status, s.plan_key FROM clients c JOIN subscriptions s ON s.client_id=c.id LIMIT 6")):
            print("client_sub:", dict(r._mapping))
    print("QUERY_OK")

asyncio.run(main())
PY
