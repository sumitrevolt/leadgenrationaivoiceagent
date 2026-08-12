# SESSION_HANDOFF — 2026-08-12 (Cursor: PR queue land + freebuff cleanup)

## Status
**PR QUEUE LAND GO (PARTIAL only on orphans + Dependabot).** Docs/security residuals merged. Freebuff gitlinks gone (Gate A green). No deploy. No flag arm.

## Facts
- `origin/main` tip = **`94cc6e44`** (#343 SSRF test CodeQL silence; ancestry includes #340/#341/#336/#339/#342)
- Freebuff tracked placeholders: **0**
- Worktrees registered: **1** (primary `main` only)
- Closed obsolete: #338 buzz residual · #337 pytest9 (greenlet SIGSEGV exit-139)
- Dependabot #322–#328 untouched
- CP5 local WIP discarded (was `.venv-sec` / `.sec-scratch` junk)

## Do not
- Deploy / arm `STAFF_BUS_ENABLED` / `GSC_ENABLED` / `DUNNING` / `BOSS_DECISION_GOVERNANCE`
- Mass-merge Dependabot
- Force-merge greenlet/pytest9 tips

## Next (owner)
1. Hot Queue + UPI ops (revenue blockers — not code)
2. Dependabot packet separate
3. Manual delete orphan dirs when unlocked (boss-second-brain, buzz-multi-agent)
