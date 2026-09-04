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

## DeepSeek Harness rollout, rollback drill, and retirement (ADR-181/182/183)
**Current posture (2026-08-16, prod `090af9e6`):** **DIRECT-RUNTIME AUTHORITY, DSH NOT ARMED.** `DSH_RUNTIME_ENABLED=0`, `DSH_SHADOW_ENABLED=0`; allowlist contains the 29 migratable identities for governed future promotion only (never `*`). Swara/Ananya remain frozen RED/hard-off. Legacy/direct executor remains the sole operational execution authority until separate owner promotion, shadow/soak evidence, rollback drill, and retirement gates are explicitly satisfied. Rollback remains `DSH_RUNTIME_ENABLED=0`.

**Redis / cancellation posture (VERIFIED 2026-08-16):** production runtime reports Redis-backed cancellation/idempotency healthy with fallback inactive and runtime DLQ count 0. This does **not** arm DSH execution; it only means the shared cancellation/idempotency substrate is healthy. If DNS ever fails inside a future `dsh-worker`, re-attach with alias: `docker network disconnect leadgen_dsh_net leadgen_redis; docker network connect --alias redis leadgen_dsh_net leadgen_redis`.

**Evidence-gated wave order (ADR-182, still the preferred path for future promotions):** shadow → Kavya read-only → Isha draft → GREEN read-only → GREEN internal mutators → Zara approved-social handoff → AMBER final-approval-gated. Shadow needs 120 golden cases + 2,000 turns / 14 days. Har next wave ke liye prior evidence retained, role-specific mutation/refusal tests green, tenant/compliance/billing/approval gates intact, queue/retry/DLQ/audit healthy, rollback drill green, aur explicit owner promotion approval mandatory hai. Time/test pass se auto-promotion nahi.

**One-flag runtime rollback drill (owner-authorized production game-day):**
1. Before state capture: exact running `APP_VERSION`, direct cache-busted `/health`, DSH runtime status, queue/DLQ depth, active allowlist/wave names only, and a known direct-executor control case. Secret/config values print mat karo.
2. Set only `DSH_RUNTIME_ENABLED=0` through the approved env-change path and recreate the affected app-image services with the same exact `APP_VERSION`; if shadow itself is faulty, set `DSH_SHADOW_ENABLED=0` too.
3. Prove `provider_for()`/runtime status selects `direct` for allowlisted agents, compliance/approval refusals remain fail-closed, and queues/DLQs do not regress.
4. Probe `/health` twice with cache-busters; require expected SHA, `environment:production`, advancing timestamp/uptime, and zero app-image skew. Record timestamps, run ids, exit codes, and evidence paths.
5. Re-arm only with fresh owner decision (ADR-183 already re-armed after the 2026-08-14 drill).

**Exact-image rollback drill:** Use the last known-good immutable `APP_VERSION` only through `scripts/deploy_vps.sh`; never hand-write compose rollback and never use `:latest`. The script must prove deployed SHA parity, migrations/readiness, service skew, and smoke; then repeat direct `/health` probes. A failed drill blocks the next wave.

**Legacy retirement checklist — every box required before deletion:**
- [ ] Final owner-authorized target wave has 30 consecutive green production days; any rollback or material incident resets the clock.
- [ ] Recorded game-day proves `DSH_RUNTIME_ENABLED=0` returns traffic to direct executor while legacy exists.
- [ ] Recorded exact-`APP_VERSION` game-day proves `scripts/deploy_vps.sh` can restore the legacy-capable image.
- [ ] Full static + dynamic caller/import/route/task/scheduler scan for `agent_runtime`, existing harness, and direct executor is reviewed; no orphan or hidden function-level import remains.
- [ ] Targeted suites, runtime/workforce parity, approval/compliance/tenant tests, `prod_check.py`, and secrets scan are green with exit codes.
- [ ] Direct cache-busted `/health` proves expected production SHA/environment; app-image skew, queues, DLQs, audit continuity, and rollback evidence are healthy.
- [ ] Deletion diff preserves Celery, Python domain engines, `agent_registry`, Owner OS, tenant/compliance/billing controls, and excludes all voice/Swara/Ananya paths.
- [ ] Owner separately authorizes legacy deletion after reviewing evidence and diff; deploy approval or canary approval does not imply deletion approval.
- [ ] Post-deletion rollback remains exact-image rollback until a replacement one-flag mechanism is production-proven.

## New marketing feature (skill: `marketing-feature`)
Module in `app/marketing/` → router (PEHLE duplicate-route grep across ALL split routers) → frontend tab SAATH me (API-only = adhoora) → flag-gated INERT default → targeted test → prod_check → smoke on VPS.

## New client onboarding (skill: `niche-onboarding`, `fde-onboard`)
`clients_store.py` entry → niche + lead_band → KB seed (website → `AUTO_ONBOARD=1` auto-path; manual seed via admin, KB-seed-via-exec IMPOSSIBLE — use API) → mini-site `/b/{slug}` → month-plan + first content pack (Day-1 queue auto) → booking slots per-client → customer login + dashboard fork check (Marketing/Voice/Combo — confirm WHICH before editing).

