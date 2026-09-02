#!/usr/bin/env bash
# LeadGen AI — health watchdog. Checks the app + reverse proxy + host, auto-restarts
# the app if it's down, and emails an alert (deduped to 1 per 30 min during an outage).
# Lightweight: pure shell + a tiny stdlib SMTP script (NO heavy app import) so it's
# safe to run every 5 minutes from cron.
#
# Cron (root):  */5 * * * *  /opt/leadgen/scripts/ops/health_monitor.sh >/dev/null 2>&1
APP_URL="${APP_URL:-http://127.0.0.1:8000/health}"
APP_DIR="${APP_DIR:-/opt/leadgen}"
LOG="${MONITOR_LOG:-$APP_DIR/logs/health_monitor.log}"
mkdir -p "$(dirname "$LOG")"

ts="$(date -Is)"
problems=""
add() { problems="$problems; $1"; }

systemctl is-active --quiet leadgen || add "leadgen service inactive"

code="$(curl -s -o /tmp/lg_health.out -w '%{http_code}' --max-time 10 "$APP_URL" 2>/dev/null || echo 000)"
[ "$code" = "200" ] || add "health http=$code"
grep -q 'healthy' /tmp/lg_health.out 2>/dev/null || add "health body not healthy"

systemctl is-active --quiet caddy || add "caddy inactive"

disk="$(df / | awk 'NR==2{gsub("%","",$5); print $5}')"
{ [ -n "$disk" ] && [ "$disk" -lt 90 ]; } 2>/dev/null || add "disk ${disk}%"

memp="$(free | awk '/Mem:/{printf("%d",$3/$2*100)}')"
{ [ -n "$memp" ] && [ "$memp" -lt 92 ]; } 2>/dev/null || add "mem ${memp}%"

if [ -z "$problems" ]; then
  echo "$ts OK (http=$code disk=${disk}% mem=${memp}%)" >> "$LOG"
  exit 0
fi

msg="LeadGen VPS alert${problems} (http=$code disk=${disk}% mem=${memp}%)"
echo "$ts $msg" >> "$LOG"

# Auto-recover: if the app is down, try a single restart.
if ! systemctl is-active --quiet leadgen; then
  if systemctl restart leadgen 2>/dev/null; then
    echo "$ts auto-restarted leadgen" >> "$LOG"
  fi
fi

# Email alert (best-effort, deduped: at most one email per 30 min).
stamp="$APP_DIR/logs/.last_alert_epoch"
now="$(date +%s)"
last="$(cat "$stamp" 2>/dev/null || echo 0)"
if [ "$(( now - last ))" -ge 1800 ]; then
  python3 "$APP_DIR/scripts/ops/alert_email.py" "$msg" >> "$LOG" 2>&1 || true
  echo "$now" > "$stamp"
fi
