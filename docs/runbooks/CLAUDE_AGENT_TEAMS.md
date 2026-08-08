# Runbook — Claude Code Agent Teams + worktrees

Decision: `docs/adr/ADR-172-claude-agent-teams-worktrees.md` · eval reject: `docs/adr/ADR-173-claw-orchestrator-eval.md`
Upstream: https://code.claude.com/docs/en/agent-teams

## What this is / is not

| Is | Is not |
|----|--------|
| Native Claude Code multi-session coordination (shared task list) | A second Owner OS / PR Factory / mission ledger |
| Local coding-plane helper + worktree isolation | Production automation or Celery/STAFF runtime |
| Additive to buzzlock + AGENT_WORK_RULES | Replacement for `EXTERNAL_AGENT_ORCHESTRATOR` |

Workforce stays **31 STAFF**. OpenClaw stays Owner Copilot edge. Agent Teams teammates
are **Claude Code sessions**, not STAFF agents.

## Two landmines (read before any canary)

1. **Shared task list ≠ file lock.** Agent Teams coordination is advisory — it reduces
   duplicate *task claiming*, it does **not** enforce exclusive file writes. Real
   isolation = **git worktree per teammate** (ADR-172) + buzzlock. **Merge order stays
   with the lead.**
2. **First-route-wins = silent death.** Two teammates can each add a route in separate
   worktrees, both green locally; after merge one route is shadowed. Canary tasks must
   be **docs/tests-only** or additive **non-route** modules — or route registration is
   **lead-only**.

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

Requires Claude Code **≥ v2.1.178**. Display: prefer **in-process** on Windows.

## Canary protocol (first live run)

| Rule | Value |
|------|--------|
| Teammates | **2 max** (not 3 — learn coordination overhead first) |
| Worktree | 1 per teammate via `scripts/agent_team_worktree.py --teammate {1,2}` |
| Branch | `agent/tm{1,2}/<slug>` |
| Lead owns | merge order · any route registration · final `/verify` |
| Teammate "done" | **not** evidence — lead exit codes are DoD |
| Quota | ~3× burn (lead + 2) on the same Claude pool as Cowork/chat |

### Frozen (no teammate may touch)

- `app/voice_agent/**`, `app/telephony/**` (Swara/voice FROZEN)
- Compliance / §5 gates (DND, TRAI window, consent, DPDP code paths)
- `scripts/deploy_vps.sh`, `.env*`, `app/billing/packages.py`
- Any new `@router` / `@app.(get|post|…)` registration (lead-only if ever needed)

### DoD (lead only)

1. Targeted pytest (exit 0)
2. `scripts/prod_check.py` (exit 0)
3. `scripts/check_secrets.py` (clean)
4. Duplicate-route grep / prod_check route collision = 0

### Stop rule

If the first canary merge has **conflict in >1 file** → canary **FAIL** → revert to
single-agent. Do not “push through” with a third teammate.

### Lead spawn prompt (copy)

```text
Spawn exactly 2 Agent Teams teammates (not subagents). Require plan approval
before any write.

Each teammate works ONLY inside its own git worktree:
  python3 scripts/agent_team_worktree.py create --name <slug> --teammate 1|2 --base origin/main
Branch must be agent/tm{1,2}/<slug>. buzzlock claim before edit.

FROZEN for teammates: app/voice_agent/**, app/telephony/**, compliance gates,
scripts/deploy_vps.sh, .env*, app/billing/packages.py, and ANY new FastAPI route
registration (lead-only).

Teammate 1 / Teammate 2: see assigned disjoint paths below.
I (lead) own merge order, route registration if any, and final verify
(pytest + prod_check + check_secrets + duplicate-route). Your "done" is not evidence.
```

## Canary task candidates (pick ONE — coordination test, not a feature sprint)

Open GH issues `#240` (payment seam) and `#185` (Jiya creative brief) are **wrong** for
canary 1 — revenue / customer / Creative OS risk. Prefer docs/tests-only:

| ID | Shape | Teammate 1 | Teammate 2 | Why safe |
|----|--------|------------|------------|----------|
| **C1 (recommended)** | Docs + contract test | Add `docs/coordination/AGENT_TEAMS_CANARY.md` (checklist + stop rule + frozen list) | Add `tests/test_agent_teams_canary_contract.py` asserting frozen globs + branch prefix `agent/tm` appear in runbook/ADR | Zero app code; tests coordination merge only |
| **C2** | Disjoint docs | Expand R7 Agent Teams note examples in `docs/AGENT_WORK_RULES.md` only | Expand Operator FAQ section in `docs/coordination/README.md` only | Two files, no routes, no scripts |
| **C3** | Additive non-route helper | `scripts/agent_team_canary_status.py` — print worktree list + frozen reminder (stdout only) | `tests/test_agent_team_canary_status.py` — CLI `--help` / exit 0 smoke | No FastAPI; lead still runs prod_check |

**Vote:** start with **C1**. First run proves Agent Teams + worktree + lead-merge, not product value.

## Worktree commands

```bash
python3 scripts/agent_team_worktree.py create --name canary-docs --teammate 1 --base origin/main
python3 scripts/agent_team_worktree.py create --name canary-tests --teammate 2 --base origin/main
python3 scripts/agent_team_worktree.py list
python3 scripts/agent_team_worktree.py remove --name canary-docs --teammate 1 --force
```

Env: `AGENT_TEAM_WORKTREE_ROOT` (preferred) or `EXTERNAL_AGENT_WORKTREE_ROOT`.

## buzzlock still required

```bash
python3 scripts/buzzlock.py claim <paths> --tool CLAUDE --reason "<one line>"
python3 scripts/buzzlock.py release <paths> --tool CLAUDE --evidence "<exit code / tests>"
```

Exit 2 on claim = stop; pick different files.

## Hard refusals (every teammate)

- `git add -A` — stage explicit paths only
- Commit / push / deploy without owner ask
- `scripts/deploy_vps.sh` or manual compose on VPS
- Swara / voice path edits (FROZEN)
- Weakening DND / TRAI window / consent / DPDP
- New route registration (canary: lead-only / prefer none)
- Routing Claude subscription OAuth into OpenCode
- Vendoring claw-orchestrator / Vibe Kanban as control plane (ADR-173)

## Quota

2 teammates ≈ **3×** token burn (lead + 2) on the same Claude subscription pool as
Cowork/chat. Cursor waves do not burn that pool — use Cursor when quota is the bottleneck.

## Relation to PR Factory

| Plane | Tool |
|-------|------|
| Interactive Claude Code parallel work | Agent Teams + this runbook |
| Owner OS–governed Cursor/Claude missions | `tools/pr_factory` → `external_agents` (flags OFF by default) |

## Later

- **claw-orchestrator** — REJECT full vendor (ADR-173). Patterns-only.
- **Vibe Kanban** — avoid as production dependency.

## Rollback

1. `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=0`
2. `python3 scripts/agent_team_worktree.py remove --name <slug> [--teammate N] --force`
3. Single-agent + buzzlock
