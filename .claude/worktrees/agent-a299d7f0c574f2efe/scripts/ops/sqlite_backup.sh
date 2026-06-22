#!/usr/bin/env bash
# LeadGen AI — consistent online SQLite backup + gzip + retention.
# Uses Python's stdlib sqlite3 .backup() (no sqlite3 CLI dep) so the copy is
# transaction-consistent even while the app is writing. Never corrupts the live DB.
#
# Cron (root):  30 3 * * *  /opt/leadgen/scripts/ops/sqlite_backup.sh >> /opt/leadgen/logs/backup.log 2>&1
# Tunables via env: APP_DIR, DB_PATH, BACKUP_DIR, RETENTION_DAYS, OFFSITE_RCLONE_REMOTE
set -uo pipefail

APP_DIR="${APP_DIR:-/opt/leadgen}"
DB="${DB_PATH:-$APP_DIR/leadgen.db}"
BACKUP_DIR="${BACKUP_DIR:-$APP_DIR/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"

mkdir -p "$BACKUP_DIR"
ts="$(date +%Y%m%d_%H%M%S)"
out="$BACKUP_DIR/leadgen_${ts}.db"

if [ ! -f "$DB" ]; then
  echo "$(date -Is) ERROR: db not found: $DB"
  exit 1
fi

# Online-consistent backup via stdlib sqlite3 .backup (portable, no CLI dependency).
python3 - "$DB" "$out" <<'PY'
import sqlite3, sys
src = sqlite3.connect(sys.argv[1])
dst = sqlite3.connect(sys.argv[2])
with dst:
    src.backup(dst)
dst.close()
src.close()
PY

if [ ! -f "$out" ]; then
  echo "$(date -Is) ERROR: backup file not created"
  exit 1
fi

gzip -9 -f "$out"
sz="$(du -h "${out}.gz" 2>/dev/null | cut -f1)"
echo "$(date -Is) backup ok: ${out}.gz (${sz})"

# Retention: drop archives older than N days.
find "$BACKUP_DIR" -name 'leadgen_*.db.gz' -mtime +"$RETENTION_DAYS" -delete 2>/dev/null || true

# Optional OFFSITE copy (set OFFSITE_RCLONE_REMOTE=remote:path and install rclone).
if [ -n "${OFFSITE_RCLONE_REMOTE:-}" ] && command -v rclone >/dev/null 2>&1; then
  if rclone copy "${out}.gz" "$OFFSITE_RCLONE_REMOTE" 2>/dev/null; then
    echo "$(date -Is) offsite copied -> $OFFSITE_RCLONE_REMOTE"
  else
    echo "$(date -Is) WARN: offsite copy failed"
  fi
fi
