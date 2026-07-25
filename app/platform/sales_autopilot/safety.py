"""Sales Autopilot message safety validator — deterministic first, LLM tone-only.

Returns ``AUTO_APPROVED | AUTO_REJECTED | OWNER_EXCEPTION_REQUIRED`` for a generated
message envelope. The DETERMINISTIC checks are authoritative and always run. The LLM is
OPTIONAL and may ONLY comment on tone — it can never approve a rejected message and never
decides suppression, consent, rate limits, or payment (those live in eligibility/send).

Fail-closed: any validator error ⇒ OWNER_EXCEPTION_REQUIRED (a human must look), never a
silent approval. Never raises.
"""

from __future__ import annotations

import re
from typing import Any

from app.platform.sales_autopilot import messages as _messages
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

AUTO_APPROVED = "AUTO_APPROVED"
AUTO_REJECTED = "AUTO_REJECTED"
OWNER_EXCEPTION_REQUIRED = "OWNER_EXCEPTION_REQUIRED"

# Banned / unverifiable-claim patterns (case-insensitive).
_BANNED_PATTERNS = [
    r"\bguarantee[d]?\b",
    r"\b100%\b",
    r"\b#1\b",
    r"\bbest in (?:the )?(?:world|india|city)\b",
    r"\bno\.?\s*1\b",
    r"\brisk[- ]free\b",
    r"\bdouble your (?:sales|revenue|leads)\b",
    r"\b\d+x (?:more|roi|return)\b",
    r"\bwinner\b",
    r"\bfree money\b",
    r"\bact now\b",
    r"\blimited time only\b",
]

# Leftover template placeholders.
_PLACEHOLDER = re.compile(r"\{\{?.*?\}?\}")

_MAX_LEN = {"whatsapp": 900, "email": 4000}
_MIN_LEN = 20


def _deterministic(envelope: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    channel = str(envelope.get("channel") or "").lower()
    body = str(envelope.get("body") or "")
    text = f"{envelope.get('subject') or ''} {body}"

    if len(body.strip()) < _MIN_LEN:
        reasons.append("too_short")

    if len(body) > _MAX_LEN.get(channel, 4000):
        reasons.append("too_long")

    if _PLACEHOLDER.search(body) or _PLACEHOLDER.search(str(envelope.get("subject") or "")):
        reasons.append("unfilled_placeholder")

    low = text.lower()
    for pat in _BANNED_PATTERNS:
        if re.search(pat, low):
            reasons.append(f"banned_claim:{pat}")

    # Pricing truth: if a rupee amount is present, it must be the Starter truth (1999)
    # or a benign link number. Reject any *other* stated monthly price.
    for m in re.finditer(r"(?:rs\.?|inr|₹)\s*([0-9][0-9,]{1,7})", low):
        amount = int(m.group(1).replace(",", ""))
        if amount != _messages.STARTER_PRICE_INR:
            reasons.append(f"price_mismatch:{amount}")

    # Outreach messages must carry an opt-out affordance (STOP / opt out / unsubscribe).
    step = str(envelope.get("step") or "").lower()
    if step in ("initial", "followup_1", "followup_2"):
        if not re.search(r"\b(stop|opt[- ]?out|unsubscribe)\b", low):
            reasons.append("missing_optout")

    return {"reasons": reasons}


def _llm_tone_ok(envelope: dict[str, Any]) -> bool | None:
    """Optional tone-only check. Returns True/False/None(unavailable). Never authoritative
    for approval — a False here downgrades to OWNER_EXCEPTION_REQUIRED, never AUTO_APPROVED."""
    import os

    if os.getenv("SALES_AUTOPILOT_LLM_TONE", "0").strip().lower() not in ("1", "true", "yes", "on"):
        return None
    # Intentionally not wired to a live LLM in this INERT default build; the hook exists so
    # tone review can be added without touching the deterministic gate. Return None = skip.
    return None


def validate(envelope: dict[str, Any]) -> dict[str, Any]:
    """Validate a message envelope. Returns {status, reasons, tone}. Never raises."""
    try:
        det = _deterministic(envelope or {})
        reasons = det["reasons"]
        if reasons:
            return {"status": AUTO_REJECTED, "reasons": reasons, "tone": None}
        tone = _llm_tone_ok(envelope or {})
        if tone is False:
            return {"status": OWNER_EXCEPTION_REQUIRED, "reasons": ["tone_flagged"], "tone": False}
        return {"status": AUTO_APPROVED, "reasons": [], "tone": tone}
    except Exception as e:  # pragma: no cover - defensive; fail-closed
        logger.warning("[sales_autopilot.safety] validate failed: %s", e)
        return {"status": OWNER_EXCEPTION_REQUIRED, "reasons": ["validator_error"], "tone": None}


__all__ = [
    "AUTO_APPROVED",
    "AUTO_REJECTED",
    "OWNER_EXCEPTION_REQUIRED",
    "validate",
]
