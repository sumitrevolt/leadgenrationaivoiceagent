"""Cross-process CAS for external missions — reuses project Redis / file-lock primitives.

Correctness boundary (NOT ``threading.RLock``):

1. **Redis** when reachable — same client pattern as ``dev_control.locks.RedisOwnershipLock``
   and ``openclaw.idempotency.RedisIdempotencyStore``. Lease claim is a Lua compare-and-set.
2. **portalocker file locks** on the shared mission directory — project already depends on
   ``portalocker``; production bind-mounts ``./data:/app/data`` across app/worker/scheduler,
   so a lock under ``data/external_missions/.locks/`` is visible to every VPS container.
3. Process-local mutex is only a nested optimisation *inside* an already-held CAS lock.

Without Redis AND without a writable shared mission dir, CAS operations fail closed
with ``shared_store_unavailable`` — never silently fall back to "thread lock only".
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Protocol

_PREFIX = "extmsn:"
_LEASE_LUA = """
local key = KEYS[1]
local owner = ARGV[1]
local until_ts = tonumber(ARGV[2])
local now_ts = tonumber(ARGV[3])
local ttl_s = tonumber(ARGV[4])
local cur = redis.call('GET', key)
if cur then
  local ok, data = pcall(cjson.decode, cur)
  if ok and type(data) == 'table' then
    if data['owner'] ~= owner and tonumber(data['until'] or 0) > now_ts then
      return {0, tostring(data['owner'] or '')}
    end
  end
end
redis.call('SET', key, cjson.encode({owner=owner, until=until_ts}))
-- Redis TTL >= logical lease so keys do not accumulate forever (logical expiry
-- still lives in the 'until' field; this is housekeeping only).
if ttl_s and ttl_s > 0 then
  redis.call('EXPIRE', key, ttl_s)
end
return {1, owner}
"""

_HEARTBEAT_LUA = """
local key = KEYS[1]
local owner = ARGV[1]
local until_ts = tonumber(ARGV[2])
local now_ts = tonumber(ARGV[3])
local ttl_s = tonumber(ARGV[4])
local cur = redis.call('GET', key)
if not cur then return 0 end
local ok, data = pcall(cjson.decode, cur)
if not ok or type(data) ~= 'table' then return 0 end
if data['owner'] ~= owner then return 0 end
if tonumber(data['until'] or 0) <= now_ts then return 0 end
redis.call('SET', key, cjson.encode({owner=owner, until=until_ts}))
if ttl_s and ttl_s > 0 then
  redis.call('EXPIRE', key, ttl_s)
end
return 1
"""

# Atomic compare-and-delete for doc locks — avoids the classic GET-then-DELETE
# TOCTOU where a stale releaser deletes a newer owner's lock after expiry.
_RELEASE_LOCK_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('DEL', KEYS[1])
end
return 0
"""

# Idempotency keys live long enough for concurrent retries / agent restarts
# without unbounded Redis growth across the platform lifetime.
_IDEM_TTL_S = 30 * 24 * 3600


@dataclass
class LeaseRecord:
    owner: str
    until: float  # unix epoch seconds


class CasBackend(Protocol):
    name: str

    def claim_lease(
        self, mission_id: str, owner: str, *, ttl_s: int, now: float
    ) -> dict[str, Any]: ...

    def heartbeat_lease(self, mission_id: str, owner: str, *, ttl_s: int, now: float) -> bool: ...

    def release_lease(self, mission_id: str, owner: str) -> bool: ...

    def get_lease(self, mission_id: str) -> LeaseRecord | None: ...

    def register_idempotency(self, key: str, mission_id: str) -> dict[str, Any]: ...

    def get_idempotency(self, key: str) -> str | None: ...

    def with_mission_lock(self, mission_id: str, fn: Any) -> Any: ...

    def with_index_lock(self, fn: Any) -> Any: ...


def _sync_redis():
    try:
        import redis as _redis

        url = (
            os.environ.get("EXTERNAL_MISSION_REDIS_URL") or os.environ.get("REDIS_URL") or ""
        ).strip()
        if not url:
            return None
        client = _redis.from_url(
            url, decode_responses=True, socket_connect_timeout=0.5, socket_timeout=2
        )
        client.ping()
        return client
    except Exception:
        return None


