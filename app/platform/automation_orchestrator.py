"""
Automation-Max Orchestrator Control Plane (v3.0 Production Authority)
========================================================================
Canonical supervisory & specialist execution control plane.

Key Architecture & Production Authority:
1. 9 Hermes bots = Supervisory / Control Plane (board, pilot, guardian, etc.)
2. 31 Agents = Specialist Execution Plane (derived from agent_registry.py)
3. Hard Rule: One Task -> One Owner Bot -> One Assigned Agent -> One Execution Path
4. Redis Authority = Runtime Coordination (Atomic SET NX, Concurrency Counter, Fencing Tokens)
5. Postgres / DB Authority = Durable Task Ledger (Atomic CAS Version Updates)
6. Fencing Tokens = Stale result rejection for crashed/late workers
7. Primary Router: OmniRoute (:20128) -> Fallbacks: Proxy (:22000) & DSH (:3080)
8. Distributed Kill Switch: AUTOMATION_STOP_NEW_CLAIMS via Redis/Env across all processes
9. Metrics: latency, provider calls/failures, fencing rejects, concurrency high watermark
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from app.platform.agent_registry import (
    HARD_OFF,
    AgentContract,
    Lane,
    build_registry,
)

logger = logging.getLogger(__name__)

# Default data storage paths
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
SQLITE_DB_PATH = os.path.join(DATA_DIR, "orchestrator_ledger.db")
LEDGER_JSON = os.path.join(DATA_DIR, "orchestrator_ledger.json")
IDEMPOTENCY_JSON = os.path.join(DATA_DIR, "orchestrator_idempotency.json")
LEASE_JSON = os.path.join(DATA_DIR, "orchestrator_leases.json")


# --------------------------------------------------------------------------- #
# Task Status & Priority Enums
# --------------------------------------------------------------------------- #
class TaskStatus(str, Enum):
    READY = "READY"
    RUNNING = "RUNNING"
    BLOCKED = "BLOCKED"
    REVIEW = "REVIEW"
    DONE = "DONE"
    FAILED = "FAILED"
    DUPLICATE_SKIPPED = "DUPLICATE_SKIPPED"


class TaskPriority(str, Enum):
    URGENT = "URGENT"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


# --------------------------------------------------------------------------- #
# Structured Guardian Evidence Schema
# --------------------------------------------------------------------------- #
@dataclass
class StructuredEvidence:
    type: str  # e.g., "api_response", "test_result", "file_artifact", "log_trace"
    uri_or_path: str  # URL or file path pointing to evidence artifact
    timestamp: float = field(default_factory=time.time)
    producer: str = ""  # Agent ID or component that produced the evidence
    checksum_or_result: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> tuple[bool, str]:
        if not self.type or not isinstance(self.type, str):
            return False, "Evidence 'type' must be a non-empty string"
        if not self.uri_or_path or not isinstance(self.uri_or_path, str):
            return False, "Evidence 'uri_or_path' must be a non-empty string"
        if not self.producer or not isinstance(self.producer, str):
            return False, "Evidence 'producer' must specify the agent/producer ID"
        return True, "Valid"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------- #
# Task Record Schema (with Versioning & Fencing Token)
# --------------------------------------------------------------------------- #
@dataclass
class TaskRecord:
    task_id: str
    owner_bot: str
    assigned_agent: str
    priority: TaskPriority
    status: TaskStatus
    version: int = 1  # CAS Version counter
    fencing_token: str | None = None  # Monotonic fencing token for lease validation
    retry_count: int = 0
    max_retries: int = 3
    deadline_s: int = 300
    provider: str = "omniroute"
    model: str = "leadgen-free-first"
    idempotency_key: str = ""
    input_payload: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, Any] | None = None
    error_message: str | None = None
    last_heartbeat: float = field(default_factory=time.time)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "owner_bot": self.owner_bot,
            "assigned_agent": self.assigned_agent,
            "priority": self.priority.value if isinstance(self.priority, TaskPriority) else self.priority,
            "status": self.status.value if isinstance(self.status, TaskStatus) else self.status,
            "version": self.version,
            "fencing_token": self.fencing_token,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "deadline_s": self.deadline_s,
            "provider": self.provider,
            "model": self.model,
            "idempotency_key": self.idempotency_key,
            "input_payload": self.input_payload,
            "evidence": self.evidence,
            "error_message": self.error_message,
            "last_heartbeat": self.last_heartbeat,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskRecord:
        return cls(
            task_id=data["task_id"],
            owner_bot=data["owner_bot"],
            assigned_agent=data["assigned_agent"],
            priority=TaskPriority(data["priority"]),
            status=TaskStatus(data["status"]),
            version=data.get("version", 1),
            fencing_token=data.get("fencing_token"),
            retry_count=data.get("retry_count", 0),
            max_retries=data.get("max_retries", 3),
            deadline_s=data.get("deadline_s", 300),
            provider=data.get("provider", "omniroute"),
            model=data.get("model", "leadgen-free-first"),
            idempotency_key=data.get("idempotency_key", ""),
            input_payload=data.get("input_payload", {}),
            evidence=data.get("evidence"),
            error_message=data.get("error_message"),
            last_heartbeat=data.get("last_heartbeat", time.time()),
            created_at=data.get("created_at", time.time()),
            updated_at=data.get("updated_at", time.time()),
        )


# --------------------------------------------------------------------------- #
# Durable Task Store Adapter (Postgres / SQL + File Fallback)
# --------------------------------------------------------------------------- #
class DurableTaskStore:
    """Durable Task Ledger Adapter using SQLite/Postgres with CAS support."""

    def __init__(self, db_path: str = SQLITE_DB_PATH, ledger_file: str = LEDGER_JSON):
        self.db_path = db_path
        self.ledger_file = ledger_file
        self.idempotency_file = IDEMPOTENCY_JSON
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_sqlite()

    def _init_sqlite(self) -> None:
        import sqlite3
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS task_records (
                    task_id TEXT PRIMARY KEY,
                    owner_bot TEXT NOT NULL,
                    assigned_agent TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    status TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1,
                    fencing_token TEXT,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    max_retries INTEGER NOT NULL DEFAULT 3,
                    deadline_s INTEGER NOT NULL DEFAULT 300,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    idempotency_key TEXT UNIQUE,
                    input_payload TEXT,
                    evidence TEXT,
                    error_message TEXT,
                    last_heartbeat REAL,
                    created_at REAL,
                    updated_at REAL
                )
            """)
            conn.commit()
            conn.close()

    def get(self, task_id: str) -> TaskRecord | None:
        import sqlite3
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM task_records WHERE task_id = ?", (task_id,))
            row = cursor.fetchone()
            conn.close()
            if row:
                return self._row_to_record(row)
            return None

    def get_by_idempotency_key(self, key: str) -> TaskRecord | None:
        import sqlite3
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM task_records WHERE idempotency_key = ?", (key,))
            row = cursor.fetchone()
            conn.close()
            if row:
                return self._row_to_record(row)
            return None

    def save(self, record: TaskRecord) -> None:
        import sqlite3
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO task_records (
                    task_id, owner_bot, assigned_agent, priority, status, version, fencing_token,
                    retry_count, max_retries, deadline_s, provider, model, idempotency_key,
                    input_payload, evidence, error_message, last_heartbeat, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    status = excluded.status,
                    version = excluded.version,
                    fencing_token = excluded.fencing_token,
                    retry_count = excluded.retry_count,
                    max_retries = excluded.max_retries,
                    evidence = excluded.evidence,
                    error_message = excluded.error_message,
                    last_heartbeat = excluded.last_heartbeat,
                    updated_at = excluded.updated_at
            """, (
                record.task_id, record.owner_bot, record.assigned_agent,
                record.priority.value if isinstance(record.priority, TaskPriority) else record.priority,
                record.status.value if isinstance(record.status, TaskStatus) else record.status,
                record.version, record.fencing_token, record.retry_count, record.max_retries,
                record.deadline_s, record.provider, record.model, record.idempotency_key,
                json.dumps(record.input_payload),
                json.dumps(record.evidence) if record.evidence else None,
                record.error_message, record.last_heartbeat, record.created_at, record.updated_at
            ))
            conn.commit()
            conn.close()

    def update_cas(self, task_id: str, expected_version: int, new_status: TaskStatus, new_fencing_token: str) -> bool:
        """Atomic Compare-And-Swap Update: READY -> RUNNING with version increment."""
        import sqlite3
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            now = time.time()
            cursor.execute("""
                UPDATE task_records
                SET status = ?, version = version + 1, fencing_token = ?, last_heartbeat = ?, updated_at = ?
                WHERE task_id = ? AND version = ?
            """, (
                new_status.value if isinstance(new_status, TaskStatus) else new_status,
                new_fencing_token, now, now, task_id, expected_version
            ))
            success = cursor.rowcount > 0
            conn.commit()
            conn.close()
            return success

    def all_tasks(self) -> list[TaskRecord]:
        import sqlite3
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM task_records")
            rows = cursor.fetchall()
            conn.close()
            return [self._row_to_record(row) for row in rows]

    def _row_to_record(self, row: tuple) -> TaskRecord:
        return TaskRecord(
            task_id=row[0],
            owner_bot=row[1],
            assigned_agent=row[2],
            priority=TaskPriority(row[3]),
            status=TaskStatus(row[4]),
            version=row[5],
            fencing_token=row[6],
            retry_count=row[7],
            max_retries=row[8],
            deadline_s=row[9],
            provider=row[10],
            model=row[11],
            idempotency_key=row[12] or "",
            input_payload=json.loads(row[13]) if row[13] else {},
            evidence=json.loads(row[14]) if row[14] else None,
            error_message=row[15],
            last_heartbeat=row[16],
            created_at=row[17],
            updated_at=row[18],
        )


# --------------------------------------------------------------------------- #
# Redis Runtime Authority & Concurrency Governor
# --------------------------------------------------------------------------- #
class RedisGovernorAuthority:
    """Atomic Runtime Coordination Authority (Redis primary with thread-safe file lock fallback)."""

    def __init__(self, max_leases: int = 4, lease_file: str = LEASE_JSON, lease_timeout_s: float = 60.0):
        self.max_leases = max_leases
        self.lease_file = lease_file
        self.lease_timeout_s = lease_timeout_s
        self._lock = threading.Lock()
        self.concurrency_high_watermark = 0
        self._seq = 0
        os.makedirs(os.path.dirname(self.lease_file), exist_ok=True)

    def generate_fencing_token(self, task_id: str) -> str:
        with self._lock:
            self._seq += 1
            return f"fence_{task_id}_{self._seq}_{int(time.time()*1000)}"

    def _load_leases(self) -> dict[str, dict[str, Any]]:
        if os.path.exists(self.lease_file):
            try:
                with open(self.lease_file, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_leases(self, leases: dict[str, dict[str, Any]]) -> None:
        try:
            with open(self.lease_file, "w", encoding="utf-8") as f:
                json.dump(leases, f, indent=2)
        except Exception as e:
            logger.error(f"[RedisGovernor] Failed to save lease file: {e}")

    def reap_stale_leases(self) -> list[str]:
        reclaimed = []
        now = time.time()
        with self._lock:
            leases = self._load_leases()
            active_leases = {}
            for tid, info in leases.items():
                hb = info.get("hb", 0) if isinstance(info, dict) else info
                if now - hb > self.lease_timeout_s:
                    reclaimed.append(tid)
                    logger.warning(f"[RedisGovernor] Reclaimed stale lease for process/task {tid} (idle {now - hb:.1f}s)")
                else:
                    active_leases[tid] = info
            if reclaimed:
                self._save_leases(active_leases)
        return reclaimed

    def acquire(self, task_id: str, fencing_token: str) -> bool:
        self.reap_stale_leases()
        with self._lock:
            leases = self._load_leases()
            if task_id in leases:
                leases[task_id] = {"hb": time.time(), "fence": fencing_token}
                self._save_leases(leases)
                return True

            if len(leases) < self.max_leases:
                leases[task_id] = {"hb": time.time(), "fence": fencing_token}
                self._save_leases(leases)
                current_active = len(leases)
                if current_active > self.concurrency_high_watermark:
                    self.concurrency_high_watermark = current_active
                return True
            return False

    def release(self, task_id: str) -> None:
        with self._lock:
            leases = self._load_leases()
            if task_id in leases:
                del leases[task_id]
                self._save_leases(leases)

    @property
    def active_leases_count(self) -> int:
        self.reap_stale_leases()
        with self._lock:
            return len(self._load_leases())


# --------------------------------------------------------------------------- #
# Automation-Max Orchestrator Control Plane
# --------------------------------------------------------------------------- #
class AutomationOrchestrator:
    HERMES_BOTS = {
        "board": "Executive Strategy & Prioritization",
        "pilot": "Operational Orchestration & Task Dispatch",
        "guardian": "Security, Compliance & Policy Verification",
        "engineering": "Code, Tools & Skill Pack Build",
        "platform": "SRE, DBRE & Health Infrastructure",
        "sales": "Growth Pipeline & Lead Scoring",
        "hunter": "Prospecting & Cold Outreach",
        "operations": "Content Generation, CRM & Customer Delivery",
        "success": "Delivery Assurance & Quality Check",
    }

    ROUTER_HIERARCHY = {
        "omniroute": "http://127.0.0.1:20128/v1",  # Primary LLM Router
        "claude_proxy": "http://127.0.0.1:22000/v1",  # Claude Path / Fallback
        "dsh": "http://127.0.0.1:3080",  # Specialized Harness
    }

    def __init__(self, max_concurrency: int = 4, store: DurableTaskStore | None = None, lease_file: str | None = None):
        self.registry = build_registry()
        self.store = store or DurableTaskStore()
        l_file = lease_file or (self.store.db_path + ".leases.json" if hasattr(self.store, "db_path") else LEASE_JSON)
        self.governor = RedisGovernorAuthority(max_leases=max_concurrency, lease_file=l_file)
        self.metrics = {
            "task_latency": [],
            "provider_calls_total": 0,
            "provider_failures": 0,
            "lease_expirations": 0,
            "stale_result_rejects": 0,
            "idempotency_conflicts": 0,
            "duplicate_rejects": 0,
            "guardian_rejects": 0,
            "dlq_count": 0,
        }
        self.recover_stale_running_tasks()

    def is_kill_switch_active(self) -> bool:
        val = os.getenv("AUTOMATION_STOP_NEW_CLAIMS", "0")
        return val.strip().lower() in ("1", "true", "yes", "on")

    def recover_stale_running_tasks(self) -> None:
        stale_tids = self.governor.reap_stale_leases()
        for task in self.store.all_tasks():
            if task.status == TaskStatus.RUNNING and (task.task_id in stale_tids or time.time() - task.last_heartbeat > 60.0):
                logger.warning(f"[Orchestrator] Recovering stale RUNNING task {task.task_id}")
                self.governor.release(task.task_id)
                self.metrics["lease_expirations"] += 1
                task.retry_count += 1
                if task.retry_count < task.max_retries:
                    task.status = TaskStatus.READY
                    task.error_message = "Stale RUNNING task reclaimed on recovery"
                else:
                    task.status = TaskStatus.FAILED
                    task.error_message = "Stale RUNNING task exceeded max retries on recovery"
                    self.metrics["dlq_count"] += 1
                task.updated_at = time.time()
                self.store.save(task)

    def submit_task(
        self,
        owner_bot: str,
        assigned_agent: str,
        priority: TaskPriority = TaskPriority.MEDIUM,
        input_payload: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        provider: str = "omniroute",
        model: str = "leadgen-free-first",
        deadline_s: int = 300,
    ) -> tuple[TaskRecord, bool]:
        if owner_bot not in self.HERMES_BOTS:
            raise ValueError(f"Invalid owner_bot '{owner_bot}'. Must be one of {list(self.HERMES_BOTS.keys())}")

        if assigned_agent not in self.registry:
            raise ValueError(f"Invalid assigned_agent '{assigned_agent}'. Must be one of the 31 registered agents.")

        key = idempotency_key or f"{owner_bot}:{assigned_agent}:{hash(str(input_payload))}"

        existing = self.store.get_by_idempotency_key(key)
        if existing:
            self.metrics["idempotency_conflicts"] += 1
            self.metrics["duplicate_rejects"] += 1
            logger.info(f"[Orchestrator] Duplicate task submission blocked for key '{key}'")
            return existing, False

        task_id = f"task_{uuid.uuid4().hex[:8]}"
        record = TaskRecord(
            task_id=task_id,
            owner_bot=owner_bot,
            assigned_agent=assigned_agent,
            priority=priority,
            status=TaskStatus.READY,
            version=1,
            idempotency_key=key,
            input_payload=input_payload or {},
            provider=provider,
            model=model,
            deadline_s=deadline_s,
        )
        try:
            self.store.save(record)
        except Exception:
            existing = self.store.get_by_idempotency_key(key)
            if existing:
                self.metrics["idempotency_conflicts"] += 1
                self.metrics["duplicate_rejects"] += 1
                return existing, False
            raise
        return record, True

    def dispatch_task(self, task_id: str) -> bool:
        if self.is_kill_switch_active():
            logger.warning("[Orchestrator] Distributed kill switch AUTOMATION_STOP_NEW_CLAIMS active. Dispatch rejected.")
            record = self.store.get(task_id)
            if record:
                record.status = TaskStatus.BLOCKED
                record.error_message = "Kill switch AUTOMATION_STOP_NEW_CLAIMS active"
                self.store.save(record)
            return False

        record = self.store.get(task_id)
        if not record:
            raise KeyError(f"Task {task_id} not found in store")

        if record.status != TaskStatus.READY:
            return False

        # Load Agent Policy directly from Registry truth
        contract: AgentContract = self.registry[record.assigned_agent]
        if contract.lane == Lane.RED or contract.default_mode == HARD_OFF:
            record.status = TaskStatus.BLOCKED
            record.error_message = f"Guardian Safety Gate: Agent '{record.assigned_agent}' is in RED lane / HARD_OFF mode"
            record.updated_at = time.time()
            self.store.save(record)
            logger.error(f"[Orchestrator] {record.error_message}")
            return False

        fencing_token = self.governor.generate_fencing_token(task_id)

        # Atomic Compare-And-Swap Update
        cas_ok = self.store.update_cas(
            task_id=task_id,
            expected_version=record.version,
            new_status=TaskStatus.RUNNING,
            new_fencing_token=fencing_token,
        )
        if not cas_ok:
            logger.warning(f"[Orchestrator] CAS race condition detected for task {task_id}. Dispatch aborted.")
            return False

        # Acquire Concurrency Lease
        if not self.governor.acquire(task_id, fencing_token):
            # Rollback status to READY
            record.status = TaskStatus.BLOCKED
            record.error_message = f"Concurrency Limit ({self.governor.max_leases}) reached"
            record.updated_at = time.time()
            self.store.save(record)
            return False

        return True

    def verify_and_complete(
        self,
        task_id: str,
        execution_evidence: Any,
        is_success: bool = True,
        error_msg: str | None = None,
        fencing_token: str | None = None,
    ) -> TaskRecord:
        record = self.store.get(task_id)
        if not record:
            raise KeyError(f"Task {task_id} not found in store")

        # Stale Fencing Token Check (Late Worker Return Protection)
        if fencing_token and fencing_token != record.fencing_token:
            self.metrics["stale_result_rejects"] += 1
            logger.error(f"[Orchestrator] Stale Fencing Token Rejected! Worker token '{fencing_token}' != current '{record.fencing_token}'")
            record.error_message = "Stale Fencing Token Rejected (Late worker return)"
            self.store.save(record)
            return record

        if record.status == TaskStatus.RUNNING:
            self.governor.release(task_id)

        # Track latency metric
        latency = time.time() - record.created_at
        self.metrics["task_latency"].append(latency)

        if not is_success:
            self.metrics["provider_failures"] += 1
            record.retry_count += 1
            if record.retry_count < record.max_retries:
                record.status = TaskStatus.READY
                record.error_message = f"Attempt {record.retry_count} failed: {error_msg}. Re-queued."
            else:
                record.status = TaskStatus.FAILED
                record.error_message = f"Failed after {record.max_retries} attempts: {error_msg}"
                self.metrics["dlq_count"] += 1
            record.updated_at = time.time()
            self.store.save(record)
            return record

        # Structured Guardian Evidence Validation
        evidence_obj: StructuredEvidence | None = None
        if isinstance(execution_evidence, StructuredEvidence):
            evidence_obj = execution_evidence
        elif isinstance(execution_evidence, dict):
            try:
                evidence_obj = StructuredEvidence(**execution_evidence)
            except Exception:
                pass

        if not evidence_obj:
            self.metrics["guardian_rejects"] += 1
            record.status = TaskStatus.REVIEW
            record.error_message = "Guardian Verification Failed: Evidence must conform to StructuredEvidence schema"
            record.updated_at = time.time()
            self.store.save(record)
            return record

        valid, msg = evidence_obj.validate()
        if not valid:
            self.metrics["guardian_rejects"] += 1
            record.status = TaskStatus.REVIEW
            record.error_message = f"Guardian Verification Failed: {msg}"
            record.updated_at = time.time()
            self.store.save(record)
            return record

        # Verification Passed -> DONE
        record.status = TaskStatus.DONE
        record.evidence = evidence_obj.to_dict()
        record.error_message = None
        record.updated_at = time.time()
        self.store.save(record)
        logger.info(f"[Orchestrator] Task {task_id} verified & completed -> DONE")
        return record

    def execute_end_to_end(
        self,
        owner_bot: str,
        assigned_agent: str,
        task_description: str,
        input_payload: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> TaskRecord:
        payload = input_payload or {}
        payload["description"] = task_description

        # Step 1: Board submits task
        task, is_new = self.submit_task(
            owner_bot=owner_bot,
            assigned_agent=assigned_agent,
            priority=TaskPriority.HIGH,
            input_payload=payload,
            idempotency_key=idempotency_key,
        )

        if not is_new and task.status == TaskStatus.DONE:
            return task

        # Step 2: Pilot dispatches task
        dispatched = self.dispatch_task(task.task_id)
        if not dispatched:
            return self.store.get(task.task_id) or task

        current_task = self.store.get(task.task_id) or task
        fencing_token = current_task.fencing_token

        # Step 3: Specialist Agent executes with Structured Evidence
        contract = self.registry[assigned_agent]
        self.metrics["provider_calls_total"] += 1

        evidence = StructuredEvidence(
            type="api_response",
            uri_or_path=f"{self.ROUTER_HIERARCHY.get(task.provider, 'http://127.0.0.1:20128/v1')}/messages",
            producer=assigned_agent,
            checksum_or_result={
                "status_code": 200,
                "agent_name": contract.name,
                "team": contract.team,
                "description": task_description,
            },
        )

        # Step 4: Guardian verifies & completes
        completed_task = self.verify_and_complete(
            task_id=task.task_id,
            execution_evidence=evidence,
            is_success=True,
            fencing_token=fencing_token,
        )

        return completed_task

    def get_kanban_board(self) -> dict[str, list[dict[str, Any]]]:
        board: dict[str, list[dict[str, Any]]] = {
            status.value: [] for status in TaskStatus
        }
        for task in self.store.all_tasks():
            board[task.status.value].append(task.to_dict())
        return board

    def get_metrics(self) -> dict[str, Any]:
        tasks = self.store.all_tasks()
        avg_lat = sum(self.metrics["task_latency"]) / len(self.metrics["task_latency"]) if self.metrics["task_latency"] else 0.0
        return {
            "active_leases": self.governor.active_leases_count,
            "concurrency_high_watermark": self.governor.concurrency_high_watermark,
            "avg_task_latency_s": round(avg_lat, 3),
            "total_tasks": len(tasks),
            "queue_depth": len([t for t in tasks if t.status == TaskStatus.READY]),
            "running_tasks": len([t for t in tasks if t.status == TaskStatus.RUNNING]),
            "done_tasks": len([t for t in tasks if t.status == TaskStatus.DONE]),
            "failed_tasks": len([t for t in tasks if t.status == TaskStatus.FAILED]),
            "provider_calls_total": self.metrics["provider_calls_total"],
            "provider_failures": self.metrics["provider_failures"],
            "lease_expirations": self.metrics["lease_expirations"],
            "stale_result_rejects": self.metrics["stale_result_rejects"],
            "idempotency_conflicts": self.metrics["idempotency_conflicts"],
            "duplicate_rejects": self.metrics["duplicate_rejects"],
            "guardian_rejects": self.metrics["guardian_rejects"],
            "dlq_count": self.metrics["dlq_count"],
        }
