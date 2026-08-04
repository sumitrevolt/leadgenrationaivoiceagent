# SESSION_HANDOFF - ship both worktrees → main → deploy

## Session objective
Merge Cursor worktrees (blueprint PR #231 + docs-ops-truth) into `main` and deploy once via `deploy_vps.sh`.

## Isolation / branches
- Worktree ship: `C:\Users\Ratanshila\Documents\leadgen-wt-blueprint-2026-08-03` · `cursor/master-blueprint-world-class-2026-08-03`
- Docs branch merged in: `cursor/docs-ops-truth-buzz-freeai` @ `fc859bf`
- Primary checkout may still sit on docs branch + untracked `opencode.jsonc` (leave untracked)

## Done this session
1. Inquiry HQ bridge idempotency keyed on inquiry `at` day (CI flake fix) — commit on blueprint
2. Docs-ops merge into blueprint ship unit (CLAUDE/AGENTS ops truth, Buzz plane doc, free-AI voice notes)
3. PR #231 marked ready for review

## Production-proven earlier (still true until this deploy)
- Prod `/health` was `303b061f` pre-this-ship
- Voice LLM free-stack primary (`VOICE_GEMINI_PRIMARY=0`); cold WA OFF; post-call WA armed
- Calling campaign flags per CLAUDE Current State — deploy cycle still needs `VOICE_LAUNCH_KILL=1` gate then restore

## Owner next after deploy evidence
1. Prove `/health.version` == deployed SHA · 5 app-image services no skew
2. Estique → real ₹1999 before PAID
3. Optional: Hot Queue /inbox Operator truth bar smoke as admin

## Do not
Mass-enable automation flags · Dependabot mega-merge without review · fabricate Estique PAID · touch Swara brain
