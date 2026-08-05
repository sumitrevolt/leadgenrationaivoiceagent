# SESSION_HANDOFF.md — LeadGen AI (deploy verified · canary + UAT pending)

> Updated 2026-07-18 ~15:30 UTC. No secrets. Deploy + billing DONE & verified. Remaining = user/credential/telecom-gated (live canary, admin+customer browser UAT) + a BLOCKED git reconcile.

## VERDICT: CONDITIONAL GO
- **Deployment `f8a5f6e9`: GO** — verified live, healthy, no regression. Safe to remain in production.
- **Live outbound calling: HOLD (stays OFF)** — the 3 voice fixes are unit-test-verified but **NOT yet proven on a live call on f8a5f6e9** (no call has run on this SHA). Keep `platform_dial=false` (0 outbound). Only a controlled canary to the company/test number may proceed, then re-evaluate.
- **Approved calling cap: 0 automated outbound** (unchanged HARD-OFF, §5). Canary = 1 controlled call to company/test number ONLY. Do not raise until canary + admin evidence pass.

## Current production state (independently verified this session)
- External `https://leadsgenai.in/health` → version **`f8a5f6e9`**, healthy, environment=production.
- 5 app containers (app/worker/scheduler/worker_heavy/worker_video): running, **restarts=0, OOMKilled=false**, all APP_VERSION=f8a5f6e9.
- Postgres accepting connections; Redis PONG. Queues: celery=0, dlq:failed_tasks=0, **dlq:dead=0** (RESOLVED 15:5x UTC — 7 stale entries were all `prospect` SoftTimeLimitExceeded from 2026-07-17; time-budget fix now deployed + unit-tested `test_prospect_time_budget`, multiple successful prospect runs since with no new dead today; archived to `data/dlq_dead_archive_20260718.jsonl` then purged).

## Post-deploy triage (this session — production is clean)
- App + worker logs: no ERRORs in the last 60m (only Sentry-init INFO). Scheduled jobs flow_cron/growth/call_processor all `ok=true`. celery inflight=0.
- Prospect timeouts (the only real problem surfaced): historical, resolved. Fix (`app/platform/prospector.py` time budget) deployed in f8a5f6e9; DLQ archived + purged.
- Non-blocking follow-up: `test_voice_gemini_primary_flag` unset-default mismatch (prod flag=0 so behavior correct) — align code default or test in a future clean-worktree session (local worktree currently dirty with parallel WIP, do not touch).
- No active deploy process. **No active outbound dialer** (`platform_dial.json enabled:false`; no dialer process; `call_loop.log` is a STALE artifact from 2026-06-22, not current activity). §5 HARD-OFF mandate intact.
- Rollback target: `1803f819` (image retained).

## Tests (ran this session, host .venv vs deployed source)
~**132 passed, 1 failed**. Only failure = `test_voice_gemini_primary_flag` (unset-default env artifact; prod flag explicitly `=0` so behavior correct; not a deployed fix; non-blocking). All billing + 3 voice-fix tests passed.

## Billing (done — do NOT reopen)
ACTIVE=1 → INV/2026-27/0001 "jiya makeover" ₹1999 (real). VOIDED=12 → INV/0002–0013 (synthetic), append-only markers `by=operator-ops-plan-C` @15:16 UTC, audit reason recorded. Ledger stable 25 lines; backup `data/invoices.jsonl.bak-voidclose-20260718_151831`.

## ⛔ STILL OPEN — USER-gated (I cannot do these here)
### 1. Controlled Swara canary (no call has run on f8a5f6e9)
I cannot place a phone call, and §5 keeps `platform_dial` HARD-OFF. **Compliant path:** dial the **company number from an approved test handset (INBOUND auto-callback)** — this needs no gate change. (Do NOT re-enable outbound `platform_dial` for the canary.) Correlation label: `swara-canary-f8a5f6e9-<ts>`. During the call test: greeting word-boundary (say a sentence with "nahi/chahiye/rahi" → must NOT trigger canned pitch; also normal Hi/Namaste/Hello greetings), direct answers (₹1,999 plan contents, "publish without approval?", "call end karo"), barge-in, guard-reject → sensible `reply()` (not generic script), closing exactly once + no speech after close, correct termination reason. ≥12 turns.
Latency to capture from logs/telemetry: end-of-speech→STT-final, STT-final→first-LLM-token, first-token→first-audio, total→playback (flag any missing instrumentation, don't estimate).

### 2. Admin browser UAT (needs your password/OTP)
Log into `/app/office` (Operating HQ): canary call appears, recording playable, transcript visible + turns ordered, termination reason correct, duration plausible, no duplicate record, provider/model route + fallback events correct, billing shows only INV/0001 (INV/0002–0013 not payable), no critical banner. (Dashboard HTML shells return 200 post-deploy = routes intact.)

### 3. Jiya customer portal UAT (needs customer password/OTP)
Login as `jiya-makeover` (Starter ₹1,999): dashboard loads, plan shows ₹1,999, no synthetic invoices payable, deliverables visible + drafts marked as drafts, approvals tenant-scoped, no admin/other-tenant data, logout invalidates session.

## ⛔ BLOCKED — local Windows Git reconcile (do NOT force)
Live check contradicts the earlier "clean" assumption: local worktree is **DIRTY** (modified tracked files: app/api/customer_dashboard.py, app/api/growth.py, app/marketing/*, frontend/customer_dashboard.html, frontend/inbox.html, CLAUDE.md, progress.md, memory/*, tests/test_customer_marketing_tools.py …) + many untracked `_tmp_*`/`_canary_*` scripts. Checked-out branch = `fix/ci-lock-transitives` @ `c4faf9f8` (NOT main). `c4faf9f8` IS already an ancestor of origin/main `f8a5f6e9` → nothing unpushed at risk. **Reconcile deferred:** the uncommitted changes look like parallel-agent (Cursor/Codex) WIP — a rebase/checkout would fail or clobber them. USER must first decide what to do with those working-tree changes (commit/stash/discard per owner), THEN: `git checkout main && git pull --ff-only` (local `main` is at ce56240, behind 7 — will fast-forward once clean). Do NOT `reset --hard`/force.

## Exact next action (single highest priority)
USER: run the controlled INBOUND Swara canary on f8a5f6e9 (company/test number, platform_dial stays off), then verify recording+transcript in admin HQ. That is the only thing gating a full GO for calling.

## Next-session continuation prompt (copy-paste)
```
LeadGen AI final UAT. As of 2026-07-18 15:30 UTC: prod DEPLOYED+verified on f8a5f6e9 (rollback 1803f819); billing clean (INV/0001 active, INV/0002-0013 voided); tests 132/1 (the 1 = env-default artifact, non-blocking); no active dialer, platform_dial HARD-OFF intact. VERDICT=CONDITIONAL GO (deploy good; live calling on HOLD until canary). OPEN: (1) controlled INBOUND Swara canary on f8a5f6e9 via company/test number — verify greeting word-boundary, direct answers, barge-in, guard-reject→reply, close-once/no-post-close-speech, termination reason, + latency stages; (2) admin HQ browser check of recording/transcript/call-detail + billing; (3) Jiya portal tenant-isolation + ₹1999 plan check; (4) local Windows git reconcile is BLOCKED by dirty parallel-agent worktree (branch fix/ci-lock-transitives @ c4faf9f8) — user must resolve working-tree changes before `git checkout main && git pull --ff-only`. Cannot place calls or log in (credentials/telecom) autonomously. Read SESSION_HANDOFF.md + CLAUDE.md first. Do NOT re-enable platform_dial outbound; do NOT reopen billing.
```
