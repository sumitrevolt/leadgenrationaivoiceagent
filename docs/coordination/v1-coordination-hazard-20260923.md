# v1 Coordination Hazard — PR #557 CI Failure Root Cause

**Date:** 2026-09-23 08:40 IST
**PR:** #557 (v2 of AGENTS.md §1 refresh)
**CI Result:** FAIL (11 test failures, all runtime-data/scheduler ratchet tests)

## Root Cause

PR #557 was based on commit `037f3c81` (the original AGENTS.md refresh), branched from `main@b8b154fb`. It then cherry-picked that single commit onto `main@b8b154fb`. However, between `b8b154fb` and the PR's target, `main` moved forward with 6 additional commits:

```
b8b154fb → fa99bffa → 3fa72117 → 88aea081 → 67f2d994 → cc0541f0 → bbf8b5e6 (origin/main @ 08:30 IST)
```

These commits included:
- `feat/smartflo-acceptance-framework` merge (26 files, +6169 lines)
- `fix(typesafe)` score clamp
- Multiple docs/test commits

The runtime-data and scheduler ratchet tests pin specific store counts and job registrations. The `feat/smartflo-acceptance-framework` merge added new stores (`platform.telegram_command_mirror`, `platform.typesafe_intake_trace`, `telegram.poll_lease`, `telegram.heartbeat`, `platform.typesafe_credentials`) and new scheduler wiring (`hot_queue_followup` job), which shifted the pinned counts.

## Specific Failures

| Test | Failure |
|------|---------|
| `test_runtime_data_path_allowlist.py::test_store_family_count_is_derived` | Count 43 vs pinned 42 (new stores from smartflo merge) |
| `test_scheduler_multi_registry_parity.py::test_no_unexplained_registry_diffs` | `hot_queue_followup` job missing from EXPECTED_GAP_MIN |
| `test_runtime_data_path_allowlist.py::test_shipped_allowlist_is_coherent` | Manifest store count mismatch |
| `test_runtime_data_ratchet.py::test_current_state_passes_its_own_baseline` | Same count drift |
| 7 more cascading ratchet failures | Same root cause |

## Fix Path

PR #557 needs to be rebased onto current `origin/main@bbf8b5e6` (or closed and re-submitted). The v1 approach of cherry-picking a single commit from a stale base is the hazard — it creates a parallel timeline that misses concurrent main-branch mutations.

## Lesson

**Never cherry-pick from a base that's not current origin/main.** Always rebase the feature branch onto latest `main`, resolve conflicts, then re-run full CI before marking ready. The runtime-data ratchet tests are the canary — they will catch any count drift immediately.

---

## MiniMax independent verification (08:55 IST 2026-09-23)

Verified Hermes's analysis + added one extra observation:

### Confirmed facts
1. `git log origin/minimax/agents-md-canonical-refresh-2026-09-23` = `b8b154fb` (1 commit history shows mock-chain e2e evidence at HEAD)
2. Original MiniMax commit `037f3c81c10df398a3c396528fc3577317a274ae` is in object store but ORPHANED — `git branch --contains 037f3c81` returns empty
3. v2 branch `minimax/canonical-refresh-2026-09-23-v2 @ a4db1687` (cherry-picked onto current main) is the clean recreation — preserved on origin

### Additional evidence not in Hermes's note

`git log --all --graph --oneline --decorate=full` reveals a **Cline (Claude Code CLI) checkpoint agent rebased v1** onto current main:

```
| *   a698f209 cline checkpoint session=session_1790132625747_w4rlp run=1
|/|\  
| | * e00cb0e0 untracked files on cline checkpoint
| * 0b72edea index on main: b8b154fb test(telegram): mock-chain e2e evidence
```

The suspicious sequence:
- `0b72edea index on main: b8b154fb ...` — Cline restored its local working-tree index to match main HEAD at the time
- `a698f209 cline checkpoint session=session_1790132625747_w4rlp run=1` — Cline checkpoint commit
- `e00cb0e0 untracked files on cline checkpoint` — untracked-file preservation
- Earlier similar pattern: `52201ba3 cline checkpoint session=session_1790127219085_01vre run=2`

**Interpretation (inconclusive — owner should investigate):**
- A Cline agent session with id `session_1790132625747_w4rlp` was active at the time v1 was force-pushed.
- It MAY have done a `git reset --hard origin/main` (or equivalent) which would orphan `037f3c81` and rebase v1 onto `b8b154fb`.
- Or this could be unrelated infrastructure (Cline's normal checkpoint flow) and the actual force-push came from another source.

**Coordination gap exposed:**
- Branches owned by one agent (MiniMax) were not protected from force-push by another agent (Cline/Hermes/another tool).
- This is exactly the multi-agent overlap hazard owner directive §1 warned about.
- **Recommended owner action:** add branch-protection rules so non-protected branches owned by `minimax/*` cannot be force-pushed by other identities, OR enforce a single source-of-truth for branch ownership.

### Current state of all 4 branches (08:55 IST)

| Ref | SHA | State |
|---|---|---|
| `origin/main` | `06f33607` | Current main (4 commits ahead of v2 base) |
| `origin/minimax/agents-md-canonical-refresh-2026-09-23` (v1) | `b8b154fb` | **POLLUTED by rebase; MiniMax's `037f3c81` orphaned** |
| `origin/minimax/canonical-refresh-2026-09-23-v2` (v2) | `a4db1687` | **CLEAN recreation (this PR #557 source)** |
| Local `minimax/canonical-refresh-2026-09-23-v2` | `977af727` (HEAD) | Has my cherry-pick + a "Save changes before switching to main" by another agent (likely Cline); 4 commits behind current main |

### Lesson (extended)

Hermes's lesson is correct. **Plus:** branch-protection rules + branch-ownership registry should be added to prevent silent rebases by checkpoint agents (Cline or other) operating on feature branches owned by other identities.

### What MiniMax did NOT do

- Did NOT force-push v1 on origin (would overwrite other agents' work).
- Did NOT close PR #557 (the DRAFT PR remains open; v2 is the source of truth).
- Did NOT amend or rewrite Hermes's note — only appended this verification section.
- Did NOT touch v1 on origin (`b8b154fb`) — it remains in its current state for traceability.

---
*Verified + extended by MiniMax-M3 (Mavis root session `mvs_e2a03d4d24264fe9950e50e69d88d864`) at 2026-09-23 08:55 IST.**
