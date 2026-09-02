"""Leads / CRM Quality Assurance — read-only lead-hygiene detection (GREEN lane).

WHY (2026-07-20, Agent-OS upgrade — Rohan/Neha/Priya lead domain): the lead
primitives all existed but were never composed into the one question that matters
for the lead pipeline: *"which leads in the store are junk / dangerous to act on,
and what's the proof?"*
  - ``prospector.list_prospects()`` = raw lead/CRM store (read helper)
  - ``lead_scoring.score_lead()`` / ``HOT_THRESHOLD`` / ``is_hot()`` = qualification
  - ``clients_store.canonical_client_id()`` = tenant resolver (billing alias -> id)
None of these answered, in one structured record: are there DUPLICATE leads, leads
with NO way to reach them, UNQUALIFIED / unscored leads, or HOT leads going STALE
with no follow-up? This module composes the existing read primitives into that
single, tenant-safe, evidence-backed report.

SAFETY CONTRACT (enforced by tests):
  - PURE READ. Calls only read functions (``list_prospects``, ``score_lead``,
    ``canonical_client_id``). Never writes a prospect/lead/client record, never
    sends WhatsApp/email, never mutates any store. The mutation paths
    (``prospector.set_prospect_fields`` / ``mark_prospect`` / ``clients_store``
    writers / ``dedupe_clients``) are NOT touched.
  - TENANT-SAFE. Duplicate detection is scoped per canonical tenant via
    ``clients_store.canonical_client_id`` so the SAME phone under two different
    tenants is never mis-flagged as one duplicate lead.
  - NEVER RAISES. Every lead is best-effort; one bad record cannot sink the scan.
  - VOICE-FREE. Imports no telephony / STT / TTS / call-runtime module; strictly
    marketing-domain (out of scope: the voice calling stack).

OBSERVABILITY: a scan emits ONE ``team.log_event`` under ``rohan`` (Leads Manager) —
lead hygiene / qualification is rohan's lane — so the run is visible on the existing
team activity feed with a real owner (no new persona invented). ``warn`` when any
issue is found, ``ok`` otherwise.

Lane: GREEN (read-only detection + report). Autonomy: L0/L1 (observe + recommend).
"""

from __future__ import annotations

