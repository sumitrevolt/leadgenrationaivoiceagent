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
3. **Commit + push** (Windows git `C:\PROGRA~1\Git\cmd\git.exe`). Push to main is SAFE (CI `DEPLOY_ENABLED` gated → gate-only, no auto-deploy). (2026-07-05) Push se pehle `git log origin/main..HEAD` — background-automation ke foreign commits inspect karo; `git add -A` KABHI nahi.
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

## Enterprise gate (risk-tier the ship before you ship)
Operating loop: Discover → Contract → Execute → Self-review → Evidence (`fable-operating-manual`). Tier the change FIRST — over-shipping a trivial change wastes a rebuild, under-gating a high-risk one = prod-down.

| Tier | Example change | Deploy gates that FIRE |
|------|---------------|------------------------|
| **Trivial** | doc/copy, single non-hot-path fn | `py_compile` + 1 targeted test + curl-verify if a page changed |
| **Standard** | new endpoint/UI tab, non-billing logic | `prod_check` + changed-file pytest + `duplicate-route-guard` grep + flag-gate + health-gate |
| **High-risk** | billing/pricing · public route · telephony/outbound · secrets/auth · worker/scheduler · DB migration | full Standard + `test_billing_truth_2026` (billing) / SSRF+auth (public) / `cross_path_audit` (telephony) + `security-review` + **named rollback pre-staged** |

**Named auto-rollback (decide BEFORE `up -d`):** health red → `git checkout HEAD~1 -- <reverted-files>` (or `git reset --hard <prev-SHA>`) + rebuild + recreate · scheduler-class regression → `.env` `RUN_IN_PROCESS_SCHEDULER=1`+`WEB_CONCURRENCY=1`, stop worker/scheduler, recreate app · last resort `down` + `systemctl start leadgen`. **Never leave prod red.**

**Evidence (done):** `scripts\prod_check.py` green + `pytest_run.log` read + 2× `/health`=`environment:production` + new route curl 200 + `docker ps` healthy. Worker/scheduler change → also `--profile celery` recreate + `redis-cli llen celery` (>500 → `del celery`). Secrets stay `.env`-only (`scripts\check_secrets.py`). Live-VPS deploy = explicit user-auth.