## Voice change QA (skills: `voice-humanization`, `web-call-triage`)
Tune on FREE web-call (`/app/test-call`) → `scripts/agent_tester.py` scorecard (double/empty/repeat/long/slow) → guards mirrored in BOTH `reply()` + `reply_stream_sentences()` → phone = final verify only (paisa). Bounded awaits everywhere.

## Enable a gated automation flag (skill: `automation-flags`)
Check `GET /api/growth/infra/flags` → read flag's ban/cost risk → enable in `.env` → app recreate → verify emit/log → monitor 24h → naya flag banaya to `AUTOMATION_FLAGS` registry me add.

## Onboarding wizard auto-setup arm (`ONBOARD_WIZARD_APPLY=1`) — deploy ke baad walkthrough
Wizard feature (business-type → niche template → auto-setup: salon/clinic/restaurant) is INERT until armed. **Catalog + preview endpoints hamesha live hain** (read-only, admin-auth); sirf `POST /api/onboard-wizard/apply` flag-gated hai. Arm ke baad verify kar lena ki apply ACTUALLY client pe niche snapshot + knowledge seed lagata hai.

**1. Check current state (pehle):**
```bash
# VPS pe (Git ssh): flag abhi kya hai + flag manifest registry me hai
ssh -i ~/.ssh/id_rsa root@72.61.245.204 "grep -c ONBOARD_WIZARD_APPLY /opt/leadgen/.env; curl -s http://127.0.0.1:8000/api/growth/infra/flags | grep -o 'ONBOARD_WIZARD_APPLY[^,]*'"
```
Expect: `.env` me 0 matches (unset = INERT, correct default) + flag registry entry listed (manifest me `SAFE_LOCAL_ONLY` — product risk, koi outbound/cost risk nahi).

**2. Arm (deploy ke saath ya baad, sirf jab wizard UI prod me use karni ho):**
```bash
# /opt/leadgen/.env me (NO inline comments — pydantic ValidationError trap):
#   ONBOARD_WIZARD_APPLY=1
docker compose -f docker-compose.vps.yml up -d --no-deps app
sleep 16 && curl -s http://127.0.0.1:8000/health | grep environment:production
```

**3. Verify apply (dummy client pe — real client PEHLE nahi):**
```bash
# Admin token se: dummy client banao + wizard apply chalao
curl -s -X POST http://127.0.0.1:8000/api/admin/customers/onboard \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"business_name":"Arm Test Salon","niche":"salon_spa","phone":"9999999901","product":"marketing"}'
curl -s -X POST http://127.0.0.1:8000/api/onboard-wizard/apply \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"client_id":"<id>","business_type":"salon"}'
```
Expect: `{"ok": true, "applied": ["niche_snapshot", "knowledge_seed"], ...}`. Snapshot warning aaye (niche NICHES-catalog me nahi, e.g. salon_spa) to bhi OK — knowledge_seed hi main value hai; NICHES-cover niches (restaurant_cafe, hospital_appointments, dental_implants…) pe dono apply honge.
Flag UNARMED hai to apply `423` deta hai (`ONBOARD_WIZARD_APPLY disabled…`) — yahi quick armed-status signal hai; catalog/preview (`GET /api/onboard-wizard/business-types`, `/preview/{type}`) flag ke BINA bhi 200 dete hain (read-only hamesha live).

**4. Smoke UI:** `/app/onboard` → Step 1 → "Business type" dropdown → salon select → niche auto-fill + preview checklist dikhna chahiye → client banao → auto-setup call best-effort.

**5. Rollback (kabhi bhi):** `.env` se line hatana (`sed -i '/ONBOARD_WIZARD_APPLY/d' /opt/leadgen/.env`) + app recreate. Catalog/preview unaffected (read-only hamesha live). Naya client onboard wizard use kare to flag ON reh sakta hai — yeh SAFE_LOCAL_ONLY product feature hai, customer-messaging/cost kuch nahi.

## Post-call AI summary arm (`POST_CALL_SUMMARY=1`) — deploy ke baad walkthrough
AI post-call summary (qualified call ke baad lead ke WhatsApp pe summary + action items) is INERT until armed. **Yeh OUTBOUND customer-messaging hai — `WHATSAPP_AUTO_SEND` ke bina kabhi live nahi hota** (fail-closed). Chaar flags chahiye — koi ek bhi missing ho to summary silently skip ho jaata hai (sab gates: `POST_CALL_SUMMARY` → `AUTO_QUALIFY_CALLS` → WhatsApp sender `WHATSAPP_AUTO_SEND` → allowlist → opt-out ledger).

**Quick post-deploy check (script):** `python scripts/verify_armed_flags.py [--env /opt/leadgen/.env] [--url https://leadsgenai.in --token <admin> --apply-client-id <id>]` — manifest registry + .env flags + endpoint 423/200 signals ek-shot me. Exit 0 = sab armed/INERT sahi · 1 = problem (missing gate, broken endpoint) · 2 = warning (INERT default ya apply probe skip).

