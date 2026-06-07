#!/usr/bin/env bash
# LeadGen AI — daily VPS backup (data/ + sqlite DBs + .env) — keep 7 days.
# Installed by scripts/backup_setup.bat → cron @ 04:00 IST daily.
set -u
APP=/opt/leadgen
DEST=/root/backups
STAMP=$(date +%F)
mkdir -p "$DEST"
cd "$APP" || exit 1
tar -czf "$DEST/leadgen_data_$STAMP.tgz" \
    --exclude='data/vectorstore' \
    data/ .env *.db 2>/dev/null
# Qdrant storage (docker volume dir) — lightweight snapshot copy
if [ -d /opt/qdrant_storage ]; then
  tar -czf "$DEST/qdrant_$STAMP.tgz" -C /opt qdrant_storage 2>/dev/null
fi
# Retention: keep last 7 of each
ls -1t "$DEST"/leadgen_data_*.tgz 2>/dev/null | tail -n +8 | xargs -r rm -f
ls -1t "$DEST"/qdrant_*.tgz 2>/dev/null | tail -n +8 | xargs -r rm -f
echo "backup done $STAMP: $(ls -lh $DEST | tail -3 | awk '{print $9, $5}' | tr '\n' ' ')"
