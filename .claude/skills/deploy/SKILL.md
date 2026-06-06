---
name: deploy
description: Deploy or update the LeadGen AI platform to production (Railway, Render, or a VPS), and wire env vars/keys. Use when the user says "deploy", "go live", "push to production", "update the server", or "set up hosting".
---

# Deploy LeadGen AI

The app is a FastAPI service (Dockerfile ready) needing Postgres + Redis + a Celery worker + websockets (always-on). Configs exist: railway.json, render.yaml, Procfile, docker-compose.prod.yml.

## Railway (recommended, easiest)
1. Push code to GitHub (commit + `git push origin main`).
2. railway.app -> New Project -> Deploy from GitHub repo -> select this repo (railway.json + Dockerfile auto-detected).
3. + New -> PostgreSQL, and + New -> Redis.
4. Web service Variables: APP_ENV=production, DEBUG=false, DATABASE_URL=${{Postgres.DATABASE_URL}}, REDIS_URL=${{Redis.REDIS_URL}}, SECRET_KEY=<random>, GEMINI_API_KEY=<key>, DEFAULT_LLM=gemini-2.5-flash, LLM_PROVIDER=gemini, TIMEZONE=Asia/Kolkata.
5. Add a worker service (same repo) with start command: `celery -A app.worker worker --loglevel=info --concurrency=2`.
6. Generate Domain. Test /health, /app/customer, /app/admin, /app/test-call.

## Render
Use the included render.yaml blueprint (web + worker + Postgres + Redis). Add GEMINI_API_KEY in dashboard (sync:false secrets).

## VPS (Hetzner/DigitalOcean) — when self-hosting SIP
`docker compose -f docker-compose.prod.yml up -d`, then Caddy/Nginx for HTTPS + domain.

## Before live
Telephony (Exotel/Plivo SIP) keys + DLT/TRAI registration + Sentry DSN. Webhook URL = `https://<domain>/telephony/twilio/media-stream`. NEVER commit .env (it is gitignored). Full details: DEPLOY_GUIDE.md.
