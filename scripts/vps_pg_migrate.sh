#!/usr/bin/env bash
# =============================================================================
# vps_pg_migrate.sh  —  Zero-downtime SQLite -> Postgres migration using the
# LIVE VENV (no Docker image build needed; sidesteps requirements drift).
#
#   * Phase 0: backup leadgen.db + .env
#   * ensure POSTGRES_* in .env (generate password if missing)
#   * Phase 1: bring up Postgres + Redis containers (host-published 127.0.0.1)
#   * Phase 2: copy SQLite -> Postgres via the venv (READ-only on sqlite), verify
#
# Does NOT switch the live app. Phase 4 (DATABASE_URL switch + restart) is the
# separate ~1-min step. Idempotent / re-runnable.
# =============================================================================
set -euo pipefail
cd /opt/leadgen
COMPOSE="docker compose -f docker-compose.vps.yml"
TS=$(date +%Y%m%d_%H%M)

echo "######## find live venv python ########"
PY=$(systemctl cat leadgen 2>/dev/null | grep -oE '/[A-Za-z0-9_./-]*/(python|uvicorn)[0-9.]*' | head -1)
case "$PY" in *uvicorn*) PY="${PY%/uvicorn*}/python";; esac
[ -x "$PY" ] || PY=/opt/leadgen/.venv/bin/python
[ -x "$PY" ] || PY=/opt/leadgen/venv/bin/python
"$PY" --version || { echo "FATAL: no venv python found"; exit 1; }
echo "using python: $PY"

echo "######## Phase 0: backup ########"
[ -f leadgen.db ] && cp -v leadgen.db "leadgen.db.bak_$TS" || echo "WARN: no leadgen.db"
cp -v .env ".env.bak_$TS"

echo "######## ensure POSTGRES_* in .env ########"
grep -q '^POSTGRES_USER=' .env || echo 'POSTGRES_USER=leadgen' >> .env
grep -q '^POSTGRES_DB='   .env || echo 'POSTGRES_DB=leadgen'   >> .env
grep -q '^POSTGRES_PASSWORD=' .env || echo "POSTGRES_PASSWORD=$(openssl rand -hex 24)" >> .env
PGUSER=$(grep '^POSTGRES_USER=' .env | head -1 | cut -d= -f2)
PGPASS=$(grep '^POSTGRES_PASSWORD=' .env | head -1 | cut -d= -f2-)
PGDB=$(grep '^POSTGRES_DB='   .env | head -1 | cut -d= -f2)
SYNC_LOCAL="postgresql+psycopg2://$PGUSER:$PGPASS@127.0.0.1:5432/$PGDB"

echo "######## Phase 1: Postgres + Redis up (127.0.0.1 published, no downtime) ########"
$COMPOSE up -d db redis
echo "waiting for Postgres healthy..."
for i in $(seq 1 40); do docker exec leadgen_db pg_isready -U "$PGUSER" -d "$PGDB" >/dev/null 2>&1 && break; sleep 2; done
docker exec leadgen_db pg_isready -U "$PGUSER" -d "$PGDB"
docker exec leadgen_redis redis-cli ping

echo "######## Phase 2: migration deps + copy ########"
"$PY" -c "import psycopg2" 2>/dev/null || "$PY" -m pip install --quiet psycopg2-binary
"$PY" -c "import sqlalchemy,sys; print('sqlalchemy', sqlalchemy.__version__)"
DATABASE_URL="$SYNC_LOCAL" "$PY" scripts/migrate_sqlite_to_postgres.py \
  --sqlite sqlite:////opt/leadgen/leadgen.db --postgres "$SYNC_LOCAL" --wipe

echo ""
echo "######## MIGRATION DONE — Postgres has schema+data. Live app STILL on SQLite (zero downtime). ########"
echo "Verify the table above shows SRC == DST and [OK]."
echo ""
echo "PHASE 4 (manual, ~1 min downtime) on GO:"
echo "  1) in .env set/replace:"
echo "       DATABASE_URL=postgresql+asyncpg://$PGUSER:$PGPASS@127.0.0.1:5432/$PGDB"
echo "       REDIS_URL=redis://127.0.0.1:6379/0"
echo "  2) systemctl restart leadgen"
echo "  3) curl -fsS http://127.0.0.1:8000/health/ready   # database+redis = healthy"
echo "ROLLBACK: restore .env.bak_$TS ; systemctl restart leadgen   (SQLite untouched = zero loss)"
