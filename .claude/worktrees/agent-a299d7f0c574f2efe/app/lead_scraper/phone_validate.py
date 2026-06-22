"""Validate + normalize phone numbers via **phonenumbers** (Google libphonenumber port).

Cleaner lead data = fewer wasted WhatsApp/call attempts and correct E.164 formatting for
telephony. Defaults to India ("IN"). Tells you if a number is a real, valid mobile.

Defensive: if `phonenumbers` is missing, falls back to an Indian 10-digit regex. Never raises.

Use:
  from app.lead_scraper.phone_validate import validate_in
  r = validate_in("098765 43210")
  # {"ok": True, "e164": "+919876543210", "national": "098765 43210",
  #  "digits": "9876543210", "is_mobile": True}
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


def _fallback(raw: str) -> dict:
    digits = re.sub(r"\D", "", raw or "")
    m = re.search(r"([6-9]\d{9})$", digits)  # last 10 digits, Indian mobile range
    if m:
        ten = m.group(1)
        return {"ok": True, "e164": "+91" + ten, "national": ten, "digits": ten, "is_mobile": True}
    return {"ok": False, "e164": "", "national": "", "digits": digits, "is_mobile": False}


def available() -> bool:
    try:
        import phonenumbers  # noqa: F401

        return True
    except Exception:
        return False


def validate_in(raw: str, region: str = "IN") -> dict:
    """Validate/format a number (default region India). Never raises."""
    s = (raw or "").strip()
    if not s:
        return {"ok": False, "e164": "", "national": "", "digits": "", "is_mobile": False}
    try:
        import phonenumbers

        num = phonenumbers.parse(s, region)
        if not phonenumbers.is_valid_number(num):
            return _fallback(s)
        ntype = phonenumbers.number_type(num)
        is_mobile = ntype in (
            phonenumbers.PhoneNumberType.MOBILE,
            phonenumbers.PhoneNumberType.FIXED_LINE_OR_MOBILE,
        )
        e164 = phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164)
        national = phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.NATIONAL)
        return {
            "ok": True,
            "e164": e164,
            "national": national,
            "digits": re.sub(r"\D", "", e164)[-10:],
            "is_mobile": is_mobile,
        }
    except Exception:
        return _fallback(s)


__all__ = ["available", "validate_in"]
