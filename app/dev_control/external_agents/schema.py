"""Canonical mission schema + validated lifecycle for external agent missions.

Pure module: no I/O, no framework imports, no env reads. Persistence lives in
``store.py``; authority/risk rules live in ``policy.py``.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

MISSION_SCHEMA_VERSION = "external-agent-mission-v1"

_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._:-]{2,79}$")


class MissionState(str, Enum):
    CREATED = "CREATED"
    PREFLIGHT = "PREFLIGHT"
    CLAIMED = "CLAIMED"
    RUNNING = "RUNNING"
    IMPLEMENTED = "IMPLEMENTED"
    TESTING = "TESTING"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    REVIEW_PASSED = "REVIEW_PASSED"
    PR_OPEN = "PR_OPEN"
    CI_RUNNING = "CI_RUNNING"
    MERGE_QUEUED = "MERGE_QUEUED"
    MERGED = "MERGED"
    DEPLOYMENT_PENDING = "DEPLOYMENT_PENDING"
    CANARY_RUNNING = "CANARY_RUNNING"
    VERIFIED = "VERIFIED"
    COMPLETE = "COMPLETE"
    # failure / hold states
    BLOCKED = "BLOCKED"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_TERMINAL = "FAILED_TERMINAL"
    CANCELLED = "CANCELLED"
    ROLLED_BACK = "ROLLED_BACK"
    OWNER_DECISION_REQUIRED = "OWNER_DECISION_REQUIRED"


class RiskClass(str, Enum):
    GREEN = "GREEN"
    AMBER = "AMBER"
    RED = "RED"


class MissionValidationError(ValueError):
    """Mission payload violates the canonical schema."""


class InvalidMissionTransition(ValueError):
    """Attempted lifecycle transition is not allowed."""


FAILURE_STATES: frozenset[MissionState] = frozenset(
    {
        MissionState.BLOCKED,
        MissionState.FAILED_RETRYABLE,
        MissionState.FAILED_TERMINAL,
        MissionState.CANCELLED,
        MissionState.ROLLED_BACK,
        MissionState.OWNER_DECISION_REQUIRED,
    }
)

TERMINAL_STATES: frozenset[MissionState] = frozenset(
    {
        MissionState.COMPLETE,
        MissionState.FAILED_TERMINAL,
        MissionState.CANCELLED,
        MissionState.ROLLED_BACK,
    }
)

# Every non-terminal state may go BLOCKED / CANCELLED / OWNER_DECISION_REQUIRED;
# those common edges are injected below so the table stays readable.
_COMMON_EXITS: frozenset[MissionState] = frozenset(
    {
        MissionState.BLOCKED,
        MissionState.CANCELLED,
        MissionState.OWNER_DECISION_REQUIRED,
        MissionState.FAILED_RETRYABLE,
        MissionState.FAILED_TERMINAL,
    }
)

_BASE_TRANSITIONS: dict[MissionState, set[MissionState]] = {
    MissionState.CREATED: {MissionState.PREFLIGHT},
    MissionState.PREFLIGHT: {MissionState.CLAIMED},
    MissionState.CLAIMED: {MissionState.RUNNING},
    MissionState.RUNNING: {MissionState.IMPLEMENTED},
    MissionState.IMPLEMENTED: {MissionState.TESTING},
    MissionState.TESTING: {MissionState.REVIEW_REQUIRED},
    MissionState.REVIEW_REQUIRED: {
        MissionState.REVIEW_PASSED,
        MissionState.CHANGES_REQUESTED,
    },
    MissionState.CHANGES_REQUESTED: {MissionState.PREFLIGHT, MissionState.RUNNING},
    MissionState.REVIEW_PASSED: {MissionState.PR_OPEN},
    MissionState.PR_OPEN: {MissionState.CI_RUNNING},
    MissionState.CI_RUNNING: {
        MissionState.MERGE_QUEUED,
        MissionState.CHANGES_REQUESTED,
    },
    MissionState.MERGE_QUEUED: {MissionState.MERGED},
    MissionState.MERGED: {MissionState.DEPLOYMENT_PENDING, MissionState.VERIFIED},
    MissionState.DEPLOYMENT_PENDING: {MissionState.CANARY_RUNNING, MissionState.VERIFIED},
    MissionState.CANARY_RUNNING: {MissionState.VERIFIED, MissionState.ROLLED_BACK},
    MissionState.VERIFIED: {MissionState.COMPLETE},
    MissionState.COMPLETE: set(),
    # failure / hold states
    MissionState.BLOCKED: {MissionState.PREFLIGHT},
    MissionState.FAILED_RETRYABLE: {MissionState.PREFLIGHT},
    MissionState.FAILED_TERMINAL: set(),
    MissionState.CANCELLED: set(),
    MissionState.ROLLED_BACK: set(),
    MissionState.OWNER_DECISION_REQUIRED: {
        MissionState.PR_OPEN,
        MissionState.DEPLOYMENT_PENDING,
        MissionState.MERGE_QUEUED,
    },
}


def _build_transitions() -> dict[MissionState, frozenset[MissionState]]:
    out: dict[MissionState, frozenset[MissionState]] = {}
    for state, targets in _BASE_TRANSITIONS.items():
        if state in TERMINAL_STATES:
            out[state] = frozenset(targets)
            continue
        out[state] = frozenset(set(targets) | set(_COMMON_EXITS) - {state})
    return out


VALID_TRANSITIONS: dict[MissionState, frozenset[MissionState]] = _build_transitions()

# States an executor agent may drive on its own. Everything else needs the
# orchestrator (review separation, approvals, merge/deploy verification).
EXECUTOR_DRIVEN_STATES: frozenset[MissionState] = frozenset(
    {
        MissionState.RUNNING,
        MissionState.IMPLEMENTED,
        MissionState.TESTING,
        MissionState.REVIEW_REQUIRED,
        MissionState.BLOCKED,
        MissionState.FAILED_RETRYABLE,
    }
)


def _norm_paths(values: Any) -> list[str]:
    if not values:
        return []
    if isinstance(values, str):
        values = [values]
    # Local import keeps schema free of a policy circular dependency at import time.
    from app.dev_control.external_agents.policy import normalize_repo_path

    out: list[str] = []
    for raw in values:
        p = normalize_repo_path(raw)
        if p and p not in out:
            out.append(p)
    return out


def _utc() -> datetime:
    return datetime.utcnow()


@dataclass
class Mission:
    """One bounded unit of external-agent work (Cursor or Claude)."""

    mission_id: str
    title: str
    executor: str
    reviewer: str
    risk_class: RiskClass
    idempotency_key: str
    parent_goal_id: str = ""
    description: str = ""
    status: MissionState = MissionState.CREATED
    priority: int = 50
    allowed_paths: list[str] = field(default_factory=list)
    prohibited_paths: list[str] = field(default_factory=list)
    branch: str = ""
    worktree: str = ""
    base_sha: str = ""
    expected_outputs: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)
    required_tests: list[str] = field(default_factory=list)
    required_checks: list[str] = field(default_factory=list)
    max_runtime_s: int = 3600
    token_budget: int = 1_000_000
    cost_budget_usd: float = 0.0
    retry_policy: dict[str, Any] = field(
        default_factory=lambda: {"max_retries": 2, "backoff_s": 60}
    )
    retry_count: int = 0
    lease_owner: str = ""
    lease_expiry: str = ""
    last_heartbeat: str = ""
    approval_state: str = "not_required"
    rollback_plan: str = ""
    evidence_refs: list[dict[str, Any]] = field(default_factory=list)
    blocker: str = ""
    schema_version: str = MISSION_SCHEMA_VERSION
    created_at: str = ""
    updated_at: str = ""

    # ---------------- construction / validation ----------------

    @staticmethod
    def new_id() -> str:
        return "msn_" + uuid.uuid4().hex[:16]

    @classmethod
    def create(cls, **kwargs: Any) -> Mission:
        data = dict(kwargs)
        data.setdefault("mission_id", cls.new_id())
        now = _utc().isoformat()
        data.setdefault("created_at", now)
        data.setdefault("updated_at", now)
        risk = data.get("risk_class", RiskClass.GREEN)
        data["risk_class"] = RiskClass(risk) if not isinstance(risk, RiskClass) else risk
        status = data.get("status", MissionState.CREATED)
        data["status"] = MissionState(status) if not isinstance(status, MissionState) else status
        data["allowed_paths"] = _norm_paths(data.get("allowed_paths"))
        data["prohibited_paths"] = _norm_paths(data.get("prohibited_paths"))
        mission = cls(**data)
        mission.validate()
        return mission

    def validate(self) -> None:
        if not _ID_RE.match(self.mission_id or ""):
            raise MissionValidationError("mission_id must be 3-80 safe chars")
        if not (self.title or "").strip():
            raise MissionValidationError("title is required")
        if len((self.idempotency_key or "").strip()) < 8:
            raise MissionValidationError("idempotency_key must be >= 8 chars")
        if not (self.executor or "").strip():
            raise MissionValidationError("executor is required")
        if not (self.reviewer or "").strip():
            raise MissionValidationError("reviewer is required")
        if self.executor.strip().lower() == self.reviewer.strip().lower():
            raise MissionValidationError("reviewer must differ from executor (review separation)")
        if not isinstance(self.risk_class, RiskClass):
            raise MissionValidationError("risk_class must be a RiskClass")
        if not 1 <= int(self.priority) <= 100:
            raise MissionValidationError("priority must be 1..100")
        if int(self.max_runtime_s) <= 0 or int(self.max_runtime_s) > 24 * 3600:
            raise MissionValidationError("max_runtime_s must be 1..86400")
        if int(self.token_budget) <= 0:
            raise MissionValidationError("token_budget must be > 0")
        if float(self.cost_budget_usd) < 0:
            raise MissionValidationError("cost_budget_usd cannot be negative")
        overlap = sorted(set(self.allowed_paths) & set(self.prohibited_paths))
        if overlap:
            raise MissionValidationError(f"path declared allowed and prohibited: {overlap}")
        if int(self.retry_policy.get("max_retries", 0)) < 0:
            raise MissionValidationError("retry_policy.max_retries cannot be negative")

    # ---------------- lifecycle ----------------

    def can_transition(self, target: MissionState) -> bool:
        return target in VALID_TRANSITIONS.get(self.status, frozenset())

    def transition(self, target: MissionState, *, actor_role: str = "orchestrator") -> Mission:
        if not isinstance(target, MissionState):
            target = MissionState(target)
        if not self.can_transition(target):
            raise InvalidMissionTransition(f"{self.status.value} -> {target.value} is not allowed")
        if actor_role == "executor" and target not in EXECUTOR_DRIVEN_STATES:
            raise InvalidMissionTransition(
                f"executor may not drive {target.value} (orchestrator/reviewer only)"
            )
        self.status = target
        self.updated_at = _utc().isoformat()
        return self

    # ---------------- leases ----------------

    def lease_active(self, now: datetime | None = None) -> bool:
        if not self.lease_owner or not self.lease_expiry:
            return False
        try:
            expiry = datetime.fromisoformat(self.lease_expiry)
        except ValueError:
            return False
        return expiry > (now or _utc())

    def set_lease(self, owner: str, ttl_s: int, now: datetime | None = None) -> None:
        base = now or _utc()
        self.lease_owner = owner
        self.lease_expiry = (base + timedelta(seconds=max(1, int(ttl_s)))).isoformat()
        self.last_heartbeat = base.isoformat()
        self.updated_at = base.isoformat()

    def clear_lease(self) -> None:
        self.lease_owner = ""
        self.lease_expiry = ""
        self.updated_at = _utc().isoformat()

    # ---------------- evidence ----------------

    def add_evidence(self, kind: str, ref: Any, *, note: str = "") -> dict[str, Any]:
        entry = {
            "kind": str(kind)[:60],
            "ref": ref,
            "note": str(note)[:500],
            "at": _utc().isoformat(),
        }
        self.evidence_refs.append(entry)
        self.updated_at = entry["at"]
        return entry

    def evidence_kinds(self) -> set[str]:
        return {str(e.get("kind")) for e in self.evidence_refs}

    # ---------------- serialisation ----------------

    def to_dict(self) -> dict[str, Any]:
        out = dict(self.__dict__)
        out["risk_class"] = self.risk_class.value
        out["status"] = self.status.value
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Mission:
        payload = dict(data)
        payload["risk_class"] = RiskClass(payload.get("risk_class", "GREEN"))
        payload["status"] = MissionState(payload.get("status", "CREATED"))
        known = set(cls.__dataclass_fields__)  # dataclass API
        return cls(**{k: v for k, v in payload.items() if k in known})
