"""PR Factory task schema — required fields, path overlap, executor≠reviewer."""

from __future__ import annotations

import pytest

from tools.pr_factory.task_schema import TaskValidationError, validate_task


def _base(**over):
    payload = {
        "title": "add unit test for helper",
        "executor": "cursor",
        "reviewer": "claude",
        "idempotency_key": "prf-key-0001",
        "allowed_paths": ["tests/test_helper.py"],
        "acceptance_criteria": ["helper covered by pytest"],
        "required_tests": ["pytest tests/test_helper.py -q"],
        "rollback_plan": "git revert the squash merge commit",
    }
    payload.update(over)
    return payload


def test_valid_task_ok():
    task = validate_task(_base())
    assert task.executor == "cursor"
    assert task.reviewer == "claude"
    kwargs = task.to_create_kwargs()
    assert kwargs["allowed_paths"] == ["tests/test_helper.py"]
    assert "issue_id" not in kwargs
    assert task.extras()["issue_id"] == ""


def test_missing_required_refused():
    with pytest.raises(TaskValidationError, match="missing_required"):
        validate_task({"title": "x"})


def test_executor_equals_reviewer_refused():
    with pytest.raises(TaskValidationError, match="executor_equals_reviewer"):
        validate_task(_base(executor="claude", reviewer="claude"))


def test_path_overlap_refused():
    with pytest.raises(TaskValidationError, match="path_overlap"):
        validate_task(
            _base(
                allowed_paths=["app/platform/foo.py"],
                prohibited_paths=["app/platform/foo.py"],
            )
        )


def test_protected_paths_refused():
    with pytest.raises(TaskValidationError, match="protected_paths"):
        validate_task(_base(allowed_paths=["app/billing/packages.py"]))


def test_empty_acceptance_refused():
    with pytest.raises(TaskValidationError, match="acceptance_criteria"):
        validate_task(_base(acceptance_criteria=[]))


def test_flag_default_name():
    from tools.pr_factory import FLAG

    assert FLAG == "PR_FACTORY_ENABLED"
