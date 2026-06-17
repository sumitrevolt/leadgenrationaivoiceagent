---
name: ship-checklist
description: Pre-deploy + deploy + verify checklist for the LeadGen AI live VPS (Docker, leadsgenai.in). Use when shipping ANY change to production — encodes this project's real deploy gotchas (Windows=truth, stale-pyc hard-reload, health-gate + auto-rollback, base64-over-ssh). Triggers - "deploy", "ship", "push to prod", "go live", after a code change that needs to reach the server.
---

# Shipping & Launch (LeadGen AI live VPS)

Faster-is-safer, but verified. This live revenue site (leadsgenai.in) has real leads + payments flowing — every deploy is health-gated + rollback-ready.

## When to Use
Any change that must reach the production VPS (72.61.245.204, `/opt/leadgen`, Docker stack).

## Process

1. **Windows = source of truth.** Sandbox mount goes STALE after file edits. Verify with `.venv\Scripts\python.exe` on Windows (Desktop Commander), not the Linux mount.
2. **Pre-flight (Windows):** `python -m py_compile <changed.py>` → `python -c "import app.main"` (IMPORT_OK) → `python scripts/prod_check.py` (ALL CHECKS PASSED, note route count) → `pytest tests/test_*.py -q` (green). Don't ship red.
3. **Commit + push** (Windows git `C:\PROGRA~1\Git\cmd\git.exe`). Push to main is SAFE (CI `DEPLOY_ENABLED` gated → gate-only, no auto-deploy).
4. **Deploy to VPS** (Git's ssh `C:\PROGRA~1\Git\usr\bin\ssh.exe`, PowerShell for clean quoting): `cd /opt/leadgen && git fetch && git merge --ff-only origin/main && docker compose -f docker-compose.vps.yml build app && docker compose -f docker-compose.vps.yml up -d --no-deps app`. (`--no-deps` = sirf app recreate; db/redis/worker/scheduler chhede bina.)
5. **HEALTH GATE + ROLLBACK.** After up: `sleep 14; curl -fsS /health/ready`. If unhealthy → `git checkout HEAD~1 -- docker-compose.vps.yml` (or revert) + recreate. Never leave prod red.
6. **New page-routes (`@app.get`) = code is baked in the Docker image** → rebuild (`build app`) picks them up (no stale-pyc in fresh image). The old systemd stale-`.pyc` gotcha is moot under Docker, but ALWAYS verify the new route serves (curl it).
7. **SSH quoting:** `&`/`<`/`{{}}`/`%{}` break over PS→ssh. For any non-trivial remote command, base64-encode and `echo <b64> | base64 -d | bash` (or `| docker exec -i leadgen_app python -`).
8. **Verify live:** `/health` (environment=production, fresh uptime), the specific new route (200 + real content), and `docker ps | grep leadgen` (healthy).
9. **Worker/scheduler code changed?** App ke saath worker bhi same image use karta — recreate karo: `docker compose -f docker-compose.vps.yml --profile celery up -d --no-deps worker scheduler`. Phir `redis-cli llen celery` (>500 = `del celery`; beat re-schedules). Scheduler = Celery durable PRIMARY; APScheduler sirf rollback.

## Red Flags
- Shipping with red prod_check/tests. · Editing on the Linux mount and trusting it (stale). · `up -d` without a health check after. · New route not curl-verified post-deploy. · Complex SSH command with unescaped `&&`/braces.

## Verification
- `/health/ready` = healthy (db+redis) post-deploy. New route curl → 200. Container Up (healthy). If anything fails, rollback executed + re-verified.
