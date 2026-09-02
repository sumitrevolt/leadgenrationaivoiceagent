"""Machine-readable pilot task manifest: validation gate before ANY file change.

A pilot manifest is the only way the bounded repair loop may touch files. It is
parsed + validated here and refused outright when malformed, over-broad or
unsafe (fail-closed). Every rule below is covered by a regression test.

Trust boundaries (see docs/PR_ORCHESTRATION_PILOT.md):
  * manifest = operator-authored, repo-reviewed artefact (no agent authorship)
  * protected prefixes are NEVER overridable — they are auto-merged into the
    denied set and any allowed-path hit is a refusal
  * required_tests / required_lint / required_security may never contain shell
    metacharacters or arbitrary executables
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from app.dev_control.external_agents import policy

#: GREEN / AMBER / RED (same lanes as Owner OS / external_agents.policy).
RISK_CLASSES: tuple[str, ...] = ("GREEN", "AMBER", "RED")

#: Task branches must be safe ref names: no leading '-', no '..', no 'refs/',
#: no whitespace, and never the base branch.
_SAFE_BRANCH_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9/._-]{0,127}$")
_FORBIDDEN_BRANCH_PARTS = ("..", "refs/", "//", "~", "^", ":", "\\")
_HEX40_RE = re.compile(r"^[0-9a-fA-F]{40}$")

#: Shell metacharacters that make a manifest command unsafe to run.
_SHELL_METACHARS = (";", "&&", "||", "`", "$(", "|", ">", "<", "*", "?", "~", "\n", "\r", "\x00")

#: Executables a manifest test/lint/security command may start with.
_TEST_PREFIXES = (
    "pytest",
    "python -m pytest",
    ".venv/bin/pytest",
    ".venv/bin/python -m pytest",
    "python3 -m pytest",
)
_LINT_PREFIXES = ("ruff",)
_SEC_PREFIXES = (
    "python scripts/",
    "python3 scripts/",
    ".venv/bin/python scripts/",
    "python -m pytest scripts/",
)

#: The only external-action permission keys the pilot understands. Anything else
#: is refused. Deployment / secrets scopes are structurally absent.
_ALLOWED_ACTION_PERMISSION_KEYS = frozenset({"pull_requests", "actions", "contents"})
_ALLOWED_ACTION_PERMISSION_VALUES = {
    "pull_requests": frozenset({"write"}),
    "actions": frozenset({"read"}),
    "contents": frozenset({"read", "task_branch_only"}),
}
_FORBIDDEN_ACTION_PERMISSION_KEYS = frozenset(
    {"deployments", "secrets", "packages", "id-token", "security-events"}
)

DEFAULT_EXTERNAL_ACTION_PERMISSIONS: dict[str, str] = {
    "pull_requests": "write",
    "actions": "read",
    "contents": "task_branch_only",
}


class PilotManifestError(ValueError):
    """Manifest is malformed, over-broad, or unsafe — refuse, do not run."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}".rstrip(": "))
        self.code = code
        self.detail = detail


@dataclass
class PilotTask:
    task_id: str
    objective: str
    owner: str
    base_branch: str
    task_branch: str
    worktree_path: str
    allowed_paths: list[str]
    denied_paths: list[str]
    risk_class: str
    required_tests: list[str]
    required_lint: list[str]
    required_security: list[str]
    expected_head_sha: str
    max_repair_attempts: int
    external_action_permissions: dict[str, str]
    owner_approval_id: str
    cleanup_ownership: str
    completion_conditions: list[str]
    ci_mode: str = "repair"
    pr_number: int | None = None

    def all_denied_paths(self) -> list[str]:
        return sorted(set(self.denied_paths) | set(policy.PROTECTED_PATH_PREFIXES))

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "objective": self.objective,
            "owner": self.owner,
            "base_branch": self.base_branch,
            "task_branch": self.task_branch,
            "worktree_path": self.worktree_path,
            "allowed_paths": list(self.allowed_paths),
            "denied_paths": list(self.denied_paths),
            "risk_class": self.risk_class,
            "required_tests": list(self.required_tests),
            "required_lint": list(self.required_lint),
            "required_security": list(self.required_security),
            "expected_head_sha": self.expected_head_sha,
            "max_repair_attempts": int(self.max_repair_attempts),
            "external_action_permissions": dict(self.external_action_permissions),
            "owner_approval_id": self.owner_approval_id,
            "cleanup_ownership": self.cleanup_ownership,
            "completion_conditions": list(self.completion_conditions),
            "ci_mode": self.ci_mode,
            "pr_number": self.pr_number,
        }


