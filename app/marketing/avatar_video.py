"""
avatar_video.py — AI avatar/voiceover VIDEO post (thin wrapper, NO rebuild).
=============================================================================

HeyGen/Synthesia-jaisa "spokesperson video" ka FREE-stack version:
EXISTING capabilities compose karta hai (kuch naya heavy build NAHI):
  - script        : free_ai.chat (Hinglish 3-4 line voiceover, template fallback)
  - video         : ai_image.video_url() (Pollinations wan-fast/veo — REUSE)
  - caption/tags  : post_generator.generate_post() (REUSE)

POLLINATIONS_API_KEY absent → {"ok": False, "reason": "key_missing"} graceful
(video URL bina key 402 deta — isliye pehle hi bata dete hain).

NOTE: faceless PIL+TTS reels ke liye EXISTING `reel_video.py` hai — yeh module
AI-generated (avatar/spokesperson style) video ke liye hai, replacement nahi.

Public API: avatar_post(topic, niche="general", slug="") — async, never-raise.
"""

from __future__ import annotations

from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_FALLBACK_SCRIPT = (
    "Namaste! {biz} me aapka swagat hai. {topic} — aaj hi humse jaaniye. "
    "Quality kaam, sahi daam. Abhi WhatsApp karein ya call karein — "
    "aapki service ek message door hai!"
)


def _brand_name(slug: str) -> str:
    try:
        from app.marketing import brand_kit

        brand = brand_kit.get_brand(slug) or {}
        return str(brand.get("business_name") or "").strip()
    except Exception:
        return ""


async def _script(topic: str, biz: str, niche: str) -> str:
    """Free-LLM 3-4 line Hinglish voiceover script — fail = template."""
    try:
        from app.voice_agent import free_ai

        system = (
            "Tu ek Indian local business ka video scriptwriter hai. 15-20 second "
            "ke spokesperson video ke liye 3-4 chhoti Hinglish (Roman script) "
            "lines likh — warm, energetic, ek clear CTA (WhatsApp/call). "
            "Sirf script do — koi heading/scene-notes nahi."
        )
        user = f"Business: {biz or 'local business'} ({niche.replace('_', ' ')})\nTopic: {topic}"
        text, _provider = await free_ai.chat(
            system, [{"role": "user", "content": user}], max_tokens=180, temperature=0.7
        )
        text = (text or "").strip().strip('"')
        if 20 < len(text) < 900:
            return text
    except Exception as e:
        logger.debug(f"[avatar_video] llm script skip: {e}")
    return _FALLBACK_SCRIPT.format(biz=biz or "Hamare business", topic=topic or "hamari services")


async def avatar_post(topic: str, niche: str = "general", slug: str = "") -> dict[str, Any]:
    """Ek topic → AI avatar-style video URL + voiceover script + caption +
    hashtags (poora post pack). Never raises.

    POLLINATIONS key absent → {"ok": False, "reason": "key_missing"}.
    """
    try:
        topic = str(topic or "").strip()
        if not topic:
            return {"ok": False, "reason": "empty_topic", "error": "topic do (e.g. 'Diwali offer')"}
        niche = str(niche or "general").strip().lower() or "general"
        slug = str(slug or "").strip()

        # --- key gate (video gen 402 deta bina key) --- #
        key = ""
        try:
            from app.marketing import ai_image

            key = ai_image._api_key()  # noqa: SLF001 — same-package helper (customer_crm pattern)
        except Exception:
            key = ""
        if not key:
            return {
                "ok": False,
                "reason": "key_missing",
                "hint": "POLLINATIONS_API_KEY set karo (enter.pollinations.ai, free) — "
                "phir AI avatar video live ho jayega.",
            }

        biz = _brand_name(slug) if slug else ""

        # --- script (free-LLM, fallback template) --- #
        script = await _script(topic, biz, niche)

        # --- video URL (REUSE ai_image.video_url — key-safety wahi handle karta) --- #
        prompt = (
            f"friendly indian business person talking to camera, {topic}, "
            f"{niche.replace('_', ' ')} business promo, warm lighting, "
            "vertical 9:16, professional, upbeat"
        )
        try:
            video = ai_image.video_url(prompt, model="wan-fast", duration=6)
        except Exception:
            video = ""

        # --- caption + hashtags (REUSE post_generator) --- #
        caption, hashtags, post_text = "", [], ""
        try:
            from app.marketing import post_generator

            post = await post_generator.generate_post(
                business_name=biz or topic, niche=niche, occasion=topic
            )
            caption = post.get("caption") or ""
            hashtags = post.get("hashtags") or []
            post_text = post.get("post_text") or ""
        except Exception as e:
            logger.debug(f"[avatar_video] post_generator skip: {e}")

        return {
            "ok": True,
            "topic": topic,
            "business_name": biz,
            "script": script,
            "video_url": video,
            "caption": caption,
            "hashtags": hashtags,
            "post_text": post_text,
            "note": "Video URL open karke download karo — reel/status pe 1-click "
            "human post (auto-publish nahi).",
        }
    except Exception as e:  # absolute guard
        logger.warning(f"[avatar_video] avatar_post failed: {e}")
        return {"ok": False, "reason": "error", "error": str(e)[:200]}


__all__ = ["avatar_post"]
