"""Flow store — persist explorer builder flows for the Flow Runner.
JSONL at data/flow_runner/flows.jsonl (shared ./data bind-mount, web+worker).
Upsert by id (rewrite). Import-safe, never-raise.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_DIR = os.path.join("data", "flow_runner")
_PATH = os.path.join(_DIR, "flows.jsonl")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_all() -> dict[str, dict]:
    out: dict[str, dict] = {}
    try:
        if os.path.exists(_PATH):
            with open(_PATH, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                        fid = rec.get("id")
                        if fid:
                            out[fid] = rec
                    except Exception:
                        pass
    except Exception as e:
        logger.warning(f"[flow_store] read failed: {e}")
    return out


def _rewrite(flows: dict[str, dict]) -> bool:
    try:
        os.makedirs(_DIR, exist_ok=True)
        tmp = _PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            for rec in flows.values():
                f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        os.replace(tmp, _PATH)
        return True
    except Exception as e:
        logger.warning(f"[flow_store] rewrite failed: {e}")
        return False


def save_flow(flow: dict, by: str = "admin") -> dict:
    try:
        if not isinstance(flow, dict):
            return {"ok": False, "error": "flow must be an object"}
        fid = str(flow.get("id") or "").strip() or f"flow_{uuid.uuid4().hex[:8]}"
        rec = {
            "id": fid,
            "name": str(flow.get("name") or "Untitled flow")[:120],
            "nodes": flow.get("nodes") or [],
            "edges": flow.get("edges") or [],
            "created_by": str(flow.get("created_by") or by)[:60],
            "updated_at": _now(),
        }
        flows = _read_all()
        flows[fid] = rec
        if not _rewrite(flows):
            return {"ok": False, "error": "persist failed"}
        return {"ok": True, "flow": rec}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def get_flow(flow_id: str) -> dict | None:
    return _read_all().get((flow_id or "").strip())


def list_flows() -> list[dict]:
    out = []
    for rec in _read_all().values():
        out.append({
            "id": rec.get("id"),
            "name": rec.get("name"),
            "nodes": len(rec.get("nodes") or []),
            "edges": len(rec.get("edges") or []),
            "updated_at": rec.get("updated_at"),
        })
    return sorted(out, key=lambda r: r.get("updated_at") or "", reverse=True)


def delete_flow(flow_id: str) -> bool:
    fid = (flow_id or "").strip()
    flows = _read_all()
    if fid in flows:
        del flows[fid]
        return _rewrite(flows)
    return False
