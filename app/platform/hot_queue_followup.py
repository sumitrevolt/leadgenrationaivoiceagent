"""Remind the owner when Hot Queue cards remain unactioned for 24 hours."""

from __future__ import annotations

import datetime

from app.utils.logger import setup_logger

logger = setup_logger(__name__)
status = "GREEN"
capacity = 1  # Single daily follow-up check


def _age_hours(card: dict) -> float | None:
    raw = str(card.get("at") or "").strip()
    if not raw:
        return None
    try:
        created = datetime.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if created.tzinfo is None:
            created = created.replace(tzinfo=datetime.timezone.utc)
        return max(
            0.0,
            (datetime.datetime.now(datetime.timezone.utc) - created).total_seconds() / 3600,
        )
    except (TypeError, ValueError):
        return None


async def check_followup() -> dict:
    """Send one owner reminder only when currently pending cards are stale."""
    from app.integrations.ntfy import enabled as ntfy_enabled
    from app.integrations.ntfy import push as ntfy_push
    from app.platform import reply_agent

    try:
        pending = reply_agent.hot_queue(limit=200, scope="boss") or []
    except Exception as exc:
        logger.warning("Hot Queue follow-up read failed: %s", type(exc).__name__)
        return {"status": "queue_unavailable", "pending": 0, "stale": 0}
    stale = [card for card in pending if (_age_hours(card) or 0) >= 24]
    if not pending:
        return {"status": "no_pending", "pending": 0, "stale": 0}
    if not stale:
        return {"status": "no_stale", "pending": len(pending), "stale": 0}
    if not ntfy_enabled():
        return {"status": "notification_disabled", "pending": len(pending), "stale": len(stale)}

    message = (
        f"REMINDER: Hot Queue has {len(stale)} lead(s) pending for 24h+. "
        "Open https://leadsgenai.in/app/inbox to review them."
    )
    sent = await ntfy_push(
        "Hot Queue Reminder",
        message,
        priority="high",
        tags=["hotqueue", "reminder"],
    )
    if not sent:
        logger.warning("Hot Queue follow-up notification delivery failed")
        return {"status": "followup_failed", "pending": len(pending), "stale": len(stale)}
    return {"status": "followup_sent", "pending": len(pending), "stale": len(stale)}


# Export for beat registration
__all__ = ["status", "capacity", "check_followup"]
