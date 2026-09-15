"""Contract: every path a workflow runs or reads exists in the COMMITTED tree.

WHY THIS FILE EXISTS (2026-09-15, real incident)
------------------------------------------------
``.github/workflows/hermes-harness.yml`` runs
``python scripts/hermes_harness_contract.py``. That script was written, was on
disk, and even passed locally — but it was **never committed** (``git ls-files``
did not know it). A GitHub runner checks out the committed tree only, so every
run died in 12 seconds with:

    python: can't open file '.../scripts/hermes_harness_contract.py': [Errno 2]

This failed on BOTH triggers — the ``push`` path filter and the DAILY cron — so
the gate was permanently red and the Hermes integration surface had no coverage
at all. Two independent runs (2026-09-14T16:36Z, 2026-09-15T08:25Z) confirmed it.

The nasty part is the failure mode: **a local-only file looks fine.** Running the
script by hand passes, the path filter matches the file on disk, and nothing in
the existing suite (``test_ci_required_lanes.py`` checks lane wiring,
``test_workflow_guards.py`` checks governance flags) notices that the file is
absent from git. That is exactly the gap this module closes.

WHAT IT PINS
------------
1. Every repo-relative path referenced from workflow YAML (``run:`` bodies,
   ``paths:`` filters, ``with:`` values) exists on disk.
2. Every such path is **tracked** — the check that would have caught the
   incident, and the reason a pure ``Path.exists()`` test is not enough.
3. Every local composite action (``uses: ./.github/actions/<name>``) has a
   committed ``action.yml``.

The scanner is deliberately not vacuous: a floor test asserts it still finds a
realistic number of references, so a regex/parser regression fails loudly
instead of turning this file green-by-emptiness.

Scope note: this reads workflow TEXT only. It does not execute GitHub Actions.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

REPO = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO / ".github" / "workflows"

# Only paths that must exist in a checkout for a job to run or route correctly.
# Keep this closed: widening it to arbitrary extensions invites false positives
# from prose (e.g. "app/main.py" mentioned in a step name).
_REF = re.compile(
    r"(?<![\w./-])"
    r"((?:scripts|tests|docs|app|frontend|deploy)/[A-Za-z0-9_./-]+"
    r"\.(?:py|sh|ps1|bat|ya?ml|json|lock|txt))"
)

# Floor for the anti-vacuity test. Observed 23 refs across 11 workflows on
# 2026-09-15; set below that so normal workflow churn never trips it, but high
# enough that a parser break (→ 0-2 refs) fails.
_MIN_EXPECTED_REFS = 10


def _tracked_paths() -> set[str]:
    """Repo-relative tracked files, forward-slashed.

    Returns an empty set when git is unavailable; the caller SKIPS rather than
    asserting absence, because "git is missing" is not evidence of drift.
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO), "ls-files", "-z"],
            capture_output=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):  # pragma: no cover - env
        return set()
    return {p for p in out.decode("utf-8", "replace").split("\0") if p}


def _strings(node: object):
    """Yield every scalar string anywhere in a parsed-YAML structure."""
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for k, v in node.items():
            yield from _strings(k)
            yield from _strings(v)
    elif isinstance(node, (list, tuple)):
        for item in node:
            yield from _strings(item)
    # ints/bools/None carry no path information


@pytest.fixture(scope="module")
def workflow_refs() -> dict[str, set[str]]:
    """path -> set of workflow filenames that reference it."""
    assert WORKFLOWS.is_dir(), f"missing {WORKFLOWS}"
    refs: dict[str, set[str]] = {}
    for wf in sorted(WORKFLOWS.glob("*.y*ml")):
        # Parsing (not raw-regexing) drops comment blocks, so we assert only on
        # real references the runner will act on.
        data = yaml.safe_load(wf.read_text(encoding="utf-8")) or {}
        for s in _strings(data):
            for m in _REF.finditer(s):
                refs.setdefault(m.group(1), set()).add(wf.name)
    return refs


@pytest.fixture(scope="module")
def tracked() -> set[str]:
    paths = _tracked_paths()
    if not paths:
        pytest.skip("git unavailable — cannot verify tracked state")
    return paths


def test_scanner_finds_references(workflow_refs: dict[str, set[str]]) -> None:
    """Anti-vacuity: a broken parser must not make this module silently green."""
    assert len(workflow_refs) >= _MIN_EXPECTED_REFS, (
        f"only {len(workflow_refs)} workflow path references found "
        f"(expected >= {_MIN_EXPECTED_REFS}) — the reference scanner has "
        f"regressed; fix the scanner rather than lowering this floor."
    )


def test_referenced_paths_exist_on_disk(workflow_refs: dict[str, set[str]]) -> None:
    missing = sorted(p for p in workflow_refs if not (REPO / p).exists())
    assert not missing, (
        "workflow(s) reference paths that do not exist:\n"
        + "\n".join(f"  {p}  <- {', '.join(sorted(workflow_refs[p]))}" for p in missing)
    )


def test_referenced_paths_are_tracked_in_git(
    workflow_refs: dict[str, set[str]], tracked: set[str]
) -> None:
    """The incident guard.

    A file present locally but absent from git is invisible to every runner.
    """
    untracked = sorted(p for p in workflow_refs if p not in tracked)
    assert not untracked, (
        "workflow(s) reference files that are NOT committed — a GitHub runner "
        "checks out the committed tree only, so these jobs fail with Errno 2:\n"
        + "\n".join(
            f"  {p}  <- {', '.join(sorted(workflow_refs[p]))}" for p in untracked
        )
        + "\nFIX: `git add <path>` and commit it (or delete the workflow step)."
    )


def test_local_composite_actions_are_tracked(tracked: set[str]) -> None:
    """`uses: ./.github/actions/<name>` needs a committed action.yml."""
    problems: list[str] = []
    for wf in sorted(WORKFLOWS.glob("*.y*ml")):
        raw = wf.read_text(encoding="utf-8")
        for m in re.finditer(r"uses:\s*\./(\.github/actions/[A-Za-z0-9_-]+)", raw):
            rel = m.group(1)
            manifest = f"{rel}/action.yml"
            if not (REPO / rel).is_dir():
                problems.append(f"{wf.name}: {rel}/ does not exist")
            elif manifest not in tracked:
                problems.append(f"{wf.name}: {manifest} is not committed")
    assert not problems, "broken local composite action refs:\n  " + "\n  ".join(problems)
