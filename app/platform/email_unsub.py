"""RFC 8058 one-click unsubscribe for COLD EMAIL OUTREACH (deliverability + DPDP).

WHY
---
Gmail/Yahoo 2026 bulk-sender rules expect promotional mail to carry a
``List-Unsubscribe`` header AND a ``List-Unsubscribe-Post: List-Unsubscribe=One-Click``
header (RFC 8058) so the mail client can show a native one-click unsubscribe and
POST to our endpoint. Missing this hurts inbox placement (and spam-complaint rate
must stay < 0.3%). Our cold-outreach (Rohan) previously sent NO List-Unsubscribe
header — this closes that gap.

Transactional mail (lead alerts, reports, confirmations) must NOT use these —
one-click List-Unsubscribe is for marketing/promotional mail only.

This module is fully self-contained and never-raise:
  - stateless HMAC token per email (no DB),
  - header + footer builders,
  - tiny append-only email suppression list (data/email_suppression.jsonl),
  - inert/safe even if env unset.

Env (all optional):
  EMAIL_UNSUB_SECRET  HMAC secret (falls back to SECRET_KEY, then a constant)
  PUBLIC_BASE_URL     public base (default https://leadsgenai.in)
  OUTREACH_UNSUB_MAILTO  mailto fallback (default admin@leadsgenai.in)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from pathlib import Path

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_SECRET = (
    os.environ.get("EMAIL_UNSUB_SECRET") or os.environ.get("SECRET_KEY") or "leadsgenai-unsub-v1"
).encode()
_STORE = Path("data") / "email_suppression.jsonl"
# Path lives on the lifecycle router: app.include_router(..., prefix="/api") +
# router prefix "/lifecycle"  ->  /api/lifecycle/outreach-unsub/{token}
_UNSUB_PATH = "/api/lifecycle/outreach-unsub"


def _base_url() -> str:
    return (os.environ.get("PUBLIC_BASE_URL") or "https://leadsgenai.in").rstrip("/")


def _mailto() -> str:
    addr = (os.environ.get("OUTREACH_UNSUB_MAILTO") or "admin@leadsgenai.in").strip()
    return f"mailto:{addr}?subject=unsubscribe"


def make_token(email: str) -> str:
    """Stateless, URL-safe HMAC token encoding the email (no DB lookup needed)."""
    e = (email or "").strip().lower()
    sig = hmac.new(_SECRET, e.encode(), hashlib.sha256).hexdigest()[:32]
    return base64.urlsafe_b64encode(f"{e}|{sig}".encode()).decode().rstrip("=")


def verify_token(token: str) -> str | None:
    """Return the email if the token is authentic, else None. Never raises."""
    try:
        pad = "=" * (-len(token) % 4)
        raw = base64.urlsafe_b64decode((token + pad).encode()).decode()
        e, sig = raw.rsplit("|", 1)
        good = hmac.new(_SECRET, e.encode(), hashlib.sha256).hexdigest()[:32]
        return e if hmac.compare_digest(sig, good) else None
    except Exception:
        return None


def unsub_url(email: str) -> str:
    return f"{_base_url()}{_UNSUB_PATH}/{make_token(email)}"


def headers_for(email: str) -> dict[str, str]:
    """RFC 2369 + RFC 8058 headers for ONE promotional recipient.

    Returns {} when email is blank so callers can splat unconditionally.
    """
    e = (email or "").strip()
    if not e:
        return {}
    return {
        "List-Unsubscribe": f"<{unsub_url(e)}>, <{_mailto()}>",
        "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
    }


def footer_text(email: str) -> str:
    return f"\n\n—\nIn emails se opt-out: {unsub_url(email)}"


def footer_html(email: str) -> str:
    return (
        '<p style="font-size:11px;color:#888;margin-top:16px">'
        f'Yeh emails nahi chahiye? <a href="{unsub_url(email)}">Unsubscribe</a>.'
        "</p>"
    )


def suppress(email: str, reason: str = "one_click") -> bool:
    """Append to the email suppression list. Idempotent-enough (dup lines ok)."""
    e = (email or "").strip().lower()
    if not e:
        return False
    try:
        _STORE.parent.mkdir(parents=True, exist_ok=True)
        with open(_STORE, "a", encoding="utf-8") as f:
            f.write(json.dumps({"email": e, "reason": reason, "ts": int(time.time())}) + "\n")
        logger.info("[email_unsub] suppressed %s (%s)", e, reason)
        # Deliverability gate: one-click opt-out = strongest recipient negative signal
        # → feed spam-complaint-rate tracker (auto-pauses outreach at 0.25% over 7d).
        try:
            from app.platform import email_warmup

            email_warmup.record_complaint(e, f"unsub_{reason}")
        except Exception:
            pass
        return True
    except Exception as ex:  # pragma: no cover — never-raise
        logger.debug("[email_unsub] suppress failed: %s", ex)
        return False


def is_suppressed(email: str) -> bool:
    """True if this email previously unsubscribed. 0-cost when no store. Never raises."""
    e = (email or "").strip().lower()
    if not e:
        return False
    try:
        if not _STORE.is_file():
            return False
        with open(_STORE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    if json.loads(line).get("email") == e:
                        return True
                except Exception:
                    continue
    except Exception:  # pragma: no cover
        pass
    return False


__all__ = [
    "make_token",
    "verify_token",
    "unsub_url",
    "headers_for",
    "footer_text",
    "footer_html",
    "suppress",
    "is_suppressed",
]
