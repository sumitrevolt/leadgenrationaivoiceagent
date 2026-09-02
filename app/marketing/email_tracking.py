"""Email open + click tracking for COLD EMAIL OUTREACH (listmonk parity).

WHY
---
Outreach (``app/platform/auto_outreach.py``) sends HTML cold-emails with
``List-Unsubscribe`` headers but NO open-pixel or click-tracking, so opens /
clicks / engagement are completely invisible. This module adds a stateless,
DB-free tracking layer that mirrors the proven ``email_unsub`` design:

  - **stateless HMAC tokens** (no DB, same secret-derivation as email_unsub),
  - ``instrument(html, ...)`` rewrites links + injects a 1x1 open-pixel,
  - append-only event log ``data/email_events.jsonl``,
  - ``stats()`` aggregation,
  - **flag-gated (EMAIL_TRACKING, default OFF)** → zero behaviour change unset,
  - **never-raise everywhere** → a tracking failure must NEVER break email send
    or the public pixel/redirect response.

Env (all optional):
  EMAIL_TRACKING       "1"/"true"/"yes"/"on" to enable (default OFF).
  EMAIL_UNSUB_SECRET   HMAC secret (falls back to SECRET_KEY, then a constant)
                       — reused from email_unsub so we add no new config.
  PUBLIC_BASE_URL      public base (default https://leadsgenai.in)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import time
from pathlib import Path

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Reuse the EXACT secret-derivation chain as email_unsub so no new config is
# introduced (and tokens stay self-consistent across the outreach surface).
_SECRET = (
    os.environ.get("EMAIL_UNSUB_SECRET") or os.environ.get("SECRET_KEY") or "leadsgenai-unsub-v1"
).encode()
_STORE = Path("data") / "email_events.jsonl"

# Token "type" discriminators baked into the signed payload.
_T_OPEN = "o"
_T_CLICK = "c"

# href="..." matcher (case-insensitive, single OR double quotes).
_HREF_RE = re.compile(r"""href\s*=\s*(['"])(.*?)\1""", re.IGNORECASE | re.DOTALL)


def enabled() -> bool:
    """True only when EMAIL_TRACKING is explicitly switched on. Never raises."""
    try:
        return (os.environ.get("EMAIL_TRACKING") or "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
    except Exception:  # pragma: no cover - defensive
        return False


def _base_url() -> str:
    return (os.environ.get("PUBLIC_BASE_URL") or "https://leadsgenai.in").rstrip("/")


def _b64e(raw: str) -> str:
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def _b64d(token: str) -> str:
    pad = "=" * (-len(token) % 4)
    return base64.urlsafe_b64decode((token + pad).encode()).decode()


def _sign(payload: str) -> str:
    return hmac.new(_SECRET, payload.encode(), hashlib.sha256).hexdigest()[:32]


# --------------------------------------------------------------------------- #
# Token make / verify  (payload = "<type>|<recipient_id>|<campaign>[|<url>]")
# --------------------------------------------------------------------------- #
def _make_token(ttype: str, recipient_id: str, campaign: str, url: str = "") -> str:
    rid = (recipient_id or "").strip()
    camp = (campaign or "").strip()
    # url may contain "|" → base64 it inside the payload so the delimiter is safe.
    url_part = _b64e(url) if url else ""
    payload = "|".join([ttype, rid, camp, url_part])
    sig = _sign(payload)
    return _b64e(f"{payload}|{sig}")


def _verify_token(token: str) -> dict | None:
    """Return decoded {type, recipient_id, campaign, url} if authentic, else None.

    Never raises.
    """
    try:
        raw = _b64d(token or "")
        payload, sig = raw.rsplit("|", 1)
        if not hmac.compare_digest(sig, _sign(payload)):
            return None
        parts = payload.split("|")
        if len(parts) != 4:
            return None
        ttype, rid, camp, url_part = parts
        url = _b64d(url_part) if url_part else ""
        return {"type": ttype, "recipient_id": rid, "campaign": camp, "url": url}
    except Exception:
        return None


def make_open_token(recipient_id: str, campaign: str = "") -> str:
    """HMAC-signed, URL-safe open-pixel token. Never raises."""
    try:
        return _make_token(_T_OPEN, recipient_id, campaign)
    except Exception:  # pragma: no cover
        return ""


def make_click_token(recipient_id: str, campaign: str, url: str) -> str:
    """HMAC-signed, URL-safe click token encoding the real target URL. Never raises."""
    try:
        return _make_token(_T_CLICK, recipient_id, campaign, url)
    except Exception:  # pragma: no cover
        return ""


def verify_open_token(token: str) -> dict | None:
    """Authentic open token → decoded dict (else None). Never raises."""
    data = _verify_token(token)
    return data if (data and data.get("type") == _T_OPEN) else None


def verify_click_token(token: str) -> dict | None:
    """Authentic click token → decoded dict incl. http/https url (else None).

    Validates the decoded scheme is http/https (open-redirect safety) — even
    though the token is HMAC-signed, we never redirect to a non-http(s) scheme.
    Never raises.
    """
    data = _verify_token(token)
    if not data or data.get("type") != _T_CLICK:
        return None
    if not _is_safe_url(data.get("url", "")):
        return None
    return data


def _is_safe_url(url: str) -> bool:
    """Only absolute http/https URLs are redirect-safe. Never raises."""
    try:
        u = (url or "").strip()
        low = u.lower()
        return low.startswith("http://") or low.startswith("https://")
    except Exception:  # pragma: no cover
        return False


# --------------------------------------------------------------------------- #
# instrument()  — rewrite links + inject open pixel
# --------------------------------------------------------------------------- #
def _should_skip_href(url: str) -> bool:
    """Skip links we must NOT wrap: mailto:, tel:, anchors, unsubscribe, already
    tracked (/t/c), and the unsub endpoint. Never raises."""
    low = (url or "").strip().lower()
    if not low:
        return True
    if low.startswith(("mailto:", "tel:", "#", "{", "%")):
        return True
    if not (low.startswith("http://") or low.startswith("https://")):
        return True
    if "/t/c/" in low or "/t/o/" in low:  # already tracked
        return True
    if "unsubscribe" in low or "outreach-unsub" in low or "list-unsubscribe" in low:
        return True
    return False


def instrument(html: str, recipient_id: str, campaign: str = "") -> str:
    """Add open-pixel + click-tracking to an outbound HTML email.

    Returns ``html`` UNCHANGED when tracking is disabled or html is empty.
    Never raises — on ANY error returns the original html (email must still send).
    """
    try:
        if not enabled() or not html:
            return html
        base = _base_url()
        rid = str(recipient_id or "")

        # (a) rewrite each external href through /t/c/{token}
        def _rewrite(m: re.Match) -> str:
            quote, url = m.group(1), m.group(2)
            if _should_skip_href(url):
                return m.group(0)
            tok = make_click_token(rid, campaign, url)
            if not tok:
                return m.group(0)
            return f"href={quote}{base}/t/c/{tok}{quote}"

        out = _HREF_RE.sub(_rewrite, html)

        # (b) append 1x1 open-pixel before </body> (or at end)
        otok = make_open_token(rid, campaign)
        if otok:
            pixel = (
                f'<img src="{base}/t/o/{otok}.gif" width="1" height="1" '
                'alt="" style="display:none;border:0;outline:none" />'
            )
            if re.search(r"</body\s*>", out, re.IGNORECASE):
                out = re.sub(r"</body\s*>", pixel + "</body>", out, count=1, flags=re.IGNORECASE)
            else:
                out = out + pixel
        return out
    except Exception as ex:  # never-raise — email send must not break
        logger.debug("[email_tracking] instrument failed: %s", ex)
        return html


# --------------------------------------------------------------------------- #
# Event recording + stats
# --------------------------------------------------------------------------- #
def _append_event(ev: dict) -> bool:
    try:
        _STORE.parent.mkdir(parents=True, exist_ok=True)
        with open(_STORE, "a", encoding="utf-8") as f:
            f.write(json.dumps(ev) + "\n")
        return True
    except Exception as ex:  # pragma: no cover - never-raise
        logger.debug("[email_tracking] append failed: %s", ex)
        return False


def record_open(token: str) -> bool:
    """Verify an open token + log the event. Never raises (returns False on bad token)."""
    try:
        data = verify_open_token(token)
        if not data:
            return False
        return _append_event(
            {
                "type": "open",
                "recipient_id": data.get("recipient_id", ""),
                "campaign": data.get("campaign", ""),
                "ts": int(time.time()),
            }
        )
    except Exception:  # pragma: no cover
        return False


def record_click(token: str) -> str | None:
    """Verify a click token + log the event; return the decoded safe URL (else None).

    Never raises.
    """
    try:
        data = verify_click_token(token)
        if not data:
            return None
        url = data.get("url", "")
        _append_event(
            {
                "type": "click",
                "recipient_id": data.get("recipient_id", ""),
                "campaign": data.get("campaign", ""),
                "url": url,
                "ts": int(time.time()),
            }
        )
        return url
    except Exception:  # pragma: no cover
        return None


def stats(campaign: str | None = None) -> dict:
    """Aggregate open/click events. Optional campaign filter. Never raises.

    Returns: {opens, clicks, unique_opens, unique_clicks, by_campaign}.
    (We only see opens/clicks here — "sent" lives in the outreach log.)
    """
    result = {
        "opens": 0,
        "clicks": 0,
        "unique_opens": 0,
        "unique_clicks": 0,
        "by_campaign": {},
    }
    try:
        if not _STORE.is_file():
            return result
        open_recips: set[str] = set()
        click_recips: set[str] = set()
        by_camp: dict[str, dict] = {}
        with open(_STORE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except Exception:
                    continue
                camp = ev.get("campaign", "") or ""
                if campaign is not None and camp != campaign:
                    continue
                rid = ev.get("recipient_id", "") or ""
                etype = ev.get("type")
                cbucket = by_camp.setdefault(
                    camp,
                    {
                        "opens": 0,
                        "clicks": 0,
                        "unique_opens": set(),
                        "unique_clicks": set(),
                    },
                )
                if etype == "open":
                    result["opens"] += 1
                    cbucket["opens"] += 1
                    if rid:
                        open_recips.add(rid)
                        cbucket["unique_opens"].add(rid)
                elif etype == "click":
                    result["clicks"] += 1
                    cbucket["clicks"] += 1
                    if rid:
                        click_recips.add(rid)
                        cbucket["unique_clicks"].add(rid)
        result["unique_opens"] = len(open_recips)
        result["unique_clicks"] = len(click_recips)
        result["by_campaign"] = {
            k: {
                "opens": v["opens"],
                "clicks": v["clicks"],
                "unique_opens": len(v["unique_opens"]),
                "unique_clicks": len(v["unique_clicks"]),
            }
            for k, v in by_camp.items()
        }
    except Exception as ex:  # pragma: no cover - never-raise
        logger.debug("[email_tracking] stats failed: %s", ex)
    return result


__all__ = [
    "enabled",
    "make_open_token",
    "make_click_token",
    "verify_open_token",
    "verify_click_token",
    "instrument",
    "record_open",
    "record_click",
    "stats",
]
