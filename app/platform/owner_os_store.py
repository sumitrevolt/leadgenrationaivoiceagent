"""Owner OS persistence — Postgres primary, hardened JSONL fallback.

TECH DEBT (temporary): when DB is unavailable or OWNER_OS_STORAGE=jsonl,
sidecars under data/ are used with file_lock + atomic replace + fsync.
Multi-container prod MUST run Alembic 019 and use Postgres.
"""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from typing import Any

from app.utils.file_lock import file_lock
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

CMD_STORE = os.path.join("data", "owner_commands.jsonl")
KILL_STORE = os.path.join("data", "owner_kill_switches.jsonl")
AUDIT_STORE = os.path.join("data", "owner_os_audit.jsonl")

_STORAGE_MODE: str | None = None  # "db" | "jsonl"


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def storage_mode() -> str:
    """Resolve backend once per process (re-probe if forced)."""
    global _STORAGE_MODE
    forced = (os.getenv("OWNER_OS_STORAGE") or "").strip().lower()
    if forced in ("jsonl", "db"):
        _STORAGE_MODE = forced
        return forced
    if _STORAGE_MODE:
        return _STORAGE_MODE
    try:
        from app.models.base import get_db_session
        from app.models.owner_os import OwnerCommand

        with get_db_session() as db:
            db.query(OwnerCommand.command_id).limit(1).all()
        _STORAGE_MODE = "db"
    except Exception as e:
        logger.info("[owner_os_store] DB unavailable → JSONL fallback: %s", type(e).__name__)
        _STORAGE_MODE = "jsonl"
    return _STORAGE_MODE


def reset_storage_mode() -> None:
    global _STORAGE_MODE
    _STORAGE_MODE = None


# ── JSONL helpers (hardened) ───────────────────────────────────────────────


