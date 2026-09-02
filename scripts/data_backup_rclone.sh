#!/usr/bin/env bash
# =============================================================================
# data_backup_rclone.sh — nightly data/ directory backup via rclone.
#
#   * Tars + gzips /opt/leadgen/data (excluding regenerable cache dirs — same
#     exclusion list as scripts/offsite_email_backup.py, kept in sync)
#   * Keeps 7 days locally in BACKUP_DIR (data/ tarballs are bigger than DB
#     dumps — shorter local retention than pg_backup.sh's 30 days)
#   * OPTIONAL offsite copy via rclone (same RCLONE_REMOTE as pg_backup.sh —
#     see deploy/offsite/rclone.conf.example, incl. Google Drive setup)
#   * No size cap (unlike offsite_email_backup.py's 18MB email-attachment
#     limit) — this is the full data/ directory, real offsite via rclone.
#
# Cron (run as root on the VPS, after pg_backup.sh):
#   45 2 * * *  /opt/leadgen/scripts/data_backup_rclone.sh >> /var/log/leadgen_backup.log 2>&1
#
# Restore:
#   tar -xzf leadgen_data_YYYYmmdd_HHMM.tar.gz -C /opt/leadgen/
# =============================================================================
set -euo pipefail

BASE="${LEADGEN_BASE:-/opt/leadgen}"
DATA_DIR="${BASE}/data"
BACKUP_DIR="${BACKUP_DIR:-/opt/leadgen/backups}"
RETENTION_DAYS="${DATA_RETENTION_DAYS:-7}"
# Same remote as pg_backup.sh — set once, both scripts use it.
RCLONE_REMOTE="${RCLONE_REMOTE:-}"
# Kept in sync with scripts/offsite_email_backup.py's EXCLUDE_DIRS.
# ollama (1.8G) + u2net (168M) = re-downloadable ML assets; backups = nested
# backup dir (redundant — pg dumps go offsite separately). Without these the
# nightly tar is ~2GB and fills a 15GB free Drive in a week (2026-07-02 drill).
EXCLUDE_DIRS=(ai_images reels jingles bg_removed vectorstore conversations logos ollama u2net backups)

STAMP="$(date +%Y%m%d_%H%M)"
OUT="${BACKUP_DIR}/leadgen_data_${STAMP}.tar.gz"

mkdir -p "${BACKUP_DIR}"

if [[ ! -d "${DATA_DIR}" ]]; then
  echo "[$(date -Is)] data dir not found: ${DATA_DIR} — skipping"
  exit 0
fi

TAR_EXCLUDES=()
for d in "${EXCLUDE_DIRS[@]}"; do
  TAR_EXCLUDES+=(--exclude="data/${d}")
done

echo "[$(date -Is)] data backup start -> ${OUT}"
# Run from BASE so the tarball's paths are "data/..." (matches the restore command above).
tar -czf "${OUT}" -C "${BASE}" "${TAR_EXCLUDES[@]}" data

SIZE="$(du -h "${OUT}" | cut -f1)"
echo "[$(date -Is)] data tar ok (${SIZE})"

# Local retention (shorter than pg_backup.sh — these are bigger files)
find "${BACKUP_DIR}" -name 'leadgen_data_*.tar.gz' -mtime +"${RETENTION_DAYS}" -delete
echo "[$(date -Is)] pruned local data backups older than ${RETENTION_DAYS}d"

# Offsite (only if configured + rclone present) — same remote as pg_backup.sh,
# so scripts/backup_offsite_check.py's freshness check covers both automatically.
# IMPORTANT: --include scopes the prune to ONLY this script's own filename
# pattern. Both scripts share one RCLONE_REMOTE root with DIFFERENT retention
# (7d here vs pg_backup.sh's 30d) — an unscoped `rclone delete` here would
# also prune pg_backup.sh's DB dumps down to 7 days, silently shortening its
# intended 30-day retention. Caught in review before this shipped.
if [[ -n "${RCLONE_REMOTE}" ]] && command -v rclone >/dev/null 2>&1; then
  echo "[$(date -Is)] offsite copy -> ${RCLONE_REMOTE}"
  rclone copy "${OUT}" "${RCLONE_REMOTE}/" --no-traverse
  rclone delete "${RCLONE_REMOTE}/" --min-age "${RETENTION_DAYS}d" --include "leadgen_data_*.tar.gz" || true
  echo "[$(date -Is)] offsite ok"
else
  echo "[$(date -Is)] offsite skipped (set RCLONE_REMOTE + install rclone to enable — see deploy/offsite/rclone.conf.example)"
fi

echo "[$(date -Is)] data backup complete"
