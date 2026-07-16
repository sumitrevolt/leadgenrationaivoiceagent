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

## Postiz env change / restart (⚠️ WRONG COMMAND = WHOLE PROD STACK DELETED)
🚨 **Read this before ANY `docker compose` on `docker-compose.postiz.yml`.** Both compose files live in `/opt/leadgen`, so Compose shares the implicit project name `leadgen` across them. On 2026-07-03 a `--remove-orphans` on the postiz file made Compose treat the ENTIRE main stack (app/db/redis/workers) as orphans and **STOP+DELETE it** (volumes survived; restart recovered). **NEVER pass `--remove-orphans` to the postiz compose file.** Plain `up -d` is safe.
1. SSH: `ssh -i ~/.ssh/id_rsa root@72.61.245.204`, `cd /opt/leadgen`.
2. Backup env first: `cp deploy/postiz/.env deploy/postiz/.env.bak_$(date +%Y%m%d-%H%M%S)` (the existing `.env.bak_*` files are prior manual edits — keep the convention).
3. Edit `deploy/postiz/.env` (this file is env-only, no app secrets — the app's own `.env` is a DIFFERENT file and stays untouched).
4. Apply — **exact command, no extra flags**:
   `docker compose -f docker-compose.postiz.yml --env-file deploy/postiz/.env up -d`
5. Verify BEFORE walking away: `docker ps --format '{{.Names}} {{.Status}}' | grep -E 'leadgen_(app|db|redis|worker|scheduler|postiz)'` — **confirm the MAIN stack is still up**, not just postiz. Then `curl -s -o /dev/null -w '%{http_code}' https://leadsgenai.in/health` = 200 and `https://postiz.leadsgenai.in/` = 307.
6. Env-name trap: compose passes `FACEBOOK_APP_ID`/`FACEBOOK_APP_SECRET` (NOT Postiz-docs' `FACEBOOK_ID`/`FACEBOOK_SECRET`). Checking the wrong name reports a false "unset" — verify against `docker-compose.postiz.yml`, not upstream docs.

**Close open registration:** `POSTIZ_DISABLE_REGISTRATION=true` in `deploy/postiz/.env`, then step 4–5. Lock-out-safe: existing operator account must already exist in Postiz DB. Verify: `https://postiz.leadsgenai.in/auth/register` should stop creating accounts; existing login still works.

**Reconnect YouTube (recurs every ~7 days until fixed properly):** the Google OAuth client is in **testing** mode → refresh tokens expire after 7 days. Postiz UI → the YouTube channel → reconnect. **Permanent fix** = Google Cloud Console → the `LeadsGenAI` project → OAuth consent screen → **Publish app** (production). Check state without guessing:
`docker exec leadgen_postiz_db psql -U postiz -d postiz -t -A -F' | ' -c 'select "providerIdentifier","refreshNeeded","tokenExpiration" from "Integration" where "deletedAt" is null;'`

## Postiz publish readiness — how to actually verify (do NOT trust one field)
`/api/growth/social/postiz/status` reports EFFECTIVE config + `integrations_source` (`client` / `social_config` / `env` / `vault` / `none`). **ADR-117:** global `POSTIZ_INTEGRATIONS` is own-brand/admin only — customers must have their own `postiz_integrations` (client dict or wizard `social_config`). Precedence: client → social_config → (own-brand only) env → vault. Ground truth (read-only, posts nothing):
```
docker exec leadgen_app python -c "from app.marketing import postiz_publish as pp; c={'id':'jiya-makeover'}; print(pp.integrations_source(c), pp.effective_integration_ids(c)); print('own', pp.integrations_source(), pp.effective_integration_ids())"
```
Empty list for a customer = no Postiz publish (honest). Also check `data/social_engine.json` `dry_run` — `true` fabricates `ok=True` (ADR-098). Hourly drain = staff job `social_drain` (:10 IST).

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

## platform_dial STAGED re-enable (2026-07-16 — user go-ahead mila; safeguards ADR-025/027 verified complete, tests 25/25)
3-layer kill abhi: `PLATFORM_DIAL_DAILY=0` (VPS .env — env explicit 0 = FINAL, file override nahi kar sakta) + `data/platform_dial.json enabled:false` + scheduler override paused. Safeguards jo pehle se built: dial_gate allowlist (fail-closed default ON) · in-call IVR-strike → call_feedback blocklist · call_qualifier bot-gate (qualified force-false on IVR-suspect/min-3-turns) · phone-type gate · learned prefix-block · `PLATFORM_DIAL_LIMIT` cap · place_call me gate (error = promotional block).
**Stage 1 (allowlist test):** USER apna mobile `data/dial_test_mode.json` `numbers` me daale (ya `DIAL_TEST_ALLOWLIST` env) → VPS .env `PLATFORM_DIAL_DAILY` unset/=1 (USER-only edit) → `data/platform_dial.json {"enabled":true,"limit":3}` → scheduler override un-pause. Test-mode ON hi rehta = batch SIRF allowlist numbers dial karega; user khud agent ki quality sune. `scripts/agent_tester.py` scorecard bhi le (§6 DoD).
**Stage 2 (real):** recordings/scorecard OK + USER final "go" → `data/dial_test_mode.json {"enabled":false}` → real prospects, saare gates (DND fail-closed 9am-7pm window, blocklist, phone-type, cap) active. Rollback kabhi bhi: `PLATFORM_DIAL_DAILY=0` (1 env var, instant).
NOTE: calling window code-conservative 9am–7pm; DLT approved hai (2026-07-14) — cold outbound legal-side clear.
