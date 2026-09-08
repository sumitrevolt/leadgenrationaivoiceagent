"""Voice follow-up scheduler — trial day 8/9 + interested-not-converted callbacks.

Consented transactional callbacks only (existing customer / prior voice contact).
NOT platform_dial cold outbound. Gated VOICE_FOLLOWUP=1 (default OFF).

Store: data/voice_scheduled_callbacks.jsonl + voice_followup_runs.jsonl
Never raises from public helpers.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_IST = ZoneInfo("Asia/Kolkata")
_STORE = os.path.join("data", "voice_scheduled_callbacks.jsonl")
_RUNS = os.path.join("data", "voice_followup_runs.jsonl")

PURPOSE_TRIAL_DAY8 = "trial_day8"
PURPOSE_TRIAL_DAY9 = "trial_day9"
PURPOSE_INTERESTED_1 = "interested_followup_1"
PURPOSE_INTERESTED_2 = "interested_followup_2"

_TRIAL_PURPOSES = frozenset({PURPOSE_TRIAL_DAY8, PURPOSE_TRIAL_DAY9})
_INTERESTED_PURPOSES = frozenset({PURPOSE_INTERESTED_1, PURPOSE_INTERESTED_2})
_ALL_PURPOSES = _TRIAL_PURPOSES | _INTERESTED_PURPOSES


def _enabled() -> bool:
    return os.environ.get("VOICE_FOLLOWUP", "0").strip().lower() in ("1", "true", "yes")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _read(path: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            rows.append(json.loads(line))
                        except Exception:
                            pass
    except Exception:
        pass
    return rows


def _write_all(path: str, rows: list[dict[str, Any]]) -> None:
    try:
        from app.utils.file_lock import locked_rewrite

        content = "".join(json.dumps(r, ensure_ascii=False, default=str) + "\n" for r in rows)
        if not locked_rewrite(path, content):
            logger.warning("[voice_followup] locked write failed: %s", path)
    except Exception as e:
        logger.warning("[voice_followup] write %s failed: %s", path, e)


def _append(path: str, rec: dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


def _phone_key(phone: str) -> str:
    d = "".join(c for c in str(phone or "") if c.isdigit())
    if len(d) == 10:
        return "91" + d
    return d


def _ist_slot(base: datetime, *, hour: int = 11, minute: int = 0) -> datetime:
    """UTC instant for hour:minute IST on the calendar day of `base` (UTC-aware)."""
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    local = base.astimezone(_IST)
    slot_local = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return slot_local.astimezone(timezone.utc)


def _followup_delay_days() -> int:
    try:
        return max(1, min(14, int(os.environ.get("VOICE_FOLLOWUP_DAYS", "3"))))
    except Exception:
        return 3


def _trial_day_offsets() -> tuple[int, int]:
    """Day offsets from trial start for conversion calls (default 8 + 9)."""
    try:
        d8 = max(1, int(os.environ.get("VOICE_TRIAL_CALL_DAY8", "8")))
        d9 = max(d8, int(os.environ.get("VOICE_TRIAL_CALL_DAY9", "9")))
        return d8, d9
    except Exception:
        return 8, 9


def _has_pending(rows: list[dict[str, Any]], phone: str, purpose: str) -> bool:
    pk = _phone_key(phone)
    for r in rows:
        if r.get("phone") != pk:
            continue
        if r.get("purpose") != purpose:
            continue
        if r.get("status") in ("pending", "placed"):
            return True
    return False


def _interested_count(rows: list[dict[str, Any]], phone: str) -> int:
    pk = _phone_key(phone)
    n = 0
    for r in rows:
        if r.get("phone") != pk:
            continue
        if r.get("purpose") not in _INTERESTED_PURPOSES:
            continue
        if r.get("status") in ("pending", "placed", "done"):
            n += 1
    return n


def _deal_is_won(phone: str) -> bool:
    pk = _phone_key(phone)
    if not pk:
        return False
    try:
        path = os.path.join("data", "deals.jsonl")
        for rec in reversed(_read(path)):
            dp = _phone_key(str(rec.get("phone") or ""))
            if dp != pk:
                continue
            return str(rec.get("stage") or "").strip().lower() == "won"
    except Exception:
        pass
    return False


async def _client_has_paid(client_id: str) -> bool:
    if not (client_id or "").strip():
        return False
    try:
        from app.marketing.lifecycle_nurture import _has_paid

        return await _has_paid(str(client_id))
    except Exception:
        try:
            from app.marketing.clients_store import get_client

            c = get_client(str(client_id)) or {}
            plan = str(c.get("plan") or "").strip().lower()
            return plan not in ("", "trial", "free", "none", "pending") and not c.get("trial")
        except Exception:
            return False


def schedule_trial_callbacks(
    *,
    phone: str,
    client_id: str = "",
    business_name: str = "",
    niche: str = "ai_marketing",
    trial_started_at: datetime | None = None,
    source: str = "trial_activation",
) -> dict[str, Any]:
    """Schedule day-8 and day-9 IST transactional feedback+conversion calls."""
    if not _enabled():
        return {"ok": False, "skipped": "disabled"}
    pk = _phone_key(phone)
    if not pk:
        return {"ok": False, "error": "bad_phone"}
    if _deal_is_won(pk):
        return {"ok": False, "skipped": "already_won"}

    started = trial_started_at or _now()
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    d8, d9 = _trial_day_offsets()
    slots = [
        (PURPOSE_TRIAL_DAY8, started + timedelta(days=d8)),
        (PURPOSE_TRIAL_DAY9, started + timedelta(days=d9)),
    ]
    rows = _read(_STORE)
    created: list[str] = []
    for purpose, when in slots:
        if _has_pending(rows, pk, purpose):
            continue
        rec = {
            "id": uuid.uuid4().hex[:12],
            "phone": pk,
            "client_id": str(client_id or ""),
            "business_name": (business_name or "")[:120],
            "niche": (niche or "ai_marketing")[:40],
            "purpose": purpose,
            "scheduled_at": _ist_slot(when).isoformat(),
            "status": "pending",
            "source": source[:60],
            "enrolled_at": _now().isoformat(),
            "attempts": 0,
        }
        rows.append(rec)
        created.append(rec["id"])
    if created:
        _write_all(_STORE, rows)
    return {"ok": True, "scheduled": created, "phone": pk}


def schedule_interested_followup(
    *,
    phone: str,
    client_id: str = "",
    business_name: str = "",
    niche: str = "ai_marketing",
    call_id: str = "",
    source: str = "post_call",
) -> dict[str, Any]:
    """Auto-schedule consented follow-up for interested-but-not-converted leads."""
    if not _enabled():
        return {"ok": False, "skipped": "disabled"}
    pk = _phone_key(phone)
    if not pk:
        return {"ok": False, "error": "bad_phone"}
    if _deal_is_won(pk):
        return {"ok": False, "skipped": "already_won"}

    try:
        from app.telephony.consent_ledger import is_suppressed

        if is_suppressed(pk):
            return {"ok": False, "skipped": "opt_out"}
    except Exception:
        pass

    rows = _read(_STORE)
    if call_id:
        for r in rows:
            if r.get("source_call_id") == call_id and r.get("purpose") in _INTERESTED_PURPOSES:
                return {"ok": False, "skipped": "duplicate_call"}
        idem = f"vf:interested:{call_id}"
        try:
            from app.billing import idempotency as _idem

            if _idem.seen_before_sync(idem, ttl_s=86400 * 30):
                return {"ok": False, "skipped": "duplicate_call"}
        except Exception:
            pass

    count = _interested_count(rows, pk)
    if count >= 2:
        return {"ok": False, "skipped": "max_followups"}

    purpose = PURPOSE_INTERESTED_1 if count == 0 else PURPOSE_INTERESTED_2

    when = _now() + timedelta(days=_followup_delay_days())
    rec = {
        "id": uuid.uuid4().hex[:12],
        "phone": pk,
        "client_id": str(client_id or ""),
        "business_name": (business_name or "")[:120],
        "niche": (niche or "ai_marketing")[:40],
        "purpose": purpose,
        "scheduled_at": _ist_slot(when).isoformat(),
        "status": "pending",
        "source": source[:60],
        "source_call_id": str(call_id or "")[:80],
        "enrolled_at": _now().isoformat(),
        "attempts": 0,
    }
    rows.append(rec)
    _write_all(_STORE, rows)
    return {"ok": True, "scheduled": rec["id"], "purpose": purpose, "phone": pk}


def cancel_for_phone(phone: str, *, reason: str = "opt_out") -> int:
    """Cancel pending follow-ups (opt-out / not_interested). Returns count cancelled."""
    pk = _phone_key(phone)
    if not pk:
        return 0
    rows = _read(_STORE)
    n = 0
    for r in rows:
        if r.get("phone") != pk:
            continue
        if r.get("status") != "pending":
            continue
        r["status"] = "cancelled"
        r["cancel_reason"] = (reason or "")[:80]
        r["cancelled_at"] = _now().isoformat()
        n += 1
    if n:
        _write_all(_STORE, rows)
    return n


async def run_post_call_workflows(
    *,
    call_id: str = "",
    phone: str = "",
    client_id: str = "",
    client_name: str = "",
    niche: str = "",
    q: dict[str, Any] | None = None,
    close_signal: bool = False,
    not_interested: bool = False,
    trial_activated: bool = False,
) -> dict[str, Any]:
    """Unified post-call automation hook — idempotent per call_id."""
    out: dict[str, Any] = {"ok": True, "actions": []}
    cid = str(call_id or "").strip()
    if cid:
        try:
            from app.billing import idempotency as _idem

            if await _idem.seen_before(f"post_call_workflow:{cid}"):
                return {"ok": True, "skipped": "duplicate", "call_id": cid}
        except Exception:
            pass

    pk = _phone_key(phone)
    if not pk:
        return {"ok": True, "skipped": "no_phone"}

    if not_interested:
        n = cancel_for_phone(pk, reason="not_interested")
        out["actions"].append({"cancelled": n})
        return out

    if trial_activated:
        r = schedule_trial_callbacks(
            phone=pk,
            client_id=client_id,
            business_name=client_name,
            niche=niche,
            source="post_call_trial",
        )
        out["actions"].append({"trial_schedule": r})

    qualified = bool((q or {}).get("qualified"))
    if qualified or close_signal:
        if not await _client_has_paid(client_id):
            r = schedule_interested_followup(
                phone=pk,
                client_id=client_id,
                business_name=client_name,
                niche=niche,
                call_id=cid,
                source="post_call_interested",
            )
            out["actions"].append({"interested_schedule": r})

    try:
        from app.platform import automation_log_service as _als

        _als.log_event(
            client_id=str(client_id or ""),
            job_type="post_call_workflow",
            status="success",
            output_summary=f"voice followup wired call={cid[:12] if cid else '?'}",
            triggered_by="vobiz_stream",
            meta_json={"call_id": cid, "phone_tail": pk[-4:], "actions": out.get("actions")},
        )
    except Exception:
        pass

    return out


async def run_due(limit: int = 20) -> dict[str, Any]:
    """Place due transactional follow-up calls. Gated + compliance-first."""
    if not _enabled():
        return {"ok": True, "skipped": "disabled", "placed": 0}
    from app.telephony.campaign_compliance import trai_window_ok

    ok_window, window_reason = trai_window_ok(True)
    if not ok_window:
        return {"ok": True, "skipped": "trai_window", "reason": window_reason, "placed": 0}

    rows = _read(_STORE)
    now = _now()
    due = [
        r
        for r in rows
        if r.get("status") == "pending" and str(r.get("scheduled_at") or "") <= now.isoformat()
    ]
    due.sort(key=lambda x: str(x.get("scheduled_at") or ""))
    due = due[: max(1, int(limit))]

    placed = 0
    skipped = 0
    for rec in due:
        pk = str(rec.get("phone") or "")
        rid = str(rec.get("id") or "")
        purpose = str(rec.get("purpose") or "")
        try:
            from app.telephony.consent_ledger import is_suppressed, reconsent_blocked

            if is_suppressed(pk) or reconsent_blocked(pk):
                rec["status"] = "skipped"
                rec["skip_reason"] = "opt_out"
                skipped += 1
                continue
        except Exception:
            pass

        cid = str(rec.get("client_id") or "")
        if purpose in _TRIAL_PURPOSES and await _client_has_paid(cid):
            rec["status"] = "skipped"
            rec["skip_reason"] = "already_paid"
            skipped += 1
            continue

        if _deal_is_won(pk):
            rec["status"] = "skipped"
            rec["skip_reason"] = "deal_won"
            skipped += 1
            continue

        idem = f"vf:place:{rid}"
        try:
            from app.billing import idempotency as _idem

            if _idem.seen_before_sync(idem, ttl_s=86400):
                rec["status"] = "skipped"
                rec["skip_reason"] = "duplicate_place"
                skipped += 1
                continue
        except Exception:
            pass

        try:
            from app.api.telephony_vobiz import start_stream_call
            from app.platform.inquiry_hooks import resolve_wizard_opening

            result = await start_stream_call(
                to=pk,
                niche=str(rec.get("niche") or "ai_marketing"),
                client_id=cid or None,
                call_type="transactional",
                # Business-type-aware followup (wizard niche + name) — wizard
                # opening se greet, generic niche script nahi. Resolve fail = ""
                # → purana niche-script chain (unchanged).
                opening_line=resolve_wizard_opening(
                    niche=str(rec.get("niche") or ""),
                    business_name=str(rec.get("business_name") or ""),
                ),
            )
            if result.get("placed"):
                rec["status"] = "placed"
                rec["placed_at"] = _now().isoformat()
                placed += 1
                try:
                    from app.platform.speed_to_lead import log_callback_touch

                    log_callback_touch(pk, placed=True)
                except Exception:
                    pass
            else:
                err = str(result.get("error") or "not_placed")
                rec["attempts"] = int(rec.get("attempts") or 0) + 1
                if err == "compliance_blocked" and rec["attempts"] < 5:
                    rec["last_error"] = err
                    skipped += 1
                    continue
                if rec["attempts"] >= 3:
                    rec["status"] = "skipped"
                    rec["skip_reason"] = err[:80]
                else:
                    rec["last_error"] = err[:80]
                skipped += 1
        except Exception as e:
            rec["attempts"] = int(rec.get("attempts") or 0) + 1
            if rec["attempts"] >= 3:
                rec["status"] = "skipped"
                rec["skip_reason"] = str(e)[:80]
            skipped += 1

    if due:
        _write_all(_STORE, rows)

    summary = {
        "ok": True,
        "placed": placed,
        "skipped": skipped,
        "due_checked": len(due),
        "at": _now().isoformat(),
    }
    _append(_RUNS, summary)
    try:
        from app.platform.team import log_event

        log_event(
            "swara",
            "voice_followup_run",
            f"placed={placed} skipped={skipped} due={len(due)}",
            status="ok" if placed or not due else "warn",
            meta=summary,
        )
    except Exception:
        pass
    return summary


def stats() -> dict[str, Any]:
    rows = _read(_STORE)
    pending = sum(1 for r in rows if r.get("status") == "pending")
    placed = sum(1 for r in rows if r.get("status") == "placed")
    return {
        "enabled": _enabled(),
        "pending": pending,
        "placed": placed,
        "total": len(rows),
    }


__all__ = [
    "schedule_trial_callbacks",
    "schedule_interested_followup",
    "cancel_for_phone",
    "run_post_call_workflows",
    "run_due",
    "stats",
]
