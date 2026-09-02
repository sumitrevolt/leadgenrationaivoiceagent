"""Validate PR Factory task YAML before bridging to create_mission."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.dev_control.external_agents import policy

REQUIRED_FIELDS: tuple[str, ...] = (
    "title",
    "executor",
    "reviewer",
    "idempotency_key",
    "allowed_paths",
    "acceptance_criteria",
    "required_tests",
    "rollback_plan",
)

OPTIONAL_FIELDS: tuple[str, ...] = (
    "description",
    "declared_risk",
    "prohibited_paths",
    "branch",
    "worktree",
    "base_sha",
    "required_checks",
    "parent_goal_id",
    "priority",
    "token_budget",
    "dependencies",
    "blast_radius_tests",
    "evidence_required",
    "issue_id",
)


class TaskValidationError(ValueError):
    """Task YAML fails PR Factory schema / constitution gates."""


@dataclass
class FactoryTask:
    title: str
    executor: str
    reviewer: str
    idempotency_key: str
    allowed_paths: list[str]
    acceptance_criteria: list[str]
    required_tests: list[str]
    rollback_plan: str
    description: str = ""
    declared_risk: str | None = None
    prohibited_paths: list[str] = field(default_factory=list)
    branch: str = ""
    worktree: str = ""
    base_sha: str = ""
    required_checks: list[str] = field(default_factory=list)
    parent_goal_id: str = ""
    priority: int = 50
    token_budget: int | None = None
    dependencies: list[str] = field(default_factory=list)
    blast_radius_tests: list[str] = field(default_factory=list)
    evidence_required: list[str] = field(default_factory=list)
    issue_id: str = ""

    def to_create_kwargs(self) -> dict[str, Any]:
        """Map 1:1 onto ``create_mission`` kwargs (+ extras stay out of mission)."""
        kwargs: dict[str, Any] = {
            "title": self.title,
            "executor": self.executor,
            "reviewer": self.reviewer,
            "idempotency_key": self.idempotency_key,
            "description": self.description,
            "allowed_paths": list(self.allowed_paths),
            "prohibited_paths": list(self.prohibited_paths),
            "branch": self.branch,
            "worktree": self.worktree,
            "base_sha": self.base_sha,
            "acceptance_criteria": list(self.acceptance_criteria),
            "required_tests": list(self.required_tests),
            "required_checks": list(self.required_checks),
            "rollback_plan": self.rollback_plan,
            "parent_goal_id": self.parent_goal_id,
            "priority": int(self.priority),
        }
        if self.declared_risk:
            kwargs["declared_risk"] = self.declared_risk
        if self.token_budget is not None:
            kwargs["token_budget"] = int(self.token_budget)
        return kwargs

    def extras(self) -> dict[str, Any]:
        return {
            "dependencies": list(self.dependencies),
            "blast_radius_tests": list(self.blast_radius_tests),
            "evidence_required": list(self.evidence_required),
            "issue_id": self.issue_id,
        }


def _as_str_list(value: Any, field_name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise TaskValidationError(f"{field_name}_must_be_list")
    out: list[str] = []
    for item in value:
        s = str(item or "").strip()
        if s:
            out.append(s)
    return out


def _paths_overlap(a: list[str], b: list[str]) -> list[str]:
    """Return canonical paths that appear in both allow and prohibit lists."""
    left = {policy.canonical_path(p) for p in a if policy.canonical_path(p)}
    right = {policy.canonical_path(p) for p in b if policy.canonical_path(p)}
    return sorted(left & right)


def _touches_protected(paths: list[str]) -> list[str]:
    hits: list[str] = []
    for raw in paths:
        canon = policy.canonical_path(raw)
        if not canon:
            continue
        for prefix in policy.PROTECTED_PATH_PREFIXES:
            p = prefix.lower()
            if canon == p or canon.startswith(p):
                hits.append(canon)
                break
    return hits


def validate_task(raw: dict[str, Any]) -> FactoryTask:
    """Validate mandatory YAML fields + constitution gates."""
    if not isinstance(raw, dict):
        raise TaskValidationError("task_must_be_mapping")

    missing = [k for k in REQUIRED_FIELDS if k not in raw or raw[k] in (None, "", [])]
    if missing:
        raise TaskValidationError(f"missing_required:{','.join(missing)}")

    title = str(raw["title"]).strip()
    executor = str(raw["executor"]).strip().lower()
    reviewer = str(raw["reviewer"]).strip().lower()
    if not title:
        raise TaskValidationError("title_empty")
    if executor == reviewer:
        raise TaskValidationError("executor_equals_reviewer")

    allowed = _as_str_list(raw.get("allowed_paths"), "allowed_paths")
    if not allowed:
        raise TaskValidationError("allowed_paths_empty")

    prohibited = _as_str_list(raw.get("prohibited_paths"), "prohibited_paths")
    overlap = _paths_overlap(allowed, prohibited)
    if overlap:
        raise TaskValidationError(f"path_overlap:{','.join(overlap)}")

    protected_hits = _touches_protected(allowed)
    if protected_hits:
        raise TaskValidationError(f"protected_paths:{','.join(protected_hits)}")

    acceptance = _as_str_list(raw.get("acceptance_criteria"), "acceptance_criteria")
    required_tests = _as_str_list(raw.get("required_tests"), "required_tests")
    if not acceptance:
        raise TaskValidationError("acceptance_criteria_empty")
    if not required_tests:
        raise TaskValidationError("required_tests_empty")

    rollback = str(raw.get("rollback_plan") or "").strip()
    if not rollback:
        raise TaskValidationError("rollback_plan_empty")

    token_budget = raw.get("token_budget")
    if token_budget is not None:
        try:
            token_budget = int(token_budget)
        except (TypeError, ValueError) as exc:
            raise TaskValidationError("token_budget_invalid") from exc

    priority = raw.get("priority", 50)
    try:
        priority = int(priority)
    except (TypeError, ValueError) as exc:
        raise TaskValidationError("priority_invalid") from exc

    declared = raw.get("declared_risk")
    declared_risk = str(declared).strip().upper() if declared else None
    if declared_risk and declared_risk not in {"GREEN", "AMBER", "RED"}:
        raise TaskValidationError("declared_risk_invalid")

    return FactoryTask(
        title=title,
        executor=executor,
        reviewer=reviewer,
        idempotency_key=str(raw["idempotency_key"]).strip(),
        allowed_paths=allowed,
        acceptance_criteria=acceptance,
        required_tests=required_tests,
        rollback_plan=rollback,
        description=str(raw.get("description") or "").strip(),
        declared_risk=declared_risk,
        prohibited_paths=prohibited,
        branch=str(raw.get("branch") or "").strip(),
        worktree=str(raw.get("worktree") or "").strip(),
        base_sha=str(raw.get("base_sha") or "").strip(),
        required_checks=_as_str_list(raw.get("required_checks"), "required_checks"),
        parent_goal_id=str(raw.get("parent_goal_id") or "").strip(),
        priority=priority,
        token_budget=token_budget,
        dependencies=_as_str_list(raw.get("dependencies"), "dependencies"),
        blast_radius_tests=_as_str_list(raw.get("blast_radius_tests"), "blast_radius_tests"),
        evidence_required=_as_str_list(raw.get("evidence_required"), "evidence_required"),
        issue_id=str(raw.get("issue_id") or "").strip(),
    )


def load_task_yaml(text: str) -> FactoryTask:
    """Parse YAML/JSON text into a validated FactoryTask."""
    import json

    text = (text or "").strip()
    if not text:
        raise TaskValidationError("empty_document")
    data: Any
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text)
    except Exception:
        data = json.loads(text)
    if not isinstance(data, dict):
        raise TaskValidationError("document_must_be_mapping")
    return validate_task(data)
