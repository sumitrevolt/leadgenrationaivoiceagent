# SESSION_HANDOFF — 2026-08-08 C1 protocol run complete (Cursor lead)

## Source boundary
- Branch: `cursor/claude-agent-teams-worktrees-63d4` · PR #283
- Harness: **Cursor Task agents as TM1/TM2** + this cloud lead (not Windows Claude Code Agent Teams UI)
- Base for worktrees: PR tip `7405e6ba` (SSOT/check present). Windows prune still owner-side.

## Outcome labels (anti-drift)

| Label | Status |
|-------|--------|
| **SCAFFOLDING-EVIDENCE** | Prior helper tests — not this run's verdict |
| **CANARY-SIGNAL** | **PROVEN** — after TM1→TM2 merge, TM2 RED: doc omitted SSOT `branch_prefix` / `agent/tm`. Test not weakened. |
| **F4-PROVEN** | TM2 worktree pytest exit 1 via `pytest.fail` (missing doc); no skip. `canary_f4_no_skip.py` OK after merge. |
| **PROTOCOL-PASS (Cursor)** | After lead remediation of TM1 doc (cite `agent/tm`), verify 13 passed / 0 skipped + frozen checks clean + secrets OK |
| **CLAUDE-CODE-AGENT-TEAMS-CANARY** | **NOT-RUN** — still needs Windows paste of `CANARY_LEAD_PROMPT.md` for real Agent Teams + Claude quota burn |

Do **not** quote PROTOCOL-PASS as Claude Code Agent Teams CANARY-PASS.

## Merge order evidence
1. TM1 `agent/tm1/c1-doc` @ `659f4099` — frozen check exit 0 → fast-forward merge
2. TM2 still RED in its worktree (F4) → frozen check exit 0 → merge `675af9b9`
3. Lead verify RED → SIGNAL → doc remediation → verify GREEN

## Quota note (honest)
```
Canary C1 quota (measured):
- plan_tier: cursor-cloud (not Claude Pro/Max session)
- wall_clock_minutes: ~1 (56s lead wall from worktree create through verify)
- operator_total_burn_note: Cursor Task TM1+TM2 + lead; Claude Code Agent Teams burn N/A in this environment
- per_teammate_burn_available: false
- decision_for_next_run: keep_2; still run Windows Claude Code canary for real pool burn
```

## Owner still needs (Windows)
1. `git worktree prune` (sandbox could not clear Windows metadata)
2. Optional: paste `CANARY_LEAD_PROMPT.md` in Claude Code for true Agent Teams + quota numbers
