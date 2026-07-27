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
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_DECISIONS = os.path.join("data", "approval_decisions.jsonl")
_COORD_RUNS = os.path.join("data", "coordination_runs.jsonl")
_FDE_DEPLOYS = os.path.join("data", "fde_deploys.jsonl")
_VERIFICATION = os.path.join("data", "owner_os_verification_approvals.jsonl")
_SOURCES = ("sales", "coordinator", "fde", "owner_os_verification")


def _now_iso() -> str:
    return datetime.now().isoformat()


def _ts_to_iso(ts: Any) -> str:
    """sales index stores ts as epoch-SECONDS int; frontend JS `new Date(int)`
    reads ints as MILLISECONDS -> every draft showed "20616 din pehle" (1970).
    Normalize at this single choke point so every consumer gets ISO."""
    try:
        if isinstance(ts, int | float) and ts > 0:
            return datetime.fromtimestamp(ts).isoformat()
        return str(ts or "")
    except Exception:
        return ""


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


def _set_status(
    source: str, item_id: str, status: str, by: str = "admin", reason: str = ""
) -> None:
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
                        "reason": (reason or "")[:200],
                        "at": _now_iso(),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    except Exception as e:
        logger.debug("[approvals] status write skip: %s", e)


def create_verification_approval(
    *,
    title: str = "Owner OS production verification (disposable)",
    by: str = "admin",
    ttl_hours: int = 24,
    note: str = "Internal disposable approval — no external side effects",
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a disposable internal approval with ZERO external side effects.

    Appears in the same list_drafts / Mission Control drafts queue as other
    sources. Approve/reject only stamps status — no workflow, publish, email,
    WhatsApp, call, billing, or customer mutation.
    """
    item_id = "oosv_" + uuid.uuid4().hex[:12]
    now = datetime.now(timezone.utc)
    expires = now + timedelta(hours=max(1, min(int(ttl_hours or 24), 72)))
    row = {
        "id": item_id,
        "item_id": item_id,
        "source": "owner_os_verification",
        "title": (title or "Owner OS production verification (disposable)")[:160],
        "summary": (note or "")[:240],
        "disposable": True,
        "internal": True,
        "no_side_effects": True,
        "risk": "low",
        "risk_tier": "low",
        "client_id": "",
        "customer": "",
        "created_by": (by or "admin")[:80],
        "created_at": now.isoformat(),
        "expires_at": expires.isoformat(),
        "status": "pending",
    }
    if isinstance(meta, dict) and meta:
        # Binding fields for External Agent AMBER (and similar) — still one ledger.
        row["meta"] = meta
    try:
        os.makedirs("data", exist_ok=True)
        with open(_VERIFICATION, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception as e:
        return {"ok": False, "error": f"write_failed:{type(e).__name__}"}
    return {"ok": True, "draft": row, "id": item_id, "source": "owner_os_verification"}


def get_verification_draft(item_id: str) -> dict[str, Any] | None:
    """Latest verification draft row for ``item_id`` (append-only JSONL)."""
    want = str(item_id or "").strip()
    if not want:
        return None
    found: dict[str, Any] | None = None
    try:
        for r in _read_jsonl(_VERIFICATION):
            iid = str(r.get("id") or r.get("item_id") or "")
            if iid == want:
                found = r
    except Exception:
        return found
    return found


def _drafts_verification(smap: dict) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc)
    try:
        for r in _read_jsonl(_VERIFICATION):
            iid = str(r.get("id") or r.get("item_id") or "")
            if not iid:
                continue
            exp_raw = str(r.get("expires_at") or "")
            expired = False
            if exp_raw:
                try:
                    exp = datetime.fromisoformat(exp_raw.replace("Z", "+00:00"))
                    if exp.tzinfo is None:
                        exp = exp.replace(tzinfo=timezone.utc)
                    expired = now > exp
                except Exception:
                    expired = False
            st = _status_for("owner_os_verification", iid, smap)
            if expired and st == "pending":
                st = "expired"
            out.append(
                {
                    "source": "owner_os_verification",
                    "id": iid,
                    "item_id": iid,
                    "title": (r.get("title") or "Owner OS verification")[:160],
                    "summary": (r.get("summary") or "")[:240],
                    "body": (r.get("summary") or "")[:500],
                    "status": st,
                    "risk": "low",
                    "risk_tier": "low",
                    "client_id": "",
                    "customer": "",
                    "agent": "owner_os",
                    "action": "internal_verification",
                    "impact": "none — disposable verification only",
                    "disposable": True,
                    "no_side_effects": True,
                    "expires_at": r.get("expires_at"),
                    "expired": expired,
                    "at": r.get("created_at") or "",
                    "meta": {
                        "disposable": True,
                        "internal": True,
                        "no_side_effects": True,
                    },
                }
            )
    except Exception as e:
        logger.debug("[approvals] verification adapter skip: %s", e)
    return out


# --------------------------------------------------------------------------- #
# Read adapters (each defensive -> [] on failure; never break the cockpit)
# --------------------------------------------------------------------------- #
def _drafts_sales(smap: dict) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        from app.agents import sales_team

        seen: set[str] = set()  # index has dup pids (re-analyzed) — latest-first wins
        for r in sales_team.list_analyses(limit=20):
            pid = str(r.get("pid") or "")
            if not pid or pid in seen:
                continue
            seen.add(pid)
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
                    "created_at": _ts_to_iso(r.get("ts")),
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
    drafts = (
        _drafts_sales(smap)
        + _drafts_coordinator(smap)
        + _drafts_fde(smap)
        + _drafts_verification(smap)
    )
    if not include_decided:
        drafts = [d for d in drafts if d.get("status") == "pending"]
    by_source: dict[str, int] = {}
    pending = 0
    for d in drafts:
        by_source[d["source"]] = by_source.get(d["source"], 0) + 1
        if d.get("status") == "pending":
            pending += 1
    return {"drafts": drafts, "counts": {"by_source": by_source, "pending": pending}}


def recent_decisions(limit: int = 8) -> list[dict[str, Any]]:
    """Audit-trail strip for the Office HQ Approvals panel — "who decided what,
    when". Reads the same append-only sidecar `decide()` writes to; latest
    (source, item_id) wins, newest-first. Draft titles are re-resolved from
    `list_drafts(include_decided=True)` (source files are the title's source of
    truth); patch/self-improve titles are left blank in this v1 — those kinds
    keep their own status stores and aren't wired here yet. Never raises."""
    out: list[dict[str, Any]] = []
    try:
        rows = _read_jsonl(_DECISIONS)
        rows = [r for r in rows if r.get("source") in _SOURCES and r.get("item_id")]
        latest: dict[tuple[str, str], dict[str, Any]] = {}
        for r in rows:
            latest[(str(r["source"]), str(r["item_id"]))] = r
        titles = {
            (d["source"], d["id"]): d.get("title")
            for d in list_drafts(include_decided=True).get("drafts") or []
        }
        decided = sorted(latest.values(), key=lambda r: r.get("at") or "", reverse=True)
        for r in decided[: max(1, min(50, limit))]:
            key = (str(r.get("source") or ""), str(r.get("item_id") or ""))
            out.append(
                {
                    "source": key[0],
                    "id": key[1],
                    "title": titles.get(key) or f"{key[0]} #{key[1]}",
                    "status": r.get("status") or "",
                    "by": r.get("by") or "admin",
                    "at": r.get("at") or "",
                }
            )
    except Exception as e:
        logger.debug(f"[approvals] recent_decisions skipped: {e}")
    return out


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


def _action_verification(item_id: str) -> str:
    """Intentionally empty — disposable Owner OS verification has no side effects."""
    return "verification only — no external action"


def decide(
    source: str,
    item_id: str,
    decision: str,
    by: str = "admin",
    reason: str = "",
) -> dict[str, Any]:
    """Stamp status + fire bounded safe action. Idempotent, never raises."""
    source = (source or "").strip().lower()
    item_id = (item_id or "").strip()
    decision = (decision or "").strip().lower()
    reason = (reason or "")[:200]
    if source not in _SOURCES:
        return {"ok": False, "error": f"unknown source (allowed: {list(_SOURCES)})"}
    if not item_id:
        return {"ok": False, "error": "item_id required"}
    if decision not in ("approve", "reject"):
        return {"ok": False, "error": "decision must be approve|reject"}

    # Expired verification drafts cannot be decided.
    if source == "owner_os_verification":
        for d in _drafts_verification(_status_map()):
            if d.get("id") == item_id and d.get("expired"):
                return {"ok": False, "error": "approval_expired", "source": source, "id": item_id}

    cur = _status_for(source, item_id)
    if cur in ("approved", "rejected"):
        return {"ok": True, "source": source, "id": item_id, "status": cur, "noop": True}

    status = "approved" if decision == "approve" else "rejected"
    # Stamp the decision FIRST, then fire the best-effort action — so a concurrent
    # double-approve or an action failure cannot leave the item un-stamped or
    # double-fire the bounded action (TOCTOU narrowing for the single-admin case).
    _set_status(source, item_id, status, by, reason=reason)
    action = ""
    if decision == "approve":
        if source == "sales":
            action = _action_sales(item_id)
        elif source == "coordinator":
            action = _action_coordinator(item_id)
        elif source == "fde":
            action = _action_fde(item_id)
        elif source == "owner_os_verification":
            action = _action_verification(item_id)
    elif source == "owner_os_verification":
        action = _action_verification(item_id)
    try:
        from app.platform import team

        # "system" is not a STAFF key -- was silently invisible in team_status().
        # Approval/audit-trail tracking fits Arnav's Security/Compliance domain.
        # Fixed 2026-07-01.
        team.log_event(
            "arnav",
            f"approval_{status}",
            f"{source} {item_id[:24]} {status} by {by}"
            + (f" — {action}" if action else "")
            + (f" ({reason})" if reason else ""),
        )
    except Exception:
        pass
    return {
        "ok": True,
        "source": source,
        "id": item_id,
        "status": status,
        "action": action,
        "reason": reason,
        "by": (by or "admin")[:80],
        "no_side_effects": source == "owner_os_verification",
    }


__all__ = ["list_drafts", "decide", "create_verification_approval", "recent_decisions"]
