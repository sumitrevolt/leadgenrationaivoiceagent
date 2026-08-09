# C1b — Claude Code Agent Teams prediction (LOCKED BEFORE RUN)

**Registered:** 2026-08-08 · prediction tip `4c151bde`+ · PR #283  
**Status:** PREDICTION-LOCKED · Claude Code Agent Teams canary **NOT-RUN**  
**Rule:** Fill **Observed** only after the Windows Claude Code run. Do not edit Predictions post-hoc.

## Validity gate (P1 confound — DECISIVE)

Cursor remediation already put `AGENT_TEAMS_CANARY.md` (with `branch_prefix` / `agent/tm`) and
`tests/test_agent_teams_canary_contract.py` on **PR #283**. Those files are **absent** on
`origin/main` @ `5ae5a4b9` (verified 2026-08-08).

| If Claude AT canary runs… | P1 status |
|---------------------------|-----------|
| **Before #283 merges**, worktrees `--base origin/main` (doc+test absent) | **VALID** |
| **After #283 merges** to main (remediated doc+test already present) | **INVALID / CONTAMINATED** — teammates have nothing left to disagree about; “no SIGNAL” must **not** be read as “task list propagated conventions” |

**Do not merge PR #283 until the Claude Code canary finishes** (or accept P1 as void).

If somehow main already contains the artifacts, do **not** invent a story — mark
`p1_validity: contaminated` and skip P1 interpretation. Pinning an old SHA while filenames
collide on merge is messy; prefer the before-merge path.

**R3 note (clean):** TM1/TM2 brief text in the lead prompt was not quietly taught
`branch_prefix` via Cursor remediation. Confound is **artifact presence on base**, not brief drift.

## What Cursor C1 already proved (do not re-claim)

| Proven | Not proven |
|--------|------------|
| SSOT coupling (doc render / test read) | Agent Teams **shared task list** mediates teammate disagreement |
| Merge order TM1→TM2 | Claude Code quota / coordination-overhead cost of 2 vs 3 teammates |
| F4 fail-not-skip | That task list prevents a `branch_prefix`-class miss |
| F1 frozen diff check | |
| Lead remediation without weakening test (SIGNAL handled correctly) | |

Cursor harness had **no** Agent Teams shared task list between TM1/TM2. SIGNAL firing there proves the **protocol**, not task-list mediation.

## Pre-registered predictions (Claude Code run)

### P1 — shared task list vs SIGNAL

**Question:** On a **valid** Claude Code Agent Teams C1 (paste `CANARY_LEAD_PROMPT.md`, base = clean `origin/main` without C1 artifacts), after TM1→TM2 merge, does TM2 contract go RED for a semantic miss — i.e. **CANARY-SIGNAL** again?

| If observed (only if `p1_validity=valid`) | Interpretation (pre-committed) |
|-------------|------------------------------|
| **SIGNAL fires again** | Shared task list is **advisory in practice**. Real safety = worktree isolation + SSOT + contract test + lead check. Keep protocol; do **not** trust task list alone; do not raise teammate count on “task list will keep them aligned.” |
| **SIGNAL does not fire** (first-pass GREEN on coupling asserts) | Task list **did** propagate conventions in this run. Evidence supports considering teammate count ↑ later (still gated by burn/overhead). One clean run ≠ permanent; re-check on next wave. |
| **`p1_validity=contaminated`** | **No P1 conclusion.** Do not claim task-list success or failure. |

**Prediction owner note:** Either valid outcome is informative. Do not rewrite this table after seeing the result.

**Observed (fill after run only):**
- base_ref: _pending (must record — e.g. `origin/main` @ `5ae5a4b9` or whatever `git rev-parse origin/main` was at start)_
- p1_validity: _pending (`valid` if base lacks both C1 artifacts; else `contaminated`)_
- canary_doc_absent_on_base: _pending (yes/no)_
- contract_test_absent_on_base: _pending (yes/no)_
- signal_fired: _pending_
- miss_description: _pending_
- tip_sha: _pending_

### P2 — burn / overhead (F7 still open)

Cursor wall ~56s + `per_teammate_burn_available=false` does **not** inform 2 vs 3 teammates. Claude Code run must measure:

**Before paste (baseline):**
- plan_tier: _pending (Pro|Max|other)_
- account_usage_note: _pending (whatever UI shows — % / resets / messages)_
- clock_start_iso: _pending_

**After verify (delta):**
- clock_end_iso: _pending_
- wall_clock_minutes: _pending_
- usage_delta_note: _pending (baseline → after; total session burn)_
- per_teammate_burn_available: false|_true if UI splits_
- decision_for_next_run: keep_2 | try_3_on_max | abort_parallel

**Pre-committed decision rule:**
- If wall clock / usage delta feels light on Max and P1 = no signal **and** `p1_validity=valid` → may trial 3 on a later non-critical canary.
- If Pro window burns hard or wall clock shows heavy coordination tax → stay at 2.
- If `per_teammate_burn_available=false`, decide on **total delta + wall clock only** — do not invent per-tm splits.
- If `p1_validity=contaminated`, ignore P1 for teammate-count decisions; P2 burn still usable.

## Owner Windows checklist (still required)

1. `git worktree prune` (pending)
2. Confirm PR #283 is **not** merged yet; `git fetch` + verify main lacks both C1 files
3. Note P2 baseline **before** pasting the lead prompt
4. Paste `docs/coordination/CANARY_LEAD_PROMPT.md` (worktrees `--base origin/main`)
5. Fill **Observed** (including **`base_ref`** + **`p1_validity`**) — never rewrite Predictions
6. Only then merge #283 (or consciously void P1)
