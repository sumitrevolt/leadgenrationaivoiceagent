---
name: loop
description: Run a prompt or skill on a recurring interval (e.g. check deploy every 5m). Use when the user asks for periodic monitoring, /loop, or self-pacing repeated tasks. Claude Code uses shell background loops with output notifications.
---
# Loop (Claude Code)

Recurring local work — Cursor `/loop` ka Claude equivalent.

## Parse

- `every 5m check health` · `loop 30s pytest` · dynamic = agent picks next delay after each run.

## Fixed interval (bash / PowerShell)

**Linux/VPS:**
```bash
while true; do
  sleep 300
  echo 'AGENT_LOOP_TICK_health {"prompt":"curl -s https://leadsgenai.in/health"}'
done
```

**Windows:** `while ($true) { Start-Sleep -Seconds 300; Write-Output 'AGENT_LOOP_TICK_...' }`

1. Unique sentinel per loop (`AGENT_LOOP_TICK_<purpose>`).
2. Run prompt **once immediately**, then wait for ticks.
3. Track PID; stop on user request.
4. Confirm: interval, first tick time, how to stop.

## Dynamic

1. Run now.
2. If gated on event (CI green, file change) → watch + sentinel on match.
3. Else one-shot `sleep N` + `AGENT_LOOP_WAKE_<purpose> {"prompt":"..."}`.
4. Re-arm after each wake.

## LeadGen examples

- `curl -s https://leadsgenai.in/health/ready`
- `python scripts/automation_health_audit.py --daily-check`
- `docker compose -f docker-compose.vps.yml ps app`

Never duplicate loops. Stop = kill PID + no re-arm.
