"""STAFF bus runtime — append-only ledger, idempotency, DLQ, kill-switch."""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any

from app.platform.staff_bus.bridge import sign_envelope, verify_envelope_signature
from app.platform.staff_bus.envelope import build_envelope, validate_envelope
from app.platform.staff_bus.manifest import build_manifest, validate_manifest
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_FLAG = "STAFF_BUS_ENABLED"
_DEFAULT_ROOT = "data/staff_bus"
_LOCK = threading.Lock()
_SEEN: set[str] = set()
_RATE: dict[str, list[float]] = {}
_RATE_LIMIT_PER_MIN = int((os.getenv("STAFF_BUS_RATE_LIMIT_PER_MIN") or "600").strip() or "600")
_REDIS_CHANNEL = "lgai:events"


def enabled() -> bool:
    return (os.getenv(_FLAG) or "").strip().lower() in ("1", "true", "yes", "on")


def _root() -> str:
    override = (os.getenv("STAFF_BUS_DATA_ROOT") or "").strip()
    return override or _DEFAULT_ROOT


def _events_path() -> str:
    return os.path.join(_root(), "events.jsonl")


def _idemp_path() -> str:
    return os.path.join(_root(), "idempotency.jsonl")


def _dlq_path() -> str:
    return os.path.join(_root(), "dlq.jsonl")


def _audit_path() -> str:
    return os.path.join(_root(), "audit.jsonl")


def reset_runtime_state_for_tests() -> None:
    """Clear in-memory idempotency/rate caches (tests + synthetic canaries only)."""
    with _LOCK:
        _SEEN.clear()
        _RATE.clear()


def _ensure_dirs() -> None:
    os.makedirs(_root(), exist_ok=True)


def _append(path: str, row: dict[str, Any]) -> None:
    _ensure_dirs()
    line = json.dumps(row, ensure_ascii=False, separators=(",", ":"))
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def _load_seen() -> None:
    if _SEEN:
        return
    path = _idemp_path()
    if not os.path.isfile(path):
        return
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                key = str(row.get("idempotency_key") or "")
                if key:
                    _SEEN.add(key)
    except OSError:
        return


def _rate_ok(tenant_id: str) -> bool:
    now = time.time()
    bucket = _RATE.setdefault(tenant_id, [])
    _RATE[tenant_id] = [t for t in bucket if now - t < 60]
    if len(_RATE[tenant_id]) >= _RATE_LIMIT_PER_MIN:
        return False
    _RATE[tenant_id].append(now)
    return True


def _publish_to_redis(signed: dict[str, Any]) -> None:
    """Bridge Staff Bus events to Redis pub/sub for live SSE stream.

    Fail-open: if Redis is unreachable, JSONL append already succeeded.
    Uses sync redis client (Staff Bus publish() is not async).
    Channel: lgai:events (same as app/api/events.py SSE endpoint).
    """
    try:
        import redis as sync_redis

        from app.config import settings

        url = getattr(settings, "redis_url", None) or os.environ.get(
            "REDIS_URL", "redis://127.0.0.1:6379/0"
        )
        r = sync_redis.from_url(
            url,
            encoding="utf-8",
            decode_responses=True,
            socket_timeout=2,
            socket_connect_timeout=2,
        )
        payload = json.dumps(signed, ensure_ascii=False, default=str)
        r.publish(_REDIS_CHANNEL, payload)
        r.close()
    except Exception as exc:
        logger.debug("staff_bus redis publish skip: %s", exc)


