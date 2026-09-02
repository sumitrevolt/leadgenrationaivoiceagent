# Upstream issue DRAFT — greenlet `green_is_gc` NULL `pimpl` dereference

**STATUS: OWNER REVIEW ONLY — do NOT submit externally without approval.**
Prepared 2026-08-10 (Cursor PR #302 remediation / fallback).

## Summary

On CPython 3.12 (non-free-threaded), greenlet 3.5.4 can SIGSEGV inside
`green_is_gc` when a `PyGreenlet` remains GC-tracked after its `pimpl` has been
nulled during thread / event-loop teardown.

## Proven (instruction / source level)

- greenlet 3.5.4 `src/greenlet/PyGreenlet.cpp`:
  - `green_traverse` guards: `if (!self->pimpl) return 0;`
  - `green_is_gc` does **not** mirror that guard; it calls `main()`, `active()`,
    and `was_running_in_dead_thread()` via `BorrowedGreenlet`.
- gdb (Linux CI-equivalent container, PR #302 forensics): faulting instruction
  loads `pimpl` then dereferences NULL (`rdi == 0`).
- Trigger surface observed under pytest 9 `gc_collect_harder` / gen-2 GC during
  large pytest-asyncio 1.4.0 suites.

## Not proven

- Exact application test/fixture lifecycle that leaves the invalid greenlet.
- Standalone minimal reproducer (bounded experiments clean).

## Suggested discussion patch (diagnostic only)

Mirror the `green_traverse` NULL check at the top of `green_is_gc` so GC can
skip / treat a greenlet with `pimpl == NULL` safely instead of crashing.
Private forks/wheels must not be production dependencies.

## Environment

- greenlet==3.5.4 (latest PyPI as of 2026-08-10; no newer release)
- CPython 3.12
- pytest==9.0.3 + pytest-asyncio==1.4.0 (advisory GHSA-6w46-j5rx-g56g requires ≥9.0.3)
- Repro: Linux GitHub Actions / Docker; Windows does not reproduce
