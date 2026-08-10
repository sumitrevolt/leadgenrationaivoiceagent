# SESSION_HANDOFF — 2026-08-10 (Cursor: deploy a3fbc8bb + cleanup)

## Done this session
- **OWNER-AUTHORIZED deploy** of `a3fbc8bb` (`a3fbc8bb33187f8d5d9eb1489f1acc3b698fef64`) via canonical `scripts/deploy_vps.sh`
- Confirmed pre-ship: `git fetch` → `origin/main` tip **still** `a3fbc8bb` (includes #320); no newer tip
- Kill-fence: backup `.env.bak-deploy-a3fbc8bb-20260810_170100` → `VOICE_LAUNCH_KILL=1` → recreate on prior SHA → deploy → restore from backup → recreate with `APP_VERSION=a3fbc8bb`
- **`.env` md5 equal backup:** `ec9db158d99269cc463e97923970b50f` (no secret values logged)
- Post-restore: all 5 app-image containers `kill=OFF` + `APP_VERSION=a3fbc8bb`
- #304: deploy-evidence comment added; **left OPEN** (bind money-path not proven without admin secrets)
  - https://github.com/sumitrevolt/leadgenrationaivoiceagent/issues/304#issuecomment-5243541691

## origin/main tip / prod
- `origin/main` = `a3fbc8bb33187f8d5d9eb1489f1acc3b698fef64`
- Prod `/health` = **`a3fbc8bb`** · `environment=production` · `status=healthy` (cache-busted curl ~17:14 UTC)
- Prior prod was `76348926`; rollback ref = that SHA / image tag if needed
- Smoke: `/` `/pricing` `/health/ready` → **200**
- Queues post-restore: `celery=0` · `dlq:failed_tasks=0` · `dlq:dead=15` (not cleared; do not attribute solely to this deploy without baseline)

## Cleanup taken
- `git worktree prune` (no stale prunable entries beyond broken canary)
- Removed broken locked worktree `/tmp/canaryverify` (path missing on Windows)
- `git fetch --prune`
- Deleted **19** fully-merged local branches (no worktree attached); skipped worktree-linked / unmerged
- Stashes: **27 kept** (not dropped — may contain WIP/security-sensitive)
- VPS: deploy retention already removed old app tags; `disk_reclaim.sh` run (safe: no `-f`, no volumes) → **RECLAIM_DONE**
- Disk: before 48%/103G free → after **39%/118G free**; KEEP tag `a3fbc8bb` only; prod health still `a3fbc8bb`

## Leftovers still present (DO NOT mass-delete)
- Many `Documents/leadgen-*` worktrees still registered (admin/ssrf/buzz/pytest9/voice mega-branch etc.)
- `.freebuff/worktrees/*` several dirs still present (non-empty; left alone)
- Locked worktrees remain (e.g. codeql path containment, admin-harden) — owner/tool must unlock
- Divergent voice / rescue remotes untouched (per instruction)

## Still open / leftover
- #304 OPEN until guest→bind→approve money-path proof
- WS-SEC1 Vobiz rotate still owner-blocked
- WS-GTM1 2nd paid customer still revenue-pending

## Do not
- Close #304 without bind-path proof
- Force-push / reset --hard / secrets in chat
- Mass-delete worktrees/stashes without owner review