def _as_str(value: Any, code: str) -> str:
    if value is None:
        raise PilotManifestError(code, "field missing")
    s = str(value).strip()
    if not s:
        raise PilotManifestError(code, "field empty")
    return s


def _as_str_list(value: Any, code: str) -> list[str]:
    if value is None:
        raise PilotManifestError(code, "field missing")
    if not isinstance(value, list) or not value:
        raise PilotManifestError(code, "must be a non-empty list")
    out: list[str] = []
    for item in value:
        s = str(item or "").strip()
        if not s:
            raise PilotManifestError(code, "contains an empty entry")
        if any(m in s for m in _SHELL_METACHARS):
            raise PilotManifestError("unsafe_command", repr(s))
        out.append(s)
    return out


def _check_command_prefixes(commands: list[str], prefixes: tuple[str, ...], code: str) -> None:
    for cmd in commands:
        if any(m in cmd for m in _SHELL_METACHARS):
            raise PilotManifestError("unsafe_command", repr(cmd))
        if not any(cmd.startswith(p) for p in prefixes):
            raise PilotManifestError(code, repr(cmd))


def _check_branch(name: str, code: str) -> None:
    if not _SAFE_BRANCH_RE.match(name):
        raise PilotManifestError(code, f"unsafe branch name {name!r}")
    for part in _FORBIDDEN_BRANCH_PARTS:
        if part in name:
            raise PilotManifestError(code, f"unsafe branch name {name!r}")


def _protected_hits(paths: list[str]) -> list[str]:
    hits: list[str] = []
    for raw in paths:
        canon = policy.canonical_path(raw)
        if not canon:
            hits.append(str(raw).strip() or "(empty)")
            continue
        for prefix in policy.PROTECTED_PATH_PREFIXES:
            p = prefix.lower()
            if canon == p or canon.startswith(p):
                hits.append(canon)
                break
    return sorted(set(hits))


