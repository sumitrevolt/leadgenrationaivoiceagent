#!/usr/bin/env python3
"""Lane C diagnostic: inspect greenlet green_is_gc asymmetry + optional NULL guard.
Scratch only — never ship a private fork/wheel in the PR.
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import textwrap

OUT = pathlib.Path("scratch/pytest9_matrix")
OUT.mkdir(parents=True, exist_ok=True)


def find_greenlet_src() -> pathlib.Path | None:
    try:
        import greenlet

        root = pathlib.Path(greenlet.__file__).resolve().parent
    except Exception as exc:
        (OUT / "C_greenlet_import.txt").write_text(f"import_fail={exc}\n", encoding="utf-8")
        return None
    # source may be in greenlet/ / greenlet/TGreenlet.cpp etc after sdist unpack
    candidates = list(root.rglob("*Greenlet*.cpp")) + list(root.rglob("*greenlet*.c"))
    (OUT / "C_greenlet_paths.txt").write_text(
        "\n".join(str(p) for p in candidates[:50])
        + f"\nmodule={greenlet.__file__}\nver={getattr(greenlet, '__version__', '?')}\n",
        encoding="utf-8",
    )
    return root


def dump_is_gc_snippet(root: pathlib.Path) -> None:
    hits = []
    for path in root.rglob("*"):
        if path.suffix.lower() not in {".cpp", ".c", ".h", ".hpp"}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if "green_is_gc" in text or "green_traverse" in text:
            hits.append(path)
    lines = [f"hits={len(hits)}"]
    for path in hits[:20]:
        lines.append(f"FILE {path}")
        text = path.read_text(encoding="utf-8", errors="ignore")
        for i, line in enumerate(text.splitlines(), 1):
            if "green_is_gc" in line or "green_traverse" in line or "pimpl" in line:
                lines.append(f"{i}:{line}")
    (OUT / "C_green_is_gc_scan.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_upstream_issue_draft() -> None:
    draft = textwrap.dedent(
        """\
        # Upstream issue DRAFT — greenlet green_is_gc NULL pimpl dereference
        STATUS: OWNER REVIEW ONLY — do not submit externally without approval.

        ## Summary
        On CPython 3.12 (non-free-threaded), greenlet 3.5.4 can segfault in
        `green_is_gc` when a `PyGreenlet` remains GC-tracked after its `pimpl`
        has been nulled during thread/loop teardown.

        ## Proven facts
        - Faulting instruction: after `mov 0x20(%rbx), %rdi` (load `pimpl`),
          `cmpq $-1, 0x40(%rdi)` with `rdi == 0` → SIGSEGV.
        - `green_traverse` already guards `if (!self->pimpl) return 0;`
        - `green_is_gc` does not mirror that guard.
        - Trigger observed under pytest 9 `gc_collect_harder` / gen-2 GC during
          large pytest-asyncio 1.4.0 suites that destroy many event loops while a
          long-lived SQLAlchemy async engine/pool still holds greenlets.
        - Minimal standalone reproducer: NOT achieved.
        - Windows does not reproduce; Linux CI/container does (nondeterministic).

        ## Not proven
        - Exact test/fixture that leaves the invalid greenlet.
        - Whether the missing NULL guard is the only defect vs an earlier UAF.

        ## Suggested upstream patch (diagnostic discussion)
        Mirror the `green_traverse` NULL check in `green_is_gc` so GC can treat
        a greenlet with `pimpl == NULL` as non-GC / safely skip, instead of
        crashing. Guarded builds are diagnostic-only until reviewed upstream.

        ## Environment
        - greenlet==3.5.4 (latest PyPI as of 2026-08-10)
        - CPython 3.12
        - pytest==9.0.3 + pytest-asyncio==1.4.0
        """
    )
    (OUT / "UPSTREAM_GREENLET_ISSUE_DRAFT.md").write_text(draft, encoding="utf-8")


def build_guarded_note() -> None:
    note = textwrap.dedent(
        """\
        Lane C plan:
        1. Behavior-identical instrumented build = stock greenlet 3.5.4 rebuilt
           from sdist with debug symbols (`CFLAGS=-g -O0`).
        2. Experimental reviewed NULL guard in green_is_gc (diagnostic wheel only).
        3. Compare stock vs guarded under shard-1 / full suite.
        4. NEVER depend on private fork/wheel in the mergeable PR.
        5. If guarded build eliminates exit-139 while stock crashes → evidence
           for upstream defect; keep draft for owner submission.

        This host run only prepares the draft + source scan. Full ASan/guarded
        rebuild requires Linux container with build-essential + greenlet sdist.
        """
    )
    (OUT / "C_plan.txt").write_text(note, encoding="utf-8")


def main() -> int:
    root = find_greenlet_src()
    if root is not None:
        dump_is_gc_snippet(root)
    write_upstream_issue_draft()
    build_guarded_note()
    print("LANE_C_PREP_DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
