"""Clean web text + contact extraction via **trafilatura** — optional, defensive.

trafilatura is the highest-accuracy open-source main-text extractor (beats readability/
boilerpipe in benchmarks). We use it to pull a business's real "about/services" text and
contacts from their website — better competitor analysis and prospect enrichment than the
current crude regex-on-raw-HTML. Free, CPU.

No env flag: if trafilatura isn't installed, ``clean_text`` falls back to a crude tag
strip; ``find_contacts`` is pure-regex and always works. Never raises.

Use:
  from app.lead_scraper import web_extract
  text = web_extract.clean_text(html)               # clean body text
  info = web_extract.find_contacts(html)            # {"emails":[...], "phones":[...]}
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_EMAIL = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
# Indian mobile numbers, optional +91/0 prefix
_PHONE = re.compile(r"(?:\+?91[\-\s]?|0)?([6-9]\d{9})\b")


def available() -> bool:
    try:
        import trafilatura  # noqa: F401

        return True
    except Exception:
        return False


def clean_text(html: str) -> str:
    """Main body text from raw HTML. Falls back to a crude tag strip if trafilatura is absent."""
    if not (html or "").strip():
        return ""
    try:
        import trafilatura

        out = trafilatura.extract(html, include_comments=False, include_tables=False)
        if out and out.strip():
            return out.strip()
    except Exception as exc:
        logger.info("clean_text trafilatura unavailable (%s)", exc)
    # fallback: strip tags
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def find_contacts(text_or_html: str) -> dict[str, Any]:
    """Emails + Indian mobile numbers (deduped). Pure regex — always works."""
    s = text_or_html or ""
    emails = sorted({e.lower() for e in _EMAIL.findall(s) if "." in e.split("@")[-1]})
    phones = sorted(set(_PHONE.findall(s)))
    return {"emails": emails, "phones": phones}


__all__ = ["available", "clean_text", "find_contacts"]