def validate_manifest(raw: dict[str, Any]) -> PilotTask:
    if not isinstance(raw, dict):
        raise PilotManifestError("not_a_mapping")

    task_id = _as_str(raw.get("task_id"), "task_id_missing")
    if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$", task_id):
        raise PilotManifestError("task_id_invalid", repr(task_id))

    objective = _as_str(raw.get("objective"), "objective_missing")
    owner = _as_str(raw.get("owner"), "owner_missing")

    base_branch = _as_str(raw.get("base_branch"), "base_branch_missing")
    if base_branch != "main":
        raise PilotManifestError("base_branch_not_main", base_branch)
    _check_branch(base_branch, "base_branch_invalid")

    task_branch = _as_str(raw.get("task_branch"), "task_branch_missing")
    _check_branch(task_branch, "task_branch_invalid")
    if task_branch == base_branch:
        raise PilotManifestError("direct_main_refused")
    if task_branch.lower() == "main":
        raise PilotManifestError("direct_main_refused")

    worktree_path = _as_str(raw.get("worktree_path"), "worktree_path_missing")

    allowed = _as_str_list(raw.get("allowed_paths"), "allowed_paths_invalid")
    denied = (
        _as_str_list(raw.get("denied_paths"), "denied_paths_invalid")
        if raw.get("denied_paths")
        else []
    )

    overlap = _paths_overlap(allowed, denied)
    if overlap:
        raise PilotManifestError(f"path_overlap:{','.join(overlap)}")

    protected_hits = _protected_hits(allowed)
    if protected_hits:
        raise PilotManifestError(f"protected_paths:{','.join(protected_hits)}")

    risk = str(raw.get("risk_class") or "GREEN").strip().upper()
    if risk not in RISK_CLASSES:
        raise PilotManifestError("risk_class_invalid", risk)
    if risk == "RED":
        raise PilotManifestError("red_risk_refused")

    required_tests = _as_str_list(raw.get("required_tests"), "required_tests_invalid")
    _check_command_prefixes(required_tests, _TEST_PREFIXES, "required_tests_unsafe")
    required_lint = (
        _as_str_list(raw.get("required_lint"), "required_lint_invalid")
        if raw.get("required_lint")
        else []
    )
    _check_command_prefixes(required_lint, _LINT_PREFIXES, "required_lint_unsafe")
    required_security = (
        _as_str_list(raw.get("required_security"), "required_security_invalid")
        if raw.get("required_security")
        else []
    )
    _check_command_prefixes(required_security, _SEC_PREFIXES, "required_security_unsafe")

    expected_sha = str(raw.get("expected_head_sha") or "").strip()
    if expected_sha not in {"", "PENDING"} and not _HEX40_RE.match(expected_sha):
        raise PilotManifestError("expected_head_sha_invalid", expected_sha)

    max_attempts = raw.get("max_repair_attempts", 2)
    try:
        max_attempts = int(max_attempts)
    except (TypeError, ValueError) as exc:
        raise PilotManifestError("max_repair_attempts_invalid", str(max_attempts)) from exc
    if not 1 <= max_attempts <= 2:
        raise PilotManifestError("max_repair_attempts_out_of_range", str(max_attempts))

    perms = raw.get("external_action_permissions")
    if perms is None:
        perms = DEFAULT_EXTERNAL_ACTION_PERMISSIONS
    if not isinstance(perms, dict):
        raise PilotManifestError("external_action_permissions_invalid")
    unknown_keys = set(perms) - _ALLOWED_ACTION_PERMISSION_KEYS
    if unknown_keys or set(perms) & _FORBIDDEN_ACTION_PERMISSION_KEYS:
        raise PilotManifestError(
            "external_action_permissions_unsafe",
            ",".join(
                sorted(set(perms) & _FORBIDDEN_ACTION_PERMISSION_KEYS) or sorted(unknown_keys)
            ),
        )
    for key, value in perms.items():
        allowed_values = _ALLOWED_ACTION_PERMISSION_VALUES.get(key)
        if allowed_values is None or str(value) not in allowed_values:
            raise PilotManifestError("external_action_permissions_unsafe", f"{key}={value}")

    owner_approval_id = str(raw.get("owner_approval_id") or "").strip()
    if risk == "AMBER" and not owner_approval_id:
        raise PilotManifestError("owner_approval_id_required")

    cleanup = str(raw.get("cleanup_ownership") or "").strip()
    if cleanup != "task_owned":
        raise PilotManifestError("cleanup_ownership_not_task_owned")

    completion = _as_str_list(raw.get("completion_conditions"), "completion_conditions_invalid")

    ci_mode = str(raw.get("ci_mode") or "repair").strip().lower()
    if ci_mode not in {"repair", "diagnose_only"}:
        raise PilotManifestError("ci_mode_invalid", ci_mode)

    pr_number = raw.get("pr_number")
    if pr_number is not None:
        try:
            pr_number = int(pr_number)
        except (TypeError, ValueError) as exc:
            raise PilotManifestError("pr_number_invalid", str(pr_number)) from exc

    return PilotTask(
        task_id=task_id,
        objective=objective,
        owner=owner,
        base_branch=base_branch,
        task_branch=task_branch,
        worktree_path=worktree_path,
        allowed_paths=allowed,
        denied_paths=denied,
        risk_class=risk,
        required_tests=required_tests,
        required_lint=required_lint,
        required_security=required_security,
        expected_head_sha=expected_sha,
        max_repair_attempts=max_attempts,
        external_action_permissions=dict(perms),
        owner_approval_id=owner_approval_id,
        cleanup_ownership=cleanup,
        completion_conditions=completion,
        ci_mode=ci_mode,
        pr_number=pr_number,
    )


def _paths_overlap(a: list[str], b: list[str]) -> list[str]:
    left = sorted({policy.canonical_path(p) for p in a if policy.canonical_path(p)})
    right = sorted({policy.canonical_path(p) for p in b if policy.canonical_path(p)})
    hits: set[str] = set()
    for l in left:
        for r in right:
            if l == r or l.startswith(r.rstrip("/") + "/") or r.startswith(l.rstrip("/") + "/"):
                hits.add(l)
                hits.add(r)
    return sorted(hits)


def parse_manifest(text: str) -> PilotTask:
    """Parse JSON text into a validated PilotTask. JSON-only (no YAML magic)."""
    if not (text or "").strip():
        raise PilotManifestError("empty_document")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PilotManifestError("malformed_json", str(exc)) from exc
    return validate_manifest(data)


def load_manifest(path: str) -> PilotTask:
    from pathlib import Path

    p = Path(path)
    if not p.is_file():
        raise PilotManifestError("manifest_not_found", str(p))
    text = p.read_text(encoding="utf-8-sig")  # BOM-tolerant (Windows editors/pipelines)
    return parse_manifest(text)


def manifest_is_safe_to_run(task: PilotTask) -> bool:
    """Semantic convenience: refuse anything that is not a GREEN, pinned repair."""
    if task.risk_class != "GREEN":
        return False
    if task.expected_head_sha == "PENDING" or not task.expected_head_sha:
        return False
    return True
