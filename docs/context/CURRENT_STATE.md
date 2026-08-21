# CURRENT_STATE - LeadGen AI (operational truth)

Evidence labels: PRODUCTION-PROVEN | CODE-PRESENT | TEST-PROVEN | LOCAL-ONLY | PARTIAL | STALE | UNKNOWN | DIRECT_HOST_VERIFIED | GIT_VERIFIED | ASSUMED
(`DIRECT_HOST_VERIFIED` = probed from the live host at a stated time; `GIT_VERIFIED` = re-derivable from this repo; `ASSUMED` = carried forward, not re-checked.)

## HYPERFRAMES ENABLED 2026-08-20 ~23:00Z — advanced video toolchain LIVE in worker-video
- **worker-video now runs `ghcr.io/...-video:1a48039b`** (Dockerfile.video overlay) with node v22.23.2 + hyperframes CLI v0.7.87 + Chrome headless. Flags already ARMED (`CREATIVE_PROVIDER_HYPERFRAMES_ENABLED=1`, canary tenant `leadgenai-self`).
- **In-container render proof:** composition compiled (1080x1920, 25.4s, 762 frames), Chrome launched, frames streamed. Static templates use screenshot capture (slow); mem_limit raised 4096m→10240m (PR #426) to escape the slow low-memory profile.
- Rollback: redeploy worker-video WITHOUT the overlay (back to shared app image).
- Label: DIRECT_HOST_VERIFIED (2026-08-20 ~23:00Z).

## DEPLOYED 2026-08-20 ~22:35Z — `1a48039b` (PR #425 Postiz X caption truncation)
- **Prod `/health` = `1a48039b`** (DIRECT_HOST_VERIFIED 22:36:10Z): `healthy` · `environment:production`. **5/5 app-image pinned `1a48039b` zero-skew**. VLK=0 restored. Rollback `2af569a2`.
- Ship: PR #425 — per-platform caption truncation (X 280, Instagram 2200, LinkedIn 3000, etc.) fixing X "post is too long" 400.
- Label: DIRECT_HOST_VERIFIED + GIT_VERIFIED (origin/main == `1a48039b`); rollback `2af569a2`.

## DEPLOYED 2026-08-20 ~18:05Z — `2af569a2` (PR #423 video own-brand canary auto-approve+publish)
- **Prod `/health` = `2af569a2`** (DIRECT_HOST_VERIFIED 18:00:24Z + 18:01:07Z): `healthy` · `environment:production`. **5/5 app-image pinned `2af569a2` zero-skew**. VLK=0 restored. Rollback `525cd33f`.
- Kill-fence SOP: `.env.bak-killfence-20260820_video` → `VOICE_LAUNCH_KILL=1` → `deploy_vps.sh` `=== DEPLOYED 2af569a2 OK ===` → VLK revert `0` → recreate 5 services.
- Ship: PR #423 — `VIDEO_OWN_BRAND_AUTO_APPROVE` flag (CANARY-FIRST) + SYSTEM principal + `auto_approve_own_brand_pending` (own-brand only, bounded, idempotent) wired into `publish_due`. Armed in prod .env (=1); `VIDEO_OWN_BRAND_ENABLED` already =1.
- **PROVEN:** trigger => auto-approve `{approved:2, cap:2}` + publish_due `{published:4, failed:1}`; REAL Postiz post_ids (4 channels). X 1-fail = "post is too long" (caption > X limit).
- **HyperFrames gap:** `CREATIVE_PROVIDER_HYPERFRAMES_ENABLED=1` + `CREATIVE_HYPERFRAMES_CANARY_TENANTS=leadgenai-self` ARMED, but toolchain MISSING from prod image (no node / hyperframes bin) — advanced render fail-closed.
- Label: DIRECT_HOST_VERIFIED + GIT_VERIFIED (origin/main == `2af569a2`); rollback `525cd33f`.

## DEPLOYED 2026-08-20 ~14:05Z — `525cd33f` (PR #422 Swara enterprise pitch + flagship voice model)
- **Prod `/health` = `525cd33f`** (DIRECT_HOST_VERIFIED 14:04:24Z + 14:05:13Z): `healthy` · `environment:production`. **5/5 app-image pinned `525cd33f` zero-skew**, all `(healthy)`. VLK=0 restored (calling live). Rollback `658fc20a` (lineage).
- Kill-fence SOP: `.env.bak-killfence-20260820_1935` → `VOICE_LAUNCH_KILL=1` → `deploy_vps.sh` `=== DEPLOYED 525cd33f OK ===` (smoke 200, queues 0/0) → VLK revert `0` → recreate 5 services.
- Ship: PR #422 (owner-authorized voice change, overrides Swara FROZEN): `universal_pitch.py` outcome-first enterprise opener/pitch + `telecaller_brain.py` `_voice_model` default → `gemini-2.5-flash` (flagship-fast). Compliance (AI disclosure, permission, soft-no, price-truth) UNTOUCHED. CI all required PASS.
- Voice model truth: `VOICE_LLM_MODEL=gemini-2.5-flash` · `VOICE_GEMINI_PRIMARY=1` · `DEFAULT_LLM=mistral-small-latest` (voice-scoped Gemini flagship-fast primary; global free stack).
- Label: DIRECT_HOST_VERIFIED + GIT_VERIFIED (origin/main == `525cd33f`); rollback `658fc20a`.

## RUNTIME FLAG + CRED TRUTH 2026-08-20 ~13:05Z (fresh host probe — supersedes older flag/cred lines)
- **Prod `/health` = `658fc20a`** re-verified (12:57:50Z + 12:58:34Z advancing, `environment:production` healthy). **5/5 app-image services pinned `658fc20a` zero-skew**, all `(healthy)`. `leadgen_dsh_worker` running (`leadgen-dsh-worker:658fc20a`) but `DSH_RUNTIME_ENABLED=0` (fail-closed). Staging `28ba5d4e`.
- **Queues clean:** celery=0 · dlq:failed_tasks=0 · dlq:dead=0. Runtime-data cutover `RUNTIME_DATA_CUTOVER_ENABLED=1`, canonical store `/opt/leadgen-runtime` (host) actively written (heartbeats fresh 13:03, job_runs 37MB).
- **Automation LIVE:** all scheduler jobs `ok=true` fresh — growth, email_outreach/email_followup, sales_autopilot, social_drain, daily_video, gsc_rank, platform_dial (06:00), coordinator, product_one_health, hot_queue_brief, daily_owner_brief, boss-autonomy-sweep (every 5m).
- **Flag drift CORRECTED (older docs said OFF/pending — LIVE truth):** `BOSS_FULL_AUTONOMY=1` + `BOSS_DECISION_GOVERNANCE=1` (governance sweep LIVE, **agents UNARMED 30/30** — rollout held, no mutating canary yet) · `CRM_SYNC=1` + `CRM_SYNC_PULL=1` · `COORD_PLAN_NODE=1` · `DAILY_VIDEO_CLIENTS=*` · `VIDEO_AD_CYCLE=1` · `DUNNING_ENGINE=1` · `OPENCLAW_ENABLED=1` · `DSH_RUNTIME_ENABLED=0` · `GSC_ENABLED` UNSET (creds present) · `VOICE_LAUNCH_KILL=0` · `PLATFORM_DIAL_DAILY=1` + `PLATFORM_DIAL_LIMIT=100` · `WHATSAPP_AUTO_SEND=1`/`POST_CALL_WHATSAPP=1`/`VOICE_CLOSE_WHATSAPP=1` · `SALES_AUTOPILOT_WHATSAPP_ENABLED=0` (cold WA OFF) · `UPI_AUTO_ACTIVATE=1` scoped to one client.
- **Provider creds PRESENT by name (older docs said "pending"):** ZOHO (id/secret/refresh) · HUBSPOT_API_KEY · GSC_SERVICE_ACCOUNT_JSON + GOOGLE_SHEETS_CREDENTIALS · META_APP_ID/SECRET/OAUTH_APPROVED · POSTIZ_API_KEY/URL/INTEGRATIONS · WAHA_API_KEY/BASE_URL/SESSION/WEBHOOK_TOKEN.
- Label: DIRECT_HOST_VERIFIED (2026-08-20 ~13:05Z, host + container env).

## DEPLOYED 2026-08-20 ~12:40Z — `658fc20a` (PR #421 wiring-gap self-diagnosis)
- **Prod `/health` = `658fc20a`** (DIRECT_HOST_VERIFIED 2026-08-20 12:40:05Z + 12:40:08Z public HTTPS dual probe — timestamps ADVANCE 3s ⇒ live, not cached): `healthy` · `environment:production` · uptime 4m.
- Pre-deploy live probe (12:07:58Z) found prod actually at `16c0475e` (NOT `ddf47c4a` — the AGENTS.md "Ops facts hot" `ddf47c4a` was STALE; SHA-discipline landmine — live probe wins). VPS checkout HEAD was `16c0475e`, FF-able to origin/main.
- Deploy via `scripts/deploy_vps.sh` (CANONICAL): candidate resolved `658fc20a` from origin/main (PR #421 squash-merged after GitHub branch-protection refused a direct `main` push — required PR + 3/3 status checks, all GREEN including Gate A this run + full pytest shards 1–4). Kill fence MANDATORY: `prod_check --deployment` gate requires `VOICE_LAUNCH_KILL` TRUE_TOKEN — UNSET/FALSE both BLOCK (`scripts/prod_check.py` `check_voice_launch_kill_env`).
- Kill-fence SOP: backup `.env.bak-killfence-20260820_120758` → `VOICE_LAUNCH_KILL=1` → `deploy_vps.sh` `=== DEPLOYED 658fc20a OK ===` (queues 0/0, smoke 10/10 → 200, lineage ROLLBACK_TAG=`16c0475e`, removed `ddf47c4a`) → VLK revert `0` → `APP_VERSION=658fc20a` recreate of all 5 app-image services. **5/5 pin `658fc20a`, VLK=0 in every service** (calling RESTORED). Disk 51%, 96G free.
- Ship: PR #421 `feat(automation): wiring-gap self-diagnosis — surface flag-ON-but-unwired`. `wiring_gaps()` reuses canonical `gsc.enabled()` (honours `google_sheets_credentials` fallback + file-exists; the prior narrow manual check false-alarmed). Signal surfaced in **daily owner brief** (p2 exceptions) + **Mission Control** rollup — "flag ON but backend/creds missing" now visible instead of dead data. 6 regression tests. Diff: automation_health.py, owner_brief.py, control_center.py, admin_dashboard.html (dialer nav — `/app/dialer` route verified-live), test file.
- Owner revenue gates unchanged (NOT a revenue fix): `ready_for_first_paid_customer` still owner-gated on UPI bind + bank confirm; cold WA + ToS-scrape still OFF by design. (Flag/cred truth corrected by the 13:05Z probe block above — CRM LIVE `hubspot`, GSC creds PRESENT with only `GSC_ENABLED` flag flip remaining; this deploy did NOT touch flags/creds.)
- Label: DIRECT_HOST_VERIFIED + GIT_VERIFIED (origin/main == `658fc20a`); rollback `16c0475e`. **AGENTS.md `## Current State` "Ops facts hot" `ddf47c4a` / `16c0475e` now SUPERSEDED — re-probe `/health` before quoting any SHA.**

## RE-VERIFICATION 2026-08-16 ~04:53Z — DEPLOY `237e20ac` (PR #380 marketing factory + admin scorecard)
- **Prod `/health` = `237e20ac`** (DIRECT_HOST_VERIFIED 04:53:37Z host + 04:53:56Z public HTTPS): `healthy` · `environment:production` · uptime 0h0m58s.
- Kill-fence deploy: backup `.env.bak-killfence-20260816_044850` → `VOICE_LAUNCH_KILL=1` → `scripts/deploy_vps.sh` **`=== DEPLOYED 237e20ac OK ===`** → VLK revert `0` → `APP_VERSION=237e20ac` recreate of all 5 app-image services. **5/5 pin `237e20ac` zero skew** (app/worker/scheduler/worker_heavy/worker_video), VLK=0 in all 5, celery=0, dlq:failed_tasks=0, dlq:dead=25 (pre-existing, do not flush). Disk 50% after build-cache retention; removed `fed0797a`; ROLLBACK_TAG=`520e90eb` (lineage `/var/lib/leadgen/deploy_rollback_lineage.json`).
- Batch contents: marketing factory ledgers on admin scorecard (form/proposal/review/drips/health/appointment builders, flags OFF), Hot Queue start-here card fix, lint/ruff-format alignment, runtime-data ratchet 62→70.
- PR #380 merged via squash (`237e20ac`, mergedBy sumitrevolt 04:30:56Z). Required CI gates green: Lint+syntax+secrets, prod_check+pytest, harness real-redis. Gate A (ruff-format vs black on test_plugin_manifest assert) + CodeQL (2 advisory findings) remain FAIL but non-required.
- `origin/main` = `237e20ac` now matches prod. Local checkout on `cursor/marketing-factory-admin-scorecard` (fast-forward behind main); `git checkout main` + `git pull` pending for clean local state.
- Inert unchanged: DSH runtime/shadow FALSE, HARNESS_SESSION_EVENTS/AGENT_HARNESS/GSC/HQ_AUTO_CHASE UNSET. Owner WAIT: Hot Queue `/app/inbox` blitz, UPI bind/re-approve, bank-credit confirm.
- Label: DIRECT_HOST_VERIFIED + GIT_VERIFIED; owner revenue gates remain owner-execution.

## RE-VERIFICATION 2026-08-16 ~03:18Z — Cursor admin marketing ledger tiles (uncommitted)
- Admin scorecard second row `#ownerMktScorecard`: review requests sent, drip sent/opened, forms submitted, proposals accepted, reminders sent, health at-risk. Source = existing `GET /api/growth/overview/today` totals. **No new route. Flags stay OFF.**
- Honest mapping: `reviews_sent` = sequence `sent` (not Google pixels); `drip_emails_opened` = drip-run `opened` (0 until EMAIL_TRACKING writes it); `health_at_risk` = `at_risk` only. Fail-open zeros; not in `problems`/`headline`/`top_blocker`.
- Tests: `test_today_overview` + `test_admin_scorecard` 52 passed; `check_html_js` JS_OK; `prod_check` ALL CHECKS PASSED (1322 routes, API.md 1344); secrets OK. Prod SHA not re-probed this slice (still `520e90eb` from earlier DIRECT_HOST_VERIFIED).
- Do **not** arm FORM_BUILDER / PROPOSAL_BUILDER / REVIEW_MONITOR / BOOKING_REMINDERS / CLIENT_HEALTH_ALERTS / EMAIL_TRACKING from this session. Customer forms/proposals pages still parked.
- Label: TEST-PROVEN + GIT_VERIFIED; Owner WAIT unchanged.

## RE-VERIFICATION 2026-08-16 ~02:16Z — Cursor ratchet/flag fix (code-only, uncommitted)
- Root cause of PR #379 CI FAIL: `runtime_data_path_scan.py ratchet` NEW_UNDECLARED / NEW_AMBIGUOUS on marketing JSONL (`appointment_reminders`, `customer_health`, `email_drips`, `form_builder`, `proposal_builder`, `review_automation`). Classified as 6 TIER_3 REBUILDABLE_CACHE families + 8 allowlist rows (GSC pattern). `deployment_blockers` still 0.
- `ONBOARDING_PIPELINE` / `FORM_BUILDER` / `PROPOSAL_BUILDER` now in `AUTOMATION_FLAGS` + typed overlay (CANARY_ONLY, default `"0"`). Form/proposal admin routes 503 while flag off. **Do not arm.**
- `scripts/runtime_data_path_scan.py ratchet` = **RATCHET OK** newly unresolved=0 (LOCAL-ONLY). `prod_check` ALL CHECKS PASSED (1322 routes, API.md 1344 in sync). Secrets OK.
- Local gitignored `scripts/_tmp_void_invoices_c.sh` deleted (scanner saw `cp data/…` as undeclared `data` REWRITE). Not in git.
- Prod SHA this session still **`520e90eb`** from earlier DIRECT_HOST_VERIFIED (not re-probed this fix). Uncommitted slice still not live.
- Label: TEST-PROVEN + GIT_VERIFIED; Owner WAIT unchanged.

## RE-VERIFICATION 2026-08-16 ~01:18Z — Cursor REVENUE-50 CP0–CP7 (owner scorecard + C-01..C-15 + plugins deep-link)
- Prod `/health` = **`520e90eb`** healthy production (DIRECT_HOST_VERIFIED). Dual probe 01:00:28Z uptime `0h 35m 44s` → 01:00:31Z `0h 35m 47s`; re-probe 01:18:02Z `0h 53m 18s` → 01:18:04Z `0h 53m 21s`.
- `activation/summary`: `payments_ready=true` `blocker_count=1` `ready_for_first_paid_customer=false`. Authenticated readiness/plugins/overview = **401** (do not guess bodies).
- Git: local `main` `520e90eb` **ahead 3** of `origin/main` `8ebdf36e`. Live SHA is **unpushed** to GitHub. Open PR #379 CI FAIL (FreeBuff). FreeBuff worktree dirty — do not touch.
- Plugin catalog now **45** manifests (+ `onboarding_factory` / `form_builder` / `proposal_builder`, CODE_PRESENT, flags default OFF).
- C-01..C-15: source tests green; honest **L3** (C-05/C-09/C-12 PARTIAL). DSH `*` allowlist fail-closed empty. `swara`/`ananya` frozen on dispatch.
- Admin “Aaj kya karna hai” now includes UPI owner queue, onboard factory, DSH/Staff Bus tri-state. Explorer `?tab=plugins` shareable; Control Center Plugins deep-link.
- Buzz local `_liveness=ok` on `:3100`. OmniRoute `:20128` **timeout** this machine (WAIT). Boss LIVE canary still Owner Desktop WAIT.
- Tests this slice: 207 passed EXIT 0 · `prod_check` ALL CHECKS PASSED (1322 routes) · secrets OK · html_js JS_OK · `git diff --check` clean · voice diff **0 paths**.
- **Do not claim:** 50/day live · revenue-generated · authenticated `paid_today` · 5/5 pin (SSH not this session) · this uncommitted slice live on prod.
- Label: DIRECT_HOST_VERIFIED + TEST-PROVEN + GIT_VERIFIED; Owner WAIT items remain owner-gated.

## RE-VERIFICATION 2026-08-15 ~16:50Z — FreeBuff session: plugin architecture + automation portfolio + dashboard UX
- Prod `/health` = `963ee800` healthy production (16:50Z, uptime 1h33m, DIRECT_HOST_VERIFIED)
- `activation/summary`: `payments_ready=true` `blocker_count=1` `ready_for_first_paid_customer=false`
- Public pages: pricing/start/audit/inbox/health_ready/admin all HTTP 200
- Plugin registry: 42 plugins, 7 categories, 4 RED (require approval), 31 PRODUCTION_PROVEN
- Plugin API: GET /api/admin/plugins + /{id} + POST /drift (3 new routes, 1285 total)
- Explorer: PLUGINS tab added with topology panel + plugin_registry node
- Admin dashboard: live scorecards (paid/activations/Hot Queue/pending) + next best action
- Automation portfolio: 50 loops inventoried (28 KEEP, 2 FIX, 1 SCALE, 14 INERT, 8 KILL)
- Capacity: 50 fake onboardings, p50=74.9ms, p95=122ms, 13.1/s throughput, 0% failure
- Tests: 250+ targeted PASS, prod_check PASS, secrets clean, API.md synced (1307)
- Voice FROZEN: zero paths touched
- Files changed: 7 modified + 9 new = 16 total, NOT committed/pushed
- Label: DIRECT_HOST_VERIFIED + TEST-PROVEN + GIT_VERIFIED

## Last verified timestamp (superseded same-day 15:21Z)
2026-08-15 ~15:21Z — prod `/health` = `963ee800` (DIRECT_HOST_VERIFIED, public dual probe 15:21:24Z / 15:21:27Z uptime 0h4m55s→0h4m57s; host 15:22:37Z 0h6m7s). `environment:production` · `healthy`. Kill-fence deploy of `origin/main` via `scripts/deploy_vps.sh` (`=== DEPLOYED 963ee800 OK ===`) then VLK restore + `APP_VERSION=963ee800` recreate. **5/5 app-image pin `963ee800` zero skew**, VLK FALSE_TOKEN 5/5, celery=0, dlq:failed_tasks=0, dlq:dead=24 (pre-existing; do not flush). Inert: DSH runtime/shadow FALSE, HARNESS_SESSION_EVENTS/AGENT_HARNESS/GSC/HQ_AUTO_CHASE UNSET. Rollback = `07870e89`. Named blocker still owner-side (`blocker_count=1`, `payments_ready=true`, `ready_for_first_paid_customer=false`). Local leftover feature branches deleted (already squash-merged; re-merge would rewind). GitHub heads = `main` only at deploy. `HQ_AUTO_CHASE` stay INERT.

## Last verified timestamp (superseded same-day 14:10Z)
2026-08-15 ~14:10Z — prod `/health` was `07870e89` (DIRECT_HOST_VERIFIED, public dual probe 14:09:45Z / 14:09:48Z uptime 0h2m23s→0h2m27s, then 14:10:17Z / 14:10:20Z 0h2m55s→0h2m58s). SUPERSEDED by 15:21Z live `963ee800`.

## Last verified timestamp (superseded same-day 13:58Z — undeployed claim)
2026-08-15 ~13:58Z — prod `/health` was `91958c23` (DIRECT_HOST_VERIFIED, public dual probe 13:58:36Z / 13:58:39Z). `origin/main` was `07870e89` **then UNDEPLOYED**. SUPERSEDED by 14:10Z live `07870e89`.

## Last verified timestamp (superseded same-day 08:08Z)
2026-08-15 ~08:08Z — prod `/health` = `91958c23` (DIRECT_HOST_VERIFIED, public 07:51:24Z / 07:55:32Z + host 08:08:50Z uptime advanced). `origin/main` was then `920a3e62` **UNDEPLOYED**. Named blocker `upi_pending_unactioned` (1 approved-unbound, has_client=0). `paid_today=0` honest. Revenue audit: `docs/gtm/REVENUE_BLOCKER_AUDIT.md`. 3 CODE P0s later landed via PR #368 (`c4e9058f`) into `07870e89` ancestry — still not live until owner deploy.

## Last verified timestamp (superseded same-day 02:42Z)
2026-08-15 ~02:42Z — prod `/health` = `91958c23` (DIRECT_HOST_VERIFIED, dual probe 02:37:40Z / 02:40:09Z uptime advanced). NEXT todos agent-side READY. Owner inbox/UPI/Boss harness still remaining. DSH local smoke + Kavya MCP plan used; prod flags not flipped. PR #363/#364 ancestry sealed at ~00:01Z re-probe (5/5 pin, VLK=0).

## NEXT todos READY 2026-08-15 — Hot Queue / UPI / capacity honesty
- Label: DIRECT_HOST_VERIFIED + TEST-PROVEN + LOCAL-ONLY (DSH Docker smoke)
- Named blocker still `upi_pending_unactioned`; `payments_ready=true`; `paid_today=0`
- Heavy jobs named: `self_improve_tick`, `run_staff_job`, kb-warmup ~96s. CPU 0.46% at 02:41Z (was 155% 01:16Z). Onboard queue stays UNSET.
- One-pagers: `docs/gtm/HOT_QUEUE_BLITZ_CHECKLIST.md` · `docs/gtm/BOSS_HARNESS_CANARY.md` · board `docs/gtm/NEXT_TODOS.md` §6
- Owner remaining: authenticated `/app/inbox` blitz, UPI bind+bank, `buzz_start_harness.py --agent Boss` (not dry-run)

## NEXT42 2026-08-15 — revenue 20 + Buzz + max-safe auto + 50/day capacity
- Label: DIRECT_HOST_VERIFIED + TEST-PROVEN + LOCAL-ONLY (relay)
- Named activation blocker = `upi_pending_unactioned` (`payments_ready=true`)
- `paid_today=0` IST 2026-08-15 honest empty day
- T31 in running app: `_notify_owner_once` + `list_actionable` both True
- Buzz local relay LIVE `127.0.0.1:3100` `/_liveness=ok`; harness `--dry-run` uses `BUZZ_RELAY`; `#staff-pulse` posted 31/31; `#build` HANDOFF posted
- `CELERY_ONBOARD_QUEUE` UNSET/INERT. Heavy 02:41Z 0.46% after kb-warmup (01:16Z was 155% / 2 jobs) — still do not arm onboard→heavy
- Loadtest: `/health` 129×200; `/` 43×429 at 5 concurrent (rate-limit knee). Safe anonymous ≈ 3 concurrent. Do not raise `WEB_CONCURRENCY`
- Live vs intended (do not flip from this session): `COORDINATION_HUB_ENABLED=1`, `DUNNING_ENGINE=1`, `UPI_AUTO_ACTIVATE=1`, `DSH_RUNTIME_ENABLED=1`. Never-arm OK: cold WA=0, GSC UNSET, HARNESS_SESSION_EVENTS UNSET
- DLQ: trainer TimeLimitExceeded dead=24 (was 23 same day) — do not flush
- Evidence: `docs/gtm/NEXT42_EVIDENCE.md` · `docs/gtm/CAPACITY_50_DAY.md`
- Owner remaining: `/app/inbox` blitz, UPI bind+bank confirm, `buzz_start_harness.py --agent Boss` (not dry-run)

## RE-VERIFICATION 2026-08-15 ~00:01Z — independent probe, docs-only session (PR #364)
Ye block kisi deploy ka nahi hai — pichhle session ke claims ko **lead** maan kar dobara probe kiya.
- **PR #363:** `gh pr view 363` → `state=MERGED`, `mergedAt=2026-08-14T21:30:39Z`, `mergeCommit=91958c23feac5aa09d85ccf7dd3a3a62c981f119`. (GIT_VERIFIED)
- **Public `/health` ×2, cache-busted:** `23:59:49.113763Z` uptime `2h 15m 22s` → `00:00:01.593698Z` uptime `2h 15m 35s`. Dono probes: `healthy` · `environment:production` · `version:91958c23`.
- **5/5 app-image pin:** `leadgen_app`, `leadgen_worker`, `leadgen_scheduler`, `leadgen_worker_heavy`, `leadgen_worker_video` — sab `ghcr.io/...:91958c23`. **Zero skew.** VLK=0. Fence backup `.env.bak-deploy-killfence-20260814_213255` (naam only).
- **Not part of the 5 app-image set:** `leadgen_dsh_worker` image `leadgen-dsh-worker:fb3d0bc2`.
Label: DIRECT_HOST_VERIFIED (2026-08-15 ~00:01Z)

## CODE-READY / INERT — DeepSeek Harness migration contract (2026-08-14)
- Runtime now LIVE-AUTHORITY on prod (ADR-183) — see DSH section below if present in later blocks; this historical paragraph kept for ancestry.

## REVENUE VERDICT (2026-08-15 — evidence-bound, do not upgrade without new proof)
- **Technical money path: GO.** Public funnel + pricing + `/start` + manual-UPI rail + admin approve/bind + ledger-backed `paid_today` sab prod pe `91958c23` par live hain.
- **Authenticated Hot Queue (`/app/inbox`): WAIT — owner par.** Surface live hai; blitz execute karna owner ka authenticated kaam hai, koi agent iske liye login nahi karega.
- **UPI activation path: WAIT — input par.** Bind / Re-Approve tabhi chalega jab koi real payment aaye. Rail ready hai, payment nahi aayi.
- **REVENUE GENERATED: WAIT.** Ye tabhi GO hoga jab **owner khud bank credit confirm kare** (`payment_verification_method = owner_confirmed_upi`). `PROVIDER_VERIFIED` by design unreachable hai (Stripe + Razorpay dono removed).
- **Aaj ka `0/0` = honest empty day, failure nahi.** `paid_activations.daily_paid_activations()` ledger padh ke `0` de raha hai — ye "metric toota hai" nahi, "aaj koi paid nahi aaya" hai. Fail-closed design: resolve na ho paye to bhi `0`, kabhi paid count fabricate nahi karta.
- **Naya module / agent / loop banane ki zaroorat NAHI hai** jab tak ek **correlated real-funnel defect** evidence ke saath na mile. Abhi ka bottleneck code nahi, owner execution hai — is stage pe naya code likhna revenue ko aage nahi badhata.
Label: GIT_VERIFIED + DIRECT_HOST_VERIFIED (2026-08-15) for the technical facts; the WAIT items are owner/input-gated by definition, not by any defect.

## DEPLOYED 2026-08-14 — `91958c23` (PR #363 ledger-backed paid activations)
**Prod `/health` = `91958c23`** (DIRECT_HOST_VERIFIED 2026-08-14 ~21:45Z — host ×2 with advancing timestamps + public HTTPS): `healthy` · `environment:production`. Squash merge `91958c23feac5aa09d85ccf7dd3a3a62c981f119`; `origin/main` == merge SHA.
CI: **13/13 checks pass**, Gate A included (is baar Gate A green tha — koi ignore nahi). Runtime-data allowlist + debt ratchet both ✓ (module is read-only over existing ledgers, no new `data/` path).
Deploy: VPS HEAD was `c4fc0087` with **zero tracked-file modifications** (only untracked leftovers) → no `git checkout --`, no `reset --hard`. Kill fence `.env.bak-deploy-killfence-20260814_213255` → log proved `VOICE_LAUNCH_KILL_IS_TRUE_TOKEN=1` → `deploy_vps.sh` `=== DEPLOYED 91958c23 OK ===` → `VOICE_LAUNCH_KILL=0` + `APP_VERSION=91958c23` recreate of all 5 app-image services (**5/5 pinned, zero skew, VLK=0 in every container**).
Live proof inside `leadgen_app`: `paid_activations.daily_paid_activations()` → day `2026-08-15`, `paid_today=0`, `activations_today=0`; `today_overview.build().totals` carries the three new keys. **0 is the honest ledger answer for today.**
Smoke `/` `/pricing` `/start` `/audit` `/health/ready` → 200. Queues `celery=0` · `dlq:failed_tasks=0` · `dlq:dead=23` (**23 was also the pre-deploy reading — not caused by this deploy**). `leadgen_dsh_worker` healthy.
Flags after deploy (booleans only): `DSH_RUNTIME_ENABLED=1` · `DSH_SHADOW_ENABLED=0` · `GSC_ENABLED=UNSET` · `AGENT_HARNESS=UNSET` · `HARNESS_SESSION_EVENTS=UNSET` · `SALES_AUTOPILOT_WHATSAPP_ENABLED=0` · `VOICE_LAUNCH_KILL=0`.
Rollback lineage: `ROLLBACK_TAG=c4fc0087`, `PROTECTED=91958c23,c4fc0087`, `fb3d0bc2` pruned by retention.
`activation/summary` still `ready_for_first_paid_customer=false` / `blocker_count=1` / `payments_ready=true` — **identical to the `c4fc0087` reading, carried forward, not introduced by #363.**
Label: DIRECT_HOST_VERIFIED (2026-08-14 ~21:45Z)
**Still do not arm:** harness session events / GSC / dunning / cold WA.

## SUPERSEDED — DEPLOYED 2026-08-14 — `c4fc0087` (PR #362 revenue automation + DSH arm docs)
> Historical. Replaced by `91958c23`. Keep as rollback tag (`ROLLBACK_TAG`).
**Prod `/health` = `c4fc0087`** (DIRECT_HOST_VERIFIED 2026-08-14 ~18:17Z HTTPS×2 + host): `healthy` · `environment:production`. Squash merge `c4fc00870dd0c6cf9e12d231a38c892c515a4813`. Kill-fence `.env.bak-deploy-killfence-20260814_180531` → VLK TRUE → `deploy_vps.sh` `=== DEPLOYED c4fc0087 OK ===` → VLK=0 recreate with `APP_VERSION=c4fc0087` (5/5 skew). DSH stays `1`. Helpers proved: `list_actionable`, `_notify_owner_once`. Rollback lineage prior tag = `fb3d0bc2`.
Label: DIRECT_HOST_VERIFIED (2026-08-14) — SUPERSEDED by `91958c23`
**#307** OPEN; **#304** guest bind now ops-visible when approved-unactivated.

## DSH LIVE-AUTHORITY 2026-08-14 — owner override of ADR-182 wave order
- Label: DIRECT_HOST_VERIFIED (armed ~16:12Z; re-proved still true under `91958c23`)
- Flags: `DSH_RUNTIME_ENABLED=1` · `DSH_SHADOW_ENABLED=0` · allowlist 29 migratable (never `*`)
- Runtime image `leadgen-dsh:47f94385` · `leadgen_dsh_worker` healthy · redis alias on `leadgen_dsh_net`
- Env bak: `.env.bak-dsh-fullarm-20260814_155839` · Kill: `DSH_RUNTIME_ENABLED=0` + recreate with exact `APP_VERSION`
- ADR-183 override; legacy direct executor NOT deleted; retirement gates unchanged

## SUPERSEDED — DEPLOYED 2026-08-14 — `fb3d0bc2` (PR #361 DSH inert code + #357/#354)
> Historical. Replaced by `c4fc0087`. Keep as rollback tag.
**Prod `/health` was `fb3d0bc2`**. Kill-fence `.env.bak-deploy-killfence-20260814_150136`.
Label: DIRECT_HOST_VERIFIED (2026-08-14) — SUPERSEDED by `c4fc0087`

## CODE-READY / INERT — DeepSeek Harness (SUPERSEDED for runtime by ADR-183)
> Historical inert posture. Runtime now LIVE-AUTHORITY — see **DSH LIVE-AUTHORITY** above. Shadow soak / retirement gates from ADR-182 still apply before legacy deletion.
- Label: SUPERSEDED for flags; code path still PRODUCTION-PROVEN on `fb3d0bc2`
- Evidence artifacts remain under `docs/evidence/DSH_*_20260814.*`

## SUPERSEDED — DEPLOYED 2026-08-14 — `150bf898` (PR #356 hygiene + ADR-180)
> Historical. Replaced by `fb3d0bc2` above. Keep as rollback tag.
**Prod `/health` was `150bf898`** (DIRECT_HOST_VERIFIED 2026-08-14). Kill-fence `.env.bak-killfence-20260814035416`. Prior rollback `2326c931` pruned by retention after `fb3d0bc2` deploy.
Label: DIRECT_HOST_VERIFIED (2026-08-14) — SUPERSEDED by `fb3d0bc2`

## SUPERSEDED — DEPLOYED 2026-08-13/14 — `2326c931` (PR #327 mypy land)
> Historical. Replaced by `150bf898`, then pruned from image retention after `fb3d0bc2`.
**Prod `/health` was `2326c931`** (DIRECT_HOST_VERIFIED 2026-08-14 pre-`150bf898`).
Label: SUPERSEDED

## SUPERSEDED — DEPLOYED 2026-08-12 (estimated) — `9c47647c` (PR #332 ADR-177 batch)
> Historical. Replaced by `2326c931` above.
`origin/main` tip = `23ea2d46` (includes #333 staff-bus, #334/#335 docs). **Prod `/health` = `9c47647c`** (DIRECT_HOST_VERIFIED 2026-08-12 07:39 UTC). Deploy timestamp estimated ~2026-08-11 22:05 UTC (uptime 9h 33m backtrack). Includes: PR #332 (ADR-177 GSC + funnel + referral + triage), PR #330 (Boss governance), PR #329 (rollback retention).
Label: DIRECT_HOST_VERIFIED (2026-08-12) — SUPERSEDED by `2326c931`

## SUPERSEDED — DEPLOYED 2026-08-11 — `9b09a808` (PR #321)
> Historical. Replaced by `9c47647c` above.
Prod `/health` = `{"version":"9b09a808","environment":"production","status":"healthy"}` (DIRECT_HOST_VERIFIED 2026-08-11; two probes with unique `cb=` — timestamp/uptime advanced). Exact SHA = `9b09a80825389983829b1c0b4de6caf3789d16bf`.
**#304 / #306:** still WAIT live proofs. **#307:** dunning OFF.
Label: DIRECT_HOST_VERIFIED (2026-08-11)

## SUPERSEDED — DEPLOYED 2026-08-10 — `a3fbc8bb`
> Historical. Replaced as prod tip by later deploys; do not quote as current without re-probe.
Rollback ref chain includes `76348926`.
Label: STALE vs 2026-08-11 prod

## SUPERSEDED — DEPLOYED 2026-08-09 — `d1b106b2` (PR #294)
> Historical only. Do not quote as current. Replaced by `a3fbc8bb` above.

Prod `/health` was `{"version":"d1b106b2","environment":"production","status":"healthy"}`. All 5 app-image services on `:d1b106b2`, **zero skew**. Queues identical to the pre-deploy baseline (`celery` 0 · `dlq:failed_tasks` 0 · `dlq:dead` **8** — the 8 were already there BEFORE this deploy, do not attribute them to it). Public smoke: `/health` 200 · new `/api/clientops/video-production/daily-status` **401** (mounted + guarded) · unknown sibling route 404.
Kill-fence procedure executed as documented: backup `.env.bak-dailyvideo-20260809` → `VOICE_LAUNCH_KILL=1` → `scripts/deploy_vps.sh` → reverted to `0` → recreate → proven `0` in all 5 containers. `.env` is byte-identical to the pre-deploy backup (md5 `ec9db158d99269cc463e97923970b50f`).
**Every new flag stayed unset** (`DAILY_VIDEO_ENABLED`, `DAILY_VIDEO_CLIENTS`, `DAILY_VIDEO_ENGINE`, `CELERY_VIDEO_QUEUE`, `CREATIVE_PROVIDER_HYPERFRAMES_ENABLED`) — the producer is INERT in prod. Calling flags unchanged (`PLATFORM_DIAL_DAILY=1`, `PLATFORM_DIAL_LIMIT=100`, `DIAL_TEST_MODE=0`, `VIDEO_AD_CYCLE=1`).
Rollback ref = `3cd95ba2` (prior prod).
⚠️ **Operator error during this deploy, recorded so it is not repeated:** the fence-closing recreate was run as a bare `docker compose up -d` **without `APP_VERSION`**, so compose fell back to `${APP_VERSION:-latest}` and prod ran the `:latest` image (`266d772a…`) for ~55s before it was caught by the `/health.version` check and corrected with `APP_VERSION=d1b106b2 docker compose … up -d`. This is exactly the ADR-097 landmine. **Any manual recreate — including the one that closes the kill fence — MUST carry `APP_VERSION=<sha>`.** `deploy_vps.sh` itself was never the problem; it pinned correctly.
Label: DIRECT_HOST_VERIFIED (2026-08-09 post-deploy probes) — STALE vs current tip

## Approval backlog — real numbers + retirement tool (2026-08-09, PR #297)
"32 stuck approvals" was only the `video_ad` slice. Real queue = **422** `content_approval` pendings: **321** belong to client ids ABSENT from `clients_store` (8 dead ids — un-actionable forever), **101** belong to the 3 live clients (`leadgenai-self` 53 · `0511a69b900e` 28 · `jiya-makeover` 20).
**The 101 are NOT technically stuck.** `token_is_expired` is consulted in exactly ONE place (`approval_principal.from_approval_token` = the public emailed link); the authenticated dashboard resolves by id and never checks it, and the customer video path is fully wired (`customer_dashboard.py` → `from_customer_session` → `approval_saga`, UI supplies `expected_content_sha256`). Customers can complete them today.
**Why they don't:** the mail is announced once per item (`idempotency_key`) and says "You have content awaiting your approval" — singular, no count, no age. Prod `approval_notifications`: **36 mails sent to jiya-makeover 2026-07-14→08-09, all `sent`, zero failures**, 20 still open. Delivery was never the problem.
Shipped: `content_approval.retire_orphaned_pending()` (orphans only · append-only terminal `expired` · `dry_run=True` default · fail-CLOSED if the live-client set can't resolve · retiring ≠ approving) + queue-aware reminder wording (no extra sends). **Sweep NOT yet run against prod** — dry-run reported scanned 422 / would-retire 321 / skipped-live 101, nothing written.
⚠️ Backpressure check: `daily_video.open_review_count` counts `video_ad_cycle`, NOT `content_approval` — measured on prod jiya=1, Kamal dar=1, leadgenai-self=4 against `DAILY_VIDEO_MAX_PENDING=2`. So the paying customer is **not** blocked by this backlog; only own-brand would be.
Label: DIRECT_HOST_VERIFIED (2026-08-09) | CODE-PRESENT (PR #297, not deployed)

## Daily video — diagnosis + new producer (2026-08-09)
Prod `/health` re-probed 2026-08-09 = **`3cd95ba2`**, equal to `origin/main` (the `33651cfc` / `084cd990` values elsewhere in these docs are stale).
Owner report "daily videos not set up, advanced not running, old not running" — probed, all three had different causes:
- **Old (classic) path DOES run** but at `VIDEO_AD_INTERVAL_DAYS` unset → **5 days**, and generation landed 2026-07-22 then not again until 2026-08-06 (**15-day gap**). **Cause of the gap = a dead gate, NOT budget starvation** (an earlier draft of this entry claimed starvation — corrected per CAUSAL-CLAIM DISCIPLINE): `git log -S` shows `1664811e` (2026-08-05) taught `video_ad_cycle.enabled()` to honour the `VIDEO_DAILY_SCHEDULER_ENABLED` alias — prod had the cell flag ON while `VIDEO_AD_CYCLE` was OFF, leaving `run_cycle` fully inert. Generation resumed the next run (08-06). Corroboration: prod `delivery_ledger` holds exactly 6 `video_*` events, **all 2026-08-06** — no render was attempted or failed during 08-02..05.
- **SEPARATE live hazard (real, but not this gap's cause):** `content` exceeded its 420s `CONTENT_TIME_BUDGET_S` on **15 consecutive daily runs** (2026-07-18 → 2026-08-01, 452–530s); `_run_content_engine` drops every engine behind the overrun **silently** (no exception, no log naming it). Runs are 32–262s since 08-02 so the window is closed — but nothing recorded it, and nothing prevented a recurrence. Now instrumented (below).
- **Advanced (Creative OS / HyperFrames) never ran**, three independent reasons: `CREATIVE_PROVIDER_HYPERFRAMES_ENABLED` **unset in prod**; the Node/Chrome toolchain exists only in the opt-in `Dockerfile.video` while `docker-compose.vps.yml` builds **all** services (incl. `worker-video`) from `Dockerfile.lock`; and Creative OS had **no scheduler producer at all** (API-enqueue-only). `CELERY_VIDEO_QUEUE` also unset → render tasks use the default queue, `worker-video` idle.
- **Review pile-up:** 32/39 video records stuck `pending`, only 4 ever published — generation had no backpressure.
Shipped (ADR-166): `app/marketing/daily_video.py` — own beat job `staff-daily-video-daily` 09:45 IST (never on the `content` chain), **enqueue-only**, engine `auto|advanced|classic`, fail-closed `DAILY_VIDEO_CLIENTS` allowlist, per-client open-review backpressure, day-level idempotency, and `run_cycle` cadence-ownership deferral so the 5-day loop cannot double-generate. Missing flags (`CREATIVE_PROVIDER_HYPERFRAMES_ENABLED`, `CREATIVE_HYPERFRAMES_CANARY_TENANTS`, `CELERY_VIDEO_QUEUE`, `VIDEO_AD_INTERVAL_DAYS`) added to `AUTOMATION_FLAGS`. Admin: `GET/POST /api/clientops/video-production/daily-status|daily-run`.
**Companion fix — silent engine-skips are now observable** (this was the systemic hole behind the whole class): `automation_health.record_engine_skip()` logs *before* persisting and records every engine a mega-job drops, via the `runtime_data_authority` resolver (a hardcoded `data/...` path would land in the LEGACY location — `data/job_heartbeats.json` is a stale leftover; live automation state is under `/var/lib/leadgen/runtime/automation/`). Surfaced as `health().engine_skips`, folded into `ok`/`status` (un-run work ≠ healthy), and rendered in the "Aaj" tab in Hinglish with a fix hint. 8 dedicated tests.
⚠️ **Rollout note:** the `run_cycle` deferral is per-client, so Stage 1 (one client) leaves inline ffmpeg running for the other ~16 clients inside the budgeted chain. `DAILY_VIDEO_CLIENTS=*` (Stage 2) is what actually retires the starvation hazard — not optional polish.
**Companion fix 2 — the CUSTOMER approval backlog is now owner-visible.** `_pending_decisions()` (the `needs_decision` number on the Aaj tab) reads `approvals_bridge`, which has **zero** reference to `content_approval` — so the queue that decides whether a generated video ever reaches a customer was counted by nothing. That is how 32/39 sat `pending` (only 4 ever published) while the page said sab theek. `today_overview` now reports count + oldest-age + per-type, kept SEPARATE from `needs_decision` (owner-decides vs customer-decides). Threshold 3 items OR 3 days. 6 tests.
Enable steps (owner, staged) = `docs/runbooks/RUNBOOK_DAILY_VIDEO.md`. All flags default OFF.
**PR #294** open (branch `freebuff/daily-posting-videos-...`), 5 commits, CI green except pre-existing non-required Gate A (ruff-format vs black conflict that already fails on untouched `main` files — proof + rationale in a PR comment; owned by WS-PRF1/#248).
Label: CODE-PRESENT | TEST-PROVEN (122 targeted tests + `prod_check` PASS) | LOCAL-ONLY (not committed/deployed); diagnosis = DIRECT_HOST_VERIFIED (2026-08-09)

## Sprint goal (LOCKED)
**GTM 0→1** — pehle paid customers on Marketing product; mid-funnel bottleneck (Hot Queue `/app/inbox` + dialer sprint); 2nd paying customer target.

## Production SHA — SUPERSEDED (historical, 2026-08-06)
> Current prod SHA lives in the `DEPLOYED 2026-08-09 — d1b106b2` section above. Everything in this
> section is the 2026-08-06 reading, kept only because the probe-discipline note below was learned
> here. Do **not** quote `b5fc2dea` as current.

`b5fc2dea` — was exact parity with `origin/main` as fetched on 2026-08-06.
`/health` = `{"status":"healthy","version":"b5fc2dea","environment":"production"}` (direct HTTPS, 2026-08-06 10:56 UTC, uptime 2h 35m).

**Prod and `origin/main` were in exact SHA parity ON 2026-08-06.** The `31169c78..b5fc2dea` delta was deployed by another authorized operator/session; this checkout did not perform that deployment.

**It was NOT deployed "since" the earlier report — it was already live when that report was written.** Uptime arithmetic: at 11:03:02 UTC uptime was `2h 42m 38s`, so the `b5fc2dea` container started ≈ **08:20 UTC**. The session that claimed "prod is 10 commits behind" did its work from ≈10:10 UTC — about **1.8 hours after** `b5fc2dea` was already serving. That claim was **false when asserted**, not overtaken by events. Root cause in the note below.
Previous deployed rollback reference: `31169c78` (confirm the canonical deploy rollback state on-host before using it).
Label: DIRECT_HOST_VERIFIED (2026-08-06) + GIT_VERIFIED (2026-08-06).

> **Correction chain:** this file has recorded prod as `33651cfc` → `31169c78` → `b5fc2dea` (2026-08-06) → `3cd95ba2` → `d1b106b2` (2026-08-09, current). Every one of those was "fresh truth" when written. Re-probe `/health` before quoting any SHA.

> 🚨 **HOW TO PROBE `/health` — the 2026-08-06 cached-probe trap.**
> An agent probed `/health` once via a fetch tool, got `31169c78`, and propagated "prod is 10 commits behind" into three context docs. The payload was **~6.5 hours stale**: it carried `timestamp` `03:37:42Z` and `uptime 1h 6m 28s` (a container started 02:31Z) while the wall clock was ≈10:10Z and the real container had been up since 08:20Z. A later identical fetch returned the **byte-identical** body — same timestamp, same uptime — which is the tell.
> **The origin is ruled out.** It correctly serves `cache-control: no-store, no-cache, must-revalidate, max-age=0` (header-verified 2026-08-06), and `curl` against the same origin returned live, advancing values. The stale copy therefore entered somewhere in the **fetch path** used by that probe. **Which component cached was never instrumented**, so no specific implementation is named here — asserting one would repeat the same unevidenced-cause mistake this note exists to prevent.
> **Rule:** probe with `curl` and a unique cache-buster —
> `curl -sS -H 'Cache-Control: no-cache' "https://leadsgenai.in/health?cb=$(date +%s)"`
> — and **sanity-check `timestamp`/`uptime` against the wall clock before believing `version`**. Two probes returning an identical `timestamp` means you are reading a cache, not production. One probe is never evidence.

## ⚠️ UPI auto-activate — documentation drift corrected 2026-08-12
Docs (CURRENT_STATE, CLAUDE.md, AGENTS.md) recorded `UPI_AUTO_ACTIVATE=0` as the 2026-07-18 containment state. **Prod `.env` actually has `UPI_AUTO_ACTIVATE=1`.** (Re-verified 2026-08-12 revenue audit.)
Containment is still effective — the master flag alone is never enough (`upi_payments.auto_activate_clients_allowed`): `UPI_AUTO_ACTIVATE_CLIENTS` holds exactly **one** client id, and both a random client and an empty client id are refused (probed). So this is ARMED-but-scoped, not open auto-activation.
Not changed by this session — flipping it is an owner money decision. Recorded so the next agent does not quote `=0` from docs.
Label: DIRECT_HOST_VERIFIED (2026-08-04 in-container probe + 2026-08-12 revenue audit)

## Origin/main — SUPERSEDED (historical, 2026-08-06)
`b5fc2dea` — was exact parity with production (`git fetch origin`, `git rev-parse origin/main`, and direct HTTPS `/health`, 2026-08-06). `origin/main` has since advanced well past this; re-derive it, do not quote this line.
Open issues: **#237** (`tests` workflow red on main — pydantic-core drift; `07bafd40` added a non-failing diagnostic, root cause still open).
Label: GIT_VERIFIED (2026-08-06, STALE)

## Production health — SUPERSEDED (historical, 2026-08-06)
`status: healthy`, `environment: production` at `b5fc2dea` (2026-08-06 10:56 UTC, direct HTTPS).
Public funnel smoke **re-run on deployed `b5fc2dea`** (2026-08-06 11:04 UTC, cache-busted `curl`): `/` `/pricing` `/start` `/audit` `/site-audit` `/demo` `/privacy` `/health/ready` — all **200**, with `/health` re-confirming `b5fc2dea` immediately after the sweep. (An earlier identical 8/8 sweep was recorded against `31169c78`; that reading is now superseded, see the cached-probe note above.)
Label: DIRECT_HOST_VERIFIED (2026-08-06)

## Sales Autopilot (live, REAL email — owner 2026-08-03 refill arm)
- `SALES_AUTOPILOT_ENABLED=1` · `DRY_RUN=0` · `EMAIL_ENABLED=1` · `WHATSAPP_ENABLED=0` · `REFILL=1` · `REFILL_CAP=25` · `REFILL_MIN_SCORE=0`.
- Manual refill 2026-08-03: upserted 25 `new` prospects (store was idle on Estique-only).
- **Cold** autopilot WhatsApp stays OFF (`SALES_AUTOPILOT_WHATSAPP_ENABLED=0`).
Label: DIRECT_HOST_VERIFIED (2026-08-03)

## Cold email outreach
`AUTO_EMAIL_OUTREACH=1` — LIVE. 2026-08-02 counts: 19 sent + 20 follow-ups.
Label: DIRECT_HOST_VERIFIED (2026-08-02)

## WAHA / WhatsApp — Swara interested follow-up ARMED
WAHA `default` = **WORKING** (`918261030181`, `leadsgenai.in`). Owner 2026-08-03: post-call WA ON for Swara-interested — `WHATSAPP_AUTO_SEND=1` · `POST_CALL_WHATSAPP=1` · `VOICE_CLOSE_WHATSAPP=1` · allowlist `*`. Cold prospect WA remains OFF. Backup `.env.bak-postcall-wa-20260803115342`.
Label: DIRECT_HOST_VERIFIED (2026-08-03 recreate + in-container env)

## Staging provenance
`docker-compose.staging.yml` ab **fail-CLOSED**: `APP_VERSION` mandatory (`${APP_VERSION:?...}`) — `:latest` refused (ADR-097, ISSUE-04). `check_skew.sh` watches `leadgen_app_staging`.
Label: CODE-PRESENT (2026-08-02)

## Calling / flag posture — read this before quoting any flag from this file
`platform_dial` = **FULL CAMPAIGN LIVE** (owner go-ahead 2026-08-02). **Naming trap:** `PLATFORM_DIAL_DAILY` = **boolean on/off** (prod `=1`); per-run cap = `PLATFORM_DIAL_LIMIT` (prod `=100`). Also: `VOICE_LAUNCH_KILL=0` · `DIAL_TEST_MODE=0` · `VOICE_DAILY_CALL_CAP=100`. LIVE proof: 3 real Vobiz calls 2026-08-02 (session `S20260802-a280d841`). Daily 11:30 IST auto-dial uses `PLATFORM_DIAL_LIMIT` (niche=all). Compliance spine UNTOUCHED. Rollback = `.env.bak-fullcampaign-20260802075851`. Docs previously mis-wrote `PLATFORM_DIAL_DAILY=100` — that was wrong wording, not a prod miss-set (re-proved 2026-08-03).
Label: DIRECT_HOST_VERIFIED (2026-08-03 in-container env + 2026-08-02 live call proof).

## Secret hygiene (owner action)
`GEMINI_API_KEY` historically leaked in bash_history (scrubbed 2026-08-03). **Owner chose not to rotate** — voice primary moved off Gemini onto free stack (`VOICE_GEMINI_PRIMARY=0`, runtime `voice_primary=false`, `GEMINI_TTS=0`). Live smoke: `free_ai.chat` → **mistral**. Optional: still revoke burned Gemini key in Google console when convenient.
Label: DIRECT_HOST_VERIFIED (2026-08-03 free-AI switch + chat smoke).

## Migration
No pending migration on the deployed release path. `008` is NOT the head — it is one revision in the 008..022 chain.
Label: PRODUCTION-PROVEN (no migration introduced by the current release lineage)

## Routes
0 route collisions on deployed release path (prod_check gate green; current session shipped additive frontend/middleware changes only — no new routes).
Label: PRODUCTION-PROVEN

## Deployment architecture (hardened path - PRODUCTION-PROVEN)
The proven canonical deployment path is:

```
GitHub Actions
  -> leadgen-deploy (dedicated SSH user, VPS_DEPLOY_USER; NOT root, no docker group)
  -> VPS_SSH_KEY_DEPLOY (dedicated ed25519 key)
  -> root-owned /usr/local/sbin/leadgen-deploy-release wrapper (scoped NOPASSWD sudo, strict 40-hex SHA validation, flock)
  -> immutable exact-SHA anonymous GHCR pull (no docker login, no registry secret)
  -> docker compose (celery profile) up
  -> alembic upgrade head (hard-gated)
  -> /health/ready gate
  -> automatic rollback to the previously-running immutable image on migration or health failure
```

- The old root-based GitHub deploy path is retired. `GHCR_PAT` is retired; the registry package is public and pulled anonymously by exact SHA.
- The emergency root key is retained OUTSIDE GitHub (operator machine / VPS recovery) for break-glass only.
- `DEPLOY_ENABLED` defaults unset (off); a push to `main` runs the gate job only. Deploy requires operator-set `DEPLOY_ENABLED=true` + `workflow_dispatch`.
- Emergency/canonical VPS path also includes `scripts/deploy_vps.sh` with mandatory `APP_VERSION=<sha>`.
Label: PRODUCTION-PROVEN

## Secret state (GitHub Actions)
Retained: `VPS_HOST`, `VPS_DEPLOY_USER`, `VPS_SSH_KEY_DEPLOY`.
Retired (deleted from GitHub Actions after the proven hardened run): `GHCR_PAT`, `VPS_USER`, `VPS_SSH_KEY`.
Emergency root key remains outside GitHub for operator recovery. (Names/state only; no values recorded.)
Label: PRODUCTION-PROVEN

## Skill architecture (canonical registry - CODE-PRESENT on main via PR #106 / ADR-131)
`.claude/skills` is the single canonical tracked skill root; `.agents/skills` is removed.
- Decision record: ADR-131 (`docs/adr/ADR-131-canonical-skill-registry.md`).
- Duplicate-regression CI guard: `tests/test_skill_tree_canonical_guard.py`.
Label: CODE-PRESENT

## OpenClaw
Stage A ON (`OPENCLAW_ENABLED=1`). Admin Dashboard `#openclawAdminCard` LIVE. GREEN-only allowlist; AMBER rejected in Stage A; RED refuse intact; `OPENCLAW_ALLOW_RED_ACTIONS=0`; Owner OS sole authority. Workforce stays **31 agents**.
Label: PRODUCTION-PROVEN (Stage A shipped PR #105) — re-probe env before acting on flags.

## Agent workforce
Canonical workforce remains **31 agents**. OpenClaw/Boss is Owner OS Copilot surface — **not** a 32nd agent.
ADR-164 adds a complete per-agent enterprise profile: agent+tenant-isolated memory/KB namespaces, eight common SaaS controls, role competencies and existing runtime governance. ADR-165 derives Boss → 7 domain teams → 30 workers from the canonical Office map, giving **31/31 coordination coverage** and visible mission assignments, handoffs and Boss verdicts in Owner OS/Coordination Hub. Coordination-ready remains setup truth: runtime is still **12 canary-ready / 17 rollout-hold / 2 intentionally disabled**; `AGENT_MATURITY_CONTEXT` and Coordination Hub flags default OFF.
Label: CODE-PRESENT | TEST-PROVEN | LOCAL-ONLY (not committed/deployed)

## Paying customers
1 - Jiya Makeover (`jiya-makeover`). MRR ₹1,999. Estique autopilot prospect `converted` (see WS-2 in ACTIVE_WORK).

## Admin manual customer call
`/app/admin` now has a prominent owner-only single-call form (phone + `ai_marketing` pitch + explicit transactional/promotional relation + confirmation). It reuses canonical `POST /api/telephony/vobiz/stream-call`; no second dialer route, no automatic retry, 60s same-number UI cooldown. Compliance remains backend fail-closed. Local evidence: 22 manual-call/Vobiz tests + 19 admin-nav tests green, `prod_check.py` PASS.
Label: CODE-PRESENT | TEST-PROVEN | LOCAL-ONLY (not committed/deployed)

## Top next actions
1. Review/commit/deploy admin manual-call slice only when owner asks; then admin-login canary.
2. GTM Hot Queue `/app/inbox` → 2nd paying Marketing customer.
3. Feed sales_autopilot new non-converted prospects (or accept idle until new leads).