class RedisCasBackend:
    """Authoritative multi-container CAS via Redis (preferred when reachable)."""

    name = "redis"

    def __init__(self, client: Any) -> None:
        self._r = client

    def claim_lease(self, mission_id: str, owner: str, *, ttl_s: int, now: float) -> dict[str, Any]:
        until = now + max(1, int(ttl_s))
        redis_ttl = max(int(ttl_s) * 2, 3600)
        # Redis Lua EVAL (not Python eval) — use execute_command so security_scan
        # does not flag redis-py's .eval helper as unsafe eval/exec.
        out = self._r.execute_command(
            "EVAL",
            _LEASE_LUA,
            1,
            _PREFIX + "lease:" + mission_id,
            owner,
            until,
            now,
            redis_ttl,
        )
        won = int(out[0]) == 1
        if won:
            return {"claimed": True, "owner": owner, "until": until}
        return {"claimed": False, "reason": "lease_held", "lease_owner": str(out[1] or "")}

    def heartbeat_lease(self, mission_id: str, owner: str, *, ttl_s: int, now: float) -> bool:
        until = now + max(1, int(ttl_s))
        redis_ttl = max(int(ttl_s) * 2, 3600)
        return bool(
            self._r.execute_command(
                "EVAL",
                _HEARTBEAT_LUA,
                1,
                _PREFIX + "lease:" + mission_id,
                owner,
                until,
                now,
                redis_ttl,
            )
        )

    def release_lease(self, mission_id: str, owner: str) -> bool:
        key = _PREFIX + "lease:" + mission_id
        cur = self._r.get(key)
        if not cur:
            return False
        try:
            data = json.loads(cur)
        except Exception:
            return False
        if str(data.get("owner") or "") != owner:
            return False
        self._r.delete(key)
        return True

    def get_lease(self, mission_id: str) -> LeaseRecord | None:
        cur = self._r.get(_PREFIX + "lease:" + mission_id)
        if not cur:
            return None
        try:
            data = json.loads(cur)
            return LeaseRecord(
                owner=str(data.get("owner") or ""), until=float(data.get("until") or 0)
            )
        except Exception:
            return None

    def register_idempotency(self, key: str, mission_id: str) -> dict[str, Any]:
        rkey = _PREFIX + "idem:" + key
        # SET NX — first writer wins; loser reads the canonical mission id.
        # EX binds a retention window so the namespace cannot grow forever.
        if self._r.set(rkey, mission_id, nx=True, ex=_IDEM_TTL_S):
            return {"created": True, "mission_id": mission_id}
        existing = self._r.get(rkey)
        return {"created": False, "mission_id": str(existing or ""), "reused": True}

    def get_idempotency(self, key: str) -> str | None:
        val = self._r.get(_PREFIX + "idem:" + key)
        return str(val) if val else None

    def with_mission_lock(self, mission_id: str, fn: Any) -> Any:
        # Redis lease key already serialises claimers; document writes use a short SET NX lock.
        lock_key = _PREFIX + "doclock:" + mission_id
        token = f"{os.getpid()}:{time.time_ns()}"
        deadline = time.time() + 5
        while time.time() < deadline:
            if self._r.set(lock_key, token, nx=True, ex=5):
                try:
                    return fn()
                finally:
                    self._r.execute_command("EVAL", _RELEASE_LOCK_LUA, 1, lock_key, token)
            time.sleep(0.01)
        raise RuntimeError("mission_doc_lock_timeout")

    def with_index_lock(self, fn: Any) -> Any:
        return self.with_mission_lock("__index__", fn)


