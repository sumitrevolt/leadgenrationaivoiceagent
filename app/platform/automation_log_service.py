"""Centralized automation log write + read service (ADR-064, 2026-07-09).

Every automation/agent/job writes logs through this service. Falls back to
JSONL file if DB is unavailable — never crashes the scheduler.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_JSONL_PATH = os.path.join("data", "automation_logs.jsonl")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log_event(
    *,
    client_id: str = "",
    job_type: str,
    status: str = "success",
    started_at: str = "",
    finished_at: str = "",
    duration_ms: int | None = None,
    input_summary: str = "",
    output_summary: str = "",
    error_message: str = "",
    retry_count: int = 0,
    next_retry_at: str = "",
    evidence_url: str = "",
    triggered_by: str = "system",
    meta_json: dict[str, Any] | None = None,
) -> str:
    """Write an automation log entry. Returns the log ID (empty string on failure)."""
    log_id = str(uuid.uuid4())
    finished = finished_at or _now()
    try:
        from app.models.automation_log import AutomationLog
        from app.models.base import get_db_session

        with get_db_session() as db:
            entry = AutomationLog(
                id=log_id,
                client_id=str(client_id or "").strip()[:36] or None,
                job_type=str(job_type)[:100],
                status=str(status)[:20],
                started_at=str(started_at)[:50] if started_at else None,
                finished_at=finished[:50],
                duration_ms=duration_ms,
                input_summary=str(input_summary)[:2000] if input_summary else None,
                output_summary=str(output_summary)[:2000] if output_summary else None,
                error_message=str(error_message)[:2000] if error_message else None,
                retry_count=int(retry_count or 0),
                next_retry_at=str(next_retry_at)[:50] if next_retry_at else None,
                evidence_url=str(evidence_url)[:500] if evidence_url else None,
                triggered_by=str(triggered_by)[:50],
                meta_json=(
                    json.dumps(meta_json, ensure_ascii=False, default=str)[:4000]
                    if meta_json
                    else None
                ),
                created_at=datetime.utcnow(),
            )
            db.add(entry)
            db.commit()
            return log_id
    except Exception as exc:
        logger.debug("AutomationLog DB write failed, falling back to JSONL: %s", exc)
        # Fallback to JSONL file
        try:
            os.makedirs(os.path.dirname(_JSONL_PATH), exist_ok=True)
            rec = {
                "id": log_id,
                "client_id": client_id,
                "job_type": job_type,
                "status": status,
                "started_at": started_at,
                "finished_at": finished,
                "duration_ms": duration_ms,
                "input_summary": input_summary,
                "output_summary": output_summary,
                "error_message": error_message,
                "retry_count": retry_count,
                "next_retry_at": next_retry_at,
                "evidence_url": evidence_url,
                "triggered_by": triggered_by,
                "meta_json": meta_json,
                "created_at": _now(),
            }
            with open(_JSONL_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
            return log_id
        except Exception as e2:
            logger.warning("AutomationLog JSONL fallback also failed: %s", e2)
        return ""


def get_logs(
    *,
    client_id: str = "",
    job_type: str = "",
    status: str = "",
    days: int = 7,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Read automation logs with optional filters."""
    try:
        from app.models.automation_log import AutomationLog
        from app.models.base import get_db_session

        with get_db_session() as db:
            q = db.query(AutomationLog)
            if client_id:
                q = q.filter(AutomationLog.client_id == str(client_id))
            if job_type:
                q = q.filter(AutomationLog.job_type == str(job_type))
            if status:
                q = q.filter(AutomationLog.status == str(status))
            if days > 0:
                cutoff = datetime.utcnow() - timedelta(days=days)
                q = q.filter(AutomationLog.created_at >= cutoff)
            rows = q.order_by(AutomationLog.created_at.desc()).limit(limit).all()
            return [_row_to_dict(r) for r in rows]
    except Exception:
        return _read_jsonl(client_id, job_type, status, days, limit)


def _row_to_dict(r: Any) -> dict[str, Any]:
    return {
        "id": r.id,
        "client_id": r.client_id,
        "job_type": r.job_type,
        "status": r.status,
        "started_at": r.started_at,
        "finished_at": r.finished_at,
        "duration_ms": r.duration_ms,
        "input_summary": r.input_summary,
        "output_summary": r.output_summary,
        "error_message": r.error_message,
        "retry_count": r.retry_count,
        "next_retry_at": r.next_retry_at,
        "evidence_url": r.evidence_url,
        "triggered_by": r.triggered_by,
        "meta_json": r.meta_json,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _read_jsonl(
    client_id: str = "", job_type: str = "", status: str = "", days: int = 7, limit: int = 200
) -> list[dict[str, Any]]:
    if not os.path.isfile(_JSONL_PATH):
        return []
    rows: list[dict[str, Any]] = []
    try:
        with open(_JSONL_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if client_id and rec.get("client_id") != client_id:
                    continue
                if job_type and rec.get("job_type") != job_type:
                    continue
                if status and rec.get("status") != status:
                    continue
                if (
                    days > 0
                    and str(rec.get("created_at") or "")[:10]
                    < (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
                ):
                    continue
                rows.append(rec)
        rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
        return rows[:limit]
    except Exception:
        return []


def has_run_today(client_id: str, job_type: str) -> bool:
    """Check if a job already ran for this client+job today (idempotency guard)."""
    today = datetime.now(timezone.utc).date().isoformat()
    today_start = (
        datetime.now(timezone.utc)
        .replace(hour=0, minute=0, second=0, microsecond=0)
        .replace(tzinfo=None)
    )
    try:
        from app.models.automation_log import AutomationLog
        from app.models.base import get_db_session

        with get_db_session() as db:
            count = (
                db.query(AutomationLog)
                .filter(
                    AutomationLog.client_id == client_id,
                    AutomationLog.job_type == job_type,
                    AutomationLog.status.in_(["success", "running"]),
                    AutomationLog.created_at >= today_start,
                )
                .count()
            )
            return count > 0
    except Exception:
        return _jsonl_has_run_today(client_id, job_type, today)


def _jsonl_has_run_today(client_id: str, job_type: str, today: str) -> bool:
    if not os.path.isfile(_JSONL_PATH):
        return False
    try:
        with open(_JSONL_PATH, encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line.strip())
                except Exception:
                    continue
                if (
                    rec.get("client_id") == client_id
                    and rec.get("job_type") == job_type
                    and rec.get("status") in ("success", "running")
                    and str(rec.get("created_at") or "")[:10] == today
                ):
                    return True
    except Exception:
        pass
    return False
