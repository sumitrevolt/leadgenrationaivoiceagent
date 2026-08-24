"""
Shared Agent Runtime — Agent-OS Phase-B execution layer (contract-ENFORCED).
============================================================================

WHY (2026-07-19, ADR-128): Phase-A ne 31 canonical Agent Runtime Contracts
banaye (`agent_registry.py`) — par woh sirf DATA the, koi runtime unhe enforce
nahi karta tha. Yeh module woh enforcement layer hai: EK common runtime jiske
upar har agent apne domain-specific capabilities chalata hai. 31 Swara-clones
ya 31 LLM services NAHI — ek control-plane, contract-driven policy gates,
per-agent tool adapters.

Swara se reuse kiye gaye PROVEN patterns (voice-specific code yahan NAHI):
  - explicit lifecycle state machine  (queued → leased → running → terminal)
  - structured result contract        (AgentResult — kabhi bare exception nahi)
  - timeout/fallback discipline       (per-attempt wait_for + bounded retry)
  - kill-switch + audit trail         (owner_os kill map + team.log_event)

REUSE-not-duplicate (koi naya queue/scheduler/persistence-system nahi):
  - kill switches      → app.platform.owner_os.kill_engaged (owner_all_agents etc.)
  - idempotency        → app.platform.agent_runtime_idempotency (Redis fail-closed)
  - cancellation       → app.platform.agent_runtime_cancellation (Redis fail-closed)
  - durable identity   → app.platform.agent_task_queue (AgentTask table, lease/claim)
  - useful-work events → app.platform.team.log_event (dashboard feed)
  - state files        → automation_health pattern (data/*.json + file_lock, atomic)

POLICY = ENFORCEMENT, display nahi. `run_task` / admission order (canonical):
  1 invalid agent/capability (no contract / not registered)
  2 RED hard-off / frozen
  3 global AGENT_RUNTIME flag
  4 individual agent primary_flag
  5 platform/agent kill switches  → reason kill_switch_engaged:<key>
  6 Owner OS stop-claims / drain / pause via runtime_admission_blocked
       → agent_claims_stopped | agent_draining | agent_paused
  7 Redis run-cancel (agent_runtime_cancellation) → cancelled
  8 capability / tenant / approval / budget policy
  9 concurrency slot + durable lease claim
  10 pre-engine re-check (admission + cancel) → then engine
  Race close: admission checked in evaluate_policy, again before durable open,
  and again immediately before cap.fn. Resume clears controls only — no catch-up.

CONTROLLED ROLLOUT: sirf PILOT_AGENTS dispatch ho sakte hain (Wave-A pilots +
Wave-B GREEN/read-only engines). Baaki agents capability-registered hote hain
(``agent_runtime_workforce``) par allowlist se bahar = intentionally disabled.
RED voice (swara/ananya) HAMESHA blocked. Big-bang 31-live activation nahi.

INERT DEFAULT: master flag `AGENT_RUNTIME` unset/0 = har dispatch SKIPPED.
Kuch bhi scheduled/automatic is module se nahi chalta — sirf Owner OS
operator-triggered runs (admin-auth) + tests. §5 gates kabhi weaken nahi hote:
RED lane (swara/ananya) HAMESHA blocked — koi env flip isse live nahi karta.

Import-safe; surface functions (runtime_status) kabhi raise nahi karte.
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Awaitable, Callable

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


# --------------------------------------------------------------------------- #
# Lifecycle
# --------------------------------------------------------------------------- #
class TaskStatus(str, Enum):
    QUEUED = "queued"
    LEASED = "leased"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"  # policy refused (fail-closed) — kill/prohibited/approval/budget/RED
    SKIPPED = "skipped"  # non-error non-run: flag off / duplicate / capability self-skip
    CANCELLED = "cancelled"  # distributed cancel observed before/at engine boundary


# Controlled rollout allowlist (code-level — never an env flip).
# Wave-A: kavya / isha / zara (proven).
# Wave-B: READ-ONLY / diagnostic GREEN only (engineer + hermes + nikhil scan).
# Mutating GREEN (neha/manager/ravi/…) stay capability-registered but OUT of
# allowlist until a dedicated canary. Voice RED + customer AMBER + voice-adjacent
# QA stay OUT.
PILOT_AGENTS: frozenset[str] = frozenset(
    {
        # Wave-A
        "kavya",
        "isha",
        "zara",
        # Wave-B read-only / diagnostic
        "hermes",
        "pranav",
        "vidya",
        "arnav",
        "kabir",
        "diya",
        "aryan",
        "arya",
        "nikhil",  # delivery_assurance scan ONLY (read-only capability)
    }
)

_MASTER_FLAG = "AGENT_RUNTIME"

# State files (automation_health pattern — data/*.json + file_lock + atomic replace).
_STATE_PATH = os.path.join("data", "agent_runtime_state.json")
_USAGE_PATH = os.path.join("data", "agent_runtime_usage.json")
_DLQ_PATH = os.path.join("data", "agent_runtime_dlq.jsonl")

_BACKOFF_BASE_S = 1.0  # retry backoff base (tests monkeypatch to 0)
_DLQ_MAX_LINES = 500


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat(timespec="seconds")


def _flag_on(name: str) -> bool:
    """Automation-flag truthiness: unset/0/false/no/off = OFF (fail-closed)."""
    v = (os.getenv(name) or "").strip().lower()
    return bool(v) and v not in ("0", "false", "no", "off")


def runtime_enabled() -> bool:
    return _flag_on(_MASTER_FLAG)


# --------------------------------------------------------------------------- #
# Injectable seams (tests monkeypatch these; defaults = real enforcement points)
# --------------------------------------------------------------------------- #
def _kill_engaged(key: str) -> bool | None:
    """None = check errored (caller treats as fail-CLOSED for owner_* keys)."""
    try:
        from app.platform.owner_os import kill_engaged

        return bool(kill_engaged(key))
    except Exception as e:
        logger.warning("[agent_runtime] kill check '%s' errored: %s", key, e)
        return None


def _owner_admission_blocked(agent_id: str) -> tuple[bool, str]:
    """Owner OS pause/drain/stop-claims — injectable seam for race tests.

    Returns (blocked, reason_code). Empty reason when not blocked.
    """
    try:
        from app.platform.owner_agent_execution import runtime_admission_blocked

        return runtime_admission_blocked(agent_id=agent_id)
    except Exception as e:
        logger.warning("[agent_runtime] owner admission check errored: %s", e)
        return True, "agent_control_state_ambiguous"


def admission_decision(
    *,
    allowed: bool,
    reason_code: str,
    agent_id: str,
    capability: str = "",
    control_source: str = "",
    control_id: str = "",
    correlation_id: str = "",
    state: str = "",
) -> dict[str, Any]:
    """Structured admission / control decision (Owner OS + admin projections)."""
    if not state:
        state = "allowed" if allowed else "blocked"
    return {
        "allowed": bool(allowed),
        "state": state,
        "reason_code": reason_code or "",
        "agent_id": agent_id,
        "capability": capability,
        "control_source": control_source,
        "control_id": control_id,
        "evaluated_at": _now_iso(),
        "correlation_id": correlation_id or "",
    }


def _idem_claim(task: AgentTask) -> Any:
    """Atomic Redis claim for Agent Runtime logical submissions (fail-closed)."""
    from app.platform import agent_runtime_idempotency as idem

    return idem.claim(
        task.agent_id,
        task.action,
        task.idempotency_key,
        tenant_id=task.tenant_id or None,
        runtime_run_id=task.task_id,
    )


def _idem_release(task: AgentTask) -> None:
    """Drop in-progress claim after control-block / capability skip (not terminal burn)."""
    try:
        from app.platform import agent_runtime_idempotency as idem

        idem.release(
            task.agent_id,
            task.action,
            task.idempotency_key,
            tenant_id=task.tenant_id or None,
        )
    except Exception:
        pass


def _idem_complete(task: AgentTask, status: str, *, reason: str = "", digest: str = "") -> Any:
    try:
        from app.platform import agent_runtime_idempotency as idem

        return idem.complete(
            task.agent_id,
            task.action,
            task.idempotency_key,
            status=status,
            tenant_id=task.tenant_id or None,
            terminal_reason=reason,
            result_digest=digest or None,
            runtime_run_id=task.task_id,
        )
    except Exception as e:
        logger.warning("[agent_runtime] idem complete failed: %s", type(e).__name__)
        return None


def _duplicate_from_claim(
    task: AgentTask, contract: Any | None, lc: list[str], claim: Any
) -> AgentResult:
    orig = claim.record or {}
    reason = claim.reason_code or "duplicate_suppressed"
    return AgentResult(
        task_id=task.task_id,
        agent_id=task.agent_id,
        action=task.action,
        status=TaskStatus.SKIPPED.value,
        reason=reason,
        mode=getattr(contract, "default_mode", "") if contract else "",
        lane=getattr(contract, "lane", "") if contract else "",
        escalation=getattr(contract, "escalation", "") if contract else "",
        lifecycle=list(lc) + [TaskStatus.SKIPPED.value],
        output={
            "original_run_id": orig.get("runtime_run_id"),
            "original_status": orig.get("status"),
            "idempotency_backend": getattr(claim, "backend", "") or "redis",
            "result_digest": orig.get("result_digest"),
        },
        decision=admission_decision(
            allowed=False,
            reason_code=reason,
            agent_id=task.agent_id,
            capability=task.action,
            control_source="agent_runtime_idempotency",
            state=str(orig.get("status") or "duplicate"),
            correlation_id=str(orig.get("runtime_run_id") or task.task_id),
        ),
    )


def _approval_approved(tenant_id: str, approval_ref: str) -> bool:
    """Default AMBER approval check — content_approval latest-state, tenant-scoped.
    Fail-CLOSED: record missing / wrong tenant / not approved / store error = False."""
    try:
        from app.marketing import content_approval

        rec = content_approval._by_id_for_client(tenant_id, approval_ref)
        return bool(rec) and str(rec.get("status") or "") == "approved"
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# Task / capability / context / result
# --------------------------------------------------------------------------- #
@dataclass
class AgentTask:
    agent_id: str
    action: str
    payload: dict[str, Any] = field(default_factory=dict)
    tenant_id: str = ""
    approval_ref: str = ""
    idempotency_key: str = ""
    trigger: str = "on_demand"
    timeout_s: float | None = None  # optional override (effective = min(contract, this))
    task_id: str = field(default_factory=lambda: "art_" + uuid.uuid4().hex[:12])
    created_at: str = field(default_factory=_now_iso)


class SkipTask(Exception):
    """Capability self-skip (e.g. downstream engine flag off) — honest non-run."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class AgentCapability:
    """Tool adapter — the ONLY way an agent does work under this runtime."""

    agent_id: str
    action: str
    fn: Callable[[AgentExecutionContext], Awaitable[dict[str, Any]]]
    side_effect: str = "none"  # none | internal | customer
    tenant_scoped: bool = False
    requires_approval: bool = False
    counts_contact: bool = False  # True = ek run == 1 customer touch (contact cap lagta)
    description: str = ""


