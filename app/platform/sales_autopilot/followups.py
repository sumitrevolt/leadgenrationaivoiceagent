"""Sales Autopilot follow-ups — max 2, reply/opt-out/payment stop, IST hours.

Selection only: :func:`due_followups` returns the (prospect, step) pairs that are *due* a
follow-up. Whether they actually send is still decided by eligibility + send (dry-run
default). Never raises.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.platform.sales_autopilot import eligibility as _elig
from app.platform.sales_autopilot import policy as _policy_mod
from app.platform.sales_autopilot import store as _store
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Minimum gap before a follow-up is considered due (hours).
FOLLOWUP_GAP_HOURS = {"followup_1": 48, "followup_2": 120}


def _hours_since(iso_ts: str | None) -> float:
    if not iso_ts:
        return 1e9
    try:
        dt = datetime.fromisoformat(iso_ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0
    except Exception:
        return 1e9


def _next_step(rec: dict[str, Any]) -> str | None:
    fc = int(rec.get("followup_count", 0))
    if fc == 0:
        return _elig.STEP_FOLLOWUP_1
    if fc == 1:
        return _elig.STEP_FOLLOWUP_2
    return None  # cap reached


def due_followups(
    pol: _policy_mod.Policy | None = None, *, channel: str = "whatsapp"
) -> list[dict[str, Any]]:
    """Return prospects due a follow-up on ``channel``. Stops on reply/opt-out/payment/cap."""
    pol = pol or _policy_mod.get_policy()
    out: list[dict[str, Any]] = []
    try:
        for rec in _store.list_prospects(limit=1000):
            status = rec.get("status")
            # Hard stops.
            if status in (
                _store.STATUS_REPLIED,
                _store.STATUS_OPTED_OUT,
                _store.STATUS_CONVERTED,
                _store.STATUS_MANUAL_OWNER_CONFIRMED,
                _store.STATUS_NEW,
            ):
                continue
            if int(rec.get("reply_count", 0)) > 0:
                continue
            step = _next_step(rec)
            if not step:
                continue
            gap = FOLLOWUP_GAP_HOURS.get(step, 48)
            if _hours_since(rec.get("updated_at")) < gap:
                continue
            out.append({"prospect": rec, "step": step, "channel": channel})
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("[sales_autopilot.followups] due scan failed: %s", e)
    return out


__all__ = ["FOLLOWUP_GAP_HOURS", "due_followups"]
