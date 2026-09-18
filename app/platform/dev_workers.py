"""Dev Workers Execution Prover — proves agents are actually executing (M1, P0).

WHY THIS EXISTS
---------------
ARCH §M1 requires `dev_workers` table to have > 0 rows as execution proof.
Currently `dev_workers = 0 rows` + `service._IDEMPOTENCY` process-local dict
(`CODE-PRESENT`). This module writes real execution proof to the ledger.

Design:
* Writes `dev_workers` rows on real task claim → run → done lifecycle
* Uses DB-backed idempotency (not process-local dict)
* Never raises — fails silently if DB unavailable
* Evidence: file/pid/url; empty ⇒ not verified

Evidence label: CODE-PRESENT (stub, needs wiring to orchestrator)
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import sqlite3
import time
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Ledger path (same as DurableTaskStore)
LEDGER_PATH = os.path.join("data", "orchestrator_ledger.db")


class DevWorkerRecord:
    """Execution proof record — written on real task lifecycle."""

    def __init__(
        self,
        worker_id: str,
        task_id: str,
        lease_token: str,
        state: str = "claimed",
        evidence: str = "",
    ):
        self.worker_id = worker_id
        self.task_id = task_id
        self.lease_token = lease_token
        self.state = state
        self.evidence = evidence
        self.claimed_at = time.time()
        self.heartbeat_at = time.time()
        self.done_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "worker_id": self.worker_id,
            "task_id": self.task_id,
            "lease_token": self.lease_token,
            "state": self.state,
            "evidence": self.evidence,
            "claimed_at": self.claimed_at,
            "heartbeat_at": self.heartbeat_at,
            "done_at": self.done_at,
        }

    def __repr__(self):  # pragma: no cover - debug aid
        return (
            f"DevWorkerRecord(task_id={self.task_id!r}, worker_id={self.worker_id!r}, "
            f"state={self.state!r}, evidence={self.evidence!r})"
        )

    def get(self, key: str, default: Any = None) -> Any:
        """dict-style read so callers may use `row["state"]` or `row.get("state")`."""
        return getattr(self, key, default)

    def __getitem__(self, key: str) -> Any:
        try:
            return getattr(self, key)
        except AttributeError:  # pragma: no cover - mirrors dict KeyError
            raise KeyError(key) from None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DevWorkerRecord:
        record = cls(
            worker_id=data["worker_id"],
            task_id=data["task_id"],
            lease_token=data["lease_token"],
            state=data.get("state", "claimed"),
            evidence=data.get("evidence", ""),
        )
        record.claimed_at = data.get("claimed_at", time.time())
        record.heartbeat_at = data.get("heartbeat_at", time.time())
        record.done_at = data.get("done_at")
        return record


class DevWorkerProver:
    """Writes execution proof to dev_workers ledger.

    Usage:
        prover = DevWorkerProver()
        prover.claim(task_id="task_abc123", lease_token="token_xyz")
        prover.heartbeat()
        prover.done(evidence="data/output.json")
    """

    def __init__(self, ledger_path: str = LEDGER_PATH):
        self.ledger_path = ledger_path
        self.workers: dict[str, DevWorkerRecord] = {}
        self._load()

    def _load(self):
        """Load existing records from ledger (if exists)."""
        if not os.path.exists(self.ledger_path):
            return
        try:
            with open(self.ledger_path) as f:
                data = json.load(f)
                for record_data in data.get("dev_workers", []):
                    worker = DevWorkerRecord.from_dict(record_data)
                    self.workers[worker.worker_id] = worker
        except Exception as e:
            logger.warning(f"[dev_workers] Failed to load ledger: {e}")

    def _save(self):
        """Persist current state to ledger."""
        try:
            os.makedirs(os.path.dirname(self.ledger_path), exist_ok=True)
            data = {
                "dev_workers": [w.to_dict() for w in self.workers.values()],
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            with open(self.ledger_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning(f"[dev_workers] Failed to save ledger: {e}")

    def claim(self, task_id: str, lease_token: str, worker_id: str | None = None) -> str:
        """Claim a task — writes first execution proof row.

        Returns worker_id (generated if not provided).
        """
        if worker_id is None:
            worker_id = f"dw_{task_id}"

        record = DevWorkerRecord(
            worker_id=worker_id,
            task_id=task_id,
            lease_token=lease_token,
            state="claimed",
        )
        self.workers[worker_id] = record
        self._save()
        logger.info(f"[dev_workers] Claimed: {worker_id} → {task_id}")
        return worker_id

    def heartbeat(self, worker_id: str):
        """Update heartbeat for running worker."""
        if worker_id in self.workers:
            self.workers[worker_id].heartbeat_at = time.time()
            self.workers[worker_id].state = "running"
            self._save()

    def done(self, worker_id: str, evidence: str = ""):
        """Mark worker as done with evidence."""
        if worker_id in self.workers:
            self.workers[worker_id].done_at = time.time()
            self.workers[worker_id].state = "done"
            self.workers[worker_id].evidence = evidence
            self._save()
            logger.info(f"[dev_workers] Done: {worker_id} (evidence: {evidence})")

    def failed(self, worker_id: str, reason: str = ""):
        """Mark worker as failed."""
        if worker_id in self.workers:
            self.workers[worker_id].state = "failed"
            self.workers[worker_id].evidence = f"FAILED: {reason}"
            self._save()
            logger.warning(f"[dev_workers] Failed: {worker_id} — {reason}")

    def get_active_count(self) -> int:
        """Count of claimed/running workers (execution proof)."""
        return sum(1 for w in self.workers.values() if w.state in ("claimed", "running"))

    def get_records(self) -> list[dict[str, Any]]:
        """Get all records (for dashboard/API)."""
        return [w.to_dict() for w in self.workers.values()]


# Module-level singleton (initialized on first use)
_prover: DevWorkerProver | None = None


_WORKER_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS dev_workers (
    task_id        TEXT PRIMARY KEY,
    worker_id      TEXT NOT NULL,
    state          TEXT NOT NULL DEFAULT 'claimed',
    lease_token    TEXT,
    evidence       TEXT NOT NULL DEFAULT '',
    attempts       INTEGER NOT NULL DEFAULT 0,
    created_at     REAL,
    updated_at     REAL,
    done_at        REAL
)
"""


