"""content_distribute.py — auto-publish READY content to LEGAL channels only.

Problem: content auto-CREATED hota hai (auto_content.run_daily_content +
seo_blog.run_daily_blog) par 'ready'/draft state me hi pada rehta hai. Meta/
FB/IG/GBP = external-approval-blocked (un par auto-post NAHI). Sirf DO legal
auto-channel hain:

  1) Telegram — Bot API free + ToS-allowed (telegram_publish.py REUSE).
  2) IndexNow/sitemap — SEO blog URLs Bing/Yandex pe ping (indexnow.py REUSE).

Yeh module wahi do RAW integrations ko ek "publish-ready self content" loop me
glue karta hai (re-implement NAHI karta):

  - publish_ready_to_telegram()  -> GATED `CONTENT_AUTOPUBLISH` (default OFF).
      LeadGen AI ke apne (self) brand ka recent 'ready' (approved) content
      configured Telegram channel (`TELEGRAM_ADMIN_CHAT_ID`) pe post karta hai,
      items ko status="posted" mark karta. Token/flag/chat unset = inert.
  - submit_indexnow(urls)        -> naye blog URLs IndexNow pe ping
      (indexnow.submit_urls REUSE; INDEXNOW_KEY unset bhi chalta — key
      auto-gen, par network/host gate ke peeche). Pure wrapper, never raises.

DEFENSIVE: koi function KABHI raise nahi karta — failure = graceful skip.
Meta/GBP yahan DELIBERATELY nahi hain (draft hi rehte).
"""

from __future__ import annotations

import os
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# LeadGen AI ka apna marketing-client id (auto_content._SELF_CLIENT_ID ke saath
# match — self brand content isi queue me). Hardcode safe fallback rakha hai
# taaki auto_content import fail ho to bhi loop chale.
_SELF_CLIENT_ID_DEFAULT = "leadgenai-self"

# Telegram pe sirf in statuses wale items publish-ready maane jaate hain.
# auto_content me approve hone par status="approved" hota hai; "ready" alias
# bhi accept (defensive — alag pipelines ka naam).
_READY_STATUSES = {"approved", "ready"}

# Telegram caption cap (send_post khud bhi cap karta, yahan defensive).
_TG_CAP = 4000

# Ek run me max kitne items post karein (spam/flood guard).
_MAX_PER_RUN = 5


