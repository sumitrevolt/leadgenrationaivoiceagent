"""AI image/video generation — Pollinations NEW API (gen.pollinations.ai).

API migrate (2026-06): old image.pollinations.ai → `https://gen.pollinations.ai/image/{prompt}`.
Key enter.pollinations.ai se (env `POLLINATIONS_API_KEY`; legacy `POLLINATIONS_TOKEN` fallback).

KEY SAFETY (important):
- `pk_` (publishable) = client-safe by design → direct URL me `?key=` embed OK.
- `sk_` (secret) = KABHI client URL me nahi → marketing_image() proxy URL deta hai
  (`/api/marketing/ai-image-proxy`), server Authorization header se fetch + disk-cache
  (data/ai_images/) karta — repeat loads pollen nahi jalate.
- Koi key nahi → direct URL (upstream 402 dega; frontend __imgErr graceful msg pehle se).

Use:
  from app.marketing.ai_image import image_url, marketing_image, video_url
  data = await marketing_image("Sharma Jewellers", "jewellery_store", occasion="Diwali")
Never raises.
"""

from __future__ import annotations

import hashlib
import logging
import os
import urllib.parse

logger = logging.getLogger(__name__)

_BASE = "https://gen.pollinations.ai/image/"
_VIDEO_BASE = "https://gen.pollinations.ai/video/"
_CACHE_DIR = os.path.join("data", "ai_images")


def _api_key() -> str:
    return (os.getenv("POLLINATIONS_API_KEY") or os.getenv("POLLINATIONS_TOKEN") or "").strip()


def has_key() -> bool:
    return bool(_api_key())


def _is_secret() -> bool:
    return _api_key().startswith("sk_")


def image_url(
    prompt: str, width: int = 1024, height: int = 1024, seed: int | None = None, model: str = "flux"
) -> str:
    """Direct Pollinations image URL. sk_ key NEVER embedded (sirf pk_). Never raises."""
    try:
        p = urllib.parse.quote((prompt or "marketing poster").strip()[:480], safe="")
        q = f"width={int(width)}&height={int(height)}&nologo=true&model={model}"
        if seed is not None:
            q += f"&seed={int(seed)}"
        key = _api_key()
        if key.startswith("pk_"):  # publishable = client-safe
            q += "&key=" + urllib.parse.quote(key, safe="")
        return f"{_BASE}{p}?{q}"
    except Exception:
        return f"{_BASE}marketing%20poster?width=1024&height=1024&nologo=true&model=flux"


def video_url(prompt: str, model: str = "wan-fast", duration: int = 4) -> str:
    """Direct AI-video (MP4) URL — naya capability. Same key-safety rule. Never raises."""
    try:
        p = urllib.parse.quote((prompt or "product showcase").strip()[:400], safe="")
        q = f"model={model}&duration={max(2, min(int(duration), 10))}"
        key = _api_key()
        if key.startswith("pk_"):
            q += "&key=" + urllib.parse.quote(key, safe="")
        return f"{_VIDEO_BASE}{p}?{q}"
    except Exception:
        return f"{_VIDEO_BASE}product%20showcase?model=wan-fast&duration=4"


def proxy_path(prompt: str, width: int = 1024, height: int = 1024, seed: int | None = None) -> str:
    """Hamare server ka proxy URL (sk_ key server-side header me lagti hai)."""
    q = urllib.parse.urlencode(
        {
            "prompt": (prompt or "")[:480],
            "w": int(width),
            "h": int(height),
            **({"seed": int(seed)} if seed is not None else {}),
        }
    )
    return f"/api/marketing/ai-image-proxy?{q}"


def _cache_file(prompt: str, width: int, height: int, seed: int | None) -> str:
    h = hashlib.sha1(f"{prompt}|{width}|{height}|{seed}".encode()).hexdigest()[:24]
    return os.path.join(_CACHE_DIR, f"{h}.jpg")


