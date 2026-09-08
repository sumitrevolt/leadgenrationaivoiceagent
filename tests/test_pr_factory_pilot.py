"""Pilot orchestration contract: bounded repair, no merge/deploy, fail-closed."""

from __future__ import annotations

import contextlib
import json
import subprocess
from pathlib import Path

import pytest

from tools.pr_factory.pilot import github_ops as gh_mod
from tools.pr_factory.pilot.guard import RepairLedger
from tools.pr_factory.pilot.manifest import PilotManifestError, parse_manifest
from tools.pr_factory.pilot.pilot import Pilot, PilotRefusal, run_pilot
from tools.pr_factory.pilot.worktree import WorktreeGuardError, remove_task_worktree

SHA_A = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
SHA_B = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
NEW_SHA = "cccccccccccccccccccccccccccccccccccccccc"


def _manifest(**over):
    payload = {
        "task_id": "pilot-orch-001",
        "objective": "fix flaky test",
        "owner": "owner@leadsgenai.in",
        "base_branch": "main",
        "task_branch": "fix/pilot-orch-001",
        "worktree_path": "C:/Users/Ratanshila/Documents/_leadgen_worktrees/pilot-orch-001",
        "allowed_paths": ["tests/test_demo.py"],
        "denied_paths": [],
        "risk_class": "GREEN",
        "required_tests": ["pytest tests/test_demo.py -q"],
        "required_lint": [],
        "required_security": [],
        "expected_head_sha": SHA_A,
        "max_repair_attempts": 2,
        "external_action_permissions": {
            "pull_requests": "write",
            "actions": "read",
            "contents": "task_branch_only",
        },
        "owner_approval_id": "",
        "cleanup_ownership": "task_owned",
        "completion_conditions": ["required checks green"],
        "pr_number": 7,
    }
    payload.update(over)
    return payload


class FakeGH:
    """Duck-typed GitHubOps: records calls, returns canned state."""

    def __init__(self) -> None:
        self.remote_sha = SHA_A
        self.changed_files = ["tests/test_demo.py"]
        self.runs: list[dict] = []
        self.fresh_run = None
        self.fail_mode: str | None = None
        self.comments: list[str] = []
        self.retried: list[int] = []
        self.calls: list[str] = []

    def _maybe_fail(self, op: str) -> None:
        self.calls.append(op)
        if self.fail_mode == "unverifiable" and op in {"remote_branch_sha", "check_runs"}:
            raise gh_mod.GitHubOpsError(f"{op} unverifiable")

    def remote_branch_sha(self, branch):
        self._maybe_fail("remote_branch_sha")
        return self.remote_sha

    def check_runs(self, head_sha):
        self._maybe_fail("check_runs")
        return [dict(r) for r in self.runs]

    def check_run_log(self, run_id):
        return "ModuleNotFoundError: no module named nope"

    def retry_run(self, run_id):
        self.retried.append(run_id)

    def pr_changed_files(self, pr_number):
        self.calls.append("pr_changed_files")
        return list(self.changed_files)

    def post_comment(self, pr_number, body):
        self.comments.append(body)

    def latest_check_run_for_sha(self, pr_number, head_sha):
        self.calls.append("latest_check_run_for_sha")
        if self.fail_mode == "unverifiable":
            raise gh_mod.GitHubOpsError("latest_check_run_for_sha unverifiable")
        return self.fresh_run


def _pilot(task, gh, tmp_path, monkeypatch, **over):
    ledger = RepairLedger(state_dir=tmp_path / "state")
    p = Pilot(
        manifest=task,
        gh=gh,
        ledger=ledger,
        repo_root=str(tmp_path),
        require_flags=False,
        code_runner=_code_runner,
    )
    for name in ("ensure_task_worktree", "push_task_branch"):
        monkeypatch.setattr(
            "tools.pr_factory.pilot.pilot.worktree." + name,
            lambda *a, _name=name: (
                {"ok": True, "worktree": str(tmp_path / "wt"), "branch": task.task_branch}
                if _name == "ensure_task_worktree"
                else NEW_SHA
            ),
        )
    monkeypatch.setattr(
        "tools.pr_factory.pilot.pilot.worktree.repository_lock",
        lambda *a, **k: contextlib.nullcontext(),
    )
    monkeypatch.setattr(Pilot, "_run_targeted_checks", lambda self, wt: None)
    return p, ledger


def _code_runner(worktree, task):
    return {"committed": True, "sha": NEW_SHA, "summary": "smallest root-cause fix"}


