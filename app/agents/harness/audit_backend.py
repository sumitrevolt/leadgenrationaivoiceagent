"""Durable, multi-worker-safe harness audit + shadow-dedup backend.

INERT BY DEFAULT. Selected by ``HARNESS_AUDIT_BACKEND`` (default ``"jsonl"``):
with the default, behaviour is byte-identical to the historical append-only JSONL
sink — production is unchanged until an operator explicitly sets ``redis``.

Persistence model (redis) — ONE authoritative all-or-nothing write
------------------------------------------------------------------
Each observation is a single immutable **record key** created with
``SET harness:{audit}:record:<sha256> <value> NX GET PX <retention>``. That one
command is simultaneously the durable audit record, the first-observer claim, the
duplicate identity, and the replay envelope:

* returns nil  → the record was created (first observer);
* returns old  → a duplicate; the returned value IS the existing record;
* raises        → nothing was created (fail closed).

No second structure is required to establish evidence durability, so a partial
commit is impossible. The Redis **Stream** and **metrics** hash are
NON-authoritative derived indexes updated best-effort AFTER the authoritative
write; if they fail, the audit evidence still exists, status reports index lag,
and an idempotent reconciler can rebuild them from the authoritative records.

Retention: the record's TTL is also its dedup lifetime (one key), so "dedup
exists but record missing" and "record exists but dedup missing" are impossible.
After retention expiry a replay legitimately becomes a new observation.

Fail-closed: in ``redis`` mode an unreachable/errored Redis drops the observation
and emits an operational error; it NEVER silently falls back to process-local
dedup or the file. An invalid ``HARNESS_AUDIT_BACKEND`` value is unhealthy and
writes nothing — never silently coerced to jsonl. This dedups the audit/shadow
EVIDENCE only; it makes no claim of exactly-once BUSINESS execution.

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
# Keys (single hash slot "{audit}" -> cluster-safe; only bounded hashes in names)
# --------------------------------------------------------------------------- #
_DEFAULT_BACKEND = "jsonl"
_RECORD_PREFIX = "harness:{audit}:record:"  # authoritative immutable records
_STREAM_KEY = "harness:{audit}:events"  # DERIVED, non-authoritative index
_METRICS_KEY = "harness:{audit}:metrics"  # DERIVED, best-effort counters
_MIGRATION_PREFIX = "harness:{audit}:migration:"  # migration idempotency markers


def _env(name: str, default: str) -> str:
    return (os.getenv(name) or default).strip()


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name) or default)
    except Exception:
        return default


def resolve_backend_config() -> dict[str, Any]:
    """Strict resolution. Unset/empty or 'jsonl' -> jsonl (valid); 'redis' -> redis
    (valid); ANY other explicit value -> invalid (unhealthy, no write, no silent
    fallback). A typo like 'redi'/'postgres' never becomes jsonl."""
    raw = os.getenv("HARNESS_AUDIT_BACKEND")
    # STRICT exact matching: unset/empty -> jsonl; exactly "jsonl"/"redis" -> that
    # backend; ANY other explicit value (typo, trailing space, wrong case) -> invalid.
    if raw is None or raw == "":
        resolved, valid = "jsonl", True
    elif raw == "jsonl":
        resolved, valid = "jsonl", True
    elif raw == "redis":
        resolved, valid = "redis", True
    else:
        resolved, valid = "invalid", False
    return {"configured_value": raw, "resolved_backend": resolved, "configuration_valid": valid}


def backend_name() -> str:
    """Resolved backend id: 'jsonl' | 'redis' | 'invalid'. Read at call time."""
    return resolve_backend_config()["resolved_backend"]


def audit_retention_s() -> int:
    # Authoritative record lifetime == dedup lifetime. >= 90 days (or a longer
    # approved compliance window). NOT a short 14-day dedup TTL.
    return _int_env("HARNESS_AUDIT_RETENTION_S", 90 * 24 * 3600)


def stream_maxlen() -> int:
    return _int_env("HARNESS_AUDIT_STREAM_MAXLEN", 1_000_000)


def max_event_bytes() -> int:
    return _int_env("HARNESS_AUDIT_MAX_BYTES", 16 * 1024)


class AuditBackendUnavailable(RuntimeError):
    """Durable backend could not service a request. Callers turn this into a
    fail-closed dropped observation + operational error; never raised into legacy."""


# --------------------------------------------------------------------------- #
# Sanitisation + identity derivation (shared).
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
    """Defence-in-depth scrub: drop forbidden-looking keys, bound strings."""
    if depth > 6:
        return "<max-depth>"
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if any(s in str(k).lower() for s in _FORBIDDEN_SUBSTRINGS):
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
    """Return a scrubbed, size-bounded copy (heavy summary truncated, then hard cap)."""
    row = _scrub(row)
    cap = max_event_bytes()
    try:
        blob = json.dumps(row, ensure_ascii=False, default=str)
    except Exception:
        blob = "{}"
    if len(blob.encode("utf-8")) <= cap:
        return row
    ex = row.get("extra")
    if isinstance(ex, dict) and "legacy_result_summary" in ex:
        ex = dict(ex)
        ex["legacy_result_summary"] = str(ex.get("legacy_result_summary"))[:512] + "…<truncated>"
        row = {**row, "extra": ex, "_size_truncated": True}
    if len(json.dumps(row, ensure_ascii=False, default=str).encode("utf-8")) > cap:
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


def derive_dedup_key(row: dict[str, Any], source_app_version: str | None = None) -> str:
    """Deterministic evidence identity. Live observations bind the CURRENT runtime
    SHA (APP_VERSION/GIT_SHA); a migration passes an explicit validated
    ``source_app_version`` so historical events keep their original provenance and
    are NOT re-identified under the migrating process's SHA."""
    ex = row.get("extra") or {}
    if source_app_version is not None:
        prod_sha = str(source_app_version)
    else:
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
    if not any(parts[1:8]):
        parts.append(
            hashlib.sha256(json.dumps(row, sort_keys=True, default=str).encode()).hexdigest()
        )
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:32]


