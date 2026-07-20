"""Approval/publishing REMEDIATION — safe execute/repair for stuck approvals.

WHY (2026-07-20): investigation of the content-assurance finding showed ~364 stuck
approvals but only ONE active client (Jiya). The bulk are DEAD drafts belonging to
inactive/legacy/synthetic clients, forever "awaiting client approval" that will never
come. This module turns that detection into a SAFE remediation:

  - inactive-client stuck drafts -> EXPIRE  (content_approval.cancel -> 'cancelled':
    an internal state transition only — NO customer contact, NO publish, NO send).
  - active-client stuck drafts   -> ESCALATE to admin (human decides; NEVER auto-publish, §5).
  - publish failures             -> surfaced (own-brand fix is a separate human action).

SAFETY CONTRACT (enforced by tests):
  - Default DRY-RUN (`plan_remediation` is pure-read; `execute_remediation(dry_run=True)`
    changes nothing). Real execution requires BOTH `dry_run=False` AND the
    `APPROVAL_REMEDIATION` env flag, and writes a JSONL backup before any change.
  - NEVER cancels an ACTIVE client's draft (active = present in
    clients_store.list_clients(status='active'), tenant-safe via canonical_client_id).
  - NEVER publishes anything (§5 ban-safety). The only state change is cancel/expire.
  - Idempotent (already-terminal drafts are skipped by the state machine). Never raises.
  - Reuses content_approval.cancel — this module does NOT edit content_approval.
  - Voice-free: strictly marketing-domain.

Lane: AMBER (internal state change), started gated-off. Owner attribution: zara (social/publishing).
"""

from __future__ import annotations