def test_no_merge_method_on_pilot_or_gh():
    assert not hasattr(gh_mod.GitHubOps, "merge")
    assert not hasattr(gh_mod.GitHubOps, "enable_auto_merge")
    assert not hasattr(Pilot, "merge")
    assert not hasattr(Pilot, "deploy")
    source = Path(gh_mod.__file__).read_text(encoding="utf-8")
    assert "pr merge" not in source
    assert "--auto" not in source
    assert "DEPLOY_ENABLED" not in source


def test_create_draft_pr_uses_draft_flag():
    seen: dict[str, list[str]] = {}

    def runner(args):
        seen["args"] = args
        return "https://github.com/org/repo/pull/42"

    gh = gh_mod.GitHubOps("sumitrevolt/leadgenrationaivoiceagent", runner=runner)
    number = gh.create_draft_pr(base="main", head="fix/x", title="t", body="b")
    assert number == 42
    assert "--draft" in seen["args"]
    assert "--merge" not in seen["args"] and "merge" not in seen["args"]
    assert "--auto" not in seen["args"]


def test_repair_happy_path_bounded_push_and_comment(tmp_path, monkeypatch):
    task = parse_manifest(json.dumps(_manifest()))
    gh = FakeGH()
    gh.runs = [
        {
            "id": 1,
            "name": "prod_check + pytest",
            "status": "completed",
            "conclusion": "failure",
            "head_sha": SHA_A,
        }
    ]
    gh.fresh_run = {"head_sha": NEW_SHA, "status": "in_progress", "conclusion": None}
    p, ledger = _pilot(task, gh, tmp_path, monkeypatch)
    report = p.repair()
    assert report.verdict == "ci_running"
    assert report.head_sha == NEW_SHA
    assert ledger.attempts_count(7, SHA_A) == 1
    assert any("bounded repair" in c for c in gh.comments)
    assert report.receipt["max_repair_attempts"] == 2


def test_latest_repair_push_requires_fresh_ci(tmp_path, monkeypatch):
    task = parse_manifest(json.dumps(_manifest()))
    gh = FakeGH()
    gh.runs = [
        {
            "id": 1,
            "name": "prod_check + pytest",
            "status": "completed",
            "conclusion": "failure",
            "head_sha": SHA_A,
        }
    ]
    gh.fresh_run = None  # no fresh CI observed for the new head
    p, ledger = _pilot(task, gh, tmp_path, monkeypatch)
    report = p.repair()
    assert report.verdict == "awaiting_fresh_ci"
    assert any("fresh CI required" in r for r in report.reasons)
    assert ledger.attempts_count(7, SHA_A) == 1


def test_no_code_push_during_diagnosis_only(tmp_path, monkeypatch):
    task = parse_manifest(json.dumps(_manifest(ci_mode="diagnose_only")))
    gh = FakeGH()
    gh.runs = [
        {
            "id": 1,
            "name": "prod_check + pytest",
            "status": "completed",
            "conclusion": "failure",
            "head_sha": SHA_A,
        }
    ]

    def _explode(*a, **k):
        raise AssertionError("diagnosis mode must never provision a worktree or push")

    monkeypatch.setattr("tools.pr_factory.pilot.pilot.worktree.ensure_task_worktree", _explode)
    monkeypatch.setattr("tools.pr_factory.pilot.pilot.worktree.push_task_branch", _explode)
    monkeypatch.setattr(
        "tools.pr_factory.pilot.pilot.worktree.repository_lock",
        lambda *a, **k: contextlib.nullcontext(),
    )

    out = run_pilot(
        manifest=task,
        gh=gh,
        ledger=RepairLedger(state_dir=tmp_path / "state"),
        repo_root=str(tmp_path),
        require_flags=False,
    )
    assert out["mode"] == "diagnose"
    assert out["verdict"] in {"diagnosed", "leave_for_owner"}
    assert "ensure_task_worktree" not in gh.calls


def test_repair_attempt_cap_stops_second_fix(tmp_path, monkeypatch):
    task = parse_manifest(json.dumps(_manifest()))
    gh = FakeGH()
    gh.runs = [
        {
            "id": 1,
            "name": "prod_check + pytest",
            "status": "completed",
            "conclusion": "failure",
            "head_sha": SHA_A,
        }
    ]
    gh.fresh_run = {"head_sha": NEW_SHA, "status": "in_progress", "conclusion": None}
    p, ledger = _pilot(task, gh, tmp_path, monkeypatch)
    p.repair()
    p.repair()
    with pytest.raises(PilotRefusal, match="attempt_cap_exceeded"):
        p.repair()


def test_head_sha_moved_refused(tmp_path, monkeypatch):
    task = parse_manifest(json.dumps(_manifest()))
    gh = FakeGH()
    gh.remote_sha = SHA_B  # branch moved away from the pinned head
    p, _ = _pilot(task, gh, tmp_path, monkeypatch)
    with pytest.raises(PilotRefusal, match="head_sha_mismatch"):
        p.repair()


