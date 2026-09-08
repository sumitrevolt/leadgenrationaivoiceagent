"""repurpose.py — "1 input → 7 formats" content pipeline (Repurpose.io-style, free-stack).

Ek topic (ya URL) do → 7 ready formats ek saath (asyncio.gather COMPOSE over
EXISTING generators — kuch bhi rebuild NAHI):

  1. post              → post_generator.generate_post (caption+hashtags+image idea)
  2. carousel          → carousel.generate_carousel (3 SVG slides)
  3. reel              → reels.reels_scripts (1 ready-to-shoot script)
  4. gbp_post          → gbp_text.gbp_texts ka pehla Google-post update
  5. whatsapp_status   → free_ai 1-liner (template fallback)
  6. email_paragraph   → free_ai short para (template fallback)
  7. hashtags          → hashtags.research (trending + best times)

URL input → httpx fetch (10s, polite UA) + lead_scraper.web_extract.clean_text.
PARTIAL-FAIL OK: har format apna try/except — jo bana wo milta hai, baaki me
{"error": ...}. Module NEVER raises, sab imports lazy (import-safe).
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_URL_RE = re.compile(r"^https?://", re.I)
_UA = "Mozilla/5.0 (compatible; LeadsGenAI-content/1.0; +https://leadsgenai.in)"


def _is_url(s: str) -> bool:
    return bool(_URL_RE.match((s or "").strip()))


async def _fetch_url_text(url: str) -> str:
    """URL → clean body text (httpx 10s + web_extract reuse). Fail = ""."""
    try:
        import httpx

        async with httpx.AsyncClient(
            timeout=10, follow_redirects=True, headers={"User-Agent": _UA}
        ) as c:
            r = await c.get(url)
            if r.status_code != 200 or not r.text:
                return ""
        try:
            from app.lead_scraper import web_extract

            return (web_extract.clean_text(r.text) or "")[:3000]
        except Exception:
            # web_extract na mile to crude tag-strip
            return re.sub(r"<[^>]+>", " ", r.text)[:3000]
    except Exception as e:
        logger.debug(f"[repurpose] url fetch skip: {e}")
        return ""


async def _wa_and_email(business: str, niche: str, topic: str) -> tuple[str, str]:
    """Ek hi free_ai call me WhatsApp-status line + email paragraph (fallback templates)."""
    wa = f"✨ {topic[:60] or 'Naya update'} — {business} se jaano! Reply karo 'INFO' 📲"
    email = (
        f"Namaste! {business} ki taraf se ek kaam ki baat — {topic[:120] or 'hamari nayi update'}. "
        "Aapke business/ghar ke liye yeh kaise useful hai, 2 minute me samjhate hain. "
        "Reply karein ya call karein — pehli baat bilkul free."
    )
    try:
        from app.voice_agent import free_ai

        text, _p = await free_ai.chat(
            (
                "Tu Indian local-business ka Hinglish copywriter hai. Output EXACT format:\n"
                "WA: <1 line WhatsApp status, 1 emoji>\n"
                "EMAIL: <3-4 line email paragraph, soft CTA>"
            ),
            [
                {
                    "role": "user",
                    "content": f"Business: {business} | Niche: {niche} | Topic: {topic[:300]}",
                }
            ],
            max_tokens=220,
            temperature=0.7,
        )
        m = re.search(r"WA\s*:\s*(.+)", text or "")
        if m and m.group(1).strip():
            wa = m.group(1).strip()[:300]
        m = re.search(r"EMAIL\s*:\s*(.+)", text or "", re.S)
        if m and m.group(1).strip():
            email = m.group(1).strip()[:800]
    except Exception as e:
        logger.debug(f"[repurpose] wa/email llm fallback: {e}")
    return wa, email


async def _safe(coro) -> Any:
    """Ek format ka guard — exception ko {'error': ...} bana do (partial-fail OK)."""
    try:
        return await coro
    except Exception as e:
        logger.debug(f"[repurpose] format failed: {e}")
        return {"error": str(e)[:160]}


async def repurpose(
    topic_or_url: str,
    niche: str = "general",
    slug: str | None = None,
    business_name: str = "",
) -> dict[str, Any]:
    """1 input → 7 formats. COMPOSE-only (existing generators), kabhi raise nahi."""
    raw = (topic_or_url or "").strip()
    niche = (niche or "general").strip().lower() or "general"

    # slug se client resolve (business name + niche default) — best-effort
    business = (business_name or "").strip()
    if slug and not business:
        try:
            from app.marketing import clients_store

            c = clients_store.get_by_slug(slug)
            if c:
                business = str(c.get("business_name") or "")
                niche = str(c.get("niche") or niche) or niche
        except Exception:
            pass
    business = business or "Aapka Business"

    source: dict[str, Any] = {"type": "topic", "input": raw[:200]}
    topic = raw
    if _is_url(raw):
        text = await _fetch_url_text(raw)
        source = {"type": "url", "url": raw[:300], "extracted_chars": len(text)}
        topic = text[:300] or raw  # fetch fail → URL hi topic, partial OK
    topic = (topic or "naye customers kaise laaye").strip()

    async def _post():
        from app.marketing import post_generator

        return await post_generator.generate_post(business, niche, occasion=topic[:100])

    async def _carousel():
        from app.marketing import carousel

        return await carousel.generate_carousel(business, niche, topic=topic[:120], slides=3)

    async def _reel():
        from app.marketing import reels

        return await reels.reels_scripts(business, niche, topic=topic[:120], n=1)

    async def _gbp():
        from app.marketing import gbp_text

        g = await gbp_text.gbp_texts(business, niche)
        posts = g.get("posts") or []
        return {"text": posts[0] if posts else "", "tip": g.get("tip", "")}

    async def _tags():
        from app.marketing import hashtags

        return await hashtags.research(niche)

    results = await asyncio.gather(
        _safe(_post()),
        _safe(_carousel()),
        _safe(_reel()),
        _safe(_gbp()),
        _safe(_wa_and_email(business, niche, topic)),
        _safe(_tags()),
    )
    post, caro, reel, gbp, wa_email, tags = results
    if isinstance(wa_email, tuple):
        wa, email = wa_email
    else:  # _wa_and_email khud fallback deta — yeh sirf _safe error-dict case
        wa, email = "", ""

    formats: dict[str, Any] = {
        "post": post,
        "carousel": caro,
        "reel": reel,
        "gbp_post": gbp,
        "whatsapp_status": wa or {"error": "wa_status failed"},
        "email_paragraph": email or {"error": "email failed"},
        "hashtags": tags,
    }
    ok_count = sum(1 for v in formats.values() if not (isinstance(v, dict) and v.get("error")))
    try:
        from app.platform.team import log_event

        log_event("isha", "repurpose_pack", f"{business}: {ok_count}/7 formats ({source['type']})")
    except Exception:
        pass
    return {
        "ok": ok_count > 0,
        "business_name": business,
        "niche": niche,
        "topic": topic[:200],
        "source": source,
        "formats": formats,
        "formats_ok": ok_count,
    }


__all__ = ["repurpose"]
