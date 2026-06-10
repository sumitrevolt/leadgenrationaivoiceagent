"""Multi-language post (AdBanao ka edge neutralize) — ek caption → Hindi (Devanagari),
Marathi, Hinglish versions.

Local business ka customer Marathi/Hindi me zyada engage karta — English-only
post = aadhi reach. free-LLM translate (brand names/numbers preserve), fallback
original. Import-safe, kabhi raise nahi.
"""

from __future__ import annotations

import json
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

LANGS = {"hinglish": "Hinglish (Roman script)", "hindi": "Hindi (Devanagari)", "marathi": "Marathi (Devanagari)"}


async def translate_post(caption: str, langs: list[str] | None = None) -> dict[str, Any]:
    """Caption ko selected languages me convert karo. Fallback = original sab me.
    Kabhi raise nahi."""
    cap = (caption or "").strip()
    if not cap:
        return {"ok": False, "error": "caption do"}
    want = [lg for lg in (langs or list(LANGS)) if lg in LANGS]
    out: dict[str, str] = {}
    try:
        from app.voice_agent.free_ai import chat

        spec = ", ".join(f'"{lg}"' for lg in want)
        raw, _ = await chat(
            (
                "Tu social media translator hai. Caption ko naturally translate kar — "
                "word-by-word nahi, LOCAL feel ke saath. Brand names, numbers, links, "
                f"emojis, hashtags SAME rakho. JSON de: {{{spec}}} keys ke saath."
            ),
            [{"role": "user", "content": cap[:600]}],
            max_tokens=500,
        )
        s, e = raw.find("{"), raw.rfind("}")
        if s >= 0 and e > s:
            parsed = json.loads(raw[s : e + 1])
            for lg in want:
                v = str(parsed.get(lg, "")).strip()
                if v:
                    out[lg] = v[:800]
    except Exception as e:
        logger.debug(f"[multilang] llm fallback: {e}")
    for lg in want:
        out.setdefault(lg, cap)  # fallback = original
    return {"ok": True, "original": cap, "versions": out, "langs": want}
