"""Client content-approval loop (agency-grade) — draft → client 1-click approve.

Agency clients ko post publish hone se PEHLE approve karna hota hai. Yeh module
har content piece ka approval record banata hai + client ko bhejne ka WhatsApp
1-click link text (ban-safe: human khud WA pe bhejta hai, auto-send NAHI).

  submit(client_id, content)   -> approval record (status=pending, secret token)
  approve(token) / reject(token, note) -> decide (idempotent)
  pending(client_id="")        -> pending approvals (latest state)
  get_by_token(token)          -> latest state of one approval

Store: data/content_approvals.jsonl — append-on-update, latest line per id wins
(minisite_builder config pattern — lock-free, multi-worker safe enough).
Pure stdlib + file IO. NEVER raises.
"""

from __future__ import annotations

import json
import os
import secrets
import time
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_FILE = os.path.join("data", "content_approvals.jsonl")

_STATUSES = {"pending", "approved", "rejected"}

# Loop-social-7 (2026-07-11): extended state machine (Phase 7). Additive over
# `_STATUSES` (kept for backward compat with `_decide`'s legacy 3-state path).
# The extended machine tracks post lifecycle after approval — a caller can now
# mark `SCHEDULED / PUBLISHING / PUBLISHED / PARTIALLY_PUBLISHED / CANCELLED`
# on an approval id and the append-latest-wins JSONL keeps the audit trail.
# Legal transitions (source → allowed destinations). Anything else is refused
# with `{"ok": False, "error": "illegal_transition"}` — prevents e.g. a
# published post being flipped back to pending, or a cancelled post reviving.
_EXTENDED_STATUSES = {
    "pending", "ready_for_review", "changes_requested",
    "approved", "rejected",
    "scheduled", "publishing", "published",
    "partially_published", "cancelled",
}
_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "pending":              {"ready_for_review", "approved", "rejected", "changes_requested", "cancelled"},
    "ready_for_review":     {"approved", "rejected", "changes_requested", "cancelled"},
    "changes_requested":    {"pending", "ready_for_review", "approved", "cancelled"},
    "approved":             {"scheduled", "publishing", "cancelled"},
    "rejected":             {"pending", "cancelled"},
    "scheduled":            {"publishing", "cancelled"},
    "publishing":           {"published", "partially_published", "rejected", "cancelled"},
    "published":            set(),                     # terminal
    "partially_published":  {"publishing", "cancelled"},
    "cancelled":            set(),                     # terminal
}


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _site_base() -> str:
    try:
        from app.marketing.embed_widget import site_base

        return site_base()
    except Exception:
        return "https://leadsgenai.in"