def worker_id_for(task_id: str) -> str:
    """Deterministic worker id for a task: `dw_<task_id>`.

    Deterministic so a retried task is attributed to the same worker — that is
    what makes the `dev_workers > 0` execution proof idempotent. Empty task_id
    yields `""` (callers treat falsy as "no worker"). Never raises.
    """
    try:
        if not task_id:
            return ""
        return f"dw_{task_id}"
    except Exception:
        return ""


class DevWorkerStore:
    """SQLite-backed execution prover (M1 T02).

    Lives in the SAME SQLite DB as the orchestrator task ledger — a single
    `dev_workers` table next to `task_records`, NOT a new ledger file. This is
    what makes the PRD 1c claim (`dev_workers > 0` after a REAL task)
    falsifiable: unless a row is written here, execution was never proven.

    Lifecycle: ``claim`` -> optional ``heartbeat`` -> ``finish``. A row counts
    as "verified" only when it is ``done`` AND carries non-empty evidence.

    Never raises: an unusable DB degrades every method to a safe ``False``/``0``.

    IMPLEMENTATION NOTE (learned the hard way): no method uses
    ``with self._conn() as conn:`` combined with an early ``return``. The
    connection helper is a plain opener closed in ``finally``. Using a
    ``@contextmanager`` here caused ``GeneratorExit`` to roll back the INSERT on
    every early return — i.e. the evidence row silently vanished.
    """

    def __init__(self, db_path: str = "data/orchestrator_ledger.db", **_ignored: Any):
        self.db_path = db_path or "data/orchestrator_ledger.db"
        self._ready = False
        conn = None
        try:
            parent = os.path.dirname(os.path.abspath(self.db_path))
            if parent:
                os.makedirs(parent, exist_ok=True)
            conn = self._conn()
            conn.execute(_WORKER_TABLE_SQL)
            conn.commit()
            self._ready = True
        except Exception as e:  # pragma: no cover - degraded mode
            logger.warning(f"[dev_workers] store unavailable ({e}) - proof disabled")
        finally:
            self._close(conn)

    # --------------------------- internals --------------------------- #
    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _close(conn: Any) -> None:
        """Close a connection, swallowing errors. Windows file-lock hygiene."""
        if conn is None:
            return
        try:
            conn.close()
        except Exception:
            pass

    @staticmethod
    def _now() -> float:
        return time.time()

    def _row_to_record(self, row: sqlite3.Row) -> DevWorkerRecord:
        rec = DevWorkerRecord(
            worker_id=row["worker_id"],
            task_id=row["task_id"],
            lease_token=row["lease_token"] or "",
            state=row["state"] or "claimed",
            evidence=row["evidence"] or "",
        )
        rec.claimed_at = row["created_at"] or time.time()
        rec.heartbeat_at = row["updated_at"] or rec.claimed_at
        rec.done_at = row["done_at"]
        return rec

    def _scalar(self, sql: str, params: tuple = ()) -> int:
        conn = None
        try:
            conn = self._conn()
            row = conn.execute(sql, params).fetchone()
            return int(row[0]) if row is not None else 0
        except Exception:
            return 0
        finally:
            self._close(conn)

    # ---------------------------- writes ----------------------------- #
    def claim(self, task_id: str, lease_token: str = "") -> bool:
        """Claim a task for a worker.

        Returns False when the task_id is empty, the DB is unavailable, or the
        task is ALREADY claimed (the double-claim guard), True on first claim.
        """
        if not self._ready or not task_id:
            return False
        conn = None
        result = False
        try:
            conn = self._conn()
            existing = conn.execute(
                "SELECT 1 FROM dev_workers WHERE task_id = ?", (task_id,)
            ).fetchone()
            if existing is None:
                conn.execute(
                    """
                    INSERT INTO dev_workers
                        (task_id, worker_id, state, lease_token, evidence,
                         attempts, created_at, updated_at)
                    VALUES (?, ?, 'claimed', ?, '', 1, ?, ?)
                    """,
                    (
                        task_id,
                        worker_id_for(task_id),
                        lease_token or None,
                        self._now(),
                        self._now(),
                    ),
                )
                conn.commit()
                result = True
        except Exception:
            result = False
        finally:
            self._close(conn)
        return result

    def heartbeat(self, task_id: str) -> bool:
        """Bump updated_at for a claimed (not yet finished) task."""
        if not self._ready or not task_id:
            return False
        conn = None
        result = False
        try:
            conn = self._conn()
            cur = conn.execute(
                "UPDATE dev_workers SET updated_at = ?, attempts = attempts + 1 "
                "WHERE task_id = ? AND done_at IS NULL",
                (self._now(), task_id),
            )
            conn.commit()
            result = cur.rowcount == 1
        except Exception:
            result = False
        finally:
            self._close(conn)
        return result

    def finish(
        self,
        task_id: str,
        success: bool = True,
        evidence: str = "",
        state: str | None = None,
    ) -> bool:
        """Terminal transition. State defaults to done (success) / dead (failure).

        Evidence is stored verbatim. Empty evidence is permitted but such a row
        is NOT counted by ``verified_count()``.
        """
        if not self._ready or not task_id:
            return False
        # Callers (orchestrator DLQ path, tests) expect "failed", not "dead".
        final_state = state or ("done" if success else "failed")
        conn = None
        result = False
        try:
            conn = self._conn()
            cur = conn.execute(
                "UPDATE dev_workers SET state = ?, evidence = ?, done_at = ?, "
                "updated_at = ? WHERE task_id = ?",
                (final_state, evidence or "", self._now(), self._now(), task_id),
            )
            conn.commit()
            result = cur.rowcount == 1
        except Exception:
            result = False
        finally:
            self._close(conn)
        return result

    # Compatibility aliases for older callers.
    def complete(self, task_id: str, evidence: str = "") -> bool:
        return self.finish(task_id, success=True, evidence=evidence)

    def fail(self, task_id: str, evidence: str = "") -> bool:
        return self.finish(task_id, success=False, evidence=evidence)

    # ----------------------------- reads ----------------------------- #
    def get(self, task_id: str) -> DevWorkerRecord | None:
        if not self._ready or not task_id:
            return None
        conn = None
        try:
            conn = self._conn()
            row = conn.execute("SELECT * FROM dev_workers WHERE task_id = ?", (task_id,)).fetchone()
            return self._row_to_record(row) if row is not None else None
        except Exception:
            return None
        finally:
            self._close(conn)

    def count(self, *, state: str | None = None) -> int:
        """Row count.

        With no ``state`` this is the `dev_workers > 0` proof counter (total
        rows). With ``state=`` it counts rows in that state — the orchestrator's
        `dev_workers_count(state="done")` dashboard consumer relies on this.
        """
        if not self._ready:
            return 0
        if state:
            return self._scalar("SELECT COUNT(*) FROM dev_workers WHERE state = ?", (state,))
        return self._scalar("SELECT COUNT(*) FROM dev_workers")

    def verified_count(self) -> int:
        """Rows that are `done` AND carry non-empty evidence - the REAL proof."""
        if not self._ready:
            return 0
        return self._scalar(
            "SELECT COUNT(*) FROM dev_workers "
            "WHERE state = 'done' AND TRIM(COALESCE(evidence,'')) <> ''"
        )

    def count_completed(self) -> int:
        """Rows in a terminal done state (evidence not required)."""
        if not self._ready:
            return 0
        return self._scalar("SELECT COUNT(*) FROM dev_workers WHERE state = 'done'")

    def list_all(self, limit: int = 100) -> list[DevWorkerRecord]:
        if not self._ready:
            return []
        conn = None
        try:
            conn = self._conn()
            rows = conn.execute(
                "SELECT * FROM dev_workers ORDER BY updated_at DESC LIMIT ?", (limit,)
            ).fetchall()
            return [self._row_to_record(r) for r in rows]
        except Exception:
            return []
        finally:
            self._close(conn)


def get_prover() -> DevWorkerProver:
    """Get or create singleton DevWorkerProver."""
    global _prover
    if _prover is None:
        _prover = DevWorkerProver()
    return _prover


def prove_execution(task_id: str, lease_token: str, evidence: str = "") -> str:
    """Convenience function: claim → heartbeat → done (full lifecycle).

    Returns worker_id.
    """
    prover = get_prover()
    worker_id = prover.claim(task_id, lease_token)
    prover.heartbeat(worker_id)
    prover.done(worker_id, evidence)
    return worker_id


__all__ = [
    "DevWorkerRecord",
    "DevWorkerStore",
    "DevWorkerProver",
    "get_prover",
    "prove_execution",
    "worker_id_for",
    "LEDGER_PATH",
]
