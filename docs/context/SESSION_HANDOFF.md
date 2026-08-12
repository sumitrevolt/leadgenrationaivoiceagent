# SESSION_HANDOFF — 2026-08-12 (Cursor: worktree/branch consolidation)

## Status
**CONSOLIDATION PARTIAL** — Phase 0 inventory + Phase 1 UPI restore done. Phase 2–4 (unique Draft PRs / remote deletes / worktree remove) in progress or next.

## Facts
- `origin/main` = `23ea2d46` (includes #333 `76064942` + #334 docs)
- Open PRs: Dependabot #322–#328 only (untouched)
- Evidence: `docs/evidence/WORKTREE_BRANCH_CONSOLIDATION_20260812.md`
- Dirty “UPI WIP” was **truncation** of `bind_client` — restored from git; **not** parked as feature branch
- Buzz canary scratch moved to `_scratch/buzz_canary_20260812/`

## Do not
- Blind-merge all old branches into main
- Deploy / arm `STAFF_BUS_ENABLED` / `GSC_ENABLED`
- Mass-merge Dependabot in this packet
- Force-push main

## Next
1. Merge inventory docs PR (if open)
2. Delete A_MERGED remotes listed in evidence
3. Draft-PR residual C_UNIQUE_KEEP (or reclassify E_OBSOLETE with evidence)
4. `git worktree remove` clean merged worktrees; fix stale `leadgen-pii-containment` “main”
5. Primary checkout on clean `main`
