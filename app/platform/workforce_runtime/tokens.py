"""Run-scoped DSH bearer tokens: Redis hash-only, immutable, fail-closed."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
import threading
import time
from dataclasses import asdict, dataclass
from typing import Any, Iterable

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
KEY_PREFIX = "dsh:run-token:v1:"
DEFAULT_TTL_S = 900
MAX_TTL_S = 3600
_redis_factory: Any = None
_MEMORY: dict[str, tuple[str, float]] = {}
_LOCK = threading.Lock()


class TokenStoreUnavailable(RuntimeError):
    """Token authority cannot prove the binding; callers must refuse."""


@dataclass(frozen=True)
class RunTokenBinding:
    run_id: str
    tenant_id: str
    agent_id: str
    allowed_tools: tuple[str, ...]
    deadline: float
    issued_at: float
    schema_version: int = SCHEMA_VERSION

    def to_record(self) -> dict[str, Any]:
        record = asdict(self)
        record["allowed_tools"] = list(self.allowed_tools)
        return record


def _backend() -> str:
    # Memory exists only for deterministic unit tests; production/default is Redis.
    return (
        "memory" if (os.getenv("DSH_TOKEN_BACKEND") or "").strip().lower() == "memory" else "redis"
    )


def _redis():
    if _redis_factory is not None:
        return _redis_factory()
    import redis

    url = (os.getenv("REDIS_URL") or "").strip()
    if not url:
        from app.config import settings

        url = settings.redis_url
    return redis.Redis.from_url(url, socket_timeout=2, decode_responses=True)


def _hash(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _key(raw_token: str) -> str:
    return f"{KEY_PREFIX}{_hash(raw_token)}"


def _safe_id(value: str, *, limit: int = 96) -> str:
    clean = str(value or "").strip()
    if (
        not clean
        or len(clean) > limit
        or any(char in clean for char in ("/", "\\", "*", "?", "\n", "\r", "\x00", " "))
    ):
        raise ValueError("invalid binding identifier")
    return clean


def _tools(values: Iterable[str]) -> tuple[str, ...]:
    result: set[str] = set()
    for value in values:
        tool = str(value or "").strip()
        if (
            not tool
            or len(tool) > 160
            or any(char in tool for char in ("\\", "*", "?", "\n", "\r", "\x00", " "))
        ):
            raise ValueError("invalid allowed tool")
        result.add(tool)
    if not result:
        raise ValueError("at least one allowed tool is required")
    return tuple(sorted(result))


def issue(
    *,
    run_id: str,
    tenant_id: str,
    agent_id: str,
    allowed_tools: Iterable[str],
    deadline: float,
    ttl_s: int = DEFAULT_TTL_S,
) -> tuple[str, RunTokenBinding]:
    """Issue one opaque bearer. Redis stores only its SHA-256-derived key."""
    now = time.time()
    effective_deadline = min(float(deadline), now + MAX_TTL_S)
    if effective_deadline <= now:
        raise ValueError("deadline must be in the future")
    ttl = max(30, min(int(ttl_s), MAX_TTL_S, int(effective_deadline - now) + 1))
    binding = RunTokenBinding(
        run_id=_safe_id(run_id),
        tenant_id=_safe_id(tenant_id) if tenant_id else "",
        agent_id=_safe_id(agent_id, limit=64).lower(),
        allowed_tools=_tools(allowed_tools),
        deadline=effective_deadline,
        issued_at=now,
    )
    payload = json.dumps(binding.to_record(), separators=(",", ":"), sort_keys=True)
    for _attempt in range(3):
        raw = secrets.token_urlsafe(32)
        key = _key(raw)
        try:
            if _backend() == "memory":
                with _LOCK:
                    if key in _MEMORY and _MEMORY[key][1] > now:
                        continue
                    _MEMORY[key] = (payload, now + ttl)
                return raw, binding
            if _redis().set(key, payload, ex=ttl, nx=True):
                return raw, binding
        except Exception as exc:
            logger.warning("[dsh_tokens] issue failed: %s", type(exc).__name__)
            raise TokenStoreUnavailable("run token store unavailable") from exc
    raise TokenStoreUnavailable("run token collision budget exhausted")


def authenticate(raw_token: str, *, required_tool: str = "") -> RunTokenBinding:
    raw = str(raw_token or "").strip()
    if len(raw) < 32 or len(raw) > 256:
        raise PermissionError("invalid_run_token")
    key = _key(raw)
    try:
        if _backend() == "memory":
            with _LOCK:
                row = _MEMORY.get(key)
            if row is None or row[1] <= time.time():
                raise PermissionError("run_token_expired_or_unknown")
            payload = row[0]
        else:
            payload = _redis().get(key)
            if payload is None:
                raise PermissionError("run_token_expired_or_unknown")
        record = json.loads(payload)
        binding = RunTokenBinding(
            run_id=_safe_id(record["run_id"]),
            tenant_id=_safe_id(record["tenant_id"]) if record.get("tenant_id") else "",
            agent_id=_safe_id(record["agent_id"], limit=64).lower(),
            allowed_tools=_tools(record["allowed_tools"]),
            deadline=float(record["deadline"]),
            issued_at=float(record["issued_at"]),
            schema_version=int(record["schema_version"]),
        )
    except PermissionError:
        raise
    except Exception as exc:
        logger.warning("[dsh_tokens] authentication store failure: %s", type(exc).__name__)
        raise TokenStoreUnavailable("run token authentication unavailable") from exc
    if binding.schema_version != SCHEMA_VERSION or binding.deadline <= time.time():
        revoke(raw)
        raise PermissionError("run_token_expired_or_unknown")
    if required_tool and required_tool not in set(binding.allowed_tools):
        raise PermissionError("tool_not_allowed")
    return binding


def revoke(raw_token: str) -> bool:
    raw = str(raw_token or "").strip()
    if not raw:
        return False
    key = _key(raw)
    try:
        if _backend() == "memory":
            with _LOCK:
                return _MEMORY.pop(key, None) is not None
        return bool(_redis().delete(key))
    except Exception as exc:
        logger.warning("[dsh_tokens] revoke failed: %s", type(exc).__name__)
        return False


def reset_memory_for_tests() -> None:
    with _LOCK:
        _MEMORY.clear()


__all__ = [
    "DEFAULT_TTL_S",
    "KEY_PREFIX",
    "RunTokenBinding",
    "TokenStoreUnavailable",
    "authenticate",
    "issue",
    "reset_memory_for_tests",
    "revoke",
]