@dataclass
class AgentExecutionContext:
    task: AgentTask
    contract: Any  # agent_registry.AgentContract
    tenant_id: str
    mode: str
    trace_id: str
    usage: dict[str, float] = field(
        default_factory=lambda: {"cost_inr": 0.0, "api_calls": 0.0, "contacts": 0.0}
    )
    # ADR-154: bounded workforce-memory brief (empty when WORKFORCE_MEMORY off)
    memory_brief: str = ""
    # ADR-161: deterministic 31-agent maturity contract plus optional bounded
    # role/knowledge context. The profile is always present; KB recall remains
    # explicitly canary-gated by AGENT_MATURITY_CONTEXT.
    maturity_profile: dict[str, Any] = field(default_factory=dict)
    skill_brief: str = ""
    knowledge_brief: str = ""

    def add_usage(self, cost_inr: float = 0.0, api_calls: int = 0, contacts: int = 0) -> None:
        self.usage["cost_inr"] += float(cost_inr or 0.0)
        self.usage["api_calls"] += int(api_calls or 0)
        self.usage["contacts"] += int(contacts or 0)

    def cancel_requested(self) -> bool:
        """Cooperative checkpoint — True if Redis cancel exists for this run."""
        from app.platform import agent_runtime_cancellation as crc

        return crc.is_requested(self.task.agent_id, self.task.task_id).requested

    def raise_if_cancelled(self) -> None:
        """Engines call at checkpoints; raises SkipTask('cancelled')."""
        if self.cancel_requested():
            raise SkipTask("cancelled")


@dataclass
class AgentResult:
    task_id: str
    agent_id: str
    action: str
    status: str
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
    decision: dict[str, Any] | None = None  # structured admission / control decision
    provider: str = "direct"
    queue: str = ""
    heartbeat: str = ""
    runtime_version: str = ""
    rollout_wave: str = "direct"
    at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}  # type: ignore[attr-defined]


# --------------------------------------------------------------------------- #
# Capability registry
# --------------------------------------------------------------------------- #
_CAPABILITIES: dict[tuple[str, str], AgentCapability] = {}
_CAP_LOCK = threading.Lock()


def register_capability(cap: AgentCapability) -> None:
    with _CAP_LOCK:
        _CAPABILITIES[(cap.agent_id, cap.action)] = cap


def get_capability(agent_id: str, action: str) -> AgentCapability | None:
    return _CAPABILITIES.get((agent_id, action))


def capabilities_for(agent_id: str) -> list[str]:
    return sorted(a for (aid, a) in _CAPABILITIES if aid == agent_id)


