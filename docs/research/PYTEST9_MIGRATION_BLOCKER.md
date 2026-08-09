# PYTEST 9 MIGRATION — BLOCKER (2026-08-10)

**Status: BLOCKED — NOT MERGEABLE in this slice.** The pytest 9 migration is correct as far as it goes (the 0.23-era cross-loop teardown hazard is fixed), but pytest 9's new session-end garbage-collection pass exposes a **latent C-extension object teardown crash** that must be root-caused before merge. The exception/expiry for GHSA-6w46-j5rx-g56g on `main` remains **intact** (main is untouched: `78e32f95`, green).

## Reproduction artifact

PR #302 (branch `freebuff/pytest9-compat-20260810`) → check `prod_check + pytest` run:
`https://github.com/sumitrevolt/leadgenrationaivoiceagent/actions/runs/31334119347/job/93297050409`

Log evidence (both shard 1 and shard 2, identical pattern):
```
pytest shard 1/4  ... 98% tests pass (all dots/skips, zero failures) ...
Fatal Python error: Segmentation fault
Current thread ... (most recent call first):
  Garbage-collecting
  File ".../_pytest/unraisableexception.py", line 33 in gc_collect_harder
  File ".../_pytest/unraisableexception.py", line 94 in cleanup
  File ".../contextlib.py", line 478 in _exit_wrapper
...
Segmentation fault (core dumped) pytest -m "not network" -q --no-header -p no:cacheprovider --timeout=60 --splits 4 --group ...
##[error]Process completed with exit code 139.
```

## Root-cause analysis

1. All tests **pass** (shards reach 98% with zero failures); the crash is at **session teardown** inside pytest's `unraisableexception` plugin `gc_collect_harder` — an aggressive double `gc.collect()` pytest added in 8.2+ and present in 9.x.
2. pytest 7.4.4 (main's current lock) has **no** `_pytest/unraisableexception.py` / `gc_collect_harder` — so the same latent defect never triggered on main. The migration did not *create* the defect; it **exposed** it.
3. The crashing object is a GC-tracked C-extension instance with a broken finalizer alive at session end — candidates in the CI env: `torch`, `av` (PyAV), `pyarrow`, `aiosqlite` worker threads, `pandas`/`numpy`. The exact object is not named in the log; faulthandler does not resolve it (it is a GC-collect crash, not a Python-frame crash).
4. This crash is independent of the conftest modernization (the same `gc_collect_harder` pattern appeared in the earlier pytest-9 attempt on unmodified conftest, PR #300 run). The cross-loop teardown fix (removing the custom session `event_loop`, `asyncio.run` teardown) was **necessary but not sufficient**.

## What is proven / not proven

| Item | Status |
|---|---|
| conftest modernization (no custom session event_loop; asyncio.run teardown) | correct + CI-validated on the new stack (crash is elsewhere) |
| pytest 9.0.3 + pytest-asyncio 1.4.0 + pytest-cov 7.1.0 compat at test level | PROVEN (local: revenue/async/scheduler/social suites exit 0; CI: tests pass to 98%) |
| Session-end teardown on Linux with the full C-extension load | **BROKEN (exit-139)** — latent GC object |
| Dependabot pytest alerts fixable in this slice | **NO — BLOCKED** |

## Next-step debugging plan (owner-funded slice)

1. Identify the crashing object: add a session-end diagnostic that snapshots `gc.get_objects()` (or `gc.get_referrers`) filtered to C-extension types before teardown, run on Linux CI, read the crash with `faulthandler` + `PYTHONMALLOC=malloc`.
2. Test `PYTHONMALLOC=malloc` on the shard command — if the crash disappears, the fault is allocator/GC interplay with a specific extension.
3. Use `-p no:unraisableexception` **only as a diagnostic** (not the fix) to confirm the crash is exclusively inside pytest's final GC pass.
4. Bisect the C-extension-heavy test files (torch/av/pyarrow users) to the leaking resource; close it deterministically at session end (same discipline as the aiosqlite #13039 fix).
5. Only then re-run the full CI matrix and merge.

## Do-nots
- Do NOT merge with `-p no:unraisableexception` as the permanent fix (hides the latent leak; violates the repo's root-cause-first security ethos).
- Do NOT dismiss the 4 pytest Dependabot alerts — the exception (expiry 2026-11-08) stays valid.
- Do NOT weaken scanners or add suppressions.

## Files touched by the blocked PR (for the next slice)
`tests/conftest.py` · `requirements*.txt` (4) · `tests/test_dependency_security_floors.py` · `.github/workflows/ci.yml` · `docs/security/DEPENDENCY_REMEDIATION_2026-08-08.md`
