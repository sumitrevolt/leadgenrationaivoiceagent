"""File-ownership locks for the engineering control plane (Phase 3).

Two workers must never edit the same files concurrently. ``overlapping`` is a
pure conflict check; the backend classes provide TTL-bounded acquire/release.
A Redis backend is used when reachable (cross-process safety); otherwise an
in-memory backend keeps a single-process worker correct and tests hermetic.
"""

from __future__ import annotations

import threading
import time
from typing import Any


def overlapping(requested: list[str], held_by_others: list[str]) -> list[str]:
    """Return the sorted set of requested paths already held by someone else."""
    req = {p.strip() for p in requested if p and p.strip()}
    return sorted(req & {p.strip() for p in held_by_others if p and p.strip()})


class InMemoryOwnershipLock:
    """Process-local ownership lock — correct for a single worker; test backend."""

    def __init__(self) -> None:
        self._held: dict[str, tuple[str, float]] = {}
        self._mutex = threading.Lock()

    def _prune(self, now: float) -> None:
        for p in [p for p, (_o, exp) in self._held.items() if exp and exp < now]:
            del self._held[p]

    def acquire(self, owner: str, paths: list[str], ttl: int = 900) -> dict[str, Any]:
        clean = [p.strip() for p in paths if p and p.strip()]
        now = time.time()
        with self._mutex:
            self._prune(now)
            conflict = [p for p in clean if p in self._held and self._held[p][0] != owner]
            if conflict:
                return {"acquired": False, "conflict": sorted(conflict)}
            for p in clean:
                self._held[p] = (owner, now + ttl)
            return {"acquired": True, "conflict": []}

    def release(self, owner: str, paths: list[str]) -> None:
        with self._mutex:
            for p in [p.strip() for p in paths if p and p.strip()]:
                if p in self._held and self._held[p][0] == owner:
                    del self._held[p]

    def held(self) -> dict[str, str]:
        with self._mutex:
            self._prune(time.time())
            return {p: o for p, (o, _exp) in self._held.items()}


class RedisOwnershipLock:
    """Cross-process ownership lock via Redis SET NX + TTL (best-effort)."""

    def __init__(self, client: Any, prefix: str = "devlock:") -> None:
        self._r = client
        self._prefix = prefix

    def acquire(self, owner: str, paths: list[str], ttl: int = 900) -> dict[str, Any]:
        clean = [p.strip() for p in paths if p and p.strip()]
        acquired: list[str] = []
        for p in clean:
            key = self._prefix + p
            if self._r.set(key, owner, nx=True, ex=ttl):
                acquired.append(p)
            elif self._r.get(key) not in (
                owner,
                owner.encode() if isinstance(owner, str) else owner,
            ):
                # rollback partial acquisition, report conflict
                for a in acquired:
                    self._r.delete(self._prefix + a)
                return {"acquired": False, "conflict": [p]}
        return {"acquired": True, "conflict": []}

    def release(self, owner: str, paths: list[str]) -> None:
        for p in [p.strip() for p in paths if p and p.strip()]:
            key = self._prefix + p
            val = self._r.get(key)
            if val in (owner, owner.encode() if isinstance(owner, str) else owner):
                self._r.delete(key)


_DEFAULT = InMemoryOwnershipLock()


def default_lock() -> InMemoryOwnershipLock:
    return _DEFAULT


def get_lock() -> Any:
    """Prefer a reachable Redis backend; fall back to the in-memory backend."""
    try:
        import redis as _redis

        from app.config import settings

        client = _redis.from_url(settings.redis_url, socket_timeout=2)
        client.ping()
        return RedisOwnershipLock(client)
    except Exception:
        return _DEFAULT
