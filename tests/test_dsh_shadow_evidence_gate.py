from __future__ import annotations

import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.api import dsh_internal
from app.platform.workforce_runtime import scheduled
from app.platform.workforce_runtime.types import WorkforceRequest, WorkforceResult
from app.tasks import dsh_jobs

dispatch = importlib.import_module("app.platform.workforce_runtime.dispatch")
ROOT = Path(__file__).resolve().parents[1]
GATE_PATH = ROOT / "deploy" / "dsh" / "evidence" / "shadow_promotion_gate.json"
GOLDEN_PATH = ROOT / "tests" / "fixtures" / "dsh_shadow_golden_set.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _promotion_blockers(gate: dict, golden: dict) -> list[str]:
    required = gate["required"]
    observed = gate["observed"]
    blockers: list[str] = []
    if observed["turns"] < required["minimum_turns"]:
        blockers.append("minimum_turns")
    if observed["duration_days"] < required["minimum_duration_days"]:
        blockers.append("minimum_duration_days")
    if observed["shadow_side_effects"] > required["maximum_shadow_side_effects"]:
        blockers.append("shadow_side_effects")
    if any(case["status"] != "passed" for case in golden["cases"]):
        blockers.append("golden_cases")
    artifacts = gate.get("artifacts") or []
    if required["artifact_sha256_required"] and (
        not artifacts
        or any(
            len(str(artifact.get("sha256") or "")) != 64
            for artifact in artifacts
            if isinstance(artifact, dict)
        )
    ):
        blockers.append("artifact_sha256")
    return blockers


def test_shadow_promotion_gate_is_honestly_blocked_until_soak_evidence() -> None:
    gate = _load(GATE_PATH)
    golden = _load(GOLDEN_PATH)

    assert gate["evidence_label"] == "LOCAL_ONLY_NOT_SOAKED"
    assert gate["promotion_allowed"] is False
    assert gate["safe_default"] == {
        "flag": "DSH_SHADOW_ENABLED",
        "default": "0",
        "authority": "direct",
        "shadow_side_effects_allowed": False,
    }
    assert set(_promotion_blockers(gate, golden)) == {
        "minimum_turns",
        "minimum_duration_days",
        "golden_cases",
        "artifact_sha256",
    }


def test_shadow_golden_set_has_unique_pending_contract_stubs() -> None:
    golden = _load(GOLDEN_PATH)
    cases = golden["cases"]
    ids = [case["id"] for case in cases]

    assert golden["evidence_state"] == "STUB_NOT_EXECUTED"
    assert golden["authoritative_runtime"] == "direct"
    assert golden["shadow_runtime"] == "dsh"
    assert len(ids) == len(set(ids)) == 8
    assert all(case["status"] == "pending" for case in cases)
    assert {
        "policy_tenant_refusal",
        "policy_approval_refusal",
        "tool_allowlist_refusal",
        "duplicate_submit",
        "unknown_outcome",
        "approval_mutation",
        "cross_tenant_status_read",
        "cancel",
    } == set(ids)


@pytest.mark.asyncio
async def test_shadow_default_off_has_no_queue_or_side_effect_path(monkeypatch) -> None:
    monkeypatch.delenv("DSH_RUNTIME_ENABLED", raising=False)
    monkeypatch.delenv("DSH_SHADOW_ENABLED", raising=False)
    monkeypatch.setenv("DSH_AGENT_ALLOWLIST", "kavya")
    direct_calls: list[str] = []

    async def fake_direct(request: WorkforceRequest) -> WorkforceResult:
        direct_calls.append(request.run_id)
        return WorkforceResult(
            run_id=request.run_id,
            agent_id=request.agent_id,
            action=request.action,
            status="succeeded",
            provider="direct",
        )

    def unexpected_enqueue(*_args, **_kwargs):
        raise AssertionError("DSH enqueue must be unreachable while both flags are off")

    monkeypatch.setattr(dispatch, "_direct", fake_direct)
    monkeypatch.setattr(dispatch, "_enqueue_dsh", unexpected_enqueue)
    result = await dispatch.dispatch(
        WorkforceRequest(
            agent_id="kavya",
            action="ops_health_check",
            payload={"opaque_ref": "lead_123"},
            tenant_id="tenant-a",
            idempotency_key="shadow_default_off",
        )
    )

    assert result.provider == "direct"
    assert len(direct_calls) == 1
    assert dispatch.provider_for("kavya") == "direct"


def test_shadow_child_has_no_capability_or_approval_mutation_tools() -> None:
    allowed = set(dsh_jobs._allowed_tools({"shadow": True, "action": "ops_health_check"}))

    assert allowed == {"dsh_llm_chat", "dsh_heartbeat"}
    assert not any(tool.startswith("dsh_capability_submit:") for tool in allowed)
    assert "dsh_approval_proposal" not in allowed
    assert not any(
        token in operation.lower()
        for operation in dsh_internal.MCP_OPERATION_IDS
        for token in ("approve", "reject", "execute", "publish", "send")
    )