# --------------------------------------------------------------------------- #
# Concurrency + distributed cancellation (Redis via agent_runtime_cancellation)
# --------------------------------------------------------------------------- #
_ACTIVE: dict[str, int] = {}
_ACTIVE_TASKS: dict[str, dict[str, Any]] = {}
_RUN_LOCK = threading.Lock()


def request_cancel_run(
    agent_id: str,
    runtime_run_id: str,
    *,
    requested_by: str = "owner",
    reason: str = "",
    command_id: str = "",
    correlation_id: str = "",
    tenant_id: str | None = None,
) -> dict[str, Any]:
    """Cancel one runtime run (Redis). Preferred Owner OS path."""
    from app.platform import agent_runtime_cancellation as crc

    out = crc.request(
        agent_id,
        runtime_run_id,
        requested_by=requested_by,
        reason=reason,
        command_id=command_id,
        correlation_id=correlation_id or runtime_run_id,
        tenant_id=tenant_id,
    )
    if out.get("ok"):
        try:
            from app.platform import owner_os

            owner_os.audit(
                requested_by,
                "agent_runtime_cancel_requested",
                {
                    "agent_id": agent_id,
                    "runtime_run_id": runtime_run_id,
                    "command_id": command_id,
                    "newly_created": out.get("newly_created"),
                },
            )
        except Exception:
            pass
    return out


def request_cancel(
    agent_id: str, *, requested_by: str = "owner", reason: str = ""
) -> dict[str, Any]:
    """Emergency: cancel every *currently registered* active run for this agent.

    Does NOT create a permanent agent-wide marker — future runs are unaffected.
    """
    from app.platform import agent_runtime_cancellation as crc

    with _RUN_LOCK:
        targets = [tid for tid, info in _ACTIVE_TASKS.items() if info.get("agent_id") == agent_id]
    if not targets:
        return {
            "ok": True,
            "status": "no_running_tasks",
            "agent_id": agent_id,
            "targeted_run_ids": [],
            "requested_count": 0,
            "already_requested_count": 0,
            "cancellation_backend": crc.backend_status().get("cancellation_backend"),
            "fallback_active": crc.backend_status().get("fallback_active"),
        }
    requested = 0
    already = 0
    targeted: list[str] = []
    for tid in targets:
        out = request_cancel_run(
            agent_id, tid, requested_by=requested_by, reason=reason or "agent_emergency_cancel"
        )
        if out.get("ok"):
            targeted.append(tid)
            if out.get("already_requested"):
                already += 1
            else:
                requested += 1
        elif out.get("reason_code") == "cancellation_store_unavailable":
            return out
    return {
        "ok": True,
        "status": "cancel_requested",
        "agent_id": agent_id,
        "targeted_run_ids": targeted,
        "requested_count": requested,
        "already_requested_count": already,
        "cancellation_backend": crc.backend_status().get("cancellation_backend"),
        "fallback_active": crc.backend_status().get("fallback_active"),
    }


def clear_cancel(agent_id: str, runtime_run_id: str = "") -> dict[str, Any]:
    """Clear a specific run cancel, or all active-task cancels for the agent."""
    from app.platform import agent_runtime_cancellation as crc

    if runtime_run_id:
        return crc.clear(agent_id, runtime_run_id)
    with _RUN_LOCK:
        targets = [tid for tid, info in _ACTIVE_TASKS.items() if info.get("agent_id") == agent_id]
    cleared = 0
    for tid in targets:
        out = crc.clear(agent_id, tid)
        if out.get("cleared"):
            cleared += 1
    return {"ok": True, "agent_id": agent_id, "cleared_count": cleared, "targeted_run_ids": targets}


def _cancel_check(
    task: AgentTask, contract: Any | None = None, lc: list[str] | None = None
) -> AgentResult | None:
    """Shared cancel probe. Returns AgentResult refusal or None to continue."""
    from app.platform import agent_runtime_cancellation as crc

    chk = crc.is_requested(task.agent_id, task.task_id)
    base_lc = list(lc or [TaskStatus.QUEUED.value])
    if chk.status == "store_unavailable":
        decision = admission_decision(
            allowed=False,
            reason_code="cancellation_store_unavailable",
            agent_id=task.agent_id,
            capability=task.action,
            control_source="agent_runtime_cancellation",
            correlation_id=task.task_id,
        )
        return _blocked(
            task,
            contract,
            "cancellation_store_unavailable",
            base_lc,
            decision=decision,
        )
    if chk.requested:
        decision = admission_decision(
            allowed=False,
            reason_code="cancel_requested",
            agent_id=task.agent_id,
            capability=task.action,
            control_source="agent_runtime_cancellation",
            correlation_id=task.task_id,
            state="cancelled",
        )
        return AgentResult(
            task_id=task.task_id,
            agent_id=task.agent_id,
            action=task.action,
            status=TaskStatus.CANCELLED.value,
            reason="cancel_requested",
            mode=getattr(contract, "default_mode", "") if contract else "",
            lane=getattr(contract, "lane", "") if contract else "",
            escalation=getattr(contract, "escalation", "") if contract else "",
            lifecycle=base_lc + [TaskStatus.CANCELLED.value],
            decision=decision,
        )
    return None


def _acquire_slot(agent_id: str, limit: int) -> bool:
    with _RUN_LOCK:
        cur = _ACTIVE.get(agent_id, 0)
        if cur >= max(1, int(limit)):
            return False
        _ACTIVE[agent_id] = cur + 1
        return True


def _release_slot(agent_id: str) -> None:
    with _RUN_LOCK:
        _ACTIVE[agent_id] = max(0, _ACTIVE.get(agent_id, 0) - 1)


# --------------------------------------------------------------------------- #
# State / usage / DLQ stores (file_lock + atomic replace — automation_health pattern)
# --------------------------------------------------------------------------- #
def _read_json(path: str) -> dict[str, Any]:
    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f) or {}
    except Exception:
        pass
    return {}


def _write_json_locked(path: str, mutate: Callable[[dict[str, Any]], None]) -> None:
    """Read-modify-write under cross-process lock + atomic replace. Never raises."""
    try:
        from app.utils.file_lock import file_lock

        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with file_lock(path):
            data = _read_json(path)
            mutate(data)
            tmp = f"{path}.tmp.{os.getpid()}"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(tmp, path)
    except Exception as e:
        logger.debug("[agent_runtime] state write skip (%s): %s", path, e)


def _record_heartbeat(
    agent_id: str, *, useful: bool = False, result: AgentResult | None = None
) -> None:
    """Process heartbeat har run-attempt pe; useful-work sirf real succeeded output pe."""

    def mut(data: dict[str, Any]) -> None:
        row = data.get(agent_id) or {}
        row["process_hb"] = _now_iso()
        if useful:
            row["useful_work"] = _now_iso()
        if result is not None:
            row["last_result"] = {
                "task_id": result.task_id,
                "action": result.action,
                "status": result.status,
                "reason": result.reason[:160],
                "error_class": result.error_class,
                "at": result.at,
            }
        data[agent_id] = row

    _write_json_locked(_STATE_PATH, mut)


