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
_HISTORY_DIR = os.path.join(_DIR, "flow_history")
_MAX_HISTORY_PER_FLOW = 20  # bounded — oldest snapshot trimmed on overflow


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
        out["cron"] = str(t.get("cron") or "").strip()[:64]  # "*/5 * * * *" OR "HH:MM" IST
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


def _history_path(flow_id: str) -> str:
    safe = "".join(c for c in (flow_id or "") if c.isalnum() or c in "-_")[:60]
    return os.path.join(_HISTORY_DIR, f"{safe}.jsonl")


def _read_history(flow_id: str) -> list[dict]:
    out: list[dict] = []
    try:
        p = _history_path(flow_id)
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        out.append(json.loads(line))
                    except Exception:
                        pass
    except Exception as e:
        logger.warning(f"[flow_store] history read failed {flow_id}: {e}")
    return out


def _archive_version(prior: dict) -> None:
    """Append `prior` (the record being superseded) to its flow's history, bounded
    to _MAX_HISTORY_PER_FLOW (oldest dropped). Never raises."""
    try:
        fid = str(prior.get("id") or "").strip()
        if not fid:
            return
        os.makedirs(_HISTORY_DIR, exist_ok=True)
        rows = _read_history(fid)
        rows.append(prior)
        rows = rows[-_MAX_HISTORY_PER_FLOW:]
        tmp = _history_path(fid) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            for rec in rows:
                f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        os.replace(tmp, _history_path(fid))
    except Exception as e:
        logger.warning(f"[flow_store] archive_version failed: {e}")


def save_flow(flow: dict, by: str = "admin", owner_client_id: str = "") -> dict:
    """Persist a flow. owner_client_id scopes it to a customer (Phase 7); admin
    flows pass "". On upsert, owner is preserved from the existing record unless a
    non-blank owner_client_id is supplied (callers must never let a customer's id
    be derived from the flow body — pass it explicitly from require_customer).

    Each overwrite archives the prior version to flow_history/<id>.jsonl (bounded)
    and bumps `version` — see list_versions()/rollback_flow() for recovery."""
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
                "version": int((existing or {}).get("version", 0)) + 1,
                "updated_at": _now(),
            }
            flows = _read_all()
            flows[fid] = rec
            if not _rewrite(flows):
                return {"ok": False, "error": "persist failed"}
            if existing:
                _archive_version(existing)
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
        out.append(
            {
                "id": rec.get("id"),
                "name": rec.get("name"),
                "nodes": len(rec.get("nodes") or []),
                "edges": len(rec.get("edges") or []),
                "trigger": (rec.get("trigger") or {}).get("type", "manual"),
                "owner": rec.get("owner_client_id") or "",
                "updated_at": rec.get("updated_at"),
            }
        )
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


def list_versions(flow_id: str) -> list[dict]:
    """Version history for a flow, newest first: archived snapshots + the live
    current record. Summaries only (no nodes/edges) — use get_version() for full body."""
    fid = (flow_id or "").strip()
    out = []
    current = _read_all().get(fid)
    if current:
        out.append(
            {
                "version": int(current.get("version", 1)),
                "name": current.get("name"),
                "updated_at": current.get("updated_at"),
                "created_by": current.get("created_by"),
                "current": True,
            }
        )
    for rec in _read_history(fid):
        out.append(
            {
                "version": int(rec.get("version", 0)),
                "name": rec.get("name"),
                "updated_at": rec.get("updated_at"),
                "created_by": rec.get("created_by"),
                "current": False,
            }
        )
    return sorted(out, key=lambda r: r.get("version", 0), reverse=True)


def get_version(flow_id: str, version: int) -> dict | None:
    """Full body (nodes/edges/trigger) of a specific past or current version, else None."""
    fid = (flow_id or "").strip()
    current = _read_all().get(fid)
    if current and int(current.get("version", 1)) == int(version):
        return current
    for rec in _read_history(fid):
        if int(rec.get("version", 0)) == int(version):
            return rec
    return None


def rollback_flow(flow_id: str, to_version: int, by: str = "admin") -> dict:
    """Restore a flow to an earlier version's content. Implemented as a fresh
    save_flow() call with the old body — this archives the (about-to-be-replaced)
    current version too, so rollback itself is undoable and version numbers only
    ever move forward (no ambiguity about "current" during a race)."""
    fid = (flow_id or "").strip()
    if not fid:
        return {"ok": False, "error": "flow_id required"}
    target = get_version(fid, to_version)
    if target is None:
        return {"ok": False, "error": f"version {to_version} not found for {fid}"}
    return save_flow(
        {
            "id": fid,
            "name": target.get("name"),
            "nodes": target.get("nodes") or [],
            "edges": target.get("edges") or [],
            "trigger": target.get("trigger"),
        },
        by=f"rollback-to-v{to_version}:{by}",
        owner_client_id="",
    )
