"""admin_pipeline_overrides.py — real, persisted admin annotations on a pipeline
item (owner/next-action/stuck-resolved/status) WITHOUT a schema/migration
change.

Same sidecar pattern as approvals_bridge.py / app.platform.lead_overrides
(append-only jsonl, collapse-to-latest, field-level merge so a later partial
update never erases an earlier one). Admin-scoped (no client_id — this is the
internal admin cockpit, not the customer-facing Kanban in
app.platform.lead_overrides, which stays untouched).

For a DEAL-type item, "move to next stage" is delegated to the REAL existing
`app.marketing.sales_pipeline.set_stage()` — never duplicated here. This
module only covers the 3 things that have no other backing store: owner
assignment, a next-action note, and stuck-resolved acknowledgement — plus a
lead's status override (LeadStatus-bounded), since no admin Lead-mutation
endpoint exists in this codebase (verified) and adding one would mean writing
to the same `leads` table the live telephony/voice pipeline writes to.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_STORE = os.path.join("data", "pipeline_admin_overrides.jsonl")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_jsonl(path: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            out.append(json.loads(line))
                        except Exception:
                            pass
    except Exception:
        pass
    return out


def _append(rec: dict[str, Any]) -> None:
    try:
        os.makedirs("data", exist_ok=True)
        with open(_STORE, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.debug("[pipeline_overrides] write skip: %s", e)


def read_all_overrides() -> dict[str, dict[str, Any]]:
    """item_id -> merged override (later non-None fields win over earlier ones).
    One file read — office_hq calls this ONCE per snapshot, not per item."""
    out: dict[str, dict[str, Any]] = {}
    for r in _read_jsonl(_STORE):
        iid = str(r.get("item_id") or "")
        if not iid:
            continue
        cur = out.setdefault(iid, {})
        for k, v in r.items():
            if k in ("item_id",):
                continue
            if v is not None:
                cur[k] = v
    return out


def get_override(item_id: str) -> dict[str, Any]:
    return read_all_overrides().get(str(item_id), {})


def set_owner(item_id: str, agent_key: str, by: str = "admin") -> dict[str, Any]:
    if not item_id or not agent_key:
        return {"ok": False, "error": "item_id and agent_key required"}
    rec = {"item_id": str(item_id), "owner_agent": agent_key, "by": by[:80], "at": _now_iso()}
    _append(rec)
    return {"ok": True, **rec}


def set_next_action(item_id: str, note: str, by: str = "admin") -> dict[str, Any]:
    if not item_id:
        return {"ok": False, "error": "item_id required"}
    rec = {
        "item_id": str(item_id),
        "next_action": (note or "")[:300],
        "by": by[:80],
        "at": _now_iso(),
    }
    _append(rec)
    return {"ok": True, **rec}


def mark_stuck_resolved(item_id: str, by: str = "admin") -> dict[str, Any]:
    if not item_id:
        return {"ok": False, "error": "item_id required"}
    rec = {
        "item_id": str(item_id),
        "stuck_resolved_at": _now_iso(),
        "by": by[:80],
        "at": _now_iso(),
    }
    _append(rec)
    return {"ok": True, **rec}


# LeadStatus values (kept as a plain tuple, not an import of the ORM enum, so
# this module has zero DB coupling — office_hq validates against the real
# enum before calling into the DB layer; this list is just for admin API
# input validation at the router edge).
LEAD_STATUS_VALUES = (
    "new",
    "contacted",
    "qualified",
    "appointment",
    "callback",
    "not_interested",
    "wrong_number",
    "dnd",
    "converted",
    "lost",
)


def set_status_override(item_id: str, status: str, by: str = "admin") -> dict[str, Any]:
    if not item_id:
        return {"ok": False, "error": "item_id required"}
    if status not in LEAD_STATUS_VALUES:
        return {"ok": False, "error": f"status must be one of {LEAD_STATUS_VALUES}"}
    rec = {"item_id": str(item_id), "status_override": status, "by": by[:80], "at": _now_iso()}
    _append(rec)
    return {"ok": True, **rec}
