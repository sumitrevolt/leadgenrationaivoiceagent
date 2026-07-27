"""PR #147 cycle-6 — five MEDIUM residual regressions (authority/consistency)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from app.dev_control.external_agents.schema import Mission, MissionState, RiskClass


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    monkeypatch.setenv("EXTERNAL_MISSION_DIR", str(tmp_path / "missions"))
    monkeypatch.setenv("EXTERNAL_AGENT_ORCHESTRATOR", "1")
    monkeypatch.setenv("EXTERNAL_AGENT_RUNNER", "1")
    monkeypatch.setenv("EXTERNAL_MISSION_CAS", "filelock")
    monkeypatch.setenv("EXTERNAL_AGENT_COORDINATION_BACKEND", "local-file")
    monkeypatch.setenv("EXTERNAL_AGENT_WORKTREE_ROOT", str(tmp_path / "wts"))
    from app.dev_control.external_agents import cas as cas_mod

    cas_mod.reset_backend()
    yield
    cas_mod.reset_backend()


def test_live_invoke_claude_uses_review_parse(monkeypatch, tmp_path):
    """Finding 1: live Claude review must ingest via review_parse, not ad-hoc extract."""
    from app.dev_control.external_agents.runner import claude_exec, review_parse
    from app.dev_control.external_agents.runner.process_safe import ProcessResult

    mid = "msn_liveparser00001"
    mission = Mission(
        mission_id=mid,
        title="t",
        description="d",
        executor="cursor",
        reviewer="claude",
        risk_class=RiskClass.GREEN,
        idempotency_key="live-parser-key-01",
        worktree=str(tmp_path),
        base_sha="deadbeefcafebabe",  # pragma: allowlist secret
        allowed_paths=["tests/fixtures/external_agent_runner/"],
    )

    called: dict[str, int] = {"recover": 0, "extract": 0}
    real_recover = review_parse.recover_independent_review

    def spy_recover(*a, **k):
        called["recover"] += 1
        return real_recover(*a, **k)

    def spy_extract(*a, **k):
        called["extract"] += 1
        raise AssertionError("extract_review_manifest must not be the live path")

    monkeypatch.setattr(review_parse, "recover_independent_review", spy_recover)
    monkeypatch.setattr(claude_exec, "extract_review_manifest", spy_extract)
    monkeypatch.setattr(claude_exec, "auth_ok", lambda: {"ok": True})
    monkeypatch.setattr(
        claude_exec,
        "build_claude_argv",
        lambda prompt, add_dir="": ["python", "-c", "print('noop')"],
    )

    inner = {
        "mission_id": mid,
        "reviewer": "claude",
        "verdict": "PASS",
        "findings": ["tests/fixtures/external_agent_runner/STATUS.txt:1"],
        "citations": ["tests/fixtures/external_agent_runner/STATUS.txt:1"],
        "reviewed_head_sha": mission.base_sha,
    }
    stdout = json.dumps({"result": json.dumps(inner)})

    def fake_run(*_a, **_k):
        return ProcessResult(
            exit_code=0,
            stdout=stdout,
            stderr="",
            duration_s=0.1,
            timed_out=False,
            cancelled=False,
            termination_reason="exited",
            pid=1,
            truncated=False,
        )

    monkeypatch.setattr(claude_exec, "run_allowlisted", fake_run)

    _proc, review, evidence = claude_exec.invoke_claude_review(
        mission,
        result_manifest={"mission_id": mid, "executor": "cursor"},
        diff_text="",
        allowed_root=str(tmp_path),
        timeout_s=30,
    )
    assert called["recover"] >= 1
    assert called["extract"] == 0
    assert review is not None
    assert review["verdict"] == "PASS"
    assert evidence.get("parser", {}).get("status") == "ok"
