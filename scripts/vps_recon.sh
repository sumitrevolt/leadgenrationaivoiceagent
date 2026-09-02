#!/usr/bin/env bash
# Read-only VPS recon before cutover. Touches NOTHING. Safe to run anytime.
set -uo pipefail
cd /opt/leadgen 2>/dev/null || { echo "FATAL: /opt/leadgen missing"; exit 1; }
echo "=== HOST ==="; uname -sr
echo "=== DOCKER ==="; docker --version; docker compose version 2>/dev/null || echo "compose v2 missing"
echo "=== DISK (/) ==="; df -h / | tail -1
echo "=== MEM (MB) ==="; free -m | awk 'NR==1||NR==2'
echo "=== RUNNING CONTAINERS ==="; docker ps --format '{{.Names}}  {{.Status}}' 2>/dev/null || echo none
echo "=== REPO HEAD ==="; git log --oneline -1
echo "=== compose+scripts present (after pull)? ==="
for f in docker-compose.vps.yml scripts/migrate_sqlite_to_postgres.py scripts/vps_cutover_prep.sh deploy/legacy/Dockerfile.production; do
  [ -f "$f" ] && echo "  ok  $f" || echo "  MISS $f"
done
echo "=== systemd leadgen ==="; systemctl is-active leadgen 2>/dev/null || echo "not-active"
echo "=== live DATABASE_URL (masked) ==="; grep -E '^DATABASE_URL=' .env 2>/dev/null | sed -E 's#://[^@]*@#://***@#' || echo "none"
echo "=== POSTGRES_PASSWORD already set? ==="; grep -q '^POSTGRES_PASSWORD=' .env 2>/dev/null && echo yes || echo no
echo "=== leadgen.db ==="; ls -lh leadgen.db 2>/dev/null | awk '{print $5, $9}' || echo "no leadgen.db"
echo "=== :8000 listener ==="; { ss -ltn 2>/dev/null || netstat -ltn 2>/dev/null; } | grep -E '[:.]8000' || echo "none"
echo "=== openssl available (for pw gen) ==="; command -v openssl >/dev/null && echo yes || echo no
echo "=== RECON DONE ==="