async def fetch_image_bytes(
    prompt: str, width: int = 1024, height: int = 1024, seed: int | None = None, model: str = "flux"
) -> bytes | None:
    """Server-side fetch (Authorization header) + disk cache. None = fail (caller handle kare)."""
    path = _cache_file(prompt, width, height, seed)
    try:
        if os.path.exists(path) and os.path.getsize(path) > 500:
            with open(path, "rb") as f:
                return f.read()
    except Exception:
        pass
    key = _api_key()
    if not key:
        return None
    # Circuit breaker (gated CIRCUIT_BREAKER=1, default OFF = pass-through): Pollinations
    # down ho to har call 45s timeout wait na kare — OPEN pe turant None (caller SVG
    # fallback leta). docs/GAP_ANALYSIS_SaaS_Infra_Upgrade_2026.md §3.3. Never-raise.
    from app.infrastructure.circuit_breaker import get_breaker

    _br = get_breaker("pollinations_image", fail_threshold=4, reset_after_s=60.0)
    if not _br.allow():
        logger.info("pollinations breaker OPEN — fast fallback (skipping fetch)")
        return None
    try:
        import httpx

        p = urllib.parse.quote((prompt or "marketing poster").strip()[:480], safe="")
        url = f"{_BASE}{p}?width={int(width)}&height={int(height)}&nologo=true&model={model}"
        if seed is not None:
            url += f"&seed={int(seed)}"
        async with httpx.AsyncClient(timeout=45) as cx:
            r = await cx.get(url, headers={"Authorization": f"Bearer {key}"}, follow_redirects=True)
        if r.status_code == 200 and len(r.content) > 500:
            _br.record_success()
            try:
                from app.platform.integration_health import record_success

                record_success("pollinations")
            except Exception:
                pass
            try:
                os.makedirs(_CACHE_DIR, exist_ok=True)
                with open(path, "wb") as f:
                    f.write(r.content)
            except Exception:
                pass
            return r.content
        _br.record_failure()
        _record_ih_failure(f"http_{r.status_code}")
        logger.warning(f"pollinations image {r.status_code}: {r.text[:120]}")
    except Exception as e:
        _br.record_failure()
        _record_ih_failure(str(e)[:80])
        logger.warning(f"pollinations fetch failed: {e}")
    return None


def _record_ih_failure(note: str) -> None:
    """Mirror breaker failures onto the integrations dashboard — "pollinations"
    was in integration_health.KNOWN but never instrumented (audit 2026-07-04).
    Never raises."""
    try:
        from app.platform.integration_health import record_failure

        record_failure("pollinations", note)
    except Exception:
        pass


async def upload_media(data: bytes, filename: str = "photo.jpg") -> str | None:
    """media.pollinations.ai pe upload → public content-addressed URL (key required)."""
    key = _api_key()
    if not key or not data:
        return None
    try:
        import httpx

        async with httpx.AsyncClient(timeout=60) as cx:
            r = await cx.post(
                "https://media.pollinations.ai/upload",
                headers={"Authorization": f"Bearer {key}"},
                files={"file": (filename, data)},
            )
        if r.status_code == 200:
            j = r.json()
            return j.get("url") or (
                f"https://media.pollinations.ai/{j['hash']}" if j.get("hash") else None
            )
        logger.warning(f"media upload {r.status_code}: {r.text[:120]}")
    except Exception as e:
        logger.warning(f"media upload failed: {e}")
    return None


