"""Bounded repair orchestration — the actual pilot control path.

Flow (fail-closed at every step, never merge, never deploy):

    validate manifest -> pin head SHA -> read CI -> retry transient (bounded)
    -> classify -> protected/scope check -> attempt-cap check
    -> [LOCK] task-owned worktree -> smallest fix -> targeted checks
    -> push task branch only -> verify new remote SHA -> [UNLOCK]
    -> fresh-CI required -> record attempt -> audit receipt -> comment

Invariants held here:
  * no GitHub network call happens while the repository lock is held
  * diagnosis-only mode performs zero worktree/code/push mutations
  * a moved/unpinned head, protected-path touch, or unverifiable GitHub state
    is a hard refusal before any file is touched
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from tools.pr_factory import pilot as pilot_mod
from tools.pr_factory.pilot import github_ops as gh_mod
from tools.pr_factory.pilot import guard, worktree
from tools.pr_factory.pilot.guard import GuardRefusal, PilotRefusal, RepairLedger
from tools.pr_factory.pilot.manifest import PilotTask

#: CodeRunner protocol: produce the smallest root-cause fix in the worktree.
CodeRunner = Callable[[Path, PilotTask], dict[str, Any]]

# Re-export for consumers/tests: guard refusals ARE pilot refusals.
__all__ = ["Pilot", "PilotRefusal", "run_pilot", "PilotReport"]


@dataclass
class PilotReport:
    pr_number: int | None
    head_sha: str
    mode: str
    verdict: str
    reasons: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)
    receipt: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pr_number": self.pr_number,
            "head_sha": self.head_sha,
            "mode": self.mode,
            "verdict": self.verdict,
            "reasons": list(self.reasons),
            "evidence": self.evidence,
            "audit_receipt": self.receipt,
        }


def _refuse(exc: Exception) -> PilotRefusal:
    if isinstance(exc, GuardRefusal):
        return PilotRefusal(exc.code, exc.reason, exc.detail)
    if isinstance(exc, gh_mod.GitHubOpsError):
        return PilotRefusal("github_state_unverifiable", str(exc))
    return PilotRefusal("refused", str(exc))


class Pilot:
    """One bounded pilot run for one manifest task."""

    def __init__(
        self,
        *,
        manifest: PilotTask,
        gh: gh_mod.GitHubOps,
        ledger: RepairLedger,
        repo_root: str,
        code_runner: CodeRunner | None = None,
        require_flags: bool = True,
    ) -> None:
        self.task = manifest
        self.gh = gh
        self.ledger = ledger
        self.repo_root = str(Path(repo_root).resolve())
        self.code_runner = code_runner
        self.require_flags = require_flags

    def _pr_number(self) -> int:
        if self.task.pr_number is None:
            raise PilotRefusal("pr_number_required", "manifest has no pr_number for repair")
        return int(self.task.pr_number)

    def _verify_flags(self) -> None:
        if self.require_flags and not pilot_mod.pilot_enabled():
            raise PilotRefusal(
                "flags_off",
                "pilot disabled: PR_FACTORY_PILOT_ENABLED/PR_FACTORY_ENABLED/EXTERNAL_AGENT_ORCHESTRATOR",
            )

    def _resolve_head(self, pr_number: int) -> str:
        try:
            remote = self.gh.remote_branch_sha(self.task.task_branch)
        except gh_mod.GitHubOpsError as exc:
            raise PilotRefusal("github_state_unverifiable", str(exc)) from exc
        if remote is None:
            raise PilotRefusal(
                "task_branch_missing", f"branch {self.task.task_branch} not found on remote"
            )
        guard.check_expected_head_sha(self.task.expected_head_sha, remote)
        return remote

    def _ci_read(self, pr_number: int, head_sha: str) -> list[dict[str, Any]]:
        try:
            runs = self.gh.check_runs(head_sha)
        except gh_mod.GitHubOpsError as exc:
            raise PilotRefusal("github_state_unverifiable", str(exc)) from exc
        for run in runs:
            if run.get("conclusion") == "failure":
                run["log"] = self.gh.check_run_log(run["id"]) if run.get("id") else ""
        return runs

    def _attempt_transient_retry(
        self, pr_number: int, runs: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """GitHub retry FIRST for transient/infra runs; re-read CI after."""
        retried = 0
        for run in runs:
            if guard.is_transient_retryable(run) and guard.can_retry_transient(retried):
                self.gh.retry_run(run["id"])
                retried += 1
        if retried:
            return self._ci_read(pr_number, self._resolve_head(pr_number))
        return runs

    def _classify_ci(self, runs: list[dict[str, Any]]) -> dict[str, Any]:
        failing = [r for r in runs if r.get("conclusion") == "failure"]
        kinds = [guard.classify_failure(r.get("log") or r.get("name") or "") for r in failing]
        if any(k == "code" for k in kinds):
            return {"action": "repair", "kind": "code", "failing": failing}
        if any(k == "infra" for k in kinds):
            return {"action": "leave_for_owner", "kind": "infra", "failing": failing}
        return {"action": "leave_for_owner", "kind": "unknown", "failing": failing}

    def _check_scope(self, pr_number: int) -> None:
        changed = self.gh.pr_changed_files(pr_number)
        protected = guard.protected_path_hits(changed)
        if protected:
            raise PilotRefusal(
                "protected_paths", ",".join(protected), "repair refused: protected paths in PR diff"
            )
        out_of_scope = guard.out_of_scope_paths(changed, self.task)
        if out_of_scope:
            raise PilotRefusal(
                "paths_out_of_scope",
                ",".join(out_of_scope),
                "changes outside manifest allowed_paths",
            )

    # -- modes ---------------------------------------------------------------

    def diagnose(self) -> PilotReport:
        """Read-only: pin, CI, retry-transient, scope. No code, no push, no worktree."""
        self._verify_flags()
        pr = self._pr_number()
        reasons: list[str] = []
        head = self._resolve_head(pr)
        self._check_scope(pr)
        reasons.append("scope OK (no protected / out-of-scope paths in PR diff)")
        runs = self._ci_read(pr, head)
        transient = [r for r in runs if guard.is_transient_retryable(r)]
        if transient:
            runs = self._attempt_transient_retry(pr, runs)
            reasons.append(f"retried {len(transient)} transient/infra run(s)")
        ci = self._classify_ci(runs)
        reasons.append(f"CI classification: {ci['kind']} -> {ci['action']}")
        if ci["action"] == "repair":
            reasons.append(
                "code repair would be permitted in repair mode (not performed in diagnose mode)"
            )
        verdict = ci["action"] if ci["action"] == "leave_for_owner" else "diagnosed"
        self._post_diagnosis_comment(pr, head, ci)
        receipt = guard.build_audit_receipt(
            pr_number=pr,
            head_sha=head,
            mode="diagnose",
            verdict=verdict,
            attempts=self.ledger.attempts_count(pr, head),
            evidence={"ci": ci, "reasons": reasons},
        )
        return PilotReport(
            pr_number=pr,
            head_sha=head,
            mode="diagnose",
            verdict=verdict,
            reasons=reasons,
            receipt=receipt,
        )

    def _post_diagnosis_comment(self, pr: int, head: str, ci: dict[str, Any]) -> None:
        body = (
            "## PR Factory pilot — read-only diagnosis\n\n"
            f"- PR head: `{head}`\n"
            f"- CI classification: `{ci['kind']}` → `{ci['action']}`\n"
            "- No code, no push, no worktree mutation performed.\n"
        )
        self.gh.post_comment(pr, body)

    def repair(self) -> PilotReport:
        """Bounded, fail-closed, task-branch-only repair. Never merge, never deploy."""
        self._verify_flags()
        pr = self._pr_number()
        head = self._resolve_head(pr)
        reasons: list[str] = []

        self._check_scope(pr)
        reasons.append(f"scope OK (allowed_paths={self.task.allowed_paths})")

        runs = self._ci_read(pr, head)
        transient = [r for r in runs if guard.is_transient_retryable(r)]
        if transient:
            runs = self._attempt_transient_retry(pr, runs)
            reasons.append(f"retried {len(transient)} transient/infra run(s)")
        ci = self._classify_ci(runs)
        if ci["action"] == "leave_for_owner":
            receipt = guard.build_audit_receipt(
                pr_number=pr,
                head_sha=head,
                mode="repair",
                verdict="leave_for_owner",
                attempts=self.ledger.attempts_count(pr, head),
                evidence={"ci": ci, "reasons": reasons},
            )
            return PilotReport(
                pr_number=pr,
                head_sha=head,
                mode="repair",
                verdict="leave_for_owner",
                reasons=reasons,
                receipt=receipt,
            )

        if not self.ledger.can_repair(pr, head, self.task.max_repair_attempts):
            raise PilotRefusal(
                "attempt_cap_exceeded",
                f"automated repair attempts exhausted (max {self.task.max_repair_attempts}); owner review required",
            )

        outcome = "no_change"
        new_head = head
        with worktree.repository_lock(self.repo_root, self.task):
            wt = worktree.ensure_task_worktree(self.repo_root, self.task)
            reasons.append(f"worktree={wt['worktree']}")
            if self.code_runner is None:
                raise PilotRefusal(
                    "code_runner_missing",
                    "no CodeRunner supplied; diagnosis-only CI info is on the PR",
                )
            fix = self.code_runner(Path(wt["worktree"]), self.task)
            if fix.get("committed") and fix.get("sha"):
                self._run_targeted_checks(Path(wt["worktree"]))
                new_head = worktree.push_task_branch(self.repo_root, self.task)
                guard.check_expected_head_sha(str(fix["sha"]), new_head)
                outcome = "pushed"
                reasons.append(f"pushed repair {new_head} to {self.task.task_branch}")
            else:
                reasons.append("no commit produced by code runner; nothing pushed")

        self.ledger.record_attempt(
            pr, head, outcome, note=fix.get("summary", "")[:200] if self.code_runner else ""
        )
        attempt = self.ledger.attempts_count(pr, head)

        fresh = self.gh.latest_check_run_for_sha(pr, new_head)
        if not fresh:
            reasons.append("fresh CI required: no check run observed for the new head yet")
            verdict = "awaiting_fresh_ci"
        else:
            reasons.append(f"fresh CI observed for {new_head}")
            verdict = "ci_running"

        receipt = guard.build_audit_receipt(
            pr_number=pr,
            head_sha=new_head,
            mode="repair",
            verdict=verdict,
            attempts=attempt,
            evidence={"ci": ci, "outcome": outcome, "reasons": reasons},
        )
        self._post_repair_comment(pr, new_head, verdict, attempt)
        return PilotReport(
            pr_number=pr,
            head_sha=new_head,
            mode="repair",
            verdict=verdict,
            reasons=reasons,
            receipt=receipt,
        )

    def _run_targeted_checks(self, worktree_path: Path) -> None:
        """Run manifest required tests/lint/security inside the task worktree.

        Commands are pre-validated at manifest load (pytest/ruff/scripts only,
        no shell metacharacters). pytest/ruff are routed through the same Python
        interpreter so they work regardless of PATH. A failure here aborts the push.
        """
        import subprocess
        import sys

        failures: list[str] = []
        for cmd in self.task.required_tests + self.task.required_lint + self.task.required_security:
            parts = cmd.split()
            if parts and parts[0] == "pytest":
                parts = [sys.executable, "-m", "pytest"] + parts[1:]
            elif parts and parts[0] == "ruff":
                parts = [sys.executable, "-m", "ruff"] + parts[1:]
            completed = subprocess.run(
                parts,
                cwd=str(worktree_path),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=300,
                check=False,
                shell=False,
            )
            if completed.returncode != 0:
                failures.append(
                    f"{cmd} -> exit {completed.returncode}: {completed.stderr.strip()[-300:]}"
                )
        if failures:
            raise PilotRefusal(
                "targeted_checks_failed", "; ".join(failures), "no push: targeted checks red"
            )

    def _post_repair_comment(self, pr: int, head: str, verdict: str, attempt: int) -> None:
        body = (
            "## PR Factory pilot — bounded repair\n\n"
            f"- PR head: `{head}`\n"
            f"- attempt: {attempt}/{self.task.max_repair_attempts}\n"
            f"- verdict: `{verdict}`\n"
            "- No merge. No deploy. Branch protection + required checks unchanged.\n"
        )
        self.gh.post_comment(pr, body)

    def verify(self) -> PilotReport:
        """Completion gate: expected head pin + fresh CI on the exact head."""
        self._verify_flags()
        pr = self._pr_number()
        head = self._resolve_head(pr)
        runs = self.gh.check_runs(head)
        guard.require_fresh_ci(runs, head)
        failing = [r for r in runs if r.get("conclusion") == "failure"]
        required = [
            "Lint + syntax + secrets",
            "prod_check + pytest",
            "harness real-redis integration",
        ]
        green = [r for r in runs if r.get("name") in required and r.get("conclusion") == "success"]
        verdict = (
            "green"
            if len(failing) == 0 and len(green) == len(required)
            else "ci_pending_or_failing"
        )
        reasons = [
            f"fresh CI present for {head}",
            f"required checks green: {len(green)}/{len(required)}",
            f"failing runs: {[r.get('name') for r in failing]}",
        ]
        receipt = guard.build_audit_receipt(
            pr_number=pr,
            head_sha=head,
            mode="verify",
            verdict=verdict,
            attempts=self.ledger.attempts_count(pr, head),
            evidence={"runs": runs, "required": required},
        )
        return PilotReport(
            pr_number=pr,
            head_sha=head,
            mode="verify",
            verdict=verdict,
            reasons=reasons,
            receipt=receipt,
        )

    def cleanup(self) -> dict[str, Any]:
        """Remove the task-owned worktree only (guarded in worktree.py)."""
        return worktree.remove_task_worktree(self.repo_root, self.task)


def run_pilot(
    *,
    manifest: PilotTask,
    gh: gh_mod.GitHubOps,
    ledger: RepairLedger,
    repo_root: str,
    code_runner: CodeRunner | None = None,
    require_flags: bool = True,
) -> dict[str, Any]:
    """Convenience: build a Pilot and run it in its declared mode."""
    pilot = Pilot(
        manifest=manifest,
        gh=gh,
        ledger=ledger,
        repo_root=repo_root,
        code_runner=code_runner,
        require_flags=require_flags,
    )
    try:
        if manifest.ci_mode == "diagnose_only" or manifest.risk_class == "AMBER":
            report = pilot.diagnose()
        else:
            report = pilot.repair()
        return report.to_dict()
    except gh_mod.GitHubOpsError as exc:
        return _refuse(exc).to_dict()
    except PilotRefusal as exc:
        return exc.to_dict()
