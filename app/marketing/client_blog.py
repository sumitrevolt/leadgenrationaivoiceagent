"""Per-client blog (programmatic SEO) — har customer ka apna blog at /b/{slug}/blog.

Audit gap #29: customer ko sirf template milta tha, koi live per-client blog page nahi.
Yeh module woh deta: free_ai se niche-aware Hinglish blog post generate + per-client jsonl
store + render helpers. Mini-site (/b/{slug}) ke saath consistent. KABHI raise nahi.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_DIR = Path(os.environ.get("DATA_DIR", "data")) / "client_blogs"


def _slugify(s: str) -> str:
    out = re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")
    return out[:60] or "post"


def _path(client_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_-]", "", str(client_id))[:64] or "x"
    return _DIR / f"{safe}.jsonl"


def client_slug(client_id: str) -> str:
    try:
        from app.marketing import clients_store

        c = clients_store.get_client(client_id) or {}
        return str(c.get("slug") or "")
    except Exception:
        return ""


def list_posts(client_id: str, limit: int = 50) -> list[dict[str, Any]]:
    p = _path(client_id)
    out: list[dict[str, Any]] = []
    if not p.exists():
        return out
    try:
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    except Exception as e:
        logger.debug("client_blog list err: %s", e)
    out.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
    return out[:limit]


def get_post(client_id: str, post_slug: str) -> dict[str, Any] | None:
    for p in list_posts(client_id, limit=500):
        if p.get("slug") == post_slug:
            return p
    return None


def _store(client_id: str, post: dict[str, Any]) -> None:
    try:
        _DIR.mkdir(parents=True, exist_ok=True)
        with _path(client_id).open("a", encoding="utf-8") as f:
            f.write(json.dumps(post, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning("client_blog store err: %s", e)


async def generate_and_store(
    client_id: str, business_name: str, niche: str, topic: str = "", keyword: str = ""
) -> dict[str, Any]:
    """Ek SEO blog post generate + store. KABHI empty nahi (template fallback)."""
    biz = (business_name or "Business").strip()
    niche = (niche or "general").strip()
    topic = (topic or "").strip()
    title, body = "", ""
    try:
        from app.voice_agent import free_ai

        sys = (
            f"Tu ek expert Indian local-business content writer hai jo {niche} ke liye "
            "SEO-friendly Hinglish blog likhta hai. Output EXACTLY:\nTITLE: <ek line>\n"
            "BODY: <250-400 words, 3-4 chhote paragraphs + ek bullet list, helpful + local, "
            "koi fake claim nahi>"
        )
        usr = (
            f"Business: {biz}\nNiche: {niche}\n"
            f"Topic: {topic or 'is niche ka ek common customer sawaal/tip'}\n"
            f"Keyword: {keyword or niche}\nEk blog post likho."
        )
        text, _ = await free_ai.chat(
            sys, [{"role": "user", "content": usr}], max_tokens=600, temperature=0.7
        )
        text = (text or "").strip()
        if "TITLE:" in text:
            after = text.split("TITLE:", 1)[1]
            title = after.split("BODY:", 1)[0].strip()[:140]
            body = after.split("BODY:", 1)[1].strip() if "BODY:" in after else ""
        if not body:
            body = text
    except Exception as e:
        logger.debug("client_blog gen err: %s", e)

    if not title:
        title = (topic or f"{biz}: {niche} ke liye useful tips")[:140]
    if not body:
        body = (
            f"{biz} aapke {niche} ki zaroorat ke liye yahan hai. Quality service, sahi daam, "
            "aur bharosa. Aaj hi humse judiye — call ya WhatsApp karein!"
        )
    post = {
        "slug": _slugify(title) + "-" + datetime.now(timezone.utc).strftime("%m%d%H%M"),
        "title": title,
        "body": body,
        "keyword": keyword or niche,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _store(client_id, post)
    return post


import html as _html


def _shell(biz: str, primary: str, inner: str, slug: str) -> str:
    e = _html.escape
    return (
        f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"/>'
        f'<meta name="viewport" content="width=device-width,initial-scale=1"/>'
        f"<title>{e(biz)} — Blog</title><style>"
        "body{font:16px/1.6 system-ui,-apple-system,sans-serif;margin:0;background:#fff;color:#1a1a2e}"
        ".wrap{max-width:720px;margin:0 auto;padding:24px 18px 60px}"
        f"a{{color:{primary};text-decoration:none}} .top{{font-size:13px;color:#888;margin-bottom:8px}}"
        "h1{font-size:24px;margin:6px 0 18px} h2{font-size:18px;margin:0 0 6px}"
        ".card{display:block;border:1px solid #eee;border-radius:12px;padding:14px 16px;margin:0 0 12px;color:inherit}"
        ".card p{color:#555;font-size:14px;margin:0} .empty{color:#888}"
        f".cta{{display:inline-block;background:{primary};color:#fff;padding:10px 18px;border-radius:10px;margin-top:18px}}"
        "article{white-space:pre-wrap}</style></head><body><div class='wrap'>"
        f"<div class='top'><a href='/b/{e(slug)}'>← {e(biz)}</a></div>{inner}"
        f"<a class='cta' href='/b/{e(slug)}'>Humse judiye →</a></div></body></html>"
    )


def render_index(client: dict[str, Any], slug: str) -> str:
    e = _html.escape
    biz = str(client.get("business_name") or "Blog")
    brand = client.get("brand") if isinstance(client.get("brand"), dict) else {}
    primary = str((brand or {}).get("primary") or "#6d28d9")
    posts = list_posts(str(client.get("id") or ""))
    if posts:
        items = "".join(
            f"<a class='card' href='/b/{e(slug)}/blog/{e(str(p.get('slug', '')))}'>"
            f"<h2>{e(str(p.get('title', '')))}</h2>"
            f"<p>{e(str(p.get('body', ''))[:150])}…</p></a>"
            for p in posts
        )
    else:
        items = "<p class='empty'>Abhi koi blog post nahi — jaldi aayega.</p>"
    return _shell(biz, primary, f"<h1>{e(biz)} — Blog</h1>{items}", slug)


def render_post(client: dict[str, Any], slug: str, post: dict[str, Any]) -> str:
    e = _html.escape
    biz = str(client.get("business_name") or "Blog")
    brand = client.get("brand") if isinstance(client.get("brand"), dict) else {}
    primary = str((brand or {}).get("primary") or "#6d28d9")
    inner = (
        f"<div class='top'><a href='/b/{e(slug)}/blog'>← Blog</a></div>"
        f"<h1>{e(str(post.get('title', '')))}</h1>"
        f"<article>{e(str(post.get('body', '')))}</article>"
    )
    return _shell(biz, primary, inner, slug)


__all__ = [
    "client_slug",
    "list_posts",
    "get_post",
    "generate_and_store",
    "render_index",
    "render_post",
]
