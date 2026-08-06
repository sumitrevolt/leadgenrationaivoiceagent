#!/usr/bin/env bash
# =============================================================================
# infra_activate.sh — one-shot VPS infra activation (run once after deploy)
# Activates: observability stack, pg_backup cron, logrotate, rate-limiting
# Run: ssh root@VPS "cd /opt/leadgen && bash scripts/infra_activate.sh"
# =============================================================================
set -euo pipefail
LOG=/var/log/leadgen_infra_activate.log
ts() { date '+%Y-%m-%d %H:%M:%S'; }
echo "$(ts) === infra_activate START ===" | tee -a "$LOG"

# 1) Alertmanager SMTP password file (from env var on VPS)
SMTP_PASS="${SMTP_PASSWORD:-}"
if [ -n "$SMTP_PASS" ]; then
  echo "$SMTP_PASS" > monitoring/alertmanager_smtp_pass
  chmod 600 monitoring/alertmanager_smtp_pass
  echo "$(ts) alertmanager_smtp_pass written" | tee -a "$LOG"
else
  echo "$(ts) WARNING: SMTP_PASSWORD not set — alertmanager email alerts won't work" | tee -a "$LOG"
fi

# 2) Start observability stack (Prometheus + Grafana + Alertmanager + exporters)
echo "$(ts) Starting observability stack..." | tee -a "$LOG"
docker compose -f deploy/compose/docker-compose.observability.yml up -d 2>&1 | tail -10 | tee -a "$LOG"
echo "$(ts) Observability stack started" | tee -a "$LOG"

# 3) pg_backup.sh cron (2:30am IST = 21:00 UTC previous day)
CRON_LINE="30 21 * * * /opt/leadgen/scripts/pg_backup.sh >> /var/log/leadgen_backup.log 2>&1"
if crontab -l 2>/dev/null | grep -qF "pg_backup.sh"; then
  echo "$(ts) pg_backup cron already set" | tee -a "$LOG"
else
  (crontab -l 2>/dev/null; echo "$CRON_LINE") | crontab -
  echo "$(ts) pg_backup cron added: $CRON_LINE" | tee -a "$LOG"
fi

# 4) Logrotate config
if [ -f scripts/logrotate_leadgen.conf ]; then
  cp scripts/logrotate_leadgen.conf /etc/logrotate.d/leadgen
  echo "$(ts) logrotate config installed" | tee -a "$LOG"
fi

# 5) Enable PLAN_RATE_LIMIT + REQUEST_GUARD in .env (idempotent)
ENV_FILE=/opt/leadgen/.env
for VAR in PLAN_RATE_LIMIT REQUEST_GUARD; do
  if grep -q "^${VAR}=" "$ENV_FILE" 2>/dev/null; then
    sed -i "s/^${VAR}=.*/${VAR}=1/" "$ENV_FILE"
    echo "$(ts) $VAR=1 updated in .env" | tee -a "$LOG"
  else
    echo "${VAR}=1" >> "$ENV_FILE"
    echo "$(ts) $VAR=1 added to .env" | tee -a "$LOG"
  fi
done

# 6) Reload app container for new env vars
echo "$(ts) Recreating app container for new env..." | tee -a "$LOG"
docker compose -f docker-compose.vps.yml up -d --no-deps app 2>&1 | tail -5 | tee -a "$LOG"

# 7) Metrics dir for node_exporter textfile collector
mkdir -p /opt/leadgen/backups/metrics

# 8) Verify
sleep 10
HEALTH=$(curl -sf http://127.0.0.1:8000/health | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('status'),d.get('environment'))" 2>/dev/null || echo "FAIL")
echo "$(ts) Health: $HEALTH" | tee -a "$LOG"

OBS_UP=$(docker ps --format '{{.Names}}' | grep -c leadgen_prometheus || true)
echo "$(ts) Observability containers: $OBS_UP Prometheus instances running" | tee -a "$LOG"

BACKUP_DIR=/opt/leadgen/backups
mkdir -p "$BACKUP_DIR"
echo "$(ts) Backup dir ready: $BACKUP_DIR" | tee -a "$LOG"

echo "$(ts) === infra_activate DONE ===" | tee -a "$LOG"
echo ""
echo "Next steps:"
echo "  1. Check Grafana: ssh -L 3000:127.0.0.1:3000 root@72.61.245.204 -> http://localhost:3000"
echo "  2. Run backup test: bash scripts/pg_backup.sh"
echo "  3. Verify cron: crontab -l"
