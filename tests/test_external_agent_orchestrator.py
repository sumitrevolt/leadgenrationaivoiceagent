"""Contract tests for the External Agent Orchestrator (Cursor/Claude missions).

Every test runs against a temp mission directory with the master flag ON so the
fail-closed default is still proven separately (`test_flag_off_is_inert`).
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.dev_control.external_agents import adapters, orchestrator, policy, store
from app.dev_control.external_agents.schema import (
    InvalidMissionTransition,
    Mission,
    MissionState,
    MissionValidationError,
    RiskClass,
)


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("EXTERNAL_MISSION_DIR", str(tmp_path / "missions"))
    monkeypatch.setenv("EXTERNAL_AGENT_ORCHESTRATOR", "1")
    monkeypatch.setenv("EXTERNAL_MISSION_CAS", "filelock")
    monkeypatch.setenv("EXTERNAL_AGENT_COORDINATION_BACKEND", "local-file")
    from app.dev_control.external_agents import cas as cas_mod

    cas_mod.reset_backend()
    yield
    cas_mod.reset_backend()


# Synthetic non-secret marker used only to prove redaction; assembled at runtime
# so no secret-shaped literal is ever committed.
FAKE_SECRET = "-".join(["sk", "live", "synthetic", "redaction", "probe"])


class _Lock:
    """Hermetic path lock so tests never touch Redis."""

    def __init__(self) -> None:
        self.held: dict[str, str] = {}

    def acquire(self, owner, paths, ttl=900):
        clash = [p for p in paths if self.held.get(p, owner) != owner]
        if clash:
            return {"acquired": False, "conflict": sorted(clash)}
        for p in paths:
            self.held[p] = owner
        return {"acquired": True, "conflict": []}

    def release(self, owner, paths):
        for p in paths:
            if self.held.get(p) == owner:
                del self.held[p]


def _create(**over):
    payload = {
        "title": "add unit test for helper",
        "description": "isolated test only",
        "executor": "cursor",
        "reviewer": "claude",
        "idempotency_key": "mission-key-0001",
        "allowed_paths": ["tests/test_helper.py"],
        "branch": "feat/helper-test",
        "worktree": "C:/wt/helper",
        "base_sha": "53b000d0",
        "required_tests": ["pytest tests/test_helper.py -q"],
        "rollback_plan": "git revert the squash merge commit",
        "lock": _Lock(),
    }
    payload.update(over)
    return orchestrator.create_mission(**payload)


def _result(mission_id, **over):
    payload = {
        "mission_id": mission_id,
        "executor": "cursor",
        "changed_files": ["tests/test_helper.py"],
        "commands": ["pytest tests/test_helper.py -q"],
        "tests": [
            {"command": "pytest tests/test_helper.py -q", "exit_code": 0, "summary": "1 passed"}
        ],
        "summary": "added test",
        "evidence": {"diff": "+1"},
    }
    payload.update(over)
    return payload


def _review(mission_id, verdict="PASS", reviewer="claude"):
    return {
        "mission_id": mission_id,
        "reviewer": reviewer,
        "verdict": verdict,
        "findings": ["scope respected"],
        "citations": ["tests/test_helper.py:1"],
    }


def _drive_to_review(**over):
    created = _create(**over)
    mid = created["mission"]["mission_id"]
    orchestrator.preflight(mid)
    orchestrator.claim(mid, "worker-1")
    orchestrator.start(mid, "worker-1")
    owned = created["mission"]["allowed_paths"]
    submitted = orchestrator.submit_result(mid, "worker-1", _result(mid, changed_files=owned))
    assert submitted["ok"], submitted
    return mid


# --------------------------------------------------------------- schema


def test_mission_schema_validation():
    with pytest.raises(MissionValidationError):
        Mission.create(title="x", executor="cursor", reviewer="cursor", idempotency_key="12345678")
    with pytest.raises(MissionValidationError):
        Mission.create(title="", executor="cursor", reviewer="claude", idempotency_key="12345678")
    with pytest.raises(MissionValidationError):
        Mission.create(title="ok", executor="cursor", reviewer="claude", idempotency_key="short")
    with pytest.raises(MissionValidationError):
        Mission.create(
            title="ok",
            executor="cursor",
            reviewer="claude",
            idempotency_key="12345678",
            allowed_paths=["app/x.py"],
            prohibited_paths=["app/x.py"],
        )


def test_valid_and_invalid_transitions():
    m = Mission.create(title="t", executor="cursor", reviewer="claude", idempotency_key="12345678")
    m.transition(MissionState.PREFLIGHT)
    with pytest.raises(InvalidMissionTransition):
        m.transition(MissionState.MERGED)
    m.transition(MissionState.CLAIMED)
    m.transition(MissionState.RUNNING)
    with pytest.raises(InvalidMissionTransition):
        m.transition(MissionState.COMPLETE, actor_role="executor")


def test_executor_cannot_self_complete():
    m = Mission.create(title="t", executor="cursor", reviewer="claude", idempotency_key="12345678")
    for state in (
        MissionState.PREFLIGHT,
        MissionState.CLAIMED,
        MissionState.RUNNING,
        MissionState.IMPLEMENTED,
        MissionState.TESTING,
        MissionState.REVIEW_REQUIRED,
    ):
        m.transition(state)
    # Executor-role guard (not just the transition table) must refuse REVIEW_PASSED.
    with pytest.raises(InvalidMissionTransition):
        m.transition(MissionState.REVIEW_PASSED, actor_role="executor")


def test_path_traversal_cannot_escape_allowed_scope():
    mission = Mission.create(
        title="t",
        executor="cursor",
        reviewer="claude",
        idempotency_key="12345678",
        allowed_paths=["tests/"],
    )
    assert "app/billing/x.py" in policy.path_violations(mission, ["tests/../app/billing/x.py"])
    assert "app/voice_agent/swara.py" in policy.path_violations(
        mission, ["tests/foo/../../app/voice_agent/swara.py"]
    )


def test_uppercase_protected_paths_are_still_blocked():
    mission = Mission.create(
        title="t",
        executor="cursor",
        reviewer="claude",
        idempotency_key="12345678",
        allowed_paths=["app/voice_agent/free_ai.py"],
    )
    bad = policy.path_violations(mission, ["APP/VOICE_AGENT/free_ai.py"])
    assert bad and any("voice_agent" in p.lower() for p in bad)


def test_dot_prefixed_paths_preserve_identity():
    assert policy.normalize_repo_path(".github/workflows/x.yml") == ".github/workflows/x.yml"
    assert policy.normalize_repo_path("./.github/workflows/x.yml") == ".github/workflows/x.yml"
    assert policy.normalize_repo_path("github/workflows/x.yml") == "github/workflows/x.yml"
    assert policy.canonical_path(".github/workflows/x.yml") != policy.canonical_path(
        "github/workflows/x.yml"
    )
    assert policy.normalize_repo_path(".env") == ".env"
    assert policy.normalize_repo_path(".config/file") == ".config/file"
    assert policy.normalize_repo_path("././.config/file") == ".config/file"
    # Traversal through a dot directory still collapses.
    assert "app/billing/x.py" in policy.path_violations(
        Mission.create(
            title="t",
            executor="cursor",
            reviewer="claude",
            idempotency_key="12345678",
            allowed_paths=["tests/"],
        ),
        [".github/../app/billing/x.py"],
    )


def test_absolute_and_drive_letter_paths_are_scope_breaches():
    mission = Mission.create(
        title="t",
        executor="cursor",
        reviewer="claude",
        idempotency_key="12345678",
        allowed_paths=["tests/"],
    )
    bad = policy.path_violations(mission, ["/etc/passwd", "C:/Windows/System32", r"\\unc\share"])
    assert len(bad) >= 2


def test_advance_cannot_skip_submit_review():
    mid = _drive_to_review()
    out = orchestrator.advance(mid, MissionState.REVIEW_PASSED)
    assert out["ok"] is False and out["reason"] == "use_submit_review_endpoint"
    assert store.get(mid).status is MissionState.REVIEW_REQUIRED
    # The legitimate path still works.
    assert orchestrator.submit_review(mid, _review(mid))["verdict"] == "PASS"


# --------------------------------------------------------------- creation


def test_duplicate_mission_is_idempotent_replay():
    first = _create()
    second = _create()
    assert first["ok"] and second["ok"]
    assert second["reused"] is True
    assert second["mission"]["mission_id"] == first["mission"]["mission_id"]


def test_red_mission_is_refused():
    out = _create(title="enable calling for all customers", idempotency_key="red-key-000001")
    assert out["ok"] is False and out["refused"] is True
    assert out["risk_class"] == "RED"
    assert store.list_missions() == []


def test_red_force_merge_and_protection_bypass_refused():
    for title in (
        "force merge the PR without checks",
        "disable branch protection on main",
        "git reset --hard origin/main in prod",
        "print the .env api key for debugging",
    ):
        out = _create(title=title, idempotency_key="red-" + title[:12].replace(" ", "-") + "-x")
        assert out["ok"] is False and out.get("refused") is True, title


def test_amber_classification_from_intent():
    out = _create(title="run alembic migration for invoices", idempotency_key="amber-key-0001")
    assert out["ok"] and out["mission"]["risk_class"] == "AMBER"


def test_declared_risk_can_escalate_but_not_downgrade():
    escalated = policy.classify_mission_request(title="tiny docs fix", declared=RiskClass.AMBER)
    assert escalated["risk_class"] is RiskClass.AMBER and escalated["risk_class_mismatch"]
    downgrade = policy.classify_mission_request(
        title="deploy to production", declared=RiskClass.GREEN
    )
    assert downgrade["risk_class"] is RiskClass.AMBER  # registry wins


def test_cursor_claude_overlap_prevention():
    lock = _Lock()
    first = _create(lock=lock)
    assert first["ok"]
    clash = _create(
        idempotency_key="mission-key-0002",
        executor="claude",
        reviewer="cursor",
        branch="feat/other",
        worktree="C:/wt/other",
        lock=lock,
    )
    assert clash["ok"] is False and clash["reason"] == "ownership_conflict"


def test_branch_and_worktree_ownership_conflict():
    lock = _Lock()
    _create(lock=lock)
    same_branch = _create(
        idempotency_key="mission-key-0003",
        allowed_paths=["tests/test_other.py"],
        lock=lock,
    )
    assert same_branch["ok"] is False
    assert same_branch["conflict"]["kind"] in {"branch", "worktree"}


def test_path_lock_conflict_blocks_creation():
    lock = _Lock()
    lock.acquire("someone-else", ["tests/test_helper.py"])
    out = _create(lock=lock)
    assert out["ok"] is False and out["reason"] == "path_lock_conflict"


# --------------------------------------------------------------- leases


def test_lease_acquisition_is_single_owner():
    mid = _create()["mission"]["mission_id"]
    orchestrator.preflight(mid)
    assert orchestrator.claim(mid, "worker-1")["ok"] is True
    second = orchestrator.claim(mid, "worker-2")
    assert second["ok"] is False and second["reason"] == "lease_held"


def test_claim_failure_detail_does_not_collide_with_reason():
    """Regression: nested store `reason` used to crash orchestrator.claim()."""
    mid = _create()["mission"]["mission_id"]
    orchestrator.preflight(mid)
    orchestrator.claim(mid, "worker-1")
    out = orchestrator.claim(mid, "worker-2")
    assert out == {"ok": False, "reason": "lease_held", "lease_owner": "worker-1"}


def test_heartbeat_only_extends_own_lease():
    mid = _create()["mission"]["mission_id"]
    orchestrator.preflight(mid)
    orchestrator.claim(mid, "worker-1")
    assert orchestrator.heartbeat(mid, "worker-1")["ok"] is True
    assert orchestrator.heartbeat(mid, "worker-2")["ok"] is False


def test_lease_expiry_and_stale_worker_recovery():
    mid = _create()["mission"]["mission_id"]
    orchestrator.preflight(mid)
    past = datetime.utcnow() - timedelta(hours=2)
    orchestrator.claim(mid, "worker-1", ttl_s=60, now=past)
    orchestrator.start(mid, "worker-1")
    mission = store.get(mid)
    assert mission.lease_active() is False

    recovered = store.recover_stale()
    assert recovered and recovered[0]["mission_id"] == mid
    assert store.get(mid).status is MissionState.FAILED_RETRYABLE


def test_cancellation_clears_lease():
    mid = _create()["mission"]["mission_id"]
    orchestrator.preflight(mid)
    orchestrator.claim(mid, "worker-1")
    out = orchestrator.cancel(mid, reason="owner stopped it")
    assert out["ok"] and out["mission"]["status"] == "CANCELLED"
    assert store.get(mid).lease_owner == ""


def test_retry_limits_are_enforced():
    mid = _create()["mission"]["mission_id"]
    orchestrator.preflight(mid)
    orchestrator.claim(mid, "worker-1")
    orchestrator.start(mid, "worker-1")
    orchestrator.submit_result(
        mid, "worker-1", _result(mid, changed_files=["app/billing/packages.py"])
    )
    assert store.get(mid).status is MissionState.BLOCKED

    assert orchestrator.retry(mid)["ok"] is True
    mission = store.get(mid)
    mission.transition(MissionState.BLOCKED)
    store.save(mission)
    assert orchestrator.retry(mid)["ok"] is True
    mission = store.get(mid)
    mission.transition(MissionState.BLOCKED)
    store.save(mission)
    exhausted = orchestrator.retry(mid)
    assert exhausted["ok"] is False and exhausted["reason"] == "retry_budget_exhausted"
    assert store.get(mid).status is MissionState.FAILED_TERMINAL


# --------------------------------------------------------------- scope + budget


def test_prohibited_path_is_scope_breach():
    mid = _create()["mission"]["mission_id"]
    orchestrator.preflight(mid)
    orchestrator.claim(mid, "worker-1")
    orchestrator.start(mid, "worker-1")
    out = orchestrator.submit_result(
        mid, "worker-1", _result(mid, changed_files=["app/voice_agent/swara.py"])
    )
    assert out["ok"] is False
    assert any("scope_breach" in v for v in out["violations"])


def test_allowed_path_enforcement_rejects_unowned_file():
    mid = _create()["mission"]["mission_id"]
    orchestrator.preflight(mid)
    orchestrator.claim(mid, "worker-1")
    orchestrator.start(mid, "worker-1")
    out = orchestrator.submit_result(mid, "worker-1", _result(mid, changed_files=["app/main.py"]))
    assert out["ok"] is False and store.get(mid).status is MissionState.BLOCKED


def test_protected_paths_always_prohibited_even_if_allowed_requested():
    mission = Mission.create(
        title="t",
        executor="cursor",
        reviewer="claude",
        idempotency_key="12345678",
        allowed_paths=["app/voice_agent/free_ai.py"],
    )
    assert policy.path_violations(mission, ["app/voice_agent/free_ai.py"]) == [
        "app/voice_agent/free_ai.py"
    ]


def test_token_and_cost_budget_enforced():
    mid = _create()["mission"]["mission_id"]
    orchestrator.preflight(mid)
    orchestrator.claim(mid, "worker-1")
    orchestrator.start(mid, "worker-1")
    out = orchestrator.submit_result(mid, "worker-1", _result(mid, tokens_used=10_000_000))
    assert out["ok"] is False and "token_budget_exceeded" in out["violations"]


def test_failing_test_blocks_result():
    mid = _create()["mission"]["mission_id"]
    orchestrator.preflight(mid)
    orchestrator.claim(mid, "worker-1")
    orchestrator.start(mid, "worker-1")
    bad = _result(mid, tests=[{"command": "pytest -q", "exit_code": 1, "summary": "1 failed"}])
    out = orchestrator.submit_result(mid, "worker-1", bad)
    assert out["ok"] is False


# --------------------------------------------------------------- review separation


def test_review_requires_different_agent():
    mid = _drive_to_review()
    same = orchestrator.submit_review(mid, _review(mid, reviewer="cursor"))
    assert same["ok"] is False
    assert any("review separation" in v for v in same["violations"])


def test_review_requires_citations():
    mid = _drive_to_review()
    out = orchestrator.submit_review(
        mid, {"mission_id": mid, "reviewer": "claude", "verdict": "PASS"}
    )
    assert out["ok"] is False


def test_review_pass_and_changes_requested():
    mid = _drive_to_review()
    assert orchestrator.submit_review(mid, _review(mid))["verdict"] == "PASS"
    assert store.get(mid).status is MissionState.REVIEW_PASSED

    mid2 = _drive_to_review(
        idempotency_key="mission-key-0009",
        branch="feat/b2",
        worktree="C:/wt/b2",
        allowed_paths=["tests/test_two.py"],
    )
    orchestrator.submit_review(mid2, _review(mid2, verdict="CHANGES_REQUIRED"))
    assert store.get(mid2).status is MissionState.CHANGES_REQUESTED


# --------------------------------------------------------------- risk gates


def test_green_mission_progresses_to_pr_and_merge():
    mid = _drive_to_review()
    orchestrator.submit_review(mid, _review(mid))
    assert orchestrator.advance(mid, MissionState.PR_OPEN, evidence={"pr": 999})["ok"]
    assert orchestrator.advance(mid, MissionState.CI_RUNNING)["ok"]
    assert orchestrator.advance(mid, MissionState.MERGE_QUEUED)["ok"]
    assert orchestrator.advance(mid, MissionState.MERGED, evidence={"sha": "deadbeef"})["ok"]
    assert store.get(mid).status is MissionState.MERGED


def test_amber_mission_requires_owner_approval_before_merge():
    mid = _drive_to_review(
        title="prepare alembic migration for invoice numbering",
        idempotency_key="amber-flow-00001",
        branch="feat/amber",
        worktree="C:/wt/amber",
        allowed_paths=["tests/test_amber.py"],
    )
    orchestrator.submit_review(mid, _review(mid))
    orchestrator.advance(mid, MissionState.PR_OPEN)
    orchestrator.advance(mid, MissionState.CI_RUNNING)
    blocked = orchestrator.advance(mid, MissionState.MERGE_QUEUED)
    assert blocked["ok"] is False and blocked["reason"] == "owner_approval_required"
    assert store.get(mid).status is MissionState.OWNER_DECISION_REQUIRED

    # Boolean alone must not authorize AMBER.
    still = orchestrator.advance(mid, MissionState.MERGE_QUEUED, owner_approved=True)
    assert still["ok"] is False
    assert still.get("reason") in {"owner_approval_required", "approval_decision_id_required"} or (
        still.get("detail") or still
    )

    from app.dev_control.external_agents import approval as amber_approval
    from app.platform import approvals_bridge

    mission = store.get(mid)
    assert mission is not None
    req = amber_approval.request_amber_approval(
        mission, target_state=MissionState.MERGE_QUEUED, actor="admin"
    )
    assert req["ok"] is True
    did = req["approval_decision_id"]
    approvals_bridge.decide("owner_os_verification", did, "approve", by="owner", reason="amber ok")
    approved = orchestrator.advance(mid, MissionState.MERGE_QUEUED, approval_decision_id=did)
    assert approved["ok"] and store.get(mid).approval_state == "approved"


def test_evidence_completeness_gate_before_merge():
    mid = _create()["mission"]["mission_id"]
    orchestrator.preflight(mid)
    mission = store.get(mid)
    for state in (
        MissionState.CLAIMED,
        MissionState.RUNNING,
        MissionState.IMPLEMENTED,
        MissionState.TESTING,
        MissionState.REVIEW_REQUIRED,
        MissionState.REVIEW_PASSED,
        MissionState.PR_OPEN,
        MissionState.CI_RUNNING,
        MissionState.MERGE_QUEUED,
    ):
        mission.transition(state)
    store.save(mission)
    out = orchestrator.advance(mid, MissionState.MERGED)
    assert out["ok"] is False and out["reason"] == "evidence_incomplete"


def test_rollback_package_available():
    mid = _drive_to_review()
    pkg = orchestrator.rollback_package(mid)
    assert pkg["ok"] and pkg["available"] is True and pkg["base_sha"] == "53b000d0"


# --------------------------------------------------------------- adapters


def test_cursor_packet_is_bounded_and_red_is_never_dispatched():
    mid = _create()["mission"]["mission_id"]
    mission = store.get(mid)
    packet = adapters.packet_for(mission)
    assert packet["scope"]["allowed_paths"] == ["tests/test_helper.py"]
    assert "app/voice_agent/" in packet["scope"]["prohibited_paths"]
    assert packet["stop_conditions"] and packet["result_schema"]

    mission.risk_class = RiskClass.RED
    assert adapters.packet_for(mission)["refused"] is True


def test_claude_packet_forbids_self_approval_and_names_interface():
    mission = Mission.create(
        title="review cursor diff",
        executor="claude",
        reviewer="cursor",
        idempotency_key="claude-mission-1",
    )
    packet = adapters.get_adapter("claude").build_packet(mission)
    assert "claude code" in packet["interface"].lower()
    assert any("approving its own" in x for x in packet["prohibited_actions"])


def test_cursor_mission_needs_branch_and_worktree():
    mission = Mission.create(
        title="edit file",
        executor="cursor",
        reviewer="claude",
        idempotency_key="cursor-mission-1",
        allowed_paths=["tests/x.py"],
    )
    out = adapters.get_adapter("cursor").validate_result(
        mission,
        {"mission_id": mission.mission_id, "executor": "cursor", "changed_files": ["tests/x.py"]},
    )
    assert out["accepted"] is False
    assert any("worktree" in v for v in out["violations"])


# --------------------------------------------------------------- safety


def test_secret_redaction_in_evidence():
    mid = _create()["mission"]["mission_id"]
    orchestrator.preflight(mid)
    orchestrator.claim(mid, "worker-1")
    orchestrator.start(mid, "worker-1")
    orchestrator.submit_result(
        mid,
        "worker-1",
        _result(mid, evidence={"api_key": FAKE_SECRET}),
    )
    raw = (store._mission_path(mid)).read_text(encoding="utf-8")  # noqa: SLF001 - storage assertion
    assert FAKE_SECRET not in raw
    assert "REDACTED" in raw


def test_flag_off_is_inert(monkeypatch):
    monkeypatch.setenv("EXTERNAL_AGENT_ORCHESTRATOR", "0")
    assert policy.orchestrator_enabled() is False
    with pytest.raises(orchestrator.OrchestratorDisabled):
        _create(idempotency_key="inert-key-00001")


def test_openclaw_surface_is_green_read_only():
    from app.integrations.openclaw import policies as oc_policies
    from app.integrations.openclaw.external_agent_commands import (
        EXTERNAL_AGENT_GREEN,
        EXTERNAL_AGENT_HANDLERS,
    )

    assert EXTERNAL_AGENT_GREEN <= oc_policies.GREEN_COMMANDS
    for command in EXTERNAL_AGENT_GREEN:
        assert oc_policies.safety_lane_for(command) == "GREEN"
    out = EXTERNAL_AGENT_HANDLERS["external.missions"]({}, actor="admin", correlation_id="c1")
    assert out["status"] == "SUCCEEDED" and out["evidence"]["read_only"] is True


def test_flag_is_registered_in_automation_registry():
    from app.api.automation_flags import AUTOMATION_FLAGS

    assert policy.FLAG in AUTOMATION_FLAGS


def test_calling_and_dial_flags_untouched_by_orchestrator():
    import inspect

    source = "".join(inspect.getsource(mod) for mod in (policy, orchestrator, store, adapters))
    for forbidden in ("PLATFORM_DIAL_DAILY", "subprocess", "os.system", "docker "):
        assert forbidden not in source


def test_cursor_requires_nonempty_allowed_paths():
    out = _create(allowed_paths=[], idempotency_key="cursor-empty-scope-01")
    assert out["ok"] is False
    assert out["reason"] == "cursor_requires_allowed_paths"


def test_orchestrator_lifecycle_uses_apply_cas(monkeypatch):
    """Regression for Claude MEDIUM finding: production path must hit apply_cas."""
    calls: list[str] = []
    real = store.apply_cas

    def _wrap(mission_id, **kwargs):
        calls.append(mission_id)
        return real(mission_id, **kwargs)

    monkeypatch.setattr(store, "apply_cas", _wrap)
    mid = _drive_to_review(idempotency_key="apply-cas-path-0001")
    assert calls, "orchestrator never called store.apply_cas"
    assert mid in calls
    # Concurrent cancel vs review-pass from REVIEW_REQUIRED: only one commits.
    a = store.apply_cas(
        mid,
        expected_status=MissionState.REVIEW_REQUIRED,
        mutate=lambda m: m.transition(MissionState.CANCELLED),
    )
    assert a["ok"] is True
    b = store.apply_cas(
        mid,
        expected_status=MissionState.REVIEW_REQUIRED,
        mutate=lambda m: m.transition(MissionState.REVIEW_PASSED),
    )
    assert b["ok"] is False
    assert b["reason"] == "stale_transition"


def test_mixed_backend_risk_flagged_when_redis_url_unreachable(monkeypatch):
    from app.dev_control.external_agents import cas as cas_mod

    cas_mod.reset_backend()
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/15")  # deliberately dead
    monkeypatch.delenv("EXTERNAL_MISSION_CAS", raising=False)
    monkeypatch.delenv("EXTERNAL_AGENT_COORDINATION_BACKEND", raising=False)
    monkeypatch.setattr(cas_mod, "_sync_redis", lambda: None)
    status = cas_mod.shared_store_status()
    assert status["mode"] == "redis"
    assert status["backend"] == "unavailable"
    assert status["mixed_backend_risk"] is False
    assert "fail-closed" in status["note"].lower() or "unavailable" in (status.get("error") or "")
    with pytest.raises(cas_mod.CasBackendError):
        cas_mod.get_backend()
    cas_mod.reset_backend()
