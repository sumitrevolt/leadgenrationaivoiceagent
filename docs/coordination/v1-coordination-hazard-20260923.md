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

*Written 2026-09-23 by Hermes — for owner review.*
