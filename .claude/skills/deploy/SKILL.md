---
name: deploy
description: Deploy or update the LeadGen AI platform to production (Hostinger VPS, Docker, leadsgenai.in) and wire env vars/keys. Use when the user says "deploy", "go live", "push to production", "update the server", or "set up hosting". NOTE - Railway/Render are NOT used; this is Hostinger VPS Docker only.
---

# Deploy LeadGen AI (Hostinger VPS · Docker)

App = FastAPI (`Dockerfile.lock`), LIVE at **https://leadsgenai.in** on a single Hostinger KVM VPS (Mumbai, **72.61.245.204**, Ubuntu 24.04, Docker). NO Railway, NO Render, NO PaaS — woh purana plan tha (`railway.json`/`render.yaml`/`Procfile` ab repo me NAHI). Yeh skill = high-level orientation; step-by-step gotchas ke liye sibling skills padho.

## Stack on the box
- App container `leadgen_app` :8000 (host Caddy → 127.0.0.1:8000, auto-HTTPS). `docker-compose.vps.yml` = canonical stack.
- DB = Postgres (`leadgen_db`) via PgBouncer (`pgbouncer:6432`); Redis (`leadgen_redis`); Qdrant. SQLite = rollback-backup only.
- **Scheduler = Celery durable (PRIMARY/LIVE)**: `leadgen_worker` + `leadgen_scheduler` (beat) containers (`--profile celery`), `.env` me `RUN_IN_PROCESS_SCHEDULER=0` + `WEB_CONCURRENCY=2`. In-process APScheduler = ROLLBACK only.
- `app/` + `frontend/` + `.claude/skills/` Docker image me BAKED → code/skill change = rebuild. `./data` + `./logs` = bind-mounts (no rebuild).
- systemd `leadgen` service = DISABLED (rollback path only).

## Deploy loop (the real flow)
1. **Windows = source of truth** (sandbox mount stale ho jata hai). `python scripts/prod_check.py` → TARGETED pytest (`.venv\Scripts\python -m pytest tests\test_<area>.py -q` — full run_tests.bat offline HANG hota hai; 2026-07-05).
2. Windows git push: `C:\PROGRA~1\Git\cmd\git.exe` (ek `.bat` ke andar).
3. VPS pe pull + rebuild (Git ka ssh — Windows OpenSSH broken):
   ```
   C:\PROGRA~1\Git\usr\bin\ssh.exe -i C:\Users\Ratanshila\.ssh\id_rsa root@72.61.245.204 \
     "cd /opt/leadgen && git fetch --all -q && git reset --hard origin/main -q && \
      docker compose -f docker-compose.vps.yml build app && \
      docker compose -f docker-compose.vps.yml up -d --no-deps app"
   ```
4. Verify: `https://leadsgenai.in/health` → `environment:production`. `sleep 16` + 2x health-check rakho.
- **Naya `@app.get` page-route**: fresh image me baked, par hard reload + curl-verify zaroor (stale-pyc 404 lesson).

## Detailed sibling skills (READ these — yahan duplicate nahi karta)
- `hostinger-deploy` — VPS gotchas (Caddy-vs-Traefik, .env inline comments, firewalled :8000, ssh quoting).
- `leadgen-ops` — proven verify→test→push→deploy loop + production triage table.
- `ship-checklist` — health-gate + rollback discipline per deploy.
- `observability-ops` — Prometheus/Grafana/Alertmanager + flower/celery-exporter addons.

## Before first paid customer
- **Payments**: Razorpay gateway HATA diya gaya (purana 401-blocker RESOLVED). Payments ab manual UPI (`UPI_VPA` set karo) / Stripe. Koi `rzp_*` key zaroorat nahi.
- Telephony: Vobiz DID + recharge + DLT/TRAI (cold-calling ke liye; inbound callback ko nahi chahiye). `VOBIZ_CALLER_ID` set.
- NEVER commit `.env` (gitignored). Full legacy guide: `docs/legacy/DEPLOY_GUIDE.md` (mostly historical).

## Enterprise gate (orientation only — gates live in siblings)
- **Operating loop:** Discover → Contract → Execute → Self-review → Evidence (`fable-operating-manual`).
- **Change-risk tier:** any live-VPS deploy = **High-risk** (locks rebuild+recreate, hard-reload for new page-routes, named rollback, 2× health-gate). Secrets `.env`-only.
- **Rollback (NAMED):** `git reset --hard <prev-SHA>`+rebuild → scheduler-class `RUN_IN_PROCESS_SCHEDULER=1`+`WEB_CONCURRENCY=1` → last-resort `systemctl start leadgen`.
- **Evidence:** `https://leadsgenai.in/health`=`environment:production` (2×) + new route curl 200.
- Full gate table / triage / health-discipline = `ship-checklist` + `leadgen-ops` + `prod-incident-triage` (yahan duplicate nahi karta). Live-VPS deploy = explicit user-auth.
