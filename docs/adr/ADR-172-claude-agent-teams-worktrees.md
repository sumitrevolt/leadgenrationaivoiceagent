# ADR-172 — Claude Code Agent Teams + mandatory worktree isolation

- **Date:** 2026-08-08
- **Status:** ACCEPTED (docs + opt-in local tooling; no production flag)
- **Extends:** ADR-148 (external orchestrator), ADR-149 (runner), ADR-155 (no vendor second OS),
  ADR-163 (PR Factory), `docs/AGENT_WORK_RULES.md` R7/R8/R9/R10

## Context

Coding tools on this repo (Cursor, Claude Code, OpenCode, Monkey Code) already collide on
dirty trees and shared files. Ready-made multi-agent harnesses exist:

| Option | Fit |
|--------|-----|
| **Claude Code Agent Teams** (native, `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`) | Lowest risk — no new dependency; shared task list is the coordination layer |
| **claw-orchestrator** (Enderfga) | Cross-harness (Claude/Codex/Gemini/Cursor) + OpenClaw plugin — natural later if Owner OS must dispatch coding missions |
| **Vibe Kanban** | Board UI; Bloop shut down early-2026; community-maintained — avoid as production dependency |
| Conductor | macOS-only — rejected (owner on Windows) |
| Claude Squad | tmux/WSL — rejected as primary |

We already have `buzzlock`, `external_agents` worktrees, and PR Factory. We must **not**
add a second control plane or route Claude subscription OAuth into OpenCode (ToS grey area;
free-stack mandate already covers OpenCode keys).

## Decision

1. **Start with native Claude Code Agent Teams + git worktrees** before adopting any
   third-party coding orchestrator YAML/runtime.
2. **Enable opt-in via project settings:** `.claude/settings.json` →
   `env.CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`. Operator may unset locally. Start with
   **2–3 teammates** (Anthropic guidance).
3. **Worktree isolation is mandatory** for every teammate that edits code. Use
   `scripts/agent_team_worktree.py` (allowlisted root, same family as
   `EXTERNAL_AGENT_WORKTREE_ROOT` / `_leadgen_worktrees`). Never edit the chronically
   dirty primary checkout from parallel teammates.
4. **buzzlock still applies** inside each worktree for shared paths; Agent Teams' task
   list does not replace `docs/coordination/LOCKS.json`.
5. **Frozen / RED surfaces stay RED:** Swara/voice, `deploy_vps.sh`, TRAI/DND/consent/DPDP,
   billing truth — teammates must not mutate these without owner "haan" (R8/R10).
6. **Defer claw-orchestrator** until Agent Teams is proven useful *and* OpenClaw needs to
   dispatch coding tasks. When evaluated, patterns-only harvest first (ADR-155 class) —
   do not vendor as a second Owner OS.
7. **Reject Vibe Kanban / Conductor / Claude Squad as primary** coordination for this repo.
8. **OpenCode stays on free-stack keys** (Groq/Mistral/Cerebras). Do not route Claude
   subscription OAuth into non-native harnesses.
9. **Cursor remains a first-class implementer** on its own subscription (does not consume
   Claude Code quota). Prefer Cursor for heavy implementation waves when Claude quota is
   the bottleneck.
10. **PR Factory / `external_agents` remain the mission ledger** for Owner OS–governed
    Cursor+Claude missions (ADR-163). Agent Teams is the *interactive Claude Code* plane —
    not a replacement for `create_mission` / leases / GREEN-AMBER-RED.

## Quota posture (operator)

Agent Teams share the Claude Code subscription pool. N parallel teammates ≈ N× token burn.
Regular multi-agent coding is impractical on Pro alone for sustained waves; Max-class
subscription is the practical floor if Agent Teams is used daily. Exact plan choice is an
**owner money decision** — this ADR does not flip billing.

## Alternatives rejected

| Option | Why |
|--------|-----|
| New YAML orchestrator before Agent Teams | Extra control plane; ADR-155/163 already cover factory path |
| Vendor claw-orchestrator now | Premature; OpenClaw coding dispatch not proven needed |
| Vibe Kanban as prod dep | Maintainer exit risk |
| Shared primary checkout for teammates | Dirty-tree + `git add -A` / deploy landmines |
| Claude OAuth → OpenCode plugins | ToS grey area + free-stack mandate |

## Consequences

- Docs: `docs/runbooks/CLAUDE_AGENT_TEAMS.md`, this ADR, coordination README pointer
- Tooling: `scripts/agent_team_worktree.py` + `tests/test_agent_team_worktree.py`
- Settings: `.claude/settings.json` env flag (local Claude Code only; no VPS/prod effect)
- Memory: append ADR-172 in `memory/decisions.md`
- No `AUTOMATION_FLAGS` / prod env change. No deploy. No OpenClaw enablement change.

## Rollback

1. Set `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=0` (or remove) in `.claude/settings.json` /
   shell.
2. Stop spawning teammates; use single session + buzzlock as before.
3. Remove agent-team worktrees: `python scripts/agent_team_worktree.py remove --name <slug>`.
4. Docs/script deletion is inert (no runtime path).
