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
TEXTFILE_DIR="${TEXTFILE_DIR:-/opt/leadgen/backups/metrics}"

# Prometheus textfile metric — drill PASS(1)/FAIL(0) + timestamp → silent-failure alert
# (node_exporter --collector.textfile.directory). "untested backup = no backup".
_emit_drill() {  # $1 = 1|0
  mkdir -p "${TEXTFILE_DIR}" 2>/dev/null || return 0
  {
    echo "# HELP leadgen_pg_restore_drill_success Last restore-drill verdict (1=pass,0=fail)"
    echo "# TYPE leadgen_pg_restore_drill_success gauge"
    echo "leadgen_pg_restore_drill_success ${1}"
    echo "# HELP leadgen_pg_restore_drill_content_ok Restored DB content integrity (1=critical tables present+non-empty,0=suspect)"
    echo "# TYPE leadgen_pg_restore_drill_content_ok gauge"
    echo "leadgen_pg_restore_drill_content_ok ${CONTENT_OK:-0}"
    echo "# HELP leadgen_pg_restore_drill_last_timestamp_seconds Last drill run (unix)"
    echo "# TYPE leadgen_pg_restore_drill_last_timestamp_seconds gauge"
    echo "leadgen_pg_restore_drill_last_timestamp_seconds $(date +%s)"
  } > "${TEXTFILE_DIR}/pg_restore_drill.prom.tmp" 2>/dev/null \
    && mv "${TEXTFILE_DIR}/pg_restore_drill.prom.tmp" "${TEXTFILE_DIR}/pg_restore_drill.prom" 2>/dev/null || true
}

# Combined exit handler — cleanup + emit metric (exit-code se pass/fail derive).
_on_exit() {
  local ec=$?
  docker rm -f "${TMP}" >/dev/null 2>&1 || true
  if [ "${ec}" -eq 0 ]; then _emit_drill 1; else _emit_drill 0; fi
}
trap _on_exit EXIT

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
for t in agent_events billing_records payments leads users; do
  c="$(docker exec "${TMP}" psql -U "${PG_USER}" -d "${PG_DB}" -tAc "select count(*) from ${t};" 2>/dev/null || echo 'n/a')"
  echo "    ${t}: ${c}"
done

# 4b) CONTENT INTEGRITY — "restored cleanly but empty/missing critical tables" guard.
# Ek dump table-COUNT sahi de ke bhi silently data miss kar sakta (galat DB, excluded
# schema) — "backups 8 mahine green the, sab khaali" failure. Critical tables EXIST karte
# hain? AUR DB empty-shell to nahi? (billing pre-revenue khaali ho sakta — uspe gate NAHI.)
CONTENT_OK=1
for t in users leads billing_records agent_events; do
  reg="$(docker exec "${TMP}" psql -U "${PG_USER}" -d "${PG_DB}" -tAc "select to_regclass('public.${t}');" 2>/dev/null || echo '')"
  if [[ -z "${reg}" ]]; then
    echo "    ⚠ MISSING critical table: ${t}"; CONTENT_OK=0
  fi
done
# Non-empty signal: core tables (users+leads+agent_events) ka total > 0 = backup khaali nahi.
SIG="$(docker exec "${TMP}" psql -U "${PG_USER}" -d "${PG_DB}" -tAc \
  "select coalesce((select count(*) from users),0)+coalesce((select count(*) from leads),0)+coalesce((select count(*) from agent_events),0);" 2>/dev/null || echo 0)"
echo "[$(date -Is)] content signal (users+leads+agent_events rows): ${SIG}"
if ! [[ "${SIG}" =~ ^[0-9]+$ ]] || (( SIG <= 0 )); then
  echo "    ⚠ EMPTY-SHELL: core tables me zero rows — backup suspect (data capture nahi hua?)"; CONTENT_OK=0
fi

# 5) Verdict — table-count AND content-integrity dono PASS hone chahiye.
if [[ "${TABLES:-0}" =~ ^[0-9]+$ ]] && (( TABLES >= MIN_TABLES )) && [[ "${CONTENT_OK}" == "1" ]]; then
  echo "[$(date -Is)] ✅ DRILL PASS (${TABLES} tables, content integrity OK)"
  exit 0
fi
echo "[$(date -Is)] ❌ DRILL FAIL — tables=${TABLES} (need >=${MIN_TABLES}), content_ok=${CONTENT_OK}. Backup suspect!"
exit 3
