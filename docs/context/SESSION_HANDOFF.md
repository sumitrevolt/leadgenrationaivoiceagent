# SESSION_HANDOFF — 2026-08-08 ADR-172 Claude Agent Teams + worktrees

## Source boundary
- Branch: `cursor/claude-agent-teams-worktrees-63d4` (from `main`)
- Cloud agent run: Claude agent teams worktrees
- No prod env / flag / deploy touch. Swara/voice untouched.

## Implemented
- **ADR-172:** native Claude Code Agent Teams + mandatory git worktree isolation as the coding-plane multi-agent path; claw-orchestrator deferred; Vibe Kanban/Conductor/Claude Squad rejected as primary; OpenCode stays free-stack (no Claude OAuth route).
- `.claude/settings.json` → `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` (local Claude Code only).
- `scripts/agent_team_worktree.py` — create/list/remove under allowlisted root (`AGENT_TEAM_WORKTREE_ROOT` / `EXTERNAL_AGENT_WORKTREE_ROOT`).
- Runbook `docs/runbooks/CLAUDE_AGENT_TEAMS.md`; pointers in coordination README, AGENT_WORK_RULES R7, PR_FACTORY.md.
- Contract tests `tests/test_agent_team_worktree.py`.

## Honest status
- Docs + opt-in local tooling = CODE-PRESENT.
- Not a second control plane; PR Factory / external_agents mission ledger unchanged.
- Owner Pro vs Max quota choice = money decision (not coded).

## Evidence
- `.venv/bin/python -m pytest tests/test_agent_team_worktree.py -q` → 5 passed (exit 0).

## Next
- Owner: confirm Claude plan headroom (2–3 teammates default).
- First live canary: spawn 2 teammates on disjoint paths inside agent-team worktrees + buzzlock.
- Only later: evaluate claw-orchestrator if OpenClaw coding dispatch is needed (patterns-first, ADR-155).
