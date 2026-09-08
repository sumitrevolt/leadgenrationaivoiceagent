"""Bio-link page (Linktree-killer, free-stack) — per-client mobile-first link page:
WhatsApp / call / UPI / catalog / video / offer blocks bade buttons me, brand
colors (brand_kit + clients_store reuse), per-block CLICK TRACKING via redirect.

  save_bio(slug, blocks, ...)   -> config save (data/bio_links.jsonl, latest-wins)
  get_bio(slug)                 -> saved config | None
  resolve_block(slug, block_id) -> final target URL + click log (None = unknown)
  bio_stats(slug)               -> clicks per block (data/bio_clicks.jsonl)
  render_bio_html(slug)         -> standalone page (serve at /b/{slug}/bio)

Security: target URLs sirf http(s)/own-relative ya HUMARE banaye wa.me/tel:/upi:
schemes — javascript:/data: kabhi nahi (open-redirect lock). Sab user text
HTML-escaped. Pure-logic (NO LLM, no network). Never raises.
"""

from __future__ import annotations

import html
import json
import os
import re
import time
from typing import Any
from urllib.parse import quote

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_BIO_FILE = os.path.join("data", "bio_links.jsonl")
_CLICKS_FILE = os.path.join("data", "bio_clicks.jsonl")

_TYPES = {"link", "whatsapp", "call", "upi", "catalog", "video", "offer"}
_ID_RE = re.compile(r"[^a-z0-9_-]")
_MAX_BLOCKS = 12

_TYPE_EMOJI = {
    "link": "🔗",
    "whatsapp": "💬",
    "call": "📞",
    "upi": "💳",
    "catalog": "🛍️",
    "video": "🎬",
    "offer": "🎁",
}


def _slug_key(slug: str) -> str:
    return "".join(c for c in (slug or "").strip().lower() if c.isalnum() or c == "-")[:64]


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _site_base() -> str:
    try:
        from app.marketing.embed_widget import site_base

        return site_base()
    except Exception:
        return "https://leadsgenai.in"


def _load_client(slug: str) -> dict[str, Any]:
    """Client record by slug (tests monkeypatch karte hain). Never raises."""
    try:
        from app.marketing import clients_store

        return clients_store.get_by_slug(slug) or {}
    except Exception:
        return {}


def _clean_color(v: Any) -> str:
    s = str(v or "").strip()
    if s.startswith("#") and 4 <= len(s) <= 9 and all(c in "0123456789abcdefABCDEF" for c in s[1:]):
        return s
    return ""


def _brand_colors(slug: str, client: dict[str, Any] | None = None) -> tuple[str, str]:
    """(primary, accent) — brand_kit > client record > defaults."""
    primary, accent = "", ""
    try:
        client = client if isinstance(client, dict) else _load_client(slug)
        cid = client.get("id")
        if cid:
            try:
                from app.marketing import brand_kit

                colors = (brand_kit.get_brand(cid) or {}).get("colors") or {}
                primary = _clean_color(colors.get("primary"))
                accent = _clean_color(colors.get("accent"))
            except Exception:
                pass
        if not primary:
            for k in ("brand_color", "primary_color", "color", "theme_color"):
                primary = _clean_color(client.get(k))
                if primary:
                    break
    except Exception:
        pass
    return (primary or "#2563eb", accent or "#f59e0b")


# --------------------------------------------------------------------------- #
# Config (data/bio_links.jsonl, latest-wins per slug)
# --------------------------------------------------------------------------- #
def _clean_block(b: Any, idx: int) -> dict[str, Any] | None:
    if not isinstance(b, dict):
        return None
    btype = str(b.get("type") or "link").strip().lower()
    if btype not in _TYPES:
        btype = "link"
    label = str(b.get("label") or "").strip()[:60]
    value = str(b.get("url") or b.get("value") or "").strip()[:300]
    # control chars strip (header/scheme inject lock)
    value = "".join(c for c in value if c.isprintable())
    if not label:
        return None
    bid = _ID_RE.sub("", str(b.get("id") or "").strip().lower())[:24] or f"b{idx + 1}"
    emoji = str(b.get("emoji") or "").strip()[:4] or _TYPE_EMOJI.get(btype, "🔗")
    return {"id": bid, "type": btype, "label": label, "value": value, "emoji": emoji}