def test_dsh_policy_refusal_preserves_canonical_reason_and_decision(monkeypatch) -> None:
    from app.platform import agent_runtime, agent_runtime_workforce

    decision = {
        "allowed": False,
        "reason_code": "tenant_mismatch",
        "control_source": "agent_runtime",
    }
    canonical = SimpleNamespace(
        status="blocked",
        reason="tenant_mismatch",
        decision=decision,
    )
    monkeypatch.setattr(agent_runtime_workforce, "ensure_workforce_registered", lambda: None)
    monkeypatch.setattr(
        agent_runtime,
        "evaluate_policy",
        lambda _task: (SimpleNamespace(), SimpleNamespace(), canonical),
    )

    result = dispatch._dsh_preflight(
        WorkforceRequest(
            agent_id="kavya",
            action="tenant_probe",
            payload={"client_id": "tenant-b"},
            tenant_id="tenant-a",
        )
    )

    assert result is not None
    assert result.status == canonical.status
    assert result.reason == canonical.reason
    assert result.decision == canonical.decision


@pytest.mark.asyncio
async def test_scheduler_and_manual_calls_share_single_dispatch_entry(monkeypatch) -> None:
    monkeypatch.setattr(
        scheduled,
        "runtime_status",
        lambda: {
            "dsh_runtime_enabled": True,
            "dsh_shadow_enabled": False,
            "dsh_agent_allowlist": ["kavya"],
        },
    )
    monkeypatch.setattr(
        "app.platform.owner_agent_execution.agent_for_job",
        lambda _job: "kavya",
    )
    monkeypatch.setattr(scheduled, "_register", lambda *_args: "scheduled__ops")
    seen: list[WorkforceRequest] = []

    async def fake_dispatch(request: WorkforceRequest) -> WorkforceResult:
        seen.append(request)
        return WorkforceResult(
            run_id=request.run_id,
            agent_id=request.agent_id,
            action=request.action,
            status="queued",
            provider="dsh",
        )

    monkeypatch.setattr(scheduled, "dispatch", fake_dispatch)
    await scheduled.maybe_dispatch("ops", idempotency_key="scheduled_once_123")
    await fake_dispatch(
        WorkforceRequest(
            agent_id="kavya",
            action="ops_health_check",
            trigger="owner_os",
            idempotency_key="manual_once_123",
        )
    )

    assert [request.trigger for request in seen] == ["scheduler", "owner_os"]
    assert all(isinstance(request, WorkforceRequest) for request in seen)


def test_dsh_container_has_default_deny_egress_and_no_child_secrets() -> None:
    compose = (ROOT / "docker-compose.vps.yml").read_text(encoding="utf-8")
    service = compose.split("\n  dsh-worker:", 1)[1].split("\n  scheduler:", 1)[0]
    network = compose.split("\nnetworks:", 1)[1]

    assert "networks: [dsh_net]" in service
    assert "env_file:" not in service
    assert "internal: true" in network
    assert "DATABASE_URL" not in service
    assert "UPI_VPA" not in service
    assert "API_KEY" not in service
    assert dsh_jobs.CHILD_ENV_NAMES == {
        "DSH_RUN_TOKEN",
        "DSH_MCP_URL",
        "DSH_LLM_BASE_URL",
        "DSH_CORDIS_CONFIG",
        "HOME",
    }


def test_voice_agents_remain_frozen_and_outside_dsh_dispatch() -> None:
    assert dispatch.FROZEN_AGENTS == {"swara", "ananya"}
    for agent_id in dispatch.FROZEN_AGENTS:
        assert dispatch.provider_for(agent_id) == "direct"
        assert dispatch.rollout_wave(agent_id) == "frozen"


@pytest.mark.asyncio
async def test_child_process_termination_is_bounded_and_clean() -> None:
    class FakeProcess:
        returncode = None
        terminated = False
        killed = False

        def terminate(self) -> None:
            self.terminated = True

        def kill(self) -> None:
            self.killed = True

        async def wait(self) -> int:
            self.returncode = 0
            return 0

    process = FakeProcess()
    elapsed = await dsh_jobs._terminate(process)

    assert process.terminated is True
    assert process.killed is False
    assert process.returncode == 0
    assert elapsed < 5.0


@pytest.mark.asyncio
async def test_dsh_cancellation_check_is_fail_closed(monkeypatch) -> None:
    from app.platform import agent_runtime_cancellation as cancellation

    monkeypatch.setattr(
        cancellation,
        "is_requested",
        lambda _agent_id, _run_id: SimpleNamespace(
            requested=True,
            status="requested",
        ),
    )
    requested, reason = await dsh_jobs._cancel_requested(
        {"agent_id": "kavya", "run_id": "dshrun_cancel123"}
    )
    assert (requested, reason) == (True, "cancel_requested")

    monkeypatch.setattr(
        cancellation,
        "is_requested",
        lambda _agent_id, _run_id: SimpleNamespace(
            requested=False,
            status="store_unavailable",
        ),
    )
    requested, reason = await dsh_jobs._cancel_requested(
        {"agent_id": "kavya", "run_id": "dshrun_cancel123"}
    )
    assert (requested, reason) == (True, "cancellation_store_unavailable")
