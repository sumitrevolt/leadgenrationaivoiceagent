#!/usr/bin/env bash
# vps_selfheal.sh — host-side self-healing loop (cron */10 min).
# 1) Unhealthy/exited leadgen containers ko restart karo (Docker restart-policy
#    ke upar EXTRA guard — healthcheck-fail wale "running but unhealthy" cases).
# 2) Nightly (03:30 IST window me) data/ jsonl-stores ka tarball backup (7 din rotate)
#    — Postgres pg_backup.sh me hai, par jsonl stores (leads/cadence/dunning/etc.)
#    ka apna backup nahi tha.
# Idempotent, kabhi exit-nonzero nahi (cron spam na ho). Log: /var/log/leadgen_selfheal.log
set +e
LOG=/var/log/leadgen_selfheal.log
ts() { date '+%Y-%m-%d %H:%M:%S'; }

# --- 1) container guard ---
for name in leadgen_app leadgen_worker leadgen_scheduler leadgen_db leadgen_redis leadgen_pgbouncer; do
  status=$(docker inspect -f '{{.State.Status}}' "$name" 2>/dev/null)
  health=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$name" 2>/dev/null)
  if [ -z "$status" ]; then
    continue  # container exist hi nahi (e.g. profile off) — skip
  fi
  if [ "$status" != "running" ] || [ "$health" = "unhealthy" ]; then
    echo "$(ts) RESTART $name (status=$status health=$health)" >> "$LOG"
    docker restart "$name" >/dev/null 2>&1
  fi
done

# --- 2) app-level health double-check (Caddy ke peeche wala port) ---
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 8 http://127.0.0.1:8000/health 2>/dev/null)
if [ "$code" != "200" ]; then
  echo "$(ts) APP_HEALTH $code -> app restart" >> "$LOG"
  docker restart leadgen_app >/dev/null 2>&1
fi

# --- 3) nightly data/ tarball (sirf 03:30-03:39 IST window me ek baar) ---
HM=$(TZ=Asia/Kolkata date '+%H%M')
if [ "$HM" -ge 0330 ] && [ "$HM" -le 0339 ]; then
  BK=/opt/leadgen/backups/data
  mkdir -p "$BK"
  day=$(date '+%Y%m%d')
  if [ ! -f "$BK/data_$day.tar.gz" ]; then
    tar -czf "$BK/data_$day.tar.gz" -C /opt/leadgen data 2>/dev/null
    echo "$(ts) DATA_BACKUP $BK/data_$day.tar.gz ($(du -h "$BK/data_$day.tar.gz" 2>/dev/null | cut -f1))" >> "$LOG"
    # 7 din se purane hatao
    find "$BK" -name 'data_*.tar.gz' -mtime +7 -delete 2>/dev/null
  fi
fi
exit 0
