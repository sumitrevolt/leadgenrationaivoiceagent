"""Meta Graph API publisher (Facebook Page + Instagram) — Track 3 social auto-posting.

DEFENSIVE + opt-in. Real publishing sirf tab jab ``SOCIAL_AUTOPOST=1`` AND ek usable
Page/IG access token ho (per-client ``data/meta_connections.jsonl``, ya global platform
token ``settings.meta_page_access_token``). Warna -> MOCK mode: kuch publish nahi hota,
sirf ek mock-result return hota hai (log me dikh jata kya post HOTA). NEVER raises.

Meta app-review unlock hone tak yeh mock chalega; tokens milte hi flag on + connect karo
=> live posting. Per-client connection store taaki har client apna FB/IG jod sake.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_CONN_FILE = os.path.join("data", "meta_connections.jsonl")


def _flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def autopost_enabled() -> bool:
    """Master switch — real publishing only when SOCIAL_AUTOPOST is truthy (env or settings)."""
    if _flag("SOCIAL_AUTOPOST"):
        return True
    try:
        from app.config import settings

        return bool(getattr(settings, "social_autopost", False))
    except Exception:
        return False


def _graph_version() -> str:
    try:
        from app.config import settings

        return (getattr(settings, "meta_graph_version", "") or "v21.0").strip()
    except Exception:
        return "v21.0"


# --------------------------------------------------------------------------- #
# Per-client connection store (tokens live here, NOT in clients_store/socials)
# --------------------------------------------------------------------------- #
def _read_conns() -> list[dict]:
    out: list[dict] = []
    try:
        if os.path.exists(_CONN_FILE):
            with open(_CONN_FILE, encoding="utf-8") as f:
                for ln in f:
                    ln = ln.strip()
                    if ln:
                        try:
                            out.append(json.loads(ln))
                        except Exception:
                            pass
    except Exception:
        pass
    return out


def connect(
    client_id: str,
    page_id: str = "",
    page_access_token: str = "",
    instagram_account_id: str = "",
) -> dict[str, Any]:
    """Store/replace a client's Meta connection. Returns the stored record. Never raises."""
    cid = (client_id or "").strip()
    rec = {
        "client_id": cid,
        "page_id": (page_id or "").strip(),
        "page_access_token": (page_access_token or "").strip(),
        "instagram_account_id": (instagram_account_id or "").strip(),
    }
    try:
        rows = [r for r in _read_conns() if str(r.get("client_id")) != cid]
        rows.append(rec)
        os.makedirs(os.path.dirname(_CONN_FILE) or ".", exist_ok=True)
        with open(_CONN_FILE, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("meta connect store err: %s", e)
    return rec


def get_connection(client_id: str | None) -> dict[str, Any] | None:
    """Per-client Meta creds; else GLOBAL platform creds (settings) as fallback. None if neither."""
    cid = (client_id or "").strip()
    if cid:
        for r in _read_conns():
            if str(r.get("client_id")) == cid and (r.get("page_access_token") or "").strip():
                return r
    # Global fallback — the platform's own page/IG (for self-marketing posts).
    try:
        from app.config import settings

        tok = (getattr(settings, "meta_page_access_token", "") or "").strip()
        if tok:
            return {
                "client_id": cid,
                "page_id": (getattr(settings, "meta_facebook_page_id", "") or "").strip(),
                "page_access_token": tok,
                "instagram_account_id": (
                    getattr(settings, "meta_instagram_account_id", "") or ""
                ).strip(),
                "_global": True,
            }
    except Exception:
        pass
    return None


def has_connection(client_id: str | None) -> bool:
    return get_connection(client_id) is not None


# --------------------------------------------------------------------------- #
# Low-level Graph publish (sync httpx — called off-thread by the async poster)
# --------------------------------------------------------------------------- #
def _post(url: str, data: dict) -> dict[str, Any]:
    try:
        import httpx

        with httpx.Client(timeout=20.0) as c:
            r = c.post(url, data=data)
            try:
                body = r.json()
            except Exception:
                body = {"raw": (r.text or "")[:500]}
            if r.status_code >= 400:
                return {"ok": False, "status": r.status_code, "error": body}
            merged = body if isinstance(body, dict) else {"data": body}
            return {"ok": True, "status": r.status_code, **merged}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def publish_facebook(
    page_id: str, page_access_token: str, message: str, image_url: str = "", version: str = ""
) -> dict[str, Any]:
    """Publish to a Facebook Page (photo if image_url else feed text). Never raises."""
    v = version or _graph_version()
    pid = (page_id or "").strip()
    tok = (page_access_token or "").strip()
    if not (pid and tok):
        return {"ok": False, "error": "missing_page_credentials"}
    if (image_url or "").strip():
        return _post(
            f"https://graph.facebook.com/{v}/{pid}/photos",
            {"caption": message, "url": image_url, "access_token": tok},
        )
    return _post(
        f"https://graph.facebook.com/{v}/{pid}/feed",
        {"message": message, "access_token": tok},
    )


def publish_instagram(
    ig_account_id: str, page_access_token: str, caption: str, image_url: str, version: str = ""
) -> dict[str, Any]:
    """Publish to Instagram (2-step container + publish). Requires a public image_url. Never raises."""
    v = version or _graph_version()
    ig = (ig_account_id or "").strip()
    tok = (page_access_token or "").strip()
    img = (image_url or "").strip()
    if not (ig and tok):
        return {"ok": False, "error": "missing_ig_credentials"}
    if not img:
        return {"ok": False, "error": "instagram_requires_image_url"}
    container = _post(
        f"https://graph.facebook.com/{v}/{ig}/media",
        {"image_url": img, "caption": caption, "access_token": tok},
    )
    if not container.get("ok") or not container.get("id"):
        return {"ok": False, "error": "container_failed", "detail": container}
    return _post(
        f"https://graph.facebook.com/{v}/{ig}/media_publish",
        {"creation_id": container.get("id"), "access_token": tok},
    )


# --------------------------------------------------------------------------- #
# High-level: publish one content_schedule 'ready' item
# --------------------------------------------------------------------------- #
def _caption_from_item(item: dict) -> str:
    content = (item or {}).get("content") or {}
    cap = str(content.get("caption") or "").strip()
    tags = content.get("hashtags") or []
    if isinstance(tags, (list, tuple)) and tags:
        cap = (cap + "\n\n" + " ".join(str(t) for t in tags)).strip()
    if not cap:
        cap = str((item or {}).get("occasion") or (item or {}).get("business_name") or "").strip()
    return cap


def publish_post(item: dict, image_url: str = "") -> dict[str, Any]:
    """Publish a content_schedule 'ready' item to the client's connected Meta account.

    MOCK (no real publish) when SOCIAL_AUTOPOST off OR no connection ->
    ``{"status": "mock", "would_post": {...}}``. Real publish ->
    ``{"status": "posted"|"failed", "results": {...}}``. NEVER raises.
    """
    try:
        item = item or {}
        client_id = str(item.get("client_id") or "")
        channel = str(item.get("channel") or "instagram").strip().lower()
        caption = _caption_from_item(item)
        conn = get_connection(client_id)

        if not autopost_enabled() or conn is None:
            return {
                "status": "mock",
                "reason": "autopost_off" if not autopost_enabled() else "no_meta_connection",
                "channel": channel,
                "would_post": {
                    "client_id": client_id,
                    "caption": caption,
                    "image_url": image_url,
                },
            }

        tok = conn.get("page_access_token", "")
        results: dict[str, Any] = {}
        # Facebook page (text or photo) — default for most niches / when no IG linked.
        if channel in ("facebook", "fb", "both", "all") or not conn.get("instagram_account_id"):
            results["facebook"] = publish_facebook(conn.get("page_id", ""), tok, caption, image_url)
        # Instagram (needs a public image_url).
        if channel in ("instagram", "ig", "both", "all") and conn.get("instagram_account_id"):
            results["instagram"] = publish_instagram(
                conn.get("instagram_account_id", ""), tok, caption, image_url
            )

        ok = any(isinstance(r, dict) and r.get("ok") for r in results.values())
        return {"status": "posted" if ok else "failed", "channel": channel, "results": results}
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("publish_post err: %s", e)
        return {"status": "error", "error": str(e)}


__all__ = [
    "autopost_enabled",
    "connect",
    "get_connection",
    "has_connection",
    "publish_facebook",
    "publish_instagram",
    "publish_post",
]
