"""Guard contract: head-SHA pinning, attempt caps, classification, fresh CI."""

from __future__ import annotations

import pytest

from tools.pr_factory.pilot import MAX_REPAIR_ATTEMPTS, guard
from tools.pr_factory.pilot.guard import (
    GuardRefusal,
    PilotStateUnverifiable,
    RepairLedger,
    check_expected_head_sha,
    classify_failure,
    fresh_ci_evidence,
    is_transient_retryable,
    protected_path_hits,
    require_fresh_ci,
    stale_ci_authorizes,
    validate_sha,
)

SHA_A = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
SHA_B = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


def test_head_sha_mismatch_refused():
    with pytest.raises(GuardRefusal, match="head_sha_mismatch"):
        check_expected_head_sha(SHA_A, SHA_B)


def test_head_sha_missing_pin_refused():
    with pytest.raises(GuardRefusal, match="head_sha_pin_missing"):
        check_expected_head_sha("PENDING", SHA_A)
    with pytest.raises(GuardRefusal, match="head_sha_pin_missing"):
        check_expected_head_sha("", SHA_A)


def test_head_sha_match_ok_case_insensitive():
    check_expected_head_sha(SHA_A, SHA_A.upper())


def test_unverifiable_remote_head_refused():
    with pytest.raises(PilotStateUnverifiable, match="github_state_unverifiable"):
        check_expected_head_sha(SHA_A, "zzz")


def test_validate_sha():
    assert validate_sha(SHA_A)
    assert not validate_sha("abc")


def test_protected_path_hits_fail_closed():
    hits = protected_path_hits(["app/billing/packages.py", "tests/ok.py", ".env"])
    assert "app/billing/packages.py" in hits
    assert ".env" in hits
    assert "tests/ok.py" not in hits
    # an unparseable path (absolute) is itself a hit — never silently ignored
    assert protected_path_hits(["C:/Windows/evil.py"]) != []


def test_repair_attempt_cap_enforced(tmp_path):
    ledger = RepairLedger(state_dir=tmp_path / "state")
    assert ledger.can_repair(1, SHA_A, cap=2)
    ledger.record_attempt(1, SHA_A, "pushed")
    ledger.record_attempt(1, SHA_A, "pushed")
    assert not ledger.can_repair(1, SHA_A, cap=2)
    assert ledger.remaining(1, SHA_A, cap=2) == 0
    with pytest.raises(GuardRefusal, match="attempt_cap_exceeded"):
        ledger.record_attempt(1, SHA_A, "pushed")


def test_repair_cap_is_per_head_sha(tmp_path):
    ledger = RepairLedger(state_dir=tmp_path / "state")
    ledger.record_attempt(1, SHA_A, "pushed")
    # A NEW head SHA on the same PR gets a fresh budget (but still capped).
    assert ledger.can_repair(1, SHA_B, cap=2)


def test_default_cap_is_two(tmp_path):
    ledger = RepairLedger(state_dir=tmp_path / "state")
    assert MAX_REPAIR_ATTEMPTS == 2
    ledger.record_attempt(1, SHA_A, "pushed")
    ledger.record_attempt(1, SHA_A, "pushed")
    assert not ledger.can_repair(1, SHA_A)


def test_classify_failure_buckets():
    assert classify_failure("ModuleNotFoundError: nope") == "code"
    assert classify_failure("pytest failed: assert 1 == 2") == "code"
    assert classify_failure("Traceback (most recent call last)") == "code"
    assert classify_failure("Docker Hub unreachable: Client.Timeout") == "infra"
    assert classify_failure("no space left on device") == "infra"
    assert classify_failure("still running, no output yet") == "unknown"


def test_transient_retryable_only_for_infra_failures():
    assert is_transient_retryable(
        {"status": "completed", "conclusion": "failure", "log": "Docker Hub unreachable"}
    )
    assert not is_transient_retryable(
        {"status": "completed", "conclusion": "failure", "log": "ModuleNotFoundError"}
    )
    assert not is_transient_retryable(
        {"status": "completed", "conclusion": "action_required", "log": ""}
    )
    assert not is_transient_retryable({"status": "completed", "conclusion": "success", "log": ""})
    assert not is_transient_retryable({"status": "in_progress", "conclusion": None, "log": ""})


def test_stale_ci_cannot_authorize_completion():
    old_runs = [
        {
            "head_sha": SHA_A,
            "name": "Lint + syntax + secrets",
            "status": "completed",
            "conclusion": "success",
        }
    ]
    assert not stale_ci_authorizes(old_runs, SHA_B)
    assert fresh_ci_evidence(old_runs, SHA_B) is None


def test_fresh_ci_required_on_exact_head():
    runs = [{"head_sha": SHA_B, "status": "completed", "conclusion": "success"}]
    require_fresh_ci(runs, SHA_B)
    with pytest.raises(GuardRefusal, match="fresh_ci_required"):
        require_fresh_ci(runs, SHA_A)


def test_fail_closed_state():
    refusal = guard.GuardRefusal("x", "y", "z")
    assert refusal.to_dict()["refused"] is True
    assert refusal.to_dict()["code"] == "x"


def test_audit_receipt_shape():
    receipt = guard.build_audit_receipt(
        pr_number=7,
        head_sha=SHA_A,
        mode="repair",
        verdict="ci_running",
        attempts=1,
        evidence={"x": 1},
    )
    assert receipt["schema"] == "leadgen.pr-pilot.receipt.v1"
    assert receipt["max_repair_attempts"] == 2
    assert receipt["attempts_used"] == 1
