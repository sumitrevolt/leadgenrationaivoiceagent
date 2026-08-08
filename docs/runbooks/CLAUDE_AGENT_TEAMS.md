# Runbook — Claude Code Agent Teams + worktrees

Decision: `docs/adr/ADR-172-claude-agent-teams-worktrees.md`
Upstream: https://code.claude.com/docs/en/agent-teams

## What this is / is not

| Is | Is not |
|----|--------|
| Native Claude Code multi-session coordination (shared task list) | A second Owner OS / PR Factory / mission ledger |
| Local coding-plane helper + worktree isolation | Production automation or Celery/STAFF runtime |
| Additive to buzzlock + AGENT_WORK_RULES | Replacement for `EXTERNAL_AGENT_ORCHESTRATOR` |

Workforce stays **31 STAFF**. OpenClaw stays Owner Copilot edge. Agent Teams teammates
are **Claude Code sessions**, not STAFF agents.

## Enable (local operator)

Project settings already set the experimental flag (ADR-172):

```json
{
  "env": {
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
  }
}
```

File: `.claude/settings.json`. To disable for one machine, override in
`~/.claude/settings.json` or unset the env var in the shell before `claude`.

Requires Claude Code **≥ v2.1.178** (teammate spawn without TeamCreate/TeamDelete).

Display: prefer **in-process** on Windows (default). Split-pane needs tmux/iTerm —
not the primary path here.

## First team (2–3 teammates only)

Start small. Example lead prompt:

```text
Spawn exactly 2 teammates for disjoint work. Each must operate only inside its
own git worktree (see scripts/agent_team_worktree.py). Claim files with
buzzlock before edit. Never touch Swara/voice, deploy_vps.sh, billing packages,
or compliance gates. Require plan approval before any write.

Teammate A: investigate X and write findings only under docs/ or tests/.
Teammate B: investigate Y on a different path set.
Synthesize when both idle.
```

If Claude spawns **subagents** instead of a team, ask again and say **agent team**
explicitly (subagents and teammates share the same panel UI).

## Worktree isolation (mandatory)

Primary checkout is chronically dirty. Parallel teammates must not share it.

```bash
# Create (allowlisted root; default EXTERNAL_AGENT_WORKTREE_ROOT or sibling _leadgen_worktrees)
python3 scripts/agent_team_worktree.py create --name review-auth --base origin/main

# List
python3 scripts/agent_team_worktree.py list

# Remove when done
python3 scripts/agent_team_worktree.py remove --name review-auth
```

Env overrides (names only — never commit values):

| Env | Purpose |
|-----|---------|
| `AGENT_TEAM_WORKTREE_ROOT` | Preferred root for agent-team worktrees |
| `EXTERNAL_AGENT_WORKTREE_ROOT` | Fallback (same as external_agents runner) |

Branch created: `claude/agent-team-<slug>`.

Each teammate session should `cd` into its worktree before editing.

## buzzlock still required

Agent Teams' shared task list prevents *some* collisions; it does **not** replace
cross-tool locks (Cursor/OpenCode/Monkey on the same paths).

```bash
python3 scripts/buzzlock.py claim <paths> --tool CLAUDE --reason "<one line>"
# ... work ...
python3 scripts/buzzlock.py release <paths> --tool CLAUDE --evidence "<exit code / tests>"
```

Exit 2 on claim = stop; pick different files.

## Hard refusals (every teammate)

- `git add -A` — stage explicit paths only
- Commit / push / deploy without owner ask
- `scripts/deploy_vps.sh` or manual compose on VPS
- Swara / voice path edits (FROZEN)
- Weakening DND / TRAI window / consent / DPDP
- Routing Claude subscription OAuth into OpenCode
- Vendoring claw-orchestrator / Vibe Kanban as control plane

## Quota

Each teammate is a separate Claude instance on the **same subscription pool**.
2–3 teammates is the default ceiling until the owner confirms plan headroom.
Cursor implementation waves do not burn Claude Code quota — use that when
Claude quota is the bottleneck.

## Relation to PR Factory

| Plane | Tool |
|-------|------|
| Interactive Claude Code parallel work | Agent Teams + this runbook |
| Owner OS–governed Cursor/Claude missions | `tools/pr_factory` → `external_agents` (flags OFF by default) |

Do not invent a third mission store.

## Later

- **claw-orchestrator** — **REJECT full vendor** (ADR-173). Diagram match is real;
  authority model is inverted (65-tool `childProcess` plugin + `bypassPermissions`
  council vs Owner OS sole authority). Patterns-only into `external_agents` / Agent Teams.
  Revisit only under ADR-173 “When to revisit” gates.
- **Vibe Kanban** — avoid as production dependency.

## Rollback

1. `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=0`
2. `python3 scripts/agent_team_worktree.py remove --name <slug>` for each leftover
3. Resume single-session + buzzlock workflow
