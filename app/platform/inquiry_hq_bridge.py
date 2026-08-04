"""Bridge platform website inquiries into Hot Queue (1-click human close).

Only LeadGen-owned inquiries (no mini-site ``client_id``) become HQ cards —
customer mini-site leads stay on the customer portal. Ban-safe: wa.me draft only.
Never raises.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_TARGET_5MIN = 300


def _india_wa(phone: str) -> str:
    d = "".join(c for c in (phone or "") if c.isdigit())
    if len(d) >= 10:
        return "91" + d[-10:]
    return ""


def _draft_for(rec: dict[str, Any]) -> str:
    name = str(rec.get("business_name") or rec.get("name") or "").strip() or "ji"
    return (
        f"Namaste {name}! LeadGen AI se Sumit. Aapki inquiry mil gayi — "
        f"AI Marketing Automation se roz leads + content automate hota hai "
        f"(₹1,999/mo). 2-min demo chahiye? Pricing: https://leadsgenai.in/pricing "
        f"· Start: https://leadsgenai.in/start"
    )


def bridge_inquiry_to_hot_queue(rec: dict[str, Any]) -> dict[str, Any]:
    """Persist an inquiry as a Hot Queue draft card. Idempotent per phone+day.

    Returns ``{ok, skipped?, hq_id?}``. Never raises.
    """
    out: dict[str, Any] = {"ok": False}
    try:
        # Mini-site / customer-owned → do not pollute owner Hot Queue.
        if str(rec.get("client_id") or "").strip() or str(rec.get("source_slug") or "").strip():
            out["skipped"] = "customer_owned"
            return out
        phone = str(rec.get("phone") or "").strip()
        email = str(rec.get("email") or "").strip().lower()
        if not phone and not email:
            out["skipped"] = "no_contact"
            return out
        from app.platform import reply_agent as _ra

        frm = phone or email
        # Idempotency day must follow the inquiry timestamp (not wall-clock
        # "today") so CI/replay with fixed ``at`` still dedupes across UTC days.
        at = str(rec.get("at") or datetime.now(timezone.utc).isoformat())
        day = (
            at[:10]
            if len(at) >= 10 and at[4:5] == "-" and at[7:8] == "-"
            else datetime.now(timezone.utc).strftime("%Y-%m-%d")
        )
        for d in _ra.list_drafts(limit=500):
            if d.get("channel") != "inquiry":
                continue
            if (d.get("hq_status") or "") == "done":
                continue
            if str(d.get("from") or "").strip().lower() == frm.lower() and str(
                d.get("at") or ""
            ).startswith(day):
                out["ok"] = True
                out["skipped"] = "already_queued"
                out["hq_id"] = _ra.hq_id_for(d)
                return out

        draft = _draft_for(rec)
        wa_num = _india_wa(phone)
        card = {
            "channel": "inquiry",
            "from": frm,
            "phone": phone,
            "email": email,
            "business_name": str(rec.get("business_name") or "")[:120],
            "niche": str(rec.get("niche") or "")[:80],
            "city": str(rec.get("city") or "")[:80],
            "text": str(rec.get("message") or rec.get("notes") or "Website inquiry")[:2000],
            "intent": "interested",
            "draft": draft,
            "hq_source": "website_inquiry",
            "inquiry_id": str(rec.get("id") or rec.get("lead_id") or ""),
            "at": at,
        }
        if wa_num:
            card["wa_link"] = f"https://wa.me/{wa_num}?text={quote(draft)}"
        saved = _ra.enqueue_action_card(card)
        out["ok"] = bool(saved)
        out["hq_id"] = _ra.hq_id_for(card)
        return out
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("[inquiry_hq_bridge] skip: %s", e)
        out["error"] = str(e)[:120]
        return out


__all__ = ["bridge_inquiry_to_hot_queue", "_TARGET_5MIN"]
