"""Own-domain short links + click tracking — attribution loop apne control me.

Pehle drafts is.gd (3rd-party, no analytics) use karte the (content_feedback.shorten).
Ab apna `leadsgenai.in/r/{code}` — click count + channel attribution + (best-effort)
channel-bandit credit. is.gd ka complement/replacement: jahan attribution chahiye
wahan `create()` use karo.

  create(url, label, channel, client_id) -> {ok, code, short_url}
  resolve(code, ua, ref)                 -> long URL | None (click bhi log hota)
  stats(code="")                         -> clicks by code / channel / day

Stores: data/short_links.jsonl (links) + data/link_clicks.jsonl (clicks).
Pure stdlib + file IO (NO ML/network) — public redirect path light rahe.
NEVER raises.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import time
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_LINKS_FILE = os.path.join("data", "short_links.jsonl")
_CLICKS_FILE = os.path.join("data", "link_clicks.jsonl")

# Ambiguous chars (0/O, 1/l/I) skip — print/bol ke share hota hai.
_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789ABCDEFGHJKMNPQRSTUVWXYZ"
_CODE_RE = re.compile(r"^[A-Za-z0-9]{4,12}$")

# Worker-local cache (miss par file reload — multi-worker safe enough).
_cache: dict[str, dict[str, Any]] = {}
_cache_loaded = False


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _append(path: str, rec: dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning(f"short_links append failed: {e}")


def _read_all(path: str) -> list[dict[str, Any]]:
    try:
        if not os.path.isfile(path):
            return []
        out: list[dict[str, Any]] = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if isinstance(rec, dict):
                    out.append(rec)
        return out
    except Exception as e:
        logger.warning(f"short_links read failed: {e}")
        return []


def _load_cache(force: bool = False) -> dict[str, dict[str, Any]]:
    global _cache_loaded
    if _cache_loaded and not force:
        return _cache
    try:
        for rec in _read_all(_LINKS_FILE):
            code = str(rec.get("code") or "")
            if code:
                _cache[code] = rec
        _cache_loaded = True
    except Exception:  # pragma: no cover - _read_all defensive hai
        pass
    return _cache


def short_url(code: str) -> str:
    """Public short URL (site base reuse — embed_widget wala helper)."""
    try:
        from app.marketing.embed_widget import site_base

        return f"{site_base()}/r/{code}"
    except Exception:
        return f"https://leadsgenai.in/r/{code}"


def _new_code() -> str:
    cache = _load_cache()
    for _ in range(20):
        code = "".join(secrets.choice(_ALPHABET) for _ in range(6))
        if code not in cache:
            return code
    return "".join(secrets.choice(_ALPHABET) for _ in range(9))  # pragma: no cover


def create(url: str, label: str = "", channel: str = "", client_id: str = "") -> dict[str, Any]:
    """Naya short link banao. Sirf http(s) URLs. Never raises."""
    try:
        url = (url or "").strip()
        if not url.lower().startswith(("http://", "https://")) or len(url) > 2000:
            return {"ok": False, "error": "valid http(s) URL chahiye."}
        rec = {
            "code": _new_code(),
            "url": url,
            "label": (label or "").strip()[:120],
            "channel": (channel or "").strip().lower()[:40],
            "client_id": (client_id or "").strip()[:60],
            "created_at": _now(),
        }
        _append(_LINKS_FILE, rec)
        _load_cache()[rec["code"]] = rec
        return {"ok": True, "code": rec["code"], "short_url": short_url(rec["code"]), "link": rec}
    except Exception as e:
        logger.warning(f"short_links create failed: {e}")
        return {"ok": False, "error": str(e)[:160]}


def _credit_channel(code: str, channel: str) -> None:
    """Best-effort channel-bandit credit — max 1/code/day (clicks inflate na karein).

    channel_experiments.record_outcome PUBLIC fn hai aur khud unknown channel
    reject karta (never raises) — isliye direct call SAFE.
    """
    try:
        if not channel:
            return
        today = time.strftime("%Y-%m-%d")
        for c in _read_all(_CLICKS_FILE):
            if c.get("code") == code and str(c.get("ts") or "").startswith(today):
                return  # aaj pehle hi credit ho chuka (yeh click abhi log NAHI hua)
        from app.marketing import channel_experiments

        channel_experiments.record_outcome(channel, kind="click", note=f"short:{code}")
    except Exception as e:
        logger.debug(f"short_links bandit credit skipped: {e}")


def resolve(code: str, ua: str = "", ref: str = "") -> str | None:
    """Code → long URL (+ click log + bandit credit). Unknown/invalid = None."""
    try:
        code = (code or "").strip()
        if not _CODE_RE.match(code):
            return None
        rec = _load_cache().get(code)
        if rec is None:
            rec = _load_cache(force=True).get(code)  # dusre worker ne banaya ho
        if rec is None:
            return None
        _credit_channel(code, str(rec.get("channel") or ""))
        _append(
            _CLICKS_FILE,
            {
                "ts": _now(),
                "code": code,
                "channel": str(rec.get("channel") or ""),
                "ua": (ua or "")[:80],
                "ref": (ref or "")[:80],
            },
        )
        return str(rec.get("url") or "") or None
    except Exception as e:
        logger.warning(f"short_links resolve failed: {e}")
        return None


def stats(code: str = "") -> dict[str, Any]:
    """Click stats — by code / channel / day (sab ya ek code). Never raises."""
    try:
        clicks = _read_all(_CLICKS_FILE)
        if code:
            clicks = [c for c in clicks if c.get("code") == code]
        by_code: dict[str, int] = {}
        by_channel: dict[str, int] = {}
        by_day: dict[str, int] = {}
        for c in clicks:
            by_code[str(c.get("code") or "?")] = by_code.get(str(c.get("code") or "?"), 0) + 1
            ch = str(c.get("channel") or "direct") or "direct"
            by_channel[ch] = by_channel.get(ch, 0) + 1
            day = str(c.get("ts") or "")[:10] or "?"
            by_day[day] = by_day.get(day, 0) + 1
        links = _read_all(_LINKS_FILE)
        if code:
            links = [r for r in links if r.get("code") == code]
        return {
            "ok": True,
            "total_clicks": len(clicks),
            "total_links": len(links),
            "by_code": by_code,
            "by_channel": by_channel,
            "by_day": dict(sorted(by_day.items())[-30:]),
            "links": [
                {
                    **r,
                    "short_url": short_url(str(r.get("code") or "")),
                    "clicks": by_code.get(str(r.get("code") or ""), 0),
                }
                for r in links[-100:]
            ],
        }
    except Exception as e:
        logger.warning(f"short_links stats failed: {e}")
        return {"ok": False, "error": str(e)[:160]}


__all__ = ["create", "resolve", "stats", "short_url"]
