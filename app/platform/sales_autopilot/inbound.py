"""Sales Autopilot inbound reply handling — classify + fail-closed opt-out.

:func:`classify_reply` is a deterministic keyword classifier (LLM not required). Categories:
``OPT_OUT | INTERESTED | PRICING_QUESTION | DEMO_REQUEST | NOT_INTERESTED | PAYMENT_DONE |
QUESTION | UNKNOWN``.

:func:`handle_inbound` applies the safe policy: opt-out ⇒ INSTANT fail-closed suppression
(cross-channel), a small set of clearly-safe categories may get a templated auto-reply
(only when the auto-reply flag is on AND policy dry_run is false), and everything else
escalates to Owner OS for a human. Never raises.
"""

from __future__ import annotations

import re
from typing import Any

from app.platform.sales_autopilot import messages as _messages
from app.platform.sales_autopilot import policy as _policy_mod
from app.platform.sales_autopilot import store as _store
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

OPT_OUT = "OPT_OUT"
INTERESTED = "INTERESTED"
PRICING_QUESTION = "PRICING_QUESTION"
DEMO_REQUEST = "DEMO_REQUEST"
NOT_INTERESTED = "NOT_INTERESTED"
PAYMENT_DONE = "PAYMENT_DONE"
QUESTION = "QUESTION"
UNKNOWN = "UNKNOWN"

# Order matters: opt-out and payment are checked first (highest safety).
_PATTERNS = [
    (
        OPT_OUT,
        r"\b(stop|unsubscribe|opt[- ]?out|don'?t (?:contact|message)|remove me|band karo|mat bhejo)\b",
    ),
    (PAYMENT_DONE, r"\b(paid|payment done|paise bhej diye|transferred|utr|txn|done payment)\b"),
    (DEMO_REQUEST, r"\b(demo|show me|walkthrough|dikhao|dikha do)\b"),
    (PRICING_QUESTION, r"\b(price|pricing|cost|kitna|kitne|charges|rate|fees?)\b"),
    (NOT_INTERESTED, r"\b(not interested|no thanks|nahi chahiye|mat|later|busy)\b"),
    (INTERESTED, r"\b(interested|yes|sure|haan|ok(?:ay)?|batao|tell me more)\b"),
    (QUESTION, r"\?"),
]

# Categories that may receive a deterministic, safe templated auto-reply.
_SAFE_AUTOREPLY = {
    DEMO_REQUEST: "demo",
    PRICING_QUESTION: "pricing",
    OPT_OUT: "optout_ack",
}


def classify_reply(text: str) -> dict[str, Any]:
    t = (text or "").strip().lower()
    if not t:
        return {"category": UNKNOWN, "confidence": 0.0}
    for cat, pat in _PATTERNS:
        if re.search(pat, t):
            return {"category": cat, "confidence": 0.8}
    return {"category": UNKNOWN, "confidence": 0.3}


def _escalate(prospect_id: str, category: str, text: str) -> None:
    """Best-effort escalation to Owner OS (inbox/attention). Never raises."""
    try:
        from app.platform import owner_os

        if hasattr(owner_os, "record_attention"):
            owner_os.record_attention(  # type: ignore[attr-defined]
                kind="sales_autopilot_reply",
                ref=str(prospect_id),
                detail={"category": category, "text": text[:400]},
            )
    except Exception:
        pass


def handle_inbound(prospect_id: str, text: str, *, channel: str = "whatsapp") -> dict[str, Any]:
    """Process an inbound reply. Returns {category, action, ...}. Never raises."""
    result: dict[str, Any] = {"prospect_id": str(prospect_id), "channel": channel}
    try:
        pol = _policy_mod.get_policy()
        cls = classify_reply(text)
        category = cls["category"]
        result["category"] = category
        result["confidence"] = cls["confidence"]

        rec = _store.get_prospect(prospect_id) or {"id": str(prospect_id)}

        # 1. OPT-OUT — fail-closed, instant cross-channel suppression. ALWAYS acted on.
        if category == OPT_OUT:
            phone = rec.get("phone")
            if phone:
                try:
                    from app.marketing import wa_campaign_runner

                    wa_campaign_runner.suppress(phone, reason="sales_autopilot_optout")
                except Exception:
                    pass
            _store.mark_status(prospect_id, _store.STATUS_OPTED_OUT, opted_out=True)
            result["action"] = "suppressed"
            # Opt-out ack is transactional/consented; still gated by dry_run + flag below.
            result["auto_reply_family"] = "optout_ack"
            return result

        # 2. Record reply → stop-on-reply engages for future cadence.
        _store.mark_status(
            prospect_id,
            _store.STATUS_REPLIED,
            reply_count=int(rec.get("reply_count", 0)) + 1,
            last_reply_category=category,
        )
        if category == PAYMENT_DONE:
            # Hand off to onboarding/activation adapter — never mutate billing here.
            result["action"] = "handoff_payment"
            return result

        # 3. Safe auto-reply candidates.
        family = _SAFE_AUTOREPLY.get(category)
        can_autoreply = (
            family is not None
            and not pol.kill("auto_replies")
            and bool(pol.get("whatsapp_enabled"))
            and not pol.dry_run
        )
        if family and can_autoreply:
            env = _messages.build(rec, channel=channel, step=family)
            result["action"] = "auto_reply"
            result["auto_reply_family"] = family
            result["preview"] = env["body"]
            return result

        # 4. Everything else → escalate to a human (Owner OS).
        _escalate(prospect_id, category, text or "")
        result["action"] = "escalate_owner"
        result["auto_reply_family"] = family
        return result
    except Exception as e:  # pragma: no cover - defensive; fail-closed to escalation
        logger.warning("[sales_autopilot.inbound] handle failed: %s", e)
        _escalate(prospect_id, "error", text or "")
        result["action"] = "escalate_owner"
        result["error"] = str(e)[:120]
        return result


__all__ = [
    "OPT_OUT",
    "INTERESTED",
    "PRICING_QUESTION",
    "DEMO_REQUEST",
    "NOT_INTERESTED",
    "PAYMENT_DONE",
    "QUESTION",
    "UNKNOWN",
    "classify_reply",
    "handle_inbound",
]
