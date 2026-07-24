# CURRENT_STATE - LeadGen AI (operational truth)

Evidence labels: PRODUCTION-PROVEN | CODE-PRESENT | TEST-PROVEN | LOCAL-ONLY | PARTIAL | STALE | UNKNOWN

## Last verified timestamp
2026-07-24T03:15Z (production running `7cab5f60`, verified via public `/health`).

## Production SHA
`7cab5f60` (`7cab5f609846e2c584edb8322dc684378a15e995`) — OpenClaw Admin Dashboard PR #105 merge; PRODUCTION-PROVEN via `scripts/deploy_vps.sh`.
Previous runtime SHA: `7f37522e` (rollback reference; not used).
Label: PRODUCTION-PROVEN

## Origin/main
`216ad5c1b47272684207dbeaf4ce368b7493eca9` — ahead of production. Includes merged PRs #105–#111 (OpenClaw Admin, Obsidian self-heal, dist-cancel/Nikhil proofs, runtime flag separation, OmniRoute governance, skill canonical index / ADR-131).
**Do not claim these post-#105 merges are live unless `/health.version` matches.** Production remains `7cab5f60`.
Label: CODE-PRESENT (main ahead of prod)

## Production health
`/health` 200 at exact `7cab5f60`; environment `production`; status `healthy` (re-probed 2026-07-24T03:15Z).
Label: PRODUCTION-PROVEN

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
