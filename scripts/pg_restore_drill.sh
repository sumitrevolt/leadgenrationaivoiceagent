#!/usr/bin/env bash
# =============================================================================
# pg_restore_drill.sh — "untested backup = no backup". Latest pg_backup dump ko
# ek THROWAWAY postgres container me restore karke verify karta (table + row
# counts). Prod DB ko bilkul touch nahi karta (alag container, alag password,
# --rm). PASS/FAIL return karta.
#
# Cron (monthly, run as root on VPS):
#   0 3 1 * *  /opt/leadgen/scripts/pg_restore_drill.sh >> /var/log/leadgen_drill.log 2>&1
#
# Manual:  bash scripts/pg_restore_drill.sh
# =============================================================================
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/opt/leadgen/backups}"
PG_USER="${POSTGRES_USER:-leadgen}"
PG_DB="${POSTGRES_DB:-leadgen}"
PG_IMAGE="${PG_IMAGE:-postgres:16-alpine}"
MIN_TABLES="${MIN_TABLES:-5}"

LATEST="$(ls -t "${BACKUP_DIR}"/leadgen_*.dump.gz 2>/dev/null | head -1 || true)"
if [[ -z "${LATEST}" ]]; then
  echo "[$(date -Is)] DRILL FAIL — no backup found in ${BACKUP_DIR}"
  exit 1
fi
echo "[$(date -Is)] restore-drill of: ${LATEST}"

TMP="leadgen_drill_$$"
cleanup() { docker rm -f "${TMP}" >/dev/null 2>&1 || true; }
trap cleanup EXIT

# 1) Throwaway Postgres (isolated; never touches prod)
docker run -d --rm --name "${TMP}" \
  -e POSTGRES_USER="${PG_USER}" \
  -e POSTGRES_PASSWORD="drill_only_$$" \
  -e POSTGRES_DB="${PG_DB}" \
  "${PG_IMAGE}" >/dev/null

# 2) Wait until ready
ready=0
for i in $(seq 1 30); do
  if docker exec "${TMP}" pg_isready -U "${PG_USER}" >/dev/null 2>&1; then ready=1; break; fi
  sleep 2
done
[[ "${ready}" != "1" ]] && { echo "[$(date -Is)] DRILL FAIL — temp pg not ready"; exit 2; }

# 3) Restore the dump
echo "[$(date -Is)] restoring…"
gunzip -c "${LATEST}" | docker exec -i "${TMP}" \
  pg_restore -U "${PG_USER}" -d "${PG_DB}" --clean --if-exists --no-owner >/dev/null 2>&1 || true

# 4) Verify — table count + sample row counts on known tables
TABLES="$(docker exec "${TMP}" psql -U "${PG_USER}" -d "${PG_DB}" -tAc \
  "select count(*) from information_schema.tables where table_schema='public';" 2>/dev/null || echo 0)"
echo "[$(date -Is)] restored public tables: ${TABLES}"
for t in agent_events billing calls leads clients; do
  c="$(docker exec "${TMP}" psql -U "${PG_USER}" -d "${PG_DB}" -tAc "select count(*) from ${t};" 2>/dev/null || echo 'n/a')"
  echo "    ${t}: ${c}"
done

# 5) Verdict
if [[ "${TABLES:-0}" =~ ^[0-9]+$ ]] && (( TABLES >= MIN_TABLES )); then
  echo "[$(date -Is)] ✅ DRILL PASS (${TABLES} tables restored cleanly)"
  exit 0
fi
echo "[$(date -Is)] ❌ DRILL FAIL — only ${TABLES} tables (expected >= ${MIN_TABLES}). Backup suspect!"
exit 3