**Prerequisites (check pehle):**
```bash
# VPS pe (Git ssh): saare 4 flags + manifest entry + WA backend
ssh -i ~/.ssh/id_rsa root@72.61.245.204 "grep -E 'POST_CALL_SUMMARY|AUTO_QUALIFY_CALLS|WHATSAPP_AUTO_SEND|WHATSAPP_SEND_ALLOWLIST' /opt/leadgen/.env; curl -s http://127.0.0.1:8000/api/growth/infra/flags | grep -o 'POST_CALL_SUMMARY[^,]*'"
```
Expect: flag registry me `POST_CALL_SUMMARY` listed (`OWNER_APPROVAL_REQUIRED`, risk=outbound, companion=`WHATSAPP_AUTO_SEND`). WhatsApp backend armed hona chahiye: `curl -s -H "X-Api-Key: $WAHA_API_KEY" http://127.0.0.1:3111/api/sessions/default` session active (WAHA) ya Cloud API creds set (`.env` me `WHATSAPP_BUSINESS_TOKEN`+`WHATSAPP_PHONE_NUMBER_ID`).

**Arm (saare 4 flags ek saath, NO inline comments):**
```bash
# /opt/leadgen/.env me:
#   POST_CALL_SUMMARY=1
#   AUTO_QUALIFY_CALLS=1          # post-call qualification flow (summary iske andar wire hai)
#   WHATSAPP_AUTO_SEND=1          # sender-boundary gate (fail-closed, §5)
#   WHATSAPP_SEND_ALLOWLIST=+919999999999   # canary: pehle sirf test number; '*' = sabko
#   ONBOARD_WIZARD_APPLY=1        # (optional) wizard auto-setup bhi chahiye to
#   POST_CALL_WHATSAPP=1          # (optional) existing trial-link message bhi
#   VOICE_CLOSE_WHATSAPP=0        # close-signal WA apna flag — alag opt-in
#   AUTO_QUALIFY_CALLS ke liye note: AUTO_QUALIFY_CALLS=1 se har call qualify hoti hai
#   (billing/CRM/RL spine bhi on ho jaata hai — POST_CALL_SUMMARY sirf usi ke saath
#   chal sakta hai, standalone nahi)
docker compose -f docker-compose.vps.yml up -d --no-deps app
sleep 16 && curl -s http://127.0.0.1:8000/health | grep environment:production
```

**Verify (canary number pe pehle — real lead PEHLE nahi):**
1. Test call karo allowlisted number pe (web `/app/test-call` ya manual dial) — call qualified honi chahiye (lead ne interest dikhaya).
2. WhatsApp pe wahi number check karo — summary message aana chahiye: 📞 Call Summary → interest score, budget, duration, AI summary, action items.
3. Logs: `docker logs leadgen_app -n 200 | grep -i 'call_summary'` — `AI summary sent to` line = send hua; `blocked`/`DENY` = gate ne roka (allowlist ya auto_send check karo).
4. Non-qualified call pe summary NAHI aana chahiye (sirf `qualified:true` wale calls pe send hota hai).

**Rollback (kabhi bhi):** `.env` me `POST_CALL_SUMMARY=0` ya line hatana + app recreate. Instant stop — send path flag check karta hai. Emergency override: `WHATSAPP_AUTO_SEND=0` (global WA kill — sab WhatsApp sends band, summary included).

**Safety:** summary sirf QUALIFIED leads pe jaata hai (not-interested/IVR-suspect calls skip), opt-out ledger fail-closed hai (opted-out number kabhi send nahi), aur WhatsApp `4096` char limit ke liye message truncate hota hai. Billing/cost: summary LLM call free-ai chain use karta hai (no paid provider), WhatsApp send existing channel pe — naya cost surface nahi.

## Wizard opening → auto-callback greeting smoke (`opening_line` chain) — post-deploy
Chain: `/audit` `/site-audit` `/demo` inquiry me visitor ka **business type + business_name** → `run_after_inquiry` → `_wizard_opening_for(rec)` wizard ka personalized `suggested_opening` resolve (`"Namaste, main Swara bol rahi hoon <Business> ki taraf se…"`) → `_auto_callback(opening_line=…)` → `start_stream_call` → Redis pending `vobiz:pending:<token>` me `opening_line` store + `answer-stream` URL qs me threading → WS `/stream/{token}?opening_line=…` → `VobizStreamSession(opening_line=…)` → greeting. Ye smoke is poore chain ko deploy ke baad prove karta hai (unit-level proof + live probe). **Resolve fail ho to `""` — call generic niche-script chain pe girta hai (unchanged, safe default).**

**1. Code-level proof (deploy ke saath, zero cost — chain mechanics):**
```bash
# local ya CI — deployed commit pe; 8 tests: label resolve, niche-key resolve, unknown→"",
# qs threading, pending store, auto_callback passthrough, session override + compliance wrap, default None
python -m pytest tests/test_auto_callback_opening.py -q
```
Expect: 8 passed. Yeh `VobizStreamSession` override (greeting) + `ensure_ai_disclosure`/`ensure_permission_ask` wrap mechanically prove karta hai — prod pe bina call lagaye.

