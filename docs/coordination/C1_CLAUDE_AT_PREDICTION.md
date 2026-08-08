# C1b — Claude Code Agent Teams prediction (LOCKED BEFORE RUN)

**Registered:** 2026-08-08 · tip `96bba2b2` · PR #283  
**Status:** PREDICTION-LOCKED · Claude Code Agent Teams canary **NOT-RUN**  
**Rule:** Fill **Observed** only after the Windows Claude Code run. Do not edit Predictions post-hoc.

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

**Question:** On a fresh Claude Code Agent Teams C1 (paste `CANARY_LEAD_PROMPT.md`), after TM1→TM2 merge, does TM2 contract go RED again for a semantic miss (SSOT field omitted / wrong convention) — i.e. **CANARY-SIGNAL** again?

| If observed | Interpretation (pre-committed) |
|-------------|------------------------------|
| **SIGNAL fires again** | Shared task list is **advisory in practice**. Real safety = worktree isolation + SSOT + contract test + lead check. Keep protocol; do **not** trust task list alone; do not raise teammate count on “task list will keep them aligned.” |
| **SIGNAL does not fire** (first-pass GREEN on coupling asserts) | Task list **did** propagate conventions in this run. Evidence supports considering teammate count ↑ later (still gated by burn/overhead). One clean run ≠ permanent; re-check on next wave. |

**Prediction owner note:** Either outcome is informative. Do not rewrite this table after seeing the result.

**Observed (fill after run only):**
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
- If wall clock / usage delta feels light on Max and P1 = no signal → may trial 3 on a later non-critical canary.
- If Pro window burns hard or wall clock shows heavy coordination tax → stay at 2.
- If `per_teammate_burn_available=false`, decide on **total delta + wall clock only** — do not invent per-tm splits.

## Owner Windows checklist (still required)

1. `git worktree prune` (pending — sandbox cannot clear Windows metadata)
2. Note P2 baseline **before** pasting the lead prompt
3. Paste `docs/coordination/CANARY_LEAD_PROMPT.md` in Claude Code Agent Teams
4. Fill **Observed** above + `SESSION_HANDOFF` — never rewrite Predictions
