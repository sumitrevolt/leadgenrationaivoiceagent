#!/usr/bin/env bash
# =============================================================================
# vps_cutover_switch.sh  —  PHASE 4: switch the live app SQLite -> Postgres+Redis.
# ~1 min downtime. AUTO-ROLLBACK to SQLite if /health/ready doesn't come back 200.
# Run ONLY after vps_pg_migrate.sh succeeded ([OK] all tables migrated).
# =============================================================================
set -uo pipefail
cd /opt/leadgen
TS=$(date +%Y%m%d_%H%M)

PGUSER=$(grep '^POSTGRES_USER=' .env | head -1 | cut -d= -f2)
PGPASS=$(grep '^POSTGRES_PASSWORD=' .env | head -1 | cut -d= -f2-)
PGDB=$(grep '^POSTGRES_DB=' .env | head -1 | cut -d= -f2)
ASYNC="postgresql+asyncpg://$PGUSER:$PGPASS@127.0.0.1:5432/$PGDB"

echo "backup .env -> .env.bak_switch_$TS"
cp .env ".env.bak_switch_$TS"

echo "set DATABASE_URL + REDIS_URL in .env"
if grep -q '^DATABASE_URL=' .env; then sed -i "s#^DATABASE_URL=.*#DATABASE_URL=$ASYNC#" .env; else echo "DATABASE_URL=$ASYNC" >> .env; fi
if grep -q '^REDIS_URL=' .env; then sed -i "s#^REDIS_URL=.*#REDIS_URL=redis://127.0.0.1:6379/0#" .env; else echo "REDIS_URL=redis://127.0.0.1:6379/0" >> .env; fi

echo "restarting leadgen (downtime starts)..."
systemctl restart leadgen

echo "waiting for /health/ready (up to ~60s)..."
ok=0
for i in $(seq 1 20); do
  code=$(curl -s -o /tmp/ready.json -w '%{http_code}' http://127.0.0.1:8000/health/ready 2>/dev/null || echo 000)
  if [ "$code" = "200" ]; then ok=1; break; fi
  sleep 3
done

echo "----- /health/ready -----"
cat /tmp/ready.json 2>/dev/null | head -c 1000; echo

if [ "$ok" = "1" ]; then
  echo ""
  echo "✅ CUTOVER OK — live app is now on Postgres + Redis."
  echo "   (SQLite backups kept: leadgen.db.bak_* ; rollback still possible.)"
else
  echo ""
  echo "❌ HEALTH NOT 200 — AUTO-ROLLBACK to SQLite"
  cp ".env.bak_switch_$TS" .env
  systemctl restart leadgen
  sleep 6
  curl -s -o /dev/null -w 'rollback /health: %{http_code}\n' http://127.0.0.1:8000/health 2>/dev/null || true
  echo "ROLLED BACK to SQLite. Logs: journalctl -u leadgen -n 100 --no-pager"
  exit 1
fi