**2. Live probe (canary number pe — ASLI Vobiz call place hoga, credit lagta hai):**
```bash
# VPS pe — disposable test inquiry: business_type + niche + business_name (teeno chahiye, warna resolve "")
curl -s -X POST http://127.0.0.1:8000/api/public/inquiry \
  -H "Content-Type: application/json" \
  -d '{"name":"Smoke Test","phone":"+919999999902","business_name":"Arm Smoke Salon","business_type":"Salon / Beauty Parlour","niche":"salon_spa","source":"smoke"}'
```
Expect: `ok: true`. Ab 2-3s rukke pending store check karo (race — Vobiz call start hone se pehle pakdo):
```bash
TOKEN=$(docker exec leadgen_redis redis-cli --scan --pattern 'vobiz:pending:*' | head -1 | sed 's|vobiz:pending:||')
if [ -z "$TOKEN" ]; then echo "pending missing — call shayad already start ho gaya (pop). Retry: naya inquiry POST karke turant scan karo."; else
  docker exec leadgen_redis redis-cli GET "vobiz:pending:$TOKEN"
  curl -s "http://127.0.0.1:8000/api/telephony/vobiz/answer-stream/$TOKEN" | grep -o 'opening_line=[^&]*'
fi
```
Expect (dono): `opening_line` me **`Arm Smoke Salon` naam ka personalized wizard opening** (wizard path PROVEN — generic path me opening_line `null`/absent hota aur opening `[Company]` placeholder/`LeadGen AI` kehta). Answer-stream XML me bhi `opening_line=` qs milega — **yehi wo value hai jo WS session constructor ko milegi** (session override reach proof, bina call answer kiye).

**3. Live greet (optional — call uthao, full loop):** canary number pe call answer karo → greeting me "Arm Smoke Salon" sunai dega (personalized), generic "LeadGen AI" nahi. `docker logs leadgen_app --since 10m | grep -iE 'auto_callback|start_stream_call'` — fail ho to error line, success pe `log_event('swara','auto_callback',…)` team events me jaata hai.

**4. Negative check (resolve-fail path):** bina `business_type`/`business_name` wala inquiry POST karo → pending me `opening_line: null` → call niche-script generic opening se greet karta hai (sabhi kuch toota nahi, fallback intact).

**5. Rollback / skip:** yeh chain INERT-additive hai — koi flag nahi. Agar prod pe koi step fail ho to `AUTO_CALLBACK_INQUIRY=0` (`.env`) = inquiry auto-callback band (purana manual follow-up path); opening_line logic remove kiye bina bhi default `""` flow hi hai. DND/disclosure gates call path me fail-closed hain — smoke opening bhi `ensure_ai_disclosure` + `ensure_permission_ask` se wrapped hai (step 1 test assert).

## WAHA secret rotation (P0 security — `scripts/activate_waha_vps.sh` had hardcoded values until 2026-07-14)
1. **Rotate on the WAHA container:** generate two new strong random values for `WAHA_API_KEY` and `WAHA_WEBHOOK_TOKEN` (e.g. `openssl rand -base64 32`).
2. SSH to VPS (`ssh -i ~/.ssh/id_rsa root@72.61.245.204`), `cd /opt/leadgen`.
3. Export the new values in the SSH session only (never paste into a committed file): `export WAHA_API_KEY=... WAHA_WEBHOOK_TOKEN=... WHATSAPP_BUSINESS_NUMBER=91XXXXXXXXXX`.
4. Run `./scripts/activate_waha_vps.sh` — it now requires these env vars (fails loudly if unset) and rewrites the `.env` WAHA block idempotently, then restarts `waha` + `app`.
5. Verify: `/health`=`environment:production`, `docker logs --tail=5 leadgen_waha` shows the container came up clean, `curl -s -H "X-Api-Key: $WAHA_API_KEY" http://127.0.0.1:3111/api/sessions/default` returns a session status (not 401).
6. Re-link WhatsApp if the session drops after rotation: `https://leadsgenai.in/app/whatsapp` → Self-host card → Start session → scan QR (phone: WhatsApp → Linked Devices → Link a Device).
7. Treat the OLD key/token (committed in git history before 2026-07-14) as permanently burned — rotation (not history rewrite) is the fix; do not reuse those values anywhere.