def derive_envelope(row: dict[str, Any]) -> dict[str, Any]:
    """Compact identity+verdict envelope (bounded, secret-free)."""
    ex = row.get("extra") or {}
    return {
        "ts": row.get("ts"),
        "kind": row.get("kind"),
        "agent": row.get("agent"),
        "tenant_id": row.get("tenant_id"),
        "source_loop": ex.get("source_loop"),
        "resolved_tool_name": ex.get("resolved_tool_name") or row.get("tool"),
        "resolved_tool_version": ex.get("resolved_tool_version"),
        "mode": ex.get("mode"),
        "execution_comparison": ex.get("execution_comparison"),
        "registry_comparison": ex.get("registry_comparison"),
        "node_or_item": ex.get("node_id") or ex.get("item_id"),
        "attempt": ex.get("attempt"),
        "run_id": row.get("run_id"),
    }


def build_record(
    row: dict[str, Any], dedup_key: str, source_app_version: str, created_at: float | None = None
) -> dict[str, Any]:
    """The authoritative record value: durable audit record + replay envelope +
    explicit provenance. ``event_id`` is deterministic (== dedup_key) so retries
    resolve identically."""
    return {
        "event_id": dedup_key,
        "event": enforce_size(row),
        "envelope": derive_envelope(row),
        "source_app_version": source_app_version,
        "created_at": created_at if created_at is not None else round(time.time(), 3),
    }


# --------------------------------------------------------------------------- #
# Backends.
# --------------------------------------------------------------------------- #
class AuditBackend:
    name = "base"

    def record(self, row: dict[str, Any], dedup_key: str) -> dict[str, Any]:
        raise NotImplementedError  # pragma: no cover

    def counts(self) -> dict[str, Any]:
        raise NotImplementedError  # pragma: no cover

    def health(self) -> dict[str, Any]:
        raise NotImplementedError  # pragma: no cover


