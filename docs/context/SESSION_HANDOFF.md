# SESSION_HANDOFF — 2026-08-15 (Cursor: leftover local branches cleaned + AUTH-DEPLOY `963ee800`)

## Status
**DONE — leftover local branches cleaned, `origin/main` deployed.** Open PRs = 0 at deploy time. Prod `/health` = `963ee800` (DIRECT_HOST_VERIFIED). Kill fence closed (VLK FALSE_TOKEN 5/5). No DSH/runtime flags armed. Voice FROZEN. Swara untouched.

## Facts
- Leftover local feature branches were already squash-merged on GitHub (#354–#373). Re-merging them onto `main` would rewind later code, so they were deleted instead.
- Local `main` reset to `origin/main` `963ee800` (stale local SESSION_HANDOFF `cb289d61` discarded).
- Deleted local refs: archive-playbooks, ci-dsh-lane-speed, consolidate-revenue, dsh-deploy-inert, next42, paid-activations, revenue-blocker-p0, two freebuff leftovers. WIP freebuff commit was whitespace-only on an audit doc.
- Extra worktrees already gone; only primary checkout remains.
- Deploy SHA: `963ee8007dc9faf6aaf375fe02a79a7df952a67a`
- Kill fence: backup `.env.bak-killfence-20260815_150619` → `VOICE_LAUNCH_KILL=1` → `scripts/deploy_vps.sh 963ee800` → `=== DEPLOYED 963ee800 OK ===` (BUILD_RC=0 UP_RC=0) → VLK=0 + recreate with `APP_VERSION=963ee800`
- Prod `/health` HTTPS ×2: `963ee800` · `environment:production` · `healthy` (15:21:24Z uptime 0h4m55s → 15:21:27Z 0h4m57s). Host 15:22:37Z uptime 0h6m7s.
- Skew: 5/5 `APP_VERSION=963ee800` · VLK FALSE 5/5 · celery=0 · dlq:failed_tasks=0 · dlq:dead=24 (pre-existing trainer dead; do not flush)
- Inert in `leadgen_app`: DSH_RUNTIME/SHADOW FALSE · HARNESS_SESSION_EVENTS UNSET · AGENT_HARNESS UNSET · GSC UNSET · HQ_AUTO_CHASE UNSET · CONTENT_APPROVAL_SWEEP_LIVE UNSET · PLATFORM_DIAL_DAILY TRUE
- Rollback tag: `07870e89` (protected). Smoke: `/health` `/api/voice/niches` `/api/billing/plans` `/api/public/pay-info` = 200
- Activation still `payments_ready=true` · `blocker_count=1` · `ready_for_first_paid_customer=false` (owner UPI/inbox, not this deploy)

## Do not
- Arm `DSH_RUNTIME_ENABLED` / `DSH_SHADOW_ENABLED` / `HARNESS_SESSION_EVENTS` / `AGENT_HARNESS` / `GSC_ENABLED` / `HQ_AUTO_CHASE` / `CONTENT_APPROVAL_SWEEP_LIVE` / dunning flip / cold WA
- Start `--profile dsh` without separate owner auth
- Edit Voice/Swara · weaken DND/TRAI/DPDP
- Recreate without `APP_VERSION=<sha>` · `--remove-orphans` on postiz compose · VPS `reset --hard` · `git add -A` · flush `dlq:dead`

## Next
1. **OWNER — Hot Queue `/app/inbox`** 15–30 min + UPI Bind/Re-Approve if bank credit real
2. Optional Boss harness start (`buzz_start_harness.py --agent Boss`)
3. Then: Jiya referral kit, GSC creds (still OFF), B3 DKIM
