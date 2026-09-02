"""Customer WhatsApp video review — outbound preview + inbound ingest.

Uses existing WAHA/selfhost path only. Default OFF (VIDEO_WHATSAPP_REVIEW_ENABLED).
Ban-safe: suppression, opt-in, rate limits, quiet hours, no admin tokens in body.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any
from urllib.parse import quote

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_IDEMP = os.path.join("data", ".video_wa_review_idempotency.json")
_FEEDBACK = os.path.join("data", "video_review_feedback.jsonl")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _load_idem() -> dict[str, str]:
    try:
        with open(_IDEMP, encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def _save_idem(d: dict[str, str]) -> None:
    try:
        os.makedirs(os.path.dirname(_IDEMP) or ".", exist_ok=True)
        tmp = _IDEMP + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f)
        os.replace(tmp, _IDEMP)
    except Exception as e:
        logger.warning(f"[video_wa] idem save failed: {e}")


def _append_feedback(rec: dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(_FEEDBACK) or ".", exist_ok=True)
        with open(_FEEDBACK, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning(f"[video_wa] feedback append failed: {e}")


def _quiet_hours_ist() -> bool:
    """True when outside 09:00–21:00 IST (conservative)."""
    try:
        from datetime import datetime, timedelta, timezone

        ist = timezone(timedelta(hours=5, minutes=30))
        h = datetime.now(ist).hour
        return not (9 <= h < 21)
    except Exception:
        return False


def _phone_for_client(client_id: str) -> str:
    try:
        import re as _re

        from app.marketing import clients_store

        c = clients_store.get_client(client_id) or {}
        digits = _re.sub(r"\D", "", str(c.get("phone") or c.get("whatsapp") or ""))
        if len(digits) >= 10:
            return digits[-10:]
    except Exception:
        pass
    return ""


def _suppressed(phone: str) -> bool:
    try:
        from app.marketing import wa_campaign_runner as runner

        return bool(runner.is_suppressed(phone) if hasattr(runner, "is_suppressed") else False)
    except Exception:
        try:
            from app.marketing import wa_campaign_runner as runner

            # fallback: list check
            for row in runner.list_suppressed() or []:
                if phone in str(row):
                    return True
        except Exception:
            pass
    return False


def build_review_message(rec: dict[str, Any], client: dict[str, Any]) -> str:
    biz = str(client.get("business_name") or "Aapka business")
    title = str(rec.get("title") or "Daily video")
    caption = str(rec.get("caption") or "")[:280]
    cta = str(rec.get("cta") or "Call / WhatsApp")
    platforms = ", ".join(rec.get("channels") or ["IG/FB"])
    when = str(rec.get("planned_at") or "aaj / kal")
    ver = int(rec.get("revision") or 0) + 1
    approve_url = str(rec.get("approve_url") or "")
    # Never include admin tokens — only public approve links already designed for clients.
    lines = [
        f"Namaste {biz}!",
        f"Aapka video preview ready hai — v{ver}: {title}",
        f"Purpose: {str(rec.get('purpose') or 'organic social')}",
        f"Caption: {caption}" if caption else "",
        f"CTA: {cta}",
        f"Platforms: {platforms}",
        f"Planned: {when}",
        "",
        "Reply:",
        "• APPROVE — post kar do",
        "• CHANGES <detail> — kya badalna hai",
        "• REJECT — mat post karo",
        "",
        "Ya dashboard pe approve/reject links:",
    ]
    if approve_url:
        lines.append(f"✅ {approve_url}")
    reject_url = str(rec.get("reject_url") or "")
    if reject_url:
        lines.append(f"❌ {reject_url}")
    return "\n".join(x for x in lines if x is not None)


def send_review_whatsapp(
    rec: dict[str, Any], client: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Send preview request. Idempotent per video_ad id + revision. Never raises."""
    from app.marketing.video_production import flags

    if not flags.whatsapp_review_enabled():
        return {"sent": False, "reason": "VIDEO_WHATSAPP_REVIEW_ENABLED off"}
    try:
        from app.marketing import clients_store

        cid = str(rec.get("client_id") or "")
        client = client or clients_store.get_client(cid) or {}
        if not client:
            return {"sent": False, "reason": "client_missing"}
        phone = _phone_for_client(cid)
        if not phone:
            return {"sent": False, "reason": "no_whatsapp_phone"}
        if _suppressed(phone):
            return {"sent": False, "reason": "suppressed"}
        if _quiet_hours_ist():
            return {"sent": False, "reason": "quiet_hours", "deferred": True}

        idem_key = hashlib.sha256(
            f"{rec.get('id')}:{rec.get('revision')}:wa_review".encode()
        ).hexdigest()[:24]
        seen = _load_idem()
        if seen.get(idem_key):
            return {"sent": False, "reason": "duplicate_suppressed", "idempotency_key": idem_key}

        msg = build_review_message(rec, client)
        # Prefer human 1-click wa.me draft when auto-send not available;
        # only use selfhost send when WAHA configured AND flag on.
        sent = False
        detail: dict[str, Any] = {}
        try:
            from app.integrations.whatsapp_selfhost import SelfHostWhatsApp

            wa = SelfHostWhatsApp()
            if getattr(wa, "configured", lambda: False)() or getattr(wa, "enabled", False):
                # send_text_message signatures vary — defensive
                fn = getattr(wa, "send_text_message", None) or getattr(wa, "send_text", None)
                if fn:
                    detail = fn(phone, msg) if callable(fn) else {}
                    sent = bool((detail or {}).get("ok") or (detail or {}).get("sent"))
        except Exception as e:
            detail = {"error": str(e)[:120]}

        wa_link = f"https://wa.me/91{phone}?text={quote(msg[:900])}"
        # Bind review to this phone so inbound cannot approve another tenant.
        try:
            from app.marketing import video_ad_cycle

            rid = str(rec.get("id") or "")
            if rid:
                video_ad_cycle._update(rid, review_phone=phone)  # noqa: SLF001
        except Exception:
            pass
        seen[idem_key] = _now()
        _save_idem(seen)
        return {
            "sent": sent,
            "wa_link": wa_link,
            "idempotency_key": idem_key,
            "phone_last4": phone[-4:],
            "detail": detail,
            "human_send_fallback": not sent,
        }
    except Exception as e:
        logger.warning(f"[video_wa] send failed: {e}")
        return {"sent": False, "reason": str(e)[:160]}