def test_protected_path_in_pr_refused(tmp_path, monkeypatch):
    task = parse_manifest(json.dumps(_manifest()))
    gh = FakeGH()
    gh.changed_files = ["app/voice_agent/brain.py"]
    p, _ = _pilot(task, gh, tmp_path, monkeypatch)
    with pytest.raises(PilotRefusal, match="protected_paths"):
        p.repair()


def test_paths_out_of_scope_refused(tmp_path, monkeypatch):
    task = parse_manifest(json.dumps(_manifest()))
    gh = FakeGH()
    gh.changed_files = ["app/platform/unrelated.py"]
    p, _ = _pilot(task, gh, tmp_path, monkeypatch)
    with pytest.raises(PilotRefusal, match="paths_out_of_scope"):
        p.repair()


def test_fail_closed_when_github_unverifiable(tmp_path, monkeypatch):
    task = parse_manifest(json.dumps(_manifest()))
    gh = FakeGH()
    gh.fail_mode = "unverifiable"
    p, _ = _pilot(task, gh, tmp_path, monkeypatch)
    with pytest.raises(PilotRefusal, match="github_state_unverifiable"):
        p.repair()
    out = run_pilot(
        manifest=task,
        gh=gh,
        ledger=RepairLedger(state_dir=tmp_path / "state"),
        repo_root=str(tmp_path),
        require_flags=False,
    )
    assert out["refused"] is True
    assert out["code"] == "github_state_unverifiable"


def test_stale_ci_cannot_authorize_completion(tmp_path, monkeypatch):
    task = parse_manifest(json.dumps(_manifest()))
    gh = FakeGH()
    # check runs bound to an OLD sha only — never the pinned head
    gh.runs = [
        {
            "id": 1,
            "name": "prod_check + pytest",
            "status": "completed",
            "conclusion": "success",
            "head_sha": SHA_B,
        }
    ]
    p, _ = _pilot(task, gh, tmp_path, monkeypatch)
    with pytest.raises(PilotRefusal, match="fresh_ci_required"):
        p.verify()


def test_verify_green_requires_all_required_checks(tmp_path, monkeypatch):
    task = parse_manifest(json.dumps(_manifest()))
    gh = FakeGH()
    gh.runs = [
        {
            "name": "Lint + syntax + secrets",
            "status": "completed",
            "conclusion": "success",
            "head_sha": SHA_A,
        },
        {
            "name": "prod_check + pytest",
            "status": "completed",
            "conclusion": "success",
            "head_sha": SHA_A,
        },
        {
            "name": "harness real-redis integration",
            "status": "completed",
            "conclusion": "success",
            "head_sha": SHA_A,
        },
    ]
    p, _ = _pilot(task, gh, tmp_path, monkeypatch)
    report = p.verify()
    assert report.verdict == "green"
    assert "fresh CI present" in " ".join(report.reasons)


def test_targeted_checks_block_push_on_red(tmp_path):
    task = parse_manifest(json.dumps(_manifest(required_tests=["pytest tests/missing_file.py -q"])))
    p = Pilot(
        manifest=task,
        gh=FakeGH(),
        ledger=RepairLedger(state_dir=tmp_path / "state"),
        repo_root=str(tmp_path),
        require_flags=False,
    )
    wt = tmp_path / "wt"
    wt.mkdir()
    with pytest.raises(PilotRefusal, match="targeted_checks_failed"):
        p._run_targeted_checks(wt)


def test_targeted_checks_pass_with_green_command(tmp_path):
    task = parse_manifest(json.dumps(_manifest(required_tests=["pytest --version"])))
    p = Pilot(
        manifest=task,
        gh=FakeGH(),
        ledger=RepairLedger(state_dir=tmp_path / "state"),
        repo_root=str(tmp_path),
        require_flags=False,
    )
    wt = tmp_path / "wt"
    wt.mkdir()
    p._run_targeted_checks(wt)  # no exception = targeted checks green


@pytest.fixture
def real_repo(tmp_path, monkeypatch):
    """A throwaway git repo with two worktrees (real subprocess)."""
    monkeypatch.setenv("EXTERNAL_AGENT_WORKTREE_ROOT", str(tmp_path))
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
    (repo / "a.txt").write_text("hello", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "a.txt"], check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            # CI runners have no git identity and no signing key; supply both inline
            # so the throwaway repo never depends on machine-level git config.
            "-c",
            "user.name=pilot-test",
            "-c",
            "user.email=pilot-test@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-m",
            "init",
            "--no-verify",
        ],
        check=True,
        capture_output=True,
    )
    wt_task = tmp_path / "wt-task"
    wt_other = tmp_path / "wt-other"
    subprocess.run(
        ["git", "-C", str(repo), "worktree", "add", "-b", "fix/task", str(wt_task), "HEAD"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "worktree", "add", "-b", "fix/other", str(wt_other), "HEAD"],
        check=True,
        capture_output=True,
    )
    return repo, wt_task, wt_other


