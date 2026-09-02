"""Apply ``auto-merge`` label via ``gh`` when GREEN + checks (Wave 1 helper)."""

from __future__ import annotations

import shutil
import subprocess
from typing import Any


class MergeTrainError(RuntimeError):
    """gh label apply failed or preconditions not met."""


def _gh_exe() -> str:
    exe = shutil.which("gh") or shutil.which("gh.exe")
    if not exe:
        raise MergeTrainError("gh_cli_unavailable")
    return exe


def can_label(*, risk_class: str, review_passed: bool, checks_green: bool) -> dict[str, Any]:
    """Gate before labeling — never auto-label RED/AMBER without Owner OS."""
    risk = (risk_class or "").strip().upper()
    if risk == "RED":
        return {"ok": False, "reason": "red_refused"}
    if risk == "AMBER":
        return {"ok": False, "reason": "amber_requires_owner_os"}
    if risk != "GREEN":
        return {"ok": False, "reason": "unknown_risk_class"}
    if not review_passed:
        return {"ok": False, "reason": "review_not_passed"}
    if not checks_green:
        return {"ok": False, "reason": "checks_not_green"}
    return {"ok": True}


def apply_auto_merge_label(
    pr_number: int, *, repo: str = "", dry_run: bool = True
) -> dict[str, Any]:
    """Apply the ``auto-merge`` label (existing workflow does the rest).

    Wave 1 default ``dry_run=True`` — prints intent without mutating GitHub.
    """
    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "pr": int(pr_number),
            "label": "auto-merge",
            "note": "set dry_run=False to apply via gh",
        }
    exe = _gh_exe()
    cmd = [exe, "pr", "edit", str(int(pr_number)), "--add-label", "auto-merge"]
    if repo:
        cmd.extend(["--repo", repo])
    completed = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
        timeout=60,
        check=False,
    )
    if completed.returncode != 0:
        raise MergeTrainError(
            f"gh_pr_edit_exit:{completed.returncode}:{(completed.stderr or '')[:200]}"
        )
    return {"ok": True, "dry_run": False, "pr": int(pr_number), "label": "auto-merge"}
