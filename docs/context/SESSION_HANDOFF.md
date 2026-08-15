# SESSION_HANDOFF — 2026-08-15 (Cursor: merge leftover trees/branches + cleanup)

## Status
**Git cleanup DONE. Live deploy NOT DONE from this sandbox.** Unique leftover product work is on `origin/main` = `07870e89`. Prod still `91958c23`. No extra GitHub heads. No open PRs. Swara/voice untouched. No flag arm.

## Evidence
- This VM worktrees: `/workspace` only (no extra git worktrees). Local branches after cleanup: `main` + this handoff branch.
- GitHub heads after prune: **`main` only** (`07870e89d925d2349b0e751eb9294e40231c3b0e`).
- Merged this session: PR **#369** `6dd4ace0` (CI lanes) · PR **#371** `07870e89` (HQ auto-chase + explorer; supersedes #370).
- Closed without merge: PR **#370** (already closed) · PR **#367** (ghost; head branch already deleted).
- Deleted leftover remote `cursor/ci-dsh-lane-speed-20260815` — CI tree **bit-identical** to #369 `6dd4ace0`; merging it would rewind later main (hq_auto_chase etc.).
- Not merged (harmful / stale, already deleted earlier): `fix/customer-auth-test-shims-20260812` (global `require_customer` override).
- Isolated Cursor cloud-agent VMs: 16 IDLE + this RUNNING. Their GitHub branches are already gone/squash-merged. Cannot merge another VM's unpushed worktree from here.
- Prod `/health` dual probe 13:58:36Z / 13:58:39Z: `healthy` · `environment:production` · `version:91958c23` · uptime 16h14m9s → 16h14m13s (DIRECT_HOST_VERIFIED).
- `deploy-vps.yml` run 31888501593 for `07870e89`: Gate SUCCESS · pytest shards skipped · Build skipped · Deploy skipped (`DEPLOY_ENABLED` not true).
- SSH `root@72.61.245.204`: no private key in this sandbox (`~/.ssh` = `known_hosts` only). Desktop Commander MCP `needsAuth`.

## Undeployed on live (owner VPS only)
`07870e89` vs live `91958c23` includes: #364 docs · #365 funnel · #366 next42 · #368 Hot Queue `callflag:` + renewal guard + DSH worker lock + Sentry unmask · #369 CI (runtime no-op) · #371 `hq_auto_chase` **INERT**.

Canonical: kill fence then `cd /opt/leadgen && setsid nohup bash scripts/deploy_vps.sh > /tmp/dep.log 2>&1 &` — runbook `docs/gtm/OWNER_DEPLOY_920a3e62.md`. Recreate MUST `APP_VERSION=<sha>` (ADR-097). Deploy **current `origin/main`** after fetch (minimum product SHA `07870e89`; later docs-only squash may move the tip). Rollback `ROLLBACK_TAG=c4fc0087` (re-probe before use).

## Do not
Cold WA · GSC without creds · HARNESS_SESSION_EVENTS · `DSH_AGENT_ALLOWLIST=*` · arm `HQ_AUTO_CHASE` / `CONTENT_APPROVAL_SWEEP_LIVE` · flush `dlq:dead` · raise `WEB_CONCURRENCY` · fake paid_today · Swara/voice edits · `git add -A` · VPS `reset --hard` · merge leftover CI branch that is behind main.

## Next (owner)
1. `/app/inbox` 15–30 min + UPI Bind/Re-Approve **if bank credit real**.
2. Deploy current `origin/main` (min `07870e89`) from a host that has VPS SSH (not this cloud agent).
3. Optional Boss harness start (not sandbox).