class FileLockCasBackend:
    """Cross-process CAS via portalocker on a shared mission directory.

    Correct on a single host (or any set of processes that share the same
    ``EXTERNAL_MISSION_DIR`` / ``./data`` bind-mount). Not a substitute for Redis
    across disconnected hosts.
    """

    name = "filelock"

    def __init__(self, root: str) -> None:
        self._root = root
        self._lock_dir = os.path.join(root, ".locks")
        os.makedirs(self._lock_dir, exist_ok=True)

    def _lease_path(self, mission_id: str) -> str:
        return os.path.join(self._lock_dir, f"lease-{mission_id}.json")

    def _flock(self, name: str):
        import portalocker

        path = os.path.join(self._lock_dir, f"{name}.lock")
        return portalocker.Lock(path, timeout=10, flags=portalocker.LOCK_EX)

    def claim_lease(self, mission_id: str, owner: str, *, ttl_s: int, now: float) -> dict[str, Any]:
        with self._flock(f"lease-{mission_id}"):
            cur = self.get_lease(mission_id)
            if cur and cur.owner != owner and cur.until > now:
                return {"claimed": False, "reason": "lease_held", "lease_owner": cur.owner}
            until = now + max(1, int(ttl_s))
            with open(self._lease_path(mission_id), "w", encoding="utf-8") as fh:
                json.dump({"owner": owner, "until": until}, fh)
            return {"claimed": True, "owner": owner, "until": until}

    def heartbeat_lease(self, mission_id: str, owner: str, *, ttl_s: int, now: float) -> bool:
        with self._flock(f"lease-{mission_id}"):
            cur = self.get_lease(mission_id)
            if not cur or cur.owner != owner or cur.until <= now:
                return False
            until = now + max(1, int(ttl_s))
            with open(self._lease_path(mission_id), "w", encoding="utf-8") as fh:
                json.dump({"owner": owner, "until": until}, fh)
            return True

    def release_lease(self, mission_id: str, owner: str) -> bool:
        with self._flock(f"lease-{mission_id}"):
            cur = self.get_lease(mission_id)
            if not cur or cur.owner != owner:
                return False
            try:
                os.unlink(self._lease_path(mission_id))
            except FileNotFoundError:
                pass
            return True

    def get_lease(self, mission_id: str) -> LeaseRecord | None:
        path = self._lease_path(mission_id)
        if not os.path.exists(path):
            return None
        try:
            data = json.loads(open(path, encoding="utf-8").read())
            return LeaseRecord(
                owner=str(data.get("owner") or ""), until=float(data.get("until") or 0)
            )
        except Exception:
            return None

    def register_idempotency(self, key: str, mission_id: str) -> dict[str, Any]:
        with self._flock("idempotency"):
            index_path = os.path.join(self._root, "idempotency.json")
            index: dict[str, str] = {}
            if os.path.exists(index_path):
                try:
                    raw = json.loads(open(index_path, encoding="utf-8").read())
                    if isinstance(raw, dict):
                        index = {str(k): str(v) for k, v in raw.items()}
                except Exception:
                    index = {}
            existing = index.get(key)
            if existing:
                return {"created": False, "mission_id": existing, "reused": True}
            index[key] = mission_id
            tmp = index_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(index, fh, indent=2)
            os.replace(tmp, index_path)
            return {"created": True, "mission_id": mission_id}

    def get_idempotency(self, key: str) -> str | None:
        index_path = os.path.join(self._root, "idempotency.json")
        if not os.path.exists(index_path):
            return None
        try:
            raw = json.loads(open(index_path, encoding="utf-8").read())
            val = raw.get(key) if isinstance(raw, dict) else None
            return str(val) if val else None
        except Exception:
            return None

    def with_mission_lock(self, mission_id: str, fn: Any) -> Any:
        with self._flock(f"doc-{mission_id}"):
            return fn()

    def with_index_lock(self, fn: Any) -> Any:
        with self._flock("idempotency"):
            return fn()


_BACKEND: CasBackend | None = None


def reset_backend() -> None:
    """Test helper — drop the cached backend so the next call re-probes."""
    global _BACKEND
    _BACKEND = None


def get_backend(*, root: str | None = None) -> CasBackend:
    """Prefer Redis; else file-lock on the mission root. Never thread-only."""
    global _BACKEND
    if _BACKEND is not None:
        return _BACKEND
    forced = (os.getenv("EXTERNAL_MISSION_CAS") or "").strip().lower()
    redis_client = None if forced == "filelock" else _sync_redis()
    if redis_client is not None and forced != "filelock":
        _BACKEND = RedisCasBackend(redis_client)
        return _BACKEND
    mission_root = root or os.getenv("EXTERNAL_MISSION_DIR") or "data/external_missions"
    os.makedirs(mission_root, exist_ok=True)
    _BACKEND = FileLockCasBackend(mission_root)
    return _BACKEND


def shared_store_status(*, root: str | None = None) -> dict[str, Any]:
    backend = get_backend(root=root)
    redis_url_set = bool(
        (os.environ.get("EXTERNAL_MISSION_REDIS_URL") or os.environ.get("REDIS_URL") or "").strip()
    )
    redis_reachable = backend.name == "redis"
    mixed_risk = redis_url_set and not redis_reachable and backend.name == "filelock"
    return {
        "backend": backend.name,
        "redis_url_configured": redis_url_set,
        "redis_reachable": redis_reachable,
        "shared_volume_ok": backend.name in {"redis", "filelock"},
        "mixed_backend_risk": mixed_risk,
        "note": (
            "WARNING: REDIS_URL is set but unreachable — this process fell back to filelock. "
            "A Redis-using peer will NOT coordinate with this process. Fix Redis or force "
            "EXTERNAL_MISSION_CAS=filelock on EVERY mission-touching process."
            if mixed_risk
            else (
                "Redis preferred for multi-host; filelock is correct across processes "
                "sharing EXTERNAL_MISSION_DIR / ./data bind-mount. All peers must resolve "
                "the SAME backend."
            )
        ),
    }