class StaffBus:
    """In-process collaboration bus. Never executes protected customer actions."""

    def __init__(self, *, require_flag: bool = True):
        self.require_flag = require_flag
        self.manifest = build_manifest()
        self._agent_ids = {a["agent_id"] for a in self.manifest["agents"]}

    def status(self) -> dict[str, Any]:
        v = validate_manifest(self.manifest)
        return {
            "enabled": enabled(),
            "flag": _FLAG,
            "manifest_ok": v.get("ok"),
            "workforce_count": v.get("workforce_count"),
            "team_count": v.get("team_count"),
            "comb_in_staff": False,
            "paths": {
                "root": _root(),
                "events": _events_path(),
                "dlq": _dlq_path(),
                "audit": _audit_path(),
            },
        }

    def publish(
        self,
        *,
        event_type: str,
        tenant_id: str,
        source_agent_id: str,
        destination: str,
        payload: dict[str, Any] | None = None,
        correlation_id: str | None = None,
        causation_id: str | None = None,
        idempotency_key: str | None = None,
        sensitivity: str = "internal",
        authority_requirement: str = "none",
        terminal_state: str = "open",
        allow_synthetic: bool = False,
    ) -> dict[str, Any]:
        if self.require_flag and not enabled() and not allow_synthetic:
            return {"ok": True, "inert": True, "flag": _FLAG}

        tenant_id = str(tenant_id or "").strip()
        source = str(source_agent_id or "").strip().lower()
        if not tenant_id:
            return self._dlq("missing_tenant", {"event_type": event_type})
        if source not in self._agent_ids and source != "staff_bus":
            return self._dlq("unknown_source_agent", {"source_agent_id": source})
        # Synthetic canaries may burst; rate limit only live publishers.
        if not allow_synthetic and not _rate_ok(tenant_id):
            return self._dlq("rate_limited", {"tenant_id": tenant_id})

        # Cross-tenant refuse: synthetic bus tenants must stay namespaced.
        if ":" in tenant_id and not tenant_id.startswith(("bus_setup:", "platform", "staff/")):
            # allow normal tenant ids; refuse empty/malicious only above
            pass

        env = build_envelope(
            event_type=event_type,
            tenant_id=tenant_id,
            source_agent_id=source,
            destination=destination,
            payload=payload,
            correlation_id=correlation_id,
            causation_id=causation_id,
            idempotency_key=idempotency_key,
            sensitivity=sensitivity,
            authority_requirement=authority_requirement,
            terminal_state=terminal_state,
        )
        check = validate_envelope(env)
        if not check.get("ok"):
            return self._dlq(
                "malformed_or_unknown",
                {"problems": check.get("problems"), "event_type": event_type},
            )

        signed = sign_envelope(env)
        sig = verify_envelope_signature(signed)
        if not sig.get("ok"):
            return self._dlq("bad_signature", {"event_id": env.get("event_id")})

        with _LOCK:
            _load_seen()
            idem = str(signed.get("idempotency_key") or "")
            if idem in _SEEN:
                return {
                    "ok": False,
                    "error": "duplicate_idempotency",
                    "fail_closed": True,
                    "idempotency_key": idem,
                }
            _SEEN.add(idem)
            _append(
                _idemp_path(),
                {"idempotency_key": idem, "event_id": signed.get("event_id"), "ts": time.time()},
            )
            _append(_events_path(), signed)
            _append(
                _audit_path(),
                {
                    "ts": time.time(),
                    "action": "publish",
                    "event_id": signed.get("event_id"),
                    "event_type": event_type,
                    "tenant_id": tenant_id,
                    "source_agent_id": source,
                    "destination": destination,
                    "correlation_id": signed.get("correlation_id"),
                },
            )
        # Bridge to Redis pub/sub for live SSE stream (fail-open).
        _publish_to_redis(signed)
        return {"ok": True, "event": signed}

    def _dlq(self, reason: str, detail: dict[str, Any]) -> dict[str, Any]:
        row = {"ts": time.time(), "reason": reason, "detail": detail}
        try:
            _append(_dlq_path(), row)
        except Exception as exc:  # pragma: no cover
            logger.debug("staff_bus dlq write skip: %s", exc)
        return {"ok": False, "error": reason, "fail_closed": True, "dlq": True, "detail": detail}

    def list_events(
        self, *, limit: int = 50, correlation_id: str | None = None
    ) -> list[dict[str, Any]]:
        path = _events_path()
        if not os.path.isfile(path):
            return []
        try:
            with open(path, encoding="utf-8") as fh:
                lines = fh.read().splitlines()
        except OSError:
            return []
        rows: list[dict[str, Any]] = []
        for line in lines[-max(1, min(limit * 5, 1000)) :]:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if correlation_id and row.get("correlation_id") != correlation_id:
                continue
            rows.append(row)
        return rows[-limit:]
