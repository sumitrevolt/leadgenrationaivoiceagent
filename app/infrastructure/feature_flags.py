"""
feature_flags.py — Redis-backed per-tenant / percentage feature flags.
================================================================================
Phase 1 of the SaaS infra upgrade (docs/GAP_ANALYSIS_SaaS_Infra_Upgrade_2026.md).

KYUN: existing `AUTOMATION_FLAGS` (growth.py) GLOBAL env on/off hain (infra/automation
loops govern karte). Yeh module ALAG concern hai — PRODUCT/customer-facing features ka
RUNTIME, PER-TENANT, PERCENTAGE rollout (A/B + progressive launch + kill-switch) bina
redeploy ke.

MASTER GATE: env `FEATURE_FLAGS` (default OFF). OFF hone pe `is_enabled()` seedha False
return karta — ZERO Redis traffic, ZERO behaviour change. Admin flags pehle se configure
kar sakta; woh tabhi asar karte jab `FEATURE_FLAGS=1`. (Registry: AUTOMATION_FLAGS.)

STORAGE: ek single Redis key `feature_flags:store` = JSON {key: flag_dict}. Isse
InMemoryCache fallback (Redis down) ke saath bhi same code chalta — koi SCAN/KEYS nahi
chahiye (InMemoryCache woh support nahi karta). Reads 60s in-process cached (hot path);
writes rare (admin toggle) → read-modify-write acceptable (multi-worker eventual ≤60s).

FAIL-SAFE: koi bhi error / Redis-absent / unknown-flag → `is_enabled()` False (feature
chhupa = safe default — adhoora feature galti se expose na ho). Service KABHI raise nahi
karta (import-safe, caller kabhi nahi tutta).
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_STORE_KEY = "feature_flags:store"
_CACHE_TTL_S = 60.0


class FeatureState(str, Enum):
    """Flag ka rollout mode."""

    DISABLED = "disabled"
    ENABLED_ALL = "enabled_all"
    ENABLED_PERCENTAGE = "enabled_percentage"
    ENABLED_TENANTS = "enabled_tenants"

    @classmethod
    def coerce(cls, v: Any) -> FeatureState:
        try:
            return cls(str(v).strip().lower())
        except Exception:
            return cls.DISABLED


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class FeatureFlag:
    """Ek flag ka config. created_at update pe preserve hota."""

    key: str
    state: FeatureState = FeatureState.DISABLED
    description: str = ""
    percentage: int = 0  # 0-100, sirf ENABLED_PERCENTAGE me
    enabled_tenants: list[str] = field(default_factory=list)  # sirf ENABLED_TENANTS me
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "state": self.state.value if isinstance(self.state, FeatureState) else str(self.state),
            "description": self.description,
            "percentage": int(self.percentage),
            "enabled_tenants": list(self.enabled_tenants or []),
            "metadata": dict(self.metadata or {}),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> FeatureFlag:
        d = d or {}
        try:
            pct = max(0, min(100, int(d.get("percentage", 0) or 0)))
        except Exception:
            pct = 0
        tenants = d.get("enabled_tenants") or []
        if not isinstance(tenants, list):
            tenants = []
        meta = d.get("metadata")
        return cls(
            key=str(d.get("key") or ""),
            state=FeatureState.coerce(d.get("state")),
            description=str(d.get("description") or ""),
            percentage=pct,
            enabled_tenants=[str(t) for t in tenants],
            metadata=meta if isinstance(meta, dict) else {},
            created_at=str(d.get("created_at") or _now_iso()),
            updated_at=str(d.get("updated_at") or _now_iso()),
        )


def _bucket(flag_key: str, ident: str) -> int:
    """Deterministic 0-99 bucket.

    hashlib use karo — Python ka builtin hash() per-process SALTED hota
    (PYTHONHASHSEED), isliye workers/restarts ke beech NON-deterministic =
    percentage rollout flaky. sha256 stable + evenly distributed.
    """
    h = hashlib.sha256(f"{flag_key}:{ident}".encode("utf-8", "ignore")).hexdigest()
    return int(h[:8], 16) % 100


def evaluate_flag(
    flag: dict[str, Any] | None,
    tenant_id: str | None = None,
    user_id: str | None = None,
) -> bool:
    """PURE evaluation (storage-independent, testable). Kabhi raise nahi → False on doubt.  # nosecurity: eval-ref-in-comment

    Deterministic: same (flag, ident) → same result har process me.
    """
    try:
        if not flag:
            return False
        state = FeatureState.coerce(flag.get("state"))
        if state == FeatureState.DISABLED:
            return False
        if state == FeatureState.ENABLED_ALL:
            return True
        if state == FeatureState.ENABLED_TENANTS:
            tenants = flag.get("enabled_tenants") or []
            return bool(tenant_id) and str(tenant_id) in {str(t) for t in tenants}
        if state == FeatureState.ENABLED_PERCENTAGE:
            try:
                pct = int(flag.get("percentage", 0) or 0)
            except Exception:
                pct = 0
            if pct <= 0:
                return False
            if pct >= 100:
                return True
            ident = str(tenant_id or user_id or "")
            return _bucket(str(flag.get("key") or ""), ident) < pct
        return False
    except Exception:
        return False


def _system_active() -> bool:
    """Master gate — FEATURE_FLAGS env ON hone pe hi system live (default OFF)."""
    return os.environ.get("FEATURE_FLAGS", "0").strip().lower() in ("1", "true", "yes")


class FeatureFlagService:
    """Redis-backed flag store. redis_getter injectable (tests me InMemoryCache)."""

    def __init__(self, redis_getter: Callable | None = None):
        self._redis_getter = redis_getter
        self._cache: dict[str, Any] | None = None
        self._cache_at: float = 0.0

    async def _redis(self):
        """Shared app Redis (InMemoryCache fallback). Never raises → None."""
        try:
            if self._redis_getter is not None:
                return await self._redis_getter()
            from app.cache import get_redis_client

            return await get_redis_client()
        except Exception as e:
            logger.debug("[feature_flags] redis getter failed: %s", e)
            return None

    def _bust(self) -> None:
        self._cache = None
        self._cache_at = 0.0

    async def _load_store(self, force: bool = False) -> dict[str, Any]:
        """Whole {key: flag_dict} store. 60s in-process cache. Never raises → {} (ya last-good)."""
        if not force and self._cache is not None and (time.time() - self._cache_at) < _CACHE_TTL_S:
            return self._cache
        store: dict[str, Any] = {}
        try:
            r = await self._redis()
            if r is not None:
                raw = await r.get(_STORE_KEY)
                if raw:
                    if isinstance(raw, (bytes, bytearray)):
                        raw = raw.decode("utf-8", "ignore")
                    parsed = json.loads(raw)
                    if isinstance(parsed, dict):
                        store = parsed
        except Exception as e:
            logger.debug("[feature_flags] load failed: %s", e)
            store = self._cache or {}
        self._cache = store
        self._cache_at = time.time()
        return store

    async def _save_store(self, store: dict[str, Any]) -> bool:
        try:
            r = await self._redis()
            if r is None:
                return False
            await r.set(_STORE_KEY, json.dumps(store, ensure_ascii=False))
            self._cache = store
            self._cache_at = time.time()
            return True
        except Exception as e:
            logger.warning("[feature_flags] save failed: %s", e)
            return False

    async def is_enabled(
        self,
        flag_key: str,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> bool:
        """Master-gated, fail-safe (False on unknown/broken/off). Never raises."""
        try:
            if not flag_key or not _system_active():
                return False
            store = await self._load_store()
            return evaluate_flag(store.get(flag_key), tenant_id, user_id)
        except Exception:
            return False

    async def get_flag(self, flag_key: str) -> FeatureFlag | None:
        try:
            store = await self._load_store()
            d = store.get(flag_key)
            return FeatureFlag.from_dict(d) if d else None
        except Exception:
            return None

    async def get_all_flags(self) -> list[FeatureFlag]:
        try:
            store = await self._load_store(force=True)
            return [FeatureFlag.from_dict(v) for v in store.values()]
        except Exception:
            return []

    async def set_flag(self, flag: FeatureFlag) -> bool:
        """Upsert. created_at preserve, updated_at refresh. True = persisted.

        NOTE: master gate (FEATURE_FLAGS) yahan CHECK nahi hota — admin system OFF
        hone par bhi flags pre-configure kar sakta (woh ON hone par live honge).
        """
        try:
            if not flag or not flag.key:
                return False
            store = await self._load_store(force=True)
            existing = store.get(flag.key) or {}
            flag.created_at = str(existing.get("created_at") or flag.created_at or _now_iso())
            flag.updated_at = _now_iso()
            store[flag.key] = flag.to_dict()
            return await self._save_store(store)
        except Exception as e:
            logger.warning("[feature_flags] set_flag failed: %s", e)
            return False

    async def delete_flag(self, flag_key: str) -> bool:
        try:
            store = await self._load_store(force=True)
            if flag_key in store:
                store.pop(flag_key, None)
                return await self._save_store(store)
            return False
        except Exception:
            return False


# Shared singleton — callers: `from app.infrastructure.feature_flags import feature_flags`
feature_flags = FeatureFlagService()


async def is_enabled(
    flag_key: str, tenant_id: str | None = None, user_id: str | None = None
) -> bool:
    """Module-level convenience over the shared singleton."""
    return await feature_flags.is_enabled(flag_key, tenant_id, user_id)


__all__ = [
    "FeatureState",
    "FeatureFlag",
    "FeatureFlagService",
    "feature_flags",
    "is_enabled",
    "evaluate_flag",
]
