#!/usr/bin/env bash
# vps_selfheal.sh — host-side self-healing loop (cron */10 min).  v2 (2026-06-14)
# -----------------------------------------------------------------------------
# WHY v2: aaj (2026-06-14) ka ~6h outage OLD self-heal ne AMPLIFY kiya tha.
# CPU-steal (Hostinger host throttle) ke karan app CPU-starved hoke "unhealthy"
# dikha. Old script har unhealthy container ko restart karta tha → har restart =
# fresh heavy import (~33s, ML embedder) = aur CPU demand = host aur throttle =
# vicious crash-loop. Restart-as-cure ne starvation ko worse kiya.
#
# FIX (v2): CPU-STEAL-AWARE.
#  - High steal (host throttle) pe RESTART nahi karte (amplify hota). Ulta heavy
#    workers SHED karte (stop) taaki scarce CPU web-app/site ko mile → site up rahe.
#  - Steal normal hone par hi normal restart-guard chalta, wo bhi RATE-LIMITED
#    (max 2 restart / 30min per container) → restart-storm impossible.
#  - ntfy alert (deduped 1/hour) jab load shed ho.
# Workers shed hone ke baad auto-restart NAHI hote (safe) — steal clear hone par
# manually/staggered restart karo (ntfy alert reminder bhejta).
#
# Idempotent, kabhi exit-nonzero nahi (cron spam na ho). Log: /var/log/leadgen_selfheal.log
set +e
LOG=/var/log/leadgen_selfheal.log
STATE=/var/run/leadgen_selfheal
ts() { date '+%Y-%m-%d %H:%M:%S'; }
NTFY="${NTFY_SELFHEAL_URL:-https://ntfy.leadsgenai.in/leadgen-alerts}"
now=$(date +%s)
mkdir -p "$STATE" 2>/dev/null

# --- 0) CPU-STEAL GATE (today's-outage fix) ---
# vmstat header se 'st' column dhoondo (kernel me 'gu' col ho sakta — robust), last data row se read.
STEAL=$(vmstat 1 2 2>/dev/null | awk 'NR==2{for(i=1;i<=NF;i++)if($i=="st")c=i} END{print (c?int($c):0)}')
STEAL=${STEAL:-0}
LIMIT=${SELFHEAL_STEAL_LIMIT:-40}

if [ "$STEAL" -ge "$LIMIT" ]; then
  echo "$(ts) HIGH_STEAL=${STEAL}% (>=$LIMIT) -> SHED heavy workers; NOT restarting app (restart amplifies starvation)" >> "$LOG"
  docker stop -t 5 leadgen_worker leadgen_worker_heavy leadgen_scheduler >/dev/null 2>&1
  af="$STATE/last_steal_alert"; last=$(cat "$af" 2>/dev/null || echo 0)
  if [ $((now-last)) -ge 3600 ]; then
    curl -s -m 5 -H "Title: LeadsGenAI self-heal" -d "CPU steal ${STEAL}% high - heavy workers shed to keep site up. Check Hostinger host (noisy neighbour) or reboot. Restart workers when steal normal." "$NTFY" >/dev/null 2>&1
    echo "$now" > "$af"
  fi
  exit 0
fi

# --- rate-limited restart helper (max 2 per 30min per container) ---
can_restart() {
  local f="$STATE/rl_$1" cutoff=$((now-1800)) n=0
  if [ -f "$f" ]; then
    awk -v c="$cutoff" '$1>=c' "$f" > "$f.t" 2>/dev/null && mv "$f.t" "$f"
    n=$(wc -l < "$f" 2>/dev/null)
  fi
  [ "${n:-0}" -lt 2 ]
}
note_restart() { echo "$now" >> "$STATE/rl_$1"; }

# --- 1) container guard (rate-limited) ---
for name in leadgen_app leadgen_worker leadgen_worker_heavy leadgen_scheduler leadgen_db leadgen_redis leadgen_redis_cache leadgen_pgbouncer leadgen_qdrant; do
  status=$(docker inspect -f '{{.State.Status}}' "$name" 2>/dev/null)
  health=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$name" 2>/dev/null)
  [ -z "$status" ] && continue
  if [ "$status" != "running" ] || [ "$health" = "unhealthy" ]; then
    if can_restart "$name"; then
      echo "$(ts) RESTART $name (status=$status health=$health steal=${STEAL}%)" >> "$LOG"
      docker restart "$name" >/dev/null 2>&1
      note_restart "$name"
    else
      echo "$(ts) SKIP_RESTART $name rate-limited >=2/30min (status=$status health=$health)" >> "$LOG"
    fi
  fi
done

# --- 2) app-level health double-check (rate-limited) ---
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 8 http://127.0.0.1:8000/health 2>/dev/null)
if [ "$code" != "200" ]; then
  if can_restart leadgen_app; then
    echo "$(ts) APP_HEALTH $code -> restart (steal=${STEAL}%)" >> "$LOG"
    docker restart leadgen_app >/dev/null 2>&1
    note_restart leadgen_app
  else
    echo "$(ts) APP_HEALTH $code -> SKIP rate-limited" >> "$LOG"
  fi
fi

# --- 3) disk space check (alert at 80%, emergency docker prune at 90%) ---
# Build-cache note: Dockerfile.lock builds can transiently need tens of GB.
# Keep .dockerignore excluding runtime data dirs (data/ollama, data/u2net, backups,
# recordings) so image export does not bake bind-mounted state into /app/data.
DISK_USED=$(df / --output=pcent 2>/dev/null | tail -1 | tr -d '% ')
DISK_USED=${DISK_USED:-0}
if [ "$DISK_USED" -ge 90 ]; then
  echo "$(ts) DISK_CRITICAL=${DISK_USED}% -> docker prune (emergency)" >> "$LOG"
  docker system prune -f --filter "until=48h" >/dev/null 2>&1
  curl -s -m 5 -H "Title: LeadsGenAI DISK CRITICAL" -d "Disk ${DISK_USED}% used — emergency docker prune ran. Check /opt/leadgen/logs + backups." -H "Tags: warning" "$NTFY" >/dev/null 2>&1
elif [ "$DISK_USED" -ge 80 ]; then
  af="$STATE/last_disk_alert"; last=$(cat "$af" 2>/dev/null || echo 0)
  if [ $((now-last)) -ge 3600 ]; then
    echo "$(ts) DISK_HIGH=${DISK_USED}% -> alert sent" >> "$LOG"
    curl -s -m 5 -H "Title: LeadsGenAI Disk High" -d "Disk ${DISK_USED}% used — manual cleanup needed (/opt/leadgen/logs, docker build cache, old backups). Before rebuild, verify .dockerignore excludes data/ollama + runtime media." "$NTFY" >/dev/null 2>&1
    echo "$now" > "$af"
  fi
fi

# --- 4) nightly data/ tarball (unchanged from v1) ---
HM=$(TZ=Asia/Kolkata date '+%H%M')
if [ "$HM" -ge 0330 ] && [ "$HM" -le 0339 ]; then
  BK=/opt/leadgen/backups/data
  mkdir -p "$BK"
  day=$(date '+%Y%m%d')
  if [ ! -f "$BK/data_$day.tar.gz" ]; then
    tar -czf "$BK/data_$day.tar.gz" -C /opt/leadgen data 2>/dev/null
    echo "$(ts) DATA_BACKUP $BK/data_$day.tar.gz ($(du -h "$BK/data_$day.tar.gz" 2>/dev/null | cut -f1))" >> "$LOG"
    find "$BK" -name 'data_*.tar.gz' -mtime +7 -delete 2>/dev/null
  fi
fi
exit 0