## Postiz env change / restart (⚠️ WRONG COMMAND = WHOLE PROD STACK DELETED)
🚨 **Read this before ANY `docker compose` on `deploy/compose/docker-compose.postiz.yml`.** Both compose files live in `/opt/leadgen`, so Compose shares the implicit project name `leadgen` across them. On 2026-07-03 a `--remove-orphans` on the postiz file made Compose treat the ENTIRE main stack (app/db/redis/workers) as orphans and **STOP+DELETE it** (volumes survived; restart recovered). **NEVER pass `--remove-orphans` to the postiz compose file.** Plain `up -d` is safe.
1. SSH: `ssh -i ~/.ssh/id_rsa root@72.61.245.204`, `cd /opt/leadgen`.
2. Backup env first: `cp deploy/postiz/.env deploy/postiz/.env.bak_$(date +%Y%m%d-%H%M%S)` (the existing `.env.bak_*` files are prior manual edits — keep the convention).
3. Edit `deploy/postiz/.env` (this file is env-only, no app secrets — the app's own `.env` is a DIFFERENT file and stays untouched).
4. Apply — **exact command, no extra flags**:
   `docker compose -f deploy/compose/docker-compose.postiz.yml --env-file deploy/postiz/.env up -d`
5. Verify BEFORE walking away: `docker ps --format '{{.Names}} {{.Status}}' | grep -E 'leadgen_(app|db|redis|worker|scheduler|postiz)'` — **confirm the MAIN stack is still up**, not just postiz. Then `curl -s -o /dev/null -w '%{http_code}' https://leadsgenai.in/health` = 200 and `https://postiz.leadsgenai.in/` = 307.
6. Env-name trap: compose passes `FACEBOOK_APP_ID`/`FACEBOOK_APP_SECRET` (NOT Postiz-docs' `FACEBOOK_ID`/`FACEBOOK_SECRET`). Checking the wrong name reports a false "unset" — verify against `deploy/compose/docker-compose.postiz.yml`, not upstream docs.

**Close open registration:** `POSTIZ_DISABLE_REGISTRATION=true` in `deploy/postiz/.env`, then step 4–5. Lock-out-safe: existing operator account must already exist in Postiz DB. Verify: `https://postiz.leadsgenai.in/auth/register` should stop creating accounts; existing login still works.

**Reconnect YouTube (recurs every ~7 days until fixed properly):** the Google OAuth client is in **testing** mode → refresh tokens expire after 7 days. Postiz UI → the YouTube channel → reconnect. **Permanent fix** = Google Cloud Console → the `LeadsGenAI` project → OAuth consent screen → **Publish app** (production). Check state without guessing:
`docker exec leadgen_postiz_db psql -U postiz -d postiz -t -A -F' | ' -c 'select "providerIdentifier","refreshNeeded","tokenExpiration" from "Integration" where "deletedAt" is null;'`

## Postiz publish readiness — how to actually verify (do NOT trust one field)
`/api/growth/social/postiz/status` reports EFFECTIVE config + `integrations_source` (`client` / `social_config` / `env` / `vault` / `none`). **ADR-117:** global `POSTIZ_INTEGRATIONS` is own-brand/admin only — customers must have their own `postiz_integrations` (client dict or wizard `social_config`). Precedence: client → social_config → (own-brand only) env → vault. Ground truth (read-only, posts nothing):
```
docker exec leadgen_app python -c "from app.marketing import postiz_publish as pp; c={'id':'jiya-makeover'}; print(pp.integrations_source(c), pp.effective_integration_ids(c)); print('own', pp.integrations_source(), pp.effective_integration_ids())"
```
Empty list for a customer = no Postiz publish (honest). Also check `data/social_engine.json` `dry_run` — `true` fabricates `ok=True` (ADR-098). Hourly drain = staff job `social_drain` (:10 IST).

### Postiz QUEUE stuck / zombie orchestrator (2026-08-05)
Symptom: LeadGen API marks social jobs `published` + Postiz has `postId`, but FB/IG/X never show the post. DB: `SELECT state,count(*) FROM "Post" GROUP BY state` shows `QUEUE` growing; Temporal `workflow list` shows `post_*` Running for hours; `temporal task-queue describe --task-queue main` shows **empty Pollers** even though `pm2 list` says orchestrator online (~60–90MB = ghost).
Recovery (NEVER `--remove-orphans` on postiz compose):
```
cd /opt/leadgen
docker compose -f deploy/compose/docker-compose.postiz.yml --env-file deploy/postiz/.env up -d --force-recreate --no-deps postiz
# wait ≥150s for orchestrator compile
docker exec leadgen_postiz npx pm2 list
docker exec leadgen_temporal temporal task-queue describe --task-queue main --namespace default
# expect Pollers Identity non-empty; QUEUE count → 0; PUBLISHED releaseURL set
```
X/`twitter` ERROR with `credits depleted` / 402 = operator must top up X API or set `POSTIZ_SKIP_PLATFORMS=x` (after deploy that ships the skip flag). Instagram/YouTube need media — text-only jobs skip those channels by design.

### Postiz multi-channel selection (2026-07-23 Stage 2 closure)
- `POSTIZ_PINTEREST_BOARD` — required when a Pinterest integration is in the target list. **Unset/whitespace = Pinterest skipped**; other eligible channels still publish (one bad channel must not 400 the whole batch).
- `POSTIZ_PUBLISH_MAX_CHANNELS` — integer cap after eligibility filtering. `unset` = uncapped (legacy). `0` / negative = **block** (no create-post API). Invalid string = uncapped + warning. Values >20 clamped to 20.
- `POSTIZ_SKIP_PLATFORMS` — CSV of Postiz identifiers to skip (e.g. `x` when API credits=0).
- Zero eligible targets → `sent=False`, **no** upload/create API call.
- Dry-run (no publish): `from app.marketing.postiz_publish import plan_publish_channels` with a local `platform_map` — does not call create/upload.
- Video scheduler: `VIDEO_AD_CYCLE=1` **or** `VIDEO_DAILY_SCHEDULER_ENABLED=1` arms `video_ad_cycle.run_cycle` (alias parity). Publish still gated by approval + `VIDEO_SOCIAL_PUBLISH_ENABLED`.

## Prod incident (skill: `prod-incident-triage`)
Health 000/502 → `docker ps` + logs → py-spy dump on stuck proc → recover (targeted restart, NOT blind) → root-cause → postmortem entry in `memory/incidents.md` + prevention rule. Self-heal cron `scripts/vps_selfheal.sh` */10 already running.

## Backups & restore (proven 2026-07-02)
Host crons: 02:30 pg_dump → Drive; 02:45 data tar (excludes ollama/u2net/backups) → Drive; email-backup cron offsite. Restore drill: pull dump → restore to scratch DB → row-counts match → FK validate. Token rotate: Google Drive → Security → third-party access.

## Gemini voice-key add/rotate
Admin "Voice Keys" page (ya `POST /api/admin/voice/gemini-keys`) → per-key Google-validate → no restart needed. Pool auto-advances on 429.

## Monthly memory pruning (INDEX rule 4)
CLAUDE.md `## Current State` > 40 lines? → stale items ko `decisions.md` me move ya delete. Stale gotcha jo ab code me fixed = incidents entry me archive. AGENTS.md byte-copy re-sync (`Copy-Item CLAUDE.md AGENTS.md`).

## Knowledge stack — OKF vs Qdrant (ADR-119)
- **OKF** (`knowledge/`): curated rules/runbooks/agent policy — Git-diffable Markdown+YAML. Edit here for stable project knowledge; never put secrets.
- **Qdrant** (`kb_main`): documents/FAQs/transcripts/approved content — Hybrid Agentic RAG upgrade path (dense+sparse later). Do **not** answer live invoice/lead counts from RAG.
- **Postgres/API**: live operational truth. **Graphify**: code/workflow relationships only. **Redis**: short-term state.
- Conflict: code wins, then fix OKF/`memory/`.

## Adding a scheduler job (skill: `scheduler-job`, `teach-agent-loop`)
6-layer wiring (job fn + team_scheduler slot + worker task + heartbeat + admin toggle + test) → boot-grace for heavy jobs → parity guarded by prod_check automation-gaps.

## platform_dial STAGED re-enable (2026-07-16 — user go-ahead mila; safeguards ADR-025/027 verified complete, tests 25/25)
3-layer kill abhi: `PLATFORM_DIAL_DAILY=0` (VPS .env — env explicit 0 = FINAL, file override nahi kar sakta) + `data/platform_dial.json enabled:false` + scheduler override paused. Safeguards jo pehle se built: dial_gate allowlist (fail-closed default ON) · in-call IVR-strike → call_feedback blocklist · call_qualifier bot-gate (qualified force-false on IVR-suspect/min-3-turns) · phone-type gate · learned prefix-block · `PLATFORM_DIAL_LIMIT` cap · place_call me gate (error = promotional block).
**Stage 1 (allowlist test):** USER apna mobile `data/dial_test_mode.json` `numbers` me daale (ya `DIAL_TEST_ALLOWLIST` env) → VPS .env `PLATFORM_DIAL_DAILY` unset/=1 (USER-only edit) → `data/platform_dial.json {"enabled":true,"limit":3}` → scheduler override un-pause. Test-mode ON hi rehta = batch SIRF allowlist numbers dial karega; user khud agent ki quality sune. `scripts/agent_tester.py` scorecard bhi le (§6 DoD).
**Stage 2 (real):** recordings/scorecard OK + USER final "go" → `data/dial_test_mode.json {"enabled":false}` → real prospects, saare gates (DND fail-closed 9am-7pm window, blocklist, phone-type, cap) active. Rollback kabhi bhi: `PLATFORM_DIAL_DAILY=0` (1 env var, instant).
NOTE: calling window code-conservative 9am–7pm; DLT approved hai (2026-07-14) — cold outbound legal-side clear.

## OpenClaw LOCAL desktop gateway â€” 24/7 run + recovery (2026-08-02)
Prod OpenClaw (Stage A, in-app) is unrelated to this: it rides the `leadgen_app` container, `restart=unless-stopped`, `OPENCLAW_ENABLED=1` / `OPENCLAW_ALLOW_RED_ACTIONS=0` / gateway IPs `127.0.0.1,::1` â€” verified 24/7 on 2026-08-02.
**Local install:** openclaw `2026.7.1-2` at `C:\oc` (bundled node `C:\oc\node-v24.16.0-win-x64\node.exe` â€” system node 24.9.0 is NOT WAL-reset-safe, openclaw refuses it). Config/state `~/.openclaw`.
**2026-08-02 state was DEAD:** config wiped (every CLI call demanded onboarding), scheduled task `OpenClaw Gateway` Disabled and pointing at a non-existent `gateway.cmd`, last live run 2026-07-21 died in a telegram `deleteWebhook 404` auto-restart loop.
**Re-onboard (non-interactive):** `node C:\oc\node_modules\openclaw\openclaw.mjs onboard --non-interactive --accept-risk --json --mode local --flow quickstart --auth-choice groq-api-key --groq-api-key <key> --gateway-bind loopback --gateway-auth token --gateway-token <tok> --install-daemon --daemon-runtime node --node-manager npm`. Result: gateway `127.0.0.1:18789` token-auth, logon item `Startup\OpenClaw Gateway.vbs`, launcher `~/.openclaw/gateway.cmd`.
**Provider = Groq, NOT Gemini.** All 8 keys in the old `GEMINI_API_KEYs.txt` are DEAD (HTTP 400 on `models.list`); the only live Gemini key is the voice-scoped one in `.env` and sharing it would eat voice quota. Groq/Cerebras/NVIDIA all returned HTTP 200 â€” Groq chosen.
**Watchdog:** `scripts/openclaw_watchdog.ps1` + scheduled task `OpenClaw Watchdog` (every 5 min + AtLogOn). Checks port 18789 + HTTP (401/403/404 still counts as alive), restarts via `gateway.cmd`, logs to `~/.openclaw/logs/watchdog.log`, optional ntfy page if `C:\oc\watchdog\ntfy.txt` holds a topic URL. **Proven 2026-08-02:** gateway killed -> `UNHEALTHY` -> `RECOVERED` in 19s.
**Gotcha:** the legacy `OpenClaw Gateway` scheduled task cannot be re-registered without admin (`Register-ScheduledTask` = Access Denied 0x80070005). Do NOT disable the Startup VBS expecting the task to take over â€” that leaves nothing starting the gateway. Startup VBS + Watchdog task is the working no-admin combo; the legacy task stays Disabled on purpose.
**Caveat:** local `24/7` = only while the machine is on and the user is logged in. Real 24/7 is the VPS.

### OpenClaw Windows Tray — common issues & fixes (2026-09-01)
**Setup port conflict (AddressAlreadyInUse):** setup-engine `preflight-port` fails if gateway is already running on :18789. Fix: `Stop-Process -Id <gateway-PID>` first, then re-run setup. Watchdog now logs PID + process name on health/unhealthy to aid diagnosis. Local setup script (`scripts/openclaw_local_setup.ps1`) now warns about port conflicts before proceeding.
**Browser proxy (port 18791) not listening:** tray node declares `browser.proxy` capability but the gateway-side browser proxy sidecar is not running. This is a tray-level feature — only matters if `browser.proxy` commands are used. No code fix in this repo; tray app configuration issue.
**Zeroconf UnobservedTaskException:** .NET Zeroconf/mDNS UDP socket abort during task finalization. Benign — does not affect gateway operation. Known .NET race condition in `Zeroconf.NetworkInterface.NetworkRequestAsync`. No fix needed.
**vmmemWSL memory pressure:** unused Ubuntu-24.04 WSL distro holds RAM via vmmemWSL process (~2.2 GB). Fix: `scripts/finish-wsl-removal.ps1` (backs up OmniRoute config, then prints gated `wsl.exe --unregister Ubuntu-24.04` command). WSL is NOT required for LeadGen core. Docker Desktop uses its own `docker-desktop` distro.
**Hermes Desktop lock file:** startup fails if `.lock` file exists from a previous run. Fix: delete the lock file or kill stale Hermes processes before restarting. Agent already handles this automatically.
**Connection instability at startup:** 8+ failed attempts with exponential backoff (1s → 73s) is normal gateway cold-start behavior. Sidecars take time to initialize. Once connected, stability is proven (heartbeats every 30m, health checks every 60s). No fix needed.
**Tray diagnostics bundle:** generated via tray menu → Debug → Export. Read-only, sanitized. Contains: connection timeline, tray log tail, diagnostics JSONL, crash log, setup logs. Useful for support but not actionable from this codebase.

## Documents folder hygiene (2026-08-02)
`C:\Users\Ratanshila\Documents` had 3 orphaned git worktrees (`leadgen-admin-ux-pr`, `leadgen-oc-enter-fix`, `leadgen-openclaw-release`) whose gitdirs were gone. Proved safe to archive: 9,685 files hashed with `git hash-object` + `cat-file --batch-check` -> only 9 blobs absent from the object DB, all of them `_tmp_*.txt` scratch or gitignored runtime `data/*.jsonl`. Zero source lost; OpenClaw work already merged (PR #65/#105/#114/#122/#146/#198), loop27/28 19/20 files in HEAD.
Layout now: `_archive_2026-08-02` (worktrees + backups + loop27/28 patch), `_trading` (MT5/crypto), `_personal` (docx), `_secrets_DO_NOT_COMMIT` (API-key txt â€” deliberately OUTSIDE the repo, never commit).

## GSC rank-tracking verification runbook (2026-08-11, ADR-177)
- **What:** daily Google Search Console snapshot (clicks/impressions/avg-position) for programmatic-SEO observability. Code INERT until creds set.
- **Enable (prod, once, owner):**
  1. GCP: naya project ya existing → Search Console API enable → service account + JSON key
  2. Search Console: add property sc-domain:leadsgenai.in → DNS TXT verification (Caddy/DNS provider)
  3. Property pe service-account email ko FULL access
  4. VPS .env: GSC_ENABLED=1, GSC_SERVICE_ACCOUNT_JSON=<json path/file content> (fallback google_sheets_credentials reuse), GSC_SITE_URL=sc-domain:leadsgenai.in
  5. docker compose -f docker-compose.vps.yml restart leadgen_app leadgen_worker leadgen_scheduler (bina rebuild)
- **Verify:** /api/clientops/gsc/overview admin → data block filled (na ki error) · data/gsc_daily.jsonl rows after 00:30 IST run · automation Mission Control me staff-gsc-rank-daily last_run fresh · ntfy page expected (staff job hooks)
- **Troubleshoot:** creds bad → module logs + never raises (graceful no-op). Google libs missing in image → google-api-python-client add karke rebuild; ImportError is CAUGHT so prod safe.
- **Rollback:** GSC_ENABLED=0 + restart — beat entry stays but job exits early; files data/gsc_daily.jsonl safe to delete.

## B3 email deliverability (DKIM/SPF/DMARC) runbook (2026-08-11, ADR-085 closure)
- **Current state (LIVE, verified):** SPF =spf1 include:_spf.mail.hostinger.com -all · DMARC p=quarantine (strong) · DKIM selector hostingermail-a._domainkey CNAME dkim.mail.hostinger.com (real RSA key). data/deliverability_checks.jsonl from 2026-07-12 onward: spf/dmarc/dkim all OK, problems=[]; last check 2026-08-06. Script: deliverability_monitor.py (scheduler pe).
- **Verify anytime:** .venv\Scripts\python.exe scripts\deliverability_monitor.py (ya jsonl tail). DNS manual: dig TXT leadsgenai.in (SPF), dig TXT _dmarc.leadsgenai.in (DMARC), dig CNAME hostingermail-a._domainkey.leadsgenai.in (DKIM).
- **Owner DNS action needed only if:** selector rotate karna ho (Hostinger panel) → naya CNAME hostinger ki taraf, phir deliverability_monitor.py confirm; ya DMARC ko p=reject tak tighten karna ho (quarantine abhi safe tier hai — pehle 30-60 din quarantine pe volume dekho).
- **What breaks email:** hostinger account suspend (bulk/abuse) · daily cap (25/day outreach) · SPF include typo. Recovery = Hostinger panel check + DNS records re-add + monitor green hone tak emails bhejna band.
- **Never:** admin@leadsgenai.in se bulk bhejna (cap), ya SPF/DKIM records alag provider pe point karna (Hostinger SMTP hi truth hai).

## Boss Autonomy launch + rollback runbook (2026-08-20, ADR-184/185)

**State:** CODE-PRESENT + TEST-PROVEN + DEPLOYED (`ddf47c4a`); flags OFF/inert; `manager` rollout held; admin `GET /api/admin/boss-autopilot` LIVE (require_admin); beat `boss-autonomy-sweep` every 5m (flag-gated inert).

**Launch (flag arm — owner-gated, reversible):**
1. Backup: `cp /opt/leadgen/.env /opt/leadgen/.env.bak-boss-autonomy-<ts>`
2. Generate secret: `openssl rand -hex 32` → add `BOSS_GOV_AUTHORITY_KEY=<secret>` to `/opt/leadgen/.env` (NEVER commit).
3. Add `BOSS_DECISION_GOVERNANCE=1` + `BOSS_FULL_AUTONOMY=1` to `.env`.
4. Recreate: `docker compose -f docker-compose.vps.yml up -d app worker scheduler`
5. Verify (admin JWT): `curl -H "Authorization: Bearer <adminJWT>" http://127.0.0.1:8000/api/admin/boss-autopilot` → `status.enabled=true`, `status.ready=true`.
6. Canary (harmless internal, no customer side-effects): `docker exec leadgen_app python -c "from app.platform import boss_autonomy as ba; print(ba.propose_and_decide(decision_type='internal_plan', title='launch-canary', agent_id='hermes', proposed_by='hermes'))"` → expect `outcome=executed` (if obsidian advice present) or `outcome=deferred` (fail-closed, no advice).

**Rollback (kill switch):**
1. `cp /opt/leadgen/.env.bak-boss-autonomy-<ts> /opt/leadgen/.env`
2. `docker compose -f docker-compose.vps.yml up -d app worker scheduler`
3. Verify `enabled=false`, `ready=false`; sweep stops; coordinator governance ledger inert again.
4. Code rollback (if needed): `bash scripts/deploy_vps.sh 67aabd2a` (rollback tag protected).

**Gates to remember:**
- `manager` rollout = held → Boss self-execution blocked until a dedicated mutating canary promotes it; use canary executors (`hermes`/`kavya`/`isha`) as `agent_id`.
- Advisory-absence defers (never auto-executes): execution needs obsidian second-brain notes with score ≥ 0.65.
- RED / UPI / unknown types refuse; AMBER → `needs_owner` (Owner OS decides).
