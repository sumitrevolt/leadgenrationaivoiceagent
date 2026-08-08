# Agent Teams C1 — lead prompt (paste into Claude Code lead session)

Owner-approved canary. SSOT: `docs/coordination/canary_frozen_paths.yml`
Loader: `scripts/canary_frozen.py` · Protocol: `docs/runbooks/CLAUDE_AGENT_TEAMS.md`

Teammates must **not** edit the SSOT, context docs (`CURRENT_STATE` / `ACTIVE_WORK` /
`SESSION_HANDOFF`), prod probes, or frozen paths. Lead owns merge + verify + quota note.

---

## Paste to lead

```text
Spawn exactly 2 Agent Teams teammates (NOT subagents). Require plan approval before any write.

SETUP (lead runs first, then each teammate cds into their worktree):
  python3 scripts/agent_team_worktree.py create --name c1-doc --teammate 1 --base origin/main
  python3 scripts/agent_team_worktree.py create --name c1-test --teammate 2 --base origin/main
Branches must be agent/tm1/c1-doc and agent/tm2/c1-test. buzzlock claim before edit.

SSOT (single source — DO NOT paste frozen paths into docs or tests):
  docs/coordination/canary_frozen_paths.yml
  Render/read via: python3 scripts/canary_frozen.py
  TM1 doc references/renders from SSOT. TM2 test LOADS SSOT via scripts/canary_frozen.py.
  If you paste the path list into the test, the canary is invalid (tautology).

FROZEN: everything in canary_frozen_paths.yml + no FastAPI route registration.
Teammates do not write context docs, do not prod-probe, do not deploy.

=== Teammate 1 (TM1) — docs only ===
Create docs/coordination/AGENT_TEAMS_CANARY.md that:
- States C1 purpose (coordination consistency, not a feature)
- References the SSOT path explicitly
- Includes a "Frozen" section that is RENDERED from scripts/canary_frozen.py
  (paste the CLI output or include instruction "run canary_frozen.py"; do not hand-type paths)
- Documents stop rule + pass rule from the SSOT (by reference, not a second invented list)
- Notes: shared task list ≠ file lock; first-route-wins; lead owns merge/verify
Do NOT edit tests/. Do NOT edit the SSOT YAML.

=== Teammate 2 (TM2) — tests only ===
Create tests/test_agent_teams_canary_contract.py that:
- Imports/loads scripts/canary_frozen.py (SSOT) — never hardcodes the frozen path list
- After TM1 merges (or against expected path), asserts AGENT_TEAMS_CANARY.md exists and
  CONTAINS each frozen_paths entry from the SSOT (string presence) OR contains the SSOT
  path + render marker — prove the doc is coupled to SSOT, not a pasted twin
- Asserts branch_prefix from SSOT appears in the doc
- Asserts max_teammates == 2 from SSOT
If the test is RED because TM1 doc disagrees with SSOT, that is a canary SIGNAL —
do not weaken asserts. Lead will surface the disagreement.
Do NOT edit docs/coordination/AGENT_TEAMS_CANARY.md. Do NOT edit the SSOT YAML.

=== Lead ===
- MERGE ORDER IS FIXED: **TM1 first, then TM2**. Do not merge TM2 before TM1 —
  without the doc, TM2 cannot fire the semantic-coupling signal (RED/GREEN is noise).
- TM2 may finish writing its test early; still hold the merge until TM1 is in.
- Resolve conflicts. Stop if >1 conflict file.
- Verify AFTER both merges: pytest tests/test_canary_frozen_ssot.py tests/test_agent_teams_canary_contract.py -q
  + scripts/prod_check.py + scripts/check_secrets.py + duplicate-route clean
- PASS only if TM1→TM2 merged + verify green + TM2 reads SSOT (not a paste)
- RED TM2 vs TM1 after merge = SIGNAL (record in SESSION_HANDOFF), not a silent pass
- After run: record ACTUAL quota burn (lead+tm1+tm2 tokens/cost + wall clock + plan tier)
  into SESSION_HANDOFF — replace the ~3× estimate with measured numbers
- Label discipline: scaffolding pytest greens from setup are NOT "canary PASS"
```

## After-run quota note template (lead fills)

```text
Canary C1 quota (measured):
- plan_tier:
- lead:
- tm1:
- tm2:
- wall_clock_minutes:
- decision_for_next_run: keep 2 | try 3 on Max | abort parallel
```
