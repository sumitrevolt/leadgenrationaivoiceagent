"""Durable, multi-worker-safe harness audit + shadow-dedup backend.

INERT BY DEFAULT. The backend is selected by ``HARNESS_AUDIT_BACKEND`` (default
``"jsonl"``). With the default, behaviour is byte-identical to the historical
append-only JSONL sink (single process; no cross-worker dedup) — production is
unchanged until an operator explicitly sets ``HARNESS_AUDIT_BACKEND=redis``.

Backends
--------
* ``jsonl`` (default): append-only file at ``HARNESS_RUN_LOG``. No record-layer
  dedup (identical to today). Intended for dev/test and the current production
  baseline. NOT multi-worker-safe.
* ``redis``: atomic first-observer-wins dedup via ``SET NX PX`` and a durable,
  retention-bounded Redis Stream for the audit-of-record. Multi-worker- and
  restart-safe. This is the production-grade path.

Fail-closed (production honesty)
--------------------------------
When ``HARNESS_AUDIT_BACKEND=redis`` and Redis is unavailable, an observation
FAILS CLOSED: no record is written, an operational error is emitted, and the
backend NEVER silently falls back to process-local dedup or the local file.
The trade-off is explicit — we drop *evidence* rather than *claim dedup safety
we cannot provide*. This dedups the audit/shadow EVIDENCE only; it makes no
claim about exactly-once BUSINESS execution (the legacy path stays authoritative
and is never re-run or altered by the audit layer).

Never stored: credentials, raw customer payloads, private message bodies, full
environment variables, or unbounded model output (size-capped + key-filtered).
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any, Optional

try:
    from app.utils.logger import setup_logger  # type: ignore

    logger = setup_logger(__name__)
except Exception:  # pragma: no cover
    import logging

    logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Configuration (all env-driven; safe defaults keep the backend inert).
# --------------------------------------------------------------------------- #
_DEFAULT_BACKEND = "jsonl"
_STREAM_KEY = "harness:audit:events"
_COUNTS_KEY = "harness:audit:counts"
_DEDUP_PREFIX = "harness:audit:dedup:"


def _env(name: str, default: str) -> str:
    return (os.getenv(name) or default).strip()


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name) or default)
    except Exception:
        return default


def backend_name() -> str:
    """Selected backend id: 'jsonl' (default) or 'redis'. Read at call time."""
    v = _env("HARNESS_AUDIT_BACKEND", _DEFAULT_BACKEND).lower()
    return v if v in ("jsonl", "redis") else _DEFAULT_BACKEND


def dedup_ttl_s() -> int:
    # Dedup claim lifetime. Must exceed the operational review window so a late
    # duplicate observation across a restart still resolves consistently.
    return _int_env("HARNESS_DEDUP_TTL_S", 14 * 24 * 3600)  # 14 days


def stream_maxlen() -> int:
    # Approximate retention bound for the durable audit stream (capacity guard,
    # not the primary retention control). 0 disables trimming.
    return _int_env("HARNESS_AUDIT_MAXLEN", 1_000_000)


def max_event_bytes() -> int:
    return _int_env("HARNESS_AUDIT_MAX_BYTES", 16 * 1024)


class AuditBackendUnavailable(RuntimeError):
    """Raised internally when a durable backend cannot service a request.
    Callers turn this into a fail-closed dropped observation + operational error;
    it is never raised into the legacy business path."""


# --------------------------------------------------------------------------- #
# Sanitisation + dedup-key derivation (shared by all backends).
# --------------------------------------------------------------------------- #
_FORBIDDEN_SUBSTRINGS = (
    "password",
    "secret",
    "token",
    "authorization",
    "api_key",
    "apikey",
    "cookie",
    "private_key",
    "dsn",
)


def _scrub(obj: Any, depth: int = 0) -> Any:
    """Best-effort structural scrub: drop forbidden-looking keys, bound strings.
    The observe() layer already redacts; this is defence-in-depth at the sink."""
    if depth > 6:
        return "<max-depth>"
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            lk = str(k).lower()
            if any(s in lk for s in _FORBIDDEN_SUBSTRINGS):
                out[k] = "<redacted>"
            else:
                out[k] = _scrub(v, depth + 1)
        return out
    if isinstance(obj, list):
        return [_scrub(x, depth + 1) for x in obj[:200]]
    if isinstance(obj, str):
        return obj if len(obj) <= 4096 else obj[:4096] + "…<truncated>"
    return obj


def enforce_size(row: dict[str, Any]) -> dict[str, Any]:
    """Return a size-bounded copy. Oversized rows get their heaviest field
    (extra.legacy_result_summary) truncated, then the whole row hard-capped."""
    row = _scrub(row)
    try:
        blob = json.dumps(row, ensure_ascii=False, default=str)
    except Exception:
        blob = "{}"
    cap = max_event_bytes()
    if len(blob.encode("utf-8")) <= cap:
        return row
    ex = row.get("extra")
    if isinstance(ex, dict) and "legacy_result_summary" in ex:
        ex = dict(ex)
        ex["legacy_result_summary"] = str(ex.get("legacy_result_summary"))[:512] + "…<truncated>"
        row = {**row, "extra": ex, "_size_truncated": True}
    blob = json.dumps(row, ensure_ascii=False, default=str)
    if len(blob.encode("utf-8")) > cap:
        # Last resort: keep only bounded identity fields (never lose the fact
        # that an event happened; drop the heavy payload).
        ex = row.get("extra") or {}
        row = {
            "ts": row.get("ts"),
            "run_id": row.get("run_id"),
            "tenant_id": row.get("tenant_id"),
            "agent": row.get("agent"),
            "kind": row.get("kind"),
            "tool": row.get("tool"),
            "extra": {
                "source_loop": ex.get("source_loop"),
                "mode": ex.get("mode"),
                "execution_comparison": ex.get("execution_comparison"),
                "registry_comparison": ex.get("registry_comparison"),
                "_oversized_dropped_payload": True,
            },
        }
    return row


def derive_dedup_key(row: dict[str, Any]) -> str:
    """Deterministic evidence-dedup key. Same logical observation (across
    processes/containers/restarts) resolves to one key; different attempts and
    different legitimate events stay distinct."""
    ex = row.get("extra") or {}
    prod_sha = _env("APP_VERSION", "") or _env("GIT_SHA", "")
    node_or_item = (
        ex.get("node_id")
        or ex.get("item_id")
        or ex.get("action_index")
        or ex.get("graph_step")
        or ""
    )
    parts = [
        prod_sha,
        str(ex.get("source_loop") or row.get("kind") or ""),
        str(row.get("agent") or ""),
        str(row.get("tenant_id") or ""),
        str(ex.get("resolved_tool_name") or ex.get("requested_tool") or row.get("tool") or ""),
        str(ex.get("resolved_tool_version") or ex.get("tool_version") or ""),
        str(row.get("run_id") or ""),
        str(node_or_item),
        str(ex.get("attempt") if ex.get("attempt") is not None else ""),
        str(row.get("kind") or ""),
    ]
    # If we have no discriminating context at all, fall back to a hash of the
    # whole row so distinct rows are never collapsed into one dedup bucket.
    if not any(parts[1:8]):
        parts.append(
            hashlib.sha256(json.dumps(row, sort_keys=True, default=str).encode()).hexdigest()
        )
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:32]


# --------------------------------------------------------------------------- #
# Backend interface + implementations.
# --------------------------------------------------------------------------- #
class AuditBackend:
    """A durable audit sink + atomic evidence-dedup claim."""

    name = "base"

    def claim(self, dedup_key: str) -> bool:  # pragma: no cover - interface
        raise NotImplementedError

    def append(self, row: dict[str, Any]) -> Optional[str]:  # pragma: no cover
        raise NotImplementedError

    def counts(self) -> dict[str, Any]:  # pragma: no cover - interface
        raise NotImplementedError

    def health(self) -> dict[str, Any]:  # pragma: no cover - interface
        raise NotImplementedError


class JsonlBackend(AuditBackend):
    """Legacy append-only file sink. Process-local (NOT multi-worker-safe).
    ``claim`` always accepts — record-layer dedup is intentionally OFF here so
    behaviour is byte-identical to the historical production baseline."""

    name = "jsonl"

    def __init__(self, path: Optional[str] = None) -> None:
        self._path = path or os.getenv("HARNESS_RUN_LOG", "data/harness_runs.jsonl")

    def claim(self, dedup_key: str) -> bool:
        return True  # no record-layer dedup in jsonl mode (unchanged behaviour)

    def append(self, row: dict[str, Any]) -> Optional[str]:
        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return None

    def counts(self) -> dict[str, Any]:
        total = 0
        by_family: dict[str, int] = {}
        by_mode: dict[str, int] = {}
        oldest = newest = None
        try:
            with open(self._path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        r = json.loads(line)
                    except Exception:
                        continue
                    total += 1
                    ex = r.get("extra") or {}
                    fam = str(ex.get("source_loop") or r.get("kind") or "unknown")
                    by_family[fam] = by_family.get(fam, 0) + 1
                    mode = str(ex.get("mode") or r.get("kind") or "unknown")
                    by_mode[mode] = by_mode.get(mode, 0) + 1
                    ts = r.get("ts")
                    if ts is not None:
                        oldest = ts if oldest is None else min(oldest, ts)
                        newest = ts if newest is None else max(newest, ts)
        except FileNotFoundError:
            pass
        return {
            "backend": self.name,
            "total": total,
            "by_family": by_family,
            "by_mode": by_mode,
            "duplicates_suppressed": 0,
            "backend_errors": 0,
            "oldest_ts": oldest,
            "newest_ts": newest,
        }

    def health(self) -> dict[str, Any]:
        return {"backend": self.name, "healthy": True, "fallback_active": True}


class RedisBackend(AuditBackend):
    """Atomic dedup (SET NX PX) + durable Redis Stream audit-of-record.
    Multi-worker- and restart-safe. Fails closed when Redis is unreachable."""

    name = "redis"

    def __init__(self, client: Any) -> None:
        if client is None:
            raise AuditBackendUnavailable("no redis client")
        self._r = client

    def claim(self, dedup_key: str) -> bool:
        key = _DEDUP_PREFIX + dedup_key
        try:
            ok = self._r.set(key, str(round(time.time(), 3)), nx=True, px=dedup_ttl_s() * 1000)
        except Exception as e:  # backend unavailable -> fail closed
            raise AuditBackendUnavailable(f"claim failed: {e}") from e
        return bool(ok)

    def append(self, row: dict[str, Any]) -> Optional[str]:
        try:
            fields = {"e": json.dumps(row, ensure_ascii=False, default=str)}
            ml = stream_maxlen()
            if ml and ml > 0:
                sid = self._r.xadd(_STREAM_KEY, fields, maxlen=ml, approximate=True)
            else:
                sid = self._r.xadd(_STREAM_KEY, fields)
            ex = row.get("extra") or {}
            fam = str(ex.get("source_loop") or row.get("kind") or "unknown")
            mode = str(ex.get("mode") or row.get("kind") or "unknown")
            try:
                self._r.hincrby(_COUNTS_KEY, "total", 1)
                self._r.hincrby(_COUNTS_KEY, f"family:{fam}", 1)
                self._r.hincrby(_COUNTS_KEY, f"mode:{mode}", 1)
            except Exception:  # counters are best-effort; the stream is durable
                pass
            return sid.decode() if isinstance(sid, bytes | bytearray) else str(sid)
        except Exception as e:
            raise AuditBackendUnavailable(f"append failed: {e}") from e

    def note_duplicate(self) -> None:
        try:
            self._r.hincrby(_COUNTS_KEY, "duplicates_suppressed", 1)
        except Exception:
            pass

    def note_error(self) -> None:
        try:
            self._r.hincrby(_COUNTS_KEY, "backend_errors", 1)
        except Exception:
            pass

    def counts(self) -> dict[str, Any]:
        def _d(x):
            return x.decode() if isinstance(x, bytes | bytearray) else x

        try:
            raw = self._r.hgetall(_COUNTS_KEY) or {}
            h = {_d(k): int(_d(v)) for k, v in raw.items()}
            total = h.get("total", 0)
            by_family = {k[7:]: v for k, v in h.items() if k.startswith("family:")}
            by_mode = {k[5:]: v for k, v in h.items() if k.startswith("mode:")}
            oldest = newest = None
            try:
                first = self._r.xrange(_STREAM_KEY, count=1)
                last = self._r.xrevrange(_STREAM_KEY, count=1)
                if first:
                    oldest = _d(first[0][0])
                if last:
                    newest = _d(last[0][0])
            except Exception:
                pass
            return {
                "backend": self.name,
                "total": total,
                "stream_len": self._safe_xlen(),
                "by_family": by_family,
                "by_mode": by_mode,
                "duplicates_suppressed": h.get("duplicates_suppressed", 0),
                "backend_errors": h.get("backend_errors", 0),
                "oldest_event_id": oldest,
                "newest_event_id": newest,
            }
        except Exception as e:
            raise AuditBackendUnavailable(f"counts failed: {e}") from e

    def _safe_xlen(self) -> int:
        try:
            return int(self._r.xlen(_STREAM_KEY))
        except Exception:
            return -1

    def health(self) -> dict[str, Any]:
        try:
            self._r.ping()
            return {"backend": self.name, "healthy": True, "fallback_active": False}
        except Exception as e:
            return {
                "backend": self.name,
                "healthy": False,
                "error": str(e)[:120],
                "fallback_active": False,
            }


# --------------------------------------------------------------------------- #
# Selection + the single write choke-point used by audit.record().
# --------------------------------------------------------------------------- #
def _get_redis_client() -> Any:
    """Reuse the app's Redis client (mirrors app.agents.harness.stop._redis)."""
    try:
        from app.cache import get_redis  # type: ignore

        return get_redis()
    except Exception:
        try:
            from app.infrastructure.redis_client import redis_client  # type: ignore

            return redis_client
        except Exception:
            return None


