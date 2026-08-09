# PYTEST 9 MIGRATION — BLOCKER (2026-08-10, forensic update)

**Status: BLOCKED — NOT MERGEABLE.** Root cause of the exit-139 is now **NATIVE-ATTRIBUTED** (greenlet, instruction level — see below); the exact in-suite trigger remains full-suite-interaction-only and no minimal deterministic reproducer was found after bounded experiments. PR #302 stays DRAFT+BLOCKED. The exception/expiry for GHSA-6w46-j5rx-g56g on `main` remains **intact** (main untouched: `78e32f95`, green).

## Reproduction artifact

PR #302 (branch `freebuff/pytest9-compat-20260810`) → check `prod_check + pytest` run:
`https://github.com/sumitrevolt/leadgenrationaivoiceagent/actions/runs/31334119347/job/93297050409`

Log evidence (both runs of shard 1/4, identical pattern):
```
pytest shard 1/4  ... 98% tests pass (all dots/skips, zero failures) ...
Fatal Python error: Segmentation fault
Current thread ... (most recent call first):
  Garbage-collecting
  File ".../_pytest/unraisableexception.py", line 33 in gc_collect_harder
  File ".../_pytest/unraisableexception.py", line 94 in cleanup
...
Segmentation fault (core dumped) pytest -m "not network" -q --no-header -p no:cacheprovider --timeout=60 --splits 4 --group ...
##[error]Process completed with exit code 139.
```
(The ci.yml retry-on-139 block, present on `main` since before PR #302, retried shard 1 once; both attempts crashed identically → deterministic on CI.)

## Root-cause analysis (forensic update 2026-08-10)

1. **Reproduced in a CI-equivalent Linux container** (Docker `python:3.12-slim` + filtered `requirements.lock.txt` + torch CPU + pytest-timeout/pytest-split — same as ci.yml). Exit 139, same `green_is_gc` crash. Nondeterministic: CI 2/2, container ~50-60% (crash point ~85% mid-run OR session-end `gc_collect_harder`). Windows does NOT reproduce.
2. **Native attribution (gdb disassembly + registers):** the crash is greenlet 3.5.4's `green_is_gc` dereferencing a **NULL `pimpl`** pointer:
   - `PyGreenlet` layout: `pimpl` at offset `0x20`. `green_is_gc` does `mov 0x20(%rbx),%rdi` then `cmpq $-1,0x40(%rdi)` with **no NULL guard**; stop-time `rdi == 0x0`; faulting PC = that `cmpq` (function offset 0x21).
   - greenlet source confirms the asymmetry: `green_traverse` guards `if (!self->pimpl) return 0;` but `green_is_gc` does **not**.
3. **Who creates the NULL-pimpl greenlet:** a greenlet whose owning thread/loop state was torn down (greenlet nulls `pimpl` on thread-state destruction) while the Python object stays alive + GC-tracked — under pytest-asyncio 1.4.0's per-test `asyncio.Runner` loops with the app's module-level singleton async engine (`app/models/base.py::_async_engine`, pool 5) crossing ~2000 loops. pytest 7.4.4 + pytest-asyncio 0.23.4 (session-scoped loop) never tore down per-test loop state → main stays green (rare exit-139 = interpreter-shutdown GC of the same class, hence main's pre-existing retry block in ci.yml).
4. **Pytest's role: trigger, not creator of the crash site.** pytest 9's new session-end `gc_collect_harder` makes the final GC near-deterministic; automatic gen-2 GC mid-run also crashes occasionally. `-p no:unraisableexception` (diagnostic only) → no session-end crash; `PYTHONMALLOC=malloc` → no crash at all (heap-state-sensitive). `PYTHONMALLOC=debug` reports no allocator overrun → not a plain buffer overflow; the damage is in the tracked-greenlet list.
5. **Upstream status: NO FIX AVAILABLE.** greenlet 3.5.4 is the current release (3.5.5 unreleased, empty); all recent greenlet GC fixes (3.5.2/3.5.3/3.5.4) target free-threaded Python 3.14/3.15 builds only. An upstream issue draft is prepared for owner submission (not filed externally).
6. **Eliminated candidates:** `pyarrow`/`pandas`/`lxml` (NOT loaded in the container crash runs — 101 vs 152 modules); plain SQLAlchemy async patterns (leak, in-loop dispose, cross-loop dispose, 300-loop singleton reuse, 60 leaked connections, 30 dead-thread greenlets incl. suspended, 200 `asyncio.Runner` loops + cross-loop dispose — all exit 0); SIGPIPE (gdb false positive, ruled out).

## What is proven / not proven

| Item | Status |
|---|---|
| conftest modernization (no custom session event_loop; asyncio.run teardown) | correct + CI-validated on the new stack (crash is elsewhere) |
| pytest 9.0.3 + pytest-asyncio 1.4.0 + pytest-cov 7.1.0 compat at test level | PROVEN (local suites exit 0; CI tests pass to 98%) |
| Native crash attribution | **PROVEN — greenlet 3.5.4 `green_is_gc` NULL-`pimpl` dereference** (gdb disassembly + registers) |
| Minimal deterministic standalone reproducer | **NOT ACHIEVED** (8 bounded experiments clean; trigger = full-suite interaction) |
| Full Linux suite with default plugins | **BROKEN (exit-139, nondeterministic)** |
| Dependabot pytest alerts fixable in this slice | **NO — BLOCKED** (upstream greenlet defect, no fixed release) |

## Done in the forensics slice (2026-08-10)

- CI-equivalent Linux container repro (exit 139) + `PYTHONMALLOC=malloc` (clean) + `-p no:unraisableexception` (clean) + gdb native backtraces (incl. the SIGPIPE false positive, ruled out).
- Native attribution at instruction level (see above); eliminated pyarrow/pandas/lxml, plain SQLAlchemy async, thread-death and suspended-greenlet leak patterns, and OOB-write (debug allocator).
- Crash-point mapping (85% mid-run, container; 98% session-end, CI) and group-1/4 node-list computation; subset bisection attempted (files 625-650 clean → trigger needs broader context).
- Loaded native-extension inventory at crash (101 modules) — pyarrow/pandas/lxml absent.

## Remaining options for the next owner-funded slice

1. File the upstream greenlet issue (draft prepared) — NULL-`pimpl` guard missing in `green_is_gc` vs `green_traverse`.
2. Binary-search the full group-1 file list under `gc.collect()`-after-each (slow: ~25 min/run) to isolate the exact corrupting test; or run group 1 repeatedly under ASan-built greenlet (needs `--no-binary greenlet` rebuild + `LD_PRELOAD=libasan`) to capture the alloc/free history of the NULL-pimpl greenlet.
3. Deterministically dispose the app's singleton async engine AND drain aiosqlite worker threads at session end on the SAME loop pattern the tests use (cross-loop teardown guard already exists; extend it to cover the engine's pooled connections before loop teardown) — if the NULL-pimpl greenlet disappears, the fix is fixture-level, not a dependency change.
4. Only then re-run the full CI matrix repeatedly (3× green) and merge.

## Do-nots
- Do NOT merge with `-p no:unraisableexception` as the permanent fix (hides the latent leak; violates the repo's root-cause-first security ethos).
- Do NOT dismiss the 4 pytest Dependabot alerts — the exception (expiry 2026-11-08) stays valid.
- Do NOT weaken scanners or add suppressions.
- Do NOT speculate a greenlet version bump: 3.5.4 IS the latest release; there is no fixed version to move to.

## Files touched by the blocked PR (for the next slice)
`tests/conftest.py` · `requirements*.txt` (4) · `tests/test_dependency_security_floors.py` · `.github/workflows/ci.yml` · `docs/security/DEPENDENCY_REMEDIATION_2026-08-08.md`
