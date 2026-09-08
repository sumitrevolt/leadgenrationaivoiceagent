"""Lightweight JSONL/JSON creative store — tenant isolated, no runtime assets in git."""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any

from app.marketing.creative_os.spec import CreativeSpec

_LOCK = threading.Lock()
_DEFAULT_DIR = os.path.join("data", "creative_os", "ledger")

COCKPIT_STATUSES = (
    "queued",
    "generating",
    "qa_failed",
    "approval_pending",
    "approved",
    "scheduled",
    "published",
    "failed",
    "quarantined",
)


def _root() -> str:
    return os.getenv("CREATIVE_LEDGER_ROOT", _DEFAULT_DIR)


def _tenant_dir(tenant_id: str) -> str:
    safe = "".join(c for c in (tenant_id or "") if c.isalnum() or c in "-_")[:60]
    return os.path.join(_root(), safe or "_invalid")


def _path(tenant_id: str, creative_id: str) -> str:
    return os.path.join(_tenant_dir(tenant_id), f"{creative_id}.json")


def save_record(spec: CreativeSpec, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        tid = spec.tenant_id
        os.makedirs(_tenant_dir(tid), exist_ok=True)
        record = {
            "creative_id": spec.creative_id,
            "tenant_id": tid,
            "status": spec.status,
            "recipe": spec.recipe,
            "aspect_ratio": spec.aspect_ratio,
            "provider": spec.provider,
            "model_name": spec.model_name,
            "brand_revision": spec.brand_revision,
            "render_duration_ms": spec.render_duration_ms,
            "qa_ok": (spec.qa_results or {}).get("ok"),
            "approval_revision": spec.approval_revision,
            "output_hash": spec.output_hash,
            "output_asset_id": getattr(spec, "output_asset_id", "") or "",
            "job_id": getattr(spec, "job_id", "") or "",
            "publish_targets": list(spec.publish_targets or []),
            "failure_reason": spec.failure_reason,
            "updated_at": time.time(),
            "spec": spec.to_dict(),
        }
        if extra:
            record.update(extra)
        fp = _path(tid, spec.creative_id)
        with _LOCK:
            with open(fp, "w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, indent=2)
        return {"ok": True, "record": record}
    except Exception as e:
        return {"ok": False, "error": str(e)[:160]}


def get_record(tenant_id: str, creative_id: str) -> dict[str, Any]:
    try:
        fp = _path(tenant_id, creative_id)
        if not os.path.isfile(fp):
            return {"ok": False, "error": "not_found"}
        with open(fp, encoding="utf-8") as f:
            rec = json.load(f)
        if str(rec.get("tenant_id") or "") != str(tenant_id):
            return {"ok": False, "error": "tenant_mismatch"}
        return {"ok": True, "record": rec}
    except Exception as e:
        return {"ok": False, "error": str(e)[:160]}


def bump_revision(
    tenant_id: str,
    creative_id: str,
    *,
    note: str = "",
    clear_approval: bool = True,
) -> dict[str, Any]:
    got = get_record(tenant_id, creative_id)
    if not got.get("ok"):
        return got
    rec = got["record"]
    spec = CreativeSpec.from_dict(rec.get("spec") or {})
    spec.approval_revision = int(spec.approval_revision or 0) + 1
    spec.status = "approval_pending"
    spec.failure_reason = ""
    if note:
        spec.captions = dict(spec.captions or {})
        spec.captions["_change_note"] = note[:500]
    if clear_approval:
        rec.pop("approval", None)
        spec.output_hash = ""
    rec["approval"] = None if clear_approval else rec.get("approval")
    return save_record(spec, extra={"approval": None, "change_note": note[:500]})


def list_records(
    tenant_id: str = "",
    *,
    status: str = "",
    limit: int = 50,
) -> dict[str, Any]:
    try:
        rows: list[dict[str, Any]] = []
        root = _root()
        if not os.path.isdir(root):
            return {"ok": True, "items": [], "counts": dict.fromkeys(COCKPIT_STATUSES, 0)}
        tenants = (
            [tenant_id]
            if tenant_id
            else [d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d))]
        )
        for tid in tenants:
            tdir = _tenant_dir(tid)
            if not os.path.isdir(tdir):
                continue
            for name in os.listdir(tdir):
                if not name.endswith(".json"):
                    continue
                try:
                    with open(os.path.join(tdir, name), encoding="utf-8") as f:
                        rec = json.load(f)
                    if status and str(rec.get("status") or "") != status:
                        continue
                    rows.append(
                        {
                            "creative_id": rec.get("creative_id"),
                            "tenant_id": rec.get("tenant_id"),
                            "status": rec.get("status"),
                            "recipe": rec.get("recipe"),
                            "aspect_ratio": rec.get("aspect_ratio"),
                            "provider": rec.get("provider"),
                            "model_name": rec.get("model_name"),
                            "brand_revision": rec.get("brand_revision"),
                            "render_duration_ms": rec.get("render_duration_ms"),
                            "qa_ok": rec.get("qa_ok"),
                            "approval_revision": rec.get("approval_revision"),
                            "output_hash": (rec.get("output_hash") or "")[:16],
                            "publish_targets": rec.get("publish_targets") or [],
                            "failure_reason": rec.get("failure_reason") or "",
                        }
                    )
                except Exception:
                    continue
        rows.sort(key=lambda r: r.get("creative_id") or "", reverse=True)
        counts = dict.fromkeys(COCKPIT_STATUSES, 0)
        for r in rows:
            st = str(r.get("status") or "")
            if st in counts:
                counts[st] += 1
        return {"ok": True, "items": rows[: max(1, limit)], "counts": counts}
    except Exception as e:
        return {"ok": False, "error": str(e)[:160], "items": [], "counts": {}}


def budget_count_today(tenant_id: str) -> int:
    """Count generations today (UTC day) for tenant budget enforcement."""
    try:
        import datetime as _dt

        day = _dt.datetime.utcnow().strftime("%Y-%m-%d")
        tdir = _tenant_dir(tenant_id)
        if not os.path.isdir(tdir):
            return 0
        n = 0
        for name in os.listdir(tdir):
            if not name.endswith(".json"):
                continue
            try:
                with open(os.path.join(tdir, name), encoding="utf-8") as f:
                    rec = json.load(f)
                ts = float(rec.get("updated_at") or 0)
                if _dt.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d") == day:
                    n += 1
            except Exception:
                continue
        return n
    except Exception:
        return 0


__all__ = [
    "COCKPIT_STATUSES",
    "budget_count_today",
    "bump_revision",
    "get_record",
    "list_records",
    "save_record",
]
