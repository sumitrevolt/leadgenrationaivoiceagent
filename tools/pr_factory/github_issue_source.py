"""Read GitHub issues via ``gh`` CLI — no Linear dependency (Wave 1)."""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any


class GitHubIssueError(RuntimeError):
    """gh CLI unavailable or issue fetch failed."""


def _gh_exe() -> str:
    exe = shutil.which("gh") or shutil.which("gh.exe")
    if not exe:
        raise GitHubIssueError("gh_cli_unavailable")
    return exe


def fetch_issue(issue_number: int, *, repo: str = "") -> dict[str, Any]:
    """Return issue metadata as a dict (title, body, labels, number, url)."""
    exe = _gh_exe()
    cmd = [
        exe,
        "issue",
        "view",
        str(int(issue_number)),
        "--json",
        "number,title,body,labels,url,state",
    ]
    if repo:
        cmd.extend(["--repo", repo])
    try:
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
    except Exception as exc:
        raise GitHubIssueError(f"gh_issue_view_failed:{type(exc).__name__}") from exc
    if completed.returncode != 0:
        raise GitHubIssueError(
            f"gh_issue_view_exit:{completed.returncode}:{(completed.stderr or '')[:200]}"
        )
    try:
        data = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise GitHubIssueError("gh_issue_json_invalid") from exc
    if not isinstance(data, dict) or not data.get("number"):
        raise GitHubIssueError("gh_issue_empty")
    return data


def issue_to_task_stub(issue: dict[str, Any]) -> dict[str, Any]:
    """Map a GitHub issue into a partial task dict (still needs paths/tests)."""
    labels = []
    for lab in issue.get("labels") or []:
        if isinstance(lab, dict):
            labels.append(str(lab.get("name") or ""))
        else:
            labels.append(str(lab))
    return {
        "title": str(issue.get("title") or "").strip(),
        "description": str(issue.get("body") or "").strip(),
        "issue_id": str(issue.get("number") or ""),
        "labels": [x for x in labels if x],
        "url": str(issue.get("url") or ""),
        "note": "Wave 1 stub — fill allowed_paths, acceptance_criteria, required_tests, rollback_plan",
    }
