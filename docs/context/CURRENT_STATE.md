# CURRENT_STATE - LeadGen AI (operational truth)

Evidence labels: PRODUCTION-PROVEN | CODE-PRESENT | TEST-PROVEN | LOCAL-ONLY | PARTIAL | STALE | UNKNOWN | DIRECT_HOST_VERIFIED | GIT_VERIFIED | ASSUMED
(`DIRECT_HOST_VERIFIED` = probed from the live host at a stated time; `GIT_VERIFIED` = re-derivable from this repo; `ASSUMED` = carried forward, not re-checked.)

## Last verified timestamp
2026-07-28T02:40Z — `/health` re-probed over direct HTTPS (no browser).
**This file went 3 days un-re-verified, and was demonstrably WRONG for about 1 of them** — `441cf37a` stopped being the running build when `dd193a69` merged on 2026-07-27T04:30Z. Those are different durations; conflating them overstates the failure and understates the cause, which was not re-probing.

## Sprint goal (LOCKED)
**Automation-Max** — safe engines auto; human only for publish / money / dial / bulk WA.

## Automation-Max (flags proven 2026-07-25; ASSUMED since)
VPS `.env` SET: `OPS_WATCHDOG=1` · `CADENCE_ENGINE=1` · `JOURNEY_ENGINE=1` · `APPROVAL_EMAIL_NOTIFY=1`.
Cold email NOT enabled. NEVER untouched: WA auto-send · platform_dial · reply-auto-send · sales-autopilot.
Script: `scripts/vps_enable_automation_max_flags.py` (ADR-097 pin-safe recreate).
Backup: `/opt/leadgen/.env.bak_automation_max`
Mission Control Band list: only `AUTO_EMAIL_OUTREACH` remains OFF (by design).
Label: **ASSUMED** — these `.env` values were proven on 2026-07-25 and NOT re-probed on 2026-07-28. See "Calling / flag posture" below.

> **Read this section before trusting any SHA elsewhere in the repo.** On
> 2026-07-25 an agent used a stale local `origin/main` ref and concluded PR #125
> was unmerged when it had in fact already shipped to production. Always
> `git fetch` and re-probe `/health` rather than trusting a checked-in number.

## Production SHA
`dd193a69` — merge commit of PR #147 (External Agent Runner v1), merged 2026-07-27.
Observed 2026-07-28T02:40:07Z: `GET https://leadsgenai.in/health` over direct HTTPS from a non-browser client returns `{"version":"dd193a69","environment":"production","status":"healthy"}`.
Previous entry in this file said `441cf37a`, which stopped being true when `dd193a69` merged (2026-07-27T04:30Z). **`441cf37a` is NOT the running build.** Rollback reference is now `dd193a69` itself until the next deploy.
Per-container `APP_VERSION` across the five app-image services was NOT re-checked this session — do not restate the old "zero skew" claim without probing.
Label: DIRECT_HOST_VERIFIED (2026-07-28T02:40:07Z, direct HTTPS, no browser cache in path)

> **Verify this the same way.** Loading `/health` in Chrome on 2026-07-28 returned a
> FIVE-DAY-OLD cached body (`47d2fe3c`, uptime frozen at `0h 9m 10s`) and silently
> stripped the cache-busting query string — a service worker answering from cache.
> That is the most likely reason a wrong SHA survived in this file for days.
> Use `curl` or any non-browser client. Never a browser tab.

## Origin/main
`6a504321` — merge of PR #160 (`feat/runtime-data-a1-telephony`). **NOT equal to production.**
`dd193a69` is a direct ancestor of main: main is ahead, production holds zero commits main lacks. Re-derive the exact gap rather than trusting a number written here:
`git fetch origin && git rev-list --count dd193a69..origin/main`
Label: GIT_VERIFIED (2026-07-28)

## Production health
`status: healthy`, `environment: production` at `dd193a69` (2026-07-28T02:40:07Z, direct HTTPS).
**Unresolved observation:** two probes 76 seconds apart returned uptimes of `22h 28m` and `1h 43m` at the same version. The straightforward reading is per-process uptime under `WEB_CONCURRENCY=2`, which would mean one of the two workers has a start time ~1h43m before the probe. Why is unknown — container/worker logs were not inspected. This repo has had restart-storm prod-downs before, so treat it as an open item, not as proven-benign and not as a proven incident.
Container/soak numbers from the 2026-07-25 deploy are NOT restated here because they were not re-measured.
Label: PARTIAL (health DIRECT_HOST_VERIFIED; worker restart UNKNOWN)

## Newly-live-but-inert (shipped 2026-07-25, never previously run in prod)
**CORRECTED 2026-07-31T05:41Z — two claims below were WRONG, re-probed directly in the running containers.** The engine is no longer "gated OFF at the master gate"; it is **armed in simulation**, which is a different posture with the same customer-facing effect (no sends). Both readings come from `docker exec leadgen_{app,scheduler} printenv`, not from `/health` — `/health` still returns no feature flags and can never confirm one.
- `SALES_AUTOPILOT_ENABLED` — **`=1` in BOTH `app` and `scheduler`**, NOT unset. The old line said "unset → engine fully inert"; that is false as of this probe. Master gate is `app/api/automation_flags.py:378`. Consistent with PR #194's safe-launch canary lane.
- `sales_autopilot` in `RUN_DUE_EXCLUDE` — **also false: `RUN_DUE_EXCLUDE` is unset** in `app`.
- **What actually keeps it safe** (all DIRECT_HOST_VERIFIED at the same timestamp): `SALES_AUTOPILOT_DRY_RUN=1` · `SALES_AUTOPILOT_WHATSAPP_ENABLED=0` · `SALES_AUTOPILOT_EMAIL_ENABLED=0` · `SALES_AUTOPILOT_CANARY_BATCH=1` · `AUTO_EMAIL_OUTREACH=0`. So it simulates and does not send.
- `WHATSAPP_AUTO_SEND=0`, `PLATFORM_DIAL_DAILY=0` (calling HARD OFF), `UPI_AUTO_ACTIVATE=0` — re-probed, all still correct.
- **Zero** autopilot lines in 24h of `leadgen_scheduler` logs — behavioural corroboration that simulation is not producing sends.
Do NOT treat these as live customer capabilities. Label: **DIRECT_HOST_VERIFIED (2026-07-31T05:41Z)** — supersedes the 2026-07-25 ASSUMED reading. Re-probe the container env before acting on any of these; do not quote this block after another deploy without re-probing.

