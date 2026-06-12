---
name: prod-incident-triage
description: leadsgenai.in down/unhealthy/freeze — health 000, workers stuck, CPU 0%, "automations broken" feel. 3 real prod-downs ka distilled runbook: detect → py-spy → recover → root-cause. systematic-debugging generic hai; yeh LIVE-INCIDENT specific.
---

# Prod Incident Triage (3 prod-downs se seekha)

## Pehle 2 minute (detect + recover)
1. `curl -s https://leadsgenai.in/health` aur VPS pe internal `curl -s 127.0.0.1:8000/health` — dono 000/timeout = app freeze; ext fail + int 200 = Caddy/DNS.
2. `docker ps` — unhealthy/restarting containers? `docker stats --no-stream` — CPU 0% + requests hang = **event-loop freeze** (classic).
3. **Stack pakdo PEHLE, restart BAAD me** (warna evidence गया): py-spy **HOST se** chalao (container me ptrace denied): `py-spy dump --pid $(pgrep -f uvicorn | head -1)`.
4. Recover: `docker compose -f docker-compose.vps.yml restart app` → `sleep 16` → 2x health-check. Selfheal cron (*/10) bhi yahi karta hai — agar woh loop me restart kar raha hai to healthcheck command khud galat ho sakta hai (scheduler pgrep lesson).

## Known freeze classes (pattern-match karo)
| Class | Signature | Fix pattern |
|---|---|---|
| Sync ML/KB on event-loop | WS/endpoint hit → dono workers stuck, CPU 0% | `asyncio.to_thread` + hard timeout (`_run_blocking` 15s, KB_EMBED_LOAD_TIMEOUT_S) |
| Model download at runtime | image rebuild ke baad first hit hang (~250MB HF) | model BAKE in Dockerfile.lock (model-asset-bake skill) + disable-switch |
| Boot-storm heavy job | deploy qa/trainer window me → boot pe job fire → HTTP starve | boot-grace (scheduler skip on boot) — Celery profile me non-issue |

**RULE: har ML asset = image-bake + off-loop load + deadline + disable-switch.**

## Job heartbeats green ≠ sab theek
Prod-down #3 me jobs sab green the par web freeze tha — user ka "automations broken" feel = HTTP path. Hamesha dono check karo: `/api/growth/infra/automation-health` AUR ext health/page curl.

## Baad me (post-incident, skip mat karo)
1. Root-cause commit + test/guard.
2. SESSION_LOG me incident entry + CLAUDE.md 1-2 line.
3. Agar naya freeze-class hai → is skill ki table me row add karo.
4. `/optimize` scan chalao (event-loop-blocking class catch karta hai).
