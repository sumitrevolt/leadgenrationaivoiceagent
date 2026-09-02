# Agent Teams C1 — lead prompt (paste into Claude Code lead session)

Owner-approved canary. Tip must include F1 `check` gate.
SSOT: `docs/coordination/canary_frozen_paths.yml`
Loader/check: `scripts/canary_frozen.py` · Protocol: `docs/runbooks/CLAUDE_AGENT_TEAMS.md`

Teammates must **not** edit the SSOT, context docs, prod probes, or frozen paths.
Lead owns merge + frozen check + verify + honest quota note.

---

## Paste to lead

```text
Spawn exactly 2 Agent Teams teammates (NOT subagents). Require plan approval before any write.

SETUP (lead runs first, then each teammate cds into their worktree):
  # VALIDITY: PR #283 must NOT be merged yet. Base must be origin/main where
  # AGENT_TEAMS_CANARY.md and test_agent_teams_canary_contract.py are ABSENT.
  # If those files already exist on base → P1 contaminated — stop or mark void.
  git fetch origin main
  git rev-parse origin/main   # record as base_ref in C1_CLAUDE_AT_PREDICTION.md Observed
  git cat-file -e origin/main:docs/coordination/AGENT_TEAMS_CANARY.md && echo CONTAMINATED && exit 1
  git cat-file -e origin/main:tests/test_agent_teams_canary_contract.py && echo CONTAMINATED && exit 1

  python3 scripts/agent_team_worktree.py create --canary --name c1-doc --teammate 1 --base origin/main
  python3 scripts/agent_team_worktree.py create --canary --name c1-test --teammate 2 --base origin/main
Branches MUST be agent/tm1/c1-doc and agent/tm2/c1-test (--canary refuses other shapes).

  # Seed SSOT+loader ONLY (never the canary doc/test) from this PR tip into each worktree:
  python3 scripts/canary_seed_tooling.py --worktree <tm1-wt> --from-ref <pr-tip-sha>
  python3 scripts/canary_seed_tooling.py --worktree <tm2-wt> --from-ref <pr-tip-sha>
  # Exit 2 if deliverables already present = contaminated.

buzzlock claim before edit.

SSOT (single source — DO NOT paste frozen paths into docs or tests):
  docs/coordination/canary_frozen_paths.yml
  Render: python3 scripts/canary_frozen.py render
  Enforce: python3 scripts/canary_frozen.py check --base origin/main --head HEAD
  TM1 doc references/renders from SSOT. TM2 test LOADS SSOT via scripts/canary_frozen.py.
  If you paste the path list into the test, the canary is invalid (tautology).

FROZEN: frozen_paths are DIFF-GATED (check command). frozen_classes (env_files_gitignored,
compliance, route registration) are policy — .env is gitignored so it cannot be diff-gated.
Teammates do not write context docs, do not prod-probe, do not deploy.

=== Teammate 1 (TM1) — docs only ===
Create docs/coordination/AGENT_TEAMS_CANARY.md that:
- States C1 purpose (coordination consistency, not a feature)
- References the SSOT path explicitly
- Includes a "Frozen" section RENDERED from `python3 scripts/canary_frozen.py render`
  (do not hand-type path bullets)
- Documents stop + pass rules by reference to the SSOT
- Notes: shared task list ≠ file lock; first-route-wins; lead owns merge/verify
Do NOT edit tests/. Do NOT edit the SSOT YAML.

=== Teammate 2 (TM2) — tests only ===
Create tests/test_agent_teams_canary_contract.py that:
- Loads scripts/canary_frozen.py (SSOT) — never hardcodes the frozen path list
- Asserts docs/coordination/AGENT_TEAMS_CANARY.md exists; if missing → pytest.fail(...)
  with a clear message. NEVER pytest.skip / skipif / xfail on missing doc.
  Your worktree is based on origin/main where the doc does not exist yet — so THIS TEST
  WILL BE RED IN YOUR WORKTREE. That is EXPECTED. Do not "fix" the RED with skip.
  Lead merges TM1 first, then your test — only then can GREEN mean coupling worked.
- After doc exists: assert it contains each frozen_paths entry from SSOT (or SSOT path +
  render marker) — prove coupling, not a pasted twin
- Asserts branch_prefix from SSOT appears in the doc; max_teammates == 2 from SSOT
If RED after TM1 merge because doc disagrees with SSOT → canary SIGNAL, do not weaken.
Do NOT edit docs/coordination/AGENT_TEAMS_CANARY.md. Do NOT edit the SSOT YAML.

=== Lead ===
- MERGE ORDER FIXED: TM1 first, then TM2.
- Before merging EACH teammate branch, from that worktree/branch run:
    python3 scripts/canary_frozen.py check --base origin/main --head HEAD
  Exit 2 = refuse merge (frozen path touched).
- Resolve conflicts. Stop if >1 conflict file.
- Verify AFTER both merges:
    pytest tests/test_canary_frozen_ssot.py tests/test_agent_teams_canary_contract.py -q -rs
  Assert summary shows **0 skipped**. Any skip on the canary contract = FAIL.
  Also: python3 scripts/canary_f4_no_skip.py  (exit 2 if skip/xfail patterns present)
  + scripts/prod_check.py + scripts/check_secrets.py + duplicate-route clean
- PASS only if TM1→TM2 merged + frozen checks clean + verify green + 0 skipped + SSOT-backed TM2
- RED TM2 vs TM1 after merge = SIGNAL (record in SESSION_HANDOFF), not a silent pass
- Quota note (honest): plan_tier, wall_clock_minutes, operator_total_burn_note,
  per_teammate_burn_available true|false (do NOT invent per-tm splits if false),
  decision_for_next_run. Write into SESSION_HANDOFF.
- Label discipline: scaffolding pytest greens are NOT "canary PASS"
```

## After-run quota note template (lead fills)

**Before paste — baseline (required; F7 still open):**
```text
Claude AT baseline:
- plan_tier:
- account_usage_note:
- clock_start_iso:
```

**After verify — delta only (do not invent per-tm splits):**
```text
Canary C1 Claude AT quota (measured):
- clock_end_iso:
- wall_clock_minutes:
- usage_delta_note:
- per_teammate_burn_available: false|true
- decision_for_next_run: keep_2 | try_3_on_max | abort_parallel
```

**P1 prediction** is locked in `docs/coordination/C1_CLAUDE_AT_PREDICTION.md` — record Observed there after the run; do not rewrite Predictions.
