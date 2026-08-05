#!/usr/bin/env python3
"""LeadGen changed-skill CI ratchet.

The canonical catalog has pre-existing lint/security/routing debt. Running the
upstream tools against every skill would make unrelated PRs permanently red.
This runner keeps the checks strict for every added or modified skill and
compares its description against the complete catalog.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import run_trigger_evals
import skill_lint
import skill_scanner

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DEFAULT_SKILLS_ROOT = REPO / ".claude" / "skills"
DEFAULT_EVALS_ROOT = HERE / "cases"
ZERO_SHA = "0" * 40


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def changed_skill_names(repo: Path, skills_root: Path, base_ref: str) -> tuple[set[str], set[str]]:
    """Return (changed, newly-added) top-level canonical skill names."""
    base_ref = (base_ref or "").strip()
    if not base_ref or base_ref == ZERO_SHA:
        parent = _git(repo, "rev-parse", "--verify", "HEAD^")
        if parent.returncode != 0:
            raise RuntimeError("no CI base ref and HEAD has no parent")
        base_ref = parent.stdout.strip()

    verify = _git(repo, "rev-parse", "--verify", f"{base_ref}^{{commit}}")
    if verify.returncode != 0:
        raise RuntimeError(
            f"base ref {base_ref!r} is unavailable; checkout history with fetch-depth: 0"
        )

    try:
        rel_root = skills_root.resolve().relative_to(repo.resolve()).as_posix()
    except ValueError as exc:
        raise RuntimeError("skills root must be inside the repository") from exc

    def names_for(diff_filter: str) -> set[str]:
        proc = _git(
            repo,
            "diff",
            "--name-only",
            f"--diff-filter={diff_filter}",
            base_ref,
            "HEAD",
            "--",
            rel_root,
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or "git diff failed")
        names = set()
        prefix = rel_root.rstrip("/") + "/"
        for raw in proc.stdout.splitlines():
            path = raw.replace("\\", "/")
            if not path.startswith(prefix):
                continue
            tail = path[len(prefix) :]
            if "/" in tail:
                names.add(tail.split("/", 1)[0])
        return names

    return names_for("ACMRD"), names_for("A")


def run_checks(
    skills_root: Path,
    evals_root: Path,
    changed: set[str],
    added: set[str] | None = None,
) -> int:
    added = added or set()
    failures = 0
    existing = []

    if not changed:
        print("skill CI: no added or modified canonical skills")
        return 0

    print("skill CI: checking %s" % ", ".join(sorted(changed)))
    for name in sorted(changed):
        skill_dir = skills_root / name
        if not skill_dir.exists():
            print(f"SKIP  {name}: skill directory deleted")
            continue
        existing.append(name)

        errors, warnings = skill_lint.lint(str(skill_dir), strict=True)
        for message in errors:
            print(f"FAIL  {name} lint: {message}")
        for message in warnings:
            print(f"WARN  {name} lint: {message}")
        failures += len(errors)

        findings = skill_scanner.scan_skill(skill_dir)
        critical = [finding for finding in findings if finding.severity == "CRITICAL"]
        for finding in findings:
            verdict = "FAIL" if finding.severity == "CRITICAL" else "WARN"
            print(
                f"{verdict}  {name} {finding.check} {finding.file}:{finding.line}: "
                f"{finding.message}"
            )
        failures += len(critical)

        case_file = evals_root / name / "trigger-cases.json"
        if name in added and not case_file.is_file():
            print(f"FAIL  {name}: new skills require {case_file}")
            failures += 1

    if existing:
        failures += run_trigger_evals.evaluate(
            str(skills_root), str(evals_root), only=set(existing)
        )

    if failures:
        print(f"skill CI: FAIL ({failures} blocking finding(s))")
        return 1
    print("skill CI: PASS")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gate new/modified LeadGen agent skills.")
    parser.add_argument("--base-ref", default="")
    parser.add_argument("--skills-root", type=Path, default=DEFAULT_SKILLS_ROOT)
    parser.add_argument("--evals-root", type=Path, default=DEFAULT_EVALS_ROOT)
    parser.add_argument("--skill", action="append", default=[], metavar="NAME")
    parser.add_argument("--added", action="append", default=[], metavar="NAME")
    args = parser.parse_args(argv)

    skills_root = args.skills_root.resolve()
    evals_root = args.evals_root.resolve()
    try:
        if args.skill:
            changed, added = set(args.skill), set(args.added)
        else:
            changed, added = changed_skill_names(REPO, skills_root, args.base_ref)
    except RuntimeError as exc:
        print(f"skill CI usage error: {exc}", file=sys.stderr)
        return 2
    return run_checks(skills_root, evals_root, changed, added)


if __name__ == "__main__":
    raise SystemExit(main())
