"""Audio jingle generator (AdBanao ke 1.5L jingles ka free-stack jawab).

niche + business → free-LLM se 15-20 sec punchy Hinglish radio-ad script →
EdgeTTS mp3 → optional ffmpeg loudness-normalize (ffmpeg ho to). Output:
data/jingles/jingle_<id>.mp3 — HUMAN use karta (WhatsApp status, reel audio,
shop speaker). Ban-safe: sirf file banti hai.

⚠️ HEAVY-ish (LLM + TTS network) — import time pe KUCH nahi chalta; sirf
endpoint/worker se call karo. `available()` dep-check; missing = error dict,
NEVER raises (reel_video.py pattern).
"""

from __future__ import annotations

import os
import re
import shutil
import time
import uuid
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_OUT_DIR = os.path.join("data", "jingles")
_NAME_RE = re.compile(r"jingle_[a-f0-9]{10}\.mp3")

# lang → default EdgeTTS voice (sab free). Unknown/missing → Swara (hi-IN).
_LANG_VOICES = {
    "hinglish": "hi-IN-SwaraNeural",
    "hindi": "hi-IN-SwaraNeural",
    "marathi": "mr-IN-AarohiNeural",
    "gujarati": "gu-IN-DhwaniNeural",
    "telugu": "te-IN-ShrutiNeural",
    "tamil": "ta-IN-PallaviNeural",
    "bengali": "bn-IN-TanishaaNeural",
    "punjabi": "pa-IN-VaaniNeural",
    "kannada": "kn-IN-SapnaNeural",
}
_DEFAULT_VOICE = "hi-IN-SwaraNeural"
_VOICE_RE = re.compile(r"^[A-Za-z]{2}-[A-Za-z]{2}-[A-Za-z0-9]+$")

# ~2.3 words/sec conversational Hindi TTS
_WORDS_PER_SEC = 2.3


def available() -> dict[str, Any]:
    """Dep-check — edge-tts zaroori, ffmpeg optional (normalize ke liye)."""
    out: dict[str, Any] = {"ffmpeg": bool(shutil.which("ffmpeg"))}
    try:
        import edge_tts  # noqa: F401

        out["edge_tts"] = True
    except Exception:
        out["edge_tts"] = False
    out["ok"] = out["edge_tts"]  # ffmpeg optional
    return out


def estimate_duration(script: str) -> float:
    """Script → approx seconds (TTS bolne ki speed se)."""
    words = len((script or "").split())
    return round(words / _WORDS_PER_SEC, 1) if words else 0.0


def safe_file_path(name: str) -> str | None:
    """Regex-locked filename → full path (serve route ke liye). Traversal-proof
    (ai_image.cache_file_path pattern)."""
    if not _NAME_RE.fullmatch(name or ""):
        return None
    p = os.path.join(_OUT_DIR, name)
    return p if os.path.exists(p) else None


def pick_voice(lang: str = "hinglish", voice: str | None = None) -> str:
    """Lang ya explicit voice → safe EdgeTTS voice name."""
    v = (voice or "").strip()
    if v and _VOICE_RE.match(v):
        return v
    return _LANG_VOICES.get((lang or "hinglish").strip().lower(), _DEFAULT_VOICE)


def _fallback_script(niche: str, business_name: str, offer: str, lang: str) -> str:
    """LLM fail ho to static punchy script — kabhi empty nahi."""
    biz = (business_name or "Aapka Business").strip()
    nic = (niche or "business").replace("_", " ").strip()
    parts = [
        f"{biz}! Aapke sheher ka sabse bharosemand {nic} naam.",
        (offer or "").strip() or "Quality kaam, sahi daam — bina tension.",
        f"Toh der kis baat ki? Aaj hi call karo {biz} ko. {biz} — kaam pakka, vaada pakka!",
    ]
    return " ".join(p for p in parts if p)