class JsonlBackend(AuditBackend):
    """Legacy append-only file sink. Process-local (NOT multi-worker-safe). No
    record-layer dedup (byte-identical to the historical production baseline)."""

    name = "jsonl"

    def __init__(self, path: str | None = None) -> None:
        self._path = path or os.getenv("HARNESS_RUN_LOG", "data/harness_runs.jsonl")

    def record(self, row: dict[str, Any], dedup_key: str) -> dict[str, Any]:
        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return {"written": True, "duplicate": False, "event_id": None}

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
        return {
            "backend": self.name,
            "healthy": True,
            "selected_intentionally": True,
            "fallback_active": False,
            "durable": False,
            "multi_worker_safe": False,
            "configuration_valid": True,
        }


class InvalidBackend(AuditBackend):
    """An explicitly invalid HARNESS_AUDIT_BACKEND value. Unhealthy; every write
    fails closed. NEVER coerced to jsonl."""

    name = "invalid"

    def __init__(self, configured_value: str | None) -> None:
        self._configured = configured_value

    def record(self, row: dict[str, Any], dedup_key: str) -> dict[str, Any]:
        raise AuditBackendUnavailable(f"invalid HARNESS_AUDIT_BACKEND={self._configured!r}")

    def counts(self) -> dict[str, Any]:
        return {"backend": self.name, "total": None, "error": "invalid backend configuration"}

    def health(self) -> dict[str, Any]:
        return {
            "backend": self.name,
            "healthy": False,
            "configuration_valid": False,
            "configured_value": self._configured,
            "fallback_active": False,
            "durable": False,
            "multi_worker_safe": False,
        }


def _to_str(x: Any) -> str:
    return x.decode() if isinstance(x, bytes | bytearray) else str(x)


