# CURRENT_STATE - LeadGen AI (operational truth)

Evidence labels: PRODUCTION-PROVEN | CODE-PRESENT | TEST-PROVEN | LOCAL-ONLY | PARTIAL | STALE | UNKNOWN

## Last verified timestamp
2026-07-25T10:34Z (Automation-Max safe flags LIVE on prod; `/health`=`441cf37a` after `:latest` skew self-heal).

## Sprint goal (LOCKED)
**Automation-Max** — safe engines auto; human only for publish / money / dial / bulk WA.

## Automation-Max (PRODUCTION-PROVEN 2026-07-25)
VPS `.env` SET: `OPS_WATCHDOG=1` · `CADENCE_ENGINE=1` · `JOURNEY_ENGINE=1` · `APPROVAL_EMAIL_NOTIFY=1`.
Cold email NOT enabled. NEVER untouched: WA auto-send · platform_dial · reply-auto-send · sales-autopilot.
Script: `scripts/vps_enable_automation_max_flags.py` (ADR-097 pin-safe recreate).
Backup: `/opt/leadgen/.env.bak_automation_max`
Mission Control Band list: only `AUTO_EMAIL_OUTREACH` remains OFF (by design).
Label: PRODUCTION-PROVEN

> **Read this section before trusting any SHA elsewhere in the repo.** On
> 2026-07-25 an agent used a stale local `origin/main` ref and concluded PR #125
> was unmerged when it had in fact already shipped to production. Always
> `git fetch` and re-probe `/health` rather than trusting a checked-in number.

## Production SHA
`441cf37a` (`441cf37a109f1a7a51c60dd96032c8251ca647f6`) — blueprint detail-import PR #133 merge; PRODUCTION-PROVEN via `scripts/deploy_vps.sh` (2026-07-25T09:27Z).
Previous runtime SHA: `d114f942` (Master Blueprint PR #125 squash merge) — rollback reference.
Verified: on-box `127.0.0.1:8000/health` and `https://leadsgenai.in/health` both report `441cf37a`.
Zero version skew — all five app-image services (`app`, `worker`, `scheduler`, `worker-heavy`, `worker-video`) run `APP_VERSION=441cf37a` on image `:441cf37a`.
Label: PRODUCTION-PROVEN

## Origin/main
`441cf37a` — **equal to production** as of this deploy.
That deploy closed a ~21-commit backlog (`d114f942..441cf37a`, 102 files, +11,069/−279): the pydantic-core lock repair (#129), Master Blueprint v4 hierarchy/harness/reconcilers (#128, #130, #131, #132, #133), the autonomous sales engine (#124), Creative OS Phase-1 (#116), entitlement-assurance admin API (#121) and an OmniRoute governor change (#113).
Label: PRODUCTION-PROVEN

## Production health
`/health` 200 at exact `441cf37a`; environment `production`; status `healthy` (re-probed 2026-07-25T09:29Z).
Post-deploy soak: 33 containers running, 0 restarting/exited, all five redeployed services `healthy`, zero ERROR/Traceback in `app`/`worker`/`scheduler` logs, `celery` + `dlq:failed_tasks` + `dlq:dead` all 0.
Label: PRODUCTION-PROVEN

## Newly-live-but-inert (shipped 2026-07-25, never previously run in prod)
The autonomous sales engine and Creative OS Phase-1 are now ON DISK in production but gated OFF. Verified in the running containers:
- `SALES_AUTOPILOT_ENABLED` — **unset in both `app` and `scheduler`** → engine fully inert (master gate, `app/api/automation_flags.py:378`)
- `sales_autopilot` is in `RUN_DUE_EXCLUDE` → recovery never auto-enqueues it
- `WHATSAPP_AUTO_SEND=0`, `PLATFORM_DIAL_DAILY=0` (calling HARD OFF)
- Zero autopilot activity in scheduler/worker logs since deploy
Do NOT treat these as live capabilities. Label: CODE-PRESENT (inert)

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
Stage A ON (`OPENCLAW_ENABLED=1` on production `7cab5f60`). Admin Dashboard `#openclawAdminCard` LIVE. GREEN-only allowlist; AMBER rejected in Stage A; RED refuse intact for matched phrases (`calling enable`); `OPENCLAW_ALLOW_RED_ACTIONS=0`; Gateway token EMPTY (browser super-admin path). Owner OS sole authority.
Label: PRODUCTION-PROVEN (Stage A ON + Admin panel)

## Calling
HARD OFF. `PLATFORM_DIAL_DAILY=0`. Unchanged by OpenClaw Admin deploy.
Label: PRODUCTION-PROVEN

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
