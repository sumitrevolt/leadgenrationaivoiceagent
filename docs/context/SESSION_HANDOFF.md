# SESSION_HANDOFF — 2026-08-08 C1 Cursor done · Claude AT prediction LOCKED

## Source boundary
- Branch: `cursor/claude-agent-teams-worktrees-63d4` · PR #283 · tip `96bba2b2`+
- Cursor C1 = protocol proof. Claude Code Agent Teams = **NOT-RUN**.

## Labels

| Label | Status |
|-------|--------|
| **PROTOCOL-PASS (Cursor)** | Done — SSOT/merge/F4/F1; SIGNAL handled without weakening test |
| **CANARY-SIGNAL (Cursor)** | Fired (`branch_prefix` / `agent/tm` miss) — expected under non-AT harness |
| **CLAUDE-CODE-AGENT-TEAMS-CANARY** | **NOT-RUN** |
| **PREDICTION-LOCKED** | `docs/coordination/C1_CLAUDE_AT_PREDICTION.md` — fill Observed only after Windows run |

## Framing (do not blur)

Cursor run proved **harness-agnostic protocol**. It did **not** prove Agent Teams shared task list prevents disagreement (no AT task list was in the loop).

## Next (Windows owner)

1. `git worktree prune`
2. Read + leave untouched the Predictions in `C1_CLAUDE_AT_PREDICTION.md`
3. **Before paste:** write P2 baseline (plan_tier + usage UI note + clock_start)
4. Paste `CANARY_LEAD_PROMPT.md` → TM1→TM2 → verify
5. Fill Observed (P1 signal yes/no + P2 delta). Do not edit prediction table.