import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Observability owner for lead-quality runs. Rohan = Leads Manager (one of the 31
# canonical personas) — lead qualification / hygiene is his lane. NOT a new persona.
_OWNER_MEMBER = "rohan"

# A hot lead with no follow-up touch in this many days = stale (actionable churn of
# a warm lead). Env override, defensively parsed.
try:
    STALE_HOT_DAYS = int(os.environ.get("LEAD_STALE_HOT_DAYS", "14"))
except Exception:
    STALE_HOT_DAYS = 14

# How many example leads to attach per issue (evidence, not a dump).
_SAMPLE_CAP = 8

# Timestamp fields that count as a "follow-up touch" on a lead (any recent one =
# not stale). updated_at is intentionally EXCLUDED — a store rewrite bumps it
# without any real outreach happening.
_TOUCH_FIELDS = (
    "emailed_at",
    "last_called_at",
    "last_contacted_at",
    "contacted_at",
    "last_followup_at",
    "followup_at",
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _norm_phone(v: Any) -> str:
    """Last-10 digits of a phone (the store's dedupe key). '' if unusable."""
    digits = re.sub(r"\D", "", str(v or ""))
    return digits[-10:] if len(digits) >= 10 else ""


def _norm_email(v: Any) -> str:
    """Lowercased, trimmed email; '' if not a plausible address."""
    e = str(v or "").strip().lower()
    if "@" not in e or "." not in e.rsplit("@", 1)[-1]:
        return ""
    return e


def _tenant(rec: dict[str, Any]) -> str:
    """Canonical tenant for a lead (normalises billing alias -> marketing id).
    Platform-level prospects default to 'platform'. Never raises."""
    raw = str((rec or {}).get("client_id") or "").strip()
    if not raw:
        return "platform"
    try:
        from app.marketing import clients_store

        return str(clients_store.canonical_client_id(raw) or raw).strip() or "platform"
    except Exception:
        return raw or "platform"


def _lead_name(rec: dict[str, Any]) -> str:
    return str((rec or {}).get("business_name") or (rec or {}).get("name") or "").strip()


def _lead_ref(rec: dict[str, Any]) -> dict[str, Any]:
    """Compact, JSON-safe reference to a lead for issue samples."""
    return {
        "id": str((rec or {}).get("id") or ""),
        "name": _lead_name(rec),
        "tenant": _tenant(rec),
    }


def _days_since(ts: Any) -> float | None:
    """Age in days of an ISO/`datetime` timestamp; None if missing/unparseable."""
    if not ts:
        return None
    try:
        if isinstance(ts, datetime):
            dt = ts
        elif isinstance(ts, str):
            dt = datetime.fromisoformat(ts.strip().replace("Z", "+00:00"))
        else:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (_now() - dt).total_seconds() / 86400.0
    except Exception:
        return None


def _last_touch_days(rec: dict[str, Any]) -> float | None:
    """Days since the most-recent follow-up touch; None if never touched."""
    best: float | None = None
    for f in _TOUCH_FIELDS:
        d = _days_since((rec or {}).get(f))
        if d is not None and (best is None or d < best):
            best = d
    return best


def _score_of(rec: dict[str, Any]) -> int | None:
    """Numeric 0-100 lead score. Uses a stored ``lead_score`` when present, else
    live-scores via ``lead_scoring.score_lead``. None only if scoring is
    unavailable (treated as 'unscored'). Never raises."""
    val = (rec or {}).get("lead_score")
    if isinstance(val, bool):
        val = None
    if isinstance(val, int | float):
        try:
            return max(0, min(100, int(val)))
        except Exception:
            pass
    try:
        from app.platform import lead_scoring

        return int(lead_scoring.score_lead(rec))
    except Exception:
        return None


def _hot_threshold() -> int:
    try:
        from app.platform import lead_scoring

        return int(lead_scoring.HOT_THRESHOLD)
    except Exception:
        return 60


def _gather_leads(limit: int) -> list[dict[str, Any]]:
    """Read-only pull of the lead/CRM store (prospect store). Never raises."""
    try:
        from app.platform import prospector

        rows = prospector.list_prospects(status=None, limit=max(1, int(limit)))
        return [r for r in (rows or []) if isinstance(r, dict)]
    except Exception as exc:
        logger.warning("lead_quality _gather_leads err: %s", exc)
        return []


def _issue(kind: str, count: int, sample: list[dict[str, Any]]) -> dict[str, Any]:
    return {"type": kind, "count": int(count), "sample": sample[:_SAMPLE_CAP]}


def _detect_duplicates(leads: list[dict[str, Any]]) -> dict[str, Any]:
    """Per-tenant duplicate detection on normalised phone / email. Read-only.
    Returns {count, sample, dup_ids}. Never raises."""
    clusters: dict[str, dict[str, Any]] = {}
    try:
        for rec in leads:
            try:
                tenant = _tenant(rec)
                for kind, key in (
                    ("phone", _norm_phone(rec.get("phone"))),
                    ("email", _norm_email(rec.get("email"))),
                ):
                    if not key:
                        continue
                    ck = f"{tenant}|{kind}:{key}"
                    node = clusters.setdefault(
                        ck, {"kind": kind, "key": key, "tenant": tenant, "leads": []}
                    )
                    node["leads"].append(rec)
            except Exception:
                continue
    except Exception as exc:
        logger.debug("lead_quality _detect_duplicates err: %s", exc)

    dup_ids: set[str] = set()
    sample: list[dict[str, Any]] = []
    for node in clusters.values():
        group = node["leads"]
        if len(group) < 2:
            continue
        ids = [str((g or {}).get("id") or "") for g in group]
        # first is the canonical keeper; the rest are the redundant duplicates
        for extra in group[1:]:
            eid = str((extra or {}).get("id") or "")
            if eid:
                dup_ids.add(eid)
        if len(sample) < _SAMPLE_CAP:
            sample.append(
                {
                    "kind": node["kind"],
                    "key": node["key"],
                    "tenant": node["tenant"],
                    "count": len(group),
                    "ids": ids[:6],
                    "names": [_lead_name(g) for g in group][:6],
                }
            )
    return {"count": len(dup_ids), "sample": sample, "dup_ids": dup_ids}


def scan_lead_quality(limit: int = 200) -> dict[str, Any]:
    """READ-ONLY aggregator: structured, tenant-safe, evidence-backed lead-hygiene
    report. AgentRunResult-shaped.

    Detects: duplicate leads (same phone/email, per tenant), leads missing any
    contact (no phone AND no email), unqualified / unscored leads (below
    HOT_THRESHOLD or no score), and stale hot leads (hot but no recent follow-up).

    No sends, no state mutation. Emits one observability event (rohan). Never
    raises — returns a shaped record with status='error' + error string on failure.
    """
    run_id = str(uuid.uuid4())
    started = _now()
    result: dict[str, Any] = {
        "run_id": run_id,
        "agent_id": "lead_quality",
        "domain": "leads_crm",
        "lane": "GREEN",
        "status": "success",
        "started_at": _iso(started),
        "completed_at": None,
        "latency_ms": 0,
        "checked": 0,
        "issues": [],
        "counts": {},
        "error": None,
    }
    try:
        leads = _gather_leads(limit)
        result["checked"] = len(leads)
        threshold = _hot_threshold()

        # --- duplicates (per-tenant, phone/email) --- #
        dup = _detect_duplicates(leads)

        # --- single-pass classification for the remaining detections --- #
        missing: list[dict[str, Any]] = []
        unqualified: list[dict[str, Any]] = []
        unscored: list[dict[str, Any]] = []
        stale_hot: list[dict[str, Any]] = []
        hot_count = 0
        tenants: set[str] = set()
        phones: set[str] = set()
        emails: set[str] = set()

        for rec in leads:
            try:
                tenants.add(_tenant(rec))
                ph = _norm_phone(rec.get("phone"))
                em = _norm_email(rec.get("email"))
                if ph:
                    phones.add(ph)
                if em:
                    emails.add(em)

                if not ph and not em:
                    missing.append(_lead_ref(rec))

                score = _score_of(rec)
                if score is None:
                    ref = _lead_ref(rec)
                    ref["score"] = None
                    unscored.append(ref)
                else:
                    if score < threshold:
                        ref = _lead_ref(rec)
                        ref["score"] = score
                        unqualified.append(ref)
                    else:
                        hot_count += 1
                        touch = _last_touch_days(rec)
                        if touch is None or touch > STALE_HOT_DAYS:
                            ref = _lead_ref(rec)
                            ref["score"] = score
                            ref["last_touch_days"] = None if touch is None else round(touch, 1)
                            stale_hot.append(ref)
            except Exception:
                # one bad record can never sink the scan
                continue

        unqualified_sample = (unqualified + unscored)[:_SAMPLE_CAP]
        result["issues"] = [
            _issue("duplicate_leads", dup["count"], dup["sample"]),
            _issue("missing_contact", len(missing), missing),
            _issue("unqualified_leads", len(unqualified) + len(unscored), unqualified_sample),
            _issue("stale_hot_leads", len(stale_hot), stale_hot),
        ]
        result["counts"] = {
            "total_leads": len(leads),
            "duplicate_leads": dup["count"],
            "missing_contact": len(missing),
            "unqualified": len(unqualified),
            "unscored": len(unscored),
            "hot_leads": hot_count,
            "stale_hot": len(stale_hot),
            "unique_phones": len(phones),
            "unique_emails": len(emails),
            "tenants": len(tenants),
            "hot_threshold": threshold,
        }
    except Exception as exc:
        logger.warning("lead_quality scan err: %s", exc)
        result["status"] = "error"
        result["error"] = str(exc)

    completed = _now()
    result["completed_at"] = _iso(completed)
    result["latency_ms"] = int((completed - started).total_seconds() * 1000)

    # observability — one team event under the leads-manager owner (no new persona)
    try:
        from app.platform import team

        total_issues = sum(int(i.get("count") or 0) for i in result["issues"])
        if result["status"] != "success":
            status = "error"
        elif total_issues:
            status = "warn"
        else:
            status = "ok"
        detail = (
            f"lead quality: {result['counts'].get('duplicate_leads', 0)} dup / "
            f"{result['counts'].get('missing_contact', 0)} no-contact / "
            f"{result['counts'].get('unqualified', 0)} unqualified / "
            f"{result['counts'].get('stale_hot', 0)} stale-hot "
            f"of {result['checked']} leads"
        )
        team.log_event(
            _OWNER_MEMBER,
            "lead_quality_scan",
            detail[:160],
            status=status,
            meta={
                "run_id": run_id,
                "checked": result["checked"],
                "issues": total_issues,
                "counts": result["counts"],
            },
        )
    except Exception as exc:
        logger.debug("lead_quality observability skip: %s", exc)

    return result


def lead_quality_summary() -> dict[str, Any]:
    """Compact admin-readable summary (counts + issue totals). Read-only."""
    scan = scan_lead_quality()
    issues = scan.get("issues") or []
    return {
        "generated_at": scan["completed_at"],
        "checked": scan["checked"],
        "status": scan["status"],
        "total_issues": sum(int(i.get("count") or 0) for i in issues),
        "counts": scan.get("counts") or {},
        "issue_totals": [
            {"type": i.get("type"), "count": int(i.get("count") or 0)} for i in issues
        ],
    }


__all__ = [
    "STALE_HOT_DAYS",
    "scan_lead_quality",
    "lead_quality_summary",
]
