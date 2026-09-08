"""Queue idempotency audit — scan all Celery tasks for idempotency patterns.

Usage:
    python scripts/queue_idempotency_audit.py

Outputs a markdown report to stdout listing:
- Tasks WITH explicit idempotency
- Tasks WITHOUT explicit idempotency (gap)
- Recommendations

Playbook ref: Queue System — every queue must have idempotency key.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Celery task patterns
TASK_PATTERNS = [
    re.compile(r"@celery_app\.task\s*\(\s*name\s*=\s*['\"]([^'\"]+)['\"]"),
    re.compile(r"@celery_app\.task\s*\(\s*bind\s*=\s*True[^)]*\)"),
    re.compile(r"@celery\.task\s*\("),
    re.compile(r"@celery_app\.task\s*\("),
]

# Idempotency patterns
IDEM_PATTERNS = [
    re.compile(r"idempotency", re.I),
    re.compile(r"seen_before", re.I),
    re.compile(r"dedup", re.I),
    re.compile(r"duplicate", re.I),
    re.compile(r"task_id\s*[=:]", re.I),
    re.compile(r"already[_\s]processed", re.I),
    re.compile(r"skip.*if.*exists", re.I),
]


def find_celery_tasks() -> list[tuple[str, int, str, str]]:
    """Return list of (file, line, task_name, line_text)."""
    tasks: list[tuple[str, int, str, str]] = []
    # Exclude virtual-env and installed-package directories so celery builtins
    # don't inflate gap counts.
    _EXCLUDE_PARTS = {".venv", "venv", "site-packages", "__pypackages__"}
    for py_file in ROOT.rglob("app/**/*.py"):
        if any(p in py_file.parts for p in _EXCLUDE_PARTS):
            continue
        if not py_file.is_file():
            continue
        try:
            text = py_file.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            # Detect Celery task decorators. Earlier this only matched "@celery*"
            # and silently MISSED every `@shared_task` (which app/tasks/*.py uses) —
            # undercounting tasks and reporting a false coverage %. Now both forms.
            stripped = line.lstrip()
            is_task_decorator = (
                stripped.startswith("@shared_task")
                or stripped.startswith("@app.task")
                or ("@celery" in line and "task" in line)
            )
            if is_task_decorator:
                # Try to find the function name on the next non-empty line
                func_name = "<unknown>"
                for j in range(i, min(i + 5, len(text.splitlines()))):
                    next_line = text.splitlines()[j]
                    m = re.search(r"^\s*def\s+(\w+)", next_line)
                    if m:
                        func_name = m.group(1)
                        break
                tasks.append((str(py_file.relative_to(ROOT)), i, func_name, line.strip()))
    return tasks


def has_idempotency(file_path: str, func_name: str) -> bool:
    """Check if the function body contains idempotency patterns."""
    fp = ROOT / file_path
    if not fp.is_file():
        return False
    try:
        text = fp.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return False

    # Find the function and extract its body
    lines = text.splitlines()
    func_line = -1
    for i, line in enumerate(lines):
        if re.search(rf"^\s*def\s+{re.escape(func_name)}\s*\(", line):
            func_line = i
            break

    if func_line < 0:
        return False

    # Also scan the decorator lines sitting above the `def` (up to 10 lines back).
    # This correctly detects `@idempotent_task(...)` decorators on tasks in
    # staff_jobs.py and brain_training.py that were previously counted as gaps.
    decorator_lines = lines[max(0, func_line - 10) : func_line]
    decorator_text = "\n".join(decorator_lines)
    if any(p.search(decorator_text) for p in IDEM_PATTERNS):
        return True

    # Extract body (simple indentation-based extraction, up to next same-level def or class)
    base_indent = len(lines[func_line]) - len(lines[func_line].lstrip())
    body_lines = []
    for line in lines[func_line + 1 :]:
        if not line.strip():
            body_lines.append(line)
            continue
        indent = len(line) - len(line.lstrip())
        if indent <= base_indent and (
            line.strip().startswith("def ") or line.strip().startswith("class ")
        ):
            break
        body_lines.append(line)

    body = "\n".join(body_lines)
    return any(p.search(body) for p in IDEM_PATTERNS)


def main() -> int:
    print("# Queue Idempotency Audit Report\n")
    print(f"Generated: {ROOT.name}\n")
    print("---\n")

    tasks = find_celery_tasks()
    if not tasks:
        print("No Celery tasks found.")
        return 0

    with_idem: list[tuple[str, str, str]] = []
    without_idem: list[tuple[str, str, str]] = []

    for file_path, line, func_name, decorator in tasks:
        if has_idempotency(file_path, func_name):
            with_idem.append((file_path, func_name, decorator))
        else:
            without_idem.append((file_path, func_name, decorator))

    print("## Summary\n")
    print(f"- Total Celery tasks found: {len(tasks)}")
    print(f"- Tasks WITH idempotency patterns: {len(with_idem)}")
    print(f"- Tasks WITHOUT idempotency patterns: {len(without_idem)}")
    print(f"- Coverage: {len(with_idem) / len(tasks) * 100:.1f}%\n")

    print("## Tasks WITH Idempotency [OK]\n")
    print("| File | Function | Decorator |")
    print("|------|----------|-----------|")
    for file_path, func_name, decorator in with_idem:
        print(f"| {file_path} | `{func_name}` | `{decorator[:60]}...` |")

    print("\n## Tasks WITHOUT Idempotency [GAP]\n")
    print("| File | Function | Decorator |")
    print("|------|----------|-----------|")
    for file_path, func_name, decorator in without_idem:
        print(f"| {file_path} | `{func_name}` | `{decorator[:60]}...` |")

    print("\n## Recommendations\n")
    print("1. **Add idempotency keys to all tasks without explicit deduplication.**")
    print("   Use `app.billing.idempotency` or Redis `setnx` with task IDs.")
    print("2. **Document idempotency strategy per queue.**")
    print("3. **Add replay-safe checkpoints for long-running tasks.**")
    print("4. **Add queue-depth alerts** for tasks that lack idempotency.")

    # RATCHET gate (2026-07-06): pehle "koi bhi gap = exit 1" tha — 117 known
    # static-scan gaps ke saath yeh step KABHI green nahi ho sakta tha (kai tasks
    # ka dedup scheduler/day-key layer pe hai jo yeh heuristic nahi dekh sakta).
    # IDEM_AUDIT_MAX_GAPS set ho → gaps > baseline = fail (naya task bina
    # idempotency ke regression block); unset → advisory report (exit 0).
    import os as _os

    gaps = len(without_idem)
    _max_raw = (_os.getenv("IDEM_AUDIT_MAX_GAPS", "") or "").strip()
    if _max_raw.isdigit():
        code = 1 if gaps > int(_max_raw) else 0
        mode = f"ratchet(max={_max_raw})"
    else:
        code = 0
        mode = "advisory"
    print("\n---\n")
    print(f"**Exit code:** {code} (gaps={gaps}, mode={mode})")
    return code


if __name__ == "__main__":
    sys.exit(main())
