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


def test_empty_citations_not_fabricated_as_runner_auto_review():
    """Finding 2: missing citations stay missing — no synthetic runner_auto_review."""
    src = Path("app/dev_control/external_agents/runner/loop.py").read_text(encoding="utf-8")
    assert "runner_auto_review" not in src

    from app.dev_control.external_agents import adapters

    mission = Mission(
        mission_id="msn_citegate000001",
        title="t",
        description="d",
        executor="cursor",
        reviewer="claude",
        risk_class=RiskClass.GREEN,
        idempotency_key="cite-gate-key-01",
        allowed_paths=["tests/fixtures/external_agent_runner/"],
        status=MissionState.REVIEW_REQUIRED,
    )
    review = {
        "mission_id": mission.mission_id,
        "reviewer": "claude",
        "verdict": "PASS",
        "findings": [],
        "citations": [],
        "evidence_status": "MISSING",
    }
    checked = adapters.get_adapter("claude").validate_review(mission, review)
    assert checked["accepted"] is False
    assert any(
        "cite" in v.lower() or "evidence" in v.lower() or "PASS" in v for v in checked["violations"]
    )
    assert "runner_auto_review" not in json.dumps(checked)

    synth = dict(review, citations=["runner_auto_review"], evidence_status="")
    synth_checked = adapters.get_adapter("claude").validate_review(mission, synth)
    assert synth_checked["accepted"] is False
    assert any(
        "synthetic" in v.lower() or "runner_auto_review" in v for v in synth_checked["violations"]
    )


def test_redis_required_does_not_fallback_to_filelock(monkeypatch, tmp_path):
    """Finding 3: redis mode + Redis down → fail closed, no FileLock claim."""
    from app.dev_control.external_agents import cas as cas_mod

    cas_mod.reset_backend()
    monkeypatch.setenv("EXTERNAL_AGENT_COORDINATION_BACKEND", "redis")
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/15")
    monkeypatch.setattr(cas_mod, "_sync_redis", lambda: None)
    with pytest.raises(cas_mod.CasBackendError, match="redis_coordination_unavailable"):
        cas_mod.get_backend(root=str(tmp_path / "missions"))
    status = cas_mod.shared_store_status(root=str(tmp_path / "missions"))
    assert status["backend"] == "unavailable"
    assert status["mixed_backend_risk"] is False
    cas_mod.reset_backend()


def test_local_file_mode_claims_and_records_backend(monkeypatch, tmp_path):
    from app.dev_control.external_agents import cas as cas_mod

    cas_mod.reset_backend()
    monkeypatch.setenv("EXTERNAL_AGENT_COORDINATION_BACKEND", "local-file")
    monkeypatch.delenv("REDIS_URL", raising=False)
    root = tmp_path / "missions"
    root.mkdir()
    be = cas_mod.get_backend(root=str(root))
    assert be.name == "filelock"
    claim = be.claim_lease("msn_backendlocal001", "owner-a", ttl_s=60, now=1_700_000_000.0)
    assert claim["claimed"] is True
    assert claim["backend"] == "filelock"
    lease = be.get_lease("msn_backendlocal001")
    assert lease is not None and lease.backend == "filelock"
    cas_mod.reset_backend()


def test_heartbeat_lease_safety_ratio():
    """Finding 4: interval must be <= lease_ttl / 3; unsafe configs refused."""
    from app.dev_control.external_agents.runner.lease_contract import (
        derive_lease_and_interval,
        validate_heartbeat_contract,
    )

    assert validate_heartbeat_contract(lease_ttl_s=90, heartbeat_interval_s=25)["ok"] is True
    bad = validate_heartbeat_contract(lease_ttl_s=30, heartbeat_interval_s=25)
    assert bad["ok"] is False
    assert bad["reason"] == "heartbeat_interval_exceeds_lease_safety_ratio"
    assert validate_heartbeat_contract(lease_ttl_s=0, heartbeat_interval_s=5)["ok"] is False
    plan = derive_lease_and_interval(30, preferred_interval_s=25)
    assert plan["ok"] is True
    assert plan["lease_ttl_s"] >= 75  # 25 * 3
    assert plan["heartbeat_interval_s"] <= plan["lease_ttl_s"] / 3
    check = validate_heartbeat_contract(
        lease_ttl_s=plan["lease_ttl_s"],
        heartbeat_interval_s=plan["heartbeat_interval_s"],
    )
    assert check["ok"] is True


def test_amber_boolean_alone_refused_requires_decision_id(tmp_path, monkeypatch):
    """Finding 5: admin boolean cannot authorize AMBER; Owner OS decision id required."""
    from app.dev_control.external_agents import approval as amber_approval
    from app.dev_control.external_agents import orchestrator, store
    from app.platform import approvals_bridge

    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    created = orchestrator.create_mission(
        title="prepare alembic migration for billing schema",
        description="AMBER test",
        executor="cursor",
        reviewer="claude",
        idempotency_key="amber-bool-" + os.urandom(4).hex(),
        declared_risk="AMBER",
        allowed_paths=["tests/fixtures/external_agent_runner/"],
        branch="feat/ext-amber-bool",
        worktree=str(tmp_path / "wt"),
        base_sha="e64b8a9d10bcf6084488b34f886f77a5752f13f8",  # pragma: allowlist secret
    )
    mid = created["mission"]["mission_id"]
    mission = store.get(mid)
    assert mission is not None
    assert mission.risk_class is RiskClass.AMBER
    for state in (
        MissionState.PREFLIGHT,
        MissionState.CLAIMED,
        MissionState.RUNNING,
        MissionState.IMPLEMENTED,
        MissionState.TESTING,
        MissionState.REVIEW_REQUIRED,
        MissionState.REVIEW_PASSED,
        MissionState.PR_OPEN,
        MissionState.CI_RUNNING,
    ):
        mission.transition(state)
    store.save(mission)
    denied = orchestrator.advance(mid, MissionState.MERGE_QUEUED, owner_approved=True)
    assert denied["ok"] is False
    req = amber_approval.request_amber_approval(
        store.get(mid), target_state=MissionState.MERGE_QUEUED, actor="admin"
    )
    assert req["ok"]
    approvals_bridge.decide(
        "owner_os_verification",
        req["approval_decision_id"],
        "approve",
        by="owner",
        reason="ok",
    )
    ok = orchestrator.advance(
        mid, MissionState.MERGE_QUEUED, approval_decision_id=req["approval_decision_id"]
    )
    assert ok["ok"] is True
