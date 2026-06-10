"""Multi-language post (AdBanao ka edge neutralize) — ek caption → 9 bhashayein.

Hinglish/Hindi/Marathi (original 3) + Gujarati/Telugu/Tamil/Bengali/Punjabi/
Kannada (native scripts) — AdBanao ke "10 languages" ka free-stack jawab.
Local business ka customer apni bhasha me zyada engage karta — English-only
post = aadhi reach. free-LLM translate (brand names/numbers preserve), fallback
original. Import-safe, kabhi raise nahi.

Backward-compat: `langs=None` ab bhi sirf original 3 (DEFAULT_LANGS) deta —
existing callers (growth.py /content/multilang) unchanged. Naye langs explicit
list me maango.
"""

from __future__ import annotations

import json
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

LANGS = {
    "hinglish": "Hinglish (Roman script)",
    "hindi": "Hindi (Devanagari script)",
    "marathi": "Marathi (Devanagari script)",
    "gujarati": "Gujarati (native ગુજરાતી script)",
    "telugu": "Telugu (native తెలుగు script)",
    "tamil": "Tamil (native தமிழ் script)",
    "bengali": "Bengali (native বাংলা script)",
    "punjabi": "Punjabi (native ਗੁਰਮੁਖੀ script)",
    "kannada": "Kannada (native ಕನ್ನಡ script)",
}

# langs=None par YAHI default — purane callers ka output shape/coverage same rahe.
DEFAULT_LANGS = ["hinglish", "hindi", "marathi"]


def supported_langs() -> list[str]:
    """Saari supported language keys (UI dropdowns ke liye)."""
    return list(LANGS)


async def translate_post(caption: str, langs: list[str] | None = None) -> dict[str, Any]:
    """Caption ko selected languages me convert karo. Fallback = original sab me.
    Kabhi raise nahi."""
    cap = (caption or "").strip()
    if not cap:
        return {"ok": False, "error": "caption do"}
    want = [lg for lg in (langs or DEFAULT_LANGS) if lg in LANGS]
    if not want:
        want = list(DEFAULT_LANGS)
    out: dict[str, str] = {}
    try:
        from app.voice_agent.free_ai import chat

        spec = ", ".join(f'"{lg}"' for lg in want)
        script_spec = "; ".join(f"{lg} = {LANGS[lg]}" for lg in want)
        raw, _ = await chat(
            (
                "Tu social media translator hai. Caption ko naturally translate kar — "
                "word-by-word nahi, LOCAL feel ke saath. Brand names, numbers, links, "
                f"emojis, hashtags SAME rakho. Har language apni NATIVE script me: {script_spec}. "
                f"JSON de: {{{spec}}} keys ke saath."
            ),
            [{"role": "user", "content": cap[:600]}],
            max_tokens=min(2000, max(500, 220 * len(want))),
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
