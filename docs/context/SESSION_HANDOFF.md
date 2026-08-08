# SESSION_HANDOFF — 2026-08-08 P1 window OPEN · Sumit-only execution

## Verified now
- Setup FROZEN/GO tip: `d1042e69` · PR #283 branch tip may be ahead (handoff-only)
- `origin/main`: `5ae5a4b9` — C1 doc + contract **absent** → **P1 window OPEN**
- Do **not** merge PR #283 until Observed filled (or contaminated recorded)
- Merge pehle = `p1_validity=contaminated` → P1 conclusion void

## AGENT FORBIDDEN (any tool — Cursor/Claude/OpenCode/Monkey/cloud)
Ye teen steps **Sumit Windows-only** hain. Agents **attempt mat karo** (do baar prove: fail / out of scope):
1. `git worktree prune` — sandbox `.git` unlink = Operation not permitted
2. Claude **Usage** baseline — Sumit account/browser only
3. Interactive Claude Code paste / session drive — terminals/IDEs blocked by design
4. Merging PR #283 “to help” before Observed — **contaminates P1**

Agents may **only** after Sumit returns `base_ref` + `p1_validity` + P1 Observed + burn delta: interpret + update handoff/docs.

## Sumit manual sequence (Windows, this order)
```
git worktree prune
git fetch origin main && git rev-parse --short origin/main   # → base_ref (expect 5ae5a4b9)
# Claude Code: note usage baseline + clock_start
# Paste docs/coordination/CANARY_LEAD_PROMPT.md
# After run: fill Observed in docs/coordination/C1_CLAUDE_AT_PREDICTION.md
#   (base_ref, p1_validity, signal_*, burn delta)
# THEN merge #283
```

Signal fire = answer, not failure. Contaminated base = no P1 conclusion.
