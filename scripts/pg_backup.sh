#!/usr/bin/env bash
# =============================================================================
# pg_backup.sh — nightly Postgres backup for the dockerised VPS stack.
#
#   * pg_dump (custom format, compressed) from the leadgen_db container
#   * keeps 30 days locally in /opt/leadgen/backups
#   * OPTIONAL offsite copy via rclone — only runs if an rclone remote is
#     configured. Any rclone remote works (Cloudflare R2 / Backblaze B2 /
#     Google Drive / etc.) — see deploy/offsite/rclone.conf.example for setup
#     of all three, including the Google Drive OAuth steps.
#
# Cron (run as root on the VPS):
#   30 2 * * *  /opt/leadgen/scripts/pg_backup.sh >> /var/log/leadgen_backup.log 2>&1
#
# Restore:
#   gunzip -c backups/leadgen_YYYYmmdd_HHMM.dump.gz | \
#     docker exec -i leadgen_db pg_restore -U leadgen -d leadgen --clean --if-exists
# =============================================================================
set -euo pipefail

DB_CONTAINER="${DB_CONTAINER:-leadgen_db}"
PG_USER="${POSTGRES_USER:-leadgen}"
PG_DB="${POSTGRES_DB:-leadgen}"
BACKUP_DIR="${BACKUP_DIR:-/opt/leadgen/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
# Set RCLONE_REMOTE (e.g. "r2:leadgen-backups" / "gdrive:leadgen-backups") to enable offsite copy.
RCLONE_REMOTE="${RCLONE_REMOTE:-}"

STAMP="$(date +%Y%m%d_%H%M)"
OUT="${BACKUP_DIR}/leadgen_${STAMP}.dump.gz"

mkdir -p "${BACKUP_DIR}"

echo "[$(date -Is)] backup start -> ${OUT}"
docker exec "${DB_CONTAINER}" pg_dump -U "${PG_USER}" -d "${PG_DB}" -F c \
  | gzip -9 > "${OUT}"

SIZE="$(du -h "${OUT}" | cut -f1)"
echo "[$(date -Is)] dump ok (${SIZE})"

# Local retention
find "${BACKUP_DIR}" -name 'leadgen_*.dump.gz' -mtime +"${RETENTION_DAYS}" -delete
echo "[$(date -Is)] pruned local backups older than ${RETENTION_DAYS}d"

# Offsite (only if configured + rclone present)
if [[ -n "${RCLONE_REMOTE}" ]] && command -v rclone >/dev/null 2>&1; then
  echo "[$(date -Is)] offsite copy -> ${RCLONE_REMOTE}"
  rclone copy "${OUT}" "${RCLONE_REMOTE}/" --no-traverse
  # Mirror retention offsite (best-effort). --include scopes this to ONLY DB
  # dumps — scripts/data_backup_rclone.sh shares this same RCLONE_REMOTE with
  # a shorter 7-day retention; an unscoped delete here would be harmless (30d
  # cap is looser), but the reverse direction is a real bug — kept scoped on
  # both sides for symmetry/clarity.
  rclone delete "${RCLONE_REMOTE}/" --min-age "${RETENTION_DAYS}d" --include "leadgen_*.dump.gz" || true
  echo "[$(date -Is)] offsite ok"
else
  echo "[$(date -Is)] offsite skipped (set RCLONE_REMOTE + install rclone to enable)"
fi

# Prometheus textfile metric (node_exporter --collector.textfile.directory) → backup
# stale/fail alerting. Success path pe hi pohnchte (set -e); fail = timestamp stale =
# alert. Best-effort (|| true) — metric-write kabhi backup ko fail na kare.
TEXTFILE_DIR="${TEXTFILE_DIR:-/opt/leadgen/backups/metrics}"
if mkdir -p "${TEXTFILE_DIR}" 2>/dev/null; then
  {
    echo "# HELP leadgen_pg_backup_last_success_timestamp_seconds Last successful pg_dump (unix)"
    echo "# TYPE leadgen_pg_backup_last_success_timestamp_seconds gauge"
    echo "leadgen_pg_backup_last_success_timestamp_seconds $(date +%s)"
    echo "# HELP leadgen_pg_backup_size_bytes Size of last pg_dump"
    echo "# TYPE leadgen_pg_backup_size_bytes gauge"
    echo "leadgen_pg_backup_size_bytes $(stat -c%s "${OUT}" 2>/dev/null || echo 0)"
  } > "${TEXTFILE_DIR}/pg_backup.prom.tmp" 2>/dev/null \
    && mv "${TEXTFILE_DIR}/pg_backup.prom.tmp" "${TEXTFILE_DIR}/pg_backup.prom" 2>/dev/null || true
fi

echo "[$(date -Is)] backup complete"