async def _llm_script(niche: str, business_name: str, offer: str, lang: str) -> str:
    """free-LLM se radio-jingle script. Fail/empty = "" (caller fallback use kare)."""
    try:
        from app.voice_agent.free_ai import chat

        lang_line = {
            "hindi": "Pure Hindi (Devanagari) me likho.",
            "marathi": "Marathi (Devanagari) me likho.",
            "gujarati": "Gujarati (native ગુજરાતી script) me likho.",
            "telugu": "Telugu (native తెలుగు script) me likho.",
            "tamil": "Tamil (native தமிழ் script) me likho.",
            "bengali": "Bengali (native বাংলা script) me likho.",
            "punjabi": "Punjabi (native ਗੁਰਮੁਖੀ script) me likho.",
            "kannada": "Kannada (native ಕನ್ನಡ script) me likho.",
        }.get((lang or "hinglish").lower(), "Hinglish (Roman script) me likho.")
        system = (
            "Tu Indian local-radio ad writer hai. 15-20 second ka PUNCHY jingle "
            "script likh — catchy hook, business naam 2 baar, ek chhota rhyme/tagline, "
            "end me clear call-to-action. 35-50 words MAX. " + lang_line + " "
            "Sirf bolne wala text de — koi stage direction, quotes, emoji ya headings nahi."
        )
        user = f"Business: {business_name or 'local business'} | Niche: {niche or 'general'}"
        if (offer or "").strip():
            user += f" | Offer: {offer.strip()}"
        raw, _provider = await chat(system, [{"role": "user", "content": user}], max_tokens=160)
        script = (raw or "").strip().strip('"').strip()
        # sanity: 8-80 words warna fallback
        n = len(script.split())
        return script if 8 <= n <= 80 else ""
    except Exception as e:
        logger.debug(f"[jingle] llm fallback: {e}")
        return ""


def _normalize_audio(path: str) -> bool:
    """ffmpeg ho to loudness-normalize (radio feel). Fail = original chalta. Never raises."""
    if not shutil.which("ffmpeg"):
        return False
    tmp = path + ".norm.mp3"
    try:
        from app.marketing.reel_video import _ffmpeg  # reuse, duplicate nahi

        ok = _ffmpeg(
            [
                "-i",
                path,
                "-af",
                "loudnorm=I=-16:TP=-1.5:LRA=11",
                "-c:a",
                "libmp3lame",
                "-q:a",
                "4",
                tmp,
            ]
        )
        if ok and os.path.exists(tmp) and os.path.getsize(tmp) > 100:
            os.replace(tmp, path)
            return True
    except Exception as e:
        logger.debug(f"[jingle] normalize skip: {e}")
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass
    return False


async def generate_jingle(
    niche: str,
    business_name: str,
    offer: str | None = None,
    lang: str = "hinglish",
    voice: str | None = None,
) -> dict[str, Any]:
    """15-20 sec audio jingle banao. Returns {ok, file, name, script, duration_est_s,...}
    ya {ok: False, error}. Kabhi raise nahi karta."""
    avail = available()
    if not avail["ok"]:
        return {
            "ok": False,
            "error": "edge-tts installed nahi — jingle audio nahi ban sakta.",
            "available": avail,
        }

    t0 = time.time()
    try:
        script = await _llm_script(
            niche or "", business_name or "", offer or "", lang or "hinglish"
        )
        provider = "llm" if script else "fallback"
        if not script:
            script = _fallback_script(
                niche or "", business_name or "", offer or "", lang or "hinglish"
            )

        vo = pick_voice(lang, voice)
        name = f"jingle_{uuid.uuid4().hex[:10]}.mp3"
        os.makedirs(_OUT_DIR, exist_ok=True)
        path = os.path.join(_OUT_DIR, name)

        import edge_tts

        try:
            await edge_tts.Communicate(script, vo).save(path)
        except Exception as e:
            # exotic voice fail (e.g. punjabi voice account pe nahi) → Swara retry
            logger.warning(f"[jingle] voice {vo} fail ({e}) — Swara retry")
            vo = _DEFAULT_VOICE
            await edge_tts.Communicate(script, vo).save(path)

        if not (os.path.exists(path) and os.path.getsize(path) > 100):
            return {"ok": False, "error": "TTS audio save fail — dobara try karo."}

        normalized = _normalize_audio(path)
        return {
            "ok": True,
            "file": path,
            "name": name,
            "script": script,
            "script_source": provider,
            "voice": vo,
            "lang": (lang or "hinglish").lower(),
            "duration_est_s": estimate_duration(script),
            "normalized": normalized,
            "size_kb": os.path.getsize(path) // 1024,
            "took_s": round(time.time() - t0, 1),
            "note": "WhatsApp status / reel audio / shop speaker pe HUMAN use kare — auto-publish nahi.",
        }
    except Exception as e:
        logger.warning(f"generate_jingle failed: {e}")
        return {"ok": False, "error": str(e)[:200]}