class RedisBackend(AuditBackend):
    """Authoritative single-write model: ``SET record NX GET PX``. All-or-nothing.
    Stream + metrics are derived best-effort indexes (never determine existence)."""

    name = "redis"

    def __init__(self, client: Any) -> None:
        if client is None:
            raise AuditBackendUnavailable("no redis client")
        self._r = client

    def record(
        self,
        row: dict[str, Any],
        dedup_key: str,
        source_app_version: str | None = None,
        created_at: float | None = None,
    ) -> dict[str, Any]:
        rec_key = _RECORD_PREFIX + dedup_key
        sav = (
            source_app_version
            if source_app_version is not None
            else (_env("APP_VERSION", "") or _env("GIT_SHA", ""))
        )
        record_val = build_record(row, dedup_key, sav, created_at)
        val_json = json.dumps(record_val, ensure_ascii=False, default=str)
        # ---- THE authoritative all-or-nothing write ----
        try:
            prev = self._r.set(rec_key, val_json, nx=True, get=True, px=audit_retention_s() * 1000)
        except Exception as e:  # nothing created -> fail closed
            self._note("script_errors")
            raise AuditBackendUnavailable(f"authoritative record write failed: {e}") from e
        if prev is not None:  # duplicate: the returned value IS the existing record
            self._note("duplicates_suppressed")
            existing_id = dedup_key
            try:
                existing_id = json.loads(_to_str(prev)).get("event_id", dedup_key)
            except Exception:
                pass
            return {"written": False, "duplicate": True, "event_id": existing_id}
        # created -> best-effort DERIVED index (must never affect the record)
        self._index_best_effort(row, dedup_key, val_json)
        return {"written": True, "duplicate": False, "event_id": dedup_key}

    def _index_best_effort(self, row: dict[str, Any], dedup_key: str, val_json: str) -> None:
        ex = row.get("extra") or {}
        fam = str(ex.get("source_loop") or row.get("kind") or "unknown")
        mode = str(ex.get("mode") or row.get("kind") or "unknown")
        try:
            ml = stream_maxlen()
            if ml and ml > 0:
                self._r.xadd(_STREAM_KEY, {"rk": dedup_key}, maxlen=ml, approximate=True)
            else:
                self._r.xadd(_STREAM_KEY, {"rk": dedup_key})
            self._r.hincrby(_METRICS_KEY, "records_created", 1)
            self._r.hincrby(_METRICS_KEY, f"family:{fam}", 1)
            self._r.hincrby(_METRICS_KEY, f"mode:{mode}", 1)
        except Exception as e:  # index lag is recoverable; the record already exists
            logger.warning("harness.audit: derived index update lagged (record durable): %s", e)
            self._note("index_errors")

    def _note(self, field: str) -> None:
        try:
            self._r.hincrby(_METRICS_KEY, field, 1)
        except Exception:
            pass

    def note_error(self) -> None:
        self._note("backend_errors")

    def _record_key_count(self, cap: int = 1_000_000) -> int:
        try:
            n = 0
            for _ in self._r.scan_iter(match=_RECORD_PREFIX + "*", count=1000):
                n += 1
                if n >= cap:
                    break
            return n
        except Exception:
            return -1

    def counts(self) -> dict[str, Any]:
        try:
            raw = self._r.hgetall(_METRICS_KEY) or {}
            h = {_to_str(k): int(_to_str(v)) for k, v in raw.items()}
            by_family = {k[7:]: v for k, v in h.items() if k.startswith("family:")}
            by_mode = {k[5:]: v for k, v in h.items() if k.startswith("mode:")}
            authoritative = self._record_key_count()
            derived = h.get("records_created", 0)
            return {
                "backend": self.name,
                "total": authoritative,  # AUTHORITATIVE record-key count
                "authoritative_records": authoritative,
                "derived_records_created": derived,  # from the best-effort index
                "index_lag": (authoritative - derived) if authoritative >= 0 else None,
                "duplicates_suppressed": h.get("duplicates_suppressed", 0),
                "backend_errors": h.get("backend_errors", 0),
                "script_errors": h.get("script_errors", 0),
                "index_errors": h.get("index_errors", 0),
                "oversize_rejections": h.get("oversize_rejections", 0),
                "stream_length": self._safe_xlen(),
                "by_family": by_family,
                "by_mode": by_mode,
            }
        except Exception as e:
            raise AuditBackendUnavailable(f"counts failed: {e}") from e

    def _safe_xlen(self) -> int:
        try:
            return int(self._r.xlen(_STREAM_KEY))
        except Exception:
            return -1

    def reconcile(self, dry_run: bool = True, cap: int = 1_000_000) -> dict[str, Any]:
        """Idempotently rebuild derived stream/metrics from authoritative records.
        Never modifies authoritative records; never creates duplicate index entries."""
        seen_stream = set()
        try:
            for _id, fields in self._r.xrange(_STREAM_KEY):
                rk = fields.get(b"rk") or fields.get("rk")
                if rk is not None:
                    seen_stream.add(_to_str(rk))
        except Exception:
            pass
        missing = []
        fam_counts: dict[str, int] = {}
        mode_counts: dict[str, int] = {}
        total = 0
        try:
            for key in self._r.scan_iter(match=_RECORD_PREFIX + "*", count=1000):
                total += 1
                if total > cap:
                    break
                kstr = _to_str(key)
                dk = kstr[len(_RECORD_PREFIX) :]
                try:
                    rec = json.loads(_to_str(self._r.get(kstr)))
                    env = rec.get("envelope") or {}
                    fam = str(env.get("source_loop") or env.get("kind") or "unknown")
                    mode = str(env.get("mode") or env.get("kind") or "unknown")
                except Exception:
                    fam = mode = "unknown"
                fam_counts[fam] = fam_counts.get(fam, 0) + 1
                mode_counts[mode] = mode_counts.get(mode, 0) + 1
                if dk not in seen_stream:
                    missing.append(dk)
        except Exception as e:
            raise AuditBackendUnavailable(f"reconcile scan failed: {e}") from e
        if not dry_run:
            for dk in missing:
                try:
                    self._r.xadd(_STREAM_KEY, {"rk": dk}, maxlen=stream_maxlen(), approximate=True)
                except Exception:
                    pass
            try:
                self._r.delete(_METRICS_KEY)
                self._r.hset(_METRICS_KEY, "records_created", total)
                for f, c in fam_counts.items():
                    self._r.hset(_METRICS_KEY, f"family:{f}", c)
                for m, c in mode_counts.items():
                    self._r.hset(_METRICS_KEY, f"mode:{m}", c)
            except Exception:
                pass
        return {
            "dry_run": dry_run,
            "authoritative_records": total,
            "missing_stream_entries": len(missing),
            "by_family": fam_counts,
            "by_mode": mode_counts,
        }

    def health(self) -> dict[str, Any]:
        try:
            self._r.ping()
            return {
                "backend": self.name,
                "healthy": True,
                "selected_intentionally": True,
                "fallback_active": False,
                "durable": True,
                "multi_worker_safe": True,
                "configuration_valid": True,
            }
        except Exception as e:
            return {
                "backend": self.name,
                "healthy": False,
                "error": str(e)[:120],
                "fallback_active": False,
                "durable": True,
                "multi_worker_safe": True,
                "configuration_valid": True,
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
    """Construct the selected backend. Strict: invalid config -> InvalidBackend
    (fail-closed). redis with no reachable client -> AuditBackendUnavailable.
    NEVER silently falls back to jsonl for redis/invalid."""
    cfg = resolve_backend_config()
    resolved = cfg["resolved_backend"]
    if resolved == "invalid":
        return InvalidBackend(cfg["configured_value"])
    if resolved == "redis":
        return RedisBackend(client if client is not None else _get_redis_client())
    return JsonlBackend()


def write(row: dict[str, Any], *, backend: AuditBackend | None = None) -> dict[str, Any]:
    """Atomic dedup + durable append for one audit row. NEVER raises — a durable
    failure is reported as a fail-closed dropped observation (written=False, error
    set) so the caller can emit an operational error without touching legacy."""
    dk = derive_dedup_key(row)  # derive BEFORE size-capping so identity is stable
    row = enforce_size(row)
    try:
        be = backend if backend is not None else get_backend()
    except AuditBackendUnavailable as e:
        logger.error("harness.audit: backend unavailable (fail-closed, dropped): %s", e)
        return {
            "written": False,
            "duplicate": False,
            "event_id": None,
            "backend": backend_name(),
            "error": str(e),
        }
    try:
        res = be.record(row, dk)
        return {
            "written": bool(res.get("written")),
            "duplicate": bool(res.get("duplicate")),
            "event_id": res.get("event_id"),
            "backend": be.name,
            "error": None,
        }
    except AuditBackendUnavailable as e:
        if hasattr(be, "note_error"):
            try:
                be.note_error()  # type: ignore[attr-defined]
            except Exception:
                pass
        logger.error("harness.audit: durable write failed closed (dropped): %s", e)
        return {
            "written": False,
            "duplicate": False,
            "event_id": None,
            "backend": be.name,
            "error": str(e),
        }


def status() -> dict[str, Any]:
    """Read-only backend status for the harness status surface (no secrets)."""
    cfg = resolve_backend_config()
    out: dict[str, Any] = {
        "backend": cfg["resolved_backend"],
        "configured_value": cfg["configured_value"],
        "configuration_valid": cfg["configuration_valid"],
        "app_version": _env("APP_VERSION", "") or _env("GIT_SHA", ""),
        "audit_retention_s": audit_retention_s(),
        "stream_maxlen": stream_maxlen(),
        "max_event_bytes": max_event_bytes(),
    }
    try:
        be = get_backend()
        out["health"] = be.health()
        out["counts"] = be.counts()
    except AuditBackendUnavailable as e:
        out["health"] = {
            "backend": cfg["resolved_backend"],
            "healthy": False,
            "error": str(e)[:120],
        }
        out["counts"] = None
    return out
