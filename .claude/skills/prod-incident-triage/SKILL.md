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
| Boot-storm heavy job | deploy qa/trainer window me → boot pe job fire → HTTP starve | (live = Celery durable, dedicated worker → HTTP starve non-issue. Rollback in-process path me boot-grace skip) |
| Stuck/backed-up Celery worker | "automations broken" but web OK; jobs not firing | `docker logs leadgen_worker` + flower :5555 (tunnel); `redis-cli llen celery` >500 = `del celery` (beat re-schedules); worker recreate |
| Office map blank (Simple→Pro) | /app/office Pro-switch pe canvas khali; JS console clean | RESOLVED 2026-07-05 (lazy Phaser boot — `OFFICE.bootGame`); regression dikhe to frontend/office_map.html me bootGame guard + `tests/test_office_map_frontend.py` dekho |

**RULE: har ML asset = image-bake + off-loop load + deadline + disable-switch.**

## Job heartbeats green ≠ sab theek
Prod-down #3 me jobs sab green the par web freeze tha — user ka "automations broken" feel = HTTP path. Hamesha dono check karo: `/api/growth/infra/automation-health` (admin) AUR ext health/page curl. Scheduler ab Celery durable hai → jobs ka asli source = `leadgen_scheduler` (beat) + `leadgen_worker` containers + flower :5555 + `dlq:failed_tasks`, sirf in-process heartbeat file nahi.

## Baad me (post-incident, skip mat karo)
1. Root-cause commit + test/guard.
2. SESSION_LOG me incident entry + CLAUDE.md 1-2 line.
3. Agar naya freeze-class hai → is skill ki table me row add karo.
4. `/optimize` scan chalao (event-loop-blocking class catch karta hai).

## Enterprise gate (live incident = always High-risk)
Operating loop: Discover → Contract → Execute → Self-review → Evidence (`fable-operating-manual`). Incident me ye **compressed**: Discover = detect+capture-stack, Execute = recover, Evidence = 2× health + post-incident commit. **Thesis = rollback/recover PEHLE, root-cause BAAD me — par root-cause zaroor pakdo (symptom-only fix = repeat-incident ban).**

- **Capture before recover:** restart se PEHLE py-spy **HOST se** (`py-spy dump --pid $(pgrep -f uvicorn | head -1)`, container me ptrace denied) — warna evidence gaya, root-cause impossible.
- **Recover (NAMED rollback ladder):** `docker compose -f docker-compose.vps.yml restart app` → scheduler-class regression → `.env` `RUN_IN_PROCESS_SCHEDULER=1`+`WEB_CONCURRENCY=1` + worker/scheduler stop → bad-image → `git reset --hard <prev-SHA>`+rebuild+recreate → last resort `down` + `systemctl start leadgen`.
- **Observability surfaces (check BOTH paths — heartbeats green ≠ web healthy):** ext `https://leadsgenai.in/health` + int `127.0.0.1:8000/health` · `docker ps`/`docker stats --no-stream` (CPU 0% + hang = event-loop freeze) · `docker logs leadgen_app`/`leadgen_worker` · `/api/growth/infra/automation-health` (admin) · flower :5555 · `redis-cli llen celery` (>500 → `del celery`) · `dlq:failed_tasks`.
- **Celery-flood guard:** repeated worker recreate → `self_improve_tick` self-requeue multiply; root-fixed (`acks_late=False` + `ensure_alive` Redis NX lock) but verify `llen celery` after any worker recreate.
- **Evidence (incident closed):** `sleep 16` + 2× `/health`=`environment:production` 200 + selfheal cron not loop-restarting + root-cause commit/test/guard landed. Mid-incident destructive ops (`del celery`, `down`, `reset --hard`) = `careful` skill discipline; no need to ask user during an active prod-down (recover-first).
