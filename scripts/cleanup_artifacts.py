"""Workspace artifact and cache cleanup script.

Safely cleans __pycache__, .pytest_cache, .mypy_cache, .ruff_cache,
and local transient test logs without touching production data, databases,
or tracked git files.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

TARGET_DIR_PATTERNS = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".benchmarks",
}

TARGET_FILE_PATTERNS = {
    ".coverage",
    "coverage.xml",
    "pytest_run.log",
}


def clean_artifacts(dry_run: bool = False) -> dict[str, int]:
    stats = {
        "dirs_removed": 0,
        "files_removed": 0,
        "bytes_freed": 0,
        "errors": 0,
    }

    # Clean directories
    for root, dirs, _ in os.walk(ROOT_DIR, topdown=False):
        for d in dirs:
            if d in TARGET_DIR_PATTERNS:
                dir_path = Path(root) / d
                # Ensure we do not touch .venv or git
                if ".venv" in dir_path.parts or ".git" in dir_path.parts:
                    continue
                try:
                    size = sum(f.stat().st_size for f in dir_path.rglob("*") if f.is_file())
                    if not dry_run:
                        shutil.rmtree(dir_path, ignore_errors=True)
                    stats["dirs_removed"] += 1
                    stats["bytes_freed"] += size
                except Exception as exc:
                    stats["errors"] += 1

    # Clean files
    for root, _, files in os.walk(ROOT_DIR):
        for f in files:
            if f in TARGET_FILE_PATTERNS or (f.startswith(".tmp_") and f.endswith(".tmp")):
                file_path = Path(root) / f
                if ".venv" in file_path.parts or ".git" in file_path.parts:
                    continue
                try:
                    size = file_path.stat().st_size
                    if not dry_run:
                        file_path.unlink(missing_ok=True)
                    stats["files_removed"] += 1
                    stats["bytes_freed"] += size
                except Exception:
                    stats["errors"] += 1

    return stats


def main() -> int:
    dry_run = "--dry-run" in sys.argv
    mode = "DRY RUN" if dry_run else "LIVE CLEANUP"
    print(f"=== Artifact Cleanup: {mode} ===")
    print(f"Target Root: {ROOT_DIR}")

    stats = clean_artifacts(dry_run=dry_run)

    freed_mb = stats["bytes_freed"] / (1024 * 1024)
    print(f"Directories removed: {stats['dirs_removed']}")
    print(f"Files removed:       {stats['files_removed']}")
    print(f"Space freed:         {freed_mb:.2f} MB")
    print(f"Errors encountered:  {stats['errors']}")
    print("=== Cleanup Complete ===")
    return 0 if stats["errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