def _read_jsonl(path: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        if not os.path.exists(path):
            return out
        with file_lock(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        out.append(json.loads(line))
                    except Exception:
                        pass
    except Exception:
        pass
    return out


def _atomic_write_jsonl(path: str, rows: list[dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(path) or "data", exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        prefix="owner_os_", suffix=".jsonl", dir=os.path.dirname(path) or "data"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
            f.flush()
            try:
                os.fsync(f.fileno())
            except Exception:
                pass
        with file_lock(path):
            os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except Exception:
            pass
        raise


def _append_jsonl(path: str, rec: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path) or "data", exist_ok=True)
    with file_lock(path):
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
            f.flush()
            try:
                os.fsync(f.fileno())
            except Exception:
                pass


def _cmd_to_api(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize DB/API shape → UI/test command dict."""
    status = row.get("status") or row.get("execution_state") or "DRAFT"
    return {
        "command_id": row.get("command_id"),
        "idempotency_key": row.get("idempotency_key"),
        "actor": row.get("actor") or row.get("actor_id") or "admin",
        "actor_id": row.get("actor_id") or row.get("actor") or "admin",
        "actor_role": row.get("actor_role"),
        "original": row.get("original") or row.get("original_instruction") or "",
        "original_instruction": row.get("original_instruction") or row.get("original") or "",
        "intent": row.get("intent") or row.get("normalized_intent"),
        "normalized_intent": row.get("normalized_intent") or row.get("intent"),
        "tenant_id": row.get("tenant_id"),
        "agent_id": row.get("agent_id") or row.get("assigned_agent_id"),
        "assigned_agent_id": row.get("assigned_agent_id") or row.get("agent_id"),
        "priority": row.get("priority") or "normal",
        "risk_level": row.get("risk_level") or "low",
        "approval_required": bool(row.get("approval_required")),
        "approval_state": row.get("approval_state") or "none",
        "parameters": (
            row.get("parameters")
            if isinstance(row.get("parameters"), dict)
            else (json.loads(row["parameters_json"]) if row.get("parameters_json") else {})
        ),
        "status": status,
        "execution_state": status,
        "progress": int(row.get("progress") or 0),
        "retry_count": int(row.get("retry_count") or 0),
        "created_at": _iso(row.get("created_at")),
        "updated_at": _iso(row.get("updated_at")),
        "completed_at": _iso(row.get("completed_at")),
        "evidence": (
            row.get("evidence")
            if isinstance(row.get("evidence"), dict)
            else (
                json.loads(row["evidence_summary_json"])
                if row.get("evidence_summary_json")
                else None
            )
        ),
        "error": row.get("error") or row.get("sanitized_error"),
        "error_code": row.get("error_code"),
        "sanitized_error": row.get("sanitized_error") or row.get("error"),
        "preview_summary": row.get("preview_summary"),
        "publish_allowed": bool(row.get("publish_allowed", False)),
        "customer_notify_allowed": bool(row.get("customer_notify_allowed", False)),
        "correlation_id": row.get("correlation_id"),
        "version": int(row.get("version") or 1),
        "storage": storage_mode(),
    }


def _iso(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.replace(tzinfo=timezone.utc).isoformat() if v.tzinfo is None else v.isoformat()
    return str(v)


# ── Commands ───────────────────────────────────────────────────────────────


def get_command(command_id: str) -> dict[str, Any] | None:
    cid = str(command_id or "")
    if not cid:
        return None
    if storage_mode() == "db":
        try:
            from app.models.base import get_db_session
            from app.models.owner_os import OwnerCommand

            with get_db_session() as db:
                row = db.query(OwnerCommand).filter(OwnerCommand.command_id == cid).first()
                if not row:
                    return None
                return _orm_cmd_to_api(row)
        except Exception as e:
            logger.debug("[owner_os_store] get_command db: %s", e)
    latest: dict[str, dict[str, Any]] = {}
    for r in _read_jsonl(CMD_STORE):
        k = str(r.get("command_id") or "")
        if k:
            latest[k] = r
    hit = latest.get(cid)
    return _cmd_to_api(hit) if hit else None


def list_commands(limit: int = 50) -> list[dict[str, Any]]:
    if storage_mode() == "db":
        try:
            from app.models.base import get_db_session
            from app.models.owner_os import OwnerCommand

            with get_db_session() as db:
                rows = (
                    db.query(OwnerCommand)
                    .order_by(
                        OwnerCommand.updated_at.desc().nullslast(), OwnerCommand.created_at.desc()
                    )
                    .limit(limit)
                    .all()
                )
                return [_orm_cmd_to_api(r) for r in rows]
        except Exception as e:
            logger.debug("[owner_os_store] list_commands db: %s", e)
    latest: dict[str, dict[str, Any]] = {}
    for r in _read_jsonl(CMD_STORE):
        k = str(r.get("command_id") or "")
        if k:
            latest[k] = r
    out = sorted(
        latest.values(),
        key=lambda x: str(x.get("updated_at") or x.get("created_at") or ""),
        reverse=True,
    )
    return [_cmd_to_api(r) for r in out[:limit]]


def find_by_idempotency(key: str) -> dict[str, Any] | None:
    key = str(key or "")
    if not key:
        return None
    if storage_mode() == "db":
        try:
            from app.models.base import get_db_session
            from app.models.owner_os import OwnerCommand

            with get_db_session() as db:
                row = db.query(OwnerCommand).filter(OwnerCommand.idempotency_key == key).first()
                if row:
                    return _orm_cmd_to_api(row)
        except Exception as e:
            logger.debug("[owner_os_store] find_idem db: %s", e)
    for c in list_commands(200):
        if c.get("idempotency_key") == key:
            return c
    return None


def _orm_cmd_to_api(row: Any) -> dict[str, Any]:
    params = {}
    if getattr(row, "parameters_json", None):
        try:
            params = json.loads(row.parameters_json)
        except Exception:
            params = {}
    evidence = None
    if getattr(row, "evidence_summary_json", None):
        try:
            evidence = json.loads(row.evidence_summary_json)
        except Exception:
            evidence = None
    return _cmd_to_api(
        {
            "command_id": row.command_id,
            "actor_id": row.actor_id,
            "actor_role": row.actor_role,
            "original_instruction": row.original_instruction,
            "normalized_intent": row.normalized_intent,
            "tenant_id": row.tenant_id,
            "assigned_agent_id": row.assigned_agent_id,
            "risk_level": row.risk_level,
            "approval_state": row.approval_state,
            "execution_state": row.execution_state,
            "idempotency_key": row.idempotency_key,
            "parameters": params,
            "publish_allowed": row.publish_allowed,
            "customer_notify_allowed": row.customer_notify_allowed,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "completed_at": row.completed_at,
            "retry_count": row.retry_count,
            "error_code": row.error_code,
            "sanitized_error": row.sanitized_error,
            "evidence": evidence,
            "correlation_id": row.correlation_id,
            "version": row.version,
            "preview_summary": row.preview_summary,
            "approval_required": (row.approval_state or "") not in ("none", "", "not_required"),
        }
    )


def insert_command(cmd: dict[str, Any]) -> dict[str, Any]:
    api = _cmd_to_api(cmd)
    if storage_mode() == "db":
        try:
            from app.models.base import get_db_session
            from app.models.owner_os import OwnerCommand

            with get_db_session() as db:
                existing = (
                    db.query(OwnerCommand)
                    .filter(OwnerCommand.idempotency_key == api["idempotency_key"])
                    .first()
                )
                if existing:
                    return _orm_cmd_to_api(existing)
                row = OwnerCommand(
                    command_id=api["command_id"],
                    actor_id=api["actor_id"],
                    actor_role=api.get("actor_role"),
                    original_instruction=api["original"],
                    normalized_intent=api["intent"],
                    tenant_id=api.get("tenant_id"),
                    assigned_agent_id=api.get("agent_id"),
                    risk_level=api.get("risk_level") or "low",
                    approval_state=api.get("approval_state")
                    or ("required" if api.get("approval_required") else "none"),
                    execution_state=api.get("status") or "DRAFT",
                    idempotency_key=api["idempotency_key"],
                    parameters_json=json.dumps(api.get("parameters") or {}, ensure_ascii=False),
                    publish_allowed=bool(api.get("publish_allowed")),
                    customer_notify_allowed=bool(api.get("customer_notify_allowed")),
                    created_at=_now(),
                    updated_at=_now(),
                    retry_count=int(api.get("retry_count") or 0),
                    correlation_id=api.get("correlation_id"),
                    version=1,
                    preview_summary=api.get("preview_summary"),
                )
                db.add(row)
            return get_command(api["command_id"]) or api
        except Exception as e:
            logger.warning("[owner_os_store] insert_command db fail → jsonl: %s", type(e).__name__)
    # Process-safe dedupe under lock (concurrent writers / multi-worker).
    with file_lock(CMD_STORE):
        latest: dict[str, dict[str, Any]] = {}
        for r in _read_jsonl(CMD_STORE):
            k = str(r.get("command_id") or "")
            if k:
                latest[k] = r
        for r in latest.values():
            if r.get("idempotency_key") == api["idempotency_key"]:
                return _cmd_to_api(r)
        row = {
            **api,
            "status": api["status"],
            "updated_at": _now_iso(),
            "created_at": api.get("created_at") or _now_iso(),
        }
        try:
            os.makedirs(os.path.dirname(CMD_STORE) or "data", exist_ok=True)
            with open(CMD_STORE, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
                f.flush()
                try:
                    os.fsync(f.fileno())
                except Exception:
                    pass
        except Exception as e:
            logger.debug("[owner_os_store] insert jsonl: %s", e)
        return _cmd_to_api(row)


def update_command(
    command_id: str, expected_version: int | None = None, **fields: Any
) -> dict[str, Any]:
    """Optimistic lock via version when DB; JSONL appends latest snapshot."""
    cur = get_command(command_id)
    if not cur:
        return {"ok": False, "error": "command not found"}
    if expected_version is not None and int(cur.get("version") or 1) != int(expected_version):
        return {"ok": False, "error": "version_conflict", "command": cur}

    merged = {
        **cur,
        **fields,
        "updated_at": _now_iso(),
        "version": int(cur.get("version") or 1) + 1,
    }
    if merged.get("status"):
        merged["execution_state"] = merged["status"]
    if merged.get("status") in ("SUCCEEDED", "FAILED", "CANCELLED"):
        merged["completed_at"] = merged.get("completed_at") or _now_iso()

    if storage_mode() == "db":
        try:
            from app.models.base import get_db_session
            from app.models.owner_os import OwnerCommand

            with get_db_session() as db:
                row = db.query(OwnerCommand).filter(OwnerCommand.command_id == command_id).first()
                if not row:
                    return {"ok": False, "error": "command not found"}
                if expected_version is not None and int(row.version or 1) != int(expected_version):
                    return {
                        "ok": False,
                        "error": "version_conflict",
                        "command": _orm_cmd_to_api(row),
                    }
                row.execution_state = merged.get("status") or row.execution_state
                if "agent_id" in fields or "assigned_agent_id" in fields:
                    row.assigned_agent_id = merged.get("agent_id")
                if "tenant_id" in fields:
                    # refuse tenant change after RUNNING+
                    if (
                        row.execution_state in ("RUNNING", "SUCCEEDED", "FAILED")
                        and fields.get("tenant_id") != row.tenant_id
                    ):
                        return {"ok": False, "error": "tenant_locked_after_execution_start"}
                    if row.execution_state not in ("RUNNING", "SUCCEEDED", "FAILED", "QUEUED"):
                        row.tenant_id = merged.get("tenant_id")
                if "retry_count" in fields:
                    row.retry_count = int(merged.get("retry_count") or 0)
                if "error" in fields or "sanitized_error" in fields:
                    row.sanitized_error = (
                        merged.get("sanitized_error") or merged.get("error") or ""
                    )[:500]
                    row.error_code = merged.get("error_code")
                if "evidence" in fields:
                    row.evidence_summary_json = json.dumps(
                        merged.get("evidence") or {}, ensure_ascii=False
                    )[:8000]
                if "preview_summary" in fields:
                    row.preview_summary = merged.get("preview_summary")
                if "approval_state" in fields:
                    row.approval_state = merged.get("approval_state")
                if "publish_allowed" in fields:
                    row.publish_allowed = bool(merged.get("publish_allowed"))
                if "customer_notify_allowed" in fields:
                    row.customer_notify_allowed = bool(merged.get("customer_notify_allowed"))
                if merged.get("status") in ("SUCCEEDED", "FAILED", "CANCELLED"):
                    row.completed_at = _now()
                row.updated_at = _now()
                row.version = int(row.version or 1) + 1
            return {"ok": True, "command": get_command(command_id)}
        except Exception as e:
            logger.warning("[owner_os_store] update_command db fail: %s", type(e).__name__)
            return {"ok": False, "error": f"db_update_failed:{type(e).__name__}"}

    _append_jsonl(CMD_STORE, merged)
    return {"ok": True, "command": _cmd_to_api(merged)}


# ── Kill switches ──────────────────────────────────────────────────────────


def kill_map() -> dict[str, dict[str, Any]]:
    m: dict[str, dict[str, Any]] = {}
    if storage_mode() == "db":
        try:
            from app.models.base import get_db_session
            from app.models.owner_os import OwnerKillSwitch

            with get_db_session() as db:
                for row in db.query(OwnerKillSwitch).all():
                    m[row.switch_name] = {
                        "key": row.switch_name,
                        "engaged": bool(row.engaged),
                        "scope": row.scope,
                        "reason": row.reason,
                        "by": row.changed_by,
                        "at": _iso(row.changed_at),
                        "version": row.version,
                    }
                return m
        except Exception as e:
            logger.debug("[owner_os_store] kill_map db: %s", e)
    for r in _read_jsonl(KILL_STORE):
        key = str(r.get("key") or r.get("switch_name") or "")
        if key:
            m[key] = r
    return m


def set_kill_record(key: str, engaged: bool, by: str, reason: str = "") -> dict[str, Any]:
    rec = {
        "key": key,
        "switch_name": key,
        "engaged": bool(engaged),
        "by": (by or "admin")[:80],
        "changed_by": (by or "admin")[:80],
        "reason": (reason or "")[:200],
        "at": _now_iso(),
        "scope": "global",
        "version": 1,
    }
    if storage_mode() == "db":
        try:
            from app.models.base import get_db_session
            from app.models.owner_os import OwnerKillSwitch

            with get_db_session() as db:
                row = db.query(OwnerKillSwitch).filter(OwnerKillSwitch.switch_name == key).first()
                if row:
                    row.engaged = bool(engaged)
                    row.reason = (reason or "")[:200]
                    row.changed_by = (by or "admin")[:80]
                    row.changed_at = _now()
                    row.version = int(row.version or 1) + 1
                    rec["version"] = row.version
                else:
                    db.add(
                        OwnerKillSwitch(
                            switch_name=key,
                            engaged=bool(engaged),
                            scope="global",
                            reason=(reason or "")[:200],
                            changed_by=(by or "admin")[:80],
                            changed_at=_now(),
                            version=1,
                        )
                    )
            return rec
        except Exception as e:
            logger.warning("[owner_os_store] set_kill db fail → jsonl: %s", type(e).__name__)
    _append_jsonl(KILL_STORE, rec)
    return rec


def kill_engaged(key: str) -> bool:
    return bool(kill_map().get(key, {}).get("engaged"))


# ── Audit ──────────────────────────────────────────────────────────────────


def append_audit(
    actor: str,
    action: str,
    *,
    target: str | None = None,
    tenant_id: str | None = None,
    correlation_id: str | None = None,
    before_summary: str | None = None,
    after_summary: str | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    # Sanitize: never persist secrets-like keys
    safe_meta = {}
    for k, v in (meta or {}).items():
        lk = str(k).lower()
        if any(
            x in lk for x in ("password", "token", "secret", "api_key", "authorization", "cookie")
        ):
            continue
        safe_meta[k] = v if not isinstance(v, str) else v[:500]

    if storage_mode() == "db":
        try:
            from app.models.base import get_db_session
            from app.models.owner_os import OwnerOSAuditEvent

            with get_db_session() as db:
                db.add(
                    OwnerOSAuditEvent(
                        id=uuid.uuid4().hex,
                        at=_now(),
                        actor=(actor or "admin")[:120],
                        action=(action or "")[:80],
                        target=(target or "")[:120] or None,
                        tenant_id=tenant_id,
                        correlation_id=correlation_id,
                        before_summary=(before_summary or "")[:500] or None,
                        after_summary=(after_summary or "")[:500] or None,
                        meta_json=(
                            json.dumps(safe_meta, ensure_ascii=False)[:4000] if safe_meta else None
                        ),
                    )
                )
            return
        except Exception as e:
            logger.debug("[owner_os_store] audit db: %s", e)
    _append_jsonl(
        AUDIT_STORE,
        {
            "at": _now_iso(),
            "actor": (actor or "admin")[:120],
            "action": (action or "")[:80],
            "target": target,
            "tenant_id": tenant_id,
            "correlation_id": correlation_id,
            "before_summary": before_summary,
            "after_summary": after_summary,
            "detail": safe_meta,
            "meta": safe_meta,
        },
    )


def recent_audit(limit: int = 40) -> list[dict[str, Any]]:
    if storage_mode() == "db":
        try:
            from app.models.base import get_db_session
            from app.models.owner_os import OwnerOSAuditEvent

            with get_db_session() as db:
                rows = (
                    db.query(OwnerOSAuditEvent)
                    .order_by(OwnerOSAuditEvent.at.desc())
                    .limit(limit)
                    .all()
                )
                out = []
                for r in rows:
                    meta = {}
                    if r.meta_json:
                        try:
                            meta = json.loads(r.meta_json)
                        except Exception:
                            meta = {}
                    out.append(
                        {
                            "at": _iso(r.at),
                            "actor": r.actor,
                            "action": r.action,
                            "target": r.target,
                            "tenant_id": r.tenant_id,
                            "correlation_id": r.correlation_id,
                            "before_summary": r.before_summary,
                            "after_summary": r.after_summary,
                            "detail": meta,
                            "meta": meta,
                        }
                    )
                return out
        except Exception as e:
            logger.debug("[owner_os_store] recent_audit db: %s", e)
    rows = _read_jsonl(AUDIT_STORE)
    return list(reversed(rows[-limit:]))
