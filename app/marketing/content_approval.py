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
Pure stdlib + file IO. NEVER raises. Test-monkeypatch: `_FILE` (call-time resolver).
"""

from __future__ import annotations

import json
import os
import secrets
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def _FILE() -> str:
    """Content approvals ledger — resolved per call, never frozen at import."""
    from app.platform import runtime_data_authority as _auth

    return str(
        _auth.resolve_store_path(
            store_id="content.approvals",
            legacy_path=Path("data") / "content_approvals.jsonl",
            target_segments=("content", "content_approvals.jsonl"),
        )
    )


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
    "pending",
    "ready_for_review",
    "changes_requested",
    "approved",
    "rejected",
    "scheduled",
    "publishing",
    "published",
    "partially_published",
    "cancelled",
}
_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"ready_for_review", "approved", "rejected", "changes_requested", "cancelled"},
    "ready_for_review": {"approved", "rejected", "changes_requested", "cancelled"},
    "changes_requested": {"pending", "ready_for_review", "approved", "cancelled"},
    "approved": {"scheduled", "publishing", "cancelled"},
    "rejected": {"pending", "cancelled"},
    "scheduled": {"publishing", "cancelled"},
    "publishing": {"published", "partially_published", "rejected", "cancelled"},
    "published": set(),  # terminal
    "partially_published": {"publishing", "cancelled"},
    "cancelled": set(),  # terminal
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
        # Probe then re-resolve at each I/O site (no local bind).
        _FILE()
        os.makedirs(os.path.dirname(_FILE()) or ".", exist_ok=True)
        with open(_FILE(), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        from app.platform import runtime_data as _rd

        if isinstance(e, _rd.RuntimeDataError):
            logger.error("[content_approval] content.approvals authority UNRESOLVABLE: %s", e)
            raise
        logger.warning(f"[content_approval] append failed: {e}")


def _read_all() -> list[dict[str, Any]]:
    """All approval rows. Unresolvable authority → [] (NEVER read as approved)."""
    out: list[dict[str, Any]] = []
    try:
        _FILE()
        if not os.path.isfile(_FILE()):
            return out
        with open(_FILE(), encoding="utf-8") as f:
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
        from app.platform import runtime_data as _rd

        if isinstance(e, _rd.RuntimeDataError):
            logger.error("[content_approval] content.approvals authority UNRESOLVABLE: %s", e)
        else:
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


#: How long a newly issued, content-bound approval token stays valid.
BOUND_TOKEN_TTL_SECONDS = 7 * 24 * 3600


def bind_token_to_content(
    approval_id: str,
    *,
    tenant_id: str,
    record_id: str,
    revision: int,
    sha256: str,
    size_bytes: int = 0,
    issued_by: str = "",
    channel: str = "approval_link",
    ttl_seconds: int = BOUND_TOKEN_TTL_SECONDS,
) -> dict[str, Any]:
    """Bind an approval token to the EXACT content its recipient will see.

    Issuance — not consumption — is where the binding has to happen: a token
    that carries no revision or hash cannot be made safe later by checking
    harder at the door. Backfilling these fields onto an existing token would
    assert a content identity nobody was ever shown, so legacy tokens are
    refused for regeneration instead.

    The token STRING is not returned or logged here; the caller already holds
    it. ``token_record_id`` is the non-secret handle for audit.
    """
    import time as _time

    aid = str(approval_id or "").strip()
    digest = str(sha256 or "").strip().lower()
    if not aid:
        return {"ok": False, "error": "approval_id required"}
    if len(digest) != 64:
        return {"ok": False, "error": "sha256 must be 64-hex"}
    tid = str(tenant_id or "").strip()
    rid = str(record_id or "").strip()
    if not tid or not rid:
        return {"ok": False, "error": "tenant_id and record_id required"}
    fields = {
        "id": aid,
        "token_record_id": f"atr_{aid}",
        "bound_tenant": tid,
        "bound_record_id": rid,
        "bound_revision": int(revision),
        "bound_sha256": digest,
        "bound_bytes": int(size_bytes or 0),
        "bound_channel": str(channel or "")[:32],
        "issued_by": str(issued_by or "")[:64],
        "expires_at": int(_time.time()) + int(ttl_seconds),
        "bound_at": _now(),
    }
    # Append-on-update store: the latest line merges over the earlier state.
    _append(fields)
    return {"ok": True, "token_record_id": fields["token_record_id"]}


def token_is_expired(record: dict[str, Any]) -> bool:
    """Absent or unparsable expiry counts as EXPIRED — an unbounded token must
    never be treated as merely 'not yet expired'."""
    import time as _time

    try:
        exp = int((record or {}).get("expires_at") or 0)
    except Exception:
        return True
    return exp <= 0 or exp <= int(_time.time())


def mark_token_consumed(approval_id: str) -> bool:
    """One-time use marker. Best-effort; the saga's transaction identity is the
    authoritative replay guard, this only shortens the window."""
    try:
        aid = str(approval_id or "").strip()
        if not aid:
            return False
        _append({"id": aid, "consumed_at": _now()})
        return True
    except Exception:
        return False


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


def persist_decision(
    token: str, status: str, note: str = "", *, txn_id: str = ""
) -> dict[str, Any]:
    """LAYER A — persist ONLY the content-approval decision.

    No callback, no enqueue, no delivery-ledger event, no video-record
    mutation. Idempotent on ``txn_id``: replaying the same transaction returns
    the existing decision instead of appending a second one.

    Returns ``{"ok", "already_decided", "approval", "txn_id"}``.
    """
    try:
        rec = get_by_token(token)
        if rec is None:
            return {"ok": False, "error": "approval nahi mila (galat ya purana link)."}
        if rec.get("status") in ("approved", "rejected"):
            # Same transaction replaying => idempotent success with evidence.
            existing_txn = str(rec.get("approval_txn") or "")
            return {
                "ok": True,
                "already_decided": True,
                "approval": rec,
                "txn_id": existing_txn,
                "txn_match": bool(txn_id) and existing_txn == txn_id,
            }
        update = {
            "id": rec["id"],
            "token": rec.get("token"),
            "client_id": rec.get("client_id"),
            "status": status if status in _STATUSES else "pending",
            "note": str(note or "").strip()[:300],
            "decided_at": _now(),
        }
        if txn_id:
            update["approval_txn"] = str(txn_id)[:64]
        _append(update)
        return {
            "ok": True,
            "already_decided": False,
            "approval": {**rec, **update},
            "txn_id": str(txn_id or ""),
        }
    except Exception as e:
        logger.warning(f"[content_approval] persist_decision failed: {e}")
        return {"ok": False, "error": str(e)[:160]}


def _decide(token: str, status: str, note: str = "") -> dict[str, Any]:
    try:
        # CONTAINMENT (Stage 3B-close). A video approval must not be decided by
        # this legacy callback path at all. Four production entrypoints reach
        # here — the unauthenticated GET link, decide_for_client (customer
        # portal + boss_council) and decide_by_id (product_one_delivery
        # automation) — none of which carries a principal or a transaction.
        #
        # The refusal is BEFORE persist_decision, so no decision bytes, no
        # queue item and no delivery-ledger row are written for a refused video.
        # REJECT is unaffected: refusing to reject would trap a customer with
        # content they do not want.
        if status == "approved":
            rec_pre = get_by_token(token) or {}
            if str((rec_pre.get("content") or {}).get("type") or "") == "video_ad":
                logger.warning(
                    "[content_approval] video approval REFUSED via legacy path (%s)",
                    str(rec_pre.get("id") or "")[:40],
                )
                return {
                    "ok": False,
                    "error": "approval_token_regeneration_required",
                    "detail": "video approval must go through the coordinated approval path",
                }

        persisted = persist_decision(token, status, note)
        if not persisted.get("ok"):
            return persisted
        if persisted.get("already_decided"):
            return {"ok": True, "already_decided": True, "approval": persisted["approval"]}
        merged = persisted["approval"]
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
                delivery_ledger.log_event(
                    str(merged.get("client_id") or ""), "post_approved", detail=title
                )
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
                # `update` used to be a local of this function; the Stage 3A
                # split moved it into persist_decision and left this reference
                # dangling, so every team event raised NameError into the
                # swallow below and silently stopped being logged.
                + (f" — note: {merged.get('note')}" if merged.get("note") else ""),
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


def escalate_for_client(client_id: str, approval_id: str, note: str = "") -> dict[str, Any]:
    """Boss/council unclear — status pending rakho, needs_admin=True flag (admin desk)."""
    try:
        rec = _by_id_for_client(client_id, approval_id)
        if rec is None:
            return {"ok": False, "error": "approval nahi mila."}
        if str(rec.get("status") or "") != "pending":
            return {"ok": False, "error": "sirf pending approval escalate ho sakti hai."}
        update = {
            "id": rec["id"],
            "token": rec.get("token"),
            "client_id": rec.get("client_id"),
            "status": "pending",
            "needs_admin": True,
            "admin_note": str(note or "").strip()[:300],
            "escalated_at": _now(),
        }
        _append(update)
        merged = {**rec, **update}
        try:
            from app.platform.team import log_event

            log_event(
                "isha",
                "content_escalated",
                f"Client {merged.get('client_id')} ne approval admin ke liye park kiya",
                meta={"approval_id": merged.get("id"), "note": update["admin_note"]},
            )
        except Exception:
            pass
        return {"ok": True, "approval": merged}
    except Exception as e:
        logger.warning(f"[content_approval] escalate failed: {e}")
        return {"ok": False, "error": str(e)[:160]}


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
            return {
                "ok": False,
                "error": "invalid_status",
                "status": ns,
                "allowed": sorted(_EXTENDED_STATUSES),
            }
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
            return {
                "ok": False,
                "error": "illegal_transition",
                "from": cur,
                "to": ns,
                "allowed": sorted(allowed),
            }
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
            return {
                "ok": False,
                "error": "edit_locked",
                "status": cur_status,
                "message": "Post is already dispatched — cancel + resubmit for changes",
            }
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
        return {
            "ok": True,
            "approval_id": aid,
            "field": field,
            "actor": actor,
            "status": cur_status,
        }
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
        approval_id,
        "caption",
        new_caption.strip()[:8000],
        actor,
        note,
        "post_draft_created",
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
        return {
            "ok": False,
            "error": "media_required",
            "message": "media_url or media_path required",
        }
    mtype = str(media_type or "").strip().lower()[:16]
    if mtype and mtype not in ("image", "video", "text"):
        return {"ok": False, "error": "invalid_media_type"}
    payload = {"url": url, "path": path, "type": mtype}
    return _edit_action(
        approval_id,
        "media",
        payload,
        actor,
        note,
        "post_draft_created",
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
        approval_id,
        "schedule",
        payload,
        actor,
        note,
        "post_scheduled",
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
    reason = str(result.get("error") or "")
    if not result.get("ok"):
        if reason == "approval_token_regeneration_required":
            title, body = (
                "Naya link chahiye",
                "Is video ka approval link purana hai. Dashboard se approve karein — "
                "hum naya secure link bhej rahe hain.",
            )
        else:
            title, body = (
                "Link sahi nahi",
                "Yeh approval link galat ya expire ho chuka hai. "
                "Apni agency se naya link maang lo.",
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
        # Machine-readable refusal reason. Non-sensitive by construction (a
        # fixed vocabulary of codes) and never the credential itself.
        + (f"<!--reason:{reason}-->" if reason else "")
        + "</div></body></html>"
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
            meta={
                "approval_id": rec.get("id"),
                "client_id": client_id,
                "status": rec.get("status"),
            },
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
    "escalate_for_client",
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
        return {
            "ok": False,
            "error": f"sirf approved/scheduled posts publish ho sakte (current: {st})",
        }
    rec["status"] = "published"
    rec["published_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rec["publish_channel"] = str(channel)[:50] if channel else "manual"
    if evidence_url:
        rec["evidence_url"] = str(evidence_url)[:500]
    _save("published", rec["client_id"], rec["id"], rec, channel=channel)
    _publish_log_event(rec["client_id"], "published", rec)
    return {"ok": True, "id": rec["id"], "status": "published"}


def _fingerprint_url(url: str) -> str:
    """Deterministic SHA-256 fingerprint of a URL (first 16 hex chars). Lets
    forensic comparison across records without retaining raw PII."""
    import hashlib as _hashlib

    return _hashlib.sha256(str(url or "").encode("utf-8", errors="replace")).hexdigest()[:16]


def _redact_url_for_audit(url: str) -> str:
    """Return a customer-tenant-safe form of the URL suitable for audit
    storage. Removes `client_id=`, `customer_id=`, `tenant=`, `slug=`,
    `email=`, `phone=` query params by replacing their VALUES with
    `[REDACTED]`. Preserves scheme/host/path so operators still see
    approximate origin. Also strips the fragment (which may contain the
    opaque delivery id — safe if kept, but stripped defensively so an
    accidental fragment-based identifier can't leak here either)."""
    if not url:
        return ""
    try:
        from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

        parts = urlsplit(str(url))
        _REDACT_KEYS = {
            "client_id",
            "clientid",
            "client-id",
            "customer_id",
            "customerid",
            "customer-id",
            "tenant",
            "tenant_id",
            "tenantid",
            "slug",
            "user",
            "user_id",
            "email",
            "phone",
            "mobile",
            "token",
            "access_token",
            "api_key",
            "apikey",
            "key",
            "secret",
        }
        pairs = parse_qsl(parts.query, keep_blank_values=True)
        # Build the query manually so the `[REDACTED]` sentinel stays literal
        # (urlencode would percent-encode `[` and `]` making the audit form
        # harder to visually scan).
        query_parts = []
        for k, v in pairs:
            if k.strip().lower() in _REDACT_KEYS:
                query_parts.append(f"{k}=[REDACTED]")
            else:
                query_parts.append(f"{k}={v}")
        return urlunsplit(
            (
                parts.scheme,
                parts.netloc,
                parts.path,
                "&".join(query_parts),
                "",  # drop fragment
            )
        )
    except Exception:
        return "[REDACTED_URL]"


def update_evidence_url(
    approval_id: str,
    new_url: str,
    *,
    actor_id: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    """Amend `evidence_url` on an already-published approval WITHOUT re-firing
    publication side effects (2026-07-11 P0 evidence-hygiene loop).

    Rationale: `mark_published` was originally the only way to persist
    `evidence_url`, but it can only run from `approved`/`scheduled` and it
    triggers a fresh `post_published` ledger event + automation log — which
    would (a) refuse to run on already-published records (see gate at line
    674), (b) double-count publications on retry, (c) create a duplicate
    customer-visible "Post publish ho gaya" event. This narrow method exists
    precisely for the retroactive-PII-URL rewrite path where the publication
    is already done and only the evidence pointer needs correction.

    Invariants:
      - only runs when the approval currently has status=='published'
      - preserves `published_at`, `publish_channel`, `status`
      - never increments any publication counter
      - never appends a `post_published` event to delivery_ledger
      - idempotent: same URL twice returns {"ok": True, "no_change": True}
      - rejects blank/None (would erase evidence — refused)
      - rejects malformed non-http(s) (defensive against local paths)
      - writes an `evidence_amended` audit marker + `evidence_url_history`
        entry so the original URL is preserved for audit
    """
    aid = str(approval_id or "").strip()
    if not aid:
        return {"ok": False, "error": "approval_id required"}
    new_url = str(new_url or "").strip()
    if not new_url:
        return {
            "ok": False,
            "error": "new_url required (blank refused to prevent evidence erasure)",
        }
    if not (new_url.startswith("http://") or new_url.startswith("https://")):
        return {"ok": False, "error": "new_url must be http(s)"}
    if len(new_url) > 500:
        return {"ok": False, "error": "new_url too long (>500 chars)"}

    rec = _latest_states().get(aid)
    if not rec:
        return {"ok": False, "error": "approval nahi mila"}
    if str(rec.get("status") or "").lower() != "published":
        return {
            "ok": False,
            "error": f"update_evidence_url runs only on published (current: {rec.get('status')})",
        }

    old_url = str(rec.get("evidence_url") or "")
    if old_url == new_url:
        return {"ok": True, "no_change": True, "id": aid, "evidence_url": new_url}

    # Preserve PROOF of change without retaining raw tenant-bearing URL.
    # (2026-07-11 P0 evidence-history privacy loop.) Store a deterministic
    # sha256 fingerprint for forensic comparison + a redacted URL form where
    # sensitive query values (client_id/tenant/email/token) are stripped +
    # the fragment removed. NEVER retain the raw `old_url` in audit history.
    history = list(rec.get("evidence_url_history") or [])
    history.append(
        {
            "old_url_fingerprint": _fingerprint_url(old_url),
            "old_url_redacted": _redact_url_for_audit(old_url),
            "changed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "actor_id": str(actor_id or "system")[:80],
            "reason": str(reason or "")[:200],
        }
    )
    rec["evidence_url_history"] = history[-5:]
    rec["evidence_url"] = new_url
    rec["evidence_url_updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # Append to JSONL directly — do NOT call _save (which fires
    # automation_log + delivery_ledger post_published event).
    try:
        update = dict(rec)
        update["id"] = aid
        update["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        _append(update)
    except Exception as exc:
        logger.warning(f"[content_approval.update_evidence_url] append failed for {aid}: {exc}")
        return {"ok": False, "error": "persist failed"}

    # Emit a separate audit marker (not a publication event) so this
    # amendment is discoverable in the ledger without being counted as a
    # new publication or triggering customer notifications.
    try:
        from app.marketing.delivery_ledger import log_event as _ledger

        _ledger(
            rec["client_id"],
            "evidence_amended",
            detail=f"evidence_url rewritten (reason: {reason or 'unspecified'})",
            actor=str(actor_id or "admin")[:40],
            key=f"evidence_amended:{aid}:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}",
        )
    except Exception:
        pass

    return {
        "ok": True,
        "id": aid,
        "evidence_url": new_url,
        "previous_evidence_url_captured_in_history": bool(old_url),
    }


_PII_URL_MARKERS = (
    "client_id=",
    "customer_id=",
    "tenant=",
    "tenant_id=",
    "slug=",
    "email=",
)


def _url_contains_pii(url: str) -> bool:
    if not url:
        return False
    lower = str(url).lower()
    return any(m in lower for m in _PII_URL_MARKERS)


def _opaque_dashboard_url(approval_id: str) -> str:
    """Canonical opaque replacement — no tenant identifier."""
    return f"https://leadsgenai.in/app/dashboard#delivery/{approval_id}"


def migrate_evidence_urls(
    *,
    dry_run: bool = True,
    client_id: str | None = None,
    limit: int | None = None,
    actor_id: str = "migration",
) -> dict[str, Any]:
    """Sweep all published approvals for PII-bearing evidence URLs.

    Rewrites both the ACTIVE `evidence_url` (via update_evidence_url so all
    invariants hold) AND redacts legacy `evidence_url_history` entries that
    still contain a raw `old_url` field (pre-2026-07-11 schema).

    Idempotent: re-running after a successful pass produces zero rewrites.
    Never fires a fresh publication event. Never changes publication counts.
    Never changes plan progress. Preserves published_at / status / channel.

    dry_run=True (default): scan + count only, no mutations.
    client_id=<cid>: restrict scope to one tenant.
    limit=<N>: process at most N records (useful for staged rollout).
    """
    result = {
        "dry_run": bool(dry_run),
        "records_scanned": 0,
        "active_urls_matched": 0,
        "active_urls_rewritten": 0,
        "history_entries_matched": 0,
        "history_entries_redacted": 0,
        "already_clean": 0,
        "skipped": 0,
        "failed": 0,
        "sample_ids_active": [],  # first 5 IDs matched (for audit)
        "sample_ids_history": [],
    }

    try:
        latest = _latest_states()
    except Exception as exc:
        result["failed"] = -1
        result["error"] = f"read_all_failed:{type(exc).__name__}"
        return result

    processed = 0
    for aid, rec in latest.items():
        if client_id and str(rec.get("client_id") or "") != client_id:
            continue
        if limit is not None and processed >= int(limit):
            break
        processed += 1
        result["records_scanned"] += 1
        if str(rec.get("status") or "").lower() != "published":
            result["skipped"] += 1
            continue

        active_url = str(rec.get("evidence_url") or "")
        active_has_pii = _url_contains_pii(active_url)
        history = list(rec.get("evidence_url_history") or [])
        legacy_history = [h for h in history if "old_url" in h and "old_url_fingerprint" not in h]

        if not active_has_pii and not legacy_history:
            result["already_clean"] += 1
            continue

        if active_has_pii:
            result["active_urls_matched"] += 1
            if len(result["sample_ids_active"]) < 5:
                result["sample_ids_active"].append(aid)
        if legacy_history:
            result["history_entries_matched"] += len(legacy_history)
            if len(result["sample_ids_history"]) < 5:
                result["sample_ids_history"].append(aid)

        if dry_run:
            continue

        try:
            if active_has_pii:
                # Route through the narrow amendment API so all invariants
                # (status/timestamps unchanged, no duplicate publication)
                # are enforced by the existing implementation + tests.
                r = update_evidence_url(
                    aid,
                    _opaque_dashboard_url(aid),
                    actor_id=str(actor_id)[:80],
                    reason="migrate_evidence_urls_sweep",
                )
                if r.get("ok"):
                    result["active_urls_rewritten"] += 1
                else:
                    result["failed"] += 1
                    continue

            if legacy_history:
                # Re-read after possible amendment above.
                rec2 = _latest_states().get(aid)
                if rec2 is None:
                    result["failed"] += 1
                    continue
                new_hist: list[dict[str, Any]] = []
                redacted_count = 0
                for entry in list(rec2.get("evidence_url_history") or []):
                    if "old_url" in entry and "old_url_fingerprint" not in entry:
                        raw = str(entry.pop("old_url"))
                        entry["old_url_fingerprint"] = _fingerprint_url(raw)
                        entry["old_url_redacted"] = _redact_url_for_audit(raw)
                        entry.setdefault(
                            "migrated_at", datetime.now(timezone.utc).isoformat(timespec="seconds")
                        )
                        redacted_count += 1
                    new_hist.append(entry)
                if redacted_count:
                    rec2["evidence_url_history"] = new_hist[-5:]
                    rec2["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
                    try:
                        _append(dict(rec2))
                        result["history_entries_redacted"] += redacted_count
                    except Exception:
                        result["failed"] += 1
        except Exception:
            result["failed"] += 1

    return result


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


# --------------------------------------------------------------------------- #
# Retirement of un-actionable pending rows
#
# `pending` is the only non-terminal state and nothing ever ages out of it, so
# the queue can only grow. Prod on 2026-08-09 held 422 pending rows, of which
# 321 belonged to client ids that no longer exist in `clients_store` — work
# literally nobody can ever decide. They inflate every backlog count, drown the
# real items, and make the owner-facing "waiting on customer" number meaningless.
#
# This retires ONLY those orphans, and only by APPENDING a terminal row —
# consistent with this store's append-on-update contract, so the original
# submission stays readable forever. Nothing is deleted and no decision is
# fabricated: retiring is explicitly NOT approving. A live customer's pending
# work is never touched, whatever its age, because they can still complete it
# from the authenticated dashboard (which does not enforce the 7-day token TTL).
# --------------------------------------------------------------------------- #

STATUS_EXPIRED = "expired"


def retire_orphaned_pending(
    *,
    dry_run: bool = True,
    limit: int = 1000,
    live_client_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Retire pending rows whose client no longer exists. Never raises.

    ``dry_run=True`` (the default) reports what WOULD change and writes nothing —
    this mutates live customer records, so the counts get reviewed before the
    write. Returns per-client counts either way.

    ``live_client_ids`` is injectable for tests; production resolves it from
    ``clients_store``. If that resolution fails the sweep refuses outright rather
    than treating an empty set as "every client is dead" — the fail-closed
    direction, since the open one would retire the entire queue.
    """
    out: dict[str, Any] = {
        "ok": True,
        "dry_run": bool(dry_run),
        "scanned": 0,
        "retired": 0,
        "by_client": {},
        "skipped_live": 0,
    }
    try:
        if live_client_ids is None:
            from app.marketing import clients_store

            rows = clients_store.list_clients() or []
            live_client_ids = {str(c.get("id") or "").strip() for c in rows if c.get("id")}
            if not live_client_ids:
                return {
                    "ok": False,
                    "error": "no_live_clients_resolved",
                    "detail": "refusing to retire anything — an empty client set would retire the whole queue",
                }

        cap = max(1, min(int(limit or 1000), 20000))
        for rec in pending():
            out["scanned"] += 1
            cid = str(rec.get("client_id") or "").strip()
            if cid in live_client_ids:
                out["skipped_live"] += 1
                continue
            if out["retired"] >= cap:
                break
            out["by_client"][cid] = out["by_client"].get(cid, 0) + 1
            out["retired"] += 1
            if not dry_run:
                _append(
                    {
                        "id": rec.get("id"),
                        "client_id": cid,
                        "status": STATUS_EXPIRED,
                        "retired_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                        "retired_reason": "client_no_longer_exists",
                        # Explicitly NOT an approval. Anything reading this row
                        # must never treat it as consent to publish.
                        "decided_by": "system:retire_orphaned_pending",
                    }
                )
        return out
    except Exception as e:
        logger.warning(f"[content_approval] retire_orphaned_pending failed: {e}")
        return {"ok": False, "error": str(e)[:200]}