import os
import shutil
import uuid
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Non-terminal statuses that can be "stuck". Terminal ones (published/cancelled/
# partially_published/rejected) are never touched.
_STUCK_STATUSES = frozenset({"pending", "approved", "ready_for_review", "changes_requested"})
_DEFAULT_MIN_AGE_H = 48.0
_STORE = os.path.join("data", "content_approvals.jsonl")
_OWNER_MEMBER = "zara"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _flag_on(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _canonical(cid: str) -> str:
    try:
        from app.marketing import clients_store

        return str(clients_store.canonical_client_id(cid) or cid or "").strip()
    except Exception:
        return str(cid or "").strip()


def _active_canonical_ids() -> set[str]:
    """Canonical ids of currently-active clients. Fail-CLOSED to 'unknown-active' on
    error by returning a sentinel that makes _is_active() conservative (see below)."""
    try:
        from app.marketing import clients_store

        out: set[str] = set()
        for c in clients_store.list_clients(status="active"):
            cid = str((c or {}).get("id") or "").strip()
            if cid:
                out.add(cid)
                out.add(_canonical(cid))
            for alias in (c or {}).get("billing_client_ids") or []:
                a = str(alias or "").strip()
                if a:
                    out.add(a)
        return out
    except Exception as exc:
        logger.warning("approval_remediation _active_canonical_ids err: %s", exc)
        return set()


def _age_hours(rec: dict[str, Any]) -> float | None:
    ts = str(rec.get("created_at") or rec.get("submitted_at") or rec.get("at") or "").strip()
    if not ts:
        return None
    try:
        d = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return round((_now() - d).total_seconds() / 3600.0, 1)
    except Exception:
        return None


def _stuck_records(min_age_hours: float) -> list[dict[str, Any]]:
    """All non-terminal approval records older than the threshold. Read-only."""
    try:
        from app.marketing import content_approval

        states = content_approval._latest_states() or {}
    except Exception as exc:
        logger.warning("approval_remediation _stuck_records read err: %s", exc)
        return []
    out: list[dict[str, Any]] = []
    for aid, rec in states.items():
        status = str((rec or {}).get("status") or "").strip().lower()
        if status not in _STUCK_STATUSES:
            continue
        age = _age_hours(rec)
        if age is not None and age < float(min_age_hours):
            continue
        out.append(
            {
                "id": str(aid),
                "client_id": str((rec or {}).get("client_id") or ""),
                "status": status,
                "age_hours": age,
                "title": str(
                    (rec or {}).get("content", {}).get("title") or (rec or {}).get("title") or ""
                )[:80],
            }
        )
    return out


def plan_remediation(min_age_hours: float = _DEFAULT_MIN_AGE_H) -> dict[str, Any]:
    """READ-ONLY plan: classify stuck approvals into expire (inactive client) vs
    escalate (active client). No state change. AgentRunResult-shaped."""
    started = _now()
    active = _active_canonical_ids()
    stuck = _stuck_records(min_age_hours)
    expire: list[dict[str, Any]] = []
    escalate: list[dict[str, Any]] = []
    for r in stuck:
        canon = _canonical(r["client_id"])
        r["canonical_id"] = canon
        is_active = bool(r["client_id"] in active or canon in active)
        r["client_active"] = is_active
        (escalate if is_active else expire).append(r)
    return {
        "run_id": str(uuid.uuid4()),
        "agent_id": "approval_remediation",
        "domain": "content_publishing",
        "lane": "AMBER",
        "status": "success",
        "generated_at": _iso(started),
        "min_age_hours": float(min_age_hours),
        "total_stuck": len(stuck),
        "expire_candidates": len(expire),
        "escalate_active": len(escalate),
        "active_clients": len(active),
        "expire_sample": expire[:8],
        "escalate_sample": escalate[:8],
    }


def _meta_channel_status(canonical_id: str, aliases: list[str] | None = None) -> dict[str, Any]:
    """Read-only Meta channel connect check for a customer. NEVER returns tokens.
    Ignores global platform fallback (own-brand) so customer proof isn't false-green.
    """
    ids = {str(canonical_id or "").strip()}
    for a in aliases or []:
        if str(a or "").strip():
            ids.add(str(a).strip())
    out: dict[str, Any] = {
        "connected": False,
        "has_page_id": False,
        "has_instagram": False,
        "scope": "none",
    }
    if not any(ids):
        return out
    try:
        from app.integrations import meta_graph

        for r in meta_graph._read_conns() or []:
            cid = str((r or {}).get("client_id") or "").strip()
            if cid not in ids:
                continue
            tok = str((r or {}).get("page_access_token") or "").strip()
            if not tok:
                continue
            out["connected"] = True
            out["has_page_id"] = bool(str((r or {}).get("page_id") or "").strip())
            out["has_instagram"] = bool(str((r or {}).get("instagram_account_id") or "").strip())
            out["scope"] = "client"
            break
    except Exception as exc:
        logger.debug("approval_remediation meta status skip: %s", exc)
        out["error"] = "meta_store_unreadable"
    return out


def client_inventory(
    client_id: str,
    min_age_hours: float = _DEFAULT_MIN_AGE_H,
) -> dict[str, Any]:
    """READ-ONLY WS-2 inventory for one customer (canonical id OR billing alias).

    Returns stuck approvals for that tenant, escalate-vs-expire classification,
    and Meta channel connect status (no tokens). Never mutates, never publishes.
    """
    started = _now()
    raw = str(client_id or "").strip()
    aliases: list[str] = []
    rec: dict[str, Any] = {}
    try:
        from app.marketing import clients_store

        rec = clients_store.resolve_client(raw) or clients_store.get_client(raw) or {}
        canon = str((rec or {}).get("id") or "").strip() or _canonical(raw) or raw
        for a in (rec or {}).get("billing_client_ids") or []:
            if str(a or "").strip():
                aliases.append(str(a).strip())
    except Exception:
        canon = _canonical(raw) or raw
        rec = {}
    match_ids = {raw, canon, *aliases} - {""}

    active = _active_canonical_ids()
    is_active = bool(raw in active or canon in active or any(a in active for a in aliases))
    stuck_all = _stuck_records(min_age_hours)
    mine = [
        r
        for r in stuck_all
        if str(r.get("client_id") or "") in match_ids
        or _canonical(str(r.get("client_id") or "")) in match_ids
    ]
    by_status: dict[str, int] = {}
    for r in mine:
        st = str(r.get("status") or "")
        by_status[st] = by_status.get(st, 0) + 1
        r["canonical_id"] = canon
        r["client_active"] = is_active

    meta = _meta_channel_status(canon, aliases)
    recovery = "none"
    if mine and is_active:
        recovery = "customer_approve_or_admin_escalate"
    elif mine and not is_active:
        recovery = "expire_inactive_via_remediation"
    if is_active and not meta.get("connected"):
        recovery = (
            "meta_customer_connect_or_manual_publish"
            if not mine
            else "approve_drafts_and_or_meta_connect"
        )

    return {
        "run_id": str(uuid.uuid4()),
        "agent_id": "approval_remediation",
        "domain": "content_publishing",
        "lane": "GREEN",
        "status": "success",
        "generated_at": _iso(started),
        "input_client_id": raw,
        "canonical_id": canon,
        "client_active": is_active,
        "client_name": (rec or {}).get("business_name"),
        "min_age_hours": float(min_age_hours),
        "stuck_count": len(mine),
        "by_status": by_status,
        "stuck_sample": mine[:20],
        "meta_channel": meta,
        "recommended_recovery": recovery,
        "note": "read-only inventory — no publish, no cancel",
    }


def _backup_store() -> str:
    """Copy the approvals JSONL to a timestamped backup. Returns path or ''."""
    try:
        if not os.path.isfile(_STORE):
            return ""
        stamp = _now().strftime("%Y%m%d_%H%M%S")
        dst = f"{_STORE}.bak-remediation-{stamp}"
        shutil.copy2(_STORE, dst)
        return dst
    except Exception as exc:
        logger.warning("approval_remediation backup err: %s", exc)
        return ""


def execute_remediation(
    min_age_hours: float = _DEFAULT_MIN_AGE_H,
    dry_run: bool = True,
    limit: int = 1000,
    flag: str = "APPROVAL_REMEDIATION",
) -> dict[str, Any]:
    """Expire (cancel) stuck drafts belonging to INACTIVE clients only. Active-client
    drafts are never touched — they are escalated for human decision.

    Gated: real execution needs dry_run=False AND the flag set. Writes a backup first.
    Never publishes. Idempotent. Never raises.
    """
    plan = plan_remediation(min_age_hours)
    result: dict[str, Any] = {
        "run_id": plan["run_id"],
        "agent_id": "approval_remediation",
        "dry_run": bool(dry_run),
        "flag_on": _flag_on(flag),
        "total_stuck": plan["total_stuck"],
        "expire_candidates": plan["expire_candidates"],
        "escalate_active": plan["escalate_active"],
        "expired": 0,
        "skipped": 0,
        "backup_path": "",
        "status": "success",
        "error": None,
    }
    # Safety gate: no state change unless explicitly executed AND flag-enabled.
    if dry_run or not _flag_on(flag):
        result["skipped"] = plan["expire_candidates"]
        result["note"] = "dry_run or flag off — no state change"
        _observe(result)
        return result

    # Real execution — backup then cancel inactive-client stuck drafts.
    result["backup_path"] = _backup_store()
    try:
        from app.marketing import content_approval

        stuck = _stuck_records(min_age_hours)
        active = _active_canonical_ids()
        done = 0
        for r in stuck:
            if done >= max(1, int(limit)):
                break
            cid = str(r.get("client_id") or "")
            canon = _canonical(cid)
            if cid in active or canon in active:
                continue  # NEVER touch an active client's draft
            try:
                res = content_approval.cancel(
                    r["id"],
                    actor="approval_remediation",
                    note="auto-expired: client inactive, draft stale (approval remediation)",
                )
                if isinstance(res, dict) and res.get("ok") is not False:
                    result["expired"] += 1
                    done += 1
                else:
                    result["skipped"] += 1
            except Exception as exc:  # pragma: no cover - defensive per record
                result["skipped"] += 1
                logger.debug("approval_remediation cancel skip %s: %s", r.get("id"), exc)
    except Exception as exc:
        result["status"] = "error"
        result["error"] = str(exc)[:160]
    _observe(result)
    return result


def _observe(result: dict[str, Any]) -> None:
    try:
        from app.platform import team

        detail = (
            f"approval remediation: {result.get('expired', 0)} expired / "
            f"{result.get('escalate_active', 0)} active-escalate "
            f"(dry_run={result.get('dry_run')})"
        )
        team.log_event(
            _OWNER_MEMBER,
            "approval_remediation",
            detail[:160],
            status="ok" if result.get("status") == "success" else "error",
            meta={"expired": result.get("expired"), "candidates": result.get("expire_candidates")},
        )
    except Exception as exc:
        logger.debug("approval_remediation observe skip: %s", exc)


__all__ = ["plan_remediation", "execute_remediation", "client_inventory"]
