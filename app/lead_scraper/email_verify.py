"""Email verification (syntax + MX deliverability) via **python-email-validator**.

Why this matters (2026 deliverability rules): Gmail/Yahoo/Outlook now REJECT bulk mail
when the bounce rate goes over ~2% — high bounces burn the sending domain. Competitors
(Hunter, Instantly, Smartlead) all verify before sending. Our live SMTP outreach scrapes
emails and must NOT send to dead addresses. This gate keeps bounces low and protects
`admin@leadsgenai.in`'s reputation — for our own outreach AND for client campaigns.

`check_mx=True` does a DNS MX lookup (real "can this domain receive mail?"); we do NOT do
SMTP probing (unreliable, often blocked, can hurt reputation). Defensive: if the library
is missing, falls back to a basic syntax check. Never raises.

Use:
  from app.lead_scraper.email_verify import verify
  r = verify("owner@dukaan.in")
  if r["ok"]:
      send_to(r["email"])      # r["email"] is normalized
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_SYNTAX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# obvious non-deliverable / role / placeholder locals worth skipping for cold outreach
_SKIP_LOCAL = {"noreply", "no-reply", "donotreply", "mailer-daemon", "postmaster"}


def available() -> bool:
    try:
        import email_validator  # noqa: F401

        return True
    except Exception:
        return False


def verify(email: str, check_mx: bool = True) -> dict:
    """Return {"ok": bool, "email": normalized, "reason": str}. Never raises."""
    raw = (email or "").strip()
    if not raw:
        return {"ok": False, "email": "", "reason": "empty"}

    local = raw.split("@", 1)[0].lower()
    if local in _SKIP_LOCAL:
        return {"ok": False, "email": raw, "reason": f"role/placeholder local '{local}'"}

    try:
        from email_validator import EmailNotValidError, validate_email

        try:
            info = validate_email(raw, check_deliverability=check_mx)
            return {"ok": True, "email": info.normalized, "reason": "valid (mx)" if check_mx else "valid"}
        except EmailNotValidError as exc:
            return {"ok": False, "email": raw, "reason": str(exc)}
    except Exception:
        # library absent -> basic syntax only (don't block sends purely on this)
        ok = bool(_SYNTAX.match(raw))
        return {"ok": ok, "email": raw, "reason": "syntax-only (email-validator absent)"}


def is_sendable(email: str) -> bool:
    """Convenience boolean for outreach gating."""
    return verify(email).get("ok", False)


__all__ = ["available", "verify", "is_sendable"]
