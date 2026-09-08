"""indexnow.py — Bing/Yandex IndexNow auto-submit (FREE, no-key signup).

Programmatic SEO pages/blog Google ke alawa Bing/Yandex pe TURANT index hon —
naye /blog/{slug} + landing pages publish hote hi search engines ko ping.

- Key: env `INDEXNOW_KEY` ya auto-generate persist `data/indexnow_key.txt`.
  Key file HAMARE host pe serve hoti hai: GET /indexnow-key.txt (main.py route),
  POST payload me `keyLocation` se point karte hain (root {key}.txt zaroori NAHI).
- `submit_urls(urls)` — manual/any-time (cap 500/call, dedupe).
- `submit_sitemap_if_enabled()` — GATED `INDEXNOW=1` (default OFF = zero change):
  apna /sitemap.xml self-fetch (scheduled job me, hot path NAHI) → <loc> parse →
  sirf NAYE/changed URLs submit (cursor sha256 me last-submitted set).
- Defensive: kabhi raise nahi karta; network fail = {"ok": False}.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_KEY_FILE = os.path.join("data", "indexnow_key.txt")
_CURSOR = os.path.join("data", "indexnow_cursor.json")
_ENDPOINT = "https://api.indexnow.org/indexnow"
_MAX_PER_CALL = 500


def _enabled() -> bool:
    return os.environ.get("INDEXNOW", "0").strip().lower() in ("1", "true", "yes")


def _base_url() -> str:
    try:
        from app.config import settings

        return (settings.public_base_url or "https://leadsgenai.in").rstrip("/")
    except Exception:
        return "https://leadsgenai.in"


def get_key() -> str:
    """IndexNow key — env override, warna persisted auto-gen (32 hex)."""
    env_key = os.environ.get("INDEXNOW_KEY", "").strip()
    if env_key:
        return env_key
    try:
        if os.path.exists(_KEY_FILE):
            k = open(_KEY_FILE, encoding="utf-8").read().strip()
            if k:
                return k
        k = secrets.token_hex(16)
        os.makedirs(os.path.dirname(_KEY_FILE) or ".", exist_ok=True)
        with open(_KEY_FILE, "w", encoding="utf-8") as f:
            f.write(k)
        return k
    except Exception as e:  # pragma: no cover
        logger.warning(f"[indexnow] key persist fail: {e}")
        return "0" * 32  # deterministic fallback (submit will just be rejected)


def build_payload(urls: list[str]) -> dict[str, Any]:
    """Pure helper (testable, no network): IndexNow POST body."""
    base = _base_url()
    host = base.split("://", 1)[-1].split("/", 1)[0]
    clean = []
    for u in urls[:_MAX_PER_CALL]:
        u = (u or "").strip()
        if not u:
            continue
        if u.startswith("/"):
            u = base + u
        if host in u:
            clean.append(u)
    return {
        "host": host,
        "key": get_key(),
        "keyLocation": f"{base}/indexnow-key.txt",
        "urlList": clean,
    }


async def submit_urls(urls: list[str]) -> dict[str, Any]:
    """URLs ko IndexNow pe POST karo (Bing+Yandex+partners ek hi ping me)."""
    payload = build_payload(urls)
    if not payload["urlList"]:
        return {"ok": False, "error": "no valid urls (same-host chahiye)"}
    try:
        import httpx

        async with httpx.AsyncClient(timeout=15) as cx:
            r = await cx.post(_ENDPOINT, json=payload)
        ok = r.status_code in (200, 202)
        if not ok:
            logger.warning(f"[indexnow] {r.status_code}: {r.text[:150]}")
        return {"ok": ok, "status": r.status_code, "submitted": len(payload["urlList"])}
    except Exception as e:
        logger.warning(f"[indexnow] submit fail: {e}")
        return {"ok": False, "error": str(e)[:160]}


def _load_seen() -> set[str]:
    try:
        if os.path.exists(_CURSOR):
            return set(json.load(open(_CURSOR, encoding="utf-8")).get("seen", []))
    except Exception:
        pass
    return set()


def _save_seen(seen: set[str]) -> None:
    try:
        os.makedirs(os.path.dirname(_CURSOR) or ".", exist_ok=True)
        with open(_CURSOR, "w", encoding="utf-8") as f:
            json.dump({"seen": sorted(seen)[-5000:]}, f)
    except Exception:
        pass


def parse_sitemap_locs(xml_text: str) -> list[str]:
    """Pure helper (testable): sitemap XML se <loc> URLs."""
    return re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml_text or "")


async def submit_sitemap_if_enabled(force: bool = False) -> dict[str, Any]:
    """Daily blog job se call hota — sirf NAYE sitemap URLs submit (gated INDEXNOW=1).

    force=True (admin manual run) = flag bypass."""
    if not force and not _enabled():
        return {"ok": False, "skipped": "INDEXNOW off"}
    try:
        import httpx

        async with httpx.AsyncClient(timeout=15) as cx:
            r = await cx.get(f"{_base_url()}/sitemap.xml")
        if r.status_code != 200:
            return {"ok": False, "error": f"sitemap {r.status_code}"}
        urls = parse_sitemap_locs(r.text)
        seen = _load_seen()
        new = [u for u in urls if hashlib.sha256(u.encode()).hexdigest() not in seen]
        if not new:
            return {"ok": True, "submitted": 0, "note": "koi naya URL nahi"}
        res = await submit_urls(new)
        if res.get("ok"):
            for u in new:
                seen.add(hashlib.sha256(u.encode()).hexdigest())
            _save_seen(seen)
            logger.info(f"[indexnow] {len(new)} naye URLs submitted")
        return res
    except Exception as e:
        logger.warning(f"[indexnow] sweep fail: {e}")
        return {"ok": False, "error": str(e)[:160]}