def _flag_on(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() in ("1", "true", "yes")


def autopublish_enabled() -> bool:
    """publish_ready_to_telegram loop ka gate. `CONTENT_AUTOPUBLISH=1` AUR
    Telegram token dono chahiye — warna inert (zero behaviour change)."""
    if not _flag_on("CONTENT_AUTOPUBLISH"):
        return False
    try:
        from app.marketing import telegram_publish

        return bool(telegram_publish.enabled())
    except Exception:
        return False


def _self_client_id() -> str:
    try:
        from app.marketing import auto_content

        return str(getattr(auto_content, "_SELF_CLIENT_ID", _SELF_CLIENT_ID_DEFAULT))
    except Exception:
        return _SELF_CLIENT_ID_DEFAULT


def _self_chat_id() -> str:
    """LeadGen AI ke apne channel ka chat id — pehle env (admin channel),
    warna self client record ka telegram_chat_id. Dono unset = ''."""
    cid = (os.getenv("TELEGRAM_ADMIN_CHAT_ID") or "").strip()
    if cid:
        return cid
    try:
        from app.marketing import clients_store

        client = clients_store.get_client(_self_client_id()) or {}
        return str(client.get("telegram_chat_id") or "").strip()
    except Exception:
        return ""


def _item_text(item: dict[str, Any]) -> str:
    """Queue item se Telegram-ready text banao (caption/title/hashtags)."""
    if not isinstance(item, dict):
        return ""
    parts: list[str] = []
    cap = str(item.get("caption") or item.get("text") or "").strip()
    if cap:
        parts.append(cap)
    elif item.get("title"):
        parts.append(str(item.get("title")).strip())
    tags = item.get("hashtags") or []
    if isinstance(tags, (list, tuple)) and tags:
        tagline = " ".join(str(t).strip() for t in tags if str(t).strip())
        if tagline:
            parts.append(tagline)
    return ("\n\n".join(parts)).strip()[:_TG_CAP]


async def publish_ready_to_telegram(limit: int = _MAX_PER_RUN) -> dict[str, Any]:
    """Self brand ka recent 'ready' (approved) content Telegram channel pe AUTO
    publish karo, posted items mark karo. GATED `CONTENT_AUTOPUBLISH` + token +
    chat id — koi bhi unset = inert. NEVER raises.

    Reuse: telegram_publish.send_post (raw send) + auto_content.list_queue/
    mark_item (state). Image-less text posts (poster svg telegram-photo nahi).
    """
    if not autopublish_enabled():
        return {"ran": False, "reason": "CONTENT_AUTOPUBLISH off ya TELEGRAM_BOT_TOKEN unset"}

    chat_id = _self_chat_id()
    if not chat_id:
        return {"ran": False, "reason": "TELEGRAM_ADMIN_CHAT_ID / self telegram_chat_id unset"}

    try:
        from app.marketing import auto_content, telegram_publish
    except Exception as e:  # pragma: no cover - import-safe deps
        logger.warning(f"[content_distribute] deps import failed: {e}")
        return {"ran": False, "reason": "deps unavailable"}

    try:
        limit = max(1, min(int(limit), _MAX_PER_RUN))
    except Exception:
        limit = _MAX_PER_RUN

    cid = _self_client_id()
    sent = failed = skipped = 0
    try:
        # Recent items (newest-first) jisme caption ho aur 'ready'/approved ho.
        candidates: list[dict[str, Any]] = []
        for st in _READY_STATUSES:
            try:
                candidates.extend(auto_content.list_queue(cid, status=st, limit=60) or [])
            except Exception:
                continue
        # Dedupe by id (do statuses overlap ho sakte) + only caption-bearing.
        seen_ids: set[str] = set()
        ready: list[dict[str, Any]] = []
        for it in candidates:
            iid = str((it or {}).get("id") or "")
            if not iid or iid in seen_ids:
                continue
            seen_ids.add(iid)
            if _item_text(it):
                ready.append(it)

        for item in ready:
            if sent >= limit:
                break
            text = _item_text(item)
            if not text:
                skipped += 1
                continue
            try:
                res = await telegram_publish.send_post(chat_id, text)
                if res.get("sent"):
                    sent += 1
                    try:
                        auto_content.mark_item(cid, str(item.get("id")), "posted")
                    except Exception:
                        pass
                else:
                    failed += 1
            except Exception as e:
                failed += 1
                logger.warning(f"[content_distribute] telegram item failed: {e}")

        if sent:
            try:
                from app.platform import team

                team.log_event(
                    "isha",
                    "content_distribute",
                    f"📣 Self content Telegram pe publish: {sent} items",
                )
            except Exception:
                pass
        return {"ran": True, "sent": sent, "failed": failed, "skipped": skipped}
    except Exception as e:
        logger.warning(f"[content_distribute] publish_ready_to_telegram failed: {e}")
        return {"ran": False, "reason": str(e)[:160]}


async def submit_indexnow(urls: list[str]) -> dict[str, Any]:
    """Naye blog/landing URLs ko IndexNow (Bing/Yandex) pe ping karo — SEO ke
    liye instant index. Reuse indexnow.submit_urls (same-host gate, dedupe key
    auto-gen). Network/host fail = {"ok": False}. NEVER raises.

    Note: yeh DIRECT submit hai (any-time, koi flag nahi — pure SEO ping, free,
    legal). Scheduled NAYA-only sweep ke liye indexnow.submit_sitemap_if_enabled
    (gated INDEXNOW) blog job me already wired hai.
    """
    if not urls:
        return {"ok": False, "error": "no urls"}
    try:
        from app.marketing import indexnow

        return await indexnow.submit_urls(list(urls))
    except Exception as e:
        logger.warning(f"[content_distribute] submit_indexnow failed: {e}")
        return {"ok": False, "error": str(e)[:160]}


async def submit_new_blog_urls(limit: int = 50) -> dict[str, Any]:
    """Convenience: recent published blog slugs ko /blog/{slug} URLs me badal ke
    IndexNow pe submit karo. Reuse seo_blog.list_articles. NEVER raises."""
    try:
        from app.marketing import seo_blog

        rows = seo_blog.list_articles(limit=limit) or []
        urls = [f"/blog/{r.get('slug')}" for r in rows if r.get("slug")]
        if not urls:
            return {"ok": False, "error": "no blog urls"}
        return await submit_indexnow(urls)
    except Exception as e:
        logger.warning(f"[content_distribute] submit_new_blog_urls failed: {e}")
        return {"ok": False, "error": str(e)[:160]}


__all__ = [
    "autopublish_enabled",
    "publish_ready_to_telegram",
    "submit_indexnow",
    "submit_new_blog_urls",
]
