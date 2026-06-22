#!/usr/bin/env bash
# =============================================================================
# vps_cutover_prep.sh  —  ZERO-DOWNTIME cutover prep (Phases 0-2).
#
#   * Phase 0: backup leadgen.db + .env (timestamped)
#   * ensure POSTGRES_* creds in .env (generate password if missing)
#   * Phase 1: bring up Postgres + Redis containers
#   * Phase 2: build app image, alembic upgrade head (on PG), copy SQLite->PG, verify
#
# DOES NOT stop systemd / DOES NOT change the live app's DATABASE_URL.
# The live app keeps serving on SQLite the whole time. Phase 3 (the ~1-min
# switch) is a SEPARATE manual step. Re-runnable (idempotent).
# =============================================================================
set -euo pipefail
cd /opt/leadgen
COMPOSE="docker compose -f docker-compose.vps.yml"
TS=$(date +%Y%m%d_%H%M)

echo "######## Phase 0: backup ########"
if [ -f leadgen.db ]; then cp -v leadgen.db "leadgen.db.bak_$TS"; else echo "WARN: no leadgen.db at /opt/leadgen"; fi
cp -v .env ".env.bak_$TS"

echo "######## ensure POSTGRES_* in .env ########"
grep -q '^POSTGRES_USER='     .env || echo 'POSTGRES_USER=leadgen' >> .env
grep -q '^POSTGRES_DB='       .env || echo 'POSTGRES_DB=leadgen'   >> .env
if ! grep -q '^POSTGRES_PASSWORD=' .env; then
  echo "POSTGRES_PASSWORD=$(openssl rand -hex 24)" >> .env
  echo "  -> generated new POSTGRES_PASSWORD"
fi
PGUSER=$(grep '^POSTGRES_USER='     .env | head -1 | cut -d= -f2)
PGPASS=$(grep '^POSTGRES_PASSWORD=' .env | head -1 | cut -d= -f2-)
PGDB=$(grep '^POSTGRES_DB='         .env | head -1 | cut -d= -f2)
ASYNC_URL="postgresql+asyncpg://$PGUSER:$PGPASS@db:5432/$PGDB"
SYNC_URL="postgresql+psycopg2://$PGUSER:$PGPASS@db:5432/$PGDB"

echo "######## Phase 1: Postgres + Redis up (no app, no downtime) ########"
$COMPOSE up -d db redis
echo "waiting for Postgres healthy..."
for i in $(seq 1 40); do
  if docker exec leadgen_db pg_isready -U "$PGUSER" -d "$PGDB" >/dev/null 2>&1; then break; fi
  sleep 2
done
docker exec leadgen_db pg_isready -U "$PGUSER" -d "$PGDB"
docker exec leadgen_redis redis-cli ping

echo "######## Phase 2: build app image (this can take a few min) ########"
$COMPOSE build app

echo "######## Phase 2a: alembic upgrade head on Postgres ########"
$COMPOSE run --rm -e DATABASE_URL="$ASYNC_URL" app alembic upgrade head

echo "######## Phase 2b: copy SQLite -> Postgres (live leadgen.db mounted READ-only) ########"
$COMPOSE run --rm \
  -v /opt/leadgen/leadgen.db:/app/leadgen.db:ro \
  -e DATABASE_URL="$SYNC_URL" \
  app python scripts/migrate_sqlite_to_postgres.py \
     --sqlite sqlite:////app/leadgen.db --postgres "$SYNC_URL"

echo ""
echo "######## PREP COMPLETE ########"
echo "Postgres now has schema + data. Live app STILL on SQLite (zero downtime so far)."
echo "Verify counts above show SRC == DST and [OK]."
echo ""
echo "PHASE 3 (manual, ~1 min downtime) when you give GO:"
echo "  1) add to .env:  DATABASE_URL=$ASYNC_URL"
echo "  2)               REDIS_URL=redis://redis:6379/0   (if not present)"
echo "  3) systemctl stop leadgen"
echo "  4) $COMPOSE up -d"
echo "  5) curl -fsS http://127.0.0.1:8000/health/ready"
echo "ROLLBACK: $COMPOSE down ; restore .env.bak_$TS ; systemctl start leadgen"
