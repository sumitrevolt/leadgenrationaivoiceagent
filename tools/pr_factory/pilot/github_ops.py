"""Thin ``gh`` wrapper for the pilot — every call fails closed.

``runner`` is injectable so tests drive the exact control paths with a fake.
Only scopes/operations the pilot is allowed to use exist here. There is
deliberately NO method for merging, auto-merge, deploying, or touching secrets.

GitHub REST primitives are read via ``gh api`` (check-runs, refs) and the PR
surface via ``gh pr`` (create --draft, comment). All responses are JSON-parsed
and validated; an unparseable/non-zero result raises ``GitHubOpsError`` which
the orchestration layer converts into a fail-closed refusal.
"""

from __future__ import annotations

import json
import re
import subprocess
from typing import Any, Callable

Runner = Callable[[list[str]], str]


def default_runner(gh_bin: str = "gh", timeout: int = 60) -> Runner:
    def _run(args: list[str]) -> str:
        completed = subprocess.run(
            [gh_bin, *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            shell=False,
        )
        if completed.returncode != 0:
            raise GitHubOpsError(
                f"gh {' '.join(args)} exit={completed.returncode}: {completed.stderr.strip()[-400:]}"
            )
        return completed.stdout

    return _run


class GitHubOpsError(RuntimeError):
    """gh call failed / unverifiable — fail closed, never assume success."""


class GitHubOps:
    def __init__(self, repo: str, runner: Runner | None = None) -> None:
        self.repo = repo
        self._run = runner or default_runner()

    def _gh(self, args: list[str]) -> str:
        return self._run(args)

    def _api_json(self, args: list[str]) -> Any:
        out = self._gh(["api", *args])
        try:
            return json.loads(out)
        except json.JSONDecodeError as exc:
            raise GitHubOpsError(f"unparseable gh api output: {out[:200]!r}") from exc

    # -- read surface -------------------------------------------------------

    def pr_head_sha(self, pr_number: int) -> str:
        data = self._api_json([f"repos/{self.repo}/pulls/{int(pr_number)}"])
        sha = data.get("head", {}).get("sha")
        if not sha:
            raise GitHubOpsError(f"pr #{pr_number} head sha missing")
        return str(sha)

    def pr_is_draft(self, pr_number: int) -> bool:
        data = self._api_json([f"repos/{self.repo}/pulls/{int(pr_number)}"])
        return bool(data.get("draft"))

    def remote_branch_sha(self, branch: str) -> str | None:
        data = self._api_json([f"repos/{self.repo}/git/ref/heads/{branch}"])
        sha = data.get("object", {}).get("sha")
        return str(sha) if sha else None

    def pr_changed_files(self, pr_number: int) -> list[str]:
        out = self._gh(["pr", "diff", "--name-only", str(int(pr_number))])
        files = [line.strip() for line in out.splitlines() if line.strip()]
        return files

    def check_runs(self, head_sha: str) -> list[dict[str, Any]]:
        data = self._api_json([f"repos/{self.repo}/commits/{head_sha}/check-runs"])
        runs = data.get("check_runs") or []
        normalized: list[dict[str, Any]] = []
        for run in runs:
            normalized.append(
                {
                    "id": run.get("id"),
                    "name": run.get("name"),
                    "status": run.get("status"),
                    "conclusion": run.get("conclusion"),
                    "head_sha": run.get("head_sha"),
                    "url": run.get("html_url"),
                }
            )
        return normalized

    def check_run_log(self, run_id: int) -> str:
        try:
            return self._gh(["run", "view", str(int(run_id)), "--log-failed"])
        except GitHubOpsError:
            return ""

    def pr_checks_text(self, pr_number: int) -> str:
        try:
            return self._gh(["pr", "checks", str(int(pr_number))])
        except GitHubOpsError:
            return ""

    # -- mutating surface (bounded, task-branch only) ------------------------

    def retry_run(self, run_id: int) -> None:
        """GitHub-level retry of a failed run (transient/infra only)."""
        self._gh(["run", "rerun", str(int(run_id)), "--failed"])

    def post_comment(self, pr_number: int, body: str) -> None:
        self._gh(["pr", "comment", str(int(pr_number)), "--body", body])

    def create_draft_pr(self, *, base: str, head: str, title: str, body: str) -> int:
        out = self._gh(
            [
                "pr",
                "create",
                "--draft",
                "--base",
                base,
                "--head",
                head,
                "--title",
                title,
                "--body",
                body,
            ]
        )
        match = re.search(r"pull/(\d+)|#(\d+)\b", out)
        number = match.group(1) or match.group(2) if match else None
        if not number:
            raise GitHubOpsError(f"could not parse created PR number from: {out[:200]!r}")
        return int(number)

    # -- fresh-CI helper ------------------------------------------------------

    def latest_check_run_for_sha(self, pr_number: int, head_sha: str) -> dict[str, Any] | None:
        from tools.pr_factory.pilot.guard import fresh_ci_evidence

        try:
            runs = self.check_runs(head_sha)
        except GitHubOpsError:
            return None
        return fresh_ci_evidence(runs, head_sha)