def _usage_today(agent_id: str) -> dict[str, float]:
    day = _now_iso()[:10]
    row = (_read_json(_USAGE_PATH).get(day) or {}).get(agent_id) or {}
    return {
        "cost_inr": float(row.get("cost_inr") or 0.0),
        "api_calls": float(row.get("api_calls") or 0.0),
        "contacts": float(row.get("contacts") or 0.0),
        "runs": float(row.get("runs") or 0.0),
    }


def _charge_usage(agent_id: str, usage: dict[str, float]) -> None:
    day = _now_iso()[:10]

    def mut(data: dict[str, Any]) -> None:
        # prune old days (7-day retention)
        for k in sorted(data.keys())[:-7]:
            data.pop(k, None)
        daymap = data.get(day) or {}
        row = daymap.get(agent_id) or {}
        row["cost_inr"] = round(
            float(row.get("cost_inr") or 0.0) + float(usage.get("cost_inr") or 0.0), 4
        )
        row["api_calls"] = int(row.get("api_calls") or 0) + int(usage.get("api_calls") or 0)
        row["contacts"] = int(row.get("contacts") or 0) + int(usage.get("contacts") or 0)
        row["runs"] = int(row.get("runs") or 0) + 1
        daymap[agent_id] = row
        data[day] = daymap

    _write_json_locked(_USAGE_PATH, mut)


