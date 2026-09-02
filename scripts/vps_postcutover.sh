#!/usr/bin/env bash
# Post-cutover: smoke test the live site + install nightly pg_backup cron + test backup.
set -uo pipefail
cd /opt/leadgen

echo "=== local /health/ready ==="
curl -s -o /dev/null -w '  health/ready: %{http_code}\n' http://127.0.0.1:8000/health/ready

echo "=== public (via Caddy/TLS) ==="
for path in "/health" "/" "/audit" "/blog" "/api/data/niches?tier=S"; do
  code=$(curl -s -o /dev/null -w '%{http_code}' "https://leadsgenai.in$path" 2>/dev/null || echo 000)
  echo "  $code  https://leadsgenai.in$path"
done

echo "=== niches API body (proves Postgres read path) ==="
curl -s "https://leadsgenai.in/api/data/niches?tier=S" 2>/dev/null | head -c 240; echo

echo "=== containers + systemd ==="
docker ps --format '  {{.Names}}  {{.Status}}'
echo -n "  leadgen systemd: "; systemctl is-active leadgen

echo "=== install nightly pg_backup cron (02:30 IST) ==="
chmod +x scripts/pg_backup.sh 2>/dev/null || true
if crontab -l 2>/dev/null | grep -q 'pg_backup.sh'; then
  echo "  cron already present"
else
  ( crontab -l 2>/dev/null; echo "30 2 * * * /opt/leadgen/scripts/pg_backup.sh >> /var/log/leadgen_backup.log 2>&1" ) | crontab -
  echo "  cron installed"
fi

echo "=== install DR / offsite backup crons (idempotent) ==="
# These 3 were originally hand-installed over SSH (SESSION_LOG 2026-07-02) so a VPS
# rebuild silently lost them. Codified here in the same grep-guard style as pg_backup.
chmod +x scripts/data_backup_rclone.sh scripts/pg_restore_drill.sh 2>/dev/null || true
# Offsite scripts ko RCLONE_REMOTE chahiye, par cron ka env minimal hota (.env load
# nahi hota). SESSION_LOG 2026-07-02: "crontab dono jobs env-prefixed" — isliye .env
# se value nikaal ke offsite crons pe inline prefix karo. Empty => script offsite
# gracefully skip karta (no-op), koi nuksaan nahi.
RCLONE_REMOTE="$(grep -E '^[[:space:]]*RCLONE_REMOTE=' /opt/leadgen/.env 2>/dev/null | tail -1 | cut -d= -f2- | sed 's/[[:space:]]*#.*$//' | xargs)"
RC_PREFIX=""
[ -n "${RCLONE_REMOTE}" ] && RC_PREFIX="RCLONE_REMOTE=${RCLONE_REMOTE} "

# 1) data/ dir nightly backup + offsite (pg_backup ke 30 2 ke turant baad)
if crontab -l 2>/dev/null | grep -q 'data_backup_rclone.sh'; then
  echo "  data_backup_rclone cron already present"
else
  ( crontab -l 2>/dev/null; echo "45 2 * * * ${RC_PREFIX}/opt/leadgen/scripts/data_backup_rclone.sh >> /var/log/leadgen_backup.log 2>&1" ) | crontab -
  echo "  data_backup_rclone cron installed"
fi

# 2) offsite freshness sensor (local/offsite backup stale ho to alert)
if crontab -l 2>/dev/null | grep -q 'backup_offsite_check.py'; then
  echo "  backup_offsite_check cron already present"
else
  ( crontab -l 2>/dev/null; echo "0 9 * * * ${RC_PREFIX}python3 /opt/leadgen/scripts/backup_offsite_check.py >> /var/log/leadgen_backup.log 2>&1" ) | crontab -
  echo "  backup_offsite_check cron installed"
fi

# 3) monthly restore-drill (RestoreDrillStale >40d alert satisfy karta; local dump use)
if crontab -l 2>/dev/null | grep -q 'pg_restore_drill.sh'; then
  echo "  pg_restore_drill cron already present"
else
  ( crontab -l 2>/dev/null; echo "15 3 1 * * /opt/leadgen/scripts/pg_restore_drill.sh >> /var/log/leadgen_drill.log 2>&1" ) | crontab -
  echo "  pg_restore_drill cron installed"
fi

echo "=== test backup once now ==="
bash scripts/pg_backup.sh 2>&1 | tail -4
ls -lh /opt/leadgen/backups/ 2>/dev/null | tail -2
echo "POSTCUTOVER DONE"
