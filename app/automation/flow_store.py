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


def _norm_trigger(t) -> dict:
    """Normalise a flow trigger block. Default + invalid -> manual (Phase 3)."""
    t = t if isinstance(t, dict) else {}
    typ = str(t.get("type") or "manual").lower()
    if typ not in ("manual", "cron", "event"):
        typ = "manual"
    out = {"type": typ}
    if typ == "cron":
        out["cron"] = str(t.get("cron") or "").strip()[:64]   # "*/5 * * * *" OR "HH:MM" IST
    if typ == "event":
        out["event"] = str(t.get("event") or "").strip()[:40]  # one of the 4 dotted events
    return out


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


def save_flow(flow: dict, by: str = "admin", owner_client_id: str = "") -> dict:
    """Persist a flow. owner_client_id scopes it to a customer (Phase 7); admin
    flows pass "". On upsert, owner is preserved from the existing record unless a
    non-blank owner_client_id is supplied (callers must never let a customer's id
    be derived from the flow body — pass it explicitly from require_customer)."""
    try:
        if not isinstance(flow, dict):
            return {"ok": False, "error": "flow must be an object"}
        fid = str(flow.get("id") or "").strip() or f"flow_{uuid.uuid4().hex[:8]}"
        from app.utils.file_lock import file_lock

        # Lock the whole read-modify-write: _rewrite is atomic but does NOT serialize
        # the read->mutate->write across WEB_CONCURRENCY=2 workers, so a concurrent save
        # could silently drop the other writer's new flow (lost update).
        with file_lock(_PATH):
            existing = _read_all().get(fid)
            owner = str(owner_client_id or (existing or {}).get("owner_client_id") or "")[:60]
            rec = {
                "id": fid,
                "name": str(flow.get("name") or "Untitled flow")[:120],
                "nodes": flow.get("nodes") or [],
                "edges": flow.get("edges") or [],
                "trigger": _norm_trigger(flow.get("trigger")),
                "owner_client_id": owner,
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


def list_flows(owner: str | None = None) -> list[dict]:
    """List flow summaries. owner=None -> all (admin); owner="cli" -> only that
    customer's flows (Phase 7 tenant scoping)."""
    out = []
    for rec in _read_all().values():
        if owner is not None and str(rec.get("owner_client_id") or "") != owner:
            continue
        out.append({
            "id": rec.get("id"),
            "name": rec.get("name"),
            "nodes": len(rec.get("nodes") or []),
            "edges": len(rec.get("edges") or []),
            "trigger": (rec.get("trigger") or {}).get("type", "manual"),
            "owner": rec.get("owner_client_id") or "",
            "updated_at": rec.get("updated_at"),
        })
    return sorted(out, key=lambda r: r.get("updated_at") or "", reverse=True)


def list_flows_full(owner: str | None = None) -> list[dict]:
    """Raw flow records (incl. nodes/edges/trigger). owner filters by tenant."""
    recs = list(_read_all().values())
    if owner is not None:
        recs = [r for r in recs if str(r.get("owner_client_id") or "") == owner]
    return recs


def owned_by(flow_id: str, client_id: str) -> bool:
    """True iff flow exists AND is owned by client_id (Phase 7 tenant isolation)."""
    rec = _read_all().get((flow_id or "").strip())
    return bool(rec) and str(rec.get("owner_client_id") or "") == str(client_id or "")


def count_for_owner(client_id: str) -> int:
    cid = str(client_id or "")
    return sum(1 for r in _read_all().values() if str(r.get("owner_client_id") or "") == cid)


def delete_flow(flow_id: str) -> bool:
    fid = (flow_id or "").strip()
    from app.utils.file_lock import file_lock

    with file_lock(_PATH):  # serialize read-modify-write (else a concurrent save is lost)
        flows = _read_all()
        if fid in flows:
            del flows[fid]
            return _rewrite(flows)
    return False