async def edit_image_bytes(
    prompt: str, photo: bytes, model: str = "kontext", width: int = 1024, height: int = 1024
) -> tuple[bytes | None, str]:
    """Photo→poster (image-to-image): user photo upload → AI edit. Returns (bytes|None, cache_name)."""
    img_url = await upload_media(photo)
    if not img_url:
        return None, ""
    key = _api_key()
    cache_key = f"edit|{prompt}|{hashlib.sha1(photo).hexdigest()[:16]}|{model}"
    path = _cache_file(cache_key, width, height, None)
    try:
        if os.path.exists(path) and os.path.getsize(path) > 500:
            with open(path, "rb") as f:
                return f.read(), os.path.basename(path)
        import httpx

        p = urllib.parse.quote(
            (prompt or "make this a professional marketing poster").strip()[:400], safe=""
        )
        url = f"{_BASE}{p}?model={model}&width={int(width)}&height={int(height)}&nologo=true&image={urllib.parse.quote(img_url, safe='')}"
        async with httpx.AsyncClient(timeout=60) as cx:
            r = await cx.get(url, headers={"Authorization": f"Bearer {key}"}, follow_redirects=True)
        if r.status_code == 200 and len(r.content) > 500:
            try:
                os.makedirs(_CACHE_DIR, exist_ok=True)
                with open(path, "wb") as f:
                    f.write(r.content)
            except Exception:
                pass
            return r.content, os.path.basename(path)
        logger.warning(f"edit image {r.status_code}: {r.text[:120]}")
    except Exception as e:
        logger.warning(f"edit image failed: {e}")
    return None, ""


def cache_file_path(name: str) -> str | None:
    """Safe cache filename → full path (serve route ke liye). Traversal-proof."""
    import re

    if not re.fullmatch(r"[a-f0-9]{24}\.jpg", name or ""):
        return None
    p = os.path.join(_CACHE_DIR, name)
    return p if os.path.exists(p) else None


def _template_prompt(business: str, niche: str, occasion: str, offer: str, style: str) -> str:
    bits = [f"{style} social-media marketing poster"]
    if occasion:
        bits.append(f"for {occasion}")
    bits.append(f"for a {niche.replace('_', ' ')} business '{business}' in India")
    if offer:
        bits.append(f"highlighting the offer: {offer}")
    bits.append(
        "vibrant colors, professional, high quality, clean space for text, Indian festive aesthetic"
    )
    return ", ".join(bits)


async def _craft_prompt(business: str, niche: str, occasion: str, offer: str, style: str) -> str:
    try:
        from app.voice_agent import free_ai

        reply, _ = await free_ai.chat(
            system="Tu ek pro graphic designer hai. Diye gaye business ke liye ek vivid ENGLISH "
            "image-generation prompt likh (max 40 words) jo ek attractive marketing poster banaye. "
            "Sirf prompt de, aur kuch nahi (no quotes).",
            messages=[
                {
                    "role": "user",
                    "content": f"Business: {business}\nNiche: {niche}\nOccasion: {occasion or 'general'}\nOffer: {offer or 'none'}\nStyle: {style}",
                }
            ],
            max_tokens=70,
            temperature=0.7,
        )
        r = (reply or "").strip().strip('"')
        if len(r) > 15:
            return r
    except Exception:
        pass
    return _template_prompt(business, niche, occasion, offer, style)


async def marketing_image(
    business_name: str,
    niche: str = "general",
    occasion: str = "",
    offer: str = "",
    style: str = "vibrant professional",
    width: int = 1024,
    height: int = 1024,
) -> dict:
    """Craft prompt + ready image URL. sk_ key → proxy URL (key-safe). Never raises."""
    business_name = (business_name or "Aapka Business").strip()
    niche = (niche or "general").strip()
    prompt = await _craft_prompt(
        business_name, niche, (occasion or "").strip(), (offer or "").strip(), style
    )
    url = proxy_path(prompt, width, height) if _is_secret() else image_url(prompt, width, height)
    return {
        "url": url,
        "prompt": prompt,
        "provider": "pollinations-flux",
        "width": width,
        "height": height,
    }


def logo_url(business_name: str, niche: str = "general", style: str = "modern minimalist") -> str:
    """AI logo URL. sk_ key → proxy path. Never raises."""
    prompt = (
        f"{style} vector logo for '{(business_name or 'Business').strip()}', a "
        f"{(niche or 'general').replace('_', ' ')} business, clean flat iconic memorable brand mark, "
        "white background, professional, centered, no text"
    )
    if _is_secret():
        return proxy_path(prompt, 512, 512)
    return image_url(prompt, width=512, height=512)


__all__ = [
    "image_url",
    "video_url",
    "marketing_image",
    "logo_url",
    "fetch_image_bytes",
    "proxy_path",
    "has_key",
]
