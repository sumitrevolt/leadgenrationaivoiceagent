# SESSION_HANDOFF — 2026-08-08 ADR-172/173 Agent Teams + claw-orchestrator eval

## Source boundary
- Branch: `cursor/claude-agent-teams-worktrees-63d4`
- PR: #283
- Eval clone (not in repo): `/tmp/claw_orch_eval/claw-orchestrator` (@enderfga/claw-orchestrator v4.11.0)
- No prod env / OpenClaw allowlist / deploy touch.

## Implemented
- **ADR-172:** Claude Code Agent Teams + mandatory worktree isolation (settings + script + runbook + tests).
- **ADR-173:** claw-orchestrator formal eval — **REJECT full vendor**; patterns-only. Diagram match ≠ authority fit.

## Honest status
- Agent Teams = local opt-in CODE-PRESENT.
- claw-orchestrator = evaluated, not installed, not registered in OpenClaw.
- Mission ledger remains `external_agents` / PR Factory.

## Evidence
- `pytest tests/test_agent_team_worktree.py` → 5 passed (prior commit).
- ADR-173 cites plugin 65 tools, `childProcess: true`, council `bypassPermissions`, install.sh gateway rewrite.

## Next
- Owner canary: 2–3 Agent Teams teammates in worktrees + buzzlock.
- Do **not** run claw-orchestrator `install.sh` on LeadGen OpenClaw gateway.
- Revisit clawo only under ADR-173 gates (Owner-OS-gated adapter, never raw plugin dump).