def _clients_matching_phone(digits: str) -> list[dict[str, Any]]:
    """Return all active clients whose phone/whatsapp ends with digits (last10)."""
    import re as _re

    from app.marketing import clients_store

    out: list[dict[str, Any]] = []
    for c in clients_store.list_clients(status="active") or []:
        ph = _re.sub(r"\D", "", str(c.get("phone") or c.get("whatsapp") or ""))[-10:]
        if ph and ph == digits:
            out.append(c)
    return out


def ingest_inbound(from_phone: str, text: str, message_id: str = "") -> dict[str, Any]:
    """Resolve pending video review for this phone and apply classified intent.

    Returns {handled, intent, video_ad_id, ...}. Never raises.

    Safety: requires VIDEO_WHATSAPP_REVIEW_ENABLED (dashboard feedback uses a
    separate customer-auth path). Shared/ambiguous phones refuse closed.
    """
    from app.marketing.video_production import flags
    from app.marketing.video_production.feedback import classify_feedback

    # Inbound WA must not activate merely because VIDEO_PRODUCTION_ENABLED is on.
    if not flags.whatsapp_review_enabled():
        return {"handled": False, "reason": "VIDEO_WHATSAPP_REVIEW_ENABLED off"}
    try:
        import re as _re

        from app.marketing import content_approval, video_ad_cycle

        digits = _re.sub(r"\D", "", str(from_phone or ""))[-10:]
        if len(digits) < 10:
            return {"handled": False, "reason": "bad_phone"}

        matches = _clients_matching_phone(digits)
        if not matches:
            return {"handled": False, "reason": "tenant_unresolved"}
        if len(matches) > 1:
            # Fail-closed: never guess across tenants that share a number.
            return {
                "handled": True,
                "intent": "ambiguous",
                "clarification": (
                    "Number multiple accounts se linked hai — dashboard se approve/reject karo."
                ),
                "reason": "phone_ambiguous_multi_tenant",
            }

        client = matches[0]
        cid = str(client.get("id") or "")
        pending = [
            r
            for r in video_ad_cycle.list_for_client(cid)
            if r.get("status") == "pending"
            # Prefer records bound to this phone at send-time; allow unbound legacy.
            and (
                not str(r.get("review_phone") or "").strip()
                or str(r.get("review_phone") or "")[-10:] == digits
            )
        ]
        if not pending:
            return {"handled": False, "reason": "no_pending_review", "client_id": cid}
        # Newest pending version
        pending.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
        rec = pending[0]
        # Exact phone bind when present on the review record
        bound = str(rec.get("review_phone") or "").strip()[-10:]
        if bound and bound != digits:
            return {"handled": False, "reason": "phone_mismatch", "client_id": cid}
        classified = classify_feedback(text)
        _append_feedback(
            {
                "at": _now(),
                "client_id": cid,
                "video_ad_id": rec.get("id"),
                "version": int(rec.get("revision") or 0),
                "approval_id": rec.get("approval_id"),
                "message_id": message_id,
                "raw": (text or "")[:500],
                "classified": classified,
            }
        )

        intent = classified.get("intent")
        if intent == "ambiguous":
            return {
                "handled": True,
                "intent": "ambiguous",
                "clarification": classified.get("clarification"),
                "video_ad_id": rec.get("id"),
                "client_id": cid,
                "version": int(rec.get("revision") or 0),
            }

        tok = str(rec.get("token") or "")
        if intent == "approve" and tok:
            from app.marketing.video_production import cell
            from app.marketing.video_production.approval_principal import (
                PrincipalRefused,
                from_whatsapp_inbound,
            )

            # Controlled refusal, by design. The route that reaches here is the
            # WAHA self-host webhook, authenticated by a shared static token —
            # not per-message provider authenticity — and the sender phone is
            # routing data, not an approver identity. There is also no review
            # token bound to record/revision/hash. Previously this approved
            # anyway and the ledger recorded it as "admin".
            try:
                principal = from_whatsapp_inbound(from_phone=from_phone, tenant_id=cid)
            except PrincipalRefused as exc:
                logger.info("[wa-review] approval refused: %s", exc.code)
                return {
                    "handled": False,
                    "intent": "approve",
                    "reason": exc.code,
                    "video_ad_id": rec.get("id"),
                    "client_id": cid,
                }

            approved = cell.approve_version(
                str(rec.get("id") or ""), int(rec.get("revision") or 0), principal=principal
            )
            if not approved.get("ok"):
                return {
                    "handled": False,
                    "intent": "approve",
                    "reason": approved.get("error") or "approval_failed",
                    "video_ad_id": rec.get("id"),
                    "client_id": cid,
                }
            return {
                "handled": True,
                "intent": "approve",
                "video_ad_id": rec.get("id"),
                "version": int(rec.get("revision") or 0),
                "client_id": cid,
            }
        if intent == "reject" and tok:
            approval = content_approval.get_by_token(tok)
            if not approval or str(approval.get("status") or "").lower() != "pending":
                return {
                    "handled": False,
                    "intent": "reject",
                    "reason": "approval_already_decided",
                }
            video_ad_cycle._update(  # noqa: SLF001 — shared store helper
                str(rec.get("id")),
                status="held_max_revisions",
                workflow_state="CLIENT_REJECTED",
                final_approved=False,
                note=(text or "")[:300],
            )
            rejected = content_approval.reject(tok, note=(text or "")[:300])
            if not rejected.get("ok") or rejected.get("already_decided"):
                return {
                    "handled": False,
                    "intent": "reject",
                    "reason": "approval_already_decided",
                }
            return {
                "handled": True,
                "intent": "reject",
                "video_ad_id": rec.get("id"),
                "client_id": cid,
            }
        if intent == "changes" and tok:
            approval = content_approval.get_by_token(tok)
            if not approval or str(approval.get("status") or "").lower() != "pending":
                return {
                    "handled": False,
                    "intent": "changes",
                    "reason": "approval_already_decided",
                }
            note = (text or "")[:300]
            changed = content_approval.reject(tok, note=note)
            if not changed.get("ok") or changed.get("already_decided"):
                return {
                    "handled": False,
                    "intent": "changes",
                    "reason": "approval_already_decided",
                }
            # on_changes_requested already via reject hook; attach structured tasks
            video_ad_cycle._update(
                str(rec.get("id")),
                revision_tasks=classified.get("tasks") or [],
                feedback_categories=classified.get("categories") or [],
            )
            return {
                "handled": True,
                "intent": "changes",
                "categories": classified.get("categories"),
                "tasks": classified.get("tasks"),
                "video_ad_id": rec.get("id"),
                "client_id": cid,
            }
        return {"handled": False, "reason": "unhandled_intent", "intent": intent}
    except Exception as e:
        logger.warning(f"[video_wa] ingest failed: {e}")
        return {"handled": False, "reason": str(e)[:160]}


__all__ = [
    "build_review_message",
    "send_review_whatsapp",
    "ingest_inbound",
]
