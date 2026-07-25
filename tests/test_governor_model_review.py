from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.governor_model_review import (
    ReviewAdapterError,
    build_claude_command,
    load_pinned_artifact,
    review_and_submit,
)

ROOT = Path(__file__).resolve().parents[1]


def _proposal(tmp_path: Path, task_id: str = "task-1") -> tuple[Path, Path, str]:
    root = tmp_path / "data" / "dev_tasks"
    task_root = root / task_id
    task_root.mkdir(parents=True)
    path = task_root / "proposal-20260715-abcd1234.md"
    path.write_text("# proposal\n+safe change\n", encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return root, path, digest


def test_claude_command_disables_tools_and_customizations():
    command = build_claude_command("claude")
    assert "--safe-mode" in command
    assert "--no-chrome" in command
    assert "--no-session-persistence" in command
    assert "--system-prompt" in command
    assert command[command.index("--tools") + 1] == ""
    assert command[command.index("--permission-mode") + 1] == "plan"


def test_artifact_loader_is_task_scoped_and_size_bounded(tmp_path):
    root, path, digest = _proposal(tmp_path)
    text, actual = load_pinned_artifact(
        task_id="task-1", artifact_path=str(path), proposals_root=root,
    )
    assert text.startswith("# proposal")
    assert actual == digest

    outside = tmp_path / "proposal-escape.md"
    outside.write_text("escape", encoding="utf-8")
    with pytest.raises(ReviewAdapterError, match="proposal_path_outside_task_scope"):
        load_pinned_artifact(
            task_id="task-1", artifact_path=str(outside), proposals_root=root,
        )


def test_valid_claude_verdict_submits_exact_local_hash(tmp_path, monkeypatch):
    root, path, digest = _proposal(tmp_path)
    monkeypatch.setattr("scripts.governor_model_review.shutil.which", lambda _name: "claude")
    captured = {}

    def runner(command, **kwargs):
        captured.update(command=command, kwargs=kwargs)
        payload = {
            "structured_output": {
                "artifact_sha256": digest,
                "decision": "approve",
                "summary": "Exact proposal is bounded and safe for tests.",
            }
        }
        return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

    def submitter(**kwargs):
        captured["submit"] = kwargs
        return {"ok": True, "review_gate": {"approved": False}}

    result = review_and_submit(
        base_url="http://127.0.0.1:8000/api", task_id="task-1",
        governor="claude", artifact_path=str(path), proposals_root=root,
        model_runner=runner, submitter=submitter,
    )
    assert result["ok"] is True
    assert captured["submit"]["artifact_hash"] == digest
    assert captured["submit"]["decision"] == "approve"
    assert "DEV_CLAUDE_REVIEW_SECRET" not in captured["kwargs"]["env"]
    assert str(path) not in " ".join(captured["command"])


def test_hash_mismatch_fails_before_submit(tmp_path, monkeypatch):
    root, path, _digest = _proposal(tmp_path)
    monkeypatch.setattr("scripts.governor_model_review.shutil.which", lambda _name: "claude")

    def runner(command, **_kwargs):
        payload = {
            "artifact_sha256": "0" * 64,
            "decision": "approve",
            "summary": "wrong artifact",
        }
        return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

    def forbidden_submitter(**_kwargs):
        raise AssertionError("submitter must not run")

    with pytest.raises(ReviewAdapterError, match="model_artifact_hash_mismatch"):
        review_and_submit(
            base_url="http://127.0.0.1:8000/api", task_id="task-1",
            governor="claude", artifact_path=str(path), proposals_root=root,
            model_runner=runner, submitter=forbidden_submitter,
        )


def test_non_string_structured_fields_fail_closed(tmp_path, monkeypatch):
    root, path, digest = _proposal(tmp_path)
    monkeypatch.setattr("scripts.governor_model_review.shutil.which", lambda _name: "claude")

    def runner(command, **_kwargs):
        payload = {"artifact_sha256": digest, "decision": "approve", "summary": None}
        return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

    with pytest.raises(ReviewAdapterError, match="model_result_schema_invalid"):
        review_and_submit(
            base_url="http://127.0.0.1:8000/api", task_id="task-1",
            governor="claude", artifact_path=str(path), proposals_root=root,
            model_runner=runner,
        )


def test_chatgpt_adapter_refuses_read_capable_codex_cli(tmp_path):
    root, path, _digest = _proposal(tmp_path)
    with pytest.raises(ReviewAdapterError, match="chatgpt_toolless_adapter_unavailable"):
        review_and_submit(
            base_url="http://127.0.0.1:8000/api", task_id="task-1",
            governor="chatgpt", artifact_path=str(path), proposals_root=root,
        )


def test_dev_control_gate_runs_directly_from_repo_root():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "dev_control_gate.py")],
        cwd=ROOT, capture_output=True, text=True, timeout=30, check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert "[OK] dev-control gate" in result.stdout
