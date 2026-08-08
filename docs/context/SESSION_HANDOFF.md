# SESSION_HANDOFF — 2026-08-08 C1 owner setup ready · CANARY-NOT-RUN

## Source boundary
- Branch: `cursor/claude-agent-teams-worktrees-63d4` · PR #283
- Live Agent Teams canary: **CANARY-NOT-RUN** (needs owner Claude Code session + prompt paste).

## Owner setup completed
- SSOT: `docs/coordination/canary_frozen_paths.yml` (frozen + merge_order TM1→TM2 + stop/pass/quota + evidence_labels)
- Loader: `scripts/canary_frozen.py`
- Lead paste prompt: `docs/coordination/CANARY_LEAD_PROMPT.md` (merge order fixed TM1 then TM2)
- Runbook: pass rule, SSOT rule, measure quota, evidence-label table

## Still for live canary
- TM1 → `docs/coordination/AGENT_TEAMS_CANARY.md` (merge **first**)
- TM2 → `tests/test_agent_teams_canary_contract.py` (merge **second**, after TM1)
- Lead verify + measured quota → only then may anyone write **CANARY-PASS**

## Evidence labels (do not drift)

| Label | Status |
|-------|--------|
| **SCAFFOLDING-EVIDENCE** | `pytest tests/test_canary_frozen_ssot.py tests/test_agent_team_worktree.py` → 9 passed (exit 0). Setup/helpers only. |
| **CANARY-NOT-RUN** | Current. No TM1/TM2 deliverables. No measured burn. |
| **CANARY-PASS** | Forbidden to claim until live C1 completes under runbook pass rule. |

Do **not** quote the scaffolding 9 passed as canary PASS in `CURRENT_STATE` or chat.
