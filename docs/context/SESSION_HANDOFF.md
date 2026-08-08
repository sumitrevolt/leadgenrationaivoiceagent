# SESSION_HANDOFF — 2026-08-08 P1 confound locked · canary BEFORE #283 merge

## Source boundary
- Branch: `cursor/claude-agent-teams-worktrees-63d4` · PR #283 · tip ~`4c151bde`
- `origin/main` @ `5ae5a4b9` — C1 doc+contract **absent** (verified). P1 valid only if canary uses that clean base.

## Labels
| Label | Status |
|-------|--------|
| **PROTOCOL-PASS (Cursor)** | Done |
| **PREDICTION-LOCKED** | `docs/coordination/C1_CLAUDE_AT_PREDICTION.md` (+ confound gate) |
| **CLAUDE-CODE-AGENT-TEAMS-CANARY** | **NOT-RUN** |
| **P1-VALID-ONLY-IF** | Canary **before** #283 merge · `--base origin/main` · record `base_ref` |

## Decisive confound
If #283 merges first, remediated doc+test land on main → no disagreement left → “no SIGNAL” would be **false** task-list success. Do **not** merge #283 until Claude AT canary Observed is filled (or mark `p1_validity=contaminated`).

## Windows sequence
1. `git worktree prune`
2. Confirm #283 unmerged; main lacks both C1 artifacts
3. P2 baseline → paste lead prompt (`--base origin/main`) → fill Observed incl. **`base_ref`** + **`p1_validity`**
4. Then merge #283