def get_backend(*, client: Any = None) -> AuditBackend:
    """Construct the selected backend. ``client`` may be injected for tests.
    In redis mode with no reachable client, raises AuditBackendUnavailable —
    production must never silently fall back to the process-local file."""
    name = backend_name()
    if name == "redis":
        return RedisBackend(client if client is not None else _get_redis_client())
    return JsonlBackend()


def write(row: dict[str, Any], *, backend: Optional[AuditBackend] = None) -> dict[str, Any]:
    """Atomic dedup + durable append for one audit row.

    Returns a result dict: {"written": bool, "duplicate": bool, "event_id": str|None,
    "backend": str, "error": str|None}. NEVER raises — a durable-backend failure
    is reported as a fail-closed dropped observation (written=False, error set) so
    the caller can emit an operational error without touching the legacy result.
    """
    row = enforce_size(row)
    try:
        be = backend if backend is not None else get_backend()
    except AuditBackendUnavailable as e:
        logger.error("harness.audit: backend unavailable (fail-closed, observation dropped): %s", e)
        return {
            "written": False,
            "duplicate": False,
            "event_id": None,
            "backend": backend_name(),
            "error": str(e),
        }
    try:
        dk = derive_dedup_key(row)
        if not be.claim(dk):
            if hasattr(be, "note_duplicate"):
                be.note_duplicate()  # type: ignore[attr-defined]
            return {
                "written": False,
                "duplicate": True,
                "event_id": None,
                "backend": be.name,
                "error": None,
            }
        eid = be.append(row)
        return {
            "written": True,
            "duplicate": False,
            "event_id": eid,
            "backend": be.name,
            "error": None,
        }
    except AuditBackendUnavailable as e:
        if hasattr(be, "note_error"):
            try:
                be.note_error()  # type: ignore[attr-defined]
            except Exception:
                pass
        logger.error("harness.audit: durable write failed closed (observation dropped): %s", e)
        return {
            "written": False,
            "duplicate": False,
            "event_id": None,
            "backend": be.name,
            "error": str(e),
        }


def status() -> dict[str, Any]:
    """Read-only backend status for the harness status surface (no secrets)."""
    name = backend_name()
    out: dict[str, Any] = {
        "backend": name,
        "app_version": _env("APP_VERSION", "") or _env("GIT_SHA", ""),
        "dedup_ttl_s": dedup_ttl_s(),
        "stream_maxlen": stream_maxlen(),
        "max_event_bytes": max_event_bytes(),
    }
    try:
        be = get_backend()
        out["health"] = be.health()
        out["counts"] = be.counts()
    except AuditBackendUnavailable as e:
        out["health"] = {
            "backend": name,
            "healthy": False,
            "error": str(e)[:120],
            "fallback_active": False,
        }
        out["counts"] = None
    return out
