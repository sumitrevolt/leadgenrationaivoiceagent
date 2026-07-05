---
name: leadgen-infra-doctor
description: Deployment infra diagnose + harden — Docker, Caddy, FastAPI, workers, scheduler, Redis, Postgres, PgBouncer, Qdrant, health endpoints, env-vars, container logs, memory, ports, TLS, restart. Use jab VPS local se alag behave kare ya code-bug vs config/resource/network/external-blocker separate karna ho.
---

# LeadGen Infra Doctor

> Enterprise audit skill. `hostinger-deploy`/`leadgen-ops` = deploy LOOP; **yeh = root-cause doctor** jab prod local se alag chale. Pehle `context-first`.

## Mission
Cloud/VPS deployment local se kyun alag — pata karo. Code-bug ko config/resource/networking/external-service blocker se separate karo.

## Repo truth (live infra)
- **VPS** `72.61.245.204` (Mumbai, Ubuntu 24.04, Docker). App `/opt/leadgen`.
- **App** = Docker container `leadgen_app` :8000 (`docker-compose.vps.yml`, restart:unless-stopped). systemd `leadgen` DISABLED (rollback only). **Caddy** host-proxy `127.0.0.1:8000` (Traefik conflict — dhyaan).
- **Data**: Postgres `leadgen_db` via **PgBouncer `pgbouncer:6432`** + Redis `leadgen_redis:6379`. SQLite = rollback-backup only. Qdrant `127.0.0.1:6333`.
- **Image** (`Dockerfile.lock`): code (`app/`+`frontend/`+`.claude/skills/`) BAKED → code change = `docker compose build app` + `up -d --no-deps app` recreate (data-only `./data`/`./logs` bind-mount change ko NAHI).
- **Containers (2026-07-05 verified)**: app · worker · worker_heavy · scheduler · redis · redis-cache · db · pgbouncer · qdrant · postiz · waha (+ obs agar deployed). Self-heal cron `scripts/vps_selfheal.sh` */10. fail2ban + unattended-upgrades.
- **Health**: `https://leadsgenai.in/health` → `environment:production` + 200 (sleep 16 boot-grace + 2x check).

## Workflow
1. Services inventory: Docker Compose, systemd, Caddy, env-files, health endpoints.
2. Har service ka purpose + dependency + restart-policy + volume-policy + health-check confirm.
3. Expected ports/routes vs actual exposed compare (`docker compose config --services` pehle — galat service-naam = poora `up` ABORT).
4. Logs inspect: import-error, stale code (`.pyc`), env-fail, DB-fail, worker-crash, memory-pressure.
5. Safe deploy commands + rollback steps.

## Enterprise checks
- Docker rebuild ACTUALLY latest code use kare (build pipe `| tail` exit-code maskta → `set -o pipefail`).
- App/worker/scheduler/Redis/Postgres/PgBouncer/Qdrant reachable.
- Health endpoint dependency detect kare, sirf process-liveness nahi.
- Env-var names code-expectation se match.
- TLS/reverse-proxy correct internal service pe point kare.
- Logs + persistent data intentionally mounted.

## Output
Infra health matrix · root-causes (log/config evidence) · deploy fix plan · rollback + verify commands · readiness /100.

## Related repo skills (duplicate mat banao)
`hostinger-deploy` (VPS gotchas) · `leadgen-ops` (verify→deploy loop) · `secure-linux-web-hosting` (hardening) · `observability-ops` (Prometheus/Loki infra) · `windows-dev-gotchas` (git/ssh) · `prod-incident-triage` (live incident).
