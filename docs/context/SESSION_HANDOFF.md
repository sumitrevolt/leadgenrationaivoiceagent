# SESSION_HANDOFF — 2026-08-08 C1 pre-flight fixes · CANARY-NOT-RUN

## Source boundary
- Branch: `cursor/claude-agent-teams-worktrees-63d4` · PR #283
- Reviewed tip was `5992b32c`; this commit adds F1–F7 hygiene before live canary.
- Live Agent Teams canary: **CANARY-NOT-RUN**.

## Review kill-facts addressed
- **F1** `canary_frozen.py check --base … --head HEAD` (exit 2 on frozen touch) + pass_rule
- **F2** scaffolding test no longer pastes frozen path strings (render round-trip instead)
- **F3** `.env*` moved to `frozen_classes` (gitignore → not diff-gateable)
- **F4** lead prompt: TM2 fail-not-skip; lead verify requires **0 skipped**
- **F5** `create --canary` requires `--teammate 1|2`
- **F6** remove keeps branch by default; `--delete-branch` opt-in (no silent `-D`)
- **F7** quota fields honest (no fake per-tm token requirement)

## Still for live canary
- TM1 → doc (merge first) · TM2 → contract test (merge second; RED in own wt expected)
- Lead: check each branch → merge TM1→TM2 → verify + 0 skipped → quota note

## Evidence labels
| Label | Status |
|-------|--------|
| **SCAFFOLDING-EVIDENCE** | Helper/SSOT/check tests green after this commit — SETUP only |
| **CANARY-NOT-RUN** | Current |
| **CANARY-PASS** | Forbidden until live C1 under pass_rule |
