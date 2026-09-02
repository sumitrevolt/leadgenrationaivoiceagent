"""Tenant-scoped creative asset registry with provenance + revocation."""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_LOCK = threading.Lock()
_DEFAULT_DIR = os.path.join("data", "creative_os", "assets")


def _root() -> str:
    return os.getenv("CREATIVE_ASSET_ROOT", _DEFAULT_DIR)


def _tenant_path(tenant_id: str) -> str:
    safe = "".join(c for c in (tenant_id or "") if c.isalnum() or c in "-_")[:60]
    return os.path.join(_root(), safe or "_invalid")


@dataclass
class AssetRecord:
    asset_id: str
    tenant_id: str
    source_type: str  # upload|generated|import|parent_derive
    ref: str  # local path or object key (never cross-tenant)
    sha256: str
    mime_type: str
    width: int = 0
    height: int = 0
    duration_s: float = 0.0
    consent_status: str = "unknown"  # unknown|granted|denied|revoked
    licence: str = "unknown"
    model_provider: str = ""
    parent_asset_ids: list[str] = field(default_factory=list)
    created_at: float = 0.0
    revoked: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> AssetRecord:
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in (d or {}).items() if k in known})


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data or b"").hexdigest()


def register_asset(
    *,
    tenant_id: str,
    source_type: str,
    ref: str,
    sha256: str,
    mime_type: str,
    width: int = 0,
    height: int = 0,
    duration_s: float = 0.0,
    consent_status: str = "unknown",
    licence: str = "unknown",
    model_provider: str = "",
    parent_asset_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Register an asset for a tenant. Never raises — returns {ok,...} or {ok:False}."""
    try:
        tid = (tenant_id or "").strip()
        if not tid:
            return {"ok": False, "error": "tenant_id required"}
        if not sha256 or len(sha256) < 16:
            return {"ok": False, "error": "sha256 required"}
        if not ref:
            return {"ok": False, "error": "ref required"}
        rec = AssetRecord(
            asset_id=f"asset_{uuid.uuid4().hex[:12]}",
            tenant_id=tid,
            source_type=(source_type or "upload").strip(),
            ref=ref,
            sha256=sha256,
            mime_type=mime_type or "application/octet-stream",
            width=int(width or 0),
            height=int(height or 0),
            duration_s=float(duration_s or 0),
            consent_status=(consent_status or "unknown").strip().lower(),
            licence=(licence or "unknown").strip().lower(),
            model_provider=model_provider or "",
            parent_asset_ids=list(parent_asset_ids or []),
            created_at=time.time(),
            revoked=False,
        )
        path = _tenant_path(tid)
        os.makedirs(path, exist_ok=True)
        fp = os.path.join(path, f"{rec.asset_id}.json")
        with _LOCK:
            with open(fp, "w", encoding="utf-8") as f:
                json.dump(rec.to_dict(), f, ensure_ascii=False, indent=2)
        return {"ok": True, "asset": rec.to_dict()}
    except Exception as e:
        logger.warning(f"[creative_os.assets] register failed: {e}")
        return {"ok": False, "error": str(e)[:160]}


def get_asset(tenant_id: str, asset_id: str) -> dict[str, Any]:
    """Tenant-scoped resolve. Cross-tenant id = not_found (no leak)."""
    try:
        tid = (tenant_id or "").strip()
        aid = (asset_id or "").strip()
        if not tid or not aid:
            return {"ok": False, "error": "tenant_id and asset_id required"}
        fp = os.path.join(_tenant_path(tid), f"{aid}.json")
        if not os.path.isfile(fp):
            return {"ok": False, "error": "not_found"}
        with open(fp, encoding="utf-8") as f:
            data = json.load(f)
        rec = AssetRecord.from_dict(data)
        if rec.tenant_id != tid:
            return {"ok": False, "error": "tenant_mismatch"}
        if rec.revoked or rec.consent_status in ("denied", "revoked"):
            return {"ok": False, "error": "revoked", "asset_id": aid}
        return {"ok": True, "asset": rec.to_dict()}
    except Exception as e:
        return {"ok": False, "error": str(e)[:160]}


def resolve_asset_ref(tenant_id: str, asset_id: str) -> dict[str, Any]:
    """Resolve usable ref only for owning tenant; refuse cross-tenant."""
    got = get_asset(tenant_id, asset_id)
    if not got.get("ok"):
        return got
    asset = got["asset"]
    return {"ok": True, "ref": asset.get("ref"), "sha256": asset.get("sha256"), "asset": asset}


def revoke_asset(tenant_id: str, asset_id: str) -> dict[str, Any]:
    try:
        tid = (tenant_id or "").strip()
        aid = (asset_id or "").strip()
        fp = os.path.join(_tenant_path(tid), f"{aid}.json")
        if not os.path.isfile(fp):
            return {"ok": False, "error": "not_found"}
        with _LOCK:
            with open(fp, encoding="utf-8") as f:
                data = json.load(f)
            if str(data.get("tenant_id") or "") != tid:
                return {"ok": False, "error": "tenant_mismatch"}
            data["revoked"] = True
            data["consent_status"] = "revoked"
            with open(fp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        return {"ok": True, "asset_id": aid, "revoked": True}
    except Exception as e:
        return {"ok": False, "error": str(e)[:160]}


__all__ = [
    "AssetRecord",
    "get_asset",
    "register_asset",
    "resolve_asset_ref",
    "revoke_asset",
    "sha256_bytes",
    "sha256_file",
]
