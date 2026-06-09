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

echo "=== test backup once now ==="
bash scripts/pg_backup.sh 2>&1 | tail -4
ls -lh /opt/leadgen/backups/ 2>/dev/null | tail -2
echo "POSTCUTOVER DONE"