## Calling / flag posture — read this before quoting any flag from this file
Every flag value in this document was probed on 2026-07-25, not on 2026-07-28. `/health` exposes version, environment, status and uptime only, so a `/health` probe can never confirm one. Treat all of them as **ASSUMED** and re-probe the container env before acting on one. Nothing in this session's changes altered a flag.

## Migration
The `510ed7bc` Video Review Stage 3 deploy completed its hard-gated transactional Alembic step successfully; OpenClaw Admin `7cab5f60` introduced no migration.
(Note: `008` is NOT the head - it is one revision in the 008..022 chain.)
Label: PRODUCTION-PROVEN

## Routes
0 route collisions on deployed release path (prod_check gate historically green on `510ed7bc`; OpenClaw Admin ship was exact-4-file additive).
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
- Counts in older notes (208/181/389) are historical snapshots — re-measure before asserting live VPS skill totals.
Label: CODE-PRESENT on `origin/main` (not independently re-proven on prod image `7cab5f60`)

## OpenClaw
Stage A ON (`OPENCLAW_ENABLED=1`). Admin Dashboard `#openclawAdminCard` LIVE. GREEN-only allowlist; AMBER rejected in Stage A; RED refuse intact for matched phrases (`calling enable`); `OPENCLAW_ALLOW_RED_ACTIONS=0`; Gateway token EMPTY (browser super-admin path). Owner OS sole authority.
Label: **ASSUMED** — proven on the older image `7cab5f60`, not on the currently observed build `dd193a69`, and NOT re-probed on 2026-07-28. (`7cab5f60` is a verified git ancestor of `dd193a69`; how many DEPLOYS separate them is not derivable from this repo — deploys are not tagged — so no count is asserted.) See "Calling / flag posture" above.

## Calling
HARD OFF. `PLATFORM_DIAL_DAILY=0`. Unchanged by OpenClaw Admin deploy.
Label: **ASSUMED** — last probed 2026-07-25 on the older image `7cab5f60`, not on the currently observed build `dd193a69`; NOT re-probed on 2026-07-28. The §5 mandate that calling stays HARD OFF is unchanged and unconditional; what is unverified is only whether the host still *matches* it. Re-probe the container env before any action that depends on the flag, and treat a mismatch as an incident rather than as permission.

## Agent workforce
Canonical workforce remains **31 agents**. OpenClaw/Boss is Owner OS Copilot surface — **not** a 32nd agent.
Label: CODE-PRESENT (registry) | PRODUCTION-PROVEN (OpenClaw Stage A does not expand workforce count)

## Obsidian nightly cron
Host cron `45 20 * * *` → `/opt/leadgen/scripts/obsidian_host_push.sh` (20:45 UTC / 02:15 IST). Log: `/var/log/leadgen_obsidian.log`.
- **2026-07-24 20:45 UTC run:** `NOT_YET_OCCURRED` (VPS clock was still ~03:18Z during review).
- **Through 2026-07-23 20:45 UTC:** `PROVEN_FAILURE` (`fetch first` push rejects).
- Host script now includes fetch+merge self-heal (file mtime 2026-07-23 21:43Z, after that night's failure). Tonight is the first scheduled chance to prove success — do not claim PROVEN_SUCCESS yet.
Label: PARTIAL (schedule+history proven; next run pending)

## Deployment gate
`DEPLOY_ENABLED` disarmed (unset/false). No deploy performed during 2026-07-24 docs PR #112 review/merge.

## Repository cleanliness
Primary worktree `feat/openclaw-admin-dashboard` was dirty (docs/ledger/temps/staged video regression). Triage ports docs via isolated `docs/canonical-handoff-20260724`; video regression file classified superseded by `tests/test_video_production_auth_ui.py`; customer ledger runtime append restored; `_tmp_*` disposable.

## Paying customers
1 - Jiya Makeover (`jiya-makeover`)

## Working customer workflows
- OpenClaw Admin / Owner Copilot Stage A — LIVE on production `7cab5f60` (PR #105)
- Delivery assurance / identity - unchanged
- Video Review Stage 3 code - deployed at `510ed7bc` (still in ancestry of prod); customer cohort gate remains OFF pending authenticated Jiya canary

## Top next actions
1. Stage B AMBER production approvals — design only; do not enable.
2. Owner login → enable only `VIDEO_CUSTOMER_REVIEW_ENABLED=1` + `VIDEO_CUSTOMER_REVIEW_CLIENTS=jiya-makeover`; authenticated read-only Jiya Preview canary.
3. GTM Hot Queue `/app/inbox` → 2nd paying Marketing customer. Keep WhatsApp review/publish/scheduler/platform_dial OFF.
