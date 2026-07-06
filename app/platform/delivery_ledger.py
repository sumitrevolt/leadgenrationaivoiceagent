"""
delivery_ledger.py — single source-of-truth customer-facing delivery ledger.

WHY: content generation already runs (auto_content.py) but customers had no
provable trail of what actually happened for them, and admin had no single
place to see it either. This module is that trail. Mirrors app/platform/
team.py's log_event()/_db() conventions exactly: sync, defensive, never
raises — a ledger write must never break the real work it's recording.

log_event(client_id, event_type, ...)     -> None   (never raises)
get_timeline(client_id, audience=...)     -> list[dict]  (never raises, [] on any error)

`audience` controls which label renders for a stored row — "customer" (plain
Hinglish, no internals) or "admin" (technical, includes `detail`). Same row,
two renderings — no duplicated storage.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# The mission's 14 canonical event types. Unknown types are still logged (never
# raise) but fall back to a generic label — see _label().
EVENT_TYPES: set[str] = {
    "customer_created",
    "plan_activated",
    "onboarding_started",
    "onboarding_completed",
    "marketing_calendar_generated",
    "post_draft_created",
    "post_approved",
    "post_published",
    "post_failed",
    "lead_captured",
    "followup_sent",
    "weekly_report_generated",
    "automation_failed",
    "admin_manual_action",
}

# event_type -> (customer-facing Hinglish label, icon). Admin label is built
# from the same base line + the raw technical `detail` (see _label()).
EVENT_LABELS: dict[str, tuple[str, str]] = {
    "customer_created": ("Aapka account ban gaya", "🆕"),
    "plan_activated": ("Aapka plan activate ho gaya", "✅"),
    "onboarding_started": ("Setup shuru ho gaya", "⚙️"),
    "onboarding_completed": ("Setup complete ho gaya", "🎉"),
    "marketing_calendar_generated": ("Naya content calendar taiyaar hua", "🗓️"),
    "post_draft_created": ("Naye post drafts taiyaar hue", "📝"),
    "post_approved": ("Aapne post approve kiya", "👍"),
    "post_published": ("Post publish ho gaya", "📣"),
    "post_failed": ("Post publish nahi ho paya", "⚠️"),
    "lead_captured": ("Naya lead aaya", "📥"),
    "followup_sent": ("Follow-up bheja gaya", "💬"),
    "weekly_report_generated": ("Weekly report taiyaar hua", "📊"),
    "automation_failed": ("Ek automation atak gaya", "🚨"),
    "admin_manual_action": ("Team ne manually kaam kiya", "🛠️"),
}

_FALLBACK_LABEL = ("Update hua", "•")


def _db():
    """Lazy sync Session (ya None). Mirrors app/platform/team.py:_db() exactly —
    duplicated on purpose (this repo's convention: small helpers stay local
    per module, not centralized)."""
    try:
        from app.models import base as _b

        _b._get_sync_engine()
        if _b._SessionLocal is None:
            return None
        return _b._SessionLocal()
    except Exception:
        return None


def log_event(
    client_id: str,
    event_type: str,
    detail: str = "",
    status: str = "ok",
    meta: dict[str, Any] | None = None,
) -> None:
    """Record one customer-facing delivery event. Sync, fast, never raises.

    client_id: the paying client's id (clients_store id).
    event_type: one of EVENT_TYPES (unknown values still logged, just render
      with a generic fallback label later — never raise on an unexpected type).
    detail: short technical line (admin view only).
    status: ok | warn | error.
    """
    try:
        from app.models.delivery_event import DeliveryEvent

        db = _db()
        if db is None:
            return
        try:
            row = DeliveryEvent(
                id=str(uuid.uuid4()),
                client_id=(client_id or "")[:40],
                event_type=(event_type or "event")[:40],
                detail=(detail or "")[:500],
                status=(status or "ok")[:10],
                meta_json=json.dumps(meta or {}, ensure_ascii=False, default=str)[:2000],
                created_at=datetime.utcnow(),
            )
            db.add(row)
            db.commit()
        finally:
            db.close()
    except Exception as e:  # NEVER break the caller's real work
        logger.debug("[delivery_ledger] log_event skipped: %s", e)


def _label(event_type: str, detail: str, audience: str) -> str:
    base, _icon = EVENT_LABELS.get(event_type, _FALLBACK_LABEL)
    if audience == "admin":
        return f"{base} ({event_type}: {detail})" if detail else f"{base} ({event_type})"
    return base


def get_timeline(client_id: str, limit: int = 50, audience: str = "customer") -> list[dict[str, Any]]:
    """Newest-first timeline for one client. Never raises — [] on any error.

    audience: "customer" (plain label only) or "admin" (label includes the
    technical event_type + detail — same underlying row, two renderings)."""
    out: list[dict[str, Any]] = []
    try:
        from app.models.delivery_event import DeliveryEvent

        db = _db()
        if db is None:
            return out
        try:
            rows = (
                db.query(DeliveryEvent)
                .filter(DeliveryEvent.client_id == str(client_id))
                .order_by(DeliveryEvent.created_at.desc())
                .limit(max(1, min(int(limit), 200)))
                .all()
            )
            for r in rows:
                _base, icon = EVENT_LABELS.get(r.event_type, _FALLBACK_LABEL)
                out.append(
                    {
                        "ts": r.created_at.isoformat() if r.created_at else "",
                        "event_type": r.event_type,
                        "label": _label(r.event_type, r.detail or "", audience),
                        "icon": icon,
                        "detail": r.detail if audience == "admin" else "",
                        "status": r.status or "ok",
                    }
                )
        finally:
            db.close()
    except Exception as e:
        logger.debug("[delivery_ledger] get_timeline skipped: %s", e)
        return []
    return out
