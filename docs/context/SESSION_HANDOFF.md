# SESSION_HANDOFF — 2026-08-08 Agent Teams canary protocol locked

## Source boundary
- Branch: `cursor/claude-agent-teams-worktrees-63d4` · PR #283
- No prod / OpenClaw allowlist / deploy.

## Implemented (this turn)
- Canary protocol in `docs/runbooks/CLAUDE_AGENT_TEAMS.md`: task-list≠lock, first-route-wins landmine, 2 teammates max, frozen paths, lead-owned merge/verify, stop rule (>1 conflict file = FAIL).
- Candidates **C1/C2/C3**; recommend **C1** (docs + contract test). GH #240/#185 unsuitable for canary 1.
- `scripts/agent_team_worktree.py --teammate {1,2}` → branch `agent/tm{N}/<slug>`.
- ADR-172 updated with canary shape.

## Next (owner)
- Pick C1 (or C2/C3) and run live Agent Teams canary on Windows Claude Code.
- Do not use #240 / #185 as first canary.
