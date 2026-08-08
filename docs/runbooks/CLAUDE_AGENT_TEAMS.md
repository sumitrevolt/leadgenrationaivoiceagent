# Runbook — Claude Code Agent Teams + worktrees

Decision: `docs/adr/ADR-172-claude-agent-teams-worktrees.md` · eval reject: `docs/adr/ADR-173-claw-orchestrator-eval.md`
Upstream: https://code.claude.com/docs/en/agent-teams
Live prompt: `docs/coordination/CANARY_LEAD_PROMPT.md`
Frozen SSOT: `docs/coordination/canary_frozen_paths.yml` · loader: `scripts/canary_frozen.py`

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

`.claude/settings.json` → `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`. Claude Code ≥ v2.1.178.
Prefer **in-process** display on Windows.

## Canary protocol (C1 — owner green-light)

| Rule | Value |
|------|--------|
| Teammates | **2 max** |
| Worktree | `--teammate {1,2}` → branch `agent/tm{N}/<slug>` |
| Lead owns | merge · route registration (none in C1) · final verify · quota measure |
| Teammate "done" | **not** evidence |
| Context docs | teammates do **not** write `CURRENT_STATE` / `ACTIVE_WORK` / `SESSION_HANDOFF` |
| Prod probe | teammates do **not** hit production |

### Frozen = SSOT only (no pasted twin)

Machine-readable truth: **`docs/coordination/canary_frozen_paths.yml`**.

- TM1 doc **references / renders** via `python3 scripts/canary_frozen.py` — does not invent a second path list.
- TM2 test **loads** the YAML through `scripts/canary_frozen.py` — never pastes paths into the test.
- A test that asserts against its own hardcoded copy is a **tautology** and fails the canary design
  (`packages.py`-class dual-truth bug).

### Merge order (fixed)

**TM1 first, then TM2.** TM2 may finish authoring early while only SSOT+loader exist —
merging the test before the doc means the semantic-coupling signal never fires.
RED/GREEN is only meaningful once TM1's doc is merged and TM2's test runs against it.

### Stop rule

Merge conflicts in **>1 file** on first canary → **FAIL** → single-agent. No third teammate.

### Pass rule (all required)

1. Lead merged deliverables in order **TM1 → TM2**.
2. Post-merge `/verify` green: targeted pytest + `prod_check.py` + `check_secrets.py` + duplicate-route clean.
3. TM2 test reads the **SSOT** (not a paste). If TM2 is RED because TM1 disagrees with SSOT,
   that is a **canary SIGNAL** (shared task list failed semantic consistency) — lead records it;
   do **not** weaken the test to force green.

### Evidence labels (anti label-drift)

| Label | Means | Does NOT mean |
|-------|--------|----------------|
| **SCAFFOLDING-EVIDENCE** | SSOT / loader / worktree helper tests green | Canary PASS |
| **CANARY-NOT-RUN** | Live Agent Teams C1 not executed yet | Failure |
| **CANARY-PASS** | TM1→TM2 merged + lead verify green + measured quota recorded | Scaffolding greens |
| **CANARY-SIGNAL** | TM2 RED vs TM1 after correct merge order | Excuse to weaken asserts |

Never quote scaffolding `N passed` as canary PASS in `CURRENT_STATE` / handoff.

### Quota (measure, do not guess)

Pre-run estimate ≈ 3× (lead + 2). **After the run**, lead records actual burn in
`SESSION_HANDOFF` (lead / tm1 / tm2 tokens-or-cost, wall clock, plan tier). Next teammate-count
decision uses that evidence. Max may afford 3 later; Pro may exhaust a window in one canary.

### C1 deliverables (semantically coupled, file-disjoint)

| Role | File | Job |
|------|------|-----|
| TM1 | `docs/coordination/AGENT_TEAMS_CANARY.md` | Checklist + landmines; Frozen section **from SSOT render** |
| TM2 | `tests/test_agent_teams_canary_contract.py` | Asserts doc ↔ SSOT coupling by **reading** YAML |
| Lead | merge **TM1→TM2** + verify + quota note | Owns PASS/FAIL/SIGNAL |

Owner setup already shipped: SSOT + loader + `tests/test_canary_frozen_ssot.py` + lead prompt
(**SCAFFOLDING-EVIDENCE** only). Live canary still creates TM1 doc + TM2 contract test.

**Not for C1:** GH `#240` (payment), `#185` (Jiya creative).

### Lead spawn prompt

Copy from `docs/coordination/CANARY_LEAD_PROMPT.md` (canonical paste block).

## Worktree commands

```bash
python3 scripts/agent_team_worktree.py create --name c1-doc --teammate 1 --base origin/main
python3 scripts/agent_team_worktree.py create --name c1-test --teammate 2 --base origin/main
python3 scripts/canary_frozen.py   # render frozen bullets from SSOT
python3 scripts/agent_team_worktree.py list
```

## buzzlock still required

```bash
python3 scripts/buzzlock.py claim <paths> --tool CLAUDE --reason "<one line>"
python3 scripts/buzzlock.py release <paths> --tool CLAUDE --evidence "<exit code / tests>"
```

Exit 2 on claim = stop.

## Hard refusals (every teammate)

- `git add -A`; commit/push/deploy without owner ask
- Paths / classes in the SSOT; FastAPI route registration
- Context-doc edits; prod probes
- Claude OAuth → OpenCode; claw-orchestrator install (ADR-173)

## Relation to PR Factory

Agent Teams = interactive Claude plane. Missions = `tools/pr_factory` → `external_agents`.

## Rollback

1. `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=0`
2. Remove canary worktrees (`--teammate` + `--force`)
3. Single-agent + buzzlock
