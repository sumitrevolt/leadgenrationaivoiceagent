from __future__ import annotations

import asyncio
import hashlib
import json
import time
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.dev_control.deploy import promote_to_staging
from app.dev_control.governor_auth import ATTESTATION_VERSION, build_governor_signature
from app.dev_control.governor_reviews import (
    artifact_sha256,
    record_governor_review,
    review_gate_status,
)
from app.dev_control.service import TaskState


ARTIFACT = "diff --git a/app/a.py b/app/a.py\n+safe change\n"
ARTIFACT_HASH = hashlib.sha256(ARTIFACT.encode("utf-8")).hexdigest()
CLAUDE_SECRET = "c" * 40


class FakeDb:
    def __init__(self, task):
        self.task = task
        self.commits = 0

    async def get(self, _model, _task_id):
        return self.task

    async def scalar(self, _statement):
        return self.task

    async def commit(self):
        self.commits += 1

    async def refresh(self, _task):
        return None


def _report() -> dict:
    return {"proposal_sha256": ARTIFACT_HASH, "governor_reviews": {}}


def _auth(nonce: str) -> dict:
    return {"attestation_version": ATTESTATION_VERSION, "attestation_nonce": nonce}


def _endpoint_task() -> SimpleNamespace:
    return SimpleNamespace(
        worker_report=json.dumps(_report()),
        updated_at=None,
        state=TaskState.REVIEW_REQUIRED.value,
        id="t1",
        idempotency_key="idem-review-2",
        parent_objective="review",
        customer_id=None,
        priority=50,
        selected_provider="omniroute",
        selected_model="free-coding-safe",
        fallback_models=None,
        worktree_path=None,
        branch_name=None,
        file_ownership=None,
        dependencies=None,
        acceptance_criteria=None,
        retry_count=0,
        lease_owner=None,
        lease_until=None,
        test_evidence=None,
        deployment_evidence=None,
        delivery_evidence=None,
        created_at=None,
        blocked_reason=None,
    )


def test_artifact_hash_is_deterministic_sha256():
    assert artifact_sha256(ARTIFACT) == ARTIFACT_HASH


def test_two_distinct_governors_must_approve_same_artifact():
    report = record_governor_review(
        _report(),
        governor="claude",
        decision="approve",
        artifact_hash=ARTIFACT_HASH,
        summary="safe",
        reviewed_by="admin",
        **_auth("claude_approval_nonce_001"),
    )
    assert review_gate_status(report)["approved"] is False
    report = record_governor_review(
        report,
        governor="chatgpt",
        decision="approve",
        artifact_hash=ARTIFACT_HASH,
        summary="tests bounded",
        reviewed_by="admin",
        **_auth("chatgpt_approval_nonce_001"),
    )
    status = review_gate_status(report)
    assert status["approved"] is True
    assert status["approved_governors"] == ["chatgpt", "claude"]


def test_duplicate_governor_is_idempotent_not_a_second_approval():
    report = record_governor_review(
        _report(),
        governor="claude",
        decision="approve",
        artifact_hash=ARTIFACT_HASH,
        summary="first",
        reviewed_by="admin",
        **_auth("claude_update_nonce_001"),
    )
    report = record_governor_review(
        report,
        governor="claude",
        decision="approve",
        artifact_hash=ARTIFACT_HASH,
        summary="updated",
        reviewed_by="admin",
        **_auth("claude_update_nonce_002"),
    )
    assert list(report["governor_reviews"]) == ["claude"]
    assert review_gate_status(report)["approved"] is False


@pytest.mark.parametrize("decision", ["changes_requested", "reject"])
def test_non_approval_decision_blocks_gate(decision):
    report = _report()
    for governor in ("claude", "chatgpt"):
        report = record_governor_review(
            report,
            governor=governor,
            decision="approve" if governor == "claude" else decision,
            artifact_hash=ARTIFACT_HASH,
            summary="bounded",
            reviewed_by="admin",
            **_auth(f"{governor}_{decision}_nonce_001"),
        )
    assert review_gate_status(report)["approved"] is False
    assert review_gate_status(report)["blocking_decisions"]


def test_hash_mismatch_and_malformed_report_fail_closed():
    with pytest.raises(ValueError, match="artifact_hash_mismatch"):
        record_governor_review(
            _report(),
            governor="claude",
            decision="approve",
            artifact_hash="0" * 64,
            summary="wrong artifact",
            reviewed_by="admin",
            **_auth("claude_mismatch_nonce_001"),
        )
    assert review_gate_status("not-json")["approved"] is False
    assert review_gate_status({"proposal_sha256": "bad"})["approved"] is False


