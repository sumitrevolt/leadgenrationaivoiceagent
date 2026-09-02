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

### Frozen = SSOT + observance gate

Machine-readable truth: **`docs/coordination/canary_frozen_paths.yml`**.

- TM1 doc **references / renders** via `python3 scripts/canary_frozen.py render`.
- TM2 test **loads** YAML through `scripts/canary_frozen.py` — never pastes paths.
- Lead **enforces** before each merge:

```bash
python3 scripts/canary_frozen.py check --base origin/main --head HEAD
# exit 0 = clean · exit 2 = frozen path touched → refuse merge
```

- `.env` / `.env.*` live under **`frozen_classes`** (`env_files_gitignored`) — gitignored,
  so they cannot be diff-gated; hooks/write_guard remain the real control.
- A test that asserts against its own hardcoded path copy is a **tautology** (R4).

### Merge order (fixed)

**TM1 first, then TM2.** TM2 may finish authoring early — hold the merge. Without the doc,
TM2 RED/GREEN is noise; with `skipif(not exists)` the coupling signal dies forever.

### Stop rule

Merge conflicts in **>1 file** on first canary → **FAIL** → single-agent. No third teammate.

### Pass rule (all required)

1. Lead merged deliverables in order **TM1 → TM2**.
2. `canary_frozen.py check` clean on each teammate branch before merge.
3. Post-merge verify green: targeted pytest with **0 skipped** + `prod_check.py` +
   `check_secrets.py` + duplicate-route clean.
4. TM2 test reads the **SSOT**; missing doc → `pytest.fail` (never skip/skipif).
5. Honest quota note recorded (see `quota.record_fields` — no invented per-tm splits).
6. If TM2 is RED because TM1 disagrees with SSOT → **CANARY-SIGNAL** (do not weaken).

### Evidence labels (anti label-drift)

| Label | Means | Does NOT mean |
|-------|--------|----------------|
| **SCAFFOLDING-EVIDENCE** | SSOT / loader / worktree / check-helper tests green | Canary PASS |
| **CANARY-NOT-RUN** | Live Agent Teams C1 not executed yet | Failure |
| **CANARY-PASS** | TM1→TM2 + frozen checks + verify + 0 skipped + quota note | Scaffolding greens |
| **CANARY-SIGNAL** | TM2 RED vs TM1 after correct merge order | Excuse to weaken asserts |

### Quota (honest measure — F7 still open until Claude AT)

Cursor ~56s + `per_teammate_burn_available=false` does **not** decide 2 vs 3 teammates.

Claude Code run: **before merging PR #283**, `--base origin/main` (C1 artifacts absent),
**baseline before paste**, **delta after verify**. Record `base_ref` + `p1_validity` in
`docs/coordination/C1_CLAUDE_AT_PREDICTION.md`. Contaminated base ⇒ no P1 conclusion.

### C1 deliverables

| Role | File | Job |
|------|------|-----|
| TM1 | `docs/coordination/AGENT_TEAMS_CANARY.md` | Render frozen from SSOT |
| TM2 | `tests/test_agent_teams_canary_contract.py` | Load SSOT; fail-not-skip if doc missing |
| Lead | merge TM1→TM2 + `check` + verify + quota | Owns PASS/FAIL/SIGNAL |

Worktrees: always `create --canary --teammate {1,2}`. Lead prompt:
`docs/coordination/CANARY_LEAD_PROMPT.md`.

**Not for C1:** GH `#240` (payment), `#185` (Jiya creative).

### Lead spawn prompt

Copy from `docs/coordination/CANARY_LEAD_PROMPT.md` (canonical paste block).

## Worktree commands

```bash
python3 scripts/agent_team_worktree.py create --canary --name c1-doc --teammate 1 --base origin/main
python3 scripts/agent_team_worktree.py create --canary --name c1-test --teammate 2 --base origin/main
python3 scripts/canary_frozen.py render
python3 scripts/canary_frozen.py check --base origin/main --head HEAD
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