def save_bio(
    slug: str, blocks: list[dict] | None, title: str = "", subtitle: str = ""
) -> dict[str, Any]:
    """Bio page blocks save (append-only, latest-wins). Duplicate ids dedupe."""
    try:
        key = _slug_key(slug)
        if not key:
            return {"ok": False, "error": "slug required"}
        clean: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for i, b in enumerate(blocks or []):
            c = _clean_block(b, i)
            if not c:
                continue
            base, n = c["id"], 2
            while c["id"] in seen_ids:  # bounded — n <= _MAX_BLOCKS
                c["id"] = f"{base[:20]}-{n}"
                n += 1
            seen_ids.add(c["id"])
            clean.append(c)
            if len(clean) >= _MAX_BLOCKS:
                break
        if not clean:
            return {"ok": False, "error": "koi valid block nahi mila"}
        rec = {
            "slug": key,
            "title": str(title or "").strip()[:80],
            "subtitle": str(subtitle or "").strip()[:120],
            "blocks": clean,
            "updated_at": _now(),
        }
        os.makedirs(os.path.dirname(_BIO_FILE) or ".", exist_ok=True)
        with open(_BIO_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return {"ok": True, "slug": key, "config": rec}
    except Exception as e:
        logger.warning(f"[bio_link] save failed: {e}")
        return {"ok": False, "error": str(e)[:160]}


def get_bio(slug: str) -> dict[str, Any] | None:
    """Latest saved config | None. Never raises."""
    try:
        key = _slug_key(slug)
        if not key or not os.path.isfile(_BIO_FILE):
            return None
        found: dict[str, Any] | None = None
        with open(_BIO_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if isinstance(rec, dict) and rec.get("slug") == key:
                    found = rec
        return found
    except Exception as e:
        logger.warning(f"[bio_link] read failed: {e}")
        return None


# --------------------------------------------------------------------------- #
# Target URL build + click tracking
# --------------------------------------------------------------------------- #
def _indian_digits(value: str) -> str:
    """10-digit Indian mobile normalize → '91XXXXXXXXXX' | ''."""
    d = re.sub(r"\D", "", value or "")
    if len(d) == 11 and d.startswith("0"):
        d = d[1:]  # common "0XXXXXXXXXX" format
    if len(d) == 10 and d[0] in "6789":
        return "91" + d
    if len(d) == 12 and d.startswith("91") and d[2] in "6789":
        return d
    return ""


def _block_target(block: dict[str, Any], slug: str, client: dict[str, Any]) -> str | None:
    """Final URL banao — sirf safe schemes (http/https/own-relative/tel/upi/wa.me)."""
    btype = block.get("type") or "link"
    value = str(block.get("value") or "").strip()
    if btype == "whatsapp":
        d = _indian_digits(value or str(client.get("phone") or ""))
        return f"https://wa.me/{d}" if d else None
    if btype == "call":
        d = _indian_digits(value or str(client.get("phone") or ""))
        return f"tel:+{d}" if d else None
    if btype == "upi":
        vpa = value or str(client.get("upi_vpa") or "")
        if "@" in vpa and 5 <= len(vpa) <= 80 and re.fullmatch(r"[A-Za-z0-9._@-]+", vpa):
            name = str(client.get("business_name") or "Business")[:40]
            return f"upi://pay?pa={quote(vpa)}&pn={quote(name)}&cu=INR"
        return None
    if btype == "catalog" and not value:
        return f"/b/{slug}"  # mini-site catalog default
    # link | video | offer | catalog-with-url — http(s) ya own-relative hi
    if value.startswith(("http://", "https://")) or (
        value.startswith("/") and not value.startswith("//")
    ):
        return value
    return None


def resolve_block(slug: str, block_id: str, ua: str = "", ref: str = "") -> str | None:
    """Block ka target URL + click log. Unknown slug/block = None (router 302 home)."""
    try:
        key = _slug_key(slug)
        bid = _ID_RE.sub("", (block_id or "").strip().lower())[:24]
        cfg = get_bio(key)
        if not cfg or not bid:
            return None
        block = next((b for b in (cfg.get("blocks") or []) if b.get("id") == bid), None)
        if not block:
            return None
        client = _load_client(key)
        url = _block_target(block, key, client)
        if not url:
            return None
        try:
            os.makedirs(os.path.dirname(_CLICKS_FILE) or ".", exist_ok=True)
            with open(_CLICKS_FILE, "a", encoding="utf-8") as f:
                f.write(
                    json.dumps(
                        {
                            "ts": _now(),
                            "slug": key,
                            "block_id": bid,
                            "type": block.get("type"),
                            "label": block.get("label"),
                            "ua": (ua or "")[:160],
                            "ref": (ref or "")[:200],
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        except Exception:
            pass  # click log best-effort — redirect kabhi na ruke
        return url
    except Exception as e:
        logger.warning(f"[bio_link] resolve failed: {e}")
        return None


def bio_stats(slug: str) -> dict[str, Any]:
    """Clicks per block + totals. Never raises."""
    key = _slug_key(slug)
    by_block: dict[str, dict[str, Any]] = {}
    total = 0
    last7 = 0
    cutoff = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - 7 * 86400))
    try:
        if key and os.path.isfile(_CLICKS_FILE):
            with open(_CLICKS_FILE, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except Exception:
                        continue
                    if not isinstance(rec, dict) or rec.get("slug") != key:
                        continue
                    total += 1
                    if str(rec.get("ts") or "") >= cutoff:
                        last7 += 1
                    bid = str(rec.get("block_id") or "?")
                    ent = by_block.setdefault(bid, {"label": rec.get("label") or bid, "clicks": 0})
                    ent["clicks"] += 1
    except Exception as e:
        logger.warning(f"[bio_link] stats failed: {e}")
    return {"slug": key, "clicks_total": total, "clicks_7d": last7, "by_block": by_block}


# --------------------------------------------------------------------------- #
# Page render (standalone, mobile-first) — serve at /b/{slug}/bio
# --------------------------------------------------------------------------- #
_PAGE_TEMPLATE = """<!doctype html><html lang="hi"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__ — Links</title>
<meta name="description" content="__TITLE__ — saare links ek jagah.">
<style>
 *{box-sizing:border-box}
 body{margin:0;font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;
  background:linear-gradient(160deg,__PRIMARY__ 0%,__PRIMARYSOFT__ 40%,#111827 130%);
  min-height:100vh;color:#fff;padding:34px 16px 50px}
 .card{max-width:430px;margin:0 auto;text-align:center}
 .avatar{width:84px;height:84px;border-radius:50%;background:#fff;color:__PRIMARY__;
  font-size:36px;font-weight:800;line-height:84px;margin:0 auto 12px;box-shadow:0 8px 30px rgba(0,0,0,.3)}
 h1{margin:0 0 4px;font-size:22px}
 .sub{opacity:.85;font-size:14px;margin-bottom:22px}
 a.blk{display:flex;align-items:center;gap:12px;background:rgba(255,255,255,.96);color:#111;
  text-decoration:none;border-radius:14px;padding:15px 16px;margin:11px 0;font-weight:700;font-size:15px;
  box-shadow:0 4px 16px rgba(0,0,0,.18);transition:transform .12s}
 a.blk:active{transform:scale(.98)}
 a.blk .em{font-size:20px}
 a.blk .lb{flex:1;text-align:left}
 a.blk .ar{opacity:.4}
 .pw{margin-top:26px;font-size:12px;opacity:.7}
 .pw a{color:#fff}
</style></head><body>
<div class="card">
  <div class="avatar">__INITIAL__</div>
  <h1>__TITLE__</h1>
  <div class="sub">__SUBTITLE__</div>
  __BLOCKS__
  <div class="pw">Powered by <a href="__BASE__" rel="noopener">LeadsGenAI</a></div>
</div>
</body></html>"""


def render_bio_html(slug: str) -> dict[str, Any]:
    """{ok, html} — config na ho to ok=False (caller 302 kare). Never raises."""
    try:
        key = _slug_key(slug)
        cfg = get_bio(key)
        if not cfg:
            # Default bio: client record se auto-blocks (WA/call/mini-site) —
            # pehli visit pe hi kaam kare, config baad me customize. Save karte
            # hain taaki click-redirect ids resolve ho (kabhi 302-blank nahi).
            client = _load_client(key)
            phone = str((client or {}).get("phone") or "").strip()
            if not client:
                return {"ok": False, "error": "bio config nahi mila"}
            default_blocks = []
            if phone:
                default_blocks.append(
                    {"type": "whatsapp", "label": "WhatsApp karein", "value": phone, "emoji": "💬"}
                )
                default_blocks.append(
                    {"type": "call", "label": "Call karein", "value": phone, "emoji": "📞"}
                )
            default_blocks.append(
                {
                    "type": "link",
                    "label": "Hamari website",
                    "value": f"{_site_base()}/b/{key}",
                    "emoji": "🌐",
                }
            )
            saved = save_bio(key, default_blocks)
            if not saved.get("ok"):
                return {"ok": False, "error": "bio config nahi mila"}
            cfg = get_bio(key)
            if not cfg:
                return {"ok": False, "error": "bio config nahi mila"}
        client = _load_client(key)
        primary, _accent = _brand_colors(key, client)
        title = str(
            cfg.get("title") or client.get("business_name") or key.replace("-", " ").title()
        )[:80]
        subtitle = str(cfg.get("subtitle") or client.get("tagline") or "Saare links ek jagah 👇")[
            :120
        ]
        rows: list[str] = []
        for b in cfg.get("blocks") or []:
            bid = html.escape(str(b.get("id") or ""))
            label = html.escape(str(b.get("label") or ""))
            emoji = html.escape(str(b.get("emoji") or "🔗"))
            href = f"/api/widgets/bio/{html.escape(key)}/c/{bid}"
            rows.append(
                f'<a class="blk" href="{href}" rel="noopener">'
                f'<span class="em">{emoji}</span><span class="lb">{label}</span><span class="ar">›</span></a>'
            )
        primary_soft = primary + "cc" if len(primary) == 7 else primary
        page = (
            _PAGE_TEMPLATE.replace("__PRIMARYSOFT__", primary_soft)
            .replace("__PRIMARY__", primary)
            .replace("__TITLE__", html.escape(title))
            .replace("__SUBTITLE__", html.escape(subtitle))
            .replace("__INITIAL__", html.escape((title[:1] or "L").upper()))
            .replace("__BLOCKS__", "\n  ".join(rows))
            .replace("__BASE__", _site_base())
        )
        return {"ok": True, "html": page}
    except Exception as e:
        logger.warning(f"[bio_link] render failed: {e}")
        return {"ok": False, "error": str(e)[:160]}


__all__ = [
    "save_bio",
    "get_bio",
    "resolve_block",
    "bio_stats",
    "render_bio_html",
]
