# Playbooks — repeatable procedures (deep versions live in `.claude/skills/`; yeh quick-reference hai)

## Deploy to VPS (skill: `hostinger-deploy`, `ship-checklist`; command `/ship`)
1. `.venv\Scripts\python.exe scripts\prod_check.py` → ALL PASS
2. `scripts\run_tests.bat` → **Read `pytest_run.log`** (full suite team_pulse pe hang ho sakta — targeted suites ok)
3. `scripts/check_secrets.py` clean
4. Windows git push (`C:\PROGRA~1\Git\cmd\git.exe`; sandbox git index unreadable)
5. SSH (Git ka ssh.exe, Windows OpenSSH broken): `cd /opt/leadgen && git pull` → `docker compose -f docker-compose.vps.yml build app` → `up -d --no-deps app`
6. Verify: `sleep 16` + 2× `curl /health` = `environment:production`. Naya `@app.get` page-route = HARD RELOAD (pycache purge / container recreate) warna stale-.pyc 404.
- ⚠️ VPS tree chronically dirty — SURGICAL deploy (`git checkout origin/main -- <files>` + `docker cp` hotfix jab flagged); KABHI `reset --hard`/blind rebuild. Build pipe `| tail` = `set -o pipefail`. Concurrent build check first. CI = gate-only (`DEPLOY_ENABLED` unset).

## Rollback ladder
- App code: previous image tag `up -d --no-deps app`.
- Scheduler: `.env RUN_IN_PROCESS_SCHEDULER=1` + `WEB_CONCURRENCY=1`, stop worker/scheduler containers, recreate app.
- Whole stack: `docker compose -f docker-compose.vps.yml down` → `systemctl start leadgen` (SQLite systemd service installed as rollback).
- Worker recreate ke baad: `redis-cli llen celery`; >500 = `del celery` (beat re-schedules).

## New marketing feature (skill: `marketing-feature`)
Module in `app/marketing/` → router (PEHLE duplicate-route grep across ALL split routers) → frontend tab SAATH me (API-only = adhoora) → flag-gated INERT default → targeted test → prod_check → smoke on VPS.

## New client onboarding (skill: `niche-onboarding`, `fde-onboard`)
`clients_store.py` entry → niche + lead_band → KB seed (website → `AUTO_ONBOARD=1` auto-path; manual seed via admin, KB-seed-via-exec IMPOSSIBLE — use API) → mini-site `/b/{slug}` → month-plan + first content pack (Day-1 queue auto) → booking slots per-client → customer login + dashboard fork check (Marketing/Voice/Combo — confirm WHICH before editing).

## Voice change QA (skills: `voice-humanization`, `web-call-triage`)
Tune on FREE web-call (`/app/test-call`) → `scripts/agent_tester.py` scorecard (double/empty/repeat/long/slow) → guards mirrored in BOTH `reply()` + `reply_stream_sentences()` → phone = final verify only (paisa). Bounded awaits everywhere.

## Enable a gated automation flag (skill: `automation-flags`)
Check `GET /api/growth/infra/flags` → read flag's ban/cost risk → enable in `.env` → app recreate → verify emit/log → monitor 24h → naya flag banaya to `AUTOMATION_FLAGS` registry me add.

## WAHA secret rotation (P0 security — `scripts/activate_waha_vps.sh` had hardcoded values until 2026-07-14)
1. **Rotate on the WAHA container:** generate two new strong random values for `WAHA_API_KEY` and `WAHA_WEBHOOK_TOKEN` (e.g. `openssl rand -base64 32`).
2. SSH to VPS (`ssh -i ~/.ssh/id_rsa root@72.61.245.204`), `cd /opt/leadgen`.
3. Export the new values in the SSH session only (never paste into a committed file): `export WAHA_API_KEY=... WAHA_WEBHOOK_TOKEN=... WHATSAPP_BUSINESS_NUMBER=91XXXXXXXXXX`.
4. Run `./scripts/activate_waha_vps.sh` — it now requires these env vars (fails loudly if unset) and rewrites the `.env` WAHA block idempotently, then restarts `waha` + `app`.
5. Verify: `/health`=`environment:production`, `docker logs --tail=5 leadgen_waha` shows the container came up clean, `curl -s -H "X-Api-Key: $WAHA_API_KEY" http://127.0.0.1:3111/api/sessions/default` returns a session status (not 401).
6. Re-link WhatsApp if the session drops after rotation: `https://leadsgenai.in/app/whatsapp` → Self-host card → Start session → scan QR (phone: WhatsApp → Linked Devices → Link a Device).
7. Treat the OLD key/token (committed in git history before 2026-07-14) as permanently burned — rotation (not history rewrite) is the fix; do not reuse those values anywhere.

## Prod incident (skill: `prod-incident-triage`)
Health 000/502 → `docker ps` + logs → py-spy dump on stuck proc → recover (targeted restart, NOT blind) → root-cause → postmortem entry in `memory/incidents.md` + prevention rule. Self-heal cron `scripts/vps_selfheal.sh` */10 already running.

## Backups & restore (proven 2026-07-02)
Host crons: 02:30 pg_dump → Drive; 02:45 data tar (excludes ollama/u2net/backups) → Drive; email-backup cron offsite. Restore drill: pull dump → restore to scratch DB → row-counts match → FK validate. Token rotate: Google Drive → Security → third-party access.

## Gemini voice-key add/rotate
Admin "Voice Keys" page (ya `POST /api/admin/voice/gemini-keys`) → per-key Google-validate → no restart needed. Pool auto-advances on 429.

## Monthly memory pruning (INDEX rule 4)
CLAUDE.md `## Current State` > 40 lines? → stale items ko `decisions.md` me move ya delete. Stale gotcha jo ab code me fixed = incidents entry me archive. AGENTS.md byte-copy re-sync (`Copy-Item CLAUDE.md AGENTS.md`).

## Adding a scheduler job (skill: `scheduler-job`, `teach-agent-loop`)
6-layer wiring (job fn + team_scheduler slot + worker task + heartbeat + admin toggle + test) → boot-grace for heavy jobs → parity guarded by prod_check automation-gaps.