def test_promote_to_staging_requires_dual_review():
    task = SimpleNamespace(
        state=TaskState.REVIEW_REQUIRED.value,
        worker_report=json.dumps(_report()),
        test_evidence=None,
        updated_at=None,
    )
    db = FakeDb(task)
    blocked = asyncio.run(promote_to_staging(db, "t1", tests_passed=True))
    assert blocked == {
        "ok": False,
        "reason": "dual_governor_review_required",
        "review_gate": review_gate_status(_report()),
    }
    assert task.state == TaskState.REVIEW_REQUIRED.value
    assert db.commits == 0

    report = _report()
    for governor in ("claude", "chatgpt"):
        report = record_governor_review(
            report,
            governor=governor,
            decision="approve",
            artifact_hash=ARTIFACT_HASH,
            summary="approved",
            reviewed_by="admin",
            **_auth(f"{governor}_promotion_nonce_001"),
        )
    task.worker_report = json.dumps(report)
    allowed = asyncio.run(promote_to_staging(db, "t1", tests_passed=True))
    assert allowed["ok"] is True
    assert task.state == TaskState.STAGING_READY.value


def test_generic_transition_cannot_bypass_dual_review(monkeypatch):
    from app.api.dev_tasks import TransitionRequest, transition_task

    monkeypatch.setenv("DEV_ORCHESTRATOR", "1")
    task = SimpleNamespace(
        state=TaskState.REVIEW_REQUIRED.value,
        worker_report=json.dumps(_report()),
        blocked_reason=None,
        updated_at=None,
    )
    with pytest.raises(HTTPException) as caught:
        asyncio.run(
            transition_task(
                "t1",
                TransitionRequest(state=TaskState.TESTS_RUNNING),
                db=FakeDb(task),
                _user=SimpleNamespace(email="admin@example.test"),
            )
        )
    assert caught.value.status_code == 409
    assert caught.value.detail == "dual_governor_review_required"
    assert task.state == TaskState.REVIEW_REQUIRED.value


def test_worker_report_cannot_erase_controlled_review_metadata(monkeypatch):
    from app.api.dev_tasks import WorkerReportRequest, record_report

    monkeypatch.setenv("DEV_ORCHESTRATOR", "1")
    report = _report()
    report = record_governor_review(
        report,
        governor="claude",
        decision="approve",
        artifact_hash=ARTIFACT_HASH,
        summary="safe",
        reviewed_by="admin",
        **_auth("claude_report_nonce_001"),
    )
    report["proposal_artifact"] = "data/dev_tasks/t1/proposal.md"
    task = SimpleNamespace(
        worker_report=json.dumps(report),
        test_evidence=None,
        updated_at=None,
        id="t1",
        idempotency_key="idem-review-1",
        parent_objective="review",
        customer_id=None,
        priority=50,
        state=TaskState.REVIEW_REQUIRED.value,
        selected_provider="omniroute",
        selected_model="free-coding-safe",
        fallback_models=None,
        worktree_path=None,
        branch_name=None,
        file_ownership=None,
        dependencies=None,
        acceptance_criteria=None,
        retry_count=0,
        lease_owner=None,
        lease_until=None,
        deployment_evidence=None,
        delivery_evidence=None,
        created_at=None,
        blocked_reason=None,
    )
    body = WorkerReportRequest(summary="worker update", test_result="not-run")
    asyncio.run(record_report("t1", body, db=FakeDb(task), _user=SimpleNamespace()))
    stored = json.loads(task.worker_report)
    assert stored["proposal_sha256"] == ARTIFACT_HASH
    assert stored["governor_reviews"]["claude"]["decision"] == "approve"
    assert stored["proposal_artifact"].endswith("proposal.md")


def test_review_endpoint_records_one_governor_and_changes_state(monkeypatch):
    from app.api.dev_tasks import GovernorReviewRequest, record_governor_review_endpoint

    monkeypatch.setenv("DEV_ORCHESTRATOR", "1")
    monkeypatch.setenv("DEV_CLAUDE_REVIEW_SECRET", CLAUDE_SECRET)
    issued_at = int(time.time())
    nonce = "claude_endpoint_nonce_001"
    signature = build_governor_signature(
        secret=CLAUDE_SECRET,
        task_id="t1",
        governor="claude",
        decision="changes_requested",
        artifact_hash=ARTIFACT_HASH,
        summary="revise boundary",
        issued_at=issued_at,
        nonce=nonce,
    )
    task = _endpoint_task()
    out = asyncio.run(
        record_governor_review_endpoint(
            "t1",
            GovernorReviewRequest(
                governor="claude",
                decision="changes_requested",
                artifact_hash=ARTIFACT_HASH,
                summary="revise boundary",
            ),
            db=FakeDb(task),
            x_governor_timestamp=str(issued_at),
            x_governor_nonce=nonce,
            x_governor_signature=signature,
        )
    )
    assert task.state == TaskState.CHANGES_REQUESTED.value
    assert out["review_gate"]["approved"] is False
    stored = json.loads(task.worker_report)["governor_reviews"]["claude"]
    assert stored["decision"] == "changes_requested"
    assert stored["reviewed_by"] == "governor:claude"
    assert "signature" not in json.dumps(stored).lower()


