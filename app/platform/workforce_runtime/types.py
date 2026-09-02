"""Runtime-neutral workforce request/result contracts."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class WorkforceRequest:
    agent_id: str
    action: str
    payload: dict[str, Any] = field(default_factory=dict)
    tenant_id: str = ""
    approval_ref: str = ""
    idempotency_key: str = ""
    trigger: str = "on_demand"
    timeout_s: float | None = None
    run_id: str = field(default_factory=lambda: "wfr_" + uuid.uuid4().hex[:16])
    created_at: str = field(default_factory=now_iso)


@dataclass
class WorkforceResult:
    run_id: str
    agent_id: str
    action: str
    status: str
    provider: str
    reason: str = ""
    output: dict[str, Any] | None = None
    error_class: str = ""
    error_message: str = ""
    attempts: int = 0
    duration_ms: int = 0
    mode: str = ""
    lane: str = ""
    escalation: str = ""
    dlq: bool = False
    lifecycle: list[str] = field(default_factory=list)
    usage: dict[str, float] = field(default_factory=dict)
    shadow_run_id: str = ""
    queue: str = ""
    heartbeat_at: str = ""
    runtime_version: str = ""
    rollout_wave: str = ""
    decision: dict[str, Any] | None = None
    at: str = field(default_factory=now_iso)

    @property
    def task_id(self) -> str:
        """Compatibility alias for historical AgentResult callers."""
        return self.run_id

    @property
    def ok(self) -> bool:
        return self.status in {"queued", "running", "succeeded", "skipped"}

    @property
    def heartbeat(self) -> str:
        return self.heartbeat_at

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


__all__ = ["WorkforceRequest", "WorkforceResult", "now_iso"]
