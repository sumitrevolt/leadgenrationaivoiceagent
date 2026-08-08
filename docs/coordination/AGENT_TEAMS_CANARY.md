# Agent Teams Canary (C1)

**Purpose:** C1 is a **coordination consistency test** for Claude Agent Teams (TM1 doc + TM2 contract). It is **not** a product feature and must not be treated as shipping functionality.

**SSOT (single source of truth):** [`docs/coordination/canary_frozen_paths.yml`](canary_frozen_paths.yml)

Frozen paths, merge order, stop rule, and pass rule live **only** in that YAML. This doc references them; it does not invent a second path list or a second rule set.

Loader / check: `scripts/canary_frozen.py` · Protocol: `docs/runbooks/CLAUDE_AGENT_TEAMS.md`

**Branch convention (SSOT `branch_prefix`):** `agent/tm` — canary worktrees use
`agent/tm{1,2}/<slug>` via `scripts/agent_team_worktree.py create --canary --teammate {1,2}`.

> Lead note (CANARY-SIGNAL remediation): after TM1→TM2 merge, TM2 contract was RED because
> this doc omitted `branch_prefix` / `agent/tm`. Test was **not** weakened; doc updated to
> cite SSOT. That miss is the coupling signal working.

---

## Frozen

Paths below are **rendered** from the SSOT via `python3 scripts/canary_frozen.py render`. Do not hand-edit these bullets — re-run render if SSOT changes.

<!-- rendered from docs/coordination/canary_frozen_paths.yml — do not hand-edit paths -->

- `app/voice_agent/`
- `app/telephony/`
- `scripts/deploy_vps.sh`
- `app/billing/packages.py`

Policy classes (not diff-gated as paths — see SSOT `frozen_classes`): `env_files_gitignored`, `compliance_gates_section_5`, `fastapi_route_registration`.

---

## Stop rule + pass rule (by reference)

Do **not** duplicate rule text here as a second truth. Read these keys from the SSOT:

| SSOT key | Role |
|----------|------|
| `merge_order` | Fixed teammate merge sequence |
| `stop_rule` | When to abort canary → single-agent |
| `pass_rule` | What must hold for C1 PASS |

Enforcement before merge (lead, on **each** teammate branch):

```bash
python3 scripts/canary_frozen.py check --base origin/main --head HEAD
```

Exit 2 = frozen path touched → do not merge.

---

## Coordination notes

- **Shared task list ≠ file lock.** A coordinated todo does not replace buzzlock / path claims; teammates still must not edit each other's deliverables or frozen surfaces.
- **First-route-wins** (FastAPI): never register duplicate routes; route registration is lead-only policy (`fastapi_route_registration` in SSOT).
- **Lead owns merge + verify.** Teammates deliver only their scoped file; lead merges and runs verify.
- **Merge order:** TM1 then TM2 (see SSOT `merge_order`). Doc must land before the contract test can meaningfully go GREEN.

---

## F4 — TM2 missing-doc behaviour

If `docs/coordination/AGENT_TEAMS_CANARY.md` is missing, TM2's contract test must **`pytest.fail(...)`** with a clear message. **Never** `pytest.skip`, `skipif`, or `xfail` on a missing doc — that would fake safety and invalidate the canary.

---

## Labels (do not confuse)

- Scaffolding green (SSOT/loader helpers) ≠ canary PASS.
- Cursor **PROTOCOL-PASS** ≠ Claude Code Agent Teams CANARY-PASS.
- Pre-registered Claude AT predictions: [`C1_CLAUDE_AT_PREDICTION.md`](C1_CLAUDE_AT_PREDICTION.md) — fill Observed after that run only.

## Claude Code AT run (next) — validity

**Run before merging PR #283.** Worktrees `--base origin/main` while C1 doc+contract are
still absent on main. Record `base_ref` + `p1_validity` in
[`C1_CLAUDE_AT_PREDICTION.md`](C1_CLAUDE_AT_PREDICTION.md) Observed. If #283 already
merged, P1 is contaminated — do not read “no SIGNAL” as task-list success.
