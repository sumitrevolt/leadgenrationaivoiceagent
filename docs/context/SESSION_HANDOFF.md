# SESSION_HANDOFF — 2026-08-08 setup FROZEN · execution = Windows owner

## Source boundary
- Branch: `cursor/claude-agent-teams-worktrees-63d4` · PR #283 · tip `437d26fa`
- Reviewer: no open findings (seeder refuse-path R1 false-positive cleared; prediction Observed fields complete)

## Status
| Label | Status |
|-------|--------|
| Setup | **FROZEN / GO** — do not add more scaffolding unless live run breaks |
| **CLAUDE-CODE-AGENT-TEAMS-CANARY** | **NOT-RUN** — owner execution only |
| **#283 merge** | **BLOCKED until** Observed filled (or `p1_validity=contaminated` recorded) |

## Owner execution only (this agent cannot paste Claude Code AT)
1. `git worktree prune`
2. Confirm `#283` unmerged; main lacks C1 doc+contract
3. P2 baseline (plan_tier + usage note + clock_start)
4. Paste `docs/coordination/CANARY_LEAD_PROMPT.md`
5. Fill Observed in `docs/coordination/C1_CLAUDE_AT_PREDICTION.md` (`base_ref`, `p1_validity`, signal, burn delta)
6. **Then** merge #283

Signal fire = answer, not failure. Contaminated base = no P1 conclusion.