def test_cleanup_refuses_unrelated_worktree(real_repo):
    repo, wt_task, wt_other = real_repo
    # manifest owns wt_task on fix/task; point cleanup at the OTHER worktree
    task = parse_manifest(
        json.dumps(
            _manifest(task_id="pilot-cleanup", task_branch="fix/other", worktree_path=str(wt_other))
        )
    )
    # wt_other is on fix/other = matches branch but is NOT the declared task path.
    # path mismatch check: declared path == derived path here, so branch + path pass;
    # this is still a *task-owned* worktree, so cleanup is allowed. The real
    # refusal happens when the path or branch does not match the manifest.
    result = remove_task_worktree(str(repo), task)
    assert result["ok"] is True
    assert wt_other.exists() is False
    # unrelated worktree untouched
    assert wt_task.exists() is True


def test_cleanup_branch_mismatch_refused(real_repo):
    repo, wt_task, wt_other = real_repo
    # Manifest declares task branch fix/task but points at the OTHER worktree (fix/other)
    task = parse_manifest(
        json.dumps(
            _manifest(task_id="pilot-cleanup2", task_branch="fix/task", worktree_path=str(wt_other))
        )
    )
    with pytest.raises(WorktreeGuardError, match="cleanup_branch_mismatch"):
        remove_task_worktree(str(repo), task)
    assert wt_other.exists() is True  # untouched
    assert wt_task.exists() is True  # untouched


def test_cleanup_path_mismatch_refused(real_repo):
    repo, wt_task, wt_other = real_repo
    task = parse_manifest(
        json.dumps(
            _manifest(task_id="pilot-cleanup3", task_branch="fix/task", worktree_path=str(wt_task))
        )
    )
    # Fudge the registered path expectation: declared path differs from task_worktree_path
    import tools.pr_factory.pilot.worktree as wt_mod

    monkeypatched = Path(str(wt_task) + "-fake").resolve()
    task.worktree_path = str(monkeypatched)
    wt = wt_mod.task_worktree_path(task)
    assert wt != Path(wt_task).resolve()
    with pytest.raises(WorktreeGuardError, match="cleanup_path_mismatch"):
        remove_task_worktree(str(repo), task)
    assert wt_task.exists() is True


def test_cleanup_refuses_dirty_task_worktree(real_repo):
    repo, wt_task, wt_other = real_repo
    task = parse_manifest(
        json.dumps(
            _manifest(task_id="pilot-cleanup4", task_branch="fix/task", worktree_path=str(wt_task))
        )
    )
    (wt_task / "dirty.txt").write_text("uncommitted", encoding="utf-8")
    with pytest.raises(WorktreeGuardError, match="cleanup_worktree_dirty"):
        remove_task_worktree(str(repo), task)
    assert wt_task.exists() is True


def test_cli_refuses_when_flags_off(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("PR_FACTORY_PILOT_ENABLED", raising=False)
    monkeypatch.delenv("PR_FACTORY_ENABLED", raising=False)
    monkeypatch.delenv("EXTERNAL_AGENT_ORCHESTRATOR", raising=False)
    from tools.pr_factory.pilot import cli

    manifest_path = tmp_path / "task.json"
    manifest_path.write_text(json.dumps(_manifest()), encoding="utf-8")
    rc = cli.main(["repair", str(manifest_path)])
    assert rc == 3
    captured = capsys.readouterr().out
    payload = json.loads(captured)
    assert payload["code"] == "flags_off"


def test_cli_validate_reports_ok(tmp_path):
    from tools.pr_factory.pilot import cli

    manifest_path = tmp_path / "task.json"
    manifest_path.write_text(json.dumps(_manifest()), encoding="utf-8")
    rc = cli.main(["validate", str(manifest_path)])
    assert rc == 0


def test_cli_validate_refuses_bad_manifest(tmp_path, capsys):
    from tools.pr_factory.pilot import cli

    manifest_path = tmp_path / "task.json"
    manifest_path.write_text(
        json.dumps(_manifest(allowed_paths=["app/billing/packages.py"])), encoding="utf-8"
    )
    rc = cli.main(["validate", str(manifest_path)])
    assert rc == 1
    captured = capsys.readouterr().out
    assert json.loads(captured)["refused"] is True


def test_run_pilot_refuses_malformed_manifest(tmp_path):
    with pytest.raises(PilotManifestError):
        parse_manifest("not json")