def test_unsigned_review_cannot_enter_approval_ledger():
    with pytest.raises(ValueError, match="attestation_required"):
        record_governor_review(
            _report(),
            governor="claude",
            decision="approve",
            artifact_hash=ARTIFACT_HASH,
            summary="unsigned",
            reviewed_by="admin",
        )


def test_attestation_nonce_cannot_be_replayed_across_governors():
    report = record_governor_review(
        _report(),
        governor="claude",
        decision="approve",
        artifact_hash=ARTIFACT_HASH,
        summary="signed",
        reviewed_by="admin",
        attestation_version=ATTESTATION_VERSION,
        attestation_nonce="one_unique_nonce_12345",
    )
    with pytest.raises(ValueError, match="attestation_replayed"):
        record_governor_review(
            report,
            governor="chatgpt",
            decision="approve",
            artifact_hash=ARTIFACT_HASH,
            summary="signed",
            reviewed_by="admin",
            attestation_version=ATTESTATION_VERSION,
            attestation_nonce="one_unique_nonce_12345",
        )


def test_review_endpoint_rejects_missing_attestation(monkeypatch):
    from app.api.dev_tasks import GovernorReviewRequest, record_governor_review_endpoint

    monkeypatch.setenv("DEV_ORCHESTRATOR", "1")
    task = SimpleNamespace(
        worker_report=json.dumps(_report()),
        updated_at=None,
        state=TaskState.REVIEW_REQUIRED.value,
    )
    with pytest.raises(HTTPException) as caught:
        asyncio.run(
            record_governor_review_endpoint(
                "t1",
                GovernorReviewRequest(
                    governor="claude",
                    decision="approve",
                    artifact_hash=ARTIFACT_HASH,
                    summary="unsigned",
                ),
                db=FakeDb(task),
            )
        )
    assert caught.value.status_code == 403
    assert caught.value.detail == "governor_attestation_invalid"


def test_old_unattested_review_rows_fail_closed():
    report = _report()
    report["governor_reviews"] = {
        governor: {
            "governor": governor,
            "decision": "approve",
            "artifact_hash": ARTIFACT_HASH,
        }
        for governor in ("claude", "chatgpt")
    }
    status = review_gate_status(report)
    assert status["approved"] is False
    assert {x["decision"] for x in status["blocking_decisions"]} == {
        "attestation_missing_or_invalid"
    }


def test_endpoint_rejects_a_valid_signature_replay(monkeypatch):
    from app.api.dev_tasks import GovernorReviewRequest, record_governor_review_endpoint

    monkeypatch.setenv("DEV_ORCHESTRATOR", "1")
    monkeypatch.setenv("DEV_CLAUDE_REVIEW_SECRET", CLAUDE_SECRET)
    issued_at = int(time.time())
    nonce = "claude_replay_nonce_001"
    body = GovernorReviewRequest(
        governor="claude",
        decision="approve",
        artifact_hash=ARTIFACT_HASH,
        summary="safe",
    )
    signature = build_governor_signature(
        secret=CLAUDE_SECRET,
        task_id="t1",
        governor="claude",
        decision="approve",
        artifact_hash=ARTIFACT_HASH,
        summary="safe",
        issued_at=issued_at,
        nonce=nonce,
    )
    db = FakeDb(_endpoint_task())
    first = asyncio.run(
        record_governor_review_endpoint(
            "t1",
            body,
            db=db,
            x_governor_timestamp=str(issued_at),
            x_governor_nonce=nonce,
            x_governor_signature=signature,
        )
    )
    assert first["review_gate"]["approved"] is False
    with pytest.raises(HTTPException) as caught:
        asyncio.run(
            record_governor_review_endpoint(
                "t1",
                body,
                db=db,
                x_governor_timestamp=str(issued_at),
                x_governor_nonce=nonce,
                x_governor_signature=signature,
            )
        )
    assert caught.value.status_code == 409
    assert caught.value.detail == "governor_attestation_replayed"
