#!/usr/bin/env python3
"""Load + enforce Agent Teams canary SSOT (docs/coordination/canary_frozen_paths.yml).

TM2 contract tests and lead tooling must import this — never paste frozen paths.

    python3 scripts/canary_frozen.py              # render markdown from SSOT
    python3 scripts/canary_frozen.py check --base origin/main --head HEAD
"""

from __future__ import annotations

import argparse
import fnmatch
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[1]
SSOT_PATH = REPO / "docs" / "coordination" / "canary_frozen_paths.yml"


@lru_cache(maxsize=1)
def load_canary_ssot() -> dict[str, Any]:
    if not SSOT_PATH.is_file():
        raise FileNotFoundError(f"missing canary SSOT: {SSOT_PATH}")
    data = yaml.safe_load(SSOT_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("canary SSOT must be a mapping")
    required = (
        "schema_version",
        "frozen_paths",
        "branch_prefix",
        "max_teammates",
        "pass_rule",
        "stop_rule",
        "merge_order",
    )
    missing = [k for k in required if k not in data]
    if missing:
        raise ValueError(f"canary SSOT missing keys: {missing}")
    if not isinstance(data["frozen_paths"], list) or not data["frozen_paths"]:
        raise ValueError("frozen_paths must be a non-empty list")
    return data


def frozen_paths() -> list[str]:
    return [str(p) for p in load_canary_ssot()["frozen_paths"]]


def frozen_classes() -> list[str]:
    return [str(c) for c in (load_canary_ssot().get("frozen_classes") or [])]


def branch_prefix() -> str:
    return str(load_canary_ssot()["branch_prefix"])


def max_teammates() -> int:
    return int(load_canary_ssot()["max_teammates"])


def path_matches_frozen(rel_path: str, patterns: list[str] | None = None) -> str | None:
    """Return the matching frozen pattern, or None.

    Patterns ending with ``/`` match as prefixes. Others match exact, prefix, or
    fnmatch (for wildcards like ``*.secret``).
    """
    rel = rel_path.replace("\\", "/").lstrip("./")
    for raw in patterns if patterns is not None else frozen_paths():
        pat = str(raw).replace("\\", "/")
        if pat.endswith("/"):
            if rel == pat.rstrip("/") or rel.startswith(pat):
                return pat
        elif "*" in pat or "?" in pat or "[" in pat:
            if fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(Path(rel).name, pat):
                return pat
        else:
            if rel == pat or rel.startswith(pat.rstrip("/") + "/"):
                return pat
    return None


def changed_files(*, base: str, head: str, cwd: Path | None = None) -> list[str]:
    root = cwd or REPO
    completed = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...{head}"],
        cwd=str(root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
        timeout=60,
        check=False,
    )
    if completed.returncode != 0:
        # Fallback for shallow / missing merge-base: two-dot
        completed = subprocess.run(
            ["git", "diff", "--name-only", base, head],
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
            timeout=60,
            check=False,
        )
    if completed.returncode != 0:
        err = (completed.stderr or completed.stdout or "").strip()[:300]
        raise RuntimeError(f"git_diff_failed: {err}")
    return [ln.strip().replace("\\", "/") for ln in completed.stdout.splitlines() if ln.strip()]


def check_diff_against_frozen(
    *, base: str, head: str, cwd: Path | None = None
) -> list[tuple[str, str]]:
    """Return list of (path, matched_pattern) violations."""
    hits: list[tuple[str, str]] = []
    for path in changed_files(base=base, head=head, cwd=cwd):
        matched = path_matches_frozen(path)
        if matched:
            hits.append((path, matched))
    return hits


def render_frozen_markdown() -> str:
    """Helper for TM1 docs — render bullets from SSOT (no hand-copied list)."""
    lines = [
        "<!-- rendered from docs/coordination/canary_frozen_paths.yml — do not hand-edit paths -->",
        "",
    ]
    for p in frozen_paths():
        lines.append(f"- `{p}`")
    classes = frozen_classes()
    if classes:
        lines.append("")
        lines.append("Classes (not diff-gated as paths — policy / gitignore):")
        for c in classes:
            lines.append(f"- `{c}`")
    return "\n".join(lines) + "\n"


def cmd_render(_args: argparse.Namespace) -> int:
    # Bust cache if SSOT edited in-process
    load_canary_ssot.cache_clear()
    print(f"ssot={SSOT_PATH}")
    print(f"branch_prefix={branch_prefix()}")
    print(f"max_teammates={max_teammates()}")
    print(f"merge_order={load_canary_ssot().get('merge_order')}")
    print(render_frozen_markdown())
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    load_canary_ssot.cache_clear()
    base = (args.base or "origin/main").strip()
    head = (args.head or "HEAD").strip()
    try:
        hits = check_diff_against_frozen(base=base, head=head)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if not hits:
        print(f"OK frozen_diff_check_clean base={base} head={head}")
        return 0
    print(
        f"REFUSED: frozen path touched ({len(hits)} file(s)) base={base} head={head}",
        file=sys.stderr,
    )
    for path, pat in hits:
        print(f"  {path}  matches  {pat}", file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd")

    p_render = sub.add_parser("render", help="Print frozen markdown from SSOT (default)")
    p_render.set_defaults(func=cmd_render)

    p_check = sub.add_parser("check", help="Fail if git diff touches a frozen_paths entry")
    p_check.add_argument("--base", default="origin/main", help="Base ref (default origin/main)")
    p_check.add_argument("--head", default="HEAD", help="Head ref (default HEAD)")
    p_check.set_defaults(func=cmd_check)

    args = parser.parse_args(argv)
    if not getattr(args, "cmd", None):
        return cmd_render(argparse.Namespace())
    try:
        return int(args.func(args))
    except SystemExit as exc:
        if isinstance(exc.code, int):
            return exc.code
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
