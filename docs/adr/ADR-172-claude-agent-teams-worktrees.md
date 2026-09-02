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
   `EXTERNAL_AGENT_WORKTREE_ROOT` / `_leadgen_worktrees`). Canary branches:
   `agent/tm{1,2}/<slug>` via `--teammate`. Never edit the chronically dirty primary
   checkout from parallel teammates.
4. **buzzlock still applies** inside each worktree for shared paths; Agent Teams' task
   list is **advisory** — it does not enforce exclusive file writes. Merge order = lead.
5. **Frozen / RED surfaces stay RED:** Swara/voice, `deploy_vps.sh`, TRAI/DND/consent/DPDP,
   billing truth — teammates must not mutate these without owner "haan" (R8/R10).
   First canary: **no teammate route registration** (FastAPI first-route-wins landmine).
6. **Canary shape (C1, owner green-light):** 2 teammates max; docs/tests-only; merge order
   **TM1 then TM2** (fixed — TM2-before-TM1 kills the coupling signal); lead owns
   merge + `/verify` + **measured** quota note; stop if merge conflicts touch **>1 file**.
   Frozen paths live in **one** machine-readable SSOT
   (`docs/coordination/canary_frozen_paths.yml`) — TM1 renders it, TM2 reads it (no pasted
   twin). Pass = TM1→TM2 merged + **frozen_diff_check_clean** on each tm branch + verify
   green + **0 skipped** + SSOT-backed TM2 fail-not-skip + honest quota note; TM2 RED vs TM1 =
   canary SIGNAL, not a silent weaken. Scaffolding helper-test greens are
   **SCAFFOLDING-EVIDENCE only** — never quote as CANARY-PASS. Lead prompt:
   `docs/coordination/CANARY_LEAD_PROMPT.md`.
7. **claw-orchestrator** — evaluated in **ADR-173**: reject full vendor / OpenClaw plugin
   install; patterns-only harvest. Revisit only after Agent Teams proves useful *and* an
   Owner-OS-gated adapter design exists (never raw 65-tool gateway dump).
8. **Reject Vibe Kanban / Conductor / Claude Squad as primary** coordination for this repo.
9. **OpenCode stays on free-stack keys** (Groq/Mistral/Cerebras). Do not route Claude
   subscription OAuth into non-native harnesses.
10. **Cursor remains a first-class implementer** on its own subscription (does not consume
    Claude Code quota). Prefer Cursor for heavy implementation waves when Claude quota is
    the bottleneck.
11. **PR Factory / `external_agents` remain the mission ledger** for Owner OS–governed
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
