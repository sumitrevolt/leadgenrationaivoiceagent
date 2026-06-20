"""approvals_bridge.py — unified read+decide bridge over agentic draft streams.

Sub-project D V1 (bridge-first): surfaces the "rotting" agentic outputs
(sales_team deep-dives, coordinator draft runs, FDE deploy reports) into ONE
human-in-the-loop queue with risk-tiered smart 1-click actions. The already-
surfaced streams (code_upgrader patches, process breakpoints, self_improve)
keep their own endpoints — this bridge is ONLY for the three orphan streams.

Design (mirrors the code_upgrader gold-pattern):
- File-backed status sidecar data/approval_decisions.jsonl, read-on-each-call
  (NEVER an in-memory singleton — that is the verified self_improve
  ApprovalQueue bug where web vs worker process state diverged).
- Source files are NOT mutated; status lives only in the sidecar (collapse-to-
  latest by (source, item_id)).
- decide() stamps status + fires a BOUNDED SAFE next-action per source:
    sales       -> mark-reviewed (the real send stays 1-click manual / draft-only)
    coordinator -> push the plan's next-action to self_improve.add_task (internal)
    fde         -> enable the disabled drip-journey from the deploy report
- Risky real-send (rohan outreach at scale, swara calls) is NEVER in the
  approve path — draft-only by design (must-stay-manual).
- Never raises. One bad stream returns [] for that source only.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_DECISIONS = os.path.join("data", "approval_decisions.jsonl")
_COORD_RUNS = os.path.join("data", "coordination_runs.jsonl")
_FDE_DEPLOYS = os.path.join("data", "fde_deploys.jsonl")
_SOURCES = ("sales", "coordinator", "fde")


def _now_iso() -> str:
    return datetime.now().isoformat()


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


# --------------------------------------------------------------------------- #
# Status sidecar (collapse-to-latest, code_upgrader pattern)
# --------------------------------------------------------------------------- #
def _status_map() -> dict[tuple[str, str], dict[str, Any]]:
    """Latest decision per (source, item_id). Later rows overwrite earlier."""
    m: dict[tuple[str, str], dict[str, Any]] = {}
    for r in _read_jsonl(_DECISIONS):
        src, iid = str(r.get("source") or ""), str(r.get("item_id") or "")
        if src and iid:
            m[(src, iid)] = r
    return m


def _status_for(source: str, item_id: str, smap: dict | None = None) -> str:
    smap = smap if smap is not None else _status_map()
    r = smap.get((source, item_id))
    return str((r or {}).get("status") or "pending")


def _set_status(source: str, item_id: str, status: str, by: str = "admin") -> None:
    try:
        os.makedirs("data", exist_ok=True)
        with open(_DECISIONS, "a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "source": source,
                        "item_id": item_id,
                        "status": status,
                        "by": (by or "admin")[:80],
                        "at": _now_iso(),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    except Exception as e:
        logger.debug("[approvals] status write skip: %s", e)


# --------------------------------------------------------------------------- #
# Read adapters (each defensive -> [] on failure; never break the cockpit)
# --------------------------------------------------------------------------- #
def _drafts_sales(smap: dict) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        from app.agents import sales_team

        for r in sales_team.list_analyses(limit=20):
            pid = str(r.get("pid") or "")
            if not pid:
                continue
            body = ""
            md = r.get("md")
            if md:
                try:
                    if os.path.exists(md):
                        with open(md, encoding="utf-8") as f:
                            body = f.read()[:2000]
                except Exception:
                    body = ""
            out.append(
                {
                    "source": "sales",
                    "id": pid,
                    "title": f"{r.get('name') or pid} — {r.get('grade') or '?'} ({r.get('score') or 0}/100)",
                    "body": body
                    or f"{r.get('niche') or ''} · {r.get('city') or ''} · {r.get('phone') or ''}",
                    "created_at": r.get("ts") or "",
                    "status": _status_for("sales", pid, smap),
                    "meta": {
                        "phone": r.get("phone"),
                        "niche": r.get("niche"),
                        "city": r.get("city"),
                        "score": r.get("score"),
                    },
                }
            )
    except Exception as e:
        logger.debug("[approvals] sales adapter skip: %s", e)
    return out


def _drafts_coordinator(smap: dict) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        rows = _read_jsonl(_COORD_RUNS)

        # Draft runs only (execute falsy) with substance; recent cap = noise control.
        # NOTE: engineering_crew runs carry design/implementation_plan (NOT
        # summary/solution) — include those keys or the flagship mode is dropped.
        def _has_substance(r: dict) -> bool:
            return bool(
                r.get("summary")
                or r.get("solution")
                or r.get("design")
                or r.get("implementation_plan")
            )

        rows = [r for r in rows if not r.get("execute") and _has_substance(r)]
        for r in rows[-15:][::-1]:
            rid = str(r.get("run_id") or r.get("id") or "")
            if not rid:
                continue
            out.append(
                {
                    "source": "coordinator",
                    "id": rid,
                    "title": f"Plan: {(r.get('goal') or 'coordination')[:80]}",
                    "body": str(
                        r.get("summary")
                        or r.get("solution")
                        or r.get("design")
                        or r.get("implementation_plan")
                        or ""
                    )[:2000],
                    "created_at": r.get("at") or "",
                    "status": _status_for("coordinator", rid, smap),
                    # persisted runs use `pattern` (engineering_crew/hierarchical/...) not `mode`
                    "meta": {
                        "mode": r.get("pattern") or r.get("mode") or "sequential",
                        "goal": r.get("goal"),
                    },
                }
            )
    except Exception as e:
        logger.debug("[approvals] coordinator adapter skip: %s", e)
    return out


def _drafts_fde(smap: dict) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        for r in _read_jsonl(_FDE_DEPLOYS)[-20:][::-1]:
            rid = str(r.get("id") or "")
            if not rid:
                continue
            client = r.get("client") or {}
            steps = r.get("steps") or []
            summ = "; ".join(
                f"{s.get('title')}: {s.get('summary', '')}" for s in steps if isinstance(s, dict)
            )[:2000]
            out.append(
                {
                    "source": "fde",
                    "id": rid,
                    "title": f"FDE {r.get('agent') or ''} → {client.get('business_name') or 'client'} ({r.get('deployed', 0)}/{r.get('total', 0)})",
                    "body": summ,
                    "created_at": r.get("at") or "",
                    "status": _status_for("fde", rid, smap),
                    "meta": {
                        "client": client,
                        "deployed": r.get("deployed"),
                        "total": r.get("total"),
                    },
                }
            )
    except Exception as e:
        logger.debug("[approvals] fde adapter skip: %s", e)
    return out


def list_drafts(include_decided: bool = False) -> dict[str, Any]:
    """Merged agentic-draft queue. Pending-only by default."""
    smap = _status_map()
    drafts = _drafts_sales(smap) + _drafts_coordinator(smap) + _drafts_fde(smap)
    if not include_decided:
        drafts = [d for d in drafts if d.get("status") == "pending"]
    by_source: dict[str, int] = {}
    pending = 0
    for d in drafts:
        by_source[d["source"]] = by_source.get(d["source"], 0) + 1
        if d.get("status") == "pending":
            pending += 1
    return {"drafts": drafts, "counts": {"by_source": by_source, "pending": pending}}


# --------------------------------------------------------------------------- #
# Bounded SAFE next-actions on approve (risk-tiered; never an auto real-send)
# --------------------------------------------------------------------------- #
def _action_sales(item_id: str) -> str:
    # Real outbound send stays manual/draft-only (must-stay-manual). Approve = reviewed.
    return "marked-reviewed (send stays 1-click manual)"


def _action_coordinator(item_id: str) -> str:
    try:
        from app.agents import self_improve

        d = next((x for x in _drafts_coordinator(_status_map()) if x["id"] == item_id), None)
        goal = (
            ((d or {}).get("meta") or {}).get("goal")
            or (d or {}).get("title")
            or "coordinator plan"
        )
        self_improve.add_task(f"Approved coordinator plan — follow up: {goal}", source="approval")
        return "queued to self_improve"
    except Exception as e:
        logger.debug("[approvals] coordinator action skip: %s", e)
        return "reviewed (self_improve queue skip)"


def _action_fde(item_id: str) -> str:
    try:
        from app.marketing import journeys

        jid = ""
        for r in _read_jsonl(_FDE_DEPLOYS):
            if str(r.get("id")) == item_id:
                for s in r.get("steps") or []:
                    if isinstance(s, dict) and s.get("skill") == "drip_journey":
                        jid = ((s.get("data") or {}).get("journey_id")) or ""
        if jid and journeys.set_enabled(jid, True):
            return f"drip journey {jid} enabled"
        return "reviewed (no drip journey to enable)"
    except Exception as e:
        logger.debug("[approvals] fde action skip: %s", e)
        return "reviewed (drip enable skip)"


def decide(source: str, item_id: str, decision: str, by: str = "admin") -> dict[str, Any]:
    """Stamp status + fire bounded safe action. Idempotent, never raises."""
    source = (source or "").strip().lower()
    item_id = (item_id or "").strip()
    decision = (decision or "").strip().lower()
    if source not in _SOURCES:
        return {"ok": False, "error": f"unknown source (allowed: {list(_SOURCES)})"}
    if not item_id:
        return {"ok": False, "error": "item_id required"}
    if decision not in ("approve", "reject"):
        return {"ok": False, "error": "decision must be approve|reject"}

    cur = _status_for(source, item_id)
    if cur in ("approved", "rejected"):
        return {"ok": True, "source": source, "id": item_id, "status": cur, "noop": True}

    status = "approved" if decision == "approve" else "rejected"
    # Stamp the decision FIRST, then fire the best-effort action — so a concurrent
    # double-approve or an action failure cannot leave the item un-stamped or
    # double-fire the bounded action (TOCTOU narrowing for the single-admin case).
    _set_status(source, item_id, status, by)
    action = ""
    if decision == "approve":
        if source == "sales":
            action = _action_sales(item_id)
        elif source == "coordinator":
            action = _action_coordinator(item_id)
        elif source == "fde":
            action = _action_fde(item_id)
    try:
        from app.platform import team

        team.log_event(
            "system",
            f"approval_{status}",
            f"{source} {item_id[:24]} {status} by {by}" + (f" — {action}" if action else ""),
        )
    except Exception:
        pass
    return {"ok": True, "source": source, "id": item_id, "status": status, "action": action}


__all__ = ["list_drafts", "decide"]
