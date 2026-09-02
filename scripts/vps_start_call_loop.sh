#!/bin/bash
# Run on VPS host — persistent cold-call loop
LOG=/opt/leadgen/data/call_loop.log
PIDFILE=/opt/leadgen/data/call_loop.pid

if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "call loop already running pid=$(cat "$PIDFILE")"
  tail -5 "$LOG" 2>/dev/null || true
  exit 0
fi

nohup docker exec leadgen_app python3 scripts/fire_calls_loop.py \
  --batch-size 3 --platform --learn --pause-batch 120 \
  >> "$LOG" 2>&1 &
echo $! > "$PIDFILE"
echo "started call loop host_pid=$(cat "$PIDFILE") log=$LOG"
sleep 3
tail -8 "$LOG" 2>/dev/null || true
