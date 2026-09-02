"""Post-call AI summary formatter — WhatsApp-ready call reports.

Call khatam hone ke baad qualifier output (interest_score, summary, next_action)
ko rich formatted WhatsApp message me convert karta hai with action items,
key details, aur emoji-rich formatting for instant readability.

Design:
  - Pure formatter — no I/O, no network calls. Easy to test.
  - Output stays within WhatsApp's 4096 char limit (truncates gracefully).
  - Hinglish-friendly labels for Indian SMB audience.
  - Feature-gated: POST_CALL_SUMMARY env flag (default OFF).
"""

from __future__ import annotations

import os
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# --------------------------------------------------------------------------- #
# Interest level → emoji + label
# --------------------------------------------------------------------------- #
_INTEREST_MAP: dict[int, tuple[str, str]] = {
    # score range → (emoji, label)
}


def _interest_label(score: int) -> tuple[str, str]:
    """Return (emoji, label) for a 0-5 interest score."""
    if score >= 4:
        return "🔥", "High Interest"
    if score >= 3:
        return "✅", "Moderate Interest"
    if score >= 2:
        return "🤔", "Low Interest"
    return "❌", "Not Interested"


def _budget_label(signal: str) -> str:
    """Human-readable budget signal."""
    return {
        "high": "💰 High Budget",
        "medium": "💵 Medium Budget",
        "low": "🪙 Budget Conscious",
    }.get(signal, "❓ Unknown Budget")


def _qualification_badge(qualified: bool, appointment: bool) -> str:
    if appointment:
        return "📅 APPOINTMENT REQUESTED"
    if qualified:
        return "✅ QUALIFIED LEAD"
    return "📋 FOLLOW-UP NEEDED"


# --------------------------------------------------------------------------- #
# Core formatter
# --------------------------------------------------------------------------- #


def format_summary_message(
    qualifier: dict[str, Any],
    *,
    client_name: str = "",
    phone: str = "",
    niche: str = "",
    call_duration_s: float = 0.0,
    call_id: str = "",
) -> str:
    """Qualifier output → rich WhatsApp summary message.

    Args:
        qualifier: Output from ``call_qualifier.qualify_transcript()`` —
                   keys: interest_score, qualified, appointment_requested,
                   budget_signal, summary, next_action, followup_draft.
        client_name: Business/brand name for personalization.
        phone: Lead phone (for context, not in message).
        niche: Business niche (salon, clinic, etc.).
        call_duration_s: Call length in seconds.
        call_id: Call ID for reference.

    Returns:
        Formatted WhatsApp message (≤4096 chars).
    """
    score = int(qualifier.get("interest_score") or 0)
    qualified = bool(qualifier.get("qualified"))
    appointment = bool(qualifier.get("appointment_requested"))
    budget = str(qualifier.get("budget_signal") or "unknown")
    summary = str(qualifier.get("summary") or "").strip()
    next_action = str(qualifier.get("next_action") or "").strip()
    followup = str(qualifier.get("followup_draft") or "").strip()

    emoji, level = _interest_label(score)
    badge = _qualification_badge(qualified, appointment)
    dur_str = _format_duration(call_duration_s) if call_duration_s else ""

    # --- Build message ---
    parts: list[str] = []

    # Header
    parts.append("📞 *Call Summary — AI Report*")
    parts.append("")

    # Badge + Interest
    parts.append(f"{badge}")
    parts.append(f"{emoji} Interest: *{level}* ({score}/5)")
    if budget != "unknown":
        parts.append(f"{_budget_label(budget)}")
    parts.append("")

    # Call details
    detail_lines: list[str] = []
    if client_name:
        detail_lines.append(f"Business: {client_name}")
    if niche:
        detail_lines.append(f"Niche: {niche}")
    if dur_str:
        detail_lines.append(f"Duration: {dur_str}")
    if detail_lines:
        parts.append("📋 *Call Details:*")
        parts.extend(detail_lines)
        parts.append("")

    # AI Summary
    if summary:
        parts.append("📝 *AI Summary:*")
        parts.append(summary)
        parts.append("")

    # Action Items
    if next_action or followup:
        parts.append("🎯 *Action Items:*")
        if next_action:
            parts.append(f"• {next_action}")
        if followup:
            # Truncate followup if too long
            fu_short = followup[:300]
            if len(followup) > 300:
                fu_short += "..."
            parts.append(f"• Follow-up: {fu_short}")
        parts.append("")

    # Footer
    parts.append("—")
    parts.append("🤖 AI-generated summary | LeadGenAI")

    message = "\n".join(parts)

    # WhatsApp limit: 4096 chars
    if len(message) > 4000:
        message = message[:3997] + "..."

    return message