def _append(rec: dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(_FILE) or ".", exist_ok=True)
        with open(_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning(f"[content_approval] append failed: {e}")


def _read_all() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        if not os.path.isfile(_FILE):
            return out
        with open(_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if isinstance(rec, dict):
                    out.append(rec)
    except Exception as e:
        logger.debug(f"[content_approval] read skip: {e}")
    return out


def _latest_states() -> dict[str, dict[str, Any]]:
    """id → merged latest state (append-on-update; baad wali line jeet ti)."""
    states: dict[str, dict[str, Any]] = {}
    for rec in _read_all():
        rid = str(rec.get("id") or "")
        if not rid:
            continue
        cur = states.get(rid) or {}
        cur.update(rec)
        states[rid] = cur
    return states


def _client_phone(client_id: str) -> str:
    try:
        from app.marketing import clients_store

        c = clients_store.get_client(client_id) or {}
        import re as _re

        return _re.sub(r"\D", "", str(c.get("phone") or ""))[-10:]
    except Exception:
        return ""


def approval_url(token: str, action: str = "approve") -> str:
    return f"{_site_base()}/api/clientops/approve/{token}?action={action}"


def wa_share_text(rec: dict[str, Any]) -> dict[str, str]:
    """Client ko bhejne wala WA message (1-click approve/reject links) + wa.me
    draft link (ban-safe — human send)."""
    content = rec.get("content") or {}
    caption = str(content.get("caption") or content.get("text") or "")[:200]
    title = str(content.get("title") or content.get("occasion") or "naya post")[:80]
    msg = (
        f"Namaste! Aapke business ka {title} taiyaar hai 👇\n\n"
        + (f"“{caption}”\n\n" if caption else "")
        + f"✅ Approve: {approval_url(str(rec.get('token') or ''), 'approve')}\n"
        + f"❌ Change chahiye: {approval_url(str(rec.get('token') or ''), 'reject')}\n\n"
        + "Ek click me ho jayega — shukriya!"
    )
    phone = _client_phone(str(rec.get("client_id") or ""))
    wa_link = (
        f"https://wa.me/91{phone}?text={quote(msg)}"
        if phone
        else f"https://wa.me/?text={quote(msg)}"
    )
    return {"message": msg, "wa_link": wa_link}


def submit(client_id: str, content: dict[str, Any]) -> dict[str, Any]:
    """Naya approval record (status=pending) + WA share draft. Never raises."""
    try:
        client_id = str(client_id or "").strip()[:60]
        if not client_id:
            return {"ok": False, "error": "client_id zaroori hai."}
        if not isinstance(content, dict) or not content:
            return {"ok": False, "error": "content (dict) zaroori hai."}
        rec = {
            "id": uuid.uuid4().hex[:12],
            "token": secrets.token_urlsafe(16),
            "client_id": client_id,
            "content": content,
            "status": "pending",
            "note": "",
            "created_at": _now(),
        }
        _append(rec)
        share = wa_share_text(rec)
        return {
            "ok": True,
            "approval": rec,
            "approve_url": approval_url(rec["token"], "approve"),
            "reject_url": approval_url(rec["token"], "reject"),
            **share,
        }
    except Exception as e:
        logger.warning(f"[content_approval] submit failed: {e}")
        return {"ok": False, "error": str(e)[:160]}


def get_by_token(token: str) -> dict[str, Any] | None:
    try:
        token = str(token or "").strip()
        if not token or len(token) > 64:
            return None
        for rec in _latest_states().values():
            if rec.get("token") == token:
                return rec
        return None
    except Exception:
        return None


def _decide(token: str, status: str, note: str = "") -> dict[str, Any]:
    try:
        rec = get_by_token(token)
        if rec is None:
            return {"ok": False, "error": "approval nahi mila (galat ya purana link)."}
        if rec.get("status") in ("approved", "rejected"):
            return {"ok": True, "already_decided": True, "approval": rec}
        update = {
            "id": rec["id"],
            "token": rec.get("token"),
            "client_id": rec.get("client_id"),
            "status": status if status in _STATUSES else "pending",
            "note": str(note or "").strip()[:300],
            "decided_at": _now(),
        }
        _append(update)
        merged = {**rec, **update}
        if status == "approved":
            try:
                from app.marketing import auto_content

                auto_content.enqueue_approved(
                    str(merged.get("client_id") or ""),
                    merged.get("content") or {},
                    str(merged.get("id") or ""),
                )
            except Exception:
                pass
            # Delivery ledger — this path creates a fresh queue item (not a
            # mark_item mutation), so it needs its own post_approved log;
            # auto_content.mark_item() covers the admin manual-approve path.
            try:
                from app.marketing import delivery_ledger

                content = merged.get("content") or {}
                title = str(content.get("title") or content.get("occasion") or "")
                delivery_ledger.log_event(str(merged.get("client_id") or ""), "post_approved", detail=title)
            except Exception as le:
                logger.debug(f"[content_approval] ledger log skip: {le}")
            # Video-ad approve -> publish-queue mark (scheduler hi publish karta; web light).
            try:
                if (merged.get("content") or {}).get("type") == "video_ad":
                    from app.marketing import video_ad_cycle

                    video_ad_cycle.on_approved(merged)
            except Exception:
                pass
        # Video-ad "change chahiye" (reject) -> changes_requested mark (scheduler regen).
        if status == "rejected":
            try:
                if (merged.get("content") or {}).get("type") == "video_ad":
                    from app.marketing import video_ad_cycle

                    video_ad_cycle.on_changes_requested(merged)
            except Exception:
                pass
        # Best-effort team event — dashboard pe dikhe (kabhi raise nahi).
        try:
            from app.platform.team import log_event

            log_event(
                "isha",
                "content_approval",
                f"Client {merged.get('client_id')} ne content {status} kiya"
                + (f" — note: {update['note']}" if update["note"] else ""),
                meta={"approval_id": merged.get("id"), "status": status},
            )
        except Exception:
            pass
        return {"ok": True, "approval": merged}
    except Exception as e:
        logger.warning(f"[content_approval] decide failed: {e}")
        return {"ok": False, "error": str(e)[:160]}


def approve(token: str) -> dict[str, Any]:
    return _decide(token, "approved")


def reject(token: str, note: str = "") -> dict[str, Any]:
    return _decide(token, "rejected", note)


def pending(client_id: str = "") -> list[dict[str, Any]]:
    """Pending approvals (optionally ek client ke). Never raises."""
    try:
        client_id = str(client_id or "").strip()
        rows = [
            r
            for r in _latest_states().values()
            if r.get("status") == "pending" and (not client_id or r.get("client_id") == client_id)
        ]
        rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
        return rows
    except Exception as e:
        logger.warning(f"[content_approval] pending failed: {e}")
        return []


def _by_id_for_client(client_id: str, approval_id: str) -> dict[str, Any] | None:
    rec = _latest_states().get(str(approval_id or "").strip())
    if not rec or str(rec.get("client_id") or "") != str(client_id or "").strip():
        return None
    return rec


def decide_for_client(
    client_id: str, approval_id: str, action: str, note: str = ""
) -> dict[str, Any]:
    """Authenticated customer portal — id se approve/reject (token expose nahi)."""
    rec = _by_id_for_client(client_id, approval_id)
    if rec is None:
        return {"ok": False, "error": "approval nahi mila."}
    token = str(rec.get("token") or "")
    if action == "reject":
        return reject(token, note)
    return approve(token)


def decide_by_id(approval_id: str, action: str, note: str = "") -> dict[str, Any]:
    """Admin/support — approval id se decide (client_id verify nahi)."""
    rec = _latest_states().get(str(approval_id or "").strip())
    if not rec:
        return {"ok": False, "error": "approval nahi mila."}
    token = str(rec.get("token") or "")
    if not token:
        return {"ok": False, "error": "approval token missing."}
    if action == "reject":
        return reject(token, note)
    return approve(token)


def transition(
    approval_id: str,
    new_status: str,
    actor: str = "system",
    note: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Loop-social-7 (2026-07-11): extended state-machine transition.

    Validates (a) approval exists, (b) new_status ∈ _EXTENDED_STATUSES,
    (c) transition allowed per _ALLOWED_TRANSITIONS. Appends a new JSONL row
    (latest-wins) with the state, actor, note, optional per-transition metadata
    (e.g. `{"scheduled_time": "2026-07-12T10:00"}` for `scheduled`, or
    `{"platforms_pending": ["instagram"], "platforms_published": ["facebook"]}`
    for `partially_published`).

    Emits canonical delivery-ledger event (Loop-social-6) so customer timeline +
    admin cockpit reflect the transition. Never raises."""
    try:
        aid = str(approval_id or "").strip()
        if not aid:
            return {"ok": False, "error": "approval_id_required"}
        ns = str(new_status or "").strip().lower()
        if ns not in _EXTENDED_STATUSES:
            return {"ok": False, "error": "invalid_status", "status": ns,
                    "allowed": sorted(_EXTENDED_STATUSES)}
        rec = _latest_states().get(aid)
        if rec is None:
            return {"ok": False, "error": "approval_not_found"}
        cur = str(rec.get("status") or "").strip().lower()
        # Legacy 3-state values that lived before this loop are treated as their
        # canonical extended equivalent for the transition check.
        if cur not in _ALLOWED_TRANSITIONS:
            cur = "pending"
        allowed = _ALLOWED_TRANSITIONS.get(cur, set())
        if ns == cur:
            return {"ok": True, "no_change": True, "approval": rec}
        if ns not in allowed:
            return {"ok": False, "error": "illegal_transition",
                    "from": cur, "to": ns, "allowed": sorted(allowed)}
        row = {
            "id": aid,
            "token": rec.get("token"),
            "client_id": rec.get("client_id"),
            "status": ns,
            "note": str(note or "").strip()[:300],
            "actor": str(actor or "system")[:60],
            "decided_at": _now(),
        }
        if isinstance(extra, dict):
            for k, v in extra.items():
                if k not in row and v is not None:
                    row[k] = v
        _append(row)
        merged = {**rec, **row}
        # Loop-social-6 wired: emit ledger event per transition (best-effort).
        _EVENT_FOR_STATUS = {
            "scheduled": "post_scheduled",
            "publishing": "post_publish_started",
            "published": "post_published",
            "partially_published": "post_partially_published",
            "cancelled": "post_cancelled",
            "rejected": "post_failed",
            "changes_requested": "post_draft_created",
        }
        ev = _EVENT_FOR_STATUS.get(ns)
        if ev:
            try:
                from app.marketing import delivery_ledger

                content = merged.get("content") or {}
                title = str(content.get("title") or content.get("occasion") or "")
                delivery_ledger.log_event(str(merged.get("client_id") or ""), ev, detail=title)
            except Exception:
                pass
        return {"ok": True, "approval": merged, "from": cur, "to": ns}
    except Exception as e:
        logger.warning(f"[content_approval] transition failed: {e}")
        return {"ok": False, "error": str(e)[:160]}


def cancel(approval_id: str, actor: str = "customer", note: str = "") -> dict[str, Any]:
    """Cancel a post at any non-terminal state. Terminal (published/cancelled)
    transitions are rejected by the state machine. Never raises."""
    return transition(approval_id, "cancelled", actor=actor, note=note)


def request_changes(approval_id: str, note: str = "", actor: str = "customer") -> dict[str, Any]:
    """Client asks for a revision (video_ad regen etc). Emits changes_requested
    then downstream `on_changes_requested` hook fires via engine wiring (video
    pipeline already listens for status=='rejected'; the extended semantic here
    is that a targeted-note revision is not the same as an outright rejection)."""
    return transition(approval_id, "changes_requested", actor=actor, note=note)


# --------------------------------------------------------------------------- #
# Loop-social-20 (2026-07-11): Phase-7 edit/replace/reschedule actions.       #
#                                                                             #
# Rule: an approval that has already dispatched (`publishing/published`) or   #
# is cancelled is FROZEN — editing after dispatch would silently lie to the   #
# provider (they already got the old body). Frontend must call `cancel()`     #
# first and re-submit. Every edit appends a new JSONL row so the audit trail  #
# preserves who changed what + when.                                          #
# --------------------------------------------------------------------------- #
_EDIT_LOCKED_STATES = {"publishing", "published", "partially_published", "cancelled"}


def _edit_action(
    approval_id: str,
    field: str,
    new_value: Any,
    actor: str,
    note: str,
    event_label: str,
) -> dict[str, Any]:
    """Common edit helper — never raises, atomic append, emits audit event."""
    try:
        aid = str(approval_id or "").strip()
        if not aid:
            return {"ok": False, "error": "approval_id_required"}
        rec = _latest_states().get(aid)
        if rec is None:
            return {"ok": False, "error": "approval_not_found"}
        cur_status = str(rec.get("status") or "").strip().lower()
        if cur_status in _EDIT_LOCKED_STATES:
            return {"ok": False, "error": "edit_locked",
                    "status": cur_status,
                    "message": "Post is already dispatched — cancel + resubmit for changes"}
        # Deep-copy content so we don't mutate the merged read view.
        content = dict(rec.get("content") or {})
        content[field] = new_value
        row = {
            "id": aid,
            "token": rec.get("token"),
            "client_id": rec.get("client_id"),
            "status": cur_status or "pending",
            "content": content,
            "note": str(note or "").strip()[:300],
            "actor": str(actor or "customer")[:60],
            "edited_field": field,
            "edited_at": _now(),
        }
        _append(row)
        try:
            from app.marketing import delivery_ledger

            delivery_ledger.log_event(
                str(rec.get("client_id") or ""),
                event_label,
                detail=f"{field} edited by {actor}",
                key=f"edit:{aid}:{field}:{_now()}",
            )
        except Exception:
            pass
        return {"ok": True, "approval_id": aid, "field": field,
                "actor": actor, "status": cur_status}
    except Exception as e:
        logger.warning(f"[content_approval] edit_action failed: {e}")
        return {"ok": False, "error": str(e)[:160]}


def edit_caption(
    approval_id: str,
    new_caption: str,
    actor: str = "customer",
    note: str = "",
) -> dict[str, Any]:
    """Replace the post caption. Locked if publishing/published/cancelled.
    Emits `post_draft_created` ledger event (customer visible = "new version")."""
    if not isinstance(new_caption, str):
        return {"ok": False, "error": "invalid_caption"}
    return _edit_action(
        approval_id, "caption", new_caption.strip()[:8000],
        actor, note, "post_draft_created",
    )


def replace_media(
    approval_id: str,
    media_url: str = "",
    media_path: str = "",
    media_type: str = "",
    actor: str = "customer",
    note: str = "",
) -> dict[str, Any]:
    """Swap the media asset. At least one of url/path required. media_type
    optional (auto-inferred by provider adapter)."""
    url = str(media_url or "").strip()[:1000]
    path = str(media_path or "").strip()[:500]
    if not url and not path:
        return {"ok": False, "error": "media_required",
                "message": "media_url or media_path required"}
    mtype = str(media_type or "").strip().lower()[:16]
    if mtype and mtype not in ("image", "video", "text"):
        return {"ok": False, "error": "invalid_media_type"}
    payload = {"url": url, "path": path, "type": mtype}
    return _edit_action(
        approval_id, "media", payload,
        actor, note, "post_draft_created",
    )


def change_scheduled_time(
    approval_id: str,
    when_iso: str,
    tz: str = "Asia/Kolkata",
    actor: str = "customer",
    note: str = "",
) -> dict[str, Any]:
    """Change the scheduled publish time. Rejects past times + malformed ISO.
    Emits `post_scheduled` ledger event so timeline reflects the new plan."""
    when = str(when_iso or "").strip()
    if not when:
        return {"ok": False, "error": "when_required"}
    try:
        import datetime as _dt

        try:
            parsed = _dt.datetime.fromisoformat(when)
        except ValueError:
            parsed = _dt.datetime.strptime(when[:19], "%Y-%m-%dT%H:%M:%S")
        # Reject past times — a schedule-in-past is almost always a bug.
        if parsed < _dt.datetime.utcnow() - _dt.timedelta(minutes=1):
            return {"ok": False, "error": "past_time", "message": "Scheduled time is in the past"}
    except Exception as e:
        return {"ok": False, "error": "invalid_iso", "message": str(e)[:120]}
    payload = {"scheduled_time": when, "timezone": str(tz or "Asia/Kolkata")[:64]}
    return _edit_action(
        approval_id, "schedule", payload,
        actor, note, "post_scheduled",
    )


def list_all(client_id: str = "", limit: int = 100) -> list[dict[str, Any]]:
    """Saare approvals latest-state (admin list). Never raises."""
    try:
        client_id = str(client_id or "").strip()
        rows = [
            r for r in _latest_states().values() if not client_id or r.get("client_id") == client_id
        ]
        rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
        return rows[: max(1, min(int(limit or 100), 500))]
    except Exception as e:
        logger.warning(f"[content_approval] list failed: {e}")
        return []


def decision_html(result: dict[str, Any], action: str) -> str:
    """Tiny Hinglish HTML — public approve/reject link ka response page."""
    if not result.get("ok"):
        title, body = (
            "Link sahi nahi",
            "Yeh approval link galat ya expire ho chuka hai. Apni agency se naya link maang lo.",
        )
        emoji = "🤔"
    elif result.get("already_decided"):
        st = (result.get("approval") or {}).get("status")
        emoji = "✅" if st == "approved" else "❌"
        title = "Pehle se ho chuka"
        body = f"Yeh content pehle hi {('approve' if st == 'approved' else 'reject')} ho chuka hai — kuch aur karna ho to agency ko batao."
    elif action == "reject":
        emoji, title = "❌", "Reject ho gaya"
        body = "Theek hai — team ko bata diya, naya version jald milega. Shukriya!"
    else:
        emoji, title = "✅", "Approve ho gaya — shukriya!"
        body = "Post ab publish ke liye ready hai. Aapka time bachane ke liye dhanyawad!"
    return (
        "<!doctype html><html lang='hi'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{title}</title></head>"
        "<body style='font-family:system-ui,sans-serif;background:#0f172a;color:#e2e8f0;"
        "display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0'>"
        "<div style='text-align:center;padding:32px;max-width:420px'>"
        f"<div style='font-size:56px'>{emoji}</div>"
        f"<h2 style='margin:12px 0 8px'>{title}</h2>"
        f"<p style='color:#94a3b8;line-height:1.5'>{body}</p>"
        "</div></body></html>"
    )


def _content_title(rec: dict[str, Any]) -> str:
    content = rec.get("content") or {}
    return str(content.get("title") or content.get("occasion") or rec.get("id") or "content")[:200]


def _publish_log_event(client_id: str, action: str, rec: dict[str, Any]) -> None:
    """Best-effort staff activity log for admin surfaces. Never raises."""
    try:
        from app.platform.team import log_event

        log_event(
            "isha",
            f"approval_{action}",
            f"Client {client_id} content {action}: {_content_title(rec)}",
            meta={"approval_id": rec.get("id"), "client_id": client_id, "status": rec.get("status")},
        )
    except Exception:
        pass


__all__ = [
    "submit",
    "approve",
    "reject",
    "pending",
    "list_all",
    "get_by_token",
    "decide_for_client",
    "decide_by_id",
    "schedule",
    "mark_published",
    "mark_failed",
    "wa_share_text",
    "approval_url",
    "decision_html",
]


def schedule(approval_id: str, scheduled_date: str) -> dict[str, Any]:
    """Mark approved content as scheduled for a future date (ADR-064)."""
    rec = _latest_states().get(str(approval_id or "").strip())
    if not rec:
        return {"ok": False, "error": "approval nahi mila"}
    st = str(rec.get("status") or "").lower()
    if st != "approved":
        return {"ok": False, "error": f"sirf approved posts schedule ho sakte (current: {st})"}
    rec["status"] = "scheduled"
    rec["scheduled_date"] = str(scheduled_date)[:10]
    rec["decided_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _save("scheduled", rec["client_id"], rec["id"], rec, scheduled_date=scheduled_date)
    _publish_log_event(rec["client_id"], "scheduled", rec)
    return {"ok": True, "id": rec["id"], "status": "scheduled"}


def mark_published(approval_id: str, channel: str = "", evidence_url: str = "") -> dict[str, Any]:
    """Mark content as published (manual or auto) (ADR-064)."""
    rec = _latest_states().get(str(approval_id or "").strip())
    if not rec:
        return {"ok": False, "error": "approval nahi mila"}
    st = str(rec.get("status") or "").lower()
    if st not in ("approved", "scheduled"):
        return {"ok": False, "error": f"sirf approved/scheduled posts publish ho sakte (current: {st})"}
    rec["status"] = "published"
    rec["published_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rec["publish_channel"] = str(channel)[:50] if channel else "manual"
    if evidence_url:
        rec["evidence_url"] = str(evidence_url)[:500]
    _save("published", rec["client_id"], rec["id"], rec, channel=channel)
    _publish_log_event(rec["client_id"], "published", rec)
    return {"ok": True, "id": rec["id"], "status": "published"}


def mark_failed(approval_id: str, error_message: str = "") -> dict[str, Any]:
    """Mark publishing attempt as failed (ADR-064)."""
    rec = _latest_states().get(str(approval_id or "").strip())
    if not rec:
        return {"ok": False, "error": "approval nahi mila"}
    rec["status"] = "failed"
    rec["failed_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rec["error_message"] = str(error_message)[:500] if error_message else "publish failed"
    _save("failed", rec["client_id"], rec["id"], rec)
    _publish_log_event(rec["client_id"], "failed", rec)
    return {"ok": True, "id": rec["id"], "status": "failed"}


def _save(action: str, client_id: str, approval_id: str, rec: dict, **extra) -> None:
    """Best-effort: log automation event + delivery ledger. Never raises."""
    try:
        update = dict(rec)
        update["id"] = approval_id
        update["client_id"] = client_id
        update["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        _append(update)
    except Exception:
        pass
    try:
        from app.platform.automation_log_service import log_event

        log_event(
            client_id=client_id,
            job_type=f"approval_{action}",
            status="success",
            input_summary=f"approval_id={approval_id}",
            output_summary=str(rec.get("content", {}).get("title", ""))[:200],
            triggered_by="system",
        )
    except Exception:
        pass
    try:
        from app.marketing.delivery_ledger import log_event as _ledger

        event = {
            "scheduled": "post_approved",
            "published": "post_published",
            "failed": "post_failed",
        }.get(action)
        if event:
            detail = _content_title(rec)
            if action == "scheduled" and extra.get("scheduled_date"):
                detail = f"{detail} scheduled for {str(extra.get('scheduled_date'))[:10]}"
            if action == "failed" and rec.get("error_message"):
                detail = str(rec.get("error_message") or "")[:400]
            _ledger(
                client_id,
                event,
                detail=detail,
                actor="content_approval",
                key=f"approval:{approval_id}:{action}",
            )
    except Exception:
        pass
