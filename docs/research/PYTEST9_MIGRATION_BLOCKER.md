# PYTEST 9 MIGRATION — BLOCKER (2026-08-10, Cursor remediation closeout)

> **Re-check 2026-08-17 (Freebuff loop):** blocker still stands. PyPI check: greenlet latest = **3.5.5** (2026-08-10) — its only change is static MSVCP140.dll linking into Windows wheels (`CHANGES.rst`), **no NULL-pimpl guard in `green_is_gc`**. 3.5.6 unreleased ("Nothing changed yet"). Go-condition for a new pytest-9 PR ("greenlet >3.5.4 with NULL guard") is **not satisfied**; do not open the PR. pytest exception (GHSA-6w46-j5rx-g56g) stays valid until 2026-11-08. Next re-check trigger: a greenlet release carrying the guard, or owner decision. Dependabot still lists 22 stale uv.lock alerts (re-scan lag after the 2026-08-16 uv.lock deletion merged at `7156b61b`); they are repo-side gone.

**Status: BLOCKED / SUPERSEDED for merge.** Safe official-dependency remediation was **not** achieved. PR #302 (pytest 9 migration) remains unmergeable; main keeps the time-limited pytest exception (expires **2026-11-08**). This document is forensic evidence only — no dependency pins change here.

## Evidence language (corrected)

| Claim | Status |
|---|---|
| Crash instruction is greenlet `green_is_gc` NULL-`pimpl` dereference | **PROVEN** (gdb + source asymmetry) |
| Exact project test/fixture lifecycle that leaves the invalid object | **NOT PROVEN** |
| Standalone minimal reproducer | **NOT ACHIEVED** |
| Retry / `-p no:unraisableexception` / incomplete exit-1 run | **NOT green proof** |

## Fresh SHAs (Cursor re-probe 2026-08-10)

- `origin/main`: `78e32f95`
- PR #302 head: `4a3ebd3b` (Draft + BLOCKED; `prod_check + pytest` exit 139 on CI)
- Primary dirty checkout preserved; work done in isolated Cursor worktrees

## Root cause (proven chain)

1. **Native crash site:** greenlet 3.5.4 `src/greenlet/PyGreenlet.cpp`
   - `green_traverse` guards `if (!self->pimpl) return 0;`
   - `green_is_gc` does **not**; it calls `main()` / `active()` / `was_running_in_dead_thread()` via `BorrowedGreenlet`
2. **Trigger (not creator):** pytest 9 session-end `gc_collect_harder` / gen-2 GC makes the crash near-deterministic on Linux CI; mid-run gen-2 also possible.
3. **Who creates the bad object (hypothesis, not isolated):** pytest-asyncio 1.4.0 per-test loops + long-lived SQLAlchemy async engine greenlets across many loop teardowns. Minimal plain-SQLAlchemy stress (400 function-scoped `asyncio.Runner`s + NullPool) **exit 0** — full-suite interaction still required.

## Lane A — Secure dependency matrix (2026-08-10)

Official GHSA-6w46-j5rx-g56g / CVE-2025-71176:

- vulnerable: `< 9.0.3`
- first patched: **`9.0.3` only** (no 8.x backport)

| Candidate | Version | Advisory OK | `pip install` | `pip check` | Decision |
|---|---|---|---|---|---|
| Lowest secure | pytest 9.0.3 + pytest-asyncio 1.4.0 + greenlet 3.5.4 | YES | exit 0 | exit 0 | allowed floor |
| Latest 9.x | pytest 9.1.1 + same | YES | exit 0 | exit 0 | allowed |
| Latest 8.x | pytest 8.4.2 + pytest-asyncio 0.26.0 | **NO** | exit 0 | exit 0 | **REJECT — insecure downgrade forbidden** |
| greenlet | 3.5.4 latest on PyPI | n/a | — | — | **no newer release** |

**Conclusion:** Dependabot's four pytest alerts require pytest ≥ 9.0.3. There is no secure pytest 8 stay-path. ecdsa GHSA-wj6h-64fc-37mp remains separate (no patched version; main exception intact).

## Lane B — Async lifecycle (Linux Docker shard 1/4)

| Variant | Shard 1 exit | Segfault signature | Notes |
|---|---|---|---|
| B0 function loops (pytest-asyncio 1.4 default) | **1** | **no** (this run) | Failures = missing `git`/bootstrap env in slim image — **not** green proof |
| B1 session loops (`asyncio_default_*_loop_scope=session`) | **1** | **no** (this run) | Same class of failures; **no durable green** |
| B-lite stress function Runner×400 | **0** | no | Does not reproduce suite crash |
| B-lite stress session single-loop×400 | **0** | no | Does not reproduce suite crash |

CI on PR #302 (`31341700583`): shard 1 **exit 139 twice** (retry block). Container nondeterminism (~50–60% historically) means one non-crash run ≠ fix.

Production pooling was **not** altered.

## Lane C — Greenlet instrumentation

- Source asymmetry extracted from official `greenlet==3.5.4` sdist: traverse guards NULL `pimpl`; `green_is_gc` does not.
- Guarded/private wheel **diagnostic-only** — **not** allowed as a merge dependency.
- Upstream issue draft prepared for **owner review** (not submitted externally): `docs/research/GREENLET_UPSTREAM_ISSUE_DRAFT.md`

## Why PR #302 is terminalized (not merged)

Merge gate requires official stock deps, normal GC plugins, no retry masking, 5× shard-1 green, 2× full workflow green, billing/UPI/async contracts, floors, prod_check/secrets/lint — **none of the crash-free durable path cleared**. Shipping pytest 9 without a fixed greenlet (or proven lifecycle fix) would replace a documented exception with a red required CI check.

## Main posture (unchanged)

- pytest remains **7.4.4** on main with EXCEPTIONS entry GHSA-6w46-j5rx-g56g expiry **2026-11-08**
- Do **not** dismiss Dependabot pytest alerts
- Do **not** merge `-p no:unraisableexception` or `PYTHONMALLOC=malloc` as “fixes”
- Production deploy: **NOT AUTHORIZED** for this slice

## Next owner actions

1. Review/submit upstream greenlet issue draft (or wait for greenlet >3.5.4 with NULL guard).
2. After upstream fix (or proven session-lifecycle fix with merge-gate evidence), open a **new** pytest 9 PR — do not revive #302 blindly.
3. Before 2026-11-08: re-justify or remediate the pytest exception.