# --------------------------------------------------------------------------- #
# Short summary for owner (admin notification)
# --------------------------------------------------------------------------- #


def format_owner_notification(
    qualifier: dict[str, Any],
    *,
    client_name: str = "",
    phone: str = "",
    niche: str = "",
    call_id: str = "",
) -> str:
    """Compact one-liner for admin/owner ntfy push.

    Short enough for phone notification — key info only.
    """
    score = int(qualifier.get("interest_score") or 0)
    qualified = bool(qualifier.get("qualified"))
    appointment = bool(qualifier.get("appointment_requested"))
    summary = str(qualifier.get("summary") or "")[:120]
    emoji, _ = _interest_label(score)

    badge = "📅" if appointment else ("✅" if qualified else "📋")
    biz = client_name or "unknown"
    phone_tail = (phone or "")[-4:] if phone else "????"

    return (
        f"{badge} Call {emoji} {biz} (..{phone_tail}) "
        f"score={score}/5 {'QUAL' if qualified else 'FOLLOW'} | "
        f"{summary}"
    )


# --------------------------------------------------------------------------- #
# WhatsApp send helper
# --------------------------------------------------------------------------- #


async def send_post_call_summary(
    qualifier: dict[str, Any],
    *,
    phone: str = "",
    client_name: str = "",
    niche: str = "",
    call_duration_s: float = 0.0,
    call_id: str = "",
) -> dict[str, Any]:
    """Format + send AI call summary via WhatsApp. Gated POST_CALL_SUMMARY.

    Best-effort, never raises. Returns send result dict.
    """
    if not _enabled():
        return {"ok": False, "reason": "POST_CALL_SUMMARY disabled"}

    if not (phone or "").strip():
        return {"ok": False, "reason": "no_phone"}

    # Only send for calls with real conversation (score > 0 or qualified)
    score = int(qualifier.get("interest_score") or 0)
    qualified = bool(qualifier.get("qualified"))
    if score == 0 and not qualified:
        return {"ok": False, "reason": "skip_low_score"}

    try:
        message = format_summary_message(
            qualifier,
            client_name=client_name,
            phone=phone,
            niche=niche,
            call_duration_s=call_duration_s,
            call_id=call_id,
        )

        from app.integrations.whatsapp import get_whatsapp_sender

        sender = get_whatsapp_sender()
        if sender is None:
            return {"ok": False, "reason": "whatsapp_not_configured"}

        result = await sender.send_text_message(phone, message)
        if result.get("error"):
            logger.warning("[call_summary] WhatsApp send failed: %s", result.get("error"))
            return {"ok": False, "reason": str(result.get("error"))[:80]}

        logger.info(
            "[call_summary] AI summary sent to %s..%s score=%d",
            (phone or "")[:3],
            (phone or "")[-4:],
            score,
        )
        return {"ok": True, "message_id": result.get("messages", [{}])[0].get("id", "")}

    except Exception as e:
        logger.debug("[call_summary] send failed: %s", e)
        return {"ok": False, "reason": f"exception:{type(e).__name__}"}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _enabled() -> bool:
    """POST_CALL_SUMMARY flag — default OFF for safe rollout."""
    return os.environ.get("POST_CALL_SUMMARY", "0").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def _format_duration(seconds: float) -> str:
    """Format seconds to human-readable string."""
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    mins = s // 60
    secs = s % 60
    if mins < 60:
        return f"{mins}m {secs}s" if secs else f"{mins}m"
    hours = mins // 60
    mins = mins % 60
    return f"{hours}h {mins}m"


__all__ = [
    "format_summary_message",
    "format_owner_notification",
    "send_post_call_summary",
]