def _dlq_push(task: AgentTask, result: AgentResult) -> None:
    """Retry-exhausted failure → runtime DLQ (failure reason ke saath, bounded)."""
    try:
        os.makedirs(os.path.dirname(_DLQ_PATH) or ".", exist_ok=True)
        rec = {
            "task_id": task.task_id,
            "agent_id": task.agent_id,
            "action": task.action,
            "tenant_id": task.tenant_id,
            "attempts": result.attempts,
            "error_class": result.error_class,
            "error_message": result.error_message[:300],
            "escalation": result.escalation,
            "at": _now_iso(),
        }
        with open(_DLQ_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        _dlq_trim()
    except Exception:
        pass


def _dlq_trim() -> None:
    try:
        with open(_DLQ_PATH, encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) > _DLQ_MAX_LINES * 2:
            with open(_DLQ_PATH, "w", encoding="utf-8") as f:
                f.writelines(lines[-_DLQ_MAX_LINES:])
    except Exception:
        pass


def _dlq_count() -> int:
    try:
        if not os.path.exists(_DLQ_PATH):
            return 0
        with open(_DLQ_PATH, encoding="utf-8") as f:
            return sum(1 for line in f if line.strip())
    except Exception:
        return 0


def _log_team_event(agent_id: str, action: str, detail: str, status: str = "ok") -> None:
    try:
        from app.platform import team

        team.log_event(agent_id, action, detail[:150], status=status)
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# Durable task-identity bridge (agent_task_queue reuse — best-effort, never raises)
# --------------------------------------------------------------------------- #
async def _durable_open(task: AgentTask) -> str | None:
    try:
        from app.platform import agent_task_queue as atq

        rec = await atq.assign(
            task.agent_id,
            f"runtime:{task.action}",
            client_id=task.tenant_id or None,
            goal_text=f"agent_runtime {task.task_id}",
            delegated_by="agent_runtime",
        )
        did = rec.get("id") if rec.get("ok") else None
        if did:
            # claim → running (lease semantics; stale_tasks() surfaces expired leases)
            claimed = await atq.claim_next(task.agent_id)
            if claimed and claimed.get("id") == did:
                await atq.start(did)
        return did
    except Exception:
        return None


async def _durable_close(durable_id: str | None, ok: bool, detail: str) -> None:
    if not durable_id:
        return
    try:
        from app.platform import agent_task_queue as atq

        if ok:
            await atq.complete(durable_id, result=detail[:300])
        else:
            await atq.fail(durable_id, detail[:300])
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# Policy evaluation (fail-CLOSED) — contract se derive, dispatch se PEHLE enforce
# --------------------------------------------------------------------------- #
def _max_attempts(retry_policy: str) -> int:
    """Bounded retry from contract retry_policy. DLQ-lane policies get 3 attempts;
    skip-on-fail / none / no-auto-retry / daily-window policies get 1."""
    return 3 if "dlq" in (retry_policy or "").lower() else 1


def _blocked(
    task: AgentTask,
    contract: Any,
    reason: str,
    lifecycle: list[str],
    *,
    decision: dict[str, Any] | None = None,
) -> AgentResult:
    return AgentResult(
        task_id=task.task_id,
        agent_id=task.agent_id,
        action=task.action,
        status=TaskStatus.BLOCKED.value,
        reason=reason,
        mode=getattr(contract, "default_mode", "") if contract else "",
        lane=getattr(contract, "lane", "") if contract else "",
        escalation=getattr(contract, "escalation", "") if contract else "",
        lifecycle=lifecycle + [TaskStatus.BLOCKED.value],
        decision=decision,
    )


def _owner_control_refusal(
    task: AgentTask, contract: Any, reason: str, lifecycle: list[str]
) -> AgentResult:
    """Block with structured Owner OS control decision + audit-friendly team event."""
    decision = admission_decision(
        allowed=False,
        reason_code=reason,
        agent_id=task.agent_id,
        capability=task.action,
        control_source="owner_os",
        correlation_id=task.task_id,
    )
    _log_team_event(
        task.agent_id,
        "runtime_control_blocked",
        f"{task.action}: {reason}",
        status="warn",
    )
    return _blocked(task, contract, reason, lifecycle, decision=decision)


def _skipped(task: AgentTask, contract: Any, reason: str, lifecycle: list[str]) -> AgentResult:
    return AgentResult(
        task_id=task.task_id,
        agent_id=task.agent_id,
        action=task.action,
        status=TaskStatus.SKIPPED.value,
        reason=reason,
        mode=getattr(contract, "default_mode", "") if contract else "",
        lane=getattr(contract, "lane", "") if contract else "",
        escalation=getattr(contract, "escalation", "") if contract else "",
        lifecycle=lifecycle + [TaskStatus.SKIPPED.value],
    )


def evaluate_policy(task: AgentTask) -> tuple[Any, AgentCapability, AgentResult | None]:
    """Pre-dispatch policy gates. Returns (contract, capability, refusal|None).

    Fail-CLOSED throughout: missing contract, RED lane, errored kill check,
    unregistered capability, tenant gap, missing approval, exhausted budget —
    sab refusal return karte hain, silent execution kabhi nahi.
    """
    from app.platform import agent_registry as ar

    lc = [TaskStatus.QUEUED.value]

    # 1. Master flag (INERT default)
    if not runtime_enabled():
        return None, None, _skipped(task, None, f"runtime_flag_disabled:{_MASTER_FLAG}", lc)

    # 2. Contract must exist (registry = source of truth)
    contract = ar.get_contract(task.agent_id)
    if contract is None:
        return None, None, _blocked(task, None, "no_contract_in_registry", lc)

    # 3. RED lane / hard_off — NEVER dispatchable here. No env flip can pass this.
    if contract.lane == ar.Lane.RED.value or contract.default_mode == ar.HARD_OFF:
        return contract, None, _blocked(task, contract, "red_lane_hard_off_mandate_required", lc)

    # 4. Controlled rollout — pilots only (code allowlist, not env)
    if task.agent_id not in PILOT_AGENTS:
        return contract, None, _blocked(task, contract, "not_in_pilot_rollout", lc)

    # 5. Prohibited actions (contract data = enforcement, not display)
    if task.action in set(contract.prohibited):
        return contract, None, _blocked(task, contract, f"prohibited_action:{task.action}", lc)

    # 6. Primary feature flag — PILOT / canary-ready agents MUST be explicitly gated.
    #    Empty primary_flag on a dispatchable agent = fail-CLOSED (agent_flag_missing).
    #    Non-pilot hold/frozen inventory may still use "" (not executable via this path).
    flag = (contract.primary_flag or "").strip()
    if task.agent_id in PILOT_AGENTS and not flag:
        decision = admission_decision(
            allowed=False,
            reason_code="agent_flag_missing",
            agent_id=task.agent_id,
            capability=task.action,
            control_source="agent_runtime",
            correlation_id=task.task_id,
        )
        return (
            contract,
            None,
            _blocked(task, contract, "agent_flag_missing", lc, decision=decision),
        )
    if flag and not _flag_on(flag):
        return (
            contract,
            None,
            _skipped(task, contract, f"flag_disabled:{flag}", lc),
        )

    # 7. Kill switches — owner_all_agents global + per-agent. Errored check on
    #    owner_* keys = fail-CLOSED (block), kyunki woh store-backed hote hain.
    for key in contract.kill_switches:
        engaged = _kill_engaged(key)
        if engaged is True:
            decision = admission_decision(
                allowed=False,
                reason_code="kill_switch_active",
                agent_id=task.agent_id,
                capability=task.action,
                control_source="owner_os",
                control_id=key,
                correlation_id=task.task_id,
            )
            # Keep legacy reason string for production-proven callers/tests;
            # structured decision.reason_code = kill_switch_active.
            return (
                contract,
                None,
                _blocked(
                    task,
                    contract,
                    f"kill_switch_engaged:{key}",
                    lc,
                    decision=decision,
                ),
            )
        if engaged is None and key.startswith("owner_"):
            return contract, None, _blocked(task, contract, f"kill_switch_check_error:{key}", lc)

    # 8. Owner OS pause / drain / stop-claims (shared admission; reject — no park)
    blocked, ctrl_reason = _owner_admission_blocked(task.agent_id)
    if blocked:
        return contract, None, _owner_control_refusal(task, contract, ctrl_reason, lc)

    # 9. Distributed run-cancel (Redis) — specific runtime_run_id only
    cancel_res = _cancel_check(task, contract, lc)
    if cancel_res is not None:
        return contract, None, cancel_res

    # 10. Capability must be registered (tool adapter = the only execution path)
    cap = get_capability(task.agent_id, task.action)
    if cap is None:
        return (
            contract,
            None,
            _blocked(task, contract, f"capability_not_registered:{task.action}", lc),
        )

    # 11. Tenant isolation — tenant-scoped work needs an explicit tenant, and the
    #    payload may not point at a different tenant (cross-client leak gate).
    if cap.tenant_scoped:
        if not task.tenant_id:
            return contract, cap, _blocked(task, contract, "tenant_required", lc)
        payload_cid = str(task.payload.get("client_id") or "")
        if payload_cid and payload_cid != task.tenant_id:
            return contract, cap, _blocked(task, contract, "tenant_mismatch", lc)

    # 12. Customer-facing approval (AMBER discipline): explicit requires_approval
    #     OR any customer side-effect on an AMBER/RED-ceiling agent.
    needs_approval = cap.requires_approval or (
        cap.side_effect == "customer" and contract.lane in (ar.Lane.AMBER.value, ar.Lane.RED.value)
    )
    if needs_approval:
        if not task.approval_ref:
            return contract, cap, _blocked(task, contract, "approval_required", lc)
        if not _approval_approved(task.tenant_id, task.approval_ref):
            return contract, cap, _blocked(task, contract, "approval_not_approved", lc)

    # 13. Contact cap: counting capability on a zero-cap agent = never allowed.
    if cap.counts_contact and contract.customer_contact_cap_day <= 0:
        return contract, cap, _blocked(task, contract, "customer_contact_not_allowed", lc)

    # 14. Budgets (daily, fail-CLOSED at the cap)
    usage = _usage_today(task.agent_id)
    if contract.cost_budget_inr_day > 0 and usage["cost_inr"] >= contract.cost_budget_inr_day:
        return contract, cap, _blocked(task, contract, "budget_exhausted:cost_inr", lc)
    if contract.api_calls_day > 0 and usage["api_calls"] >= contract.api_calls_day:
        return contract, cap, _blocked(task, contract, "budget_exhausted:api_calls", lc)
    if cap.counts_contact and usage["contacts"] >= contract.customer_contact_cap_day:
        return contract, cap, _blocked(task, contract, "budget_exhausted:contacts", lc)

    return contract, cap, None


# --------------------------------------------------------------------------- #
# The runner
# --------------------------------------------------------------------------- #
async def run_task(task: AgentTask) -> AgentResult:
    """Execute ONE task under full contract policy. Never raises — structured
    AgentResult always. Lifecycle: queued → leased → running → terminal."""
    t0 = time.monotonic()
    lc = [TaskStatus.QUEUED.value]

    try:
        contract, cap, refusal = evaluate_policy(task)
    except Exception as e:  # policy evaluator crash = fail-CLOSED block
        logger.warning("[agent_runtime] policy eval crashed: %s", e)
        refusal = _blocked(task, None, f"policy_eval_error:{type(e).__name__}", lc)
        contract, cap = None, None

    # Process heartbeat on EVERY dispatch attempt (even refusals) — runtime alive.
    if refusal is not None:
        _record_heartbeat(task.agent_id, useful=False, result=refusal)
        if refusal.status in (TaskStatus.BLOCKED.value, TaskStatus.CANCELLED.value):
            _log_team_event(
                task.agent_id, "runtime_blocked", f"{task.action}: {refusal.reason}", status="warn"
            )
        return refusal

    # Race close #1: control set after policy pass, before concurrency lease.
    late_block, late_reason = _owner_admission_blocked(task.agent_id)
    if late_block:
        res = _owner_control_refusal(task, contract, late_reason, lc)
        _record_heartbeat(task.agent_id, useful=False, result=res)
        return res
    cancel_res = _cancel_check(task, contract, lc)
    if cancel_res is not None:
        _record_heartbeat(task.agent_id, useful=False, result=cancel_res)
        return cancel_res

    # Concurrency slot (lease semantics — in-process; durable lease via atq below)
    if not _acquire_slot(task.agent_id, contract.max_concurrency):
        res = _blocked(task, contract, "concurrency_limit", lc)
        _record_heartbeat(task.agent_id, useful=False, result=res)
        return res

    durable_id: str | None = None
    idem_claimed = False
    try:
        # Race close #2: control between slot acquire and durable/engine work.
        late_block, late_reason = _owner_admission_blocked(task.agent_id)
        if late_block:
            res = _owner_control_refusal(task, contract, late_reason, lc)
            _record_heartbeat(task.agent_id, useful=False, result=res)
            return res
        cancel_res = _cancel_check(task, contract, lc)
        if cancel_res is not None:
            _record_heartbeat(task.agent_id, useful=False, result=cancel_res)
            return cancel_res

        lc.append(TaskStatus.LEASED.value)
        with _RUN_LOCK:
            _ACTIVE_TASKS[task.task_id] = {
                "agent_id": task.agent_id,
                "action": task.action,
                "tenant_id": task.tenant_id,
                "started_at": _now_iso(),
            }
        # Idempotency claim — sab gates pass hone ke BAAD (blocked runs key nahi jalate)
        if task.idempotency_key:
            claim = _idem_claim(task)
            if claim.store_unavailable or (
                not claim.ok and claim.reason_code == "idempotency_store_unavailable"
            ):
                res = _blocked(
                    task,
                    contract,
                    "idempotency_store_unavailable",
                    lc,
                    decision=admission_decision(
                        allowed=False,
                        reason_code="idempotency_store_unavailable",
                        agent_id=task.agent_id,
                        capability=task.action,
                        control_source="agent_runtime_idempotency",
                        correlation_id=task.task_id,
                    ),
                )
                _record_heartbeat(task.agent_id, useful=False, result=res)
                return res
            if not claim.ok and claim.reason_code in (
                "malformed_idempotency_key",
                "idempotency_record_malformed",
            ):
                res = _blocked(task, contract, claim.reason_code, lc)
                _record_heartbeat(task.agent_id, useful=False, result=res)
                return res
            if claim.duplicate:
                res = _duplicate_from_claim(task, contract, lc, claim)
                _record_heartbeat(task.agent_id, useful=False, result=res)
                return res
            idem_claimed = bool(claim.claimed)

        durable_id = await _durable_open(task)

        # Post-lease / post-durable cancel (before engine)
        cancel_res = _cancel_check(task, contract, lc)
        if cancel_res is not None:
            if idem_claimed:
                _idem_complete(task, "cancelled", reason=cancel_res.reason or "cancel_requested")
            await _durable_close(durable_id, False, "cancelled:post_lease")
            _record_heartbeat(task.agent_id, useful=False, result=cancel_res)
            return cancel_res

        effective_timeout = float(contract.run_timeout_s)
        if task.timeout_s:
            effective_timeout = min(effective_timeout, float(task.timeout_s))

        attempts_allowed = _max_attempts(contract.retry_policy)
        mem_brief = ""
        try:
            from app.platform import workforce_memory as _wfm

            mem_brief = (
                _wfm.inject_for_runtime(task.agent_id, task.action, tenant_id=task.tenant_id) or ""
            )
        except Exception:
            mem_brief = ""

        maturity_profile: dict[str, Any] = {}
        maturity_briefs: dict[str, Any] = {}
        try:
            from app.platform import agent_maturity as _maturity

            maturity_profile = _maturity.profile(task.agent_id, task.tenant_id)
            maturity_briefs = await _maturity.runtime_briefs(
                task.agent_id, task.tenant_id, task.action
            )
        except Exception:
            maturity_profile = {}
            maturity_briefs = {}

        ctx = AgentExecutionContext(
            task=task,
            contract=contract,
            tenant_id=task.tenant_id,
            mode=contract.default_mode,
            trace_id="tr_" + uuid.uuid4().hex[:10],
            memory_brief=mem_brief[:2000],
            maturity_profile=maturity_profile,
            skill_brief=str(maturity_briefs.get("skill_brief") or "")[:1200],
            knowledge_brief=str(maturity_briefs.get("knowledge_brief") or "")[:1600],
        )

        lc.append(TaskStatus.RUNNING.value)
        last_err: tuple[str, str] = ("", "")
        for attempt in range(1, attempts_allowed + 1):
            # Race close #3: control / cancel immediately before engine call.
            pre_block, pre_reason = _owner_admission_blocked(task.agent_id)
            if pre_block:
                if idem_claimed:
                    _idem_release(task)  # control-blocked — do not burn successful key
                res = _owner_control_refusal(task, contract, pre_reason, lc)
                await _durable_close(durable_id, False, f"blocked:{pre_reason}")
                _record_heartbeat(task.agent_id, useful=False, result=res)
                return res
            cancel_res = _cancel_check(task, contract, lc)
            if cancel_res is not None:
                if idem_claimed:
                    _idem_complete(
                        task, "cancelled", reason=cancel_res.reason or "cancel_requested"
                    )
                await _durable_close(durable_id, False, "cancelled:pre_engine")
                _record_heartbeat(task.agent_id, useful=False, result=cancel_res)
                return cancel_res
            try:
                output = await asyncio.wait_for(cap.fn(ctx), timeout=effective_timeout)
                dur = int((time.monotonic() - t0) * 1000)
                # Non-cooperative engine: cancel requested during wait_for completed
                # anyway — classify honestly (do not pretend we cancelled mid-flight).
                from app.platform import agent_runtime_cancellation as crc

                post = crc.is_requested(task.agent_id, task.task_id)
                if post.requested:
                    res = AgentResult(
                        task_id=task.task_id,
                        agent_id=task.agent_id,
                        action=task.action,
                        status=TaskStatus.SUCCEEDED.value,
                        reason="cancel_requested_but_engine_completed",
                        output=output if isinstance(output, dict) else {"value": output},
                        attempts=attempt,
                        duration_ms=dur,
                        mode=contract.default_mode,
                        lane=contract.lane,
                        escalation=contract.escalation,
                        lifecycle=lc + [TaskStatus.SUCCEEDED.value],
                        usage=dict(ctx.usage),
                        decision=admission_decision(
                            allowed=True,
                            reason_code="cancel_requested_but_engine_completed",
                            agent_id=task.agent_id,
                            capability=task.action,
                            control_source="agent_runtime_cancellation",
                            state="completed_despite_cancel",
                            correlation_id=task.task_id,
                        ),
                    )
                    if idem_claimed:
                        commit = _idem_complete(
                            task,
                            "cancel_requested_but_engine_completed",
                            reason="noncoop",
                            digest=task.task_id,
                        )
                        if commit is not None and getattr(commit, "store_unavailable", False):
                            res.reason = "execution_completed_idempotency_commit_uncertain"
                    _charge_usage(task.agent_id, ctx.usage)
                    _record_heartbeat(task.agent_id, useful=True, result=res)
                    _log_team_event(
                        task.agent_id,
                        "runtime_cancel_after_complete",
                        f"{task.action}: engine finished under cancel request",
                        status="warn",
                    )
                    await _durable_close(
                        durable_id, True, f"{task.action}: cancel_requested_but_engine_completed"
                    )
                    return res
                res = AgentResult(
                    task_id=task.task_id,
                    agent_id=task.agent_id,
                    action=task.action,
                    status=TaskStatus.SUCCEEDED.value,
                    output=output if isinstance(output, dict) else {"value": output},
                    attempts=attempt,
                    duration_ms=dur,
                    mode=contract.default_mode,
                    lane=contract.lane,
                    escalation=contract.escalation,
                    lifecycle=lc + [TaskStatus.SUCCEEDED.value],
                    usage=dict(ctx.usage),
                )
                if idem_claimed:
                    commit = _idem_complete(task, "succeeded", reason="ok", digest=task.task_id)
                    if commit is not None and getattr(commit, "store_unavailable", False):
                        res.reason = "execution_completed_idempotency_commit_uncertain"
                _charge_usage(task.agent_id, ctx.usage)
                _record_heartbeat(task.agent_id, useful=True, result=res)
                _log_team_event(task.agent_id, "runtime_done", f"{task.action} ok ({dur}ms)")
                try:
                    from app.platform import workforce_memory as _wfm

                    _wfm.remember_runtime_outcome(
                        task.agent_id,
                        task.action,
                        ok=True,
                        detail=f"{dur}ms",
                        tenant_id=task.tenant_id,
                    )
                except Exception:
                    pass
                await _durable_close(durable_id, True, f"{task.action} succeeded")
                return res
            except SkipTask as sk:
                if str(sk.reason) == "cancelled":
                    if idem_claimed:
                        _idem_complete(task, "cancelled", reason="cooperative")
                    res = _cancel_check(task, contract, lc) or AgentResult(
                        task_id=task.task_id,
                        agent_id=task.agent_id,
                        action=task.action,
                        status=TaskStatus.CANCELLED.value,
                        reason="cancel_requested",
                        attempts=attempt,
                        lifecycle=lc + [TaskStatus.CANCELLED.value],
                    )
                    await _durable_close(durable_id, False, "cancelled:cooperative")
                    _record_heartbeat(task.agent_id, useful=False, result=res)
                    return res
                res = _skipped(task, contract, f"capability_skip:{sk.reason}", lc)
                res.attempts = attempt
                res.usage = dict(ctx.usage)
                _charge_usage(task.agent_id, ctx.usage)
                _record_heartbeat(task.agent_id, useful=False, result=res)
                await _durable_close(durable_id, True, f"{task.action} skipped: {sk.reason}")
                if idem_claimed:
                    _idem_release(task)  # skip ≠ durable success — retry allowed later
                return res
            except asyncio.TimeoutError:
                last_err = ("TimeoutError", f"attempt {attempt} exceeded {effective_timeout}s")
            except Exception as e:
                last_err = (type(e).__name__, str(e)[:300])
            if attempt < attempts_allowed and _BACKOFF_BASE_S > 0:
                await asyncio.sleep(min(_BACKOFF_BASE_S * attempt, 10.0))

        # Retry-exhausted → FAILED (+ DLQ for DLQ-lane retry policies)
        dur = int((time.monotonic() - t0) * 1000)
        goes_dlq = "dlq" in (contract.retry_policy or "").lower()
        res = AgentResult(
            task_id=task.task_id,
            agent_id=task.agent_id,
            action=task.action,
            status=TaskStatus.FAILED.value,
            reason="retry_exhausted" if attempts_allowed > 1 else "execution_failed",
            error_class=last_err[0],
            error_message=last_err[1],
            attempts=attempts_allowed,
            duration_ms=dur,
            mode=contract.default_mode,
            lane=contract.lane,
            escalation=contract.escalation,
            dlq=goes_dlq,
            lifecycle=lc + [TaskStatus.FAILED.value],
            usage=dict(ctx.usage),
        )
        _charge_usage(task.agent_id, ctx.usage)
        if goes_dlq:
            _dlq_push(task, res)
        if idem_claimed:
            # Terminal failure retained — same key does not auto-retry (need new key)
            _idem_complete(task, "failed", reason=res.reason or "execution_failed")
        _record_heartbeat(task.agent_id, useful=False, result=res)
        _log_team_event(
            task.agent_id,
            "runtime_failed",
            f"{task.action}: {last_err[0]} → escalate {contract.escalation}",
            status="error",
        )
        await _durable_close(durable_id, False, f"{last_err[0]}: {last_err[1]}")
        return res
    finally:
        _release_slot(task.agent_id)
        with _RUN_LOCK:
            _ACTIVE_TASKS.pop(task.task_id, None)


async def submit(
    agent_id: str,
    action: str,
    payload: dict[str, Any] | None = None,
    *,
    tenant_id: str = "",
    approval_ref: str = "",
    idempotency_key: str = "",
    trigger: str = "on_demand",
    timeout_s: float | None = None,
) -> AgentResult:
    """Canonical runtime-neutral submission; DSH OFF rolls back to direct."""
    from app.platform.workforce_runtime import WorkforceRequest
    from app.platform.workforce_runtime import dispatch as workforce_dispatch

    result = await workforce_dispatch(
        WorkforceRequest(
            agent_id=agent_id,
            action=action,
            payload=dict(payload or {}),
            tenant_id=tenant_id,
            approval_ref=approval_ref,
            idempotency_key=idempotency_key,
            trigger=trigger,
            timeout_s=timeout_s,
        )
    )
    decision = result.decision or admission_decision(
        allowed=result.ok,
        reason_code=result.reason,
        agent_id=agent_id,
        capability=action,
        control_source="workforce_dispatch",
        correlation_id=result.run_id,
        state=result.status,
    )
    return AgentResult(
        task_id=result.run_id or idempotency_key,
        agent_id=agent_id,
        action=action,
        status=result.status,
        reason=result.reason,
        output=result.output,
        error_class=result.error_class,
        error_message=result.error_message,
        attempts=result.attempts,
        duration_ms=result.duration_ms,
        mode=result.mode,
        lane=result.lane,
        escalation=result.escalation,
        dlq=result.dlq,
        lifecycle=(
            list(result.lifecycle)
            if result.lifecycle
            else [TaskStatus.QUEUED.value]
            if result.status == "queued"
            else [result.status]
        ),
        usage=dict(result.usage),
        decision=decision,
        provider=result.provider,
        queue=result.queue,
        heartbeat=result.heartbeat,
        runtime_version=result.runtime_version,
        rollout_wave=result.rollout_wave,
    )


# --------------------------------------------------------------------------- #
# Operator status surface (never raises)
# --------------------------------------------------------------------------- #
def _agent_health(aid: str, contract: Any, row: dict[str, Any], event_only: bool) -> str:
    """Honest per-agent health. Event/on-demand idle = healthy_idle, NEVER offline."""
    hb = row.get("process_hb")
    useful = row.get("useful_work")
    if aid not in PILOT_AGENTS:
        if capabilities_for(aid):
            return "healthy_idle" if event_only else "capability_ready_hold"
        return "healthy_idle" if event_only else "registry_only"
    if not hb:
        return "pilot_ready"  # wired but not yet dispatched — not an incident
    try:
        gap = contract.useful_work_gap_min
        if gap is None or event_only:
            return "healthy" if useful else "healthy_idle"
        if not useful:
            return "healthy_idle"
        last = datetime.fromisoformat(str(useful))
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        stale = (_now() - last).total_seconds() / 60 > float(gap)
        return "stale_useful_work" if stale else "healthy"
    except Exception:
        return "unknown"


def _calling_badge_for_runtime() -> str:
    """Honest dial posture for runtime_status UI — never hard-code HARD OFF.

    Agent Runtime still blocks Swara/Ananya RED dispatch; that is orthogonal to
    whether the separately governed platform_dial / voice_launch campaign is live.
    """
    try:
        from app.platform.owner_os import calling_posture

        return str(calling_posture().get("badge") or "Calling OFF")
    except Exception:
        return "Calling OFF"


def runtime_status() -> dict[str, Any]:
    """Owner OS panel rollup — 31 agents × mode/lane/hb/useful-work/budget/kill/DLQ.
    Never raises; degraded sources surface as fields, not exceptions."""
    try:
        from app.platform import agent_registry as ar

        reg = ar.build_registry()
        state = _read_json(_STATE_PATH)
        day = _now_iso()[:10]
        usage_all = _read_json(_USAGE_PATH).get(day) or {}
        kill_cache: dict[str, Any] = {}
        agents: list[dict[str, Any]] = []
        with _RUN_LOCK:
            active_by_agent: dict[str, list[dict[str, Any]]] = {}
            for tid, info in _ACTIVE_TASKS.items():
                active_by_agent.setdefault(info["agent_id"], []).append({"task_id": tid, **info})
        try:
            from app.platform import agent_runtime_cancellation as crc

            cancel_backend = crc.backend_status()
        except Exception:
            crc = None  # type: ignore
            cancel_backend = {"cancellation_backend": "unknown", "fallback_active": True}
        for aid, c in reg.items():
            row = state.get(aid) or {}
            u = usage_all.get(aid) or {}
            kills = {}
            for k in c.kill_switches:
                if k not in kill_cache:
                    kill_cache[k] = _kill_engaged(k)
                kills[k] = kill_cache[k]
            event_only = aid in ar.EVENT_OR_ONDEMAND_ONLY
            active_runs = active_by_agent.get(aid) or []
            cancel_flags: list[str] = []
            if crc is not None:
                for arun in active_runs[:5]:
                    try:
                        chk = crc.is_requested(aid, arun["task_id"])
                        if chk.requested:
                            cancel_flags.append(arun["task_id"])
                    except Exception:
                        pass
            agents.append(
                {
                    "agent_id": aid,
                    "name": c.name,
                    "team": c.team,
                    "lane": c.lane,
                    "mode": c.default_mode,
                    "autonomy": c.autonomy,
                    "pilot": aid in PILOT_AGENTS,
                    "capabilities": capabilities_for(aid),
                    "health": _agent_health(aid, c, row, event_only),
                    "event_or_ondemand_only": event_only,
                    "last_heartbeat": row.get("process_hb"),
                    "last_useful_work": row.get("useful_work"),
                    "active_tasks": active_runs,
                    "last_result": row.get("last_result"),
                    "cancel_requested": bool(cancel_flags),
                    "cancel_targeted_run_ids": cancel_flags,
                    "budget": {
                        "cost_inr": {
                            "used": float(u.get("cost_inr") or 0.0),
                            "cap": c.cost_budget_inr_day,
                        },
                        "api_calls": {"used": int(u.get("api_calls") or 0), "cap": c.api_calls_day},
                        "contacts": {
                            "used": int(u.get("contacts") or 0),
                            "cap": c.customer_contact_cap_day,
                        },
                        "runs_today": int(u.get("runs") or 0),
                    },
                    "kill_switches": kills,
                    "escalation": c.escalation,
                }
            )
        agents.sort(key=lambda a: (not a["pilot"], a["team"], a["agent_id"]))
        queue: dict[str, Any] = {}
        try:
            from app.platform import automation_health

            queue = automation_health.queue_depth()
        except Exception:
            queue = {"error": "queue_depth_unavailable"}
        try:
            from app.platform import agent_runtime_idempotency as arid

            idem_status = arid.backend_status()
        except Exception:
            idem_status = {"idempotency_backend": "unknown", "fallback_active": True}
        return {
            "ok": True,
            "runtime_enabled": runtime_enabled(),
            "master_flag": _MASTER_FLAG,
            "pilots": sorted(PILOT_AGENTS),
            "rollout_note": (
                "Controlled rollout — PILOT_AGENTS dispatchable under AGENT_RUNTIME. "
                "Others capability-registered but hold/frozen; no big-bang 31-live."
            ),
            "canonical_count": len(reg),
            "runtime_dlq_count": _dlq_count(),
            "celery_queue": queue,
            "cancellation": cancel_backend,
            "idempotency": idem_status,
            "agents": agents,
            # Reuse Owner OS posture — never hard-code HARD OFF when dial is live.
            # Agent Runtime RED still blocks Swara/Ananya dispatch; that is separate
            # from the compliance-gated platform_dial / voice_launch campaign.
            "calling_badge": _calling_badge_for_runtime(),
            "generated_at": _now_iso(),
        }
    except Exception as e:
        logger.warning("[agent_runtime] runtime_status degraded: %s", e)
        return {"ok": False, "error": type(e).__name__, "agents": [], "generated_at": _now_iso()}


def runtime_dlq(limit: int = 50) -> list[dict[str, Any]]:
    """Last N runtime-DLQ records (never raises)."""
    out: list[dict[str, Any]] = []
    try:
        if os.path.exists(_DLQ_PATH):
            with open(_DLQ_PATH, encoding="utf-8") as f:
                lines = [line.strip() for line in f if line.strip()]
            for line in lines[-max(1, min(int(limit), 200)) :]:
                try:
                    out.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        pass
    return list(reversed(out))


__all__ = [
    "TaskStatus",
    "AgentTask",
    "AgentCapability",
    "AgentExecutionContext",
    "AgentResult",
    "SkipTask",
    "PILOT_AGENTS",
    "register_capability",
    "get_capability",
    "capabilities_for",
    "run_task",
    "submit",
    "request_cancel",
    "request_cancel_run",
    "clear_cancel",
    "runtime_enabled",
    "runtime_status",
    "runtime_dlq",
    "evaluate_policy",
    "admission_decision",
]
